import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
SCENE_VALIDATOR = REPO / "skills" / "deepwhite-scene-asset-planner" / "scripts" / "validate_scene_asset_plan.py"
SCENE_EXAMPLE = REPO / "skills" / "deepwhite-scene-asset-planner" / "templates" / "scene-asset-plan.example.json"
ANGLE_VALIDATOR = REPO / "skills" / "deepwhite-image-prompt-builder" / "scripts" / "validate_angle_pack.py"
ANGLE_EXAMPLE = REPO / "skills" / "deepwhite-image-prompt-builder" / "templates" / "angle-pack-manifest.example.json"
ENV_VALIDATOR = REPO / "skills" / "deepwhite-shotlist-builder-zh-user" / "scripts" / "validate_environment_continuity.py"
RETRY_GUARD = REPO / "workspaces" / "drama-producer" / "scripts" / "asset_retry_guard.py"
PIPELINE_EVIDENCE = REPO / "skills" / "deepwhite-00-novel-series-orchestrator" / "scripts" / "validate_episode_pipeline.py"


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def run(script: Path, *args: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(script), *map(str, args)], text=True, capture_output=True, check=False)


class ProductionSafetyGateTests(unittest.TestCase):
    def test_scene_coverage_uses_authoritative_scene_index(self):
        plan = json.loads(SCENE_EXAMPLE.read_text(encoding="utf-8"))
        scene_index = {
            "schema_version": "1.0",
            "scenes": [
                {
                    "scene_id": row["scene_id"], "scene_order": row["scene_order"],
                    "expected_duration_seconds": row["expected_duration_seconds"],
                    "movement_required": False,
                }
                for row in plan["scene_bindings"]
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan_path = root / "plan.json"; index_path = root / "scene_index.json"; gate_path = root / "gate.json"
            write_json(plan_path, plan); write_json(index_path, scene_index)
            passed = run(SCENE_VALIDATOR, "--plan", plan_path, "--scene-index", index_path, "--gate-out", gate_path)
            self.assertEqual(passed.returncode, 0, passed.stdout + passed.stderr)
            plan["scene_bindings"].pop()
            write_json(plan_path, plan)
            failed = run(SCENE_VALIDATOR, "--plan", plan_path, "--scene-index", index_path, "--gate-out", gate_path)
            self.assertEqual(failed.returncode, 2)
            report = json.loads(gate_path.read_text(encoding="utf-8"))
            self.assertEqual(report["deterministic_checks"]["missing_scene_ids"], ["SC05"])

    def test_movement_scene_requires_distinct_route_anchors(self):
        plan = json.loads(SCENE_EXAMPLE.read_text(encoding="utf-8"))
        index_rows = []
        for row in plan["scene_bindings"]:
            index_rows.append({
                "scene_id": row["scene_id"], "scene_order": row["scene_order"],
                "expected_duration_seconds": row["expected_duration_seconds"],
                "movement_required": row["scene_id"] == "SC04",
            })
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); plan_path = root / "plan.json"; index_path = root / "index.json"
            write_json(plan_path, plan); write_json(index_path, {"scenes": index_rows})
            failed = run(SCENE_VALIDATOR, "--plan", plan_path, "--scene-index", index_path, "--json")
            self.assertEqual(failed.returncode, 2)
            self.assertIn("至少需要", failed.stdout)

    def test_angle_pack_requires_separate_standard_assets(self):
        manifest = json.loads(ANGLE_EXAMPLE.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "angles.json"; write_json(path, manifest)
            passed = run(ANGLE_VALIDATOR, "--manifest", path)
            self.assertEqual(passed.returncode, 0, passed.stdout + passed.stderr)
            manifest["packs"][0]["assets"][0]["contains_multiple_independent_assets"] = True
            write_json(path, manifest)
            failed = run(ANGLE_VALIDATOR, "--manifest", path)
            self.assertEqual(failed.returncode, 2)
            self.assertIn("contains_multiple_independent_assets", failed.stdout)

    def test_environment_route_requires_verified_predecessor_reference(self):
        handoff = {
            "gate_passed": True,
            "scene_bindings": {"SC01": {
                "location_id": "LOC-ROUTE",
                "route_anchors": [
                    {"route_anchor_id": "RA1", "role": "departure", "location_asset_id": "A1", "predecessor_environment_asset_id": None},
                    {"route_anchor_id": "RA2", "role": "arrival", "location_asset_id": "A2", "predecessor_environment_asset_id": "A1"},
                ],
            }},
        }
        assets = {"assets": [{"asset_id": "A1", "status": "approved"}, {"asset_id": "A2", "status": "approved"}]}
        base = {
            "inherited_location_id": "LOC-ROUTE", "character_position": "center", "camera_position": "front",
            "camera_view_direction": "north", "route_direction": "east", "landmark_ids": ["TREE"],
            "landmark_world_relationships": {"TREE": "north_of_path"}, "expected_screen_position_and_scale": "mid-left medium",
            "distance_change": "closer", "landmark_parallax": "moves_left", "justified_occlusion": "none",
        }
        n1 = {**base, **handoff["scene_bindings"]["SC01"]["route_anchors"][0]}
        n2 = {**base, **handoff["scene_bindings"]["SC01"]["route_anchors"][1], "reference_evidence": {"provider_reference_verified": True, "reference_asset_ids": ["A1"]}}
        spatial = {"environment_continuity_map": {"routes": [{"scene_id": "SC01", "nodes": [n1, n2]}]}}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); hp = root / "h.json"; ap = root / "a.json"; sp = root / "s.json"
            write_json(hp, handoff); write_json(ap, assets); write_json(sp, spatial)
            passed = run(ENV_VALIDATOR, "--handoff", hp, "--assets", ap, "--spatial", sp)
            self.assertEqual(passed.returncode, 0, passed.stdout + passed.stderr)
            del spatial["environment_continuity_map"]["routes"][0]["nodes"][1]["reference_evidence"]
            write_json(sp, spatial)
            failed = run(ENV_VALIDATOR, "--handoff", hp, "--assets", ap, "--spatial", sp)
            self.assertEqual(failed.returncode, 2)
            self.assertIn("verified predecessor", failed.stdout)

    def test_retry_guard_blocks_same_failed_prompt_across_new_job(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            jobs = root / "dispatch" / "asset_jobs"
            base_asset = {
                "asset_id": "A1", "asset_lineage_id": "CHAR-A", "requirement_sha256": "a" * 64,
                "revision_reason_code": "initial", "prompt": "front portrait", "angle_id": "front",
            }
            first = jobs / "J1.json"; write_json(first, {"job_id": "J1", "assets": [base_asset]})
            self.assertEqual(run(RETRY_GUARD, "reserve", "--job", first).returncode, 0)
            rejected = run(RETRY_GUARD, "update", "--job", first, "--status", "rejected", "--reason-code", "wrong_identity")
            self.assertEqual(rejected.returncode, 0, rejected.stdout + rejected.stderr)
            second_asset = copy.deepcopy(base_asset); second_asset["revision_reason_code"] = "wrong_identity_fix"
            second = jobs / "J2.json"; write_json(second, {"job_id": "J2", "assets": [second_asset]})
            blocked = run(RETRY_GUARD, "check", "--job", second)
            self.assertEqual(blocked.returncode, 2)
            self.assertIn("不得原样重复", blocked.stdout)

    def test_inflight_v12_contract_keeps_original_five_gate_shape(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            contract = root / "input" / "production_pipeline_contract.json"
            write_json(contract, {"schema_version": "1.2", "pipeline_profile": "scene_bound_auto_v1.2"})
            legacy = run(PIPELINE_EVIDENCE, "--project-root", root)
            self.assertEqual(json.loads(legacy.stdout)["required_gate_count"], 5)
            write_json(contract, {"schema_version": "1.3", "pipeline_profile": "scene_bound_auto_v1.2"})
            current = run(PIPELINE_EVIDENCE, "--project-root", root)
            self.assertEqual(json.loads(current.stdout)["required_gate_count"], 8)


if __name__ == "__main__":
    unittest.main()
