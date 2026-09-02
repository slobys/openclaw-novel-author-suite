import assert from "node:assert/strict";
import { promises as fs } from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { LOGIC_AUDIT_CATEGORIES, NovelEngine } from "../src/engine.js";
import { canonicalBodySha256, finalizeChapterRecoverable } from "../src/finalize.js";

function review(role, sessionId, hash) {
  return { reviewerRole: role, reviewerSessionId: sessionId, bodySha256: hash, conclusion: "pass", checks: {}, issues: [] };
}

function payload() {
  const content = "第一行\r\n第二行";
  const hash = canonicalBodySha256(content);
  return {
    projectId: "demo",
    expectedChapter: 1,
    title: "开场",
    content,
    summary: "摘要",
    requestId: "job-1-ch1",
    writerSessionId: "writer-1",
    audit: { decision: "pass", checks: {} },
    continuityReview: review("continuity-auditor", "continuity-1", hash),
    readerReview: review("reader-editor", "reader-1", hash),
    genreGate: { bodySha256: hash, pass: true },
    signature: { bodySha256: hash, chapterNo: 1, function: "opening" },
    causalEvents: [{ eventId: "ev-1", summary: "事件", status: "occurred" }],
    memoryRecords: [{ id: "mem-1", tier: "short", text: "记忆" }]
  };
}

function mockEngine({ committed = false, committedHash = null } = {}) {
  const calls = [];
  const p = payload();
  const hash = committedHash ?? canonicalBodySha256(p.content);
  const engine = {
    calls,
    async commitStatus(args) { calls.push(["commitStatus", args]); return committed ? { status: "committed", bodySha256: hash, nextChapter: 2 } : { status: "not_found" }; },
    async recordChapterAudit(args) { calls.push(["audit", args]); return { auditId: "audit-1" }; },
    async recordChapterQuality(args) { calls.push(["quality", args]); return { qualityId: "quality-1" }; },
    async commitChapter(args) { calls.push(["commit", args]); return { bodySha256: hash, nextChapter: 2, transactionId: "tx-1" }; },
    async recordCausalEvent(args) { calls.push(["causal", args]); return { eventId: args.event.eventId }; },
    async upsertForeshadowing(args) { calls.push(["foreshadowing", args]); return { id: args.entry.id }; },
    async storyLedgerUpsert(args) { calls.push(["ledger", args]); return { id: args.entry.id }; },
    async dynamicStateUpdate(args) { calls.push(["dynamic", args]); return { updatedCounts: {} }; },
    async memoryRecord(args) { calls.push(["memory", args]); return { recorded: args.records.length }; },
    async recordChapterClosure(args) { calls.push(["closure", args]); return { status: "complete", closurePass: true, path: "story/closures/chapter-0001.json" }; },
    async chapterIntegrityCheck(args) { calls.push(["chapterIntegrity", args]); return { integrityPass: true, status: "clean", scope: "chapter", checkedChapters: 1 }; },
    async projectIntegrityCheck(args) { calls.push(["integrity", args]); return { integrityPass: true, status: "clean", checkedChapters: 1 }; }
  };
  return engine;
}

test("canonical body hash normalizes CRLF and surrounding whitespace", () => {
  assert.equal(canonicalBodySha256(" 甲\r\n乙 \n"), canonicalBodySha256("甲\n乙"));
});

test("recoverable finalizer runs the proven gate chain and closes the chapter", async () => {
  const engine = mockEngine();
  const result = await finalizeChapterRecoverable(engine, payload());
  assert.equal(result.productionProfile, "strict");
  assert.equal(result.integrity.scope, "project");
  assert.equal(result.finalizeMode, "recoverable-idempotent");
  assert.equal(result.integrity.status, "clean");
  assert.deepEqual(engine.calls.slice(0, 4).map(([name]) => name), ["commitStatus", "audit", "quality", "commit"]);
  assert.equal(engine.calls.at(-2)[0], "closure");
  assert.equal(engine.calls.at(-1)[0], "integrity");
  const causal = engine.calls.find(([name]) => name === "causal")[1];
  assert.equal(causal.event.chapter, 1);
  assert.equal(causal.event.bodySha256, result.bodySha256);
  const signature = engine.calls.find(([name, args]) => name === "ledger" && args.ledgerType === "chapterSignature")[1];
  assert.equal(signature.entry.chapter, 1);
  assert.equal(signature.entry.bodySha256, result.bodySha256);
});

test("recoverable finalizer resumes after an already committed request without redoing semantic gates", async () => {
  const engine = mockEngine({ committed: true });
  const result = await finalizeChapterRecoverable(engine, payload());
  assert.equal(result.commit.status, "committed");
  assert.equal(engine.calls.some(([name]) => name === "audit"), false);
  assert.equal(engine.calls.some(([name]) => name === "quality"), false);
  assert.equal(engine.calls.some(([name]) => name === "commit"), false);
  assert.equal(engine.calls.some(([name]) => name === "closure"), true);
});

test("balanced-fast finalizer uses chapter integrity except on five-chapter checkpoints", async () => {
  const fastEngine = mockEngine();
  const fastPayload = { ...payload(), expectedChapter: 2, productionProfile: "balanced-fast", signature: { ...payload().signature, chapterNo: 2 } };
  const fastResult = await finalizeChapterRecoverable(fastEngine, fastPayload);
  assert.equal(fastResult.integrity.scope, "chapter");
  assert.equal(fastEngine.calls.some(([name]) => name === "chapterIntegrity"), true);
  assert.equal(fastEngine.calls.some(([name]) => name === "integrity"), false);

  const checkpointEngine = mockEngine();
  const checkpointPayload = { ...payload(), expectedChapter: 5, productionProfile: "balanced-fast", signature: { ...payload().signature, chapterNo: 5 } };
  const checkpointResult = await finalizeChapterRecoverable(checkpointEngine, checkpointPayload);
  assert.equal(checkpointResult.integrity.scope, "project");
  assert.equal(checkpointEngine.calls.some(([name]) => name === "integrity"), true);
});

test("recoverable finalizer rejects requestId reuse for a different body", async () => {
  const engine = mockEngine({ committed: true, committedHash: "0".repeat(64) });
  await assert.rejects(() => finalizeChapterRecoverable(engine, payload()), (error) => error.code === "FINALIZE_IDEMPOTENCY_BODY_MISMATCH");
});

test("recoverable finalizer completes a real Engine chapter, closure and integrity chain", async (t) => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), "novel-finalize-integration-"));
  t.after(() => fs.rm(root, { recursive: true, force: true }));
  const engine = new NovelEngine({
    projectsRoot: root,
    minChapterChars: 10,
    minChapterHanChars: 20,
    targetChapterHanChars: 30,
    targetChapterHanCharsMax: 40,
    requireChapterAudit: true,
    requireCompleteAuditChecks: true,
    requireQualityGate: true,
    requireClosureReceipt: true
  });
  await engine.createProject({ projectId: "realbook", title: "真实收尾测试", genre: "奇幻" });
  const content = "汉".repeat(30);
  const bodySha256 = canonicalBodySha256(content);
  const auditChecks = Object.fromEntries(LOGIC_AUDIT_CATEGORIES.map((key) => [key, { status: "pass", evidence: "verified" }]));
  const continuityChecks = Object.fromEntries(["facts", "timeline", "knowledgeBoundary", "stateContinuity", "causality", "promiseContinuity", "relationshipContinuity"].map((key) => [key, "pass"]));
  const readerChecks = Object.fromEntries(["readability", "pacing", "repetition", "genreExperience", "hookQuality", "characterAgency"].map((key) => [key, "pass"]));

  const result = await finalizeChapterRecoverable(engine, {
    projectId: "realbook",
    expectedChapter: 1,
    title: "开端",
    content,
    summary: "主角迈出第一步。",
    requestId: "real-finalize-ch1",
    writerSessionId: "writer-real-1",
    audit: { decision: "pass", checks: auditChecks, issues: [], summary: "十七项通过。" },
    continuityReview: { reviewerRole: "continuity-auditor", reviewerSessionId: "continuity-real-1", bodySha256, conclusion: "pass", checks: continuityChecks, issues: [] },
    readerReview: { reviewerRole: "reader-editor", reviewerSessionId: "reader-real-1", bodySha256, conclusion: "pass", checks: readerChecks, issues: [] },
    genreGate: { bodySha256, pass: true },
    signature: { bodySha256, chapterNo: 1, function: "opening", rhythm: "balanced" }
  });

  assert.equal(result.bodySha256, bodySha256);
  assert.equal(result.closure.status, "complete");
  assert.equal(result.integrity.status, "clean");
  const committed = await engine.readChapter({ projectId: "realbook", chapter: 1 });
  assert.equal(committed.contentSha256, bodySha256);
  const signatures = await engine.storyLedgerQuery({ projectId: "realbook", ledgerType: "chapterSignature" });
  assert.equal(signatures.count, 1);
  assert.equal(signatures.entries[0].bodySha256, bodySha256);
  const scopedIntegrity = await engine.chapterIntegrityCheck({ projectId: "realbook", chapter: 1 });
  assert.equal(scopedIntegrity.integrityPass, true);
  assert.equal(scopedIntegrity.scope, "chapter");
});
