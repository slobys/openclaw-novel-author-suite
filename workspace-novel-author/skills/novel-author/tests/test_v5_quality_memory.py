import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL_ROOT / "scripts"


def run_script(name, *args):
    return subprocess.run(
        [sys.executable, str(SCRIPTS / name), *map(str, args)],
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )


class NarrativeFatigueRegressionTests(unittest.TestCase):
    def run_with(self, intensities):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / "sig.jsonl"
            rows = [
                {
                    "chapterNo": i + 1,
                    "function": "progress",
                    "hookType": "question",
                    "conflictMode": "mystery",
                    "closingEmotion": {"name": "unease", "intensity": value},
                    "relationshipActions": ["x"],
                    "irreversibleChange": "x",
                }
                for i, value in enumerate(intensities)
            ]
            p.write_text("\n".join(json.dumps(x) for x in rows), encoding="utf-8")
            result = run_script("narrative_fatigue.py", p)
            self.assertEqual(result.returncode, 0, result.stderr)
            return json.loads(result.stdout)

    def test_low_intensity_run_does_not_fake_high_intensity_warning(self):
        data = self.run_with([4, 4, 4, 9, 6])
        self.assertFalse(any(x.startswith("SUSTAINED_HIGH_INTENSITY") for x in data["warnings"]))

    def test_three_real_high_intensity_closings_warn(self):
        data = self.run_with([4, 9, 9, 9, 6])
        self.assertTrue(any(x.startswith("SUSTAINED_HIGH_INTENSITY:3") for x in data["warnings"]))


class LengthContractTests(unittest.TestCase):
    def test_default_2166_han_is_accepted_without_padding(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / "chapter.md"
            p.write_text("章" * 2166, encoding="utf-8")
            result = run_script("chapter_length.py", p)
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(result.stdout)
            self.assertTrue(data["hardGatePass"])
            self.assertTrue(data["targetRangePass"])
            self.assertFalse(data["preferredTargetReached"])
            self.assertEqual(data["lengthDecision"], "accept")

    def test_default_below_2000_requires_one_revision(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / "chapter.md"
            p.write_text("章" * 1999, encoding="utf-8")
            result = run_script("chapter_length.py", p)
            self.assertEqual(result.returncode, 2)
            data = json.loads(result.stdout)
            self.assertFalse(data["hardGatePass"])
            self.assertEqual(data["lengthDecision"], "revise_once")

    def test_custom_hard_min_is_enforced(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / "chapter.md"
            p.write_text("章" * 3000, encoding="utf-8")
            result = run_script("chapter_length.py", p, "--hard-min", "3200", "--target-min", "3400", "--target-max", "3800")
            self.assertEqual(result.returncode, 2)
            data = json.loads(result.stdout)
            self.assertEqual(data["hardMinimumHanChars"], 3200)
            self.assertFalse(data["hardGatePass"])


class DraftRevisionGateTests(unittest.TestCase):
    def make_before(self, root, count=1900):
        body = root / "chapter.md"
        receipt = root / "length-r0.json"
        body.write_text("前" * count, encoding="utf-8")
        result = run_script("chapter_length.py", body, "--receipt", receipt)
        self.assertEqual(result.returncode, 2)
        return body, receipt

    def test_changed_draft_reaching_hard_min_passes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            body, receipt = self.make_before(root)
            body.write_text("后" * 2100, encoding="utf-8")
            result = run_script("draft_revision_gate.py", "--before-receipt", receipt, "--after-file", body, "--attempt", "1")
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(result.stdout)
            self.assertTrue(data["revisionPass"])
            self.assertTrue(data["draftChanged"])
            self.assertEqual(data["afterHanChars"], 2100)

    def test_unchanged_draft_is_blocked(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            body, receipt = self.make_before(root)
            result = run_script("draft_revision_gate.py", "--before-receipt", receipt, "--after-file", body, "--attempt", "1")
            self.assertEqual(result.returncode, 2)
            data = json.loads(result.stdout)
            self.assertIn("DRAFT_BODY_UNCHANGED", data["reasons"])
            self.assertIn("DRAFT_STILL_BELOW_HARD_MINIMUM", data["reasons"])

    def test_second_automatic_revision_is_blocked(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            body, receipt = self.make_before(root)
            body.write_text("后" * 2100, encoding="utf-8")
            result = run_script("draft_revision_gate.py", "--before-receipt", receipt, "--after-file", body, "--attempt", "2")
            self.assertEqual(result.returncode, 2)
            self.assertIn("AUTO_REVISION_LIMIT_EXCEEDED", json.loads(result.stdout)["reasons"])


class DynamicStateTests(unittest.TestCase):
    def test_latest_state_wins_and_knowledge_is_keyed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            ledger = root / "state.jsonl"
            sha1 = "a" * 64
            sha2 = "b" * 64
            u1 = root / "u1.json"
            u2 = root / "u2.json"
            u1.write_text(json.dumps({
                "projectId": "P1", "chapterNo": 1, "bodySha256": sha1,
                "characters": [{"characterId": "hero", "locationId": "village", "health": "ok"}],
                "knowledge": [{"knowledgeKey": "hero::secret1", "knowerId": "hero", "factId": "secret1", "status": "unknown"}],
                "inventory": [{"itemId": "knife", "holderId": "hero"}],
                "locations": [{"locationId": "village", "status": "safe"}],
            }), encoding="utf-8")
            u2.write_text(json.dumps({
                "projectId": "P1", "chapterNo": 2, "bodySha256": sha2,
                "characters": [{"characterId": "hero", "locationId": "forest", "health": "hurt"}],
                "knowledge": [{"knowledgeKey": "hero::secret1", "knowerId": "hero", "factId": "secret1", "status": "known"}],
                "inventory": [{"itemId": "knife", "holderId": "ally"}],
                "locations": [{"locationId": "forest", "status": "danger"}],
            }), encoding="utf-8")
            self.assertEqual(run_script("dynamic_state.py", "upsert", ledger, u1).returncode, 0)
            self.assertEqual(run_script("dynamic_state.py", "upsert", ledger, u2).returncode, 0)
            result = run_script("dynamic_state.py", "context", ledger, "--project", "P1")
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(result.stdout)
            self.assertEqual(data["characters"]["hero"]["locationId"], "forest")
            self.assertEqual(data["knowledge"]["hero::secret1"]["status"], "known")
            self.assertEqual(data["inventory"]["knife"]["holderId"], "ally")


class MemoryIndexTests(unittest.TestCase):
    def test_three_tier_context_and_long_retrieval(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            ledger = root / "memory.jsonl"
            records = [
                {"memoryId": "s1", "projectId": "P1", "tier": "short", "chapterNo": 10, "text": "主角刚刚进入黑石村", "sourceRef": "chapter:10", "sourceSha256": "a"*64},
                {"memoryId": "m1", "projectId": "P1", "tier": "mid", "chapterNo": 8, "text": "本卷核心冲突是村庄水源争夺", "sourceRef": "arc:1", "sourceSha256": "b"*64},
                {"memoryId": "l1", "projectId": "P1", "tier": "long", "chapterNo": 2, "text": "古井下面曾传来铁链声，疑似封印线索", "entities": ["古井"], "tags": ["伏笔"], "sourceRef": "chapter:2", "sourceSha256": "c"*64},
                {"memoryId": "l2", "projectId": "P1", "tier": "long", "chapterNo": 3, "text": "集市买过一把旧刀", "entities": ["集市"], "sourceRef": "chapter:3", "sourceSha256": "d"*64},
            ]
            for i, record in enumerate(records):
                p = root / f"r{i}.json"
                p.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
                self.assertEqual(run_script("memory_index.py", "upsert", ledger, p).returncode, 0)
            result = run_script("memory_index.py", "context", ledger, "--project", "P1", "--query", "古井铁链封印", "--through", "10")
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(result.stdout)
            self.assertEqual(data["short"][0]["memoryId"], "s1")
            self.assertEqual(data["mid"][0]["memoryId"], "m1")
            self.assertEqual(data["long"][0]["memoryId"], "l1")


class IndependentAuditTests(unittest.TestCase):
    def review(self, role, session, sha):
        checks = {
            "continuity-auditor": ["facts", "timeline", "knowledgeBoundary", "stateContinuity", "causality", "promiseContinuity", "relationshipContinuity"],
            "reader-editor": ["readability", "pacing", "repetition", "genreExperience", "hookQuality", "characterAgency"],
        }[role]
        return {
            "reviewerRole": role,
            "reviewerSessionId": session,
            "bodySha256": sha,
            "conclusion": "pass",
            "issues": [],
            "checks": {k: "pass" for k in checks},
        }

    def test_writer_cannot_review_own_chapter(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            body = root / "body.md"
            body.write_text("正文", encoding="utf-8")
            sha = hashlib.sha256(body.read_bytes()).hexdigest()
            c = root / "c.json"; r = root / "r.json"
            c.write_text(json.dumps(self.review("continuity-auditor", "writer", sha)), encoding="utf-8")
            r.write_text(json.dumps(self.review("reader-editor", "reader-2", sha)), encoding="utf-8")
            result = run_script("independent_audit_gate.py", "--body-file", body, "--writer-session", "writer", "--continuity-review", c, "--reader-review", r)
            self.assertEqual(result.returncode, 2)
            self.assertIn("CONTINUITY_NOT_INDEPENDENT", json.loads(result.stdout)["reasons"])

    def test_two_independent_reviews_pass(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            body = root / "body.md"; body.write_text("正文", encoding="utf-8")
            sha = hashlib.sha256(body.read_bytes()).hexdigest()
            c = root / "c.json"; r = root / "r.json"
            c.write_text(json.dumps(self.review("continuity-auditor", "auditor-1", sha)), encoding="utf-8")
            r.write_text(json.dumps(self.review("reader-editor", "reader-2", sha)), encoding="utf-8")
            result = run_script("independent_audit_gate.py", "--body-file", body, "--writer-session", "writer", "--continuity-review", c, "--reader-review", r)
            self.assertEqual(result.returncode, 0, result.stderr)
            receipt = json.loads(result.stdout)
            self.assertTrue(receipt["independentAuditPass"])
            self.assertEqual(receipt["engineReviews"]["continuityReview"]["checks"]["facts"], {"status": "pass"})
            self.assertEqual(receipt["engineReviews"]["readerReview"]["checks"]["pacing"], {"status": "pass"})

    def test_status_objects_are_normalized_for_engine_payload(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            body = root / "body.md"; body.write_text("正文", encoding="utf-8")
            sha = hashlib.sha256(body.read_bytes()).hexdigest()
            continuity = self.review("continuity-auditor", "auditor-1", sha)
            reader = self.review("reader-editor", "reader-2", sha)
            continuity["checks"]["facts"] = {"status": "passed", "evidence": "人物与既有事实一致"}
            reader["checks"]["pacing"] = {"pass": True, "description": "节奏无阻断问题"}
            c = root / "c.json"; r = root / "r.json"
            c.write_text(json.dumps(continuity, ensure_ascii=False), encoding="utf-8")
            r.write_text(json.dumps(reader, ensure_ascii=False), encoding="utf-8")
            result = run_script("independent_audit_gate.py", "--body-file", body, "--writer-session", "writer", "--continuity-review", c, "--reader-review", r)
            self.assertEqual(result.returncode, 0, result.stderr)
            reviews = json.loads(result.stdout)["engineReviews"]
            self.assertEqual(reviews["continuityReview"]["checks"]["facts"], {"status": "pass", "evidence": "人物与既有事实一致"})
            self.assertEqual(reviews["readerReview"]["checks"]["pacing"], {"status": "pass", "evidence": "节奏无阻断问题"})

    def test_descriptive_or_concatenated_check_values_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            body = root / "body.md"; body.write_text("正文", encoding="utf-8")
            sha = hashlib.sha256(body.read_bytes()).hexdigest()
            continuity = self.review("continuity-auditor", "auditor-1", sha)
            reader = self.review("reader-editor", "reader-2", sha)
            continuity["checks"]["facts"] = "pass：人物与前文一致"
            reader["checks"]["pacing"] = "节奏无阻断问题"
            c = root / "c.json"; r = root / "r.json"
            c.write_text(json.dumps(continuity, ensure_ascii=False), encoding="utf-8")
            r.write_text(json.dumps(reader, ensure_ascii=False), encoding="utf-8")
            result = run_script("independent_audit_gate.py", "--body-file", body, "--writer-session", "writer", "--continuity-review", c, "--reader-review", r)
            self.assertEqual(result.returncode, 2)
            receipt = json.loads(result.stdout)
            self.assertIn("CONTINUITY_CHECKS_NOT_PASS:facts", receipt["reasons"])
            self.assertIn("READER_CHECKS_NOT_PASS:pacing", receipt["reasons"])
            self.assertNotIn("engineReviews", receipt)

    def test_note_and_warning_checks_are_non_blocking(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            body = root / "body.md"; body.write_text("正文", encoding="utf-8")
            sha = hashlib.sha256(body.read_bytes()).hexdigest()
            continuity = self.review("continuity-auditor", "auditor-1", sha)
            reader = self.review("reader-editor", "reader-2", sha)
            continuity["checks"]["facts"] = "note"
            reader["checks"]["pacing"] = "warning"
            continuity["issues"] = [{"severity": "note", "category": "facts", "evidence": "minor detail"}]
            reader["issues"] = [{"severity": "warning", "category": "pacing", "evidence": "optional improvement"}]
            c = root / "c.json"; r = root / "r.json"
            c.write_text(json.dumps(continuity), encoding="utf-8")
            r.write_text(json.dumps(reader), encoding="utf-8")
            result = run_script("independent_audit_gate.py", "--body-file", body, "--writer-session", "writer", "--continuity-review", c, "--reader-review", r)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(json.loads(result.stdout)["independentAuditPass"])

    def test_same_reviewer_sessions_can_issue_fresh_receipts_for_new_hash(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            body = root / "body.md"; body.write_text("修订后的正文", encoding="utf-8")
            new_sha = hashlib.sha256(body.read_bytes()).hexdigest()
            c = root / "c.json"; r = root / "r.json"
            c.write_text(json.dumps(self.review("continuity-auditor", "auditor-1", new_sha)), encoding="utf-8")
            r.write_text(json.dumps(self.review("reader-editor", "reader-2", new_sha)), encoding="utf-8")
            result = run_script("independent_audit_gate.py", "--body-file", body, "--writer-session", "writer", "--continuity-review", c, "--reader-review", r)
            self.assertEqual(result.returncode, 0, result.stderr)
            receipt = json.loads(result.stdout)
            self.assertEqual(receipt["continuityReviewerSessionId"], "auditor-1")
            self.assertEqual(receipt["readerReviewerSessionId"], "reader-2")
            self.assertEqual(receipt["bodySha256"], new_sha)


class GenrePromiseTests(unittest.TestCase):
    def test_passing_receipt_is_engine_quality_ready(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            profile = root / "profile.json"
            ledger = root / "sig.jsonl"
            current = root / "current.json"
            body_sha = "b" * 64
            profile.write_text(json.dumps({"primaryExperiences": {"comedy": {"target": 7, "floor": 5}}}), encoding="utf-8")
            ledger.write_text("", encoding="utf-8")
            current.write_text(json.dumps({"chapterNo": 1, "bodySha256": body_sha, "experienceScores": {"comedy": 7}}), encoding="utf-8")
            result = run_script("genre_promise.py", "--profile", profile, "--signature-ledger", ledger, "--current-signature", current)
            self.assertEqual(result.returncode, 0, result.stderr)
            receipt = json.loads(result.stdout)
            self.assertTrue(receipt["genreGatePass"])
            self.assertTrue(receipt["pass"])
            self.assertTrue(receipt["genrePass"])
            self.assertFalse(receipt["hardBlock"])
            self.assertEqual(receipt["bodySha256"], body_sha)

    def test_severe_primary_genre_drift_blocks(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            profile = root / "profile.json"
            ledger = root / "sig.jsonl"
            current = root / "current.json"
            profile.write_text(json.dumps({"primaryExperiences": {"comedy": {"target": 7, "floor": 5}}}), encoding="utf-8")
            rows = [
                {"chapterNo": 1, "experienceScores": {"comedy": 1}},
                {"chapterNo": 2, "experienceScores": {"comedy": 1}},
            ]
            ledger.write_text("\n".join(json.dumps(x) for x in rows), encoding="utf-8")
            current.write_text(json.dumps({"chapterNo": 3, "bodySha256": "a"*64, "experienceScores": {"comedy": 1}}), encoding="utf-8")
            result = run_script("genre_promise.py", "--profile", profile, "--signature-ledger", ledger, "--current-signature", current)
            self.assertEqual(result.returncode, 2)
            receipt = json.loads(result.stdout)
            self.assertFalse(receipt["genreGatePass"])
            self.assertFalse(receipt["pass"])
            self.assertFalse(receipt["genrePass"])
            self.assertTrue(receipt["hardBlock"])
            self.assertEqual(receipt["bodySha256"], "a"*64)


class OutlineDriftTests(unittest.TestCase):
    def test_unmet_required_beats_are_reported(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); plan=root/"plan.json"; sig=root/"sig.jsonl"
            plan.write_text(json.dumps({"chapters":[{"chapterNo":1,"plannedBeatIds":["B1","B2"],"requiredBeatIds":["B1","B2"]}]}),encoding="utf-8")
            sig.write_text(json.dumps({"chapterNo":1,"fulfilledBeatIds":["B1"]})+"\n",encoding="utf-8")
            result=run_script("outline_drift.py","--plan",plan,"--signature-ledger",sig,"--start","1","--end","1")
            self.assertEqual(result.returncode,0,result.stderr)
            data=json.loads(result.stdout)
            self.assertIn("B2",data["unmetRequiredBeatIds"])


class QualityGateTests(unittest.TestCase):
    def test_combined_receipts_bind_to_same_body(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); body=root/"body.md"; body.write_text("正文",encoding="utf-8")
            sha=hashlib.sha256(body.read_bytes()).hexdigest()
            independent=root/"ind.json"; genre=root/"genre.json"
            independent.write_text(json.dumps({"independentAuditPass":True,"bodySha256":sha}),encoding="utf-8")
            genre.write_text(json.dumps({"genreGatePass":True,"bodySha256":sha,"warnings":[]}),encoding="utf-8")
            result=run_script("quality_gate.py","--body-file",body,"--independent-receipt",independent,"--genre-receipt",genre)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertTrue(json.loads(result.stdout)["qualityPass"])


class ServerCapabilityTests(unittest.TestCase):
    def test_server_gate_rejects_pre_045_engine(self):
        with tempfile.TemporaryDirectory() as temp:
            cap=Path(temp)/"cap.json"
            cap.write_text(json.dumps({
                "engineVersion":"0.4.4","enforcedServerSide":True,"minChapterHanChars":2600,
                "commitRehash":True,"auditHashBinding":True,"completeAuditCoverage":True,
                "independentQualityReceipt":True,"closureReceiptRequired":True,"requestIdRequired":True,
                "derivedBodyHashBinding":True,"requiredAuditCategoryCount":17,"requestIdIdempotency":True,
                "requestIdPayloadBinding":True,"crashRecoverableTransactions":True,
                "commitStatusReconciliation":True,"revisionCas":True,"projectIntegrityCheck":True
            }),encoding="utf-8")
            result=run_script("server_capability_gate.py",cap,"--hard-min","2600")
            self.assertEqual(result.returncode,2)
            self.assertIn("SERVER_ENGINE_VERSION_TOO_OLD",json.loads(result.stdout)["reasons"])

    def test_server_gate_requires_all_hard_capabilities(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); cap=root/"cap.json"
            cap.write_text(json.dumps({
                "engineVersion":"0.4.8",
                "enforcedServerSide":True,"minChapterHanChars":2600,
                "commitRehash":True,"auditHashBinding":True,"completeAuditCoverage":True,
                "independentQualityReceipt":True,"requestIdIdempotency":True,
                "closureReceiptRequired":True,"requestIdRequired":True,
                "derivedBodyHashBinding":True,"requiredAuditCategoryCount":17,
                "requestIdPayloadBinding":True,"crashRecoverableTransactions":True,
                "commitStatusReconciliation":True,"revisionCas":True,"projectIntegrityCheck":True
            }),encoding="utf-8")
            result=run_script("server_capability_gate.py",cap,"--hard-min","2600")
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertTrue(json.loads(result.stdout)["serverGateVerified"])

    def test_server_gate_accepts_novel_engine_045_project_status(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); cap=root/"status.json"
            cap.write_text(json.dumps({
                "engineVersion":"0.4.8",
                "storyLedgers":{"chapterLengthGate":{"minHanChars":3200,"enforcedServerSide":True},"closureReceiptRequired":True,"requiredAuditCategories":[f"c{i}" for i in range(17)]},
                "serverCapabilities":{
                    "serverGateVerified":True,
                    "engineVersion":"0.4.8",
                    "hanLengthRecount":True,
                    "auditBodyHashBinding":True,
                    "completeAuditCoverage":True,
                    "independentQualityReceipt":True,
                    "closureReceiptRequired":True,
                    "requestIdRequired":True,
                    "derivedBodyHashBinding":True,
                    "requiredAuditCategoryCount":17,
                    "requestIdIdempotency":True,
                    "requestIdPayloadBinding":True,
                    "crashRecoverableTransactions":True,
                    "commitStatusReconciliation":True,
                    "revisionCas":True,
                    "projectIntegrityCheck":True,
                    "resolvedHardMinHanChars":3200
                }
            }),encoding="utf-8")
            result=run_script("server_capability_gate.py",cap,"--hard-min","3200")
            self.assertEqual(result.returncode,0,result.stderr)
            data=json.loads(result.stdout)
            self.assertTrue(data["serverGateVerified"])
            self.assertEqual(data["observed"]["minChapterHanChars"],3200)

if __name__ == "__main__":
    unittest.main()
