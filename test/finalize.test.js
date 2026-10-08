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

async function narrativeFixture(t) {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), "novel-narrative-finalize-"));
  t.after(() => fs.rm(root, { recursive: true, force: true }));
  const engine = new NovelEngine({ projectsRoot: root, minChapterChars: 10, minChapterHanChars: 20, targetChapterHanChars: 30, targetChapterHanCharsMax: 40, requireClosureReceipt: true });
  await engine.createProject({ projectId: "realbook", title: "合成叙事门禁", genre: "推理" });
  const content = "侦探看到沾血钥匙，认出血型后解开密室谜团。".repeat(2);
  const hash = canonicalBodySha256(content);
  const checks = (names) => Object.fromEntries(names.map((name) => [name, "pass"]));
  const input = {
    projectId: "realbook", expectedChapter: 1, title: "钥匙", content, summary: "钥匙与密室", requestId: "narrative-ch1", writerSessionId: "synthetic-writer",
    audit: { decision: "pass", checks: checks(LOGIC_AUDIT_CATEGORIES) },
    continuityReview: { ...review("continuity-auditor", "synthetic-continuity", hash), checks: checks(["facts", "timeline", "knowledgeBoundary", "stateContinuity", "causality", "promiseContinuity", "relationshipContinuity"]) },
    readerReview: { ...review("reader-editor", "synthetic-reader", hash), checks: checks(["readability", "pacing", "repetition", "genreExperience", "hookQuality", "characterAgency"]) },
    genreGate: { bodySha256: hash, pass: true }, signature: { bodySha256: hash, function: "investigation" }
  };
  return { engine, input, root, projectDir: path.join(root, "realbook") };
}

test("real finalizer rejects illegal narrative projections before any chapter commit", async (t) => {
  const invalid = [
    { code: "CAUSAL_REFERENCE_NOT_FOUND", extra: { causalEvents: [{ eventId: "effect", summary: "结果没有原因", status: "occurred", causes: ["missing"] }] } },
    { code: "CAUSAL_CAUSE_NOT_OCCURRED", extra: { causalEvents: [{ eventId: "effect", summary: "尚未发生的原因", status: "occurred", causes: ["future"] }, { eventId: "future", summary: "未来计划", status: "planned" }] } },
    { code: "CAUSAL_CYCLE", extra: { causalEvents: [{ eventId: "a", summary: "循环 A", status: "occurred", causes: ["b"] }, { eventId: "b", summary: "循环 B", status: "occurred", enables: ["a"] , causes: ["a"] }] } },
    { code: "FORESHADOW_TRANSITION_INVALID", extra: { foreshadowingEntries: [{ id: "orphan", status: "paid", plantedChapter: 1 }] } },
    { code: "FORESHADOW_TRANSITION_INVALID", extra: { continuityDelta: { foreshadowing: [{ id: "orphan", action: "payoff" }] } } }
  ];
  for (const item of invalid) await t.test(item.code, async (child) => {
    const { engine, input, projectDir } = await narrativeFixture(child);
    const beforeState = await fs.readFile(path.join(projectDir, "state.json"), "utf8");
    const beforeCausal = await fs.readFile(path.join(projectDir, "story", "causal-events.json"), "utf8");
    const beforeClues = await fs.readFile(path.join(projectDir, "story", "foreshadowing.json"), "utf8");
    await assert.rejects(finalizeChapterRecoverable(engine, { ...input, ...item.extra }), (error) => error.code === item.code);
    assert.equal((await engine.commitStatus({ projectId: input.projectId, requestId: input.requestId })).status, "not_found");
    assert.equal(await fs.readFile(path.join(projectDir, "state.json"), "utf8"), beforeState);
    assert.equal(await fs.readFile(path.join(projectDir, "story", "causal-events.json"), "utf8"), beforeCausal);
    assert.equal(await fs.readFile(path.join(projectDir, "story", "foreshadowing.json"), "utf8"), beforeClues);
    assert.deepEqual(await fs.readdir(path.join(projectDir, "requests", "commits")), []);
    assert.deepEqual(await fs.readdir(path.join(projectDir, "story", "quality", "history")), []);
  });
});

test("real finalizer topologically applies reverse-ordered causes and delta references", async (t) => {
  const { engine, input, projectDir } = await narrativeFixture(t);
  const result = await finalizeChapterRecoverable(engine, {
    ...input,
    causalEvents: [{ eventId: "effect", summary: "密室解开", status: "occurred", causes: ["blood"] }, { eventId: "blood", summary: "确认血型", status: "occurred", causes: ["key"] }, { eventId: "key", summary: "找到钥匙", status: "occurred", enables: ["blood"] }],
    continuityDelta: { causalEvents: [{ eventId: "effect", summary: "密室解开", status: "occurred", causes: ["blood"] }], foreshadowing: [{ id: "key-clue", action: "open" }, { id: "key-clue", action: "payoff" }] }
  });
  assert.deepEqual(result.steps.filter((step) => step.stage === "causalEvents").map((step) => step.id), ["key", "blood", "effect"]);
  assert.equal(result.closure.status, "complete");
  assert.equal(result.integrity.status, "clean");
  const ledger = JSON.parse(await fs.readFile(path.join(projectDir, "story", "foreshadowing.json"), "utf8"));
  assert.equal(ledger.entries[0].status, "paid");
  assert.equal(ledger.entries[0].plantedBodySha256, result.bodySha256);
});

test("finalizer resumes after terminal clue writes without reauditing or reopening clues", async (t) => {
  const { engine, input, projectDir } = await narrativeFixture(t);
  const request = { ...input, continuityDelta: { foreshadowing: [{ id: "key", action: "open" }] }, foreshadowingEntries: [{ id: "key", status: "advanced", notes: "确认血型" }, { id: "key", status: "paid", notes: "密室兑现" }], causalEvents: [{ eventId: "cause", summary: "证据成立", status: "occurred" }], memoryRecords: [{ id: "clue-memory", tier: "short", text: "沾血钥匙已经兑现" }] };
  let audits = 0;
  let qualities = 0;
  const audit = engine.recordChapterAudit.bind(engine);
  const quality = engine.recordChapterQuality.bind(engine);
  engine.recordChapterAudit = async (args) => { audits += 1; return audit(args); };
  engine.recordChapterQuality = async (args) => { qualities += 1; return quality(args); };
  const memory = engine.memoryRecord.bind(engine);
  let injected = false;
  engine.memoryRecord = async (args) => { if (!injected) { injected = true; throw new Error("synthetic failure after terminal clue writes"); } return memory(args); };
  await assert.rejects(finalizeChapterRecoverable(engine, request), /synthetic failure/);
  assert.equal((await engine.commitStatus({ projectId: input.projectId, requestId: input.requestId })).status, "committed");
  const resumed = await finalizeChapterRecoverable(engine, request);
  assert.equal(resumed.closure.status, "complete");
  assert.equal(resumed.integrity.status, "clean");
  assert.equal(audits, 1);
  assert.equal(qualities, 1);
  const clue = JSON.parse(await fs.readFile(path.join(projectDir, "story", "foreshadowing.json"), "utf8")).entries[0];
  assert.equal(clue.status, "paid");
  assert.equal(clue.plantedBodySha256, resumed.bodySha256);
  const replay = await finalizeChapterRecoverable(engine, request);
  assert.equal(replay.bodySha256, resumed.bodySha256);
  assert.equal(audits, 1);
});

test("finalizer rejects changed terminal notes for the same committed request and body", async (t) => {
  const { engine, input, projectDir } = await narrativeFixture(t);
  const request = { ...input, continuityDelta: { foreshadowing: [{ id: "seed", action: "open" }] }, foreshadowingEntries: [{ id: "seed", status: "paid", notes: "original" }] };
  await finalizeChapterRecoverable(engine, request);
  await finalizeChapterRecoverable(engine, request);
  const before = await fs.readFile(path.join(projectDir, "story", "foreshadowing.json"), "utf8");
  const beforeClosure = await fs.readFile(path.join(projectDir, "story", "closures", "chapter-0001.json"), "utf8");
  await assert.rejects(finalizeChapterRecoverable(engine, { ...request, foreshadowingEntries: [{ id: "seed", status: "paid", notes: "rewritten payoff" }] }), (error) => error.code === "FORESHADOW_TERMINAL_PAYLOAD_MISMATCH");
  assert.equal(await fs.readFile(path.join(projectDir, "story", "foreshadowing.json"), "utf8"), before);
  assert.equal(await fs.readFile(path.join(projectDir, "story", "closures", "chapter-0001.json"), "utf8"), beforeClosure);
  assert.equal((await engine.commitStatus({ projectId: input.projectId, requestId: input.requestId })).status, "committed");
});

test("finalizer replaces existing DAG edges as one valid batch and resumes after a later interruption", async (t) => {
  const { engine, input, projectDir } = await narrativeFixture(t);
  await finalizeChapterRecoverable(engine, { ...input, causalEvents: [{ eventId: "a", summary: "old a", status: "occurred", causes: [], enables: ["b"] }, { eventId: "b", summary: "old b", status: "occurred", causes: ["a"], enables: [] }] });
  const request = { ...input, expectedChapter: 2, requestId: "narrative-ch2", causalEvents: [{ eventId: "a", summary: "new a", status: "occurred", causes: ["b"], enables: [] }, { eventId: "b", summary: "new b", status: "occurred", causes: [], enables: ["a"] }], memoryRecords: [{ id: "batch-memory", tier: "short", text: "new causal chain" }] };
  const memory = engine.memoryRecord.bind(engine);
  let injected = false;
  engine.memoryRecord = async (args) => { if (!injected) { injected = true; throw new Error("synthetic interruption after causal batch"); } return memory(args); };
  await assert.rejects(finalizeChapterRecoverable(engine, request), /synthetic interruption after causal batch/);
  const graph = JSON.parse(await fs.readFile(path.join(projectDir, "story", "causal-events.json"), "utf8"));
  assert.deepEqual(graph.events.find((event) => event.eventId === "a").causes, ["b"]);
  assert.deepEqual(graph.events.find((event) => event.eventId === "a").enables, []);
  assert.deepEqual(graph.events.find((event) => event.eventId === "b").causes, []);
  assert.deepEqual(graph.events.find((event) => event.eventId === "b").enables, ["a"]);
  const recovered = await finalizeChapterRecoverable(engine, request);
  assert.equal(recovered.closure.status, "complete");
  assert.equal(recovered.integrity.status, "clean");
  assert.equal(recovered.steps.find((step) => step.stage === "commit").status, "reused");
  assert.deepEqual(recovered.steps.filter((step) => step.stage === "causalEvents").map((step) => step.id), ["b", "a"]);
});

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
  for (const name of ["audit", "quality", "commit", "closure", "integrity"]) {
    assert.equal(engine.calls.filter(([called]) => called === name).length, 1, `${name} should execute once inside the one finalizer invocation`);
  }
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
