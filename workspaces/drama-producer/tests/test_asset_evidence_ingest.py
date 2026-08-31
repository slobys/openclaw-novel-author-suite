import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


WORKSPACE = Path(__file__).resolve().parents[1]
INGEST = WORKSPACE / "scripts" / "ingest_asset_evidence.py"


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def run(project: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(INGEST), "--project-root", str(project)],
        text=True,
        capture_output=True,
        check=False,
    )


class AssetEvidenceIngestTests(unittest.TestCase):
    def fixture(self, root: Path, *, ambiguity=None) -> tuple[Path, Path, dict]:
        project = root / "project"
        image = root / "shared" / "A1.png"
        image.parent.mkdir(parents=True)
        image.write_bytes(b"deterministic-image-fixture")
        digest = "sha256:" + hashlib.sha256(image.read_bytes()).hexdigest()
        planned = {
            "asset_id": "A1",
            "category": "character",
            "asset_role": "video_reference",
            "asset_kind": "character",
            "layout_type": "single_view_clean",
            "contains_multiple_independent_assets": False,
            "lock_hash": "lock-A1",
            "reference_inputs": [],
            "filename": "A1.png",
        }
        write_json(project / "project.json", {"project_id": "DEMO"})
        write_json(project / "assets" / "expanded_asset_list.base.json", {"assets": [planned]})
        write_json(project / "assets" / "expanded_asset_list.shot.json", {"assets": []})
        write_json(
            project / "assets" / "reference_registry.json",
            {
                "project_id": "DEMO",
                "assets": {
                    "A1": {
                        **planned,
                        "status": "approved",
                        "job_id": "JOB1",
                        "payload_sha256": "payload-hash",
                        "path": str(image),
                        "file_size": image.stat().st_size,
                        "sha256": digest,
                        "qa_evidence": {
                            "schema_version": "1.0",
                            "review_authority": "n8n_structured_visual_qa",
                            "pass": True,
                            "score": 92,
                            "hard_requirement_failures": [],
                            "production_safety": {
                                "reference_consistency_checked": False,
                                "identity_consistency_applicable": False,
                                "identity_consistent": True,
                                "scene_topology_applicable": False,
                                "scene_topology_consistent": True,
                                "single_view_clean": True,
                                "contains_multiple_independent_assets": False,
                                "contains_text_or_annotations": False,
                                "ambiguity_reasons": ambiguity or [],
                                "evidence_summary": "clean single character view",
                            },
                        },
                    }
                },
            },
        )
        return project, image, planned

    def test_complete_n8n_evidence_skips_agent_visual_review(self):
        with tempfile.TemporaryDirectory() as directory:
            project, _, _ = self.fixture(Path(directory))
            result = run(project)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            gate = json.loads((project / "gates" / "asset_evidence_gate.json").read_text(encoding="utf-8"))
            self.assertTrue(gate["passed"])
            self.assertEqual(gate["manual_visual_review_required_count"], 0)
            manifest = json.loads((project / "assets" / "actual_asset_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["source_authority"], "n8n_reference_registry_with_structured_qa")
            self.assertEqual(manifest["assets"][0]["asset_id"], "A1")

    def test_ambiguity_routes_only_that_asset_to_exception_review(self):
        with tempfile.TemporaryDirectory() as directory:
            project, _, _ = self.fixture(Path(directory), ambiguity=["左手轮廓被遮挡，无法确认"])
            result = run(project)
            self.assertEqual(result.returncode, 2)
            report = json.loads((project / "review" / "asset_review_exceptions.json").read_text(encoding="utf-8"))
            self.assertEqual(report["exception_count"], 1)
            self.assertEqual(report["exceptions"][0]["asset_id"], "A1")

    def test_hash_mismatch_fails_without_semantic_re_review(self):
        with tempfile.TemporaryDirectory() as directory:
            project, image, _ = self.fixture(Path(directory))
            image.write_bytes(b"changed-after-registry")
            result = run(project)
            self.assertEqual(result.returncode, 2)
            gate = json.loads((project / "gates" / "asset_evidence_gate.json").read_text(encoding="utf-8"))
            self.assertIn("ASSET_SHA256_MISMATCH", {item["code"] for item in gate["errors"]})


if __name__ == "__main__":
    unittest.main()
