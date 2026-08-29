import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL_ROOT / "scripts"
REPO_ROOT = Path(__file__).resolve().parents[4]
ENGINE_MODULE = next(
    path for path in (REPO_ROOT / "src" / "engine.js", REPO_ROOT / "novel-engine" / "src" / "engine.js")
    if path.exists()
)


def run_job(root, *args):
    return subprocess.run(
        [sys.executable, str(SCRIPTS / "job_state.py"), "--dir", str(root), *map(str, args)],
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )


class EngineBridgeContractTests(unittest.TestCase):
    def test_local_body_hash_uses_engine_canonical_text_contract(self):
        with tempfile.TemporaryDirectory() as temp:
            body = Path(temp) / "body.md"
            body.write_bytes("\r\n正文\r\n\r\n".encode("utf-8"))
            result = subprocess.run(
                [sys.executable, str(SCRIPTS / "chapter_payload_gate.py"), "--chapter", "1", "--title", "统一哈希", "--body-file", str(body)],
                text=True,
                encoding="utf-8",
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["bodySha256"], hashlib.sha256("正文".encode("utf-8")).hexdigest())

    def test_real_engine_commit_receipt_advances_agent_to_closing(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            engine_root = root / "engine-data"
            script = f'''\
import {{ NovelEngine, LOGIC_AUDIT_CATEGORIES }} from {json.dumps(ENGINE_MODULE.as_uri())};
import {{ sha256 }} from {json.dumps((ENGINE_MODULE.parent / "utils.js").as_uri())};
const body = "汉".repeat(30);
const bodySha256 = sha256(body);
const engine = new NovelEngine({{projectsRoot: process.argv[1], minChapterChars: 10, minChapterHanChars: 20, targetChapterHanChars: 30, targetChapterHanCharsMax: 40, requireClosureReceipt: false}});
await engine.createProject({{projectId:"bridge01", title:"桥接测试", genre:"测试"}});
await engine.recordChapterAudit({{projectId:"bridge01", chapter:1, stage:"precommit", decision:"pass", content:body, checks:Object.fromEntries(LOGIC_AUDIT_CATEGORIES.map(k=>[k,{{status:"pass"}}]))}});
const continuityChecks = Object.fromEntries(["facts","timeline","knowledgeBoundary","stateContinuity","causality","promiseContinuity","relationshipContinuity"].map(k=>[k,{{status:"pass",evidence:`${{k}} verified`}}]));
const readerChecks = Object.fromEntries(["readability","pacing","repetition","genreExperience","hookQuality","characterAgency"].map(k=>[k,{{status:"pass",evidence:`${{k}} verified`}}]));
await engine.recordChapterQuality({{projectId:"bridge01", chapter:1, content:body, writerSessionId:"writer", continuityReview:{{reviewerRole:"continuity-auditor",reviewerSessionId:"continuity",bodySha256,conclusion:"pass",checks:continuityChecks,issues:[]}}, readerReview:{{reviewerRole:"reader-editor",reviewerSessionId:"reader",bodySha256,conclusion:"pass",checks:readerChecks,issues:[]}}, genreGate:{{pass:true,bodySha256}}, signature:{{bodySha256,rhythm:"balanced"}}}});
const commit = await engine.commitChapter({{projectId:"bridge01",expectedChapter:1,title:"桥接",content:body,summary:"测试",requestId:"J1-ch1"}});
const operations = Object.fromEntries(["causalEvents","foreshadowing","promisePayoff","relationshipGraph","oppositionClocks","chapterSignature","dynamicState","memoryIndex"].map(key=>[key,{{status:"skipped",reason:`${{key}} has no applicable change in this fixture.`}}]));
const closure = await engine.recordChapterClosure({{projectId:"bridge01",chapter:1,bodySha256,operations}});
console.log(JSON.stringify({{commit,closure}}));
'''
            result = subprocess.run(
                ["node", "--input-type=module", "-e", script, str(engine_root)],
                text=True,
                encoding="utf-8",
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            engine_result = json.loads(result.stdout)
            receipt = engine_result["commit"]
            receipt_path = root / "engine-commit.json"
            receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
            closure_path = root / "engine-closure.json"
            closure_path.write_text(json.dumps(engine_result["closure"]), encoding="utf-8")

            job_root = root / "jobs"
            created = run_job(job_root, "create", "--project", "bridge01", "--start", "1", "--end", "1", "--job-id", "J1")
            self.assertEqual(created.returncode, 0, created.stderr)

            def revision():
                return json.loads((job_root / "J1.json").read_text(encoding="utf-8"))["revision"]

            def advance(state, evidence):
                return run_job(job_root, "set", "--job", "J1", "--chapter", "1", "--expect-revision", revision(), "--state", state, "--evidence", evidence)

            for state in ["preparing", "drafting", "length_gate", "auditing", "quality_gate"]:
                advanced = advance(state, "bridge-test")
                self.assertEqual(advanced.returncode, 0, advanced.stderr)
            quality_path = root / "quality.json"
            quality_path.write_text(json.dumps({"qualityPass": True, "bodySha256": receipt["bodySha256"]}), encoding="utf-8")
            self.assertEqual(advance("precommit_gate", quality_path).returncode, 0)
            gate_path = root / "gate.json"
            gate_path.write_text(json.dumps({"gatePass": True, "bodySha256": receipt["bodySha256"]}), encoding="utf-8")
            self.assertEqual(advance("committing", gate_path).returncode, 0)
            closing = advance("closing", receipt_path)
            self.assertEqual(closing.returncode, 0, closing.stderr)
            integrity = advance("integrity_gate", "bridge-integrity-pass")
            self.assertEqual(integrity.returncode, 0, integrity.stderr)
            committed = advance("committed", closure_path)
            self.assertEqual(committed.returncode, 0, committed.stderr)


if __name__ == "__main__":
    unittest.main()
