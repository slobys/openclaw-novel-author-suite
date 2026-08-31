import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "record_user_episode_advance.py"
SPEC = importlib.util.spec_from_file_location("record_user_episode_advance", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class SelectCompletedQueueItemTests(unittest.TestCase):
    def test_selects_latest_series_committed_revision(self):
        with tempfile.TemporaryDirectory() as tmp:
            series_root = Path(tmp)
            done = series_root / "queue" / "done"
            done.mkdir(parents=True)
            for suffix, project_id, committed_at in (
                ("", "series_s01e007", "2026-08-26T10:00:00Z"),
                ("_r2", "series_s01e007_r2", "2026-08-27T08:45:00Z"),
            ):
                queue_path = done / f"episode_007{suffix}.json"
                queue_path.write_text(
                    json.dumps({"episode_number": 7, "episode_project_id": project_id}),
                    encoding="utf-8",
                )
                (done / f".{project_id}.series_commit.json").write_text(
                    json.dumps(
                        {
                            "episode_number": 7,
                            "episode_project_id": project_id,
                            "committed_at": committed_at,
                        }
                    ),
                    encoding="utf-8",
                )

            selected = MODULE.select_completed_queue_item(series_root, 7)

            self.assertEqual(selected, done / "episode_007_r2.json")

    def test_ignores_uncommitted_revision(self):
        with tempfile.TemporaryDirectory() as tmp:
            series_root = Path(tmp)
            done = series_root / "queue" / "done"
            done.mkdir(parents=True)
            (done / "episode_007_r3.json").write_text(
                json.dumps({"episode_number": 7, "episode_project_id": "series_s01e007_r3"}),
                encoding="utf-8",
            )

            self.assertIsNone(MODULE.select_completed_queue_item(series_root, 7))


if __name__ == "__main__":
    unittest.main()
