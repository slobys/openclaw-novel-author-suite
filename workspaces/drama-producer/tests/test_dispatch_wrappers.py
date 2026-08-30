import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).parents[3]
WORKSPACE = Path(__file__).parents[1]
ASSET_WRAPPER = WORKSPACE / "scripts" / "submit_asset_job.py"
VIDEO_WRAPPER = WORKSPACE / "scripts" / "submit_video_job.py"


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


class DispatchWrapperTests(unittest.TestCase):
    def test_asset_wrapper_dry_run_uses_prompt_coverage_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "project"
            requirements_source = REPO_ROOT / "skills" / "deepwhite-image-prompt-builder" / "templates" / "location-asset-requirements.example.json"
            manifest_source = REPO_ROOT / "skills" / "deepwhite-image-prompt-builder" / "templates" / "location-asset-prompt-manifest.example.json"
            requirements = json.loads(requirements_source.read_text(encoding="utf-8"))
            manifest = json.loads(manifest_source.read_text(encoding="utf-8"))
            write_json(project / "assets" / "location_asset_requirements.json", requirements)
            write_json(project / "assets" / "location_asset_prompt_manifest.json", manifest)

            prompt_asset = manifest["assets"][0]
            job_asset = {
                **prompt_asset,
                "asset_role": "video_reference",
                "asset_kind": "location",
                "angle_id": "wide_establishing",
                "layout_type": "single_view_clean",
                "contains_multiple_independent_assets": False,
                "aspect_ratio": "16:9",
            }
            job = {
                "schema_version": "1.0",
                "job_id": "DEMO_ASSET_001",
                "project_id": "DEMO",
                "source": "openclaw",
                "defaults": {
                    "model": "gemini-3.1-flash-image",
                    "aspect_ratio": "16:9",
                    "image_size": "2K",
                },
                "assets": [job_asset],
            }
            job_path = project / "dispatch" / "asset_jobs" / "DEMO_ASSET_001.json"
            write_json(job_path, job)
            result = subprocess.run(
                [sys.executable, str(ASSET_WRAPPER), "--job", str(job_path), "--dry-run"],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('"dry_run": true', result.stdout)

    def test_video_wrapper_dry_run_passes_scene_handoff_arguments(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "project"
            video_skill = REPO_ROOT / "skills" / "deepwhite-n8n-video-dispatcher"
            job_path = project / "dispatch" / "video_jobs" / "video-job.json"
            actual_path = project / "assets" / "actual_asset_manifest.json"
            handoff_path = project / "handoffs" / "scene_asset_handoff.json"
            job_path.parent.mkdir(parents=True, exist_ok=True)
            actual_path.parent.mkdir(parents=True, exist_ok=True)
            handoff_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(video_skill / "templates" / "video-job.example.json", job_path)
            shutil.copy2(video_skill / "templates" / "actual-asset-manifest.example.json", actual_path)
            shutil.copy2(video_skill / "templates" / "scene-asset-handoff.example.json", handoff_path)

            job = json.loads(job_path.read_text(encoding="utf-8"))
            referenced = {asset_id for clip in job["clips"] for asset_id in clip["reference_asset_ids"]}
            refs = []
            for asset_id in sorted(referenced):
                scope = "character_single" if "-CH-" in asset_id else "location_single_composition"
                refs.append(
                    {
                        "asset_id": asset_id,
                        "filename": f"{asset_id}.png",
                        "asset_role": "video_reference",
                        "layout_type": "single_view_clean",
                        "reference_scope": scope,
                        "contains_text_or_annotations": False,
                        "contains_multiple_independent_assets": False,
                        "video_reference_eligible": True,
                    }
                )
            write_json(
                project / "assets" / "video_reference_manifest.json",
                {"schema_version": "1.0", "gate_status": "passed", "assets": refs},
            )

            result = subprocess.run(
                [sys.executable, str(VIDEO_WRAPPER), "--job", str(job_path), "--dry-run"],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('"dry_run": true', result.stdout)
            self.assertTrue((project / "gates" / "video_scene_binding_gate.json").is_file())


if __name__ == "__main__":
    unittest.main()
