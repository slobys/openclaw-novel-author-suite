import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL_ROOT / "scripts"
AUDIT_CHECKS = [
    "facts", "timeline", "space", "motivation", "knowledge", "worldRules",
    "resources", "causality", "foreshadowing", "originality", "voice",
    "sceneDynamics", "promiseFairness", "relationshipContinuity", "emotionCurve",
    "fatigueRisk", "oppositionPressure",
]


def run_script(name, *args):
    return subprocess.run(
        [sys.executable, str(SCRIPTS / name), *map(str, args)],
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )


class ToolLimitedSessionHandoffTests(unittest.TestCase):
    def writer_envelope(self, body="汉" * 2100):
        return {
            "schemaVersion": "novel-writer-return-v1",
            "chapterNo": 17,
            "title": "风从旧门来",
            "plan": {"alternativesConsidered": 2, "selected": "主动追查"},
            "body": body,
            "audit": {
                "decision": "pass",
                "checks": {name: "pass" for name in AUDIT_CHECKS},
                "issues": [],
            },
        }

    def test_parent_materializes_tool_limited_writer_return_then_gate_passes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "writer-return.txt"
            evidence = root / "evidence"
            source.write_text(
                "```json\n" + json.dumps(self.writer_envelope(), ensure_ascii=False) + "\n```",
                encoding="utf-8",
            )
            materialized = run_script(
                "materialize_session_handoff.py", "writer",
                "--input", source, "--output-dir", evidence,
                "--chapter", "17", "--writer-session-id", "writer-session-17",
            )
            self.assertEqual(materialized.returncode, 0, materialized.stderr)
            receipt = json.loads(materialized.stdout)
            body = evidence / "chapter.md"
            audit = evidence / "writer-audit.json"
            self.assertEqual(receipt["bodySha256"], hashlib.sha256(("汉" * 2100).encode("utf-8")).hexdigest())
            self.assertEqual(json.loads(audit.read_text(encoding="utf-8"))["writerSessionId"], "writer-session-17")

            gate = run_script(
                "writer_handoff_gate.py", "--chapter", "17",
                "--writer-session-id", "writer-session-17",
                "--body-file", body, "--audit-file", audit, "--hard-min", "2000",
            )
            self.assertEqual(gate.returncode, 0, gate.stderr)
            self.assertTrue(json.loads(gate.stdout)["handoffPass"])

    def test_parent_rejects_forged_writer_hash_without_writing_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "writer-return.json"
            evidence = root / "evidence"
            envelope = self.writer_envelope()
            envelope["bodySha256"] = "0" * 64
            source.write_text(json.dumps(envelope, ensure_ascii=False), encoding="utf-8")
            result = run_script(
                "materialize_session_handoff.py", "writer",
                "--input", source, "--output-dir", evidence,
                "--chapter", "17", "--writer-session-id", "writer-session-17",
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("bodySha256 mismatch", result.stderr)
            self.assertFalse((evidence / "chapter.md").exists())

    def test_parent_materializes_reviewer_return_and_binds_real_session_and_hash(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            body = root / "chapter.md"
            source = root / "review-return.json"
            output = root / "continuity.json"
            body.write_text("汉" * 2100, encoding="utf-8")
            source.write_text(json.dumps({
                "schemaVersion": "novel-review-return-v1",
                "chapterNo": 17,
                "reviewerRole": "continuity-auditor",
                "conclusion": "pass",
                "checks": {
                    "facts": "pass", "timeline": "pass", "knowledgeBoundary": "pass",
                    "stateContinuity": "pass", "causality": "pass",
                    "promiseContinuity": "pass", "relationshipContinuity": "pass",
                },
                "issues": [],
                "summary": "连续性通过",
            }, ensure_ascii=False), encoding="utf-8")
            result = run_script(
                "materialize_session_handoff.py", "reviewer",
                "--input", source, "--output", output, "--body-file", body,
                "--chapter", "17", "--role", "continuity-auditor",
                "--reviewer-session-id", "continuity-session-17",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            review = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(review["reviewerSessionId"], "continuity-session-17")
            self.assertEqual(review["bodySha256"], hashlib.sha256(("汉" * 2100).encode("utf-8")).hexdigest())

    def test_machine_workflow_does_not_require_leaf_writer_tools(self):
        workflow = (SKILL_ROOT.parents[1] / "novel-author-workflow.yaml").read_text(encoding="utf-8")
        agents = (SKILL_ROOT.parents[1] / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("direct_file_write: forbidden", workflow)
        self.assertIn("novel_engine_tools: forbidden_and_not_required", workflow)
        self.assertIn("session_or_subagent_tools: forbidden_and_not_required", workflow)
        self.assertIn("materialize_session_handoff.py_writer", workflow)
        self.assertIn("没有文件、命令、`novel_*` 或会话工具是合法且推荐", agents)


if __name__ == "__main__":
    unittest.main()
