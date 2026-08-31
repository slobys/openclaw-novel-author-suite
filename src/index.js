import { Type } from "typebox";
import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";
import { LOGIC_AUDIT_CATEGORIES, NovelEngine } from "./engine.js";

const configSchema = Type.Object({
  projectsRoot: Type.Optional(Type.String({ minLength: 1, description: "Absolute persistent directory for novel projects; defaults to ~/.openclaw/data/novels." })),
  importRoots: Type.Optional(Type.Array(Type.String({ minLength: 1 }), { description: "Allowed reference-import roots; defaults to ~/.openclaw/data/novel-imports." })),
  maxReferenceBytes: Type.Optional(Type.Integer({ minimum: 1024, maximum: 104857600, default: 20971520 })),
  referenceChunkChars: Type.Optional(Type.Integer({ minimum: 2000, maximum: 40000, default: 12000 })),
  minChapterChars: Type.Optional(Type.Integer({ minimum: 100, maximum: 10000, default: 800, description: "Legacy raw string-length safety check." })),
  minChapterHanChars: Type.Optional(Type.Integer({ minimum: 0, maximum: 20000, default: 2600, description: "Default project hard minimum Han-character count; each project may override it." })),
  targetChapterHanChars: Type.Optional(Type.Integer({ minimum: 0, maximum: 30000, default: 3000 })),
  targetChapterHanCharsMax: Type.Optional(Type.Integer({ minimum: 0, maximum: 50000, default: 3400 })),
  requireChapterAudit: Type.Optional(Type.Boolean({ default: true })),
  requireCompleteAuditChecks: Type.Optional(Type.Boolean({ default: true })),
  requireQualityGate: Type.Optional(Type.Boolean({ default: true })),
  requireRevisionAudit: Type.Optional(Type.Boolean({ default: true })),
  requireRevisionCas: Type.Optional(Type.Boolean({ default: true })),
  requireClosureReceipt: Type.Optional(Type.Boolean({ default: true })),
  rejectEmbeddedChapterHeading: Type.Optional(Type.Boolean({ default: true })),
  lockStaleMs: Type.Optional(Type.Integer({ minimum: 1000, maximum: 86400000, default: 600000 })),
  maxArtifactChars: Type.Optional(Type.Integer({ minimum: 1000, maximum: 5000000, default: 500000 })),
  maxContinuityDeltaChars: Type.Optional(Type.Integer({ minimum: 1000, maximum: 2000000, default: 200000 })),
  maxMemoryRecords: Type.Optional(Type.Integer({ minimum: 100, maximum: 100000, default: 10000 })),
  maxLedgerEntries: Type.Optional(Type.Integer({ minimum: 100, maximum: 100000, default: 10000 })),
  transactionRetention: Type.Optional(Type.Integer({ minimum: 10, maximum: 10000, default: 200 }))
}, { additionalProperties: false });

const ProjectId = Type.String({ minLength: 2, maxLength: 64, pattern: "^[A-Za-z0-9][A-Za-z0-9_-]+$" });
const Chapter = Type.Integer({ minimum: 1, maximum: 999999 });
const Sha256 = Type.String({ pattern: "^[a-fA-F0-9]{64}$" });
const Revision = Type.Integer({ minimum: 0, maximum: 2147483647 });
const AuditCategory = Type.Union(LOGIC_AUDIT_CATEGORIES.map((item) => Type.Literal(item)));
const LedgerType = Type.Union(["promise", "relationship", "oppositionClock", "chapterSignature", "arcAudit", "outlineDrift"].map((item) => Type.Literal(item)));
const MemoryTier = Type.Union([Type.Literal("short"), Type.Literal("mid"), Type.Literal("long")]);
const ClosureOperationStatus = Type.Union([Type.Literal("pending"), Type.Literal("completed"), Type.Literal("skipped"), Type.Literal("failed")]);
const ClosureOperation = Type.Union([
  ClosureOperationStatus,
  Type.Object({
    status: ClosureOperationStatus,
    evidence: Type.Optional(Type.String({ maxLength: 1000 })),
    reason: Type.Optional(Type.String({ maxLength: 5000 })),
    note: Type.Optional(Type.String({ maxLength: 5000 }))
  }, { additionalProperties: false })
]);

const ArtifactType = Type.Union([
  "structure-fingerprint", "reference-synthesis", "creative-brief", "story-engine", "novelty-report",
  "premise", "world", "world-rules", "characters", "master-outline", "writing-rules", "genre-profile",
  "volume-outline", "chapter-outline"
].map((item) => Type.Literal(item)));

const IdeaScores = Type.Object({
  originality: Type.Number({ minimum: 0, maximum: 100 }),
  tension: Type.Number({ minimum: 0, maximum: 100 }),
  agency: Type.Number({ minimum: 0, maximum: 100 }),
  sustainability: Type.Number({ minimum: 0, maximum: 100 }),
  emotion: Type.Number({ minimum: 0, maximum: 100 }),
  genrePromise: Type.Number({ minimum: 0, maximum: 100 })
});

const IdeaCandidate = Type.Object({
  id: Type.String({ minLength: 1, maxLength: 64, pattern: "^[A-Za-z0-9][A-Za-z0-9_-]*$" }),
  title: Type.String({ minLength: 1, maxLength: 200 }),
  hook: Type.String({ minLength: 1, maxLength: 2000 }),
  premise: Type.String({ minLength: 1, maxLength: 5000 }),
  storyEngine: Type.String({ minLength: 1, maxLength: 5000 }),
  protagonist: Type.Optional(Type.String({ maxLength: 2000 })),
  coreConflict: Type.Optional(Type.String({ maxLength: 3000 })),
  worldMechanism: Type.Optional(Type.String({ maxLength: 3000 })),
  cost: Type.Optional(Type.String({ maxLength: 3000 })),
  endingQuestion: Type.Optional(Type.String({ maxLength: 3000 })),
  referenceDistance: Type.Optional(Type.String({ maxLength: 3000 })),
  strengths: Type.Optional(Type.Array(Type.String({ maxLength: 1000 }), { maxItems: 20 })),
  risks: Type.Optional(Type.Array(Type.String({ maxLength: 1000 }), { maxItems: 20 })),
  scores: Type.Optional(IdeaScores),
  status: Type.Optional(Type.Union(["draft", "shortlisted", "selected", "rejected"].map((item) => Type.Literal(item))))
});

const CausalEvent = Type.Object({
  eventId: Type.String({ minLength: 1, maxLength: 64, pattern: "^[A-Za-z0-9][A-Za-z0-9_-]*$" }),
  summary: Type.String({ minLength: 1, maxLength: 3000 }),
  chapter: Type.Optional(Chapter),
  bodySha256: Type.Optional(Sha256),
  status: Type.Optional(Type.Union(["planned", "occurred", "cancelled"].map((item) => Type.Literal(item)))),
  preconditions: Type.Optional(Type.Array(Type.String({ maxLength: 1000 }), { maxItems: 50 })),
  causes: Type.Optional(Type.Array(Type.String({ maxLength: 64 }), { maxItems: 50 })),
  enables: Type.Optional(Type.Array(Type.String({ maxLength: 64 }), { maxItems: 50 })),
  actorGoals: Type.Optional(Type.Array(Type.String({ maxLength: 1000 }), { maxItems: 30 })),
  trigger: Type.Optional(Type.String({ maxLength: 2000 })),
  action: Type.Optional(Type.String({ maxLength: 3000 })),
  cost: Type.Optional(Type.String({ maxLength: 3000 })),
  outcome: Type.Optional(Type.String({ maxLength: 3000 })),
  stateChanges: Type.Optional(Type.Array(Type.String({ maxLength: 1000 }), { maxItems: 50 }))
});

const ForeshadowingEntry = Type.Object({
  id: Type.String({ minLength: 1, maxLength: 64, pattern: "^[A-Za-z0-9][A-Za-z0-9_-]*$" }),
  type: Type.Optional(Type.Union(["plot", "character", "world", "theme", "prop", "information"].map((item) => Type.Literal(item)))),
  status: Type.Optional(Type.Union(["planned", "open", "advanced", "paid", "cancelled"].map((item) => Type.Literal(item)))),
  surfaceMeaning: Type.Optional(Type.String({ maxLength: 3000 })),
  hiddenMeaning: Type.Optional(Type.String({ maxLength: 3000 })),
  plantedChapter: Type.Optional(Chapter),
  sourceChapter: Type.Optional(Chapter),
  bodySha256: Type.Optional(Sha256),
  reinforceChapters: Type.Optional(Type.Array(Chapter, { maxItems: 100 })),
  payoffWindow: Type.Optional(Type.Object({ start: Chapter, end: Chapter })),
  readerAwareness: Type.Optional(Type.String({ maxLength: 1000 })),
  characterAwareness: Type.Optional(Type.Unknown()),
  prerequisites: Type.Optional(Type.Array(Type.String({ maxLength: 1000 }), { maxItems: 50 })),
  payoffPlan: Type.Optional(Type.String({ maxLength: 5000 })),
  notes: Type.Optional(Type.String({ maxLength: 5000 }))
});

const AuditIssue = Type.Object({
  category: AuditCategory,
  severity: Type.Union(["note", "warning", "error", "block", "fatal"].map((item) => Type.Literal(item))),
  evidence: Type.Optional(Type.String({ maxLength: 5000 })),
  repair: Type.Optional(Type.String({ maxLength: 5000 }))
});

const ReviewIssue = Type.Object({
  category: Type.Optional(Type.String({ maxLength: 200 })),
  severity: Type.Union(["note", "warning", "error", "block", "fatal"].map((item) => Type.Literal(item))),
  evidence: Type.Optional(Type.String({ maxLength: 5000 })),
  repair: Type.Optional(Type.String({ maxLength: 5000 }))
});

const IndependentReview = Type.Object({
  reviewerRole: Type.Union([Type.Literal("continuity-auditor"), Type.Literal("reader-editor")]),
  reviewerSessionId: Type.String({ minLength: 1, maxLength: 500 }),
  bodySha256: Sha256,
  conclusion: Type.Union([Type.Literal("pass"), Type.Literal("revise"), Type.Literal("block")]),
  checks: Type.Unknown(),
  issues: Type.Array(ReviewIssue, { maxItems: 100 }),
  summary: Type.Optional(Type.String({ maxLength: 10000 }))
});

const WritingContract = Type.Object({
  minHanChars: Type.Optional(Type.Integer({ minimum: 0, maximum: 20000 })),
  targetMinHanChars: Type.Optional(Type.Integer({ minimum: 0, maximum: 30000 })),
  targetMaxHanChars: Type.Optional(Type.Integer({ minimum: 0, maximum: 50000 }))
}, { additionalProperties: false });

const EnforcementConfig = Type.Object({
  lengthFromChapter: Type.Optional(Chapter),
  auditFromChapter: Type.Optional(Chapter),
  qualityFromChapter: Type.Optional(Chapter),
  closureFromChapter: Type.Optional(Chapter),
  metadataFromChapter: Type.Optional(Chapter)
}, { additionalProperties: false });

const QualityConfig = Type.Object({
  requireChapterAudit: Type.Optional(Type.Boolean()),
  requireCompleteAuditChecks: Type.Optional(Type.Boolean()),
  requiredAuditCategories: Type.Optional(Type.Array(AuditCategory, { minItems: 1, maxItems: LOGIC_AUDIT_CATEGORIES.length })),
  requireQualityGate: Type.Optional(Type.Boolean()),
  requireRevisionAudit: Type.Optional(Type.Boolean()),
  requireRevisionCas: Type.Optional(Type.Boolean()),
  requireClosureReceipt: Type.Optional(Type.Boolean())
}, { additionalProperties: false });

function toolResult(value) {
  return { content: [{ type: "text", text: JSON.stringify(value, null, 2) }], details: value };
}

function register(api, definition) {
  const { run, ...toolDefinition } = definition;
  api.registerTool({
    ...toolDefinition,
    async execute(_toolCallId, params) {
      return toolResult(await run(params));
    }
  }, { optional: true });
}

export default definePluginEntry({
  id: "novel-engine",
  name: "Novel Engine",
  description: "V5 persistent novel engine with server-side writing contracts, audit/quality gates, recoverable transactions, story ledgers and long-form memory.",
  configSchema,
  register(api) {
    const engine = new NovelEngine(api.pluginConfig ?? {});
    const add = (definition) => register(api, definition);

    add({ name: "novel_project_create", label: "Create Novel Project", description: "Create a persistent original-novel project without overwriting an existing project.", parameters: Type.Object({ projectId: ProjectId, title: Type.String({ minLength: 1, maxLength: 200 }), genre: Type.Optional(Type.String({ maxLength: 200 })), premise: Type.Optional(Type.String({ maxLength: 4000 })), referenceTitle: Type.Optional(Type.String({ maxLength: 500 })) }), run: (params) => engine.createProject(params) });
    add({ name: "novel_project_list", label: "List Novel Projects", description: "Authoritative persistent project inventory.", parameters: Type.Object({}, { additionalProperties: false }), run: () => engine.listProjects() });
    add({ name: "novel_project_status", label: "Novel Project Status", description: "Inspect project progress, server gates, ledgers and runtime health.", parameters: Type.Object({ projectId: ProjectId }), run: ({ projectId }) => engine.projectStatus(projectId) });
    add({ name: "novel_project_configure", label: "Configure Novel Project", description: "CAS-update the project writing contract, quality requirements and genre profile.", parameters: Type.Object({ projectId: ProjectId, expectedRevision: Type.Optional(Revision), writingContract: Type.Optional(WritingContract), quality: Type.Optional(QualityConfig), enforcement: Type.Optional(EnforcementConfig), genreProfile: Type.Optional(Type.Unknown()) }), run: (params) => engine.configureProject(params) });
    add({ name: "novel_project_config_read", label: "Read Novel Project Configuration", description: "Read the resolved per-project writing and quality contract.", parameters: Type.Object({ projectId: ProjectId }), run: ({ projectId }) => engine.projectConfigStatus(projectId) });

    add({ name: "novel_reference_import", label: "Import Reference Novel", description: "Import and split one UTF-8 TXT reference from an allowlisted operator directory.", parameters: Type.Object({ projectId: ProjectId, sourcePath: Type.String({ minLength: 1 }), title: Type.Optional(Type.String({ maxLength: 500 })) }), run: (params) => engine.importReference(params) });
    add({ name: "novel_reference_next_batch", label: "Next Reference Batch", description: "Return a bounded batch of unanalyzed reference chunks for abstract analysis only.", parameters: Type.Object({ projectId: ProjectId, limit: Type.Optional(Type.Integer({ minimum: 1, maximum: 10 })), maxTotalChars: Type.Optional(Type.Integer({ minimum: 4000, maximum: 80000 })) }), run: (params) => engine.nextReferenceBatch(params) });
    add({ name: "novel_reference_analysis_batch", label: "Read Reference Analysis Batch", description: "Read saved abstract reference chapter cards for synthesis.", parameters: Type.Object({ projectId: ProjectId, start: Type.Optional(Type.Integer({ minimum: 1 })), limit: Type.Optional(Type.Integer({ minimum: 1, maximum: 50 })) }), run: (params) => engine.referenceAnalysisBatch(params) });
    add({ name: "novel_reference_record_batch", label: "Record Reference Batch", description: "Persist 1-10 structured abstract reference analyses.", parameters: Type.Object({ projectId: ProjectId, analyses: Type.Array(Type.Object({ chunkId: Type.String({ pattern: "^chunk-[0-9]{5}$" }), analysis: Type.Unknown() }), { minItems: 1, maxItems: 10 }) }), run: (params) => engine.recordReferenceBatch(params) });

    add({ name: "novel_artifact_write", label: "Write Novel Artifact", description: "Save a controlled planning artifact with optional SHA-256 CAS.", parameters: Type.Object({ projectId: ProjectId, artifactType: ArtifactType, key: Type.Optional(Type.String({ maxLength: 64 })), content: Type.String({ minLength: 1 }), expectedSha256: Type.Optional(Sha256) }), run: (params) => engine.writeArtifact(params) });
    add({ name: "novel_artifact_read", label: "Read Novel Artifact", description: "Read a controlled planning artifact and its hash.", parameters: Type.Object({ projectId: ProjectId, artifactType: ArtifactType, key: Type.Optional(Type.String({ maxLength: 64 })) }), run: (params) => engine.readArtifact(params) });
    add({ name: "novel_idea_bank_write", label: "Write Novel Idea Bank", description: "Persist and merge deliberately diverse original story candidates.", parameters: Type.Object({ projectId: ProjectId, candidates: Type.Array(IdeaCandidate, { minItems: 1, maxItems: 30 }), selectedId: Type.Optional(Type.String({ minLength: 1, maxLength: 64, pattern: "^[A-Za-z0-9][A-Za-z0-9_-]*$" })), expectedRevision: Type.Optional(Revision) }), run: (params) => engine.writeIdeaBank(params) });
    add({ name: "novel_creativity_review", label: "Review Novel Idea", description: "Score and shortlist, reject or select a story candidate.", parameters: Type.Object({ projectId: ProjectId, candidateId: Type.String({ minLength: 1, maxLength: 64, pattern: "^[A-Za-z0-9][A-Za-z0-9_-]*$" }), scores: IdeaScores, strengths: Type.Optional(Type.Array(Type.String({ maxLength: 1000 }), { maxItems: 20 })), risks: Type.Optional(Type.Array(Type.String({ maxLength: 1000 }), { maxItems: 20 })), rationale: Type.Optional(Type.String({ maxLength: 5000 })), decision: Type.Union([Type.Literal("shortlist"), Type.Literal("reject"), Type.Literal("select")]) }), run: (params) => engine.reviewCreativity(params) });

    add({ name: "novel_causal_event_record", label: "Record Causal Story Event", description: "CAS-upsert a causal story event.", parameters: Type.Object({ projectId: ProjectId, event: CausalEvent, expectedRevision: Type.Optional(Revision) }), run: (params) => engine.recordCausalEvent(params) });
    add({ name: "novel_foreshadowing_upsert", label: "Upsert Foreshadowing", description: "CAS-upsert a full foreshadowing lifecycle entry.", parameters: Type.Object({ projectId: ProjectId, entry: ForeshadowingEntry, expectedRevision: Type.Optional(Revision) }), run: (params) => engine.upsertForeshadowing(params) });
    add({ name: "novel_foreshadowing_due", label: "List Due Foreshadowing", description: "List due, overdue and upcoming foreshadowing.", parameters: Type.Object({ projectId: ProjectId, chapter: Type.Optional(Chapter), horizon: Type.Optional(Type.Integer({ minimum: 0, maximum: 100 })) }), run: (params) => engine.foreshadowingDue(params) });
    add({ name: "novel_story_ledger_upsert", label: "Upsert Story Ledger Entry", description: "CAS-upsert Promise, relationship, opposition-clock, chapter-signature, arc-audit or outline-drift state.", parameters: Type.Object({ projectId: ProjectId, ledgerType: LedgerType, entry: Type.Unknown(), expectedRevision: Type.Optional(Revision) }), run: (params) => engine.storyLedgerUpsert(params) });
    add({ name: "novel_story_ledger_query", label: "Query Story Ledger", description: "Query durable story ledgers by IDs, status or chapter horizon.", parameters: Type.Object({ projectId: ProjectId, ledgerType: LedgerType, ids: Type.Optional(Type.Array(Type.String({ maxLength: 200 }), { maxItems: 200 })), status: Type.Optional(Type.String({ maxLength: 100 })), chapter: Type.Optional(Chapter), horizon: Type.Optional(Type.Integer({ minimum: 0, maximum: 100 })), limit: Type.Optional(Type.Integer({ minimum: 1, maximum: 200 })) }), run: (params) => engine.storyLedgerQuery(params) });

    add({ name: "novel_dynamic_state_update", label: "Update Dynamic Story State", description: "Hash-bind and CAS-update character, knowledge, inventory and location state from a committed chapter.", parameters: Type.Object({ projectId: ProjectId, chapter: Chapter, bodySha256: Sha256, sourceRef: Type.Optional(Type.String({ maxLength: 1000 })), characters: Type.Optional(Type.Array(Type.Unknown(), { maxItems: 500 })), knowledge: Type.Optional(Type.Array(Type.Unknown(), { maxItems: 500 })), inventory: Type.Optional(Type.Array(Type.Unknown(), { maxItems: 500 })), locations: Type.Optional(Type.Array(Type.Unknown(), { maxItems: 500 })), expectedRevision: Type.Optional(Revision) }), run: (params) => engine.dynamicStateUpdate(params) });
    add({ name: "novel_dynamic_state_context", label: "Read Dynamic Story State", description: "Read all or selected character, knowledge, inventory and location state.", parameters: Type.Object({ projectId: ProjectId, characterIds: Type.Optional(Type.Array(Type.String({ maxLength: 200 }), { maxItems: 500 })), knowledgeKeys: Type.Optional(Type.Array(Type.String({ maxLength: 200 }), { maxItems: 500 })), itemIds: Type.Optional(Type.Array(Type.String({ maxLength: 200 }), { maxItems: 500 })), locationIds: Type.Optional(Type.Array(Type.String({ maxLength: 200 }), { maxItems: 500 })) }), run: (params) => engine.dynamicStateContext(params) });
    add({ name: "novel_memory_record", label: "Record Long-Form Memory", description: "CAS-record short-, mid- or long-tier memories, optionally hash-bound to committed chapters.", parameters: Type.Object({ projectId: ProjectId, records: Type.Array(Type.Object({ id: Type.String({ minLength: 1, maxLength: 200 }), tier: MemoryTier, text: Type.String({ minLength: 1, maxLength: 20000 }), chapter: Type.Optional(Chapter), tags: Type.Optional(Type.Array(Type.String({ maxLength: 200 }), { maxItems: 100 })), sourceRef: Type.Optional(Type.String({ maxLength: 1000 })), sourceSha256: Type.Optional(Sha256), bodySha256: Type.Optional(Sha256), importance: Type.Optional(Type.Number({ minimum: 0, maximum: 10 })) }, { additionalProperties: true }), { minItems: 1, maxItems: 50 }), expectedRevision: Type.Optional(Revision) }), run: (params) => engine.memoryRecord(params) });
    add({ name: "novel_memory_search", label: "Search Long-Form Memory", description: "Search tiered memories using Chinese n-grams and TF-IDF ranking.", parameters: Type.Object({ projectId: ProjectId, query: Type.String({ minLength: 1, maxLength: 20000 }), tiers: Type.Optional(Type.Array(MemoryTier, { maxItems: 3 })), tags: Type.Optional(Type.Array(Type.String({ maxLength: 200 }), { maxItems: 100 })), chapterBefore: Type.Optional(Chapter), topK: Type.Optional(Type.Integer({ minimum: 1, maximum: 50 })) }), run: (params) => engine.memorySearch(params) });

    add({ name: "novel_logic_audit_prepare", label: "Prepare Chapter Logic Audit", description: "Build a 17-category logic audit packet with state, memory and story-ledger context.", parameters: Type.Object({ projectId: ProjectId, chapter: Type.Optional(Chapter) }), run: (params) => engine.prepareLogicAudit(params) });
    add({ name: "novel_chapter_audit_record", label: "Record Chapter Audit", description: "Server-recount, hash-bind and persist a complete 17-category chapter audit.", parameters: Type.Object({ projectId: ProjectId, chapter: Chapter, stage: Type.Optional(Type.Union([Type.Literal("precommit"), Type.Literal("postcommit")])), decision: Type.Union([Type.Literal("pass"), Type.Literal("revise"), Type.Literal("block")]), content: Type.Optional(Type.String({ minLength: 1 })), checks: Type.Optional(Type.Unknown()), issues: Type.Optional(Type.Array(AuditIssue, { maxItems: 100 })), summary: Type.Optional(Type.String({ maxLength: 5000 })) }), run: (params) => engine.recordChapterAudit(params) });
    add({ name: "novel_chapter_quality_record", label: "Record Independent Chapter Quality", description: "Hash-bind independent Continuity Auditor and Reader Editor receipts plus genre/signature gates.", parameters: Type.Object({ projectId: ProjectId, chapter: Chapter, content: Type.String({ minLength: 1 }), writerSessionId: Type.String({ minLength: 1, maxLength: 500 }), continuityReview: IndependentReview, readerReview: IndependentReview, genreGate: Type.Unknown(), signature: Type.Unknown(), summary: Type.Optional(Type.String({ maxLength: 10000 })) }), run: (params) => engine.recordChapterQuality(params) });

    add({ name: "novel_prepare_chapter", label: "Prepare Next Chapter", description: "Build the next writing packet from plans, state, recent chapters, tiered memory and due ledgers; raw reference prose is excluded.", parameters: Type.Object({ projectId: ProjectId }), run: ({ projectId }) => engine.prepareChapter(projectId) });
    add({ name: "novel_commit_chapter", label: "Commit Novel Chapter", description: "Crash-recoverably commit exactly the expected next chapter after project length, full audit, body-hash and independent quality gates pass.", parameters: Type.Object({ projectId: ProjectId, expectedChapter: Chapter, title: Type.String({ minLength: 1, maxLength: 200 }), content: Type.String({ minLength: 1 }), summary: Type.String({ minLength: 1, maxLength: 10000 }), continuityDelta: Type.Optional(Type.Unknown()), requestId: Type.String({ minLength: 1, maxLength: 500 }) }), run: (params) => engine.commitChapter(params) });
    add({ name: "novel_commit_status", label: "Reconcile Chapter Commit", description: "Resolve an uncertain commit result by requestId or chapter after recovering any prepared transaction.", parameters: Type.Object({ projectId: ProjectId, chapter: Type.Optional(Chapter), requestId: Type.Optional(Type.String({ maxLength: 500 })) }), run: (params) => engine.commitStatus(params) });
    add({ name: "novel_read_chapter", label: "Read Novel Chapter", description: "Read a committed chapter with parsed body, hash, revision, summary, delta and closure.", parameters: Type.Object({ projectId: ProjectId, chapter: Chapter }), run: (params) => engine.readChapter(params) });
    add({ name: "novel_revise_chapter", label: "Revise Novel Chapter", description: "CAS-revise an existing chapter through the current project length, audit and quality gates while preserving the prior version.", parameters: Type.Object({ projectId: ProjectId, chapter: Chapter, title: Type.Optional(Type.String({ maxLength: 200 })), content: Type.String({ minLength: 1 }), summary: Type.Optional(Type.String({ maxLength: 10000 })), continuityDelta: Type.Optional(Type.Unknown()), changeNote: Type.Optional(Type.String({ maxLength: 5000 })), expectedBodySha256: Type.Optional(Sha256), expectedRevision: Type.Optional(Revision), requestId: Type.String({ minLength: 1, maxLength: 500 }) }), run: (params) => engine.reviseChapter(params) });

    add({ name: "novel_chapter_closure_record", label: "Record Chapter Closure", description: "Hash-bind closure status and durable evidence for causal, foreshadowing, Promise, relationship, opposition, signature, state and memory updates.", parameters: Type.Object({ projectId: ProjectId, chapter: Chapter, bodySha256: Sha256, operations: Type.Object({ causalEvents: Type.Optional(ClosureOperation), foreshadowing: Type.Optional(ClosureOperation), promisePayoff: Type.Optional(ClosureOperation), relationshipGraph: Type.Optional(ClosureOperation), oppositionClocks: Type.Optional(ClosureOperation), chapterSignature: Type.Optional(ClosureOperation), dynamicState: Type.Optional(ClosureOperation), memoryIndex: Type.Optional(ClosureOperation) }, { additionalProperties: false }), note: Type.Optional(Type.String({ maxLength: 10000 })) }), run: (params) => engine.recordChapterClosure(params) });
    add({ name: "novel_chapter_closure_status", label: "Read Chapter Closure", description: "Read chapter closure completeness and verify its current body-hash binding.", parameters: Type.Object({ projectId: ProjectId, chapter: Chapter }), run: (params) => engine.chapterClosureStatus(params) });
    add({ name: "novel_project_integrity_check", label: "Check Novel Project Integrity", description: "Recover pending transactions, validate all chapter/receipt/hash/state/memory bindings and optionally perform safe metadata repairs.", parameters: Type.Object({ projectId: ProjectId, repair: Type.Optional(Type.Boolean()) }), run: (params) => engine.projectIntegrityCheck(params) });
  }
});
