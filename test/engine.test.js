import assert from "node:assert/strict";
import { promises as fs } from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { LOGIC_AUDIT_CATEGORIES, NovelEngine } from "../src/engine.js";
import { sha256 } from "../src/utils.js";

function passChecks() {
  return Object.fromEntries(LOGIC_AUDIT_CATEGORIES.map((category) => [category, { status: "pass", evidence: "verified" }]));
}

function bodyOf(count, token = "汉") {
  return token.repeat(count);
}

async function fixture(t, overrides = {}) {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), "novel-engine-v5-"));
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
    requireRevisionAudit: true,
    requireRevisionCas: true,
    requireClosureReceipt: false,
    ...overrides
  });
  await engine.createProject({ projectId: "book01", title: "测试长篇", genre: "奇幻" });
  return { root, engine, projectDir: path.join(root, "book01") };
}

async function approve(engine, chapter, body, suffix = String(chapter)) {
  const bodySha256 = sha256(body.replace(/\r\n?/g, "\n").trim());
  await engine.recordChapterAudit({
    projectId: "book01",
    chapter,
    stage: "precommit",
    decision: "pass",
    content: body,
    checks: passChecks(),
    summary: "全部十七项检查通过。"
  });
  await engine.recordChapterQuality({
    projectId: "book01",
    chapter,
    content: body,
    writerSessionId: `writer-${suffix}`,
    continuityReview: {
      reviewerRole: "continuity-auditor",
      reviewerSessionId: `continuity-${suffix}`,
      bodySha256,
      conclusion: "pass",
      checks: Object.fromEntries(["facts", "timeline", "knowledgeBoundary", "stateContinuity", "causality", "promiseContinuity", "relationshipContinuity"].map((key) => [key, "pass"])),
      issues: []
    },
    readerReview: {
      reviewerRole: "reader-editor",
      reviewerSessionId: `reader-${suffix}`,
      bodySha256,
      conclusion: "pass",
      checks: Object.fromEntries(["readability", "pacing", "repetition", "genreExperience", "hookQuality", "characterAgency"].map((key) => [key, "pass"])),
      issues: []
    },
    genreGate: { pass: true, bodySha256, experience: "on-promise" },
    signature: { bodySha256, rhythm: "balanced", closeIntensity: 6 }
  });
}

async function commitOne(engine, body = bodyOf(30), requestId = "commit-1", continuityDelta = {}) {
  await approve(engine, 1, body, requestId);
  return engine.commitChapter({
    projectId: "book01",
    expectedChapter: 1,
    title: "开端",
    content: body,
    summary: "主角迈出第一步。",
    continuityDelta,
    requestId
  });
}

async function expectCode(promise, code) {
  await assert.rejects(promise, (error) => {
    assert.equal(error.code, code, `Expected ${code}, received ${error.code}: ${error.message}`);
    return true;
  });
}

test("project configuration supports CAS and project-level writing contracts", async (t) => {
  const { engine } = await fixture(t);
  const before = await engine.projectConfigStatus("book01");
  assert.equal(before.revision, 1);
  const updated = await engine.configureProject({
    projectId: "book01",
    expectedRevision: 1,
    writingContract: { minHanChars: 28, targetMinHanChars: 36, targetMaxHanChars: 44 },
    quality: { requireClosureReceipt: true },
    genreProfile: { primary: "comedy", experienceTargets: { comedy: 7 } }
  });
  assert.equal(updated.revision, 2);
  assert.deepEqual(updated.writingContract, { minHanChars: 28, targetMinHanChars: 36, targetMaxHanChars: 44 });
  assert.equal(updated.quality.requireClosureReceipt, true);
  await expectCode(engine.configureProject({ projectId: "book01", expectedRevision: 1, writingContract: { minHanChars: 20 } }), "PROJECT_CONFIG_REVISION_MISMATCH");
});

test("the server hard-gates 2599 versus exactly 2600 Han characters", async (t) => {
  const { engine } = await fixture(t, { minChapterChars: 1, minChapterHanChars: 2600, targetChapterHanChars: 3000, targetChapterHanCharsMax: 3400 });
  await expectCode(engine.recordChapterAudit({ projectId: "book01", chapter: 1, decision: "pass", content: bodyOf(2599), checks: passChecks() }), "CHAPTER_LENGTH_BELOW_MINIMUM");
  const exact = bodyOf(2600);
  const audit = await engine.recordChapterAudit({ projectId: "book01", chapter: 1, decision: "pass", content: exact, checks: passChecks() });
  assert.equal(audit.contentHanChars, 2600);
  await engine.recordChapterQuality({
    projectId: "book01", chapter: 1, content: exact, writerSessionId: "w-2600",
    continuityReview: { reviewerRole: "continuity-auditor", reviewerSessionId: "c-2600", bodySha256: sha256(exact), conclusion: "pass", checks: Object.fromEntries(["facts", "timeline", "knowledgeBoundary", "stateContinuity", "causality", "promiseContinuity", "relationshipContinuity"].map((key) => [key, "pass"])), issues: [] },
    readerReview: { reviewerRole: "reader-editor", reviewerSessionId: "r-2600", bodySha256: sha256(exact), conclusion: "pass", checks: Object.fromEntries(["readability", "pacing", "repetition", "genreExperience", "hookQuality", "characterAgency"].map((key) => [key, "pass"])), issues: [] },
    genreGate: { pass: true, bodySha256: sha256(exact) },
    signature: { bodySha256: sha256(exact), rhythm: "balanced" }
  });
  const committed = await engine.commitChapter({ projectId: "book01", expectedChapter: 1, title: "精确门槛", content: exact, summary: "精确达到门槛。", requestId: "exact-2600" });
  assert.equal(committed.contentHanChars, 2600);
  assert.equal(committed.serverGate.lengthPass, true);
});

test("passing audits require all 17 configured categories", async (t) => {
  const { engine } = await fixture(t);
  const incomplete = passChecks();
  delete incomplete.oppositionPressure;
  await expectCode(engine.recordChapterAudit({ projectId: "book01", chapter: 1, decision: "pass", content: bodyOf(30), checks: incomplete }), "AUDIT_CHECK_COVERAGE_INCOMPLETE");
  const packet = await engine.prepareLogicAudit({ projectId: "book01", chapter: 1 });
  assert.deepEqual(packet.auditContract.requiredCategories, LOGIC_AUDIT_CATEGORIES);
  assert.equal(packet.auditContract.requiredCategories.length, 17);
});

test("quality receipts require independent Writer, Continuity Auditor and Reader Editor sessions", async (t) => {
  const { engine } = await fixture(t);
  const body = bodyOf(30);
  const bodySha256 = sha256(body);
  const continuityChecks = Object.fromEntries(["facts", "timeline", "knowledgeBoundary", "stateContinuity", "causality", "promiseContinuity", "relationshipContinuity"].map((key) => [key, "pass"]));
  const readerChecks = Object.fromEntries(["readability", "pacing", "repetition", "genreExperience", "hookQuality", "characterAgency"].map((key) => [key, "pass"]));
  await expectCode(engine.recordChapterQuality({
    projectId: "book01", chapter: 1, content: body, writerSessionId: "writer",
    continuityReview: { reviewerRole: "continuity-auditor", reviewerSessionId: "continuity", conclusion: "pass", checks: continuityChecks, issues: [] },
    readerReview: { reviewerRole: "reader-editor", reviewerSessionId: "reader", bodySha256, conclusion: "pass", checks: readerChecks, issues: [] },
    genreGate: { pass: true, bodySha256 }, signature: { bodySha256, rhythm: "balanced" }
  }), "REVIEW_BODY_HASH_REQUIRED");
  await expectCode(engine.recordChapterQuality({
    projectId: "book01", chapter: 1, content: body, writerSessionId: "same",
    continuityReview: { reviewerRole: "continuity-auditor", reviewerSessionId: "same", bodySha256, conclusion: "pass", checks: continuityChecks, issues: [] },
    readerReview: { reviewerRole: "reader-editor", reviewerSessionId: "reader", bodySha256, conclusion: "pass", checks: readerChecks, issues: [] },
    genreGate: { pass: true, bodySha256 }, signature: { bodySha256, rhythm: "balanced" }
  }), "REVIEW_SESSION_NOT_INDEPENDENT");
  const receipt = await engine.recordChapterQuality({
    projectId: "book01", chapter: 1, content: body, writerSessionId: "writer",
    continuityReview: { reviewerRole: "continuity-auditor", reviewerSessionId: "continuity", bodySha256, conclusion: "pass", checks: continuityChecks, issues: [] },
    readerReview: { reviewerRole: "reader-editor", reviewerSessionId: "reader", bodySha256, conclusion: "pass", checks: readerChecks, issues: [] },
    genreGate: { pass: true, bodySha256 }, signature: { bodySha256, rhythm: "balanced" }
  });
  assert.equal(receipt.qualityPass, true);
});

test("commit is payload-bound and idempotent, and rejects duplicate headings", async (t) => {
  const { engine } = await fixture(t);
  const body = bodyOf(30);
  await approve(engine, 1, body, "idempotent");
  await expectCode(engine.commitChapter({ projectId: "book01", expectedChapter: 1, title: "第1章 错误标题", content: body, summary: "摘要", requestId: "bad-heading" }), "CHAPTER_TITLE_NOT_PURE");
  const first = await engine.commitChapter({ projectId: "book01", expectedChapter: 1, title: "纯标题", content: body, summary: "摘要", requestId: "stable-request" });
  assert.equal(first.confirmed, true);
  assert.equal(first.chapterNo, 1);
  assert.equal(first.requestId, "stable-request");
  assert.equal(first.bodySha256, first.contentSha256);
  const replay = await engine.commitChapter({ projectId: "book01", expectedChapter: 1, title: "纯标题", content: body, summary: "摘要", requestId: "stable-request" });
  assert.equal(replay.idempotentReplay, true);
  assert.equal(replay.contentSha256, first.contentSha256);
  await expectCode(engine.commitChapter({ projectId: "book01", expectedChapter: 1, title: "改了标题", content: body, summary: "摘要", requestId: "stable-request" }), "IDEMPOTENCY_PAYLOAD_MISMATCH");
  const wrongRequest = await engine.commitStatus({ projectId: "book01", chapter: 1, requestId: "different-request" });
  assert.equal(wrongRequest.status, "not_found");
  assert.equal(wrongRequest.source, "request-mismatch");
});

test("chapter body hashing is stable across CRLF and trailing whitespace", async (t) => {
  const { engine } = await fixture(t);
  const canonical = bodyOf(30);
  const transportBody = `\r\n${canonical}\r\n\r\n`;
  await approve(engine, 1, transportBody, "canonical-hash");
  const committed = await engine.commitChapter({ projectId: "book01", expectedChapter: 1, title: "统一哈希", content: transportBody, summary: "换行规范化。", requestId: "canonical-hash" });
  assert.equal(committed.bodySha256, sha256(canonical));
});

test("prepared multi-file commits recover after an injected crash and reconcile by requestId", async (t) => {
  const { root, engine } = await fixture(t, { __testFailAfterTargetWrites: 3 });
  const body = bodyOf(30);
  await approve(engine, 1, body, "crash");
  await expectCode(engine.commitChapter({ projectId: "book01", expectedChapter: 1, title: "恢复", content: body, summary: "崩溃恢复测试。", requestId: "crash-request" }), "TEST_INJECTED_TRANSACTION_FAILURE");
  const recoveredEngine = new NovelEngine({
    projectsRoot: root, minChapterChars: 10, minChapterHanChars: 20, targetChapterHanChars: 30, targetChapterHanCharsMax: 40,
    requireChapterAudit: true, requireCompleteAuditChecks: true, requireQualityGate: true
  });
  const status = await recoveredEngine.commitStatus({ projectId: "book01", requestId: "crash-request" });
  assert.equal(status.status, "committed");
  assert.equal(status.chapter, 1);
  assert.ok(status.recoveredTransactions.length >= 1);
  const read = await recoveredEngine.readChapter({ projectId: "book01", chapter: 1 });
  assert.equal(read.found, true);
});

test("dynamic state and tiered memory are body-hash-bound and searchable", async (t) => {
  const { engine } = await fixture(t);
  const committed = await commitOne(engine);
  const state = await engine.dynamicStateUpdate({
    projectId: "book01", chapter: 1, bodySha256: committed.contentSha256,
    characters: [{ characterId: "hero", location: "black-village", health: "light-injury" }],
    knowledge: [{ knowerId: "hero", factId: "well-chain", confidence: 0.8 }],
    inventory: [{ itemId: "old-knife", ownerId: "hero" }],
    locations: [{ locationId: "black-village", weather: "rain" }]
  });
  assert.equal(state.updatedCounts.characters, 1);
  await expectCode(engine.dynamicStateUpdate({ projectId: "book01", chapter: 1, bodySha256: sha256("wrong"), characters: [{ characterId: "hero" }] }), "SOURCE_BODY_HASH_MISMATCH");
  await engine.memoryRecord({ projectId: "book01", records: [
    { id: "short-1", tier: "short", text: "主角在黑石村发现井底铁链声", chapter: 1, sourceSha256: committed.contentSha256, tags: ["主角", "铁链"] },
    { id: "long-1", tier: "long", text: "早期伏笔：井底铁链连接后山遗迹", chapter: 1, sourceSha256: committed.contentSha256, tags: ["伏笔", "遗迹"], importance: 9 }
  ] });
  const found = await engine.memorySearch({ projectId: "book01", query: "井底铁链和后山遗迹", tiers: ["long"], topK: 5 });
  assert.equal(found.results[0].id, "long-1");
});

test("Promise, relationship, opposition and chapter-signature ledgers persist with CAS", async (t) => {
  const { engine } = await fixture(t);
  const committed = await commitOne(engine);
  const promise = await engine.storyLedgerUpsert({ projectId: "book01", ledgerType: "promise", entry: { id: "promise-map", promise: "新地图会回应主角", status: "open", openedChapter: 1, sourceChapter: 1, bodySha256: committed.contentSha256, payoffWindow: { start: 5, end: 20 } }, expectedRevision: 0 });
  assert.equal(promise.revision, 1);
  await expectCode(engine.storyLedgerUpsert({ projectId: "book01", ledgerType: "promise", entry: { id: "promise-two", promise: "冲突", status: "open", sourceChapter: 1, bodySha256: committed.contentSha256 }, expectedRevision: 0 }), "LEDGER_REVISION_MISMATCH");
  await engine.storyLedgerUpsert({ projectId: "book01", ledgerType: "relationship", entry: { fromId: "hero", toId: "partner", sourceChapter: 1, bodySha256: committed.contentSha256, dimensions: { trust: 12, resentment: 4 }, unresolved: ["秘密未说明"] } });
  await engine.storyLedgerUpsert({ projectId: "book01", ledgerType: "oppositionClock", entry: { id: "enemy-clock", status: "active", sourceChapter: 1, bodySha256: committed.contentSha256, progress: 30, deadlineChapter: 8, nextAction: "封锁村口" } });
  await engine.storyLedgerUpsert({ projectId: "book01", ledgerType: "chapterSignature", entry: { chapter: 1, sourceChapter: 1, bodySha256: committed.contentSha256, experienceScores: { comedy: 5, adventure: 7 }, plannedBeatIds: ["B001"], fulfilledBeatIds: ["B001"] } });
  const due = await engine.storyLedgerQuery({ projectId: "book01", ledgerType: "promise", chapter: 5, horizon: 3 });
  assert.equal(due.entries[0].id, "promise-map");
});

test("required closure blocks the next chapter until durable evidence is recorded", async (t) => {
  const { engine } = await fixture(t);
  await engine.configureProject({ projectId: "book01", expectedRevision: 1, quality: { requireClosureReceipt: true } });
  const body = bodyOf(30);
  const committed = await commitOne(engine, body, "closure-commit", { dynamicState: [{ characterId: "hero" }] });
  await engine.writeArtifact({ projectId: "book01", artifactType: "chapter-outline", key: "2", content: "第二章继续推进。" });
  await expectCode(engine.prepareChapter("book01"), "PREVIOUS_CHAPTER_CLOSURE_INCOMPLETE");
  await engine.dynamicStateUpdate({ projectId: "book01", chapter: 1, bodySha256: committed.contentSha256, characters: [{ characterId: "hero", location: "village" }] });
  await expectCode(engine.recordChapterClosure({ projectId: "book01", chapter: 1, bodySha256: committed.contentSha256, operations: { memoryIndex: { status: "skipped" } } }), "CLOSURE_SKIP_REASON_REQUIRED");
  const closure = await engine.recordChapterClosure({ projectId: "book01", chapter: 1, bodySha256: committed.contentSha256, operations: {
    causalEvents: { status: "skipped", reason: "No causal-event change in this chapter." },
    foreshadowing: { status: "skipped", reason: "No foreshadowing change in this chapter." },
    promisePayoff: { status: "skipped", reason: "No promise change in this chapter." },
    relationshipGraph: { status: "skipped", reason: "No relationship change in this chapter." },
    oppositionClocks: { status: "skipped", reason: "No opposition-clock change in this chapter." },
    chapterSignature: { status: "skipped", reason: "Signature is not part of this fixture." },
    dynamicState: { status: "completed", evidence: "story/dynamic/state.json", reason: "State ledger updated." },
    memoryIndex: { status: "skipped", reason: "No memory change in this chapter." }
  } });
  assert.equal(closure.status, "complete");
  const packet = await engine.prepareChapter("book01");
  assert.equal(packet.ready, true);
  assert.equal(packet.chapter, 2);
});

test("chapter revision uses CAS, preserves a backup and supports idempotent replay", async (t) => {
  const { engine, projectDir } = await fixture(t);
  await commitOne(engine);
  const before = await engine.readChapter({ projectId: "book01", chapter: 1 });
  const revisedBody = bodyOf(35, "修");
  await approve(engine, 1, revisedBody, "revision");
  const beforeRevisionIntegrity = await engine.projectIntegrityCheck({ projectId: "book01" });
  assert.equal(beforeRevisionIntegrity.integrityPass, true, "staged revision audit/quality must not replace current pointers before revise succeeds");
  const revised = await engine.reviseChapter({ projectId: "book01", chapter: 1, title: "修订后", content: revisedBody, summary: "修订摘要。", changeNote: "增强人物动机", expectedBodySha256: before.contentSha256, expectedRevision: before.revision, requestId: "revision-request" });
  assert.equal(revised.revision, 2);
  assert.equal((await fs.readFile(path.join(projectDir, revised.backup), "utf8")).includes("第1章 开端"), true);
  const replay = await engine.reviseChapter({ projectId: "book01", chapter: 1, title: "修订后", content: revisedBody, summary: "修订摘要。", changeNote: "增强人物动机", expectedBodySha256: before.contentSha256, expectedRevision: before.revision, requestId: "revision-request" });
  assert.equal(replay.idempotentReplay, true);
  await expectCode(engine.reviseChapter({ projectId: "book01", chapter: 1, title: "再次改", content: bodyOf(36, "再"), summary: "再次修改", expectedBodySha256: before.contentSha256, expectedRevision: 1, requestId: "new-revision" }), "REVISION_BODY_CAS_MISMATCH");
  const integrity = await engine.projectIntegrityCheck({ projectId: "book01" });
  assert.equal(integrity.integrityPass, true);
});

test("integrity check detects stale state and memory bindings after a chapter revision", async (t) => {
  const { engine } = await fixture(t);
  const committed = await commitOne(engine);
  await engine.dynamicStateUpdate({ projectId: "book01", chapter: 1, bodySha256: committed.contentSha256, characters: [{ characterId: "hero", mood: "calm" }] });
  await engine.memoryRecord({ projectId: "book01", records: [{ id: "memory-old", tier: "long", text: "旧正文中的关键事实", chapter: 1, sourceSha256: committed.contentSha256 }] });
  const before = await engine.readChapter({ projectId: "book01", chapter: 1 });
  const revisedBody = bodyOf(35, "新");
  await approve(engine, 1, revisedBody, "stale-revision");
  await engine.reviseChapter({ projectId: "book01", chapter: 1, content: revisedBody, summary: "新摘要", expectedBodySha256: before.contentSha256, expectedRevision: 1, requestId: "stale-revision" });
  const integrity = await engine.projectIntegrityCheck({ projectId: "book01" });
  assert.equal(integrity.integrityPass, false);
  assert.ok(integrity.errors.some((item) => item.code === "DYNAMIC_STATE_STALE_BINDING"));
  assert.ok(integrity.errors.some((item) => item.code === "MEMORY_STALE_BINDING"));
});

test("artifact writes support SHA-256 CAS and preserve prior versions", async (t) => {
  const { engine, projectDir } = await fixture(t);
  const first = await engine.writeArtifact({ projectId: "book01", artifactType: "premise", content: "初版前提" });
  await expectCode(engine.writeArtifact({ projectId: "book01", artifactType: "premise", content: "冲突版本", expectedSha256: sha256("wrong") }), "ARTIFACT_CAS_MISMATCH");
  const second = await engine.writeArtifact({ projectId: "book01", artifactType: "premise", content: "第二版前提", expectedSha256: first.sha256 });
  assert.notEqual(second.sha256, first.sha256);
  const versionFiles = await fs.readdir(path.join(projectDir, "versions", "artifacts", "premise-default"));
  assert.ok(versionFiles.length >= 1);
});

test("integrity repair safely creates missing chapter metadata", async (t) => {
  const { engine, projectDir } = await fixture(t, { requireChapterAudit: false, requireQualityGate: false, requireRevisionAudit: false });
  await engine.configureProject({ projectId: "book01", expectedRevision: 1, quality: { requireChapterAudit: false, requireQualityGate: false, requireRevisionAudit: false } });
  const body = bodyOf(30);
  await engine.commitChapter({ projectId: "book01", expectedChapter: 1, title: "无审计兼容", content: body, summary: "兼容测试", requestId: "legacy-like" });
  await fs.unlink(path.join(projectDir, "chapters", "meta", "chapter-0001.json"));
  const before = await engine.projectIntegrityCheck({ projectId: "book01", repair: false });
  assert.ok(before.errors.some((item) => item.code === "CHAPTER_META_MISSING"));
  const repaired = await engine.projectIntegrityCheck({ projectId: "book01", repair: true });
  assert.ok(repaired.repairs.some((item) => item.code === "META_CREATED"));
  assert.equal(repaired.integrityPass, true);
});

test("prepare chapter packet includes dynamic state, tiered memory and 17-category audit contract", async (t) => {
  const { engine } = await fixture(t);
  await engine.writeArtifact({ projectId: "book01", artifactType: "chapter-outline", key: "1", content: "主角在井边听见铁链声。" });
  const packet = await engine.prepareChapter("book01");
  assert.equal(packet.ready, true);
  assert.equal(packet.chapter, 1);
  assert.equal(packet.context.auditContract.requiredCategories.length, 17);
  assert.ok(packet.context.dynamicState);
  assert.ok(packet.context.memory);
  assert.ok(packet.packet.includes("三级历史记忆候选"));
});

test("reference import is constrained to configured roots", async (t) => {
  const importRoot = await fs.mkdtemp(path.join(os.tmpdir(), "novel-imports-"));
  t.after(() => fs.rm(importRoot, { recursive: true, force: true }));
  const { engine } = await fixture(t, { importRoots: [importRoot] });
  const allowed = path.join(importRoot, "reference.txt");
  await fs.writeFile(allowed, "第一章\n参考文本。\n\n第二章\n更多参考文本。", "utf8");
  const imported = await engine.importReference({ projectId: "book01", sourcePath: allowed, title: "参考书" });
  assert.ok(imported.totalChunks >= 1);
  const outside = path.join(os.tmpdir(), "outside-reference.txt");
  await fs.writeFile(outside, "不允许导入", "utf8");
  t.after(() => fs.rm(outside, { force: true }));
  await expectCode(engine.importReference({ projectId: "book01", sourcePath: outside }), "REFERENCE_PATH_NOT_ALLOWED");
});

test("legacy projects are lazily migrated without retroactively failing old chapters", async (t) => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), "novel-engine-legacy-"));
  t.after(() => fs.rm(root, { recursive: true, force: true }));
  const legacy = new NovelEngine({
    projectsRoot: root,
    minChapterChars: 1,
    minChapterHanChars: 0,
    targetChapterHanChars: 0,
    targetChapterHanCharsMax: 0,
    requireChapterAudit: false,
    requireQualityGate: false,
    requireRevisionAudit: false
  });
  await legacy.createProject({ projectId: "legacy01", title: "旧项目" });
  await legacy.configureProject({ projectId: "legacy01", expectedRevision: 1, writingContract: { minHanChars: 0, targetMinHanChars: 0, targetMaxHanChars: 0 }, quality: { requireChapterAudit: false, requireQualityGate: false, requireRevisionAudit: false } });
  await legacy.commitChapter({ projectId: "legacy01", expectedChapter: 1, title: "旧章", content: bodyOf(10), summary: "旧摘要", requestId: "legacy-commit" });
  const projectDir = path.join(root, "legacy01");
  await fs.rm(path.join(projectDir, "project-config.json"), { force: true });
  await fs.rm(path.join(projectDir, "chapters", "meta", "chapter-0001.json"), { force: true });
  await fs.rm(path.join(projectDir, "story", "closures", "chapter-0001.json"), { force: true });

  const upgraded = new NovelEngine({
    projectsRoot: root,
    minChapterChars: 10,
    minChapterHanChars: 20,
    targetChapterHanChars: 30,
    targetChapterHanCharsMax: 40,
    requireChapterAudit: true,
    requireCompleteAuditChecks: true,
    requireQualityGate: true
  });
  const config = await upgraded.projectConfigStatus("legacy01");
  assert.equal(config.migratedFromLegacy, true);
  assert.equal(config.enforcement.lengthFromChapter, 2);
  assert.equal(config.enforcement.qualityFromChapter, 2);
  const integrity = await upgraded.projectIntegrityCheck({ projectId: "legacy01" });
  assert.equal(integrity.integrityPass, true);
  assert.ok(integrity.warnings.some((item) => item.code === "LEGACY_CHAPTER_BELOW_CURRENT_MINIMUM"));
  assert.ok(integrity.warnings.some((item) => item.code === "CHAPTER_META_MISSING"));
});
