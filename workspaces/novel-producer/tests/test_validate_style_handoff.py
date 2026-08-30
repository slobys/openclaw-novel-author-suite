import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "validate_style_handoff.py"
OPENCLAW_STATE_DIR = Path(os.environ.get("OPENCLAW_STATE_DIR", Path.home() / ".openclaw"))
DEPLOYED_DISPATCHER = OPENCLAW_STATE_DIR / "skills" / "deepwhite-n8n-asset-dispatcher" / "scripts" / "send-assets-to-n8n.mjs"
LOCAL_DISPATCHER = Path(__file__).parents[3] / "skills" / "deepwhite-n8n-asset-dispatcher" / "scripts" / "send-assets-to-n8n.mjs"
DISPATCHER = DEPLOYED_DISPATCHER if DEPLOYED_DISPATCHER.is_file() else LOCAL_DISPATCHER


def canonical_hash(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


class StyleHandoffValidatorTests(unittest.TestCase):
    def contract(self):
        return {
            "contract_version": "1.0",
            "authority": "drama-producer",
            "mode": "user_locked",
            "raw_user_request": "国风半写实厚涂 2D",
            "source": "user_explicit_request",
            "must_preserve": ["2D", "国风", "厚涂"],
            "must_not_transform_to": ["3D", "PBR"],
            "story_visual_context": {"tone": ["克制"]},
            "reference_assets": [],
        }

    def make_series(self, root, contract=None, episode_hash=None, schema_version="1.2"):
        contract = contract or self.contract()
        style_hash = canonical_hash(contract)
        strategy = {
            "schema_version": schema_version,
            "style_handoff": contract,
            "style_handoff_sha256": style_hash,
        }
        write_json(root / "plan" / "format_strategy.json", strategy)
        write_json(
            root / "episodes" / "episode_001.json",
            {"style_handoff_sha256": episode_hash or style_hash},
        )
        return strategy, style_hash

    def run_validator(self, *args):
        return subprocess.run(
            [sys.executable, str(SCRIPT), *map(str, args)],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_valid_series_passes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_series(root)
            result = self.run_validator("--series-root", root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_episode_hash_drift_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_series(root, episode_hash="0" * 64)
            result = self.run_validator("--series-root", root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("episode_001.json.style_handoff_sha256", result.stdout)

    def test_fake_user_confirmation_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            contract = self.contract()
            contract["user_confirmed"] = True
            self.make_series(root, contract=contract)
            result = self.run_validator("--series-root", root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("用户选择证据", result.stdout)

    def test_asset_job_without_style_injection_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            strategy, style_hash = self.make_series(root)
            context = {
                "series_format_strategy": strategy,
                "episode": {"style_handoff_sha256": style_hash},
            }
            asset_job = {
                "style_contract": strategy["style_handoff"],
                "style_contract_sha256": style_hash,
                "assets": [{"prompt_zh": "普通提示词", "negative_prompt": "3D"}],
            }
            context_path = root / "context.json"
            asset_job_path = root / "asset_job.json"
            write_json(context_path, context)
            write_json(asset_job_path, asset_job)
            result = self.run_validator(
                "--context", context_path, "--asset-job", asset_job_path
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("系列风格硬约束", result.stdout)
            self.assertIn("pbr", result.stdout.casefold())

    def test_valid_asset_job_passes_validator_and_dispatcher_dry_run(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            strategy, style_hash = self.make_series(root)
            context = {
                "series_format_strategy": strategy,
                "episode": {"style_handoff_sha256": style_hash},
            }
            asset_job = {
                "schema_version": "1.0",
                "job_id": "style_contract_test_001",
                "project_id": "style_contract_test",
                "source": "openclaw",
                "defaults": {
                    "model": "gemini-3.1-flash-image",
                    "aspect_ratio": "16:9",
                    "image_size": "2K",
                },
                "style_contract": strategy["style_handoff"],
                "style_contract_sha256": style_hash,
                "assets": [
                    {
                        "asset_id": "AST-CH01",
                        "category": "character",
                        "name": "角色",
                        "filename": "TEST_CH01_v01.png",
                        "prompt_zh": "【系列风格硬约束】国风半写实厚涂2D。人物设定页。",
                        "negative_prompt": "3D, PBR",
                        "aspect_ratio": "9:16",
                    }
                ],
            }
            context_path = root / "context.json"
            asset_job_path = root / "asset_job.json"
            write_json(context_path, context)
            write_json(asset_job_path, asset_job)
            result = self.run_validator(
                "--context", context_path, "--asset-job", asset_job_path
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            dispatch = subprocess.run(
                ["node", str(DISPATCHER), str(asset_job_path), "--dry-run"],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(dispatch.returncode, 0, dispatch.stdout + dispatch.stderr)

    def test_legacy_series_is_read_only_compatible(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_json(root / "plan" / "format_strategy.json", {"schema_version": "1.1"})
            write_json(root / "episodes" / "episode_001.json", {})
            result = self.run_validator("--series-root", root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('"legacy": true', result.stdout)


if __name__ == "__main__":
    unittest.main()
