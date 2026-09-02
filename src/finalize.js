import { createHash } from "node:crypto";

const CLOSURE_EVIDENCE = Object.freeze({
  causalEvents: "story/causal-events.json",
  foreshadowing: "story/foreshadowing.json",
  promisePayoff: "story/ledgers/promises.json",
  relationshipGraph: "story/ledgers/relationships.json",
  oppositionClocks: "story/ledgers/opposition-clocks.json",
  chapterSignature: "story/ledgers/chapter-signatures.json",
  dynamicState: "story/dynamic/state.json",
  memoryIndex: "story/memory/index.json"
});

function codedError(code, message, details = undefined) {
  const error = new Error(message);
  error.code = code;
  if (details !== undefined) error.details = details;
  return error;
}

export function canonicalBodyText(body) {
  return String(body ?? "").replace(/\r\n?/g, "\n").trim();
}

export function canonicalBodySha256(body) {
  return createHash("sha256").update(canonicalBodyText(body), "utf8").digest("hex");
}

function nonEmptyArray(value, label) {
  if (value === undefined) return [];
  if (!Array.isArray(value)) throw codedError("INVALID_FINALIZE_PAYLOAD", `${label} must be an array.`);
  return value;
}

function completed(evidence, reason) {
  return { status: "completed", evidence, reason };
}

function skipped(reason) {
  return { status: "skipped", reason };
}

function hasDynamicUpdates(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  return ["characters", "knowledge", "inventory", "locations"].some((key) => Array.isArray(value[key]) && value[key].length > 0);
}

function normalizeFinalizeInput(input) {
  if (!input || typeof input !== "object" || Array.isArray(input)) throw codedError("INVALID_FINALIZE_PAYLOAD", "Finalize payload must be an object.");
  const requiredStrings = ["projectId", "title", "content", "summary", "requestId", "writerSessionId"];
  for (const key of requiredStrings) {
    if (!String(input[key] ?? "").trim()) throw codedError("INVALID_FINALIZE_PAYLOAD", `${key} is required.`, { field: key });
  }
  if (!Number.isInteger(input.expectedChapter) || input.expectedChapter < 1) throw codedError("INVALID_FINALIZE_PAYLOAD", "expectedChapter must be a positive integer.");
  if (!input.audit || typeof input.audit !== "object" || Array.isArray(input.audit)) throw codedError("INVALID_FINALIZE_PAYLOAD", "audit is required.");
  for (const key of ["continuityReview", "readerReview", "genreGate", "signature"]) {
    if (!input[key] || typeof input[key] !== "object" || Array.isArray(input[key])) throw codedError("INVALID_FINALIZE_PAYLOAD", `${key} is required.`);
  }
  const productionProfile = String(input.productionProfile ?? "strict").trim().toLowerCase();
  if (!["balanced-fast", "strict"].includes(productionProfile)) throw codedError("INVALID_FINALIZE_PAYLOAD", "productionProfile must be balanced-fast or strict.", { productionProfile });
  return {
    ...input,
    productionProfile,
    content: canonicalBodyText(input.content),
    causalEvents: nonEmptyArray(input.causalEvents, "causalEvents"),
    foreshadowingEntries: nonEmptyArray(input.foreshadowingEntries, "foreshadowingEntries"),
    storyLedgerEntries: nonEmptyArray(input.storyLedgerEntries, "storyLedgerEntries"),
    memoryRecords: nonEmptyArray(input.memoryRecords, "memoryRecords")
  };
}

async function ensureCommit(engine, input, expectedHash, steps) {
  const status = await engine.commitStatus({ projectId: input.projectId, chapter: input.expectedChapter, requestId: input.requestId });
  if (status.status === "pending") throw codedError("FINALIZE_COMMIT_PENDING", "A matching chapter commit is still pending; retry the same finalize request after reconciliation.", { status });
  if (status.status === "committed") {
    const actualHash = String(status.bodySha256 ?? status.contentSha256 ?? "").toLowerCase();
    if (actualHash !== expectedHash) throw codedError("FINALIZE_IDEMPOTENCY_BODY_MISMATCH", "The requestId is already bound to a different chapter body.", { expected: expectedHash, actual: actualHash });
    steps.push({ stage: "commit", status: "reused", requestId: input.requestId });
    return status;
  }
  if (status.status !== "not_found") throw codedError("FINALIZE_COMMIT_STATE_UNSAFE", "Chapter state cannot be safely finalized.", { status });

  const audit = await engine.recordChapterAudit({
    projectId: input.projectId,
    chapter: input.expectedChapter,
    stage: "precommit",
    decision: input.audit.decision,
    content: input.content,
    checks: input.audit.checks,
    issues: input.audit.issues ?? [],
    summary: input.audit.summary ?? ""
  });
  steps.push({ stage: "audit", status: "recorded", auditId: audit.auditId });

  const quality = await engine.recordChapterQuality({
    projectId: input.projectId,
    chapter: input.expectedChapter,
    content: input.content,
    writerSessionId: input.writerSessionId,
    continuityReview: input.continuityReview,
    readerReview: input.readerReview,
    genreGate: input.genreGate,
    signature: input.signature,
    summary: input.qualitySummary ?? ""
  });
  steps.push({ stage: "quality", status: "recorded", qualityId: quality.qualityId });

  const commit = await engine.commitChapter({
    projectId: input.projectId,
    expectedChapter: input.expectedChapter,
    title: input.title,
    content: input.content,
    summary: input.summary,
    continuityDelta: input.continuityDelta ?? {},
    requestId: input.requestId
  });
  steps.push({ stage: "commit", status: "committed", transactionId: commit.transactionId });
  return commit;
}

export async function finalizeChapterRecoverable(engine, rawInput) {
  if (!engine) throw new TypeError("NovelEngine instance is required.");
  const input = normalizeFinalizeInput(rawInput);
  const expectedHash = canonicalBodySha256(input.content);
  const steps = [];
  const commit = await ensureCommit(engine, input, expectedHash, steps);
  const bodySha256 = String(commit.bodySha256 ?? commit.contentSha256 ?? expectedHash).toLowerCase();
  const chapter = input.expectedChapter;
  const operations = {};

  for (const raw of input.causalEvents) {
    const result = await engine.recordCausalEvent({ projectId: input.projectId, event: { ...raw, chapter, bodySha256 } });
    steps.push({ stage: "causalEvents", id: result.eventId, status: "upserted" });
  }
  operations.causalEvents = input.causalEvents.length
    ? completed(CLOSURE_EVIDENCE.causalEvents, `${input.causalEvents.length} causal event(s) upserted by recoverable finalizer.`)
    : skipped("No causal-event change was declared for this chapter.");

  for (const raw of input.foreshadowingEntries) {
    const result = await engine.upsertForeshadowing({ projectId: input.projectId, entry: { ...raw, sourceChapter: chapter, bodySha256 } });
    steps.push({ stage: "foreshadowing", id: result.id, status: "upserted" });
  }
  operations.foreshadowing = input.foreshadowingEntries.length
    ? completed(CLOSURE_EVIDENCE.foreshadowing, `${input.foreshadowingEntries.length} foreshadowing entry or entries upserted.`)
    : skipped("No foreshadowing change was declared for this chapter.");

  const ledgerCounts = { promise: 0, relationship: 0, oppositionClock: 0, chapterSignature: 0 };
  const ledgerEntries = [...input.storyLedgerEntries];
  if (!ledgerEntries.some((item) => item?.ledgerType === "chapterSignature")) {
    ledgerEntries.push({
      ledgerType: "chapterSignature",
      entry: {
        ...input.signature,
        chapter: input.signature.chapter ?? input.signature.chapterNo ?? chapter,
        bodySha256
      }
    });
  }
  for (const item of ledgerEntries) {
    if (!item || typeof item !== "object" || Array.isArray(item) || !item.ledgerType || !item.entry) throw codedError("INVALID_FINALIZE_PAYLOAD", "Each storyLedgerEntries item requires ledgerType and entry.");
    const result = await engine.storyLedgerUpsert({
      projectId: input.projectId,
      ledgerType: item.ledgerType,
      entry: { ...item.entry, sourceChapter: chapter, bodySha256 }
    });
    if (Object.hasOwn(ledgerCounts, item.ledgerType)) ledgerCounts[item.ledgerType] += 1;
    steps.push({ stage: "storyLedger", ledgerType: item.ledgerType, id: result.id, status: "upserted" });
  }
  operations.promisePayoff = ledgerCounts.promise
    ? completed(CLOSURE_EVIDENCE.promisePayoff, `${ledgerCounts.promise} promise entry or entries upserted.`)
    : skipped("No Promise/Payoff change was declared for this chapter.");
  operations.relationshipGraph = ledgerCounts.relationship
    ? completed(CLOSURE_EVIDENCE.relationshipGraph, `${ledgerCounts.relationship} relationship entry or entries upserted.`)
    : skipped("No relationship change was declared for this chapter.");
  operations.oppositionClocks = ledgerCounts.oppositionClock
    ? completed(CLOSURE_EVIDENCE.oppositionClocks, `${ledgerCounts.oppositionClock} opposition-clock entry or entries upserted.`)
    : skipped("No opposition-clock change was declared for this chapter.");
  operations.chapterSignature = ledgerCounts.chapterSignature
    ? completed(CLOSURE_EVIDENCE.chapterSignature, `${ledgerCounts.chapterSignature} chapter-signature entry or entries upserted.`)
    : skipped("No durable chapter-signature ledger update was declared.");

  if (hasDynamicUpdates(input.dynamicState)) {
    const result = await engine.dynamicStateUpdate({
      projectId: input.projectId,
      chapter,
      bodySha256,
      sourceRef: input.dynamicState.sourceRef ?? `chapter:${chapter}`,
      characters: input.dynamicState.characters ?? [],
      knowledge: input.dynamicState.knowledge ?? [],
      inventory: input.dynamicState.inventory ?? [],
      locations: input.dynamicState.locations ?? []
    });
    steps.push({ stage: "dynamicState", status: "updated", counts: result.updatedCounts });
    operations.dynamicState = completed(CLOSURE_EVIDENCE.dynamicState, "Dynamic state updates were durably recorded.");
  } else {
    operations.dynamicState = skipped("No dynamic-state change was declared for this chapter.");
  }

  if (input.memoryRecords.length) {
    const records = input.memoryRecords.map((record) => ({ ...record, chapter, bodySha256, sourceSha256: bodySha256 }));
    const result = await engine.memoryRecord({ projectId: input.projectId, records });
    steps.push({ stage: "memoryIndex", status: "updated", recorded: result.recorded });
    operations.memoryIndex = completed(CLOSURE_EVIDENCE.memoryIndex, `${result.recorded} memory record(s) upserted.`);
  } else {
    operations.memoryIndex = skipped("No memory record was declared for this chapter.");
  }

  const closure = await engine.recordChapterClosure({ projectId: input.projectId, chapter, bodySha256, operations, note: input.closureNote ?? "Completed by novel_finalize_chapter." });
  steps.push({ stage: "closure", status: closure.status });
  if (!closure.closurePass) throw codedError("FINALIZE_CLOSURE_INCOMPLETE", "Chapter closure did not complete.", { closure });

  const periodicFullCheck = chapter === 1 || chapter % 5 === 0;
  const useFullIntegrity = input.productionProfile === "strict" || periodicFullCheck || typeof engine.chapterIntegrityCheck !== "function";
  const integrity = useFullIntegrity
    ? await engine.projectIntegrityCheck({ projectId: input.projectId, repair: false })
    : await engine.chapterIntegrityCheck({ projectId: input.projectId, chapter });
  steps.push({ stage: "integrity", status: integrity.status });
  if (!integrity.integrityPass) throw codedError("FINALIZE_INTEGRITY_FAILED", "Project integrity check failed after chapter finalization.", { integrity });

  return {
    projectId: input.projectId,
    chapter,
    requestId: input.requestId,
    bodySha256,
    nextChapter: commit.nextChapter ?? chapter + 1,
    finalizeMode: "recoverable-idempotent",
    productionProfile: input.productionProfile,
    commit,
    closure: { status: closure.status, path: closure.path },
    integrity: { status: integrity.status, scope: integrity.scope ?? "project", checkedChapters: integrity.checkedChapters },
    steps
  };
}

export { CLOSURE_EVIDENCE };
