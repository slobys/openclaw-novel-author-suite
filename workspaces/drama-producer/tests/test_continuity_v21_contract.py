import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = ROOT.parents[1]
SKILLS_ROOT = PACKAGE_ROOT / "skills"
WORLD_VALIDATOR = SKILLS_ROOT / "deepwhite-continuity-worldstate-zh" / "scripts" / "validate_world_state_bundle.py"
JOB_VALIDATOR = SKILLS_ROOT / "deepwhite-n8n-asset-dispatcher" / "scripts" / "validate-continuity-job.mjs"
JOB_SENDER = SKILLS_ROOT / "deepwhite-n8n-asset-dispatcher" / "scripts" / "send-continuity-job-to-n8n.mjs"
JOB_EXAMPLE = SKILLS_ROOT / "deepwhite-n8n-asset-dispatcher" / "templates" / "asset-job.continuity.example.json"
PACKAGER_VALIDATOR = SKILLS_ROOT / "deepwhite-image-prompt-builder" / "scripts" / "validate_packager_handoff.py"
N8N_WORKFLOW = ROOT / "integration" / "deepwhite-continuity" / "n8n" / "OpenClaw连续资产依赖生图_参考图注入版_v2.json"


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


class ContinuityV21ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("world_validator", WORLD_VALIDATOR)
        cls.world_validator = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(cls.world_validator)
        packager_spec = importlib.util.spec_from_file_location("packager_validator", PACKAGER_VALIDATOR)
        cls.packager_validator = importlib.util.module_from_spec(packager_spec)
        assert packager_spec and packager_spec.loader
        packager_spec.loader.exec_module(cls.packager_validator)
        cls.node = shutil.which("node")

    def test_workflow_keeps_scene_authority_and_final_video_completion(self):
        text = (ROOT / "drama-workflow.yaml").read_text(encoding="utf-8")
        required_in_order = [
            "stage_10_screenplay:",
            "stage_20_continuity:",
            "stage_25_scene_asset_plan:",
            "stage_30_base_continuity_design:",
            "stage_35_base_asset_dispatch:",
            "stage_50_final_shotlist:",
            "stage_55_shot_binding_gate:",
            "stage_70_video_dispatch:",
            "stage_90_final_composition:",
            "stage_100_series_commit:",
        ]
        positions = [text.index(item) for item in required_in_order]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("pipeline_profile: scene_bound_auto_v1.2", text)
        self.assertIn("success_status: final_video_ready", text)
        self.assertIn("forbid_asset_only_completion: true", text)
        self.assertIn("conditional_requires:\n    series_project:", text)
        required_review = text.split("human_review:", 1)[1]
        self.assertNotIn("required_before:\n    - video_generation", required_review)

    def make_world_bundle(self, root: Path):
        write_json(root / "script" / "scene_index.json", {
            "project_id": "demo",
            "scenes": [{"scene_id": "SC01", "scene_order": 1}],
        })
        write_json(root / "world" / "characters.json", {
            "project_id": "demo",
            "characters": [{"character_id": "CHAR_A", "name": "甲", "identity_fingerprint": {}, "current_state": {}}],
        })
        write_json(root / "world" / "locations.json", {
            "project_id": "demo",
            "locations": [{"location_id": "LOC_A", "name": "屋内", "current_state": {}}],
        })
        write_json(root / "world" / "props.json", {
            "project_id": "demo",
            "props": [{"prop_id": "PROP_A", "name": "钥匙", "current_state": {}}],
        })
        write_json(root / "continuity" / "continuity_handoff.json", {
            "project_id": "demo",
            "source_scene_index": "script/scene_index.json",
            "scenes": [{
                "scene_id": "SC01",
                "character_ids": ["CHAR_A"],
                "location_id": "LOC_A",
                "prop_ids": ["PROP_A"],
                "state_before": {},
                "state_changes": {},
                "state_after": {},
                "evidence": ["剧本证据"],
            }],
        })

    def test_world_state_bundle_has_full_scene_coverage(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.make_world_bundle(root)
            result = self.world_validator.validate(root, root / "script" / "scene_index.json")
            self.assertTrue(result["passed"], result["errors"])
            self.assertEqual(1.0, result["scene_coverage_ratio"])
            self.assertTrue(result["zero_unknown_references"])

    def test_packager_only_preserves_every_asset_and_binding(self):
        job = json.loads(JOB_EXAMPLE.read_text(encoding="utf-8"))
        expanded = {"expanded_assets": json.loads(json.dumps(job["assets"], ensure_ascii=False))}
        result = self.packager_validator.validate(expanded, job)
        self.assertTrue(result["passed"], result["errors"])
        self.assertEqual(1.0, result["coverage_ratio"])

        changed = json.loads(json.dumps(job, ensure_ascii=False))
        changed["assets"][0]["scene_id"] = "SC_CHANGED"
        result = self.packager_validator.validate(expanded, changed)
        self.assertFalse(result["passed"])
        self.assertTrue(any("scene_id changed" in item for item in result["errors"]))

    @unittest.skipUnless(shutil.which("node"), "node is required")
    def test_job_validator_and_dry_run_need_no_secrets(self):
        validated = subprocess.run([self.node, str(JOB_VALIDATOR), str(JOB_EXAMPLE)], capture_output=True, text=True)
        self.assertEqual(0, validated.returncode, validated.stderr + validated.stdout)
        env = os.environ.copy()
        env.pop("N8N_ASSET_WEBHOOK_URL", None)
        env.pop("N8N_ASSET_WEBHOOK_SECRET", None)
        dry_run = subprocess.run([self.node, str(JOB_SENDER), str(JOB_EXAMPLE), "--dry-run"], capture_output=True, text=True, env=env)
        self.assertEqual(0, dry_run.returncode, dry_run.stderr + dry_run.stdout)
        self.assertIn('"validation": "passed"', dry_run.stdout)

    @unittest.skipUnless(shutil.which("node"), "node is required")
    def test_job_validator_rejects_path_and_fake_hash(self):
        with tempfile.TemporaryDirectory() as temp:
            job = json.loads(JOB_EXAMPLE.read_text(encoding="utf-8"))
            job["project_id"] = "../escape"
            job["assets"][0]["filename"] = "../escape.png"
            job["assets"][0]["lock_hash"] = "sha256:" + "0" * 64
            target = Path(temp) / "bad-job.json"
            write_json(target, job)
            result = subprocess.run([self.node, str(JOB_VALIDATOR), str(target)], capture_output=True, text=True)
            self.assertNotEqual(0, result.returncode)
            self.assertIn("lock_hash mismatch", result.stdout)
            self.assertIn("safe image filename", result.stdout)

    def test_n8n_summary_fails_closed(self):
        workflow = json.loads(N8N_WORKFLOW.read_text(encoding="utf-8"))
        nodes = {node["name"]: node for node in workflow["nodes"]}
        summary_code = nodes["汇总任务结果"]["parameters"]["jsCode"]
        validation_code = nodes["校验任务并拓扑排序"]["parameters"]["jsCode"]
        response_options = nodes["返回结果"]["parameters"]["options"]
        self.assertIn("failed_count === 0", summary_code)
        self.assertIn("all_required_assets_approved", summary_code)
        self.assertIn("shared_asset_root 禁止由 Payload 指定", validation_code)
        self.assertEqual("={{ $json.ok ? 200 : 422 }}", response_options["responseCode"])


if __name__ == "__main__":
    unittest.main()
