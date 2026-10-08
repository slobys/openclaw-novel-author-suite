import assert from "node:assert/strict";
import { promises as fs } from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { LOGIC_AUDIT_CATEGORIES, NovelEngine } from "../src/engine.js";
import { finalizeChapterRecoverable } from "../src/finalize.js";
import { sha256 } from "../src/utils.js";

test("M2 fix protects legal stageId identity in actual Writer/Reader packets", async (t) => {
  for (const length of [16, 128]) for (const profile of ["balanced-fast", "compact"]) for (const role of ["writer", "reader-editor"]) {
    await t.test(`${length}-character ${profile} ${role}`, async (child) => {
      const { engine, projectDir } = await fixture(child, { minChapterChars: 800, minChapterHanChars: 2000, targetChapterHanChars: 2600, targetChapterHanCharsMax: 3200, requireClosureReceipt: true });
      const stageId = "s".repeat(length);
      const plan = { schemaVersion: "novel-stage-plan-v1", stages: [{ id: stageId, startChapter: 1, endChapter: 5, goal: "查清故障并承担后果" }] };
      await engine.writeArtifact({ projectId: "book01", artifactType: "stage-plan", content: JSON.stringify(plan) });
      const content = "文".repeat(2000), bodySha256 = sha256(content);
      const checks = (names) => Object.fromEntries(names.map((name) => [name, "pass"]));
      const committed = await finalizeChapterRecoverable(engine, {
        projectId: "book01", expectedChapter: 1, title: "线索", content, summary: "故障的线索", requestId: "protected-stage-ch1", writerSessionId: "synthetic-stage-writer",
        audit: { decision: "pass", checks: checks(LOGIC_AUDIT_CATEGORIES), issues: [] },
        continuityReview: { reviewerRole: "continuity-auditor", reviewerSessionId: "synthetic-stage-continuity", bodySha256, conclusion: "pass", checks: checks(["facts", "timeline", "knowledgeBoundary", "stateContinuity", "causality", "promiseContinuity", "relationshipContinuity"]), issues: [] },
        readerReview: { reviewerRole: "reader-editor", reviewerSessionId: "synthetic-stage-reader", bodySha256, conclusion: "pass", checks: checks(["readability", "pacing", "repetition", "genreExperience", "hookQuality", "characterAgency"]), issues: [] },
        genreGate: { bodySha256, pass: true }, signature: { bodySha256, stageId, function: "调查与后果".repeat(100), solutionMode: "协作取证".repeat(100) }
      });
      assert.equal(committed.closure.status, "complete");
      assert.equal(committed.integrity.status, "clean");
      await engine.writeArtifact({ projectId: "book01", artifactType: "chapter-outline", key: "2", content: "进一步调查，保留旧代价" });
      const query = await engine.storyLedgerQuery({ projectId: "book01", ledgerType: "chapterSignature", chapter: 1, limit: 3 });
      assert.equal(query.entries[0].stageId, stageId);
      const protectedPaths = ["state.json", "story/ledgers/chapter-signatures.json", "blueprint/stage-plan.json", "chapters/chapter-0001.md", "chapters/meta/chapter-0001.json"];
      const before = await Promise.all(protectedPaths.map(async (relative) => sha256(await fs.readFile(path.join(projectDir, relative), "utf8"))));
      const prepared = await engine.prepareChapter("book01", { profile, role });
      const after = await Promise.all(protectedPaths.map(async (relative) => sha256(await fs.readFile(path.join(projectDir, relative), "utf8"))));
      assert.deepEqual(after, before, "Prepare must not modify persisted identity or source files");
      const heading = "\n## 最近三章精简结构签名（chapter/bodySha256 为来源）\n";
      const entries = JSON.parse(prepared.packet.split(heading)[1].split("\n")[0]);
      assert.equal(entries.length, 1);
      assert.equal(entries[0].chapter, 1);
      assert.equal(entries[0].bodySha256, committed.bodySha256);
      assert.equal(prepared.stageContext.latestObservedStageId, stageId);
      assert.equal(prepared.stageContext.plannedStage.id, stageId);
      assert.ok(entries[0].function.length <= 80 && entries[0].solutionMode.length <= 80, "Narrative dimensions remain bounded");
      assert.ok(entries[0].function.includes("资料已按快档上限截断"));
      assert.ok(prepared.packetChars <= (role === "writer" ? 16000 : 6000));
      child.diagnostic(JSON.stringify({ length, profile, role, signatureStageIdChars: entries[0].stageId.length, bodySha256: entries[0].bodySha256, packetChars: prepared.packetChars }));
      assert.equal(entries[0].stageId, stageId, "Protected stage ID must preserve the official source identity");
      if (length === 128) {
        await engine.writeArtifact({ projectId: "book01", artifactType: "chapter-outline", key: "2", content: "必需章纲".repeat(4000) });
        await expectCode(engine.prepareChapter("book01", { profile, role }), "PREPARE_REQUIRED_CONTEXT_BUDGET_EXCEEDED");
      }
    });
  }
});

test("M2 length guidance keeps resolved target and samples the last five committed Meta records", async (t) => {
  const { engine } = await fixture(t, { requireChapterAudit: false, requireQualityGate: false });
  for (let chapter = 1; chapter <= 10; chapter += 1) {
    await engine.writeArtifact({ projectId: "book01", artifactType: "chapter-outline", key: String(chapter), content: "调查与后果" });
    const prepared = await engine.prepareChapter("book01");
    assert.equal(prepared.lengthGuidance.targetMinHanChars, 30);
    assert.equal(prepared.lengthGuidance.configRevision, 1);
    await engine.commitChapter({ projectId: "book01", expectedChapter: chapter, title: "调查", content: bodyOf(40 - chapter * 2), summary: "真实合成章", requestId: `m2-${chapter}` });
  }
  await engine.writeArtifact({ projectId: "book01", artifactType: "chapter-outline", key: "11", content: "处理后果" });
  const prepared = await engine.prepareChapter("book01");
  assert.deepEqual(prepared.lengthGuidance.samples.map((s) => s.chapter), [6, 7, 8, 9, 10]);
  assert.equal(prepared.lengthGuidance.metrics.netChangeHanChars, -8);
  assert.equal(prepared.lengthGuidance.metrics.consecutiveBelowTarget, 5);
  assert.ok(prepared.lengthGuidance.samples.every((s) => /^[a-f0-9]{64}$/.test(s.bodySha256)));
  assert.ok(prepared.lengthGuidance.warnings.includes("RECENT_CHAPTER_LENGTH_DECLINING"));
  assert.ok(prepared.lengthGuidance.warnings.includes("RECENT_CHAPTERS_PERSISTENTLY_BELOW_PREFERRED_TARGET"));
});

test("M2 Writer and Reader receive three complete bounded signatures with source hashes", async (t) => {
  const { engine } = await fixture(t, { requireChapterAudit: false, requireQualityGate: false });
  for (let chapter = 1; chapter <= 3; chapter += 1) {
    const body = bodyOf(30 + chapter);
    await engine.commitChapter({ projectId: "book01", expectedChapter: chapter, title: "调查", content: body, summary: "调查", requestId: `sig-${chapter}` });
    await engine.storyLedgerUpsert({ projectId: "book01", ledgerType: "chapterSignature", entry: { chapter, bodySha256: sha256(body), function: `FUNCTION-${chapter}`, solutionMode: `SOLUTION-${chapter}`, notes: "冗余".repeat(3000) } });
  }
  await engine.writeArtifact({ projectId: "book01", artifactType: "chapter-outline", key: "4", content: "承担选择后果" });
  for (const profile of ["balanced-fast", "compact"]) for (const role of ["writer", "reader-editor"]) {
    const prepared = await engine.prepareChapter("book01", { profile, role });
    for (let chapter = 1; chapter <= 3; chapter += 1) {
      assert.ok(prepared.packet.includes(`FUNCTION-${chapter}`));
      assert.ok(prepared.packet.includes(`SOLUTION-${chapter}`));
      assert.ok(prepared.packet.includes(sha256(bodyOf(30 + chapter))));
    }
    assert.ok(prepared.packet.length <= (role === "writer" ? 16000 : 6000));
  }
});

test("M2 Prepare invalidates independent-engine ledger, dynamic state and memory writes", async (t) => {
  const { engine, root } = await fixture(t);
  const committed = await commitOne(engine);
  await engine.writeArtifact({ projectId: "book01", artifactType: "chapter-outline", key: "2", content: "处理债务" });
  const other = new NovelEngine({ ...engine.config, projectsRoot: root });
  let previous = await engine.prepareChapter("book01", { role: "continuity-auditor" });
  const mutations = [
    () => other.storyLedgerUpsert({ projectId: "book01", ledgerType: "promise", entry: { id: "debt", sourceChapter: 1, bodySha256: committed.bodySha256, promise: "PROMISE-NEW", status: "open" } }),
    () => other.dynamicStateUpdate({ projectId: "book01", chapter: 1, bodySha256: committed.bodySha256, characters: [{ characterId: "hero", description: "DYNAMIC-NEW" }] }),
    () => other.memoryRecord({ projectId: "book01", chapter: 1, bodySha256: committed.bodySha256, records: [{ id: "debt-memory", tier: "short", text: "处理债务 MEMORY-NEW", importance: 1 }] })
  ];
  for (const mutate of mutations) {
    await mutate();
    const current = await engine.prepareChapter("book01");
    assert.notEqual(current.contextSnapshot.key, previous.contextSnapshot.key);
    assert.equal(current.contextSnapshot.reused, false);
    previous = current;
  }
  const full = await engine.prepareChapter("book01", { profile: "full" });
  assert.ok(full.packet.includes("PROMISE-NEW"));
  assert.ok(full.packet.includes("DYNAMIC-NEW"));
  assert.ok(full.packet.includes("MEMORY-NEW"));
});

test("M2 stage plan validates before artifact history/state writes and distinguishes planned from observed", async (t) => {
  const { engine, projectDir } = await fixture(t);
  const committed = await commitOne(engine);
  await engine.storyLedgerUpsert({ projectId: "book01", ledgerType: "chapterSignature", entry: { chapter: 1, bodySha256: committed.bodySha256, function: "investigate", stageId: "village" } });
  await engine.storyLedgerUpsert({ projectId: "book01", ledgerType: "promise", entry: { id: "debt", sourceChapter: 1, bodySha256: committed.bodySha256, promise: "OLD-DEBT", status: "open" } });
  const plan = { schemaVersion: "novel-stage-plan-v1", stages: [{ id: "village", startChapter: 1, endChapter: 1, goal: "查清故障", costs: ["旧债不能清零"], carryForwardPromiseIds: ["debt"], nextStageId: "city", bridgeToNext: { condition: "证据指向城市", foreshadowingIds: ["future-clue"] } }, { id: "city", startChapter: 2, endChapter: 8, goal: "组织协作" }] };
  const saved = await engine.writeArtifact({ projectId: "book01", artifactType: "stage-plan", content: JSON.stringify(plan) });
  const beforeState = await fs.readFile(path.join(projectDir, "state.json"), "utf8");
  const before = await engine.readArtifact({ projectId: "book01", artifactType: "stage-plan" });
  for (const invalid of ["{", JSON.stringify({ ...plan, schemaVersion: "wrong" }), JSON.stringify({ ...plan, stages: [plan.stages[0], { ...plan.stages[1], startChapter: 1 }] }), JSON.stringify({ ...plan, stages: [{ ...plan.stages[0], nextStageId: "missing" }] }), JSON.stringify({ ...plan, stages: [{ ...plan.stages[0], costs: [42] }] })]) {
    await expectCode(engine.writeArtifact({ projectId: "book01", artifactType: "stage-plan", content: invalid }), "INVALID_STAGE_PLAN");
    assert.equal(await fs.readFile(path.join(projectDir, "state.json"), "utf8"), beforeState);
    assert.equal((await engine.readArtifact({ projectId: "book01", artifactType: "stage-plan" })).content, before.content);
  }
  assert.equal(await fs.access(path.join(projectDir, "versions/artifacts/stage-plan-default")).then(() => true).catch(() => false), false);
  await engine.writeArtifact({ projectId: "book01", artifactType: "chapter-outline", key: "2", content: "承担旧债" });
  for (const role of ["writer", "continuity-auditor", "reader-editor"]) {
    const prepared = await engine.prepareChapter("book01", { role });
    assert.equal(prepared.stageContext.plannedStage.id, "city");
    assert.equal(prepared.stageContext.latestObservedStageId, "village");
    assert.equal(prepared.stageContext.planSha256, saved.sha256);
    assert.ok(prepared.stageContext.missingEvidenceIds.foreshadowing.includes("future-clue"));
    assert.ok(prepared.packet.includes(saved.sha256));
    assert.ok(prepared.packet.includes("debt"));
    assert.ok(prepared.packet.includes(committed.bodySha256));
    assert.ok(prepared.packet.includes("future-clue"));
  }
});

test("M2 Prepare retries source changes only once and reports required packet overflow", async (t) => {
  const { engine } = await fixture(t);
  await engine.writeArtifact({ projectId: "book01", artifactType: "chapter-outline", key: "1", content: "本章计划" });
  const build = engine._prepareLogicAudit.bind(engine);
  let assemblies = 0;
  engine._prepareLogicAudit = async (args) => {
    const audit = await build(args);
    assemblies += 1;
    await engine.writeArtifact({ projectId: "book01", artifactType: "story-engine", content: `中途变化-${assemblies}` });
    return audit;
  };
  await expectCode(engine.prepareChapter("book01"), "PREPARE_CONTEXT_CHANGED");
  assert.equal(assemblies, 2);
  engine._prepareLogicAudit = build;
  const clean = await engine.prepareChapter("book01");
  assert.equal(clean.stageContext, null);
  assert.equal(clean.lengthGuidance.metrics.meanHanChars, null);
  await engine.writeArtifact({ projectId: "book01", artifactType: "chapter-outline", key: "1", content: "本章必要计划".repeat(4000) });
  await expectCode(engine.prepareChapter("book01"), "PREPARE_REQUIRED_CONTEXT_BUDGET_EXCEEDED");
});

test("M2 optional stage plan works before the first commit and malformed external JSON is explicit", async (t) => {
  const { engine, projectDir } = await fixture(t);
  await engine.writeArtifact({ projectId: "book01", artifactType: "chapter-outline", key: "1", content: "本章计划" });
  const before = await engine.prepareChapter("book01");
  const plan = { schemaVersion: "novel-stage-plan-v1", stages: [{ id: "local", startChapter: 1, endChapter: 5, goal: "理解故障", foreshadowingIds: ["future"] }] };
  await engine.writeArtifact({ projectId: "book01", artifactType: "stage-plan", content: JSON.stringify(plan) });
  const current = await engine.prepareChapter("book01");
  assert.notEqual(current.contextSnapshot.key, before.contextSnapshot.key);
  assert.equal(current.stageContext.latestObservedStageId, null);
  assert.deepEqual(current.stageContext.missingEvidenceIds.foreshadowing, ["future"]);
  const ledger = await readLedger(projectDir, "foreshadowing.json");
  assert.equal(ledger.entries.length, 0);
  await fs.writeFile(path.join(projectDir, "blueprint/stage-plan.json"), "{", "utf8");
  await expectCode(engine.prepareChapter("book01"), "INVALID_STAGE_PLAN");
  await expectCode(engine.readArtifact({ projectId: "book01", artifactType: "stage-plan" }), "INVALID_STAGE_PLAN");
});

test("M2 Prepare does not cache stale config or outline in the recovery-to-fingerprint gap", async (t) => {
  const { engine } = await fixture(t);
  await engine.writeArtifact({ projectId: "book01", artifactType: "chapter-outline", key: "1", content: "OLD-OUTLINE" });
  const fingerprint = engine._prepareDependencyFingerprint.bind(engine);
  let changed = false;
  engine._prepareDependencyFingerprint = async (...args) => {
    if (!changed) {
      changed = true;
      await engine.configureProject({ projectId: "book01", expectedRevision: 1, writingContract: { minHanChars: 20, targetMinHanChars: 35, targetMaxHanChars: 45 } });
      await engine.writeArtifact({ projectId: "book01", artifactType: "chapter-outline", key: "1", content: "NEW-OUTLINE" });
    }
    return fingerprint(...args);
  };
  const prepared = await engine.prepareChapter("book01");
  assert.equal(prepared.lengthGuidance.targetMinHanChars, 35);
  assert.ok(prepared.packet.includes("NEW-OUTLINE"));
  assert.equal(prepared.packet.includes("OLD-OUTLINE"), false);
  assert.equal(prepared.contextSnapshot.assemblyAttempts, 2);
});

test("M2 three prefetched role packets share one assembly and expiry is truthful", async (t) => {
  const { engine, root } = await fixture(t);
  await engine.writeArtifact({ projectId: "book01", artifactType: "chapter-outline", key: "1", content: "调查" });
  let assemblies = 0, recoveries = 0;
  const build = engine._prepareLogicAudit.bind(engine), recover = engine.recoverProjectForRead.bind(engine);
  engine._prepareLogicAudit = async (args) => { assemblies += 1; return build(args); };
  engine.recoverProjectForRead = async (args) => { recoveries += 1; return recover(args); };
  const packets = [];
  const evidenceDir = path.join(root, "evidence", "chapter-1");
  await fs.mkdir(evidenceDir, { recursive: true });
  for (const role of ["writer", "continuity-auditor", "reader-editor"]) {
    const actualResponse = await engine.prepareChapter("book01", { role });
    const evidencePath = path.join(evidenceDir, `prepare-${role}.json`);
    await fs.writeFile(evidencePath, JSON.stringify(actualResponse), "utf8");
    const saved = JSON.parse(await fs.readFile(evidencePath, "utf8"));
    assert.equal(saved.packetSha256, sha256(saved.packet));
    packets.push(saved);
  }
  assert.deepEqual(packets.map((p) => p.contextSnapshot.reused), [false, true, true]);
  assert.equal(new Set(packets.map((p) => p.contextSnapshot.key)).size, 1);
  assert.equal(assemblies, 1);
  assert.equal(recoveries, 3);
  t.diagnostic(JSON.stringify({ packets: packets.map((p) => ({ role: p.role, chars: p.packetChars, reused: p.contextSnapshot.reused })), assemblies, recoveries }));
  engine.prepareSnapshotCache.get(packets[0].contextSnapshot.key).createdAt = 0;
  const expired = await engine.prepareChapter("book01", { role: "reader-editor" });
  assert.equal(expired.contextSnapshot.key, packets[0].contextSnapshot.key);
  assert.equal(expired.contextSnapshot.reused, false);
  assert.equal(assemblies, 2);
});

test("M2 simultaneous cold roles share in-flight assembly rather than duplicating reads", async (t) => {
  const { engine } = await fixture(t);
  await engine.writeArtifact({ projectId: "book01", artifactType: "chapter-outline", key: "1", content: "调查" });
  const build = engine._prepareLogicAudit.bind(engine);
  let assemblies = 0;
  engine._prepareLogicAudit = async (args) => {
    assemblies += 1;
    await new Promise((resolve) => setTimeout(resolve, 50));
    return build(args);
  };
  const prepared = await Promise.all(["writer", "continuity-auditor", "reader-editor"].map((role) => engine.prepareChapter("book01", { role })));
  assert.equal(assemblies, 1);
  assert.equal(new Set(prepared.map((p) => p.contextSnapshot.key)).size, 1);
  assert.equal(prepared.filter((p) => p.contextSnapshot.reused).length, 2);
});

test("M2 future and stale signatures are not represented as committed history", async (t) => {
  const { engine } = await fixture(t);
  await engine.storyLedgerUpsert({ projectId: "book01", ledgerType: "chapterSignature", entry: { chapter: 9, bodySha256: "f".repeat(64), function: "FUTURE-SENTINEL" } });
  await engine.writeArtifact({ projectId: "book01", artifactType: "chapter-outline", key: "1", content: "调查" });
  assert.equal((await engine.prepareChapter("book01")).packet.includes("FUTURE-SENTINEL"), false);
  const committed = await commitOne(engine);
  await engine.storyLedgerUpsert({ projectId: "book01", ledgerType: "chapterSignature", entry: { chapter: 1, bodySha256: committed.bodySha256, function: "OLD-SENTINEL" } });
  const revised = bodyOf(32, "改");
  await approve(engine, 1, revised, "m2-signature-revision");
  await engine.reviseChapter({ projectId: "book01", chapter: 1, content: revised, summary: "修订", expectedBodySha256: committed.bodySha256, expectedRevision: 1, requestId: "m2-signature-revision" });
  await engine.writeArtifact({ projectId: "book01", artifactType: "chapter-outline", key: "2", content: "处理后果" });
  const prepared = await engine.prepareChapter("book01");
  assert.equal(prepared.packet.includes("OLD-SENTINEL"), false);
  assert.equal(prepared.packet.includes("FUTURE-SENTINEL"), false);
  assert.equal(prepared.packetDiagnostics.signatureSourceWarnings[0].reason, "missing-or-stale-committed-meta");
});

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

async function readLedger(projectDir, name) {
  return JSON.parse(await fs.readFile(path.join(projectDir, "story", name), "utf8"));
}

async function commitSecond(engine) {
  const content = bodyOf(32, "后");
  await approve(engine, 2, content, "second");
  return engine.commitChapter({ projectId: "book01", expectedChapter: 2, title: "后来揭示", content, summary: "后来叙述先前事件。", requestId: "second-chapter" });
}

test("unplanted foreshadowing delta cannot advance or pay off before commit", async (t) => {
  const { engine, projectDir } = await fixture(t);
  const body = bodyOf(30);
  await approve(engine, 1, body);
  const before = await fs.readFile(path.join(projectDir, "state.json"), "utf8");
  const beforeLedger = await readLedger(projectDir, "foreshadowing.json");
  for (const action of ["advance", "payoff", "close"]) {
    await expectCode(engine.commitChapter({ projectId: "book01", expectedChapter: 1, title: "无埋设回收", content: body, summary: "未知线索", requestId: `invalid-${action}`, continuityDelta: { foreshadowing: [{ id: "orphan", action }] } }), "FORESHADOW_TRANSITION_INVALID");
    assert.equal((await engine.commitStatus({ projectId: "book01", requestId: `invalid-${action}` })).status, "not_found");
  }
  assert.equal(await fs.readFile(path.join(projectDir, "state.json"), "utf8"), before);
  assert.deepEqual(await readLedger(projectDir, "foreshadowing.json"), beforeLedger);
  assert.deepEqual(await fs.readdir(path.join(projectDir, "requests", "commits")), []);
  assert.equal((await engine.readChapter({ projectId: "book01", chapter: 1 })).found, false);

  const committed = await engine.commitChapter({ projectId: "book01", expectedChapter: 1, title: "短伏笔", content: body, summary: "同章埋设并回收", requestId: "short-clue", continuityDelta: { foreshadowing: [{ id: "key", action: "open" }, { id: "key", action: "payoff" }] } });
  const clue = (await readLedger(projectDir, "foreshadowing.json")).entries[0];
  assert.equal(clue.status, "paid");
  assert.equal(clue.plantedChapter, 1);
  assert.equal(clue.payoffChapter, 1);
  assert.equal(clue.plantedBodySha256, committed.bodySha256);
  const replay = await engine.commitChapter({ projectId: "book01", expectedChapter: 1, title: "短伏笔", content: body, summary: "同章埋设并回收", requestId: "short-clue", continuityDelta: { foreshadowing: [{ id: "key", action: "open" }, { id: "key", action: "payoff" }] } });
  assert.equal(replay.idempotentReplay, true);
});

test("partial foreshadowing updates retain planting provenance and terminal replay", async (t) => {
  const { engine, projectDir } = await fixture(t);
  const first = await commitOne(engine);
  const second = await commitSecond(engine);
  await engine.upsertForeshadowing({ projectId: "book01", expectedRevision: 0, entry: { id: "key", type: "prop", status: "open", plantedChapter: 1, sourceChapter: 1, bodySha256: first.bodySha256, surfaceMeaning: "沾血钥匙", payoffWindow: { start: 2, end: 3 } } });
  await engine.upsertForeshadowing({ projectId: "book01", expectedRevision: 1, entry: { id: "key", status: "advanced", sourceChapter: 2, bodySha256: second.bodySha256, notes: "血型确认" } });
  const advanced = (await readLedger(projectDir, "foreshadowing.json")).entries[0];
  assert.equal(advanced.type, "prop");
  assert.equal(advanced.plantedChapter, 1);
  assert.equal(advanced.plantedBodySha256, first.bodySha256);
  assert.equal(advanced.bodySha256, second.bodySha256);
  await engine.upsertForeshadowing({ projectId: "book01", entry: { id: "key", notes: "只修改说明" } });
  assert.equal((await readLedger(projectDir, "foreshadowing.json")).entries[0].status, "advanced");
  const paid = { id: "key", status: "paid", sourceChapter: 2, bodySha256: second.bodySha256 };
  await engine.upsertForeshadowing({ projectId: "book01", entry: paid });
  await engine.upsertForeshadowing({ projectId: "book01", entry: paid });
  const before = await readLedger(projectDir, "foreshadowing.json");
  await expectCode(engine.upsertForeshadowing({ projectId: "book01", entry: { ...paid, status: "open" } }), "FORESHADOW_TRANSITION_INVALID");
  await expectCode(engine.upsertForeshadowing({ projectId: "book01", entry: { ...paid, plantedChapter: 2 } }), "FORESHADOW_PLANT_IMMUTABLE");
  await expectCode(engine.upsertForeshadowing({ projectId: "book01", expectedRevision: 0, entry: paid }), "FORESHADOW_LEDGER_REVISION_MISMATCH");
  assert.deepEqual(await readLedger(projectDir, "foreshadowing.json"), before);
  assert.equal(before.entries[0].payoffChapter, 2);
  assert.equal((await engine.foreshadowingDue({ projectId: "book01", chapter: 3 })).due.length, 0);
});

test("planned and cancelled clues stay compatible without inventing planting evidence", async (t) => {
  const { engine, projectDir } = await fixture(t);
  await engine.upsertForeshadowing({ projectId: "book01", entry: { id: "future", status: "planned", plantedChapter: 8, type: "world" } });
  await engine.upsertForeshadowing({ projectId: "book01", entry: { id: "future", notes: "仍然是计划" } });
  const first = await commitOne(engine);
  await engine.upsertForeshadowing({ projectId: "book01", entry: { id: "future", status: "open", sourceChapter: 1, bodySha256: first.bodySha256 } });
  const opened = (await readLedger(projectDir, "foreshadowing.json")).entries[0];
  assert.equal(opened.plantedChapter, 1, "scheduled planting is not a frozen actual anchor");
  assert.equal(opened.type, "world");
  await expectCode(engine.upsertForeshadowing({ projectId: "book01", entry: { id: "late", status: "open", plantedChapter: 3, sourceChapter: 1, bodySha256: first.bodySha256 } }), "FORESHADOW_PLANT_AFTER_SOURCE");
  await engine.upsertForeshadowing({ projectId: "book01", entry: { id: "cancelled", status: "cancelled", sourceChapter: 1, bodySha256: first.bodySha256 } });
  await expectCode(engine.upsertForeshadowing({ projectId: "book01", entry: { id: "cancelled", status: "open", sourceChapter: 1, bodySha256: first.bodySha256 } }), "FORESHADOW_TRANSITION_INVALID");
  const ledger = await readLedger(projectDir, "foreshadowing.json");
  assert.equal(ledger.entries.find((entry) => entry.id === "cancelled").plantedBodySha256, null);
});

test("terminal clues freeze normalized facts while identical replay remains legal", async (t) => {
  for (const status of ["paid", "cancelled"]) await t.test(status, async (child) => {
    const { engine, projectDir } = await fixture(child);
    const first = await commitOne(engine);
    const second = await commitSecond(engine);
    if (status === "paid") await engine.upsertForeshadowing({ projectId: "book01", entry: { id: "seed", status: "open", sourceChapter: 1, bodySha256: first.bodySha256 } });
    const terminal = { id: "seed", status, sourceChapter: 2, bodySha256: second.bodySha256, notes: "original" };
    await engine.upsertForeshadowing({ projectId: "book01", entry: terminal });
    await engine.upsertForeshadowing({ projectId: "book01", entry: { ...terminal, bodySha256: second.bodySha256.toUpperCase(), notes: " original " } });
    const laterBody = bodyOf(33, "三");
    await approve(engine, 3, laterBody, "terminal-third");
    const later = await engine.commitChapter({ projectId: "book01", expectedChapter: 3, title: "无关后章", content: laterBody, summary: "不移动已有回收", requestId: "terminal-third" });
    const before = await readLedger(projectDir, "foreshadowing.json");
    const beforeState = await fs.readFile(path.join(projectDir, "state.json"), "utf8");
    for (const patch of [{ notes: "rewritten" }, { sourceChapter: 3, bodySha256: later.bodySha256 }, { bodySha256: first.bodySha256 }, { type: "information" }, { hiddenMeaning: "different fact" }, { prerequisites: ["new prerequisite"] }, { plantedBodySha256: first.bodySha256, notes: "cannot hide a rewrite in provenance repair" }]) {
      await expectCode(engine.upsertForeshadowing({ projectId: "book01", entry: { ...terminal, ...patch } }), "FORESHADOW_TERMINAL_PAYLOAD_MISMATCH");
      assert.deepEqual(await readLedger(projectDir, "foreshadowing.json"), before);
      assert.equal(await fs.readFile(path.join(projectDir, "state.json"), "utf8"), beforeState);
    }
  });
});

test("revised planting evidence blocks delta advance and payoff before the chapter transaction", async (t) => {
  const { engine, projectDir } = await fixture(t);
  const first = await commitOne(engine);
  await engine.upsertForeshadowing({ projectId: "book01", entry: { id: "seed", status: "open", sourceChapter: 1, bodySha256: first.bodySha256 } });
  await commitSecond(engine);
  const revised = bodyOf(35, "修");
  await approve(engine, 1, revised, "stale-plant");
  await engine.reviseChapter({ projectId: "book01", chapter: 1, content: revised, summary: "埋设章修订", expectedBodySha256: first.bodySha256, expectedRevision: 1, requestId: "stale-plant-revision" });
  const content = bodyOf(33, "三");
  await approve(engine, 3, content, "third");
  const beforeState = await fs.readFile(path.join(projectDir, "state.json"), "utf8");
  const beforeLedger = await readLedger(projectDir, "foreshadowing.json");
  for (const action of ["advance", "payoff"]) {
    const requestId = `stale-plant-${action}`;
    await expectCode(engine.commitChapter({ projectId: "book01", expectedChapter: 3, title: "不能使用旧证据", content, summary: "推进线索", requestId, continuityDelta: { foreshadowing: [{ id: "seed", action }] } }), "SOURCE_BODY_HASH_MISMATCH");
    assert.equal((await engine.commitStatus({ projectId: "book01", requestId })).status, "not_found");
    assert.equal(await fs.readFile(path.join(projectDir, "state.json"), "utf8"), beforeState);
    assert.deepEqual(await readLedger(projectDir, "foreshadowing.json"), beforeLedger);
    assert.equal((await engine.readChapter({ projectId: "book01", chapter: 3 })).found, false);
  }
  await engine.upsertForeshadowing({ projectId: "book01", entry: { id: "seed", bodySha256: sha256(revised), plantedBodySha256: sha256(revised) } });
  const committed = await engine.commitChapter({ projectId: "book01", expectedChapter: 3, title: "核验后的线索", content, summary: "来源已重建", requestId: "rebuilt-plant-advance", continuityDelta: { foreshadowing: [{ id: "seed", action: "advance" }] } });
  assert.equal(committed.nextChapter, 4);
  assert.deepEqual((await readLedger(projectDir, "foreshadowing.json")).entries[0].plantedEvidenceHistory, [{ chapter: 1, bodySha256: first.bodySha256 }]);
});

test("legacy plant hashes are only supplemented by explicit source-validated updates", async (t) => {
  const { engine, projectDir } = await fixture(t);
  const first = await commitOne(engine);
  const legacy = { id: "legacy", status: "open", plantedChapter: 1, sourceChapter: 1, bodySha256: first.bodySha256 };
  await fs.writeFile(path.join(projectDir, "story", "foreshadowing.json"), JSON.stringify({ revision: 1, entries: [legacy] }));
  await engine.upsertForeshadowing({ projectId: "book01", entry: { id: "legacy", notes: "legacy remains unknown" } });
  assert.equal((await readLedger(projectDir, "foreshadowing.json")).entries[0].plantedBodySha256, null);
  const before = await readLedger(projectDir, "foreshadowing.json");
  await expectCode(engine.upsertForeshadowing({ projectId: "book01", entry: { id: "legacy", plantedBodySha256: "0".repeat(64) } }), "SOURCE_BODY_HASH_MISMATCH");
  assert.deepEqual(await readLedger(projectDir, "foreshadowing.json"), before);
  await engine.upsertForeshadowing({ projectId: "book01", entry: { id: "legacy", plantedBodySha256: first.bodySha256 } });
  assert.equal((await readLedger(projectDir, "foreshadowing.json")).entries[0].plantedBodySha256, first.bodySha256);
});

test("causal mutations reject missing, unoccurred, cancelled and cyclic causes without writes", async (t) => {
  const { engine, projectDir } = await fixture(t);
  const commit = await commitOne(engine);
  const event = (eventId, extra = {}) => ({ eventId, summary: eventId, status: "occurred", chapter: 1, bodySha256: commit.bodySha256, ...extra });
  await engine.recordCausalEvent({ projectId: "book01", event: event("root") });
  await engine.recordCausalEvent({ projectId: "book01", event: event("child", { causes: ["root"] }) });
  await engine.recordCausalEvent({ projectId: "book01", event: { eventId: "future", summary: "尚未发生的原因", status: "planned", chapter: 9 } });
  const before = await readLedger(projectDir, "causal-events.json");
  await expectCode(engine.recordCausalEvent({ projectId: "book01", event: event("missing", { causes: ["absent"] }) }), "CAUSAL_REFERENCE_NOT_FOUND");
  await expectCode(engine.recordCausalEvent({ projectId: "book01", event: event("premature", { causes: ["future"] }) }), "CAUSAL_CAUSE_NOT_OCCURRED");
  await expectCode(engine.recordCausalEvent({ projectId: "book01", event: event("root", { causes: ["child"] }) }), "CAUSAL_CYCLE");
  await expectCode(engine.recordCausalEvent({ projectId: "book01", event: event("root", { status: "cancelled" }) }), "CAUSAL_CAUSE_NOT_OCCURRED");
  await expectCode(engine.recordCausalEvent({ projectId: "book01", event: { eventId: "future", summary: "改成 enables 也不能绕过", status: "planned", enables: ["child"] } }), "CAUSAL_CAUSE_NOT_OCCURRED");
  await expectCode(engine.recordCausalEvent({ projectId: "book01", event: event("self", { causes: ["self"] }) }), "CAUSAL_SELF_REFERENCE");
  await expectCode(engine.recordCausalEvent({ projectId: "book01", expectedRevision: 0, event: event("stale") }), "CAUSAL_LEDGER_REVISION_MISMATCH");
  assert.deepEqual(await readLedger(projectDir, "causal-events.json"), before);
  await engine.recordCausalEvent({ projectId: "book01", event: event("cancelled", { status: "cancelled" }) });
  await expectCode(engine.recordCausalEvent({ projectId: "book01", event: event("effect", { causes: ["cancelled"] }) }), "CAUSAL_CAUSE_NOT_OCCURRED");
});

test("internal causal batches preserve CAS and reject the entire invalid proposal without writing", async (t) => {
  const { engine, projectDir } = await fixture(t);
  const first = await commitOne(engine);
  const event = (eventId, extra = {}) => ({ eventId, summary: eventId, status: "occurred", chapter: 1, bodySha256: first.bodySha256, ...extra });
  await engine.recordCausalEvent({ projectId: "book01", event: event("a") });
  const before = await readLedger(projectDir, "causal-events.json");
  await expectCode(engine.recordCausalEvents({ projectId: "book01", expectedRevision: before.revision, events: [event("b", { causes: ["a"] }), event("a", { causes: ["b"] })] }), "CAUSAL_CYCLE");
  assert.deepEqual(await readLedger(projectDir, "causal-events.json"), before);
  await expectCode(engine.recordCausalEvents({ projectId: "book01", expectedRevision: before.revision - 1, events: [event("b")] }), "CAUSAL_LEDGER_REVISION_MISMATCH");
  assert.deepEqual(await readLedger(projectDir, "causal-events.json"), before);
  const batch = await engine.recordCausalEvents({ projectId: "book01", expectedRevision: before.revision, events: [event("b", { causes: ["a"] }), event("a", { enables: ["b"] })] });
  assert.equal(batch.revision, before.revision + 1);
  assert.equal(batch.eventCount, 2);
});

test("causes and enables share cycle semantics while planned forward edges remain legal", async (t) => {
  const { engine } = await fixture(t);
  await engine.recordCausalEvent({ projectId: "book01", event: { eventId: "a", summary: "计划 A", status: "planned", enables: ["b"] } });
  await engine.recordCausalEvent({ projectId: "book01", event: { eventId: "b", summary: "计划 B", status: "planned", causes: ["a"], enables: ["c"] } });
  await assert.rejects(engine.recordCausalEvent({ projectId: "book01", event: { eventId: "c", summary: "计划 C", status: "planned", enables: ["a"] } }), (error) => error.code === "CAUSAL_CYCLE" && error.details.cycle.length === 4);
  const integrity = await engine.projectIntegrityCheck({ projectId: "book01" });
  assert.equal(integrity.integrityPass, true);
  assert.ok(integrity.warnings.some((finding) => finding.code === "CAUSAL_REFERENCE_NOT_FOUND"));
});

test("valid later-recorded occurred causes permit nonlinear narration and verify ancestor hashes", async (t) => {
  const { engine, projectDir } = await fixture(t);
  const first = await commitOne(engine);
  const second = await commitSecond(engine);
  await engine.recordCausalEvent({ projectId: "book01", event: { eventId: "earlier-world-event", summary: "第二章回溯揭示此前证据", status: "occurred", chapter: 2, bodySha256: second.bodySha256 } });
  await engine.recordCausalEvent({ projectId: "book01", event: { eventId: "first-narration", summary: "第一章事件后来补全原因", status: "occurred", chapter: 1, bodySha256: first.bodySha256, causes: ["earlier-world-event"] } });
  assert.equal((await engine.projectIntegrityCheck({ projectId: "book01" })).integrityPass, true);
  const ledger = await readLedger(projectDir, "causal-events.json");
  ledger.events.find((event) => event.eventId === "earlier-world-event").bodySha256 = "0".repeat(64);
  await fs.writeFile(path.join(projectDir, "story", "causal-events.json"), JSON.stringify(ledger));
  await expectCode(engine.recordCausalEvent({ projectId: "book01", event: { eventId: "dependent", summary: "不能消费陈旧原因", status: "occurred", chapter: 1, bodySha256: first.bodySha256, causes: ["earlier-world-event"] } }), "SOURCE_BODY_HASH_MISMATCH");
});

test("long planned chains use iterative cycle detection", async (t) => {
  const { engine, projectDir } = await fixture(t);
  const events = Array.from({ length: 1500 }, (_, index) => ({ eventId: `e${index}`, summary: "计划", status: "planned", chapter: null, bodySha256: null, causes: index ? [`e${index - 1}`] : [], enables: [] }));
  await fs.writeFile(path.join(projectDir, "story", "causal-events.json"), JSON.stringify({ revision: 0, events }));
  await assert.rejects(engine.recordCausalEvent({ projectId: "book01", event: { eventId: "e0", summary: "闭环", status: "planned", causes: ["e1499"] } }), (error) => error.code === "CAUSAL_CYCLE" && error.details.cycle.length === 1501);
});

test("invalid causal continuity delta is rejected before its chapter transaction", async (t) => {
  const { engine } = await fixture(t);
  const body = bodyOf(30);
  await approve(engine, 1, body);
  await expectCode(engine.commitChapter({ projectId: "book01", expectedChapter: 1, title: "无来源原因", content: body, summary: "非法因果", requestId: "invalid-causal-delta", continuityDelta: { causalEvents: [{ eventId: "effect", summary: "结果", status: "occurred", causes: ["missing"] }] } }), "CAUSAL_REFERENCE_NOT_FOUND");
  assert.equal((await engine.commitStatus({ projectId: "book01", requestId: "invalid-causal-delta" })).status, "not_found");
  assert.equal((await engine.projectStatus("book01")).state.nextChapter, 1);
});

test("integrity diagnoses historical invalid graphs and clues without fabricating repairs", async (t) => {
  const { engine, projectDir } = await fixture(t);
  const first = await commitOne(engine);
  const events = [
    { eventId: "a", summary: "环 A", status: "occurred", chapter: 1, bodySha256: first.bodySha256, causes: ["b"] },
    { eventId: "b", summary: "环 B", status: "occurred", chapter: 1, bodySha256: first.bodySha256, causes: ["a"] },
    { eventId: "lost", summary: "不存在的原因", status: "occurred", chapter: 1, bodySha256: first.bodySha256, causes: ["absent"] }
  ];
  const clue = { id: "orphan", status: "paid", plantedChapter: null, payoffChapter: 1, sourceChapter: 1, bodySha256: first.bodySha256 };
  await fs.writeFile(path.join(projectDir, "story", "causal-events.json"), JSON.stringify({ revision: 1, events }));
  await fs.writeFile(path.join(projectDir, "story", "foreshadowing.json"), JSON.stringify({ revision: 1, entries: [clue] }));
  for (const result of [await engine.projectIntegrityCheck({ projectId: "book01", repair: true }), await engine.chapterIntegrityCheck({ projectId: "book01", chapter: 1 })]) {
    assert.equal(result.integrityPass, false);
    assert.ok(result.errors.some((finding) => finding.code === "CAUSAL_CYCLE"));
    assert.ok(result.errors.some((finding) => finding.code === "CAUSAL_REFERENCE_NOT_FOUND"));
    assert.ok(result.errors.some((finding) => finding.code === "FORESHADOW_PLANT_REQUIRED"));
  }
  assert.deepEqual((await readLedger(projectDir, "causal-events.json")).events, events);
  assert.deepEqual((await readLedger(projectDir, "foreshadowing.json")).entries, [clue]);
  await engine.recordCausalEvent({ projectId: "book01", event: { eventId: "independent-plan", summary: "无关正常计划", status: "planned" } });
});

test("legacy clue provenance stays unknown and new planting hashes detect revisions independently", async (t) => {
  const { engine, projectDir } = await fixture(t);
  const first = await commitOne(engine);
  const second = await commitSecond(engine);
  const legacy = { id: "legacy", status: "paid", plantedChapter: 1, sourceChapter: 2, bodySha256: second.bodySha256 };
  await fs.writeFile(path.join(projectDir, "story", "foreshadowing.json"), JSON.stringify({ revision: 1, entries: [legacy] }));
  const legacyCheck = await engine.projectIntegrityCheck({ projectId: "book01" });
  assert.equal(legacyCheck.integrityPass, true, "missing newly introduced optional provenance is not a forced migration");
  assert.ok(legacyCheck.warnings.some((finding) => finding.code === "FORESHADOW_PLANT_PROVENANCE_LEGACY"));
  assert.deepEqual((await readLedger(projectDir, "foreshadowing.json")).entries[0], legacy);
  await engine.upsertForeshadowing({ projectId: "book01", entry: { id: "new", status: "open", sourceChapter: 1, bodySha256: first.bodySha256 } });
  await expectCode(engine.upsertForeshadowing({ projectId: "book01", entry: { id: "new", status: "paid", sourceChapter: 2, bodySha256: second.bodySha256, payoffChapter: 1 } }), "FORESHADOW_PAYOFF_INVALID");
  await engine.upsertForeshadowing({ projectId: "book01", entry: { id: "new", status: "paid", sourceChapter: 2, bodySha256: second.bodySha256 } });
  const revisedBody = bodyOf(35, "修");
  await approve(engine, 1, revisedBody, "plant-revision");
  await engine.reviseChapter({ projectId: "book01", chapter: 1, content: revisedBody, summary: "原埋设章修订", expectedBodySha256: first.bodySha256, expectedRevision: 1, requestId: "plant-revision" });
  const project = await engine.projectIntegrityCheck({ projectId: "book01" });
  assert.ok(project.errors.some((finding) => finding.code === "FORESHADOW_PLANT_STALE_BINDING" && finding.id === "new"));
  const scoped = await engine.chapterIntegrityCheck({ projectId: "book01", chapter: 2 });
  assert.ok(scoped.errors.some((finding) => finding.code === "FORESHADOW_PLANT_STALE_BINDING" && finding.id === "new"));
  const clue = (await readLedger(projectDir, "foreshadowing.json")).entries.find((entry) => entry.id === "new");
  assert.equal(clue.bodySha256, second.bodySha256);
  assert.equal(clue.plantedBodySha256, first.bodySha256, "payoff evidence cannot wash away stale planting provenance");
  await expectCode(engine.upsertForeshadowing({ projectId: "book01", entry: { id: "new", plantedBodySha256: "0".repeat(64) } }), "SOURCE_BODY_HASH_MISMATCH");
  await engine.upsertForeshadowing({ projectId: "book01", entry: { id: "new", plantedBodySha256: sha256(revisedBody) } });
  const rebuilt = (await readLedger(projectDir, "foreshadowing.json")).entries.find((entry) => entry.id === "new");
  assert.deepEqual(rebuilt.plantedEvidenceHistory, [{ chapter: 1, bodySha256: first.bodySha256 }]);
  assert.equal(rebuilt.bodySha256, second.bodySha256);
  assert.equal((await engine.projectIntegrityCheck({ projectId: "book01" })).integrityPass, true, "explicit source-validated evidence rebuild can recover after revision");
});

test("project locks wait for short contention instead of failing immediately", async (t) => {
  const { engine, projectDir } = await fixture(t, { lockAcquireTimeoutMs: 1000 });
  let releaseOwner;
  let ownerEntered;
  const entered = new Promise((resolve) => { ownerEntered = resolve; });
  const release = new Promise((resolve) => { releaseOwner = resolve; });
  const owner = engine.withProjectLock(projectDir, async () => {
    ownerEntered();
    await release;
  });
  await entered;
  const contender = engine.withProjectLock(projectDir, async () => "acquired-after-wait");
  setTimeout(releaseOwner, 120);
  assert.equal(await contender, "acquired-after-wait");
  await owner;
});

test("balanced-fast prepare reuses one snapshot and enforces role packet caps", async (t) => {
  const { engine, projectDir } = await fixture(t);
  // Stress optional material; oversized required outlines now fail explicitly instead of being tail-clipped.
  await fs.writeFile(path.join(projectDir, "outlines", "chapter-0001.md"), `第一章大纲\n${"推进情节。".repeat(300)}`, "utf8");
  await fs.writeFile(path.join(projectDir, "blueprint", "story-engine.md"), "故事发动机。".repeat(1200), "utf8");
  await fs.writeFile(path.join(projectDir, "blueprint", "world-rules.md"), "世界规则。".repeat(1200), "utf8");
  await fs.writeFile(path.join(projectDir, "blueprint", "characters.md"), "人物设定。".repeat(1200), "utf8");
  await fs.writeFile(path.join(projectDir, "blueprint", "writing-rules.md"), "写作规则。".repeat(1200), "utf8");

  const writer = await engine.prepareChapter("book01", { role: "writer" });
  const continuity = await engine.prepareChapter("book01", { profile: "balanced-fast", role: "continuity-auditor" });
  const reader = await engine.prepareChapter("book01", { profile: "balanced-fast", role: "reader-editor" });
  assert.equal(writer.profile, "balanced-fast");
  assert.ok(writer.packetChars <= 16000);
  assert.ok(continuity.packetChars <= 8000);
  assert.ok(reader.packetChars <= 6000);
  assert.equal(writer.contextSnapshot.reused, false);
  assert.equal(continuity.contextSnapshot.reused, true);
  assert.equal(reader.contextSnapshot.reused, true);
  assert.equal(writer.contextSnapshot.key, continuity.contextSnapshot.key);
  assert.match(writer.packet, /通过项只写 pass/);

  engine.prepareSnapshotCache.get(writer.contextSnapshot.key).createdAt = Date.now() - 120001;
  const expired = await engine.prepareChapter("book01", { profile: "balanced-fast", role: "reader-editor" });
  assert.equal(expired.contextSnapshot.reused, false);
});

test("project locks still fail after the bounded wait expires", async (t) => {
  const { engine, projectDir } = await fixture(t, { lockAcquireTimeoutMs: 100 });
  let releaseOwner;
  let ownerEntered;
  const entered = new Promise((resolve) => { ownerEntered = resolve; });
  const release = new Promise((resolve) => { releaseOwner = resolve; });
  const owner = engine.withProjectLock(projectDir, async () => {
    ownerEntered();
    await release;
  });
  await entered;
  await assert.rejects(engine.withProjectLock(projectDir, async () => "unexpected"), (error) => {
    assert.equal(error.code, "PROJECT_WRITE_LOCKED");
    assert.ok(error.details.waitedMs >= 100);
    assert.equal(error.details.lockAcquireTimeoutMs, 100);
    return true;
  });
  releaseOwner();
  await owner;
});

test("stale same-process lock leases are safely recovered", async (t) => {
  const { engine, projectDir } = await fixture(t, { lockStaleMs: 1000, lockAcquireTimeoutMs: 500 });
  const lockPath = path.join(projectDir, ".write.lock");
  await fs.writeFile(lockPath, JSON.stringify({ pid: process.pid, hostname: os.hostname(), token: "orphaned", createdAt: new Date(Date.now() - 5000).toISOString() }), "utf8");
  const staleTime = new Date(Date.now() - 5000);
  await fs.utimes(lockPath, staleTime, staleTime);
  assert.equal(await engine.withProjectLock(projectDir, async () => "recovered"), "recovered");
  await assert.rejects(fs.access(lockPath), (error) => error.code === "ENOENT");
});

test("fresh lock files owned by a dead same-host process are recovered immediately", async (t) => {
  const { engine, projectDir } = await fixture(t, { lockStaleMs: 600000, lockAcquireTimeoutMs: 500 });
  const lockPath = path.join(projectDir, ".write.lock");
  await fs.writeFile(lockPath, JSON.stringify({ pid: 2147483647, hostname: os.hostname(), token: "dead-owner", createdAt: new Date().toISOString() }), "utf8");
  assert.equal(await engine.withProjectLock(projectDir, async () => "recovered-dead-owner"), "recovered-dead-owner");
  await assert.rejects(fs.access(lockPath), (error) => error.code === "ENOENT");
});

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

test("prepare chapter defaults to balanced-fast and keeps full profile for diagnosis", async (t) => {
  const { engine } = await fixture(t);
  await engine.writeArtifact({ projectId: "book01", artifactType: "chapter-outline", key: "1", content: "主角在井边听见铁链声。" });
  const fast = await engine.prepareChapter("book01");
  assert.equal(fast.ready, true);
  assert.equal(fast.chapter, 1);
  assert.equal(fast.profile, "balanced-fast");
  assert.equal(fast.role, "writer");
  assert.equal(fast.context, undefined);
  assert.ok(fast.packet.includes("Writer Balanced-Fast 资料包"));
  assert.ok(fast.packet.includes("17 类审计契约"));

  const continuity = await engine.prepareChapter("book01", { role: "continuity-auditor" });
  assert.ok(continuity.packet.includes("Continuity Auditor Balanced-Fast 资料包"));
  assert.ok(!continuity.packet.includes("最近章节节奏指纹"));

  const full = await engine.prepareChapter("book01", { profile: "full" });
  assert.equal(full.profile, "full");
  assert.equal(full.context.auditContract.requiredCategories.length, 17);
  assert.ok(full.context.dynamicState);
  assert.ok(full.context.memory);
  assert.ok(full.packet.includes("三级历史记忆候选"));
  assert.ok(fast.packet.length < full.packet.length);
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
