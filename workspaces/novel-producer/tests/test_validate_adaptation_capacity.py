import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "validate_adaptation_capacity.py"
SPEC = importlib.util.spec_from_file_location("validate_adaptation_capacity", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def capacity(source_chars: int) -> dict:
    return {
        "source_char_count": source_chars,
        "source_event_count": 1,
        "source_char_soft_limit": 1200,
        "source_char_hard_limit": 1800,
        "estimated_screen_seconds": 60,
        "effective_beat_count": 3,
        "mapped_event_count": 1,
        "unmapped_event_ids": [],
        "compression_actions": [],
        "capacity_status": "pass",
    }


class StandardAdaptationSourceSpanTests(unittest.TestCase):
    def build_root(self, spans_by_episode):
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name)
        write_json(root / "chapters" / "chapter_index.json", {
            "chapters": [{"chapter_id": "CH001", "char_count": 2000}],
        })
        write_json(root / "plan" / "format_strategy.json", {"episode_duration_seconds": 90})
        episodes = []
        ledger = []
        for number, spans in enumerate(spans_by_episode, start=1):
            event_id = f"E{number}"
            row = {
                "global_episode_number": number,
                "target_duration_seconds": 90,
                "source_chapter_ids": ["CH001"],
                "source_event_ids": [event_id],
                "episode_capacity": capacity(sum(span["end"] - span["start"] for span in spans) if spans else 2000),
            }
            if spans is not None:
                row["source_spans"] = spans
            episodes.append(row)
            ledger.append({"event_id": event_id, "episode_assignment": {"global_episode_number": number}})
        write_json(root / "plan" / "series_plan.json", {"episodes": episodes})
        write_json(root / "plan" / "adaptation_ledger.json", {"entries": ledger})
        return temp, root

    def test_split_chapter_uses_exact_non_overlapping_spans(self):
        temp, root = self.build_root([
            [{"chapter_id": "CH001", "start": 0, "end": 1000}],
            [{"chapter_id": "CH001", "start": 1000, "end": 2000}],
        ])
        self.addCleanup(temp.cleanup)
        result = MODULE.validate(root)
        self.assertTrue(result["ok"], result["errors"])
        self.assertEqual([1000, 1000], [row["source_char_count"] for row in result["episodes"]])

    def test_repeated_chapter_without_spans_is_rejected(self):
        temp, root = self.build_root([None, None])
        self.addCleanup(temp.cleanup)
        result = MODULE.validate(root)
        self.assertFalse(result["ok"])
        self.assertTrue(any("必须提供精确 source_spans" in item for item in result["errors"]))

    def test_overlapping_spans_are_rejected(self):
        temp, root = self.build_root([
            [{"chapter_id": "CH001", "start": 0, "end": 1100}],
            [{"chapter_id": "CH001", "start": 1000, "end": 2000}],
        ])
        self.addCleanup(temp.cleanup)
        result = MODULE.validate(root)
        self.assertFalse(result["ok"])
        self.assertTrue(any("source_spans 重叠" in item for item in result["errors"]))

    def test_every_declared_chapter_has_a_span(self):
        temp, root = self.build_root([
            [{"chapter_id": "CH001", "start": 0, "end": 1000}],
        ])
        self.addCleanup(temp.cleanup)
        index_path = root / "chapters" / "chapter_index.json"
        index = json.loads(index_path.read_text(encoding="utf-8"))
        index["chapters"].append({"chapter_id": "CH002", "char_count": 1000})
        write_json(index_path, index)
        plan_path = root / "plan" / "series_plan.json"
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        plan["episodes"][0]["source_chapter_ids"] = ["CH001", "CH002"]
        write_json(plan_path, plan)
        result = MODULE.validate(root)
        self.assertFalse(result["ok"])
        self.assertTrue(any("已声明章节缺少 source_spans" in item for item in result["errors"]))


if __name__ == "__main__":
    unittest.main()
