import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "pipeline_state.py"


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


class PipelineStateTests(unittest.TestCase):
    def run_state(self, *args: object) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *map(str, args)],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_stage_checkpoint_and_invalidation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = self.run_state("init", "--project-root", root, "--project-id", "DEMO")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

            screenplay = root / "script" / "episode_script.md"
            continuity = root / "continuity" / "continuity_handoff.json"
            screenplay.parent.mkdir(parents=True, exist_ok=True)
            screenplay.write_text("SC01", encoding="utf-8")
            write_json(continuity, {"scene_id": "SC01"})
            for stage, artifact in ((10, screenplay), (20, continuity)):
                completed = self.run_state(
                    "complete-stage",
                    "--project-root",
                    root,
                    "--stage",
                    stage,
                    "--artifact",
                    artifact,
                )
                self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)

            handoff = root / "handoffs" / "scene_asset_handoff.json"
            gate = root / "gates" / "scene_asset_coverage_gate.json"
            write_json(handoff, {"gate_passed": True, "scene_bindings": {"SC01": {}}})
            write_json(gate, {"passed": True, "scene_coverage_ratio": 1.0})
            result = self.run_state(
                "complete-stage",
                "--project-root",
                root,
                "--stage",
                25,
                "--artifact",
                handoff,
                "--gate",
                gate,
                "--status",
                "scene_assets_planned",
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

            result = self.run_state(
                "invalidate",
                "--project-root",
                root,
                "--from-stage",
                25,
                "--reason",
                "continuity_changed",
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            state = json.loads((root / "state" / "pipeline_state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["stages"]["25"]["status"], "pending")
            self.assertEqual(state["current_stage"], 20)

    def test_same_job_id_cannot_change_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual(
                self.run_state("init", "--project-root", root, "--project-id", "DEMO").returncode,
                0,
            )
            payload = root / "dispatch" / "asset_jobs" / "A1.json"
            write_json(payload, {"job_id": "A1"})
            first = self.run_state(
                "record-job",
                "--project-root",
                root,
                "--kind",
                "asset",
                "--job-id",
                "A1",
                "--status",
                "prepared",
                "--payload",
                payload,
            )
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            write_json(payload, {"job_id": "A1", "changed": True})
            second = self.run_state(
                "record-job",
                "--project-root",
                root,
                "--kind",
                "asset",
                "--job-id",
                "A1",
                "--status",
                "validated",
                "--payload",
                payload,
            )
            self.assertNotEqual(second.returncode, 0)
            self.assertIn("payload_sha256", second.stderr)


if __name__ == "__main__":
    unittest.main()
