import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
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


class PrecommitGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.chapter = self.root / "chapter.md"
        self.audit = self.root / "audit.json"
        self.payload = self.root / "payload.json"
        self.chapter.write_text("章" * 2600, encoding="utf-8")
        self.body_sha = hashlib.sha256(self.chapter.read_bytes()).hexdigest()
        self.quality = self.root / "quality.json"
        self.quality.write_text(
            json.dumps({"qualityPass": True, "bodySha256": self.body_sha}), encoding="utf-8"
        )
        payload_result = run_script(
            "chapter_payload_gate.py", "--chapter", "7", "--title", "纯标题",
            "--body-file", self.chapter, "--receipt", self.payload
        )
        self.assertEqual(payload_result.returncode, 0, payload_result.stderr)

    def tearDown(self):
        self.temp.cleanup()

    def audit_data(self, **updates):
        data = {
            "conclusion": "pass",
            "issues": [],
            "bodySha256": self.body_sha,
            "checks": {name: "pass" for name in AUDIT_CHECKS},
        }
        data.update(updates)
        return data

    def test_missing_body_hash_is_hard_failure(self):
        self.audit.write_text(
            json.dumps(self.audit_data(bodySha256=None)), encoding="utf-8"
        )
        result = run_script("precommit_gate.py", self.chapter, self.audit, "--payload-receipt", self.payload, "--quality-receipt", self.quality)
        self.assertEqual(result.returncode, 2)
        receipt = json.loads(result.stdout)
        self.assertFalse(receipt["gatePass"])
        self.assertIn("PRECOMMIT_BODY_HASH_MISSING", receipt["reasons"])

    def test_matching_hash_passes(self):
        self.audit.write_text(
            json.dumps(self.audit_data()),
            encoding="utf-8",
        )
        result = run_script("precommit_gate.py", self.chapter, self.audit, "--payload-receipt", self.payload, "--quality-receipt", self.quality)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["gatePass"])

    def test_mismatched_hash_fails(self):
        self.audit.write_text(
            json.dumps(self.audit_data(bodySha256="0" * 64)),
            encoding="utf-8",
        )
        result = run_script("precommit_gate.py", self.chapter, self.audit, "--payload-receipt", self.payload, "--quality-receipt", self.quality)
        self.assertEqual(result.returncode, 2)
        self.assertIn("PRECOMMIT_BODY_HASH_MISMATCH", json.loads(result.stdout)["reasons"])

    def test_missing_required_audit_checks_fails(self):
        self.audit.write_text(
            json.dumps(self.audit_data(checks={"facts": "pass"})), encoding="utf-8"
        )
        result = run_script("precommit_gate.py", self.chapter, self.audit, "--payload-receipt", self.payload, "--quality-receipt", self.quality)
        self.assertEqual(result.returncode, 2)
        self.assertTrue(
            any(reason.startswith("PRECOMMIT_AUDIT_CHECKS_MISSING:") for reason in json.loads(result.stdout)["reasons"])
        )


class ChapterPayloadGateTests(unittest.TestCase):
    def test_rejects_duplicate_chapter_heading(self):
        with tempfile.TemporaryDirectory() as temp:
            body = Path(temp) / "body.md"
            body.write_text("# 第7章 拱地的家伙\n正文", encoding="utf-8")
            result = run_script(
                "chapter_payload_gate.py", "--chapter", "7", "--title", "第7章 拱地的家伙",
                "--body-file", body
            )
            self.assertEqual(result.returncode, 2)
            reasons = json.loads(result.stdout)["reasons"]
            self.assertIn("TITLE_CONTAINS_CHAPTER_PREFIX", reasons)
            self.assertIn("BODY_CONTAINS_CHAPTER_HEADING", reasons)

    def test_accepts_pure_title_and_body(self):
        with tempfile.TemporaryDirectory() as temp:
            body = Path(temp) / "body.md"
            body.write_text("正文从这里开始。", encoding="utf-8")
            result = run_script(
                "chapter_payload_gate.py", "--chapter", "7", "--title", "拱地的家伙",
                "--body-file", body
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["canonicalDisplayTitle"], "第7章 拱地的家伙")


class JobStateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        result = self.job("create", "--project", "P1", "--start", "7", "--end", "8", "--job-id", "J1")
        self.assertEqual(result.returncode, 0, result.stderr)

    def tearDown(self):
        self.temp.cleanup()

    def job(self, *args):
        return run_script("job_state.py", "--dir", self.root, *args)

    def data(self):
        return json.loads((self.root / "J1.json").read_text(encoding="utf-8"))

    def set_state(self, chapter, state, evidence="test-evidence"):
        revision = self.data()["revision"]
        return self.job(
            "set",
            "--job", "J1",
            "--chapter", chapter,
            "--expect-revision", revision,
            "--state", state,
            "--evidence", evidence,
        )

    def test_forward_stage_skip_is_rejected(self):
        result = self.set_state(7, "committing")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("expected preparing", result.stderr)
        self.assertEqual(self.data()["chapters"]["7"]["state"], "pending")

    def test_next_chapter_cannot_start_early(self):
        result = self.set_state(8, "preparing")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("strict serial violation", result.stderr)

    def test_second_active_job_for_project_is_rejected(self):
        result = self.job(
            "create", "--project", "P1", "--start", "9", "--end", "9", "--job-id", "J2"
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("active job already exists", result.stderr)

    def test_stale_revision_is_rejected(self):
        self.assertEqual(self.set_state(7, "preparing").returncode, 0)
        result = self.job(
            "set", "--job", "J1", "--chapter", "7", "--expect-revision", "1",
            "--state", "drafting", "--evidence", "draft-plan"
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("revision conflict", result.stderr)

    def test_second_identical_failure_blocks(self):
        self.assertEqual(self.set_state(7, "preparing").returncode, 0)
        revision = self.data()["revision"]
        first = self.job(
            "fail", "--job", "J1", "--chapter", "7", "--expect-revision", revision,
            "--error-code", "SCHEMA_ERROR", "--error", "bad key"
        )
        self.assertEqual(first.returncode, 0, first.stderr)
        revision = self.data()["revision"]
        resumed = self.job(
            "resume", "--job", "J1", "--chapter", "7", "--expect-revision", revision
        )
        self.assertEqual(resumed.returncode, 0, resumed.stderr)
        revision = self.data()["revision"]
        second = self.job(
            "fail", "--job", "J1", "--chapter", "7", "--expect-revision", revision,
            "--error-code", "SCHEMA_ERROR", "--error", "bad key again"
        )
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(self.data()["chapters"]["7"]["state"], "blocked")

    def test_critical_transitions_require_bound_receipts(self):
        for state in ["preparing", "drafting", "length_gate", "auditing", "quality_gate"]:
            self.assertEqual(self.set_state(7, state).returncode, 0)

        quality = self.root / "quality.json"
        body_sha = "a" * 64
        quality.write_text(
            json.dumps({"qualityPass": True, "bodySha256": body_sha}), encoding="utf-8"
        )
        self.assertEqual(self.set_state(7, "precommit_gate", quality).returncode, 0)

        invalid_gate = self.root / "invalid-gate.json"
        invalid_gate.write_text(json.dumps({"gatePass": False}), encoding="utf-8")
        rejected = self.set_state(7, "committing", invalid_gate)
        self.assertNotEqual(rejected.returncode, 0)

        body_sha = "a" * 64
        gate = self.root / "gate.json"
        gate.write_text(
            json.dumps({"gatePass": True, "bodySha256": body_sha}), encoding="utf-8"
        )
        self.assertEqual(self.set_state(7, "committing", gate).returncode, 0)

        engine = self.root / "engine.json"
        engine.write_text(
            json.dumps({
                "confirmed": True,
                "chapterNo": 7,
                "requestId": "J1-ch7",
                "bodySha256": body_sha,
            }),
            encoding="utf-8",
        )
        self.assertEqual(self.set_state(7, "closing", engine).returncode, 0)
        self.assertEqual(self.set_state(7, "integrity_gate", "closure-manifest").returncode, 0)

        closure = self.root / "closure-receipt.json"
        closure.write_text(
            json.dumps({
                "closurePass": True,
                "chapterNo": 7,
                "requestId": "J1-ch7",
                "bodySha256": body_sha,
            }),
            encoding="utf-8",
        )
        self.assertEqual(self.set_state(7, "committed", closure).returncode, 0)


class ChapterClosureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.manifest = self.root / "closure.json"
        self.gate = self.root / "gate.json"
        self.body_sha = "b" * 64
        self.gate.write_text(
            json.dumps({"gatePass": True, "bodySha256": self.body_sha}), encoding="utf-8"
        )

    def tearDown(self):
        self.temp.cleanup()

    def closure(self, *args):
        return run_script("chapter_closure.py", *args)

    def revision(self):
        return json.loads(self.manifest.read_text(encoding="utf-8"))["revision"]

    def test_incomplete_closure_fails_then_complete_closure_passes(self):
        created = self.closure(
            "init", "--manifest", self.manifest, "--project", "P1", "--chapter", "7",
            "--request-id", "J1-ch7", "--body-sha256", self.body_sha,
            "--operation", "causal_events", "--operation", "chapter_signature"
        )
        self.assertEqual(created.returncode, 0, created.stderr)
        incomplete = self.closure("verify", "--manifest", self.manifest, "--gate-receipt", self.gate)
        self.assertEqual(incomplete.returncode, 2)

        confirmed = self.closure(
            "confirm-commit", "--manifest", self.manifest, "--expect-revision", self.revision(),
            "--engine-body-sha256", self.body_sha, "--evidence", "engine:chapter:7"
        )
        self.assertEqual(confirmed.returncode, 0, confirmed.stderr)
        completed = self.closure(
            "mark", "--manifest", self.manifest, "--expect-revision", self.revision(),
            "--operation", "causal_events", "--status", "completed", "--evidence", "event:42"
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        skipped = self.closure(
            "mark", "--manifest", self.manifest, "--expect-revision", self.revision(),
            "--operation", "chapter_signature", "--status", "skipped", "--reason", "not applicable"
        )
        self.assertEqual(skipped.returncode, 0, skipped.stderr)
        receipt = self.root / "closure-receipt.json"
        verified = self.closure(
            "verify", "--manifest", self.manifest, "--gate-receipt", self.gate,
            "--receipt", receipt
        )
        self.assertEqual(verified.returncode, 0, verified.stderr)
        self.assertTrue(json.loads(receipt.read_text(encoding="utf-8"))["closurePass"])


class ChapterSignatureTests(unittest.TestCase):
    def test_concurrent_upserts_preserve_all_chapters(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            ledger = root / "signatures.jsonl"

            def upsert(chapter_no):
                source = root / f"signature-{chapter_no}.json"
                source.write_text(
                    json.dumps({"chapterNo": chapter_no, "function": "progress"}),
                    encoding="utf-8",
                )
                return run_script("chapter_signature.py", ledger, source)

            with ThreadPoolExecutor(max_workers=8) as pool:
                results = list(pool.map(upsert, range(1, 21)))
            self.assertTrue(all(result.returncode == 0 for result in results))
            rows = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
            self.assertEqual([row["chapterNo"] for row in rows], list(range(1, 21)))


if __name__ == "__main__":
    unittest.main()
