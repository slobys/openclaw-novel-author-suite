import { promises as fs } from "node:fs";
import os from "node:os";
import path from "node:path";
import {
  PROJECT_ID_PATTERN,
  atomicWrite,
  boundedNumber,
  clip,
  codedError,
  countHanChars,
  exists,
  firstNonEmptyLine,
  isInside,
  isPidAlive,
  normalizeChapterList,
  normalizeProjectId,
  normalizeStringArray,
  nowIso,
  padChapter,
  parseChapter,
  parseChapterMarkdown,
  readJson,
  readJsonOr,
  readTextOr,
  resolveInside,
  safeKey,
  sanitizeForJson,
  sha256,
  stableStringify,
  tokenizeForSearch,
  writeJson
} from "./utils.js";

export const ENGINE_VERSION = "0.4.8";
export const ENGINE_SCHEMA_VERSION = 2;

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

const IDEA_SCORE_WEIGHTS = {
  originality: 0.25,
  tension: 0.2,
  agency: 0.15,
  sustainability: 0.15,
  emotion: 0.15,
  genrePromise: 0.1
};

export const LOGIC_AUDIT_CATEGORIES = [
  "facts",
  "timeline",
  "space",
  "motivation",
  "knowledge",
  "worldRules",
  "resources",
  "causality",
  "foreshadowing",
  "originality",
  "voice",
  "sceneDynamics",
  "promiseFairness",
  "relationshipContinuity",
  "emotionCurve",
  "fatigueRisk",
  "oppositionPressure"
];

const ARTIFACTS = {
  "structure-fingerprint": () => "analysis/structure-fingerprint.md",
  "reference-synthesis": (key) => `analysis/synthesis/${safeKey(key, "synthesis key")}.md`,
  "creative-brief": () => "blueprint/creative-brief.md",
  "story-engine": () => "blueprint/story-engine.md",
  "novelty-report": () => "blueprint/novelty-report.md",
  premise: () => "blueprint/premise.md",
  world: () => "blueprint/world.md",
  "world-rules": () => "blueprint/world-rules.md",
  characters: () => "blueprint/characters.md",
  "master-outline": () => "blueprint/master-outline.md",
  "writing-rules": () => "blueprint/writing-rules.md",
  "genre-profile": () => "blueprint/genre-profile.json",
  "volume-outline": (key) => `blueprint/volume-outlines/${safeKey(String(key), "volume key")}.md`,
  "chapter-outline": (key) => `outlines/chapter-${padChapter(parseChapter(key))}.md`
};

const LEDGER_FILES = {
  promise: "story/ledgers/promises.json",
  relationship: "story/ledgers/relationships.json",
  oppositionClock: "story/ledgers/opposition-clocks.json",
  chapterSignature: "story/ledgers/chapter-signatures.json",
  arcAudit: "story/ledgers/arc-audits.json",
  outlineDrift: "story/ledgers/outline-drift.json"
};

const CLOSURE_OPERATIONS = [
  "causalEvents",
  "foreshadowing",
  "promisePayoff",
  "relationshipGraph",
  "oppositionClocks",
  "chapterSignature",
  "dynamicState",
  "memoryIndex"
];

const ACCEPTED_CHECK_STATUSES = new Set(["pass", "passed", "ok", "true", "note", "warning", "warn", "na", "n/a", "not_applicable"]);
const BLOCKING_CHECK_STATUSES = new Set(["fail", "failed", "false", "error", "block", "blocked", "fatal", "revise"]);
const BLOCKING_SEVERITIES = new Set(["error", "block", "fatal"]);
const REVIEW_REQUIRED_CHECKS = {
  "continuity-auditor": ["facts", "timeline", "knowledgeBoundary", "stateContinuity", "causality", "promiseContinuity", "relationshipContinuity"],
  "reader-editor": ["readability", "pacing", "repetition", "genreExperience", "hookQuality", "characterAgency"]
};

function splitByParagraphs(text, maxChars, title = "未命名片段") {
  const paragraphs = text.split(/\n{2,}/).map((item) => item.trim()).filter(Boolean);
  if (paragraphs.length === 0) return [];
  const result = [];
  let current = "";
  let part = 1;
  for (const paragraph of paragraphs) {
    if (current && current.length + paragraph.length + 2 > maxChars) {
      result.push({ title: part === 1 ? title : `${title}（续${part}）`, content: current });
      current = "";
      part += 1;
    }
    if (paragraph.length > maxChars) {
      if (current) {
        result.push({ title: part === 1 ? title : `${title}（续${part}）`, content: current });
        current = "";
        part += 1;
      }
      for (let offset = 0; offset < paragraph.length; offset += maxChars) {
        result.push({ title: `${title}（分段${part}）`, content: paragraph.slice(offset, offset + maxChars) });
        part += 1;
      }
    } else {
      current = current ? `${current}\n\n${paragraph}` : paragraph;
    }
  }
  if (current) result.push({ title: part === 1 ? title : `${title}（续${part}）`, content: current });
  return result;
}

export function splitReferenceText(rawText, maxChars = 12000) {
  const text = String(rawText ?? "").replace(/^\uFEFF/, "").replace(/\r\n?/g, "\n").trim();
  if (!text) throw codedError("REFERENCE_EMPTY", "Reference text is empty.");
  const headingPattern = /(?:^|\n)[ \t]*(第[〇零一二三四五六七八九十百千万两0-9０-９]+(?:章|回|节)[^\n]*)[ \t]*(?=\n|$)/g;
  const matches = [...text.matchAll(headingPattern)];
  if (matches.length < 2) return splitByParagraphs(text, maxChars);

  const chunks = [];
  const preface = text.slice(0, matches[0].index).trim();
  if (preface) chunks.push(...splitByParagraphs(preface, maxChars, "正文前资料"));
  for (let index = 0; index < matches.length; index += 1) {
    const start = matches[index].index + (matches[index][0].startsWith("\n") ? 1 : 0);
    const end = index + 1 < matches.length ? matches[index + 1].index : text.length;
    const content = text.slice(start, end).trim();
    chunks.push(...splitByParagraphs(content, maxChars, matches[index][1].trim()));
  }
  return chunks;
}

async function listChapterNumbers(projectDir) {
  const directory = resolveInside(projectDir, "chapters");
  let names = [];
  try {
    names = await fs.readdir(directory);
  } catch (error) {
    if (error.code !== "ENOENT") throw error;
  }
  return names
    .map((name) => /^chapter-(\d+)\.md$/.exec(name))
    .filter(Boolean)
    .map((match) => Number(match[1]))
    .sort((a, b) => a - b);
}

function assertContiguous(numbers) {
  for (let index = 0; index < numbers.length; index += 1) {
    if (numbers[index] !== index + 1) {
      throw codedError("CHAPTER_SEQUENCE_GAP", `Chapter sequence has a gap before chapter ${numbers[index]}.`, { numbers });
    }
  }
}

function scoreIdea(scores) {
  if (scores === undefined || scores === null) return null;
  if (!scores || typeof scores !== "object" || Array.isArray(scores)) {
    throw codedError("INVALID_IDEA_SCORES", "scores must be a JSON object.");
  }
  const normalized = {};
  let weightedTotal = 0;
  for (const [field, weight] of Object.entries(IDEA_SCORE_WEIGHTS)) {
    const value = Number(scores[field]);
    if (!Number.isFinite(value) || value < 0 || value > 100) {
      throw codedError("INVALID_IDEA_SCORE", `scores.${field} must be between 0 and 100.`, { field, value: scores[field] });
    }
    normalized[field] = Math.round(value * 100) / 100;
    weightedTotal += value * weight;
  }
  return { ...normalized, weightedTotal: Math.round(weightedTotal * 100) / 100 };
}

function normalizeForeshadowingChanges(value) {
  if (value === undefined || value === null) return [];
  if (!Array.isArray(value) || value.length > 100) {
    throw codedError("INVALID_FORESHADOWING_DELTA", "continuityDelta.foreshadowing must be an array of at most 100 items.");
  }
  return value.map((item) => {
    if (!item || typeof item !== "object" || Array.isArray(item)) {
      throw codedError("INVALID_FORESHADOWING_CHANGE", "Each foreshadowing change must be an object.");
    }
    const id = safeKey(item.id, "foreshadowing id");
    const action = item.action;
    if (!["open", "advance", "close", "payoff", "cancel"].includes(action)) {
      throw codedError("UNSUPPORTED_FORESHADOWING_ACTION", `Unsupported foreshadowing action: ${action}`, { action });
    }
    return { id, action, note: String(item.note ?? "").trim() };
  });
}

function normalizeTitle(title, chapter, rejectEmbeddedHeading = true) {
  const normalized = String(title ?? "").trim();
  if (!normalized) throw codedError("CHAPTER_TITLE_REQUIRED", "Chapter title is required.");
  if (/\r|\n/.test(normalized)) throw codedError("CHAPTER_TITLE_MULTILINE", "Chapter title must be a single line.");
  if (rejectEmbeddedHeading && (/^#+\s*/.test(normalized) || /^第\s*[0-9〇零一二三四五六七八九十百千万两]+\s*章/u.test(normalized))) {
    throw codedError("CHAPTER_TITLE_NOT_PURE", "title must contain only the chapter title, without Markdown or chapter number.", { chapter, title: normalized });
  }
  return normalized;
}

function canonicalBodyText(body) {
  return String(body ?? "").replace(/\r\n?/g, "\n").trim();
}

function assertBodyPayload(body, chapter, rejectEmbeddedHeading = true) {
  const trimmed = canonicalBodyText(body);
  if (!trimmed) throw codedError("CHAPTER_BODY_REQUIRED", "Chapter body is required.");
  const firstLine = firstNonEmptyLine(trimmed);
  if (rejectEmbeddedHeading && (/^#{1,6}\s*/.test(firstLine) || /^第\s*[0-9〇零一二三四五六七八九十百千万两]+\s*章(?:\s|$)/u.test(firstLine))) {
    throw codedError("CHAPTER_BODY_CONTAINS_HEADING", "Chapter body must not contain a chapter heading; the engine renders it exactly once.", { chapter, firstLine });
  }
  return trimmed;
}

function requestFingerprint({ chapter, title, content, summary, continuityDelta, operation = "commit" }) {
  return sha256(stableStringify({
    operation,
    chapter,
    title: String(title ?? "").trim(),
    contentSha256: sha256(canonicalBodyText(content)),
    summarySha256: sha256(String(summary ?? "").trim()),
    continuitySha256: sha256(stableStringify(continuityDelta ?? {}))
  }));
}

function extractCheckStatus(value) {
  if (typeof value === "boolean") return value ? "pass" : "fail";
  if (typeof value === "string") return value.trim().toLowerCase();
  if (value && typeof value === "object" && !Array.isArray(value)) {
    if (typeof value.pass === "boolean") return value.pass ? "pass" : "fail";
    for (const key of ["status", "decision", "result", "conclusion"]) {
      if (typeof value[key] === "string") return value[key].trim().toLowerCase();
    }
  }
  return "unknown";
}

function analyzeAuditChecks(checks, requiredCategories, requireComplete) {
  if (!checks || typeof checks !== "object" || Array.isArray(checks)) {
    throw codedError("INVALID_AUDIT_CHECKS", "checks must be a JSON object.");
  }
  const coverage = {};
  const missing = [];
  const failing = [];
  for (const category of requiredCategories) {
    if (!(category in checks)) {
      coverage[category] = "missing";
      if (requireComplete) missing.push(category);
      continue;
    }
    const status = extractCheckStatus(checks[category]);
    coverage[category] = status;
    if (BLOCKING_CHECK_STATUSES.has(status)) failing.push(category);
    else if (!ACCEPTED_CHECK_STATUSES.has(status) && requireComplete) failing.push(category);
  }
  return { coverage, missing, failing, complete: missing.length === 0, pass: missing.length === 0 && failing.length === 0 };
}

function normalizeReviewIssues(value, label) {
  if (value === undefined || value === null) return [];
  if (!Array.isArray(value) || value.length > 100) {
    throw codedError("INVALID_REVIEW_ISSUES", `${label} must be an array of at most 100 items.`, { label });
  }
  return value.map((item) => {
    if (!item || typeof item !== "object" || Array.isArray(item)) {
      throw codedError("INVALID_REVIEW_ISSUE", `${label} entries must be objects.`, { label });
    }
    const severity = String(item.severity ?? "note").trim().toLowerCase();
    if (!["note", "warning", "error", "block", "fatal"].includes(severity)) {
      throw codedError("INVALID_REVIEW_SEVERITY", `Unsupported review severity: ${severity}`, { label, severity });
    }
    return {
      category: String(item.category ?? "general").trim(),
      severity,
      evidence: String(item.evidence ?? item.message ?? "").trim(),
      repair: String(item.repair ?? item.suggestion ?? "").trim()
    };
  });
}

function normalizeReviewer(review, expectedRole, bodySha256) {
  if (!review || typeof review !== "object" || Array.isArray(review)) {
    throw codedError("INVALID_REVIEW_RECEIPT", `${expectedRole} review must be an object.`);
  }
  const role = String(review.reviewerRole ?? "").trim();
  if (role !== expectedRole) {
    throw codedError("REVIEW_ROLE_MISMATCH", `Expected reviewerRole=${expectedRole}.`, { expectedRole, actualRole: role });
  }
  const reviewerSessionId = String(review.reviewerSessionId ?? "").trim();
  if (!reviewerSessionId) throw codedError("REVIEW_SESSION_REQUIRED", `${expectedRole} reviewerSessionId is required.`);
  const reviewBodySha256 = String(review.bodySha256 ?? "").trim().toLowerCase();
  if (!/^[a-f0-9]{64}$/.test(reviewBodySha256)) {
    throw codedError("REVIEW_BODY_HASH_REQUIRED", `${expectedRole} must provide the reviewed bodySha256.`);
  }
  if (reviewBodySha256 !== bodySha256) {
    throw codedError("REVIEW_BODY_HASH_MISMATCH", `${expectedRole} review does not match the supplied chapter body.`, { expected: bodySha256, actual: review.bodySha256 });
  }
  const conclusion = String(review.conclusion ?? review.decision ?? "").trim().toLowerCase();
  if (!["pass", "revise", "block"].includes(conclusion)) {
    throw codedError("INVALID_REVIEW_CONCLUSION", `${expectedRole} conclusion must be pass, revise or block.`, { conclusion });
  }
  if (!Array.isArray(review.issues)) throw codedError("REVIEW_ISSUES_REQUIRED", `${expectedRole}.issues must be an array.`);
  const issues = normalizeReviewIssues(review.issues, `${expectedRole}.issues`);
  const checks = review.checks;
  if (!checks || typeof checks !== "object" || Array.isArray(checks)) {
    throw codedError("REVIEW_CHECKS_REQUIRED", `${expectedRole}.checks must be an object.`);
  }
  const missingChecks = REVIEW_REQUIRED_CHECKS[expectedRole].filter((key) => !(key in checks));
  const failingChecks = REVIEW_REQUIRED_CHECKS[expectedRole].filter((key) => key in checks && !ACCEPTED_CHECK_STATUSES.has(extractCheckStatus(checks[key])));
  if (missingChecks.length || failingChecks.length) {
    throw codedError("REVIEW_CHECKS_INCOMPLETE", `${expectedRole} review checks are incomplete or not passing.`, { missing: missingChecks, failing: failingChecks });
  }
  const blockingIssues = issues.filter((item) => BLOCKING_SEVERITIES.has(item.severity));
  return {
    reviewerRole: expectedRole,
    reviewerSessionId,
    bodySha256,
    conclusion,
    checks: sanitizeForJson(checks, 100000),
    issues,
    summary: String(review.summary ?? "").trim(),
    blockingIssueCount: blockingIssues.length,
    pass: conclusion === "pass" && blockingIssues.length === 0
  };
}

function defaultProjectConfig(engineConfig, timestamp = nowIso(), enforcementFromChapter = 1) {
  const minHan = engineConfig.minChapterHanChars;
  const targetMin = Math.max(minHan, engineConfig.targetChapterHanChars);
  const targetMax = Math.max(targetMin, engineConfig.targetChapterHanCharsMax);
  return {
    schemaVersion: ENGINE_SCHEMA_VERSION,
    revision: 1,
    writingContract: {
      minHanChars: minHan,
      targetMinHanChars: targetMin,
      targetMaxHanChars: targetMax
    },
    quality: {
      requireChapterAudit: engineConfig.requireChapterAudit,
      requireCompleteAuditChecks: engineConfig.requireCompleteAuditChecks,
      requiredAuditCategories: [...LOGIC_AUDIT_CATEGORIES],
      requireQualityGate: engineConfig.requireQualityGate,
      requireRevisionAudit: engineConfig.requireRevisionAudit,
      requireRevisionCas: engineConfig.requireRevisionCas,
      requireClosureReceipt: engineConfig.requireClosureReceipt
    },
    enforcement: {
      lengthFromChapter: enforcementFromChapter,
      auditFromChapter: enforcementFromChapter,
      qualityFromChapter: enforcementFromChapter,
      closureFromChapter: enforcementFromChapter,
      metadataFromChapter: enforcementFromChapter
    },
    genreProfile: {},
    createdAt: timestamp,
    updatedAt: timestamp
  };
}

function validateWritingContract(value, fallback) {
  const source = value ?? fallback;
  if (!source || typeof source !== "object" || Array.isArray(source)) {
    throw codedError("INVALID_WRITING_CONTRACT", "writingContract must be an object.");
  }
  const minHanChars = boundedNumber(source.minHanChars ?? fallback.minHanChars, { label: "writingContract.minHanChars", min: 0, max: 20000, integer: true });
  const targetMinHanChars = boundedNumber(source.targetMinHanChars ?? fallback.targetMinHanChars, { label: "writingContract.targetMinHanChars", min: 0, max: 30000, integer: true });
  const targetMaxHanChars = boundedNumber(source.targetMaxHanChars ?? fallback.targetMaxHanChars, { label: "writingContract.targetMaxHanChars", min: 0, max: 50000, integer: true });
  if (targetMinHanChars < minHanChars) {
    throw codedError("INVALID_WRITING_CONTRACT", "targetMinHanChars must be greater than or equal to minHanChars.", { minHanChars, targetMinHanChars });
  }
  if (targetMaxHanChars < targetMinHanChars) {
    throw codedError("INVALID_WRITING_CONTRACT", "targetMaxHanChars must be greater than or equal to targetMinHanChars.", { targetMinHanChars, targetMaxHanChars });
  }
  return { minHanChars, targetMinHanChars, targetMaxHanChars };
}

function validateQualityConfig(value, fallback) {
  const source = value ?? fallback;
  if (!source || typeof source !== "object" || Array.isArray(source)) {
    throw codedError("INVALID_QUALITY_CONFIG", "quality must be an object.");
  }
  const categories = source.requiredAuditCategories === undefined
    ? [...fallback.requiredAuditCategories]
    : normalizeStringArray(source.requiredAuditCategories, "quality.requiredAuditCategories", LOGIC_AUDIT_CATEGORIES.length, 100);
  const unsupported = categories.filter((item) => !LOGIC_AUDIT_CATEGORIES.includes(item));
  if (unsupported.length) {
    throw codedError("UNSUPPORTED_AUDIT_CATEGORY", "quality.requiredAuditCategories contains unsupported values.", { unsupported });
  }
  return {
    requireChapterAudit: source.requireChapterAudit ?? fallback.requireChapterAudit,
    requireCompleteAuditChecks: source.requireCompleteAuditChecks ?? fallback.requireCompleteAuditChecks,
    requiredAuditCategories: categories,
    requireQualityGate: source.requireQualityGate ?? fallback.requireQualityGate,
    requireRevisionAudit: source.requireRevisionAudit ?? fallback.requireRevisionAudit,
    requireRevisionCas: source.requireRevisionCas ?? fallback.requireRevisionCas,
    requireClosureReceipt: source.requireClosureReceipt ?? fallback.requireClosureReceipt
  };
}

function validateEnforcement(value, fallback) {
  const source = value ?? fallback;
  if (!source || typeof source !== "object" || Array.isArray(source)) throw codedError("INVALID_ENFORCEMENT_CONFIG", "enforcement must be an object.");
  const field = (name) => boundedNumber(source[name] ?? fallback[name], { label: `enforcement.${name}`, min: 1, max: 999999, integer: true });
  return {
    lengthFromChapter: field("lengthFromChapter"),
    auditFromChapter: field("auditFromChapter"),
    qualityFromChapter: field("qualityFromChapter"),
    closureFromChapter: field("closureFromChapter"),
    metadataFromChapter: field("metadataFromChapter")
  };
}

function ledgerTemplate() {
  return { schemaVersion: ENGINE_SCHEMA_VERSION, revision: 0, entries: [], updatedAt: null };
}

function dynamicStateTemplate() {
  return {
    schemaVersion: ENGINE_SCHEMA_VERSION,
    revision: 0,
    characters: {},
    knowledge: {},
    inventory: {},
    locations: {},
    updatedAt: null
  };
}

function memoryTemplate() {
  return { schemaVersion: ENGINE_SCHEMA_VERSION, revision: 0, records: [], updatedAt: null };
}

function normalizeLedgerEntry(ledgerType, rawEntry) {
  if (!rawEntry || typeof rawEntry !== "object" || Array.isArray(rawEntry)) {
    throw codedError("INVALID_LEDGER_ENTRY", `${ledgerType} entry must be an object.`, { ledgerType });
  }
  const entry = sanitizeForJson(rawEntry, 100000);
  if (ledgerType === "promise") {
    const id = safeKey(entry.id, "promise id");
    const status = entry.status ?? "open";
    if (!["planned", "open", "touched", "partial", "paid", "cancelled"].includes(status)) {
      throw codedError("INVALID_PROMISE_STATUS", `Unsupported promise status: ${status}`, { status });
    }
    return {
      ...entry,
      id,
      status,
      promise: String(entry.promise ?? entry.summary ?? "").trim(),
      intensity: entry.intensity === undefined ? null : boundedNumber(entry.intensity, { label: "promise.intensity", min: 0, max: 10 }),
      openedChapter: entry.openedChapter == null ? null : parseChapter(entry.openedChapter),
      lastTouchedChapter: entry.lastTouchedChapter == null ? null : parseChapter(entry.lastTouchedChapter),
      payoffChapter: entry.payoffChapter == null ? null : parseChapter(entry.payoffChapter),
      payoffWindow: entry.payoffWindow ? {
        start: parseChapter(entry.payoffWindow.start),
        end: parseChapter(entry.payoffWindow.end)
      } : null
    };
  }
  if (ledgerType === "relationship") {
    const fromId = safeKey(entry.fromId, "relationship fromId");
    const toId = safeKey(entry.toId, "relationship toId");
    if (fromId === toId) throw codedError("INVALID_RELATIONSHIP", "Relationship endpoints must be different.");
    const id = entry.id ? safeKey(entry.id, "relationship id") : `${fromId}::${toId}`;
    const dimensions = {};
    for (const [key, value] of Object.entries(entry.dimensions ?? {})) {
      safeKey(key, "relationship dimension");
      dimensions[key] = boundedNumber(value, { label: `relationship.dimensions.${key}`, min: -100, max: 100 });
    }
    return {
      ...entry,
      id,
      fromId,
      toId,
      stage: String(entry.stage ?? "unknown").trim(),
      dimensions,
      unresolved: normalizeStringArray(entry.unresolved, "relationship.unresolved", 100, 2000)
    };
  }
  if (ledgerType === "oppositionClock") {
    const id = safeKey(entry.id, "opposition clock id");
    const status = entry.status ?? "active";
    if (!["planned", "active", "paused", "resolved", "cancelled"].includes(status)) {
      throw codedError("INVALID_OPPOSITION_STATUS", `Unsupported opposition clock status: ${status}`, { status });
    }
    return {
      ...entry,
      id,
      status,
      progress: entry.progress === undefined ? 0 : boundedNumber(entry.progress, { label: "oppositionClock.progress", min: 0, max: 100 }),
      lastAdvancedChapter: entry.lastAdvancedChapter == null ? null : parseChapter(entry.lastAdvancedChapter),
      deadlineChapter: entry.deadlineChapter == null ? null : parseChapter(entry.deadlineChapter),
      nextAction: String(entry.nextAction ?? "").trim()
    };
  }
  if (ledgerType === "chapterSignature") {
    const chapter = parseChapter(entry.chapter);
    if (!/^[a-f0-9]{64}$/i.test(String(entry.bodySha256 ?? ""))) {
      throw codedError("INVALID_BODY_HASH", "chapterSignature.bodySha256 must be a SHA-256 hex string.");
    }
    return {
      ...entry,
      id: `chapter-${padChapter(chapter)}`,
      chapter,
      bodySha256: String(entry.bodySha256).toLowerCase(),
      experienceScores: sanitizeForJson(entry.experienceScores ?? {}, 20000),
      plannedBeatIds: normalizeStringArray(entry.plannedBeatIds, "chapterSignature.plannedBeatIds", 100, 200),
      fulfilledBeatIds: normalizeStringArray(entry.fulfilledBeatIds, "chapterSignature.fulfilledBeatIds", 100, 200),
      deferredBeatIds: normalizeStringArray(entry.deferredBeatIds, "chapterSignature.deferredBeatIds", 100, 200),
      newBeatIds: normalizeStringArray(entry.newBeatIds, "chapterSignature.newBeatIds", 100, 200)
    };
  }
  if (ledgerType === "arcAudit") {
    const startChapter = parseChapter(entry.startChapter);
    const endChapter = parseChapter(entry.endChapter);
    if (endChapter < startChapter) throw codedError("INVALID_ARC_RANGE", "arcAudit.endChapter must be at or after startChapter.");
    return {
      ...entry,
      id: entry.id ? safeKey(entry.id, "arc audit id") : `arc-${padChapter(startChapter)}-${padChapter(endChapter)}`,
      startChapter,
      endChapter,
      findings: sanitizeForJson(entry.findings ?? {}, 100000),
      decisions: sanitizeForJson(entry.decisions ?? {}, 100000)
    };
  }
  if (ledgerType === "outlineDrift") {
    const checkpointChapter = parseChapter(entry.checkpointChapter);
    return {
      ...entry,
      id: entry.id ? safeKey(entry.id, "outline drift id") : `drift-${padChapter(checkpointChapter)}`,
      checkpointChapter,
      plannedBeatIds: normalizeStringArray(entry.plannedBeatIds, "outlineDrift.plannedBeatIds", 500, 200),
      fulfilledBeatIds: normalizeStringArray(entry.fulfilledBeatIds, "outlineDrift.fulfilledBeatIds", 500, 200),
      deferredBeatIds: normalizeStringArray(entry.deferredBeatIds, "outlineDrift.deferredBeatIds", 500, 200),
      newBeatIds: normalizeStringArray(entry.newBeatIds, "outlineDrift.newBeatIds", 500, 200),
      driftScore: entry.driftScore === undefined ? null : boundedNumber(entry.driftScore, { label: "outlineDrift.driftScore", min: 0, max: 100 })
    };
  }
  throw codedError("UNSUPPORTED_LEDGER_TYPE", `Unsupported ledger type: ${ledgerType}`, { ledgerType });
}

function queryLedgerEntries(ledgerType, entries, query) {
  let result = [...entries];
  if (Array.isArray(query.ids) && query.ids.length) {
    const ids = new Set(query.ids.map((item) => safeKey(item, "ledger id")));
    result = result.filter((item) => ids.has(item.id));
  }
  if (query.status) result = result.filter((item) => item.status === query.status);
  const chapter = query.chapter == null ? null : parseChapter(query.chapter);
  const horizon = Math.max(0, Math.min(100, Number(query.horizon ?? 0)));
  if (chapter !== null) {
    if (ledgerType === "promise") {
      result = result.filter((item) => {
        if (["paid", "cancelled"].includes(item.status)) return false;
        if (item.payoffWindow?.end != null && item.payoffWindow.end < chapter) return true;
        if (item.payoffWindow?.start != null && item.payoffWindow.start <= chapter + horizon) return true;
        return item.status === "open" || item.status === "touched" || item.status === "partial";
      });
    } else if (ledgerType === "oppositionClock") {
      result = result.filter((item) => item.status === "active" && (item.deadlineChapter == null || item.deadlineChapter <= chapter + horizon));
    } else if (ledgerType === "chapterSignature") {
      result = result.filter((item) => item.chapter <= chapter);
    }
  }
  if (ledgerType === "chapterSignature") result.sort((left, right) => right.chapter - left.chapter);
  else result.sort((left, right) => String(right.updatedAt ?? "").localeCompare(String(left.updatedAt ?? "")));
  const limit = Math.max(1, Math.min(200, Number(query.limit ?? 50)));
  return result.slice(0, limit);
}

export class NovelEngine {
  constructor(config = {}) {
    const defaultDataRoot = path.join(os.homedir(), ".openclaw", "data");
    this.config = {
      projectsRoot: path.resolve(config.projectsRoot ?? path.join(defaultDataRoot, "novels")),
      importRoots: (config.importRoots ?? [path.join(defaultDataRoot, "novel-imports")]).map((item) => path.resolve(item)),
      maxReferenceBytes: config.maxReferenceBytes ?? 20 * 1024 * 1024,
      referenceChunkChars: config.referenceChunkChars ?? 12000,
      minChapterChars: config.minChapterChars ?? 800,
      minChapterHanChars: config.minChapterHanChars ?? 2000,
      targetChapterHanChars: config.targetChapterHanChars ?? 2600,
      targetChapterHanCharsMax: config.targetChapterHanCharsMax ?? 3200,
      requireChapterAudit: config.requireChapterAudit ?? true,
      requireCompleteAuditChecks: config.requireCompleteAuditChecks ?? true,
      requireQualityGate: config.requireQualityGate ?? true,
      requireRevisionAudit: config.requireRevisionAudit ?? true,
      requireRevisionCas: config.requireRevisionCas ?? true,
      requireClosureReceipt: config.requireClosureReceipt ?? true,
      rejectEmbeddedChapterHeading: config.rejectEmbeddedChapterHeading ?? true,
      lockStaleMs: config.lockStaleMs ?? 10 * 60 * 1000,
      lockAcquireTimeoutMs: config.lockAcquireTimeoutMs ?? 15 * 1000,
      maxArtifactChars: config.maxArtifactChars ?? 500000,
      maxContinuityDeltaChars: config.maxContinuityDeltaChars ?? 200000,
      maxMemoryRecords: config.maxMemoryRecords ?? 10000,
      maxLedgerEntries: config.maxLedgerEntries ?? 10000,
      transactionRetention: config.transactionRetention ?? 200,
      __testFailAfterTargetWrites: config.__testFailAfterTargetWrites ?? null
    };
    if (this.config.targetChapterHanChars < this.config.minChapterHanChars) {
      throw codedError("INVALID_ENGINE_CONFIG", "targetChapterHanChars must be greater than or equal to minChapterHanChars.");
    }
    if (this.config.targetChapterHanCharsMax < this.config.targetChapterHanChars) {
      throw codedError("INVALID_ENGINE_CONFIG", "targetChapterHanCharsMax must be greater than or equal to targetChapterHanChars.");
    }
  }

  projectDir(projectId) {
    return resolveInside(this.config.projectsRoot, normalizeProjectId(projectId));
  }

  async requireProject(projectId) {
    const projectDir = this.projectDir(projectId);
    if (!(await exists(resolveInside(projectDir, "project.json")))) {
      throw codedError("PROJECT_NOT_FOUND", `Novel project does not exist: ${projectId}`, { projectId });
    }
    await this.ensureProjectDirectories(projectDir);
    return projectDir;
  }

  async ensureProjectDirectories(projectDir) {
    const directories = [
      "sources/reference-chunks",
      "analysis/chapter-cards",
      "analysis/synthesis",
      "blueprint/volume-outlines",
      "creative",
      "outlines",
      "chapters",
      "chapters/meta",
      "summaries",
      "continuity/deltas",
      "story/audits/history",
      "story/quality/history",
      "story/ledgers",
      "story/dynamic",
      "story/memory",
      "story/closures",
      "versions/chapters",
      "versions/artifacts",
      "requests/commits",
      "requests/revisions",
      "receipts/commits",
      "receipts/revisions",
      "transactions/pending",
      "transactions/completed"
    ];
    await Promise.all(directories.map((item) => fs.mkdir(resolveInside(projectDir, item), { recursive: true })));
  }

  async initializeOptionalLedgers(projectDir, timestamp = nowIso()) {
    const initialFiles = [
      ["story/causal-events.json", { schemaVersion: ENGINE_SCHEMA_VERSION, revision: 0, events: [], updatedAt: timestamp }],
      ["story/foreshadowing.json", { schemaVersion: ENGINE_SCHEMA_VERSION, revision: 0, entries: [], updatedAt: timestamp }],
      ...Object.values(LEDGER_FILES).map((relativePath) => [relativePath, { ...ledgerTemplate(), updatedAt: timestamp }]),
      ["story/dynamic/state.json", { ...dynamicStateTemplate(), updatedAt: timestamp }],
      ["story/memory/index.json", { ...memoryTemplate(), updatedAt: timestamp }]
    ];
    for (const [relativePath, value] of initialFiles) {
      const filePath = resolveInside(projectDir, relativePath);
      if (!(await exists(filePath))) await writeJson(filePath, value);
    }
  }

  async readProjectConfig(projectDir) {
    const configPath = resolveInside(projectDir, "project-config.json");
    if (!(await exists(configPath))) {
      const state = await readJsonOr(resolveInside(projectDir, "state.json"), { nextChapter: 1 });
      const boundary = Number.isInteger(state.nextChapter) && state.nextChapter > 0 ? state.nextChapter : 1;
      const migrated = {
        ...defaultProjectConfig(this.config, nowIso(), boundary),
        migratedFromLegacy: boundary > 1,
        legacyBoundaryChapter: boundary > 1 ? boundary : null
      };
      await writeJson(configPath, migrated);
      return { ...migrated, persisted: true };
    }
    const stored = await readJson(configPath);
    const defaultConfig = defaultProjectConfig(this.config, stored.createdAt ?? nowIso(), 1);
    const writingContract = validateWritingContract(stored.writingContract, defaultConfig.writingContract);
    const quality = validateQualityConfig(stored.quality, defaultConfig.quality);
    const enforcement = validateEnforcement(stored.enforcement, defaultConfig.enforcement);
    return {
      schemaVersion: stored.schemaVersion ?? ENGINE_SCHEMA_VERSION,
      revision: Number.isInteger(stored.revision) ? stored.revision : 1,
      writingContract,
      quality,
      enforcement,
      genreProfile: sanitizeForJson(stored.genreProfile ?? {}, 100000),
      migratedFromLegacy: stored.migratedFromLegacy === true,
      legacyBoundaryChapter: stored.legacyBoundaryChapter ?? null,
      createdAt: stored.createdAt ?? defaultConfig.createdAt,
      updatedAt: stored.updatedAt ?? defaultConfig.updatedAt,
      persisted: true
    };
  }

  async configureProject({ projectId, expectedRevision, writingContract, quality, enforcement, genreProfile }) {
    const projectDir = await this.requireProject(projectId);
    return this.withProjectLock(projectDir, async () => {
      await this.recoverPendingTransactionsUnlocked(projectDir);
      const current = await this.readProjectConfig(projectDir);
      if (expectedRevision !== undefined && expectedRevision !== null && Number(expectedRevision) !== current.revision) {
        throw codedError("PROJECT_CONFIG_REVISION_MISMATCH", "Project configuration changed since it was read.", { expectedRevision, actualRevision: current.revision });
      }
      const next = {
        schemaVersion: ENGINE_SCHEMA_VERSION,
        revision: current.revision + (current.persisted ? 1 : 0),
        writingContract: validateWritingContract(writingContract, current.writingContract),
        quality: validateQualityConfig(quality, current.quality),
        enforcement: validateEnforcement(enforcement, current.enforcement),
        genreProfile: genreProfile === undefined ? current.genreProfile : sanitizeForJson(genreProfile, 100000),
        migratedFromLegacy: current.migratedFromLegacy === true,
        legacyBoundaryChapter: current.legacyBoundaryChapter ?? null,
        createdAt: current.createdAt,
        updatedAt: nowIso()
      };
      await writeJson(resolveInside(projectDir, "project-config.json"), next);
      return { projectId: normalizeProjectId(projectId), ...next, persisted: true };
    });
  }

  async projectConfigStatus(projectId) {
    const projectDir = await this.requireProject(projectId);
    const { projectConfig, recoveredTransactions } = await this.recoverProjectForRead(projectDir);
    return { projectId: normalizeProjectId(projectId), ...projectConfig, recoveredTransactions };
  }

  async withProjectLock(projectDir, action) {
    const lockPath = resolveInside(projectDir, ".write.lock");
    const token = sha256(`${process.pid}:${nowIso()}:${Math.random()}`);
    const lockPayload = { leaseVersion: 1, pid: process.pid, hostname: os.hostname(), token, createdAt: nowIso() };
    const acquireStartedAt = Date.now();
    let replacedStaleLock = null;

    const createLock = async () => {
      let handle;
      try {
        handle = await fs.open(lockPath, "wx", 0o600);
        await handle.writeFile(JSON.stringify(replacedStaleLock ? { ...lockPayload, replacedStaleLock } : lockPayload), "utf8");
        await handle.sync();
        return true;
      } catch (error) {
        if (error.code === "EEXIST") return false;
        throw error;
      } finally {
        await handle?.close().catch(() => {});
      }
    };

    const acquire = async () => {
      while (!(await createLock())) {
        let previous = null;
        let stat = null;
        try {
          previous = await readJson(lockPath);
          stat = await fs.stat(lockPath);
        } catch (error) {
          if (error.code === "ENOENT") continue;
          if (error.code === "JSON_CORRUPT") {
            try {
              stat = await fs.stat(lockPath);
            } catch (statError) {
              if (statError.code === "ENOENT") continue;
              throw statError;
            }
          } else {
            throw error;
          }
        }

        const ageMs = stat ? Math.max(0, Date.now() - stat.mtimeMs) : 0;
        const sameHost = previous?.hostname === os.hostname();
        const ownerPid = Number(previous?.pid);
        const sameHostAlive = sameHost && isPidAlive(ownerPid);
        const sameHostOwnerDead = sameHost && Number.isInteger(ownerPid) && ownerPid > 0 && !sameHostAlive;
        if (sameHostOwnerDead || ageMs > this.config.lockStaleMs) {
          let unchanged = false;
          try {
            const currentStat = await fs.stat(lockPath);
            if (previous?.token) {
              const current = await readJson(lockPath);
              unchanged = current.token === previous.token;
            } else {
              unchanged = currentStat.mtimeMs === stat?.mtimeMs && currentStat.size === stat?.size;
            }
          } catch (error) {
            if (error.code === "ENOENT") continue;
            if (error.code !== "JSON_CORRUPT") throw error;
          }
          if (unchanged) {
            await fs.unlink(lockPath).catch(() => {});
            replacedStaleLock = { previous, ageMs, sameHostAlive, sameHostOwnerDead, replacedAt: nowIso() };
          }
          continue;
        }

        const waitedMs = Date.now() - acquireStartedAt;
        if (waitedMs >= this.config.lockAcquireTimeoutMs) {
          throw codedError("PROJECT_WRITE_LOCKED", "This novel project is already being written.", {
            previous,
            ageMs,
            sameHostAlive,
            sameHostOwnerDead,
            waitedMs,
            lockAcquireTimeoutMs: this.config.lockAcquireTimeoutMs
          });
        }
        await delay(Math.min(100, Math.max(1, this.config.lockAcquireTimeoutMs - waitedMs)));
      }
    };

    await acquire();
    const heartbeatMs = Math.max(250, Math.min(30000, Math.floor(this.config.lockStaleMs / 3)));
    let heartbeatBusy = false;
    const heartbeat = setInterval(() => {
      if (heartbeatBusy) return;
      heartbeatBusy = true;
      void (async () => {
        try {
          const current = await readJson(lockPath);
          if (current.token === token) {
            const timestamp = new Date();
            await fs.utimes(lockPath, timestamp, timestamp);
          }
        } catch {
          // A failed heartbeat is handled by token-aware cleanup or stale-lock recovery.
        } finally {
          heartbeatBusy = false;
        }
      })();
    }, heartbeatMs);
    heartbeat.unref?.();
    try {
      return await action();
    } finally {
      clearInterval(heartbeat);
      try {
        const current = await readJson(lockPath);
        if (current.token === token) await fs.unlink(lockPath);
      } catch {
        // The lock may already have been removed after a process-level failure.
      }
    }
  }

  async currentFileFingerprint(filePath) {
    if (!(await exists(filePath))) return null;
    return sha256(await fs.readFile(filePath, "utf8"));
  }

  async buildTransactionWrite(projectDir, relativePath, content, expectedSha256 = undefined) {
    const safePath = resolveInside(projectDir, relativePath);
    const currentSha256 = expectedSha256 === undefined ? await this.currentFileFingerprint(safePath) : expectedSha256;
    return {
      relativePath: relativePath.replaceAll("\\", "/"),
      expectedSha256: currentSha256,
      targetSha256: sha256(content),
      content
    };
  }

  async prepareTransaction(projectDir, transaction) {
    const pendingPath = resolveInside(projectDir, `transactions/pending/${safeKey(transaction.transactionId, "transaction id")}.json`);
    if (await exists(pendingPath)) {
      const previous = await readJson(pendingPath);
      if (previous.payloadFingerprint !== transaction.payloadFingerprint) {
        throw codedError("TRANSACTION_ID_COLLISION", "Existing transaction ID has a different payload.", { transactionId: transaction.transactionId });
      }
      return previous;
    }
    const manifest = {
      schemaVersion: ENGINE_SCHEMA_VERSION,
      engineVersion: ENGINE_VERSION,
      status: "prepared",
      createdAt: nowIso(),
      appliedWrites: 0,
      ...transaction
    };
    await writeJson(pendingPath, manifest);
    return manifest;
  }

  async applyTransactionUnlocked(projectDir, manifest) {
    const pendingPath = resolveInside(projectDir, `transactions/pending/${safeKey(manifest.transactionId, "transaction id")}.json`);
    let appliedWrites = 0;
    const writes = manifest.writes ?? [];
    for (let writeIndex = 0; writeIndex < writes.length; writeIndex += 1) {
      const write = writes[writeIndex];
      const targetPath = resolveInside(projectDir, write.relativePath);
      const currentSha256 = await this.currentFileFingerprint(targetPath);
      if (currentSha256 === write.targetSha256) {
        // A recovery pass may encounter targets already written by the failed pass.
        // Derive progress from the target index instead of incrementing the stale
        // manifest counter, otherwise appliedWrites can exceed writes.length.
        appliedWrites = writeIndex + 1;
        continue;
      }
      if (write.expectedSha256 === null && currentSha256 !== null) {
        throw codedError("TRANSACTION_TARGET_CONFLICT", "Transaction expected a new file, but the target already exists with different content.", { transactionId: manifest.transactionId, relativePath: write.relativePath, currentSha256, targetSha256: write.targetSha256 });
      }
      if (write.expectedSha256 !== null && currentSha256 !== write.expectedSha256) {
        throw codedError("TRANSACTION_CAS_CONFLICT", "Transaction target changed after preparation.", { transactionId: manifest.transactionId, relativePath: write.relativePath, expectedSha256: write.expectedSha256, currentSha256 });
      }
      await atomicWrite(targetPath, write.content);
      appliedWrites = writeIndex + 1;
      manifest.appliedWrites = appliedWrites;
      manifest.status = "applying";
      manifest.updatedAt = nowIso();
      await writeJson(pendingPath, manifest);
      if (this.config.__testFailAfterTargetWrites && appliedWrites >= this.config.__testFailAfterTargetWrites) {
        this.config.__testFailAfterTargetWrites = null;
        throw codedError("TEST_INJECTED_TRANSACTION_FAILURE", "Injected failure after transaction target write.", { appliedWrites });
      }
    }
    manifest.status = "committed";
    manifest.appliedWrites = manifest.writes.length;
    manifest.completedAt = nowIso();
    await writeJson(pendingPath, manifest);
    const completedPath = resolveInside(projectDir, `transactions/completed/${manifest.transactionId}.json`);
    await fs.rename(pendingPath, completedPath).catch(async (error) => {
      if (error.code !== "ENOENT") throw error;
    });
    await this.pruneCompletedTransactions(projectDir);
    return manifest.result;
  }

  async recoverPendingTransactionsUnlocked(projectDir) {
    const pendingDir = resolveInside(projectDir, "transactions/pending");
    await fs.mkdir(pendingDir, { recursive: true });
    const names = (await fs.readdir(pendingDir)).filter((name) => name.endsWith(".json")).sort();
    const recovered = [];
    for (const name of names) {
      const manifest = await readJson(resolveInside(pendingDir, name));
      const result = await this.applyTransactionUnlocked(projectDir, manifest);
      recovered.push({ transactionId: manifest.transactionId, kind: manifest.kind, result });
    }
    return recovered;
  }

  async pruneCompletedTransactions(projectDir) {
    const completedDir = resolveInside(projectDir, "transactions/completed");
    const entries = [];
    for (const name of await fs.readdir(completedDir)) {
      if (!name.endsWith(".json")) continue;
      const filePath = resolveInside(completedDir, name);
      const stat = await fs.stat(filePath);
      entries.push({ name, mtimeMs: stat.mtimeMs });
    }
    entries.sort((left, right) => right.mtimeMs - left.mtimeMs);
    for (const stale of entries.slice(this.config.transactionRetention)) {
      await fs.unlink(resolveInside(completedDir, stale.name)).catch(() => {});
    }
  }

  async reconcileStateUnlocked(projectDir) {
    const statePath = resolveInside(projectDir, "state.json");
    const state = await readJson(statePath);
    const numbers = await listChapterNumbers(projectDir);
    assertContiguous(numbers);
    const last = numbers.at(-1) ?? 0;
    if (state.lastCommittedChapter !== last || state.nextChapter !== last + 1) {
      state.lastCommittedChapter = last;
      state.nextChapter = last + 1;
      state.updatedAt = nowIso();
      state.reconciledByEngineVersion = ENGINE_VERSION;
      await writeJson(statePath, state);
    }
    return state;
  }

  async recoverProjectForRead(projectDir) {
    return this.withProjectLock(projectDir, async () => {
      await this.ensureProjectDirectories(projectDir);
      await this.initializeOptionalLedgers(projectDir);
      const recoveredTransactions = await this.recoverPendingTransactionsUnlocked(projectDir);
      const project = await readJson(resolveInside(projectDir, "project.json"));
      const state = await this.reconcileStateUnlocked(projectDir);
      const projectConfig = await this.readProjectConfig(projectDir);
      return { project, state, projectConfig, recoveredTransactions };
    });
  }

  async createProject({ projectId, title, genre = "", premise = "", referenceTitle = "" }) {
    const id = normalizeProjectId(projectId);
    if (typeof title !== "string" || !title.trim()) throw codedError("PROJECT_TITLE_REQUIRED", "title is required.");
    await fs.mkdir(this.config.projectsRoot, { recursive: true });
    const projectDir = this.projectDir(id);
    try {
      await fs.mkdir(projectDir);
    } catch (error) {
      if (error.code === "EEXIST") throw codedError("PROJECT_ALREADY_EXISTS", `Novel project already exists: ${id}`, { projectId: id });
      throw error;
    }
    await this.ensureProjectDirectories(projectDir);
    const timestamp = nowIso();
    await writeJson(resolveInside(projectDir, "project.json"), {
      schemaVersion: ENGINE_SCHEMA_VERSION,
      id,
      title: title.trim(),
      genre: String(genre).trim(),
      premise: String(premise).trim(),
      referenceTitle: String(referenceTitle).trim(),
      createdAt: timestamp,
      updatedAt: timestamp
    });
    await writeJson(resolveInside(projectDir, "project-config.json"), defaultProjectConfig(this.config, timestamp));
    await writeJson(resolveInside(projectDir, "state.json"), {
      schemaVersion: ENGINE_SCHEMA_VERSION,
      revision: 1,
      phase: "created",
      nextChapter: 1,
      lastCommittedChapter: 0,
      integrityStatus: "clean",
      reference: { imported: false, totalChunks: 0, analyzedChunks: 0 },
      createdAt: timestamp,
      updatedAt: timestamp
    });
    await writeJson(resolveInside(projectDir, "creative/idea-bank.json"), {
      schemaVersion: ENGINE_SCHEMA_VERSION,
      revision: 0,
      candidates: [],
      selectedId: null,
      updatedAt: timestamp
    });
    await this.initializeOptionalLedgers(projectDir, timestamp);
    return {
      projectId: id,
      projectDir,
      phase: "created",
      nextChapter: 1,
      engineVersion: ENGINE_VERSION,
      projectConfig: await this.readProjectConfig(projectDir)
    };
  }

  async listProjects() {
    await fs.mkdir(this.config.projectsRoot, { recursive: true });
    const entries = await fs.readdir(this.config.projectsRoot, { withFileTypes: true });
    const projects = [];
    for (const entry of entries) {
      if (!entry.isDirectory() || !PROJECT_ID_PATTERN.test(entry.name)) continue;
      const projectDir = resolveInside(this.config.projectsRoot, entry.name);
      const projectPath = resolveInside(projectDir, "project.json");
      const statePath = resolveInside(projectDir, "state.json");
      if (!(await exists(projectPath)) || !(await exists(statePath))) continue;
      try {
        const item = await this.withProjectLock(projectDir, async () => {
          await this.ensureProjectDirectories(projectDir);
          await this.recoverPendingTransactionsUnlocked(projectDir);
          const project = await readJson(projectPath);
          const state = await this.reconcileStateUnlocked(projectDir);
          return { id: project.id, title: project.title, genre: project.genre, phase: state.phase, nextChapter: state.nextChapter, updatedAt: state.updatedAt };
        });
        projects.push(item);
      } catch (error) {
        if (error.code === "PROJECT_WRITE_LOCKED") {
          const project = await readJson(projectPath);
          const state = await readJson(statePath);
          projects.push({ id: project.id, title: project.title, genre: project.genre, phase: state.phase, nextChapter: state.nextChapter, updatedAt: state.updatedAt, busy: true });
        } else {
          projects.push({ id: entry.name, error: error.message, errorCode: error.code ?? "UNKNOWN" });
        }
      }
    }
    projects.sort((left, right) => String(right.updatedAt ?? "").localeCompare(String(left.updatedAt ?? "")));
    return { engineVersion: ENGINE_VERSION, projects };
  }

  async projectStatus(projectId) {
    const projectDir = await this.requireProject(projectId);
    return this.withProjectLock(projectDir, async () => {
      await this.initializeOptionalLedgers(projectDir);
      const recoveredTransactions = await this.recoverPendingTransactionsUnlocked(projectDir);
      const project = await readJson(resolveInside(projectDir, "project.json"));
      const state = await this.reconcileStateUnlocked(projectDir);
      const projectConfig = await this.readProjectConfig(projectDir);
      const required = {
        structureFingerprint: await exists(resolveInside(projectDir, "analysis/structure-fingerprint.md")),
        creativeBrief: await exists(resolveInside(projectDir, "blueprint/creative-brief.md")),
        storyEngine: await exists(resolveInside(projectDir, "blueprint/story-engine.md")),
        noveltyReport: await exists(resolveInside(projectDir, "blueprint/novelty-report.md")),
        premise: await exists(resolveInside(projectDir, "blueprint/premise.md")),
        world: await exists(resolveInside(projectDir, "blueprint/world.md")),
        worldRules: await exists(resolveInside(projectDir, "blueprint/world-rules.md")),
        characters: await exists(resolveInside(projectDir, "blueprint/characters.md")),
        masterOutline: await exists(resolveInside(projectDir, "blueprint/master-outline.md")),
        nextChapterOutline: await exists(resolveInside(projectDir, `outlines/chapter-${padChapter(state.nextChapter)}.md`))
      };
      const ideaBank = await readJsonOr(resolveInside(projectDir, "creative/idea-bank.json"), { candidates: [], selectedId: null });
      const causalGraph = await readJsonOr(resolveInside(projectDir, "story/causal-events.json"), { events: [] });
      const foreshadowing = await readJsonOr(resolveInside(projectDir, "story/foreshadowing.json"), { entries: [] });
      const promises = await readJsonOr(resolveInside(projectDir, LEDGER_FILES.promise), ledgerTemplate());
      const relationships = await readJsonOr(resolveInside(projectDir, LEDGER_FILES.relationship), ledgerTemplate());
      const opposition = await readJsonOr(resolveInside(projectDir, LEDGER_FILES.oppositionClock), ledgerTemplate());
      const signatures = await readJsonOr(resolveInside(projectDir, LEDGER_FILES.chapterSignature), ledgerTemplate());
      const dynamicState = await readJsonOr(resolveInside(projectDir, "story/dynamic/state.json"), dynamicStateTemplate());
      const memory = await readJsonOr(resolveInside(projectDir, "story/memory/index.json"), memoryTemplate());
      const nextAuditPath = resolveInside(projectDir, `story/audits/chapter-${padChapter(state.nextChapter)}-precommit.json`);
      const nextQualityPath = resolveInside(projectDir, `story/quality/chapter-${padChapter(state.nextChapter)}.json`);
      const nextAudit = await readJsonOr(nextAuditPath, null);
      const nextQuality = await readJsonOr(nextQualityPath, null);
      const closureNames = (await fs.readdir(resolveInside(projectDir, "story/closures"))).filter((name) => /^chapter-\d+\.json$/.test(name));
      let pendingClosures = 0;
      for (const name of closureNames) {
        const closure = await readJson(resolveInside(projectDir, `story/closures/${name}`));
        if (closure.status !== "complete") pendingClosures += 1;
      }
      const pendingTransactions = (await fs.readdir(resolveInside(projectDir, "transactions/pending"))).filter((name) => name.endsWith(".json")).length;
      return {
        engineVersion: ENGINE_VERSION,
        engineSchemaVersion: ENGINE_SCHEMA_VERSION,
        project,
        projectConfig,
        state,
        required,
        creativeReadiness: {
          candidateCount: ideaBank.candidates?.length ?? 0,
          selectedIdeaId: ideaBank.selectedId ?? null,
          ready: Boolean(ideaBank.selectedId && required.creativeBrief && required.storyEngine && required.noveltyReport)
        },
        storyLedgers: {
          causalEvents: causalGraph.events?.length ?? 0,
          openForeshadowing: (foreshadowing.entries ?? []).filter((item) => ["open", "advanced"].includes(item.status)).length,
          overdueForeshadowing: (foreshadowing.entries ?? []).filter((item) => ["open", "advanced"].includes(item.status) && item.payoffWindow?.end < state.nextChapter).length,
          openPromises: (promises.entries ?? []).filter((item) => !["paid", "cancelled"].includes(item.status)).length,
          relationshipEdges: relationships.entries?.length ?? 0,
          activeOppositionClocks: (opposition.entries ?? []).filter((item) => item.status === "active").length,
          chapterSignatures: signatures.entries?.length ?? 0,
          dynamicStateRevision: dynamicState.revision ?? 0,
          memoryRecords: memory.records?.length ?? 0,
          pendingClosures,
          nextChapterAudit: nextAudit?.decision ?? null,
          nextChapterQuality: nextQuality?.qualityPass ?? null,
          auditRequired: projectConfig.quality.requireChapterAudit,
          qualityGateRequired: projectConfig.quality.requireQualityGate,
          closureReceiptRequired: projectConfig.quality.requireClosureReceipt,
          requiredAuditCategories: projectConfig.quality.requiredAuditCategories,
          chapterLengthGate: {
            legacyMinChars: this.config.minChapterChars,
            minHanChars: projectConfig.writingContract.minHanChars,
            targetMinHanChars: projectConfig.writingContract.targetMinHanChars,
            targetMaxHanChars: projectConfig.writingContract.targetMaxHanChars,
            enforcedServerSide: projectConfig.writingContract.minHanChars > 0
          }
        },
        serverCapabilities: {
          serverGateVerified: projectConfig.writingContract.minHanChars > 0
            && projectConfig.quality.requireChapterAudit === true
            && projectConfig.quality.requireCompleteAuditChecks === true
            && LOGIC_AUDIT_CATEGORIES.every((category) => projectConfig.quality.requiredAuditCategories.includes(category))
            && projectConfig.quality.requireQualityGate === true
            && projectConfig.quality.requireClosureReceipt === true,
          engineVersion: ENGINE_VERSION,
          hanLengthRecount: true,
          auditBodyHashBinding: true,
          completeAuditCoverage: projectConfig.quality.requireCompleteAuditChecks === true && LOGIC_AUDIT_CATEGORIES.every((category) => projectConfig.quality.requiredAuditCategories.includes(category)),
          requiredAuditCategoryCount: projectConfig.quality.requiredAuditCategories.length,
          independentQualityReceipt: projectConfig.quality.requireQualityGate === true,
          closureReceiptRequired: projectConfig.quality.requireClosureReceipt === true,
          requestIdRequired: true,
          derivedBodyHashBinding: true,
          requestIdIdempotency: true,
          requestIdPayloadBinding: true,
          crashRecoverableTransactions: true,
          commitStatusReconciliation: true,
          revisionCas: true,
          dynamicStateLedger: true,
          threeTierMemory: true,
          storyLedgers: true,
          projectIntegrityCheck: true,
          resolvedHardMinHanChars: projectConfig.writingContract.minHanChars
        },
        runtimeHealth: {
          pendingTransactions,
          recoveredTransactions,
          integrityStatus: state.integrityStatus ?? "unknown"
        },
        readyToWrite: required.premise && required.world && required.characters && required.masterOutline && required.nextChapterOutline
      };
    });
  }

  async importReference({ projectId, sourcePath, title = "" }) {
    const projectDir = await this.requireProject(projectId);
    const absoluteSource = path.resolve(sourcePath);
    if (path.extname(absoluteSource).toLowerCase() !== ".txt") throw codedError("REFERENCE_FORMAT_UNSUPPORTED", "Only UTF-8 TXT reference files are supported.");
    if (this.config.importRoots.length === 0) throw codedError("REFERENCE_IMPORT_DISABLED", "No importRoots configured.");
    if (!this.config.importRoots.some((root) => isInside(absoluteSource, root))) {
      throw codedError("REFERENCE_PATH_NOT_ALLOWED", "Reference path is outside configured importRoots.", { sourcePath: absoluteSource });
    }
    const stat = await fs.stat(absoluteSource);
    if (!stat.isFile()) throw codedError("REFERENCE_NOT_FILE", "Reference path is not a file.");
    if (stat.size > this.config.maxReferenceBytes) {
      throw codedError("REFERENCE_TOO_LARGE", `Reference exceeds maxReferenceBytes (${this.config.maxReferenceBytes}).`, { bytes: stat.size });
    }
    const content = await fs.readFile(absoluteSource, "utf8");
    const chunks = splitReferenceText(content, this.config.referenceChunkChars);
    return this.withProjectLock(projectDir, async () => {
      await this.recoverPendingTransactionsUnlocked(projectDir);
      const sourceCopy = resolveInside(projectDir, "sources/reference.txt");
      await atomicWrite(sourceCopy, content);
      const manifest = {
        schemaVersion: ENGINE_SCHEMA_VERSION,
        revision: 1,
        title: String(title).trim() || path.basename(absoluteSource, path.extname(absoluteSource)),
        sourceFile: "sources/reference.txt",
        sourceSha256: sha256(content),
        importedAt: nowIso(),
        chunks: []
      };
      for (let index = 0; index < chunks.length; index += 1) {
        const id = `chunk-${String(index + 1).padStart(5, "0")}`;
        const relativeFile = `sources/reference-chunks/${id}.txt`;
        await atomicWrite(resolveInside(projectDir, relativeFile), `${chunks[index].content.trim()}\n`);
        manifest.chunks.push({ id, title: chunks[index].title, file: relativeFile, chars: chunks[index].content.length, status: "pending" });
      }
      await writeJson(resolveInside(projectDir, "sources/reference-manifest.json"), manifest);
      const state = await this.reconcileStateUnlocked(projectDir);
      state.phase = "analyzing-reference";
      state.reference = { imported: true, totalChunks: chunks.length, analyzedChunks: 0 };
      state.revision = Number(state.revision ?? 0) + 1;
      state.updatedAt = nowIso();
      await writeJson(resolveInside(projectDir, "state.json"), state);
      return { projectId: normalizeProjectId(projectId), referenceTitle: manifest.title, sourceSha256: manifest.sourceSha256, totalChunks: chunks.length };
    });
  }

  async nextReferenceChunk(projectId) {
    const batch = await this.nextReferenceBatch({ projectId, limit: 1, maxTotalChars: this.config.referenceChunkChars + 1000 });
    if (batch.complete) return { complete: true, analyzedChunks: batch.progress.analyzedChunks, totalChunks: batch.progress.totalChunks };
    const chunk = batch.chunks[0];
    return { complete: false, chunkId: chunk.chunkId, title: chunk.title, content: chunk.content, progress: batch.progress, analysisContract: batch.analysisContract };
  }

  async nextReferenceBatch({ projectId, limit = 4, maxTotalChars = 30000 }) {
    const projectDir = await this.requireProject(projectId);
    const manifestPath = resolveInside(projectDir, "sources/reference-manifest.json");
    if (!(await exists(manifestPath))) throw codedError("REFERENCE_NOT_IMPORTED", "No reference has been imported.");
    const manifest = await readJson(manifestPath);
    const pending = manifest.chunks.filter((item) => item.status !== "analyzed");
    const analyzed = manifest.chunks.length - pending.length;
    if (pending.length === 0) return { complete: true, chunks: [], progress: { analyzedChunks: analyzed, totalChunks: manifest.chunks.length } };
    const boundedLimit = Math.min(10, Math.max(1, Number(limit)));
    const boundedChars = Math.min(80000, Math.max(4000, Number(maxTotalChars)));
    const selected = [];
    let chars = 0;
    for (const chunk of pending) {
      if (selected.length >= boundedLimit) break;
      if (selected.length > 0 && chars + chunk.chars > boundedChars) break;
      selected.push({ chunkId: chunk.id, title: chunk.title, content: await fs.readFile(resolveInside(projectDir, chunk.file), "utf8") });
      chars += chunk.chars;
    }
    return {
      complete: false,
      chunks: selected,
      progress: { analyzedChunks: analyzed, totalChunks: manifest.chunks.length },
      analysisContract: ["summary", "chapterFunction", "goals", "conflicts", "turningPoints", "hooks", "characterChanges", "foreshadowing", "pacing", "styleMetrics"]
    };
  }

  async referenceAnalysisBatch({ projectId, start = 1, limit = 20 }) {
    const projectDir = await this.requireProject(projectId);
    const manifestPath = resolveInside(projectDir, "sources/reference-manifest.json");
    if (!(await exists(manifestPath))) throw codedError("REFERENCE_NOT_IMPORTED", "No reference has been imported.");
    const manifest = await readJson(manifestPath);
    const first = Math.max(1, Number(start));
    const boundedLimit = Math.min(50, Math.max(1, Number(limit)));
    const selected = manifest.chunks.slice(first - 1, first - 1 + boundedLimit);
    const cards = [];
    for (const chunk of selected) {
      if (chunk.status !== "analyzed" || !chunk.analysisFile) cards.push({ chunkId: chunk.id, title: chunk.title, status: chunk.status });
      else cards.push(await readJson(resolveInside(projectDir, chunk.analysisFile)));
    }
    return { start: first, count: cards.length, totalChunks: manifest.chunks.length, nextStart: first - 1 + cards.length < manifest.chunks.length ? first + cards.length : null, cards };
  }

  async recordReferenceAnalysisUnlocked(projectDir, chunkId, analysis) {
    const manifestPath = resolveInside(projectDir, "sources/reference-manifest.json");
    const manifest = await readJson(manifestPath);
    const chunk = manifest.chunks.find((item) => item.id === chunkId);
    if (!chunk) throw codedError("REFERENCE_CHUNK_NOT_FOUND", `Unknown reference chunk: ${chunkId}`, { chunkId });
    if (!analysis || typeof analysis !== "object" || Array.isArray(analysis)) throw codedError("INVALID_REFERENCE_ANALYSIS", "analysis must be a JSON object.");
    const analysisPath = resolveInside(projectDir, `analysis/chapter-cards/${chunk.id}.json`);
    await writeJson(analysisPath, { ...sanitizeForJson(analysis, 200000), schemaVersion: ENGINE_SCHEMA_VERSION, chunkId, title: chunk.title, analyzedAt: nowIso() });
    chunk.status = "analyzed";
    chunk.analysisFile = `analysis/chapter-cards/${chunk.id}.json`;
    manifest.revision = Number(manifest.revision ?? 0) + 1;
    manifest.updatedAt = nowIso();
    await writeJson(manifestPath, manifest);
    const analyzedChunks = manifest.chunks.filter((item) => item.status === "analyzed").length;
    const state = await this.reconcileStateUnlocked(projectDir);
    state.reference = { imported: true, totalChunks: manifest.chunks.length, analyzedChunks };
    if (analyzedChunks === manifest.chunks.length) state.phase = "reference-analyzed";
    state.revision = Number(state.revision ?? 0) + 1;
    state.updatedAt = nowIso();
    await writeJson(resolveInside(projectDir, "state.json"), state);
    return { chunkId, analyzedChunks, totalChunks: manifest.chunks.length, complete: analyzedChunks === manifest.chunks.length };
  }

  async recordReferenceAnalysis({ projectId, chunkId, analysis }) {
    const projectDir = await this.requireProject(projectId);
    return this.withProjectLock(projectDir, async () => {
      await this.recoverPendingTransactionsUnlocked(projectDir);
      return this.recordReferenceAnalysisUnlocked(projectDir, chunkId, analysis);
    });
  }

  async recordReferenceBatch({ projectId, analyses }) {
    if (!Array.isArray(analyses) || analyses.length < 1 || analyses.length > 10) {
      throw codedError("INVALID_REFERENCE_BATCH", "analyses must contain 1-10 chunk analysis objects.");
    }
    const projectDir = await this.requireProject(projectId);
    return this.withProjectLock(projectDir, async () => {
      await this.recoverPendingTransactionsUnlocked(projectDir);
      let result;
      for (const item of analyses) result = await this.recordReferenceAnalysisUnlocked(projectDir, item.chunkId, item.analysis);
      return { ...result, recorded: analyses.length };
    });
  }

  artifactPath(projectDir, artifactType, key) {
    const resolver = ARTIFACTS[artifactType];
    if (!resolver) throw codedError("UNSUPPORTED_ARTIFACT_TYPE", `Unsupported artifactType: ${artifactType}`, { artifactType });
    if (["reference-synthesis", "volume-outline", "chapter-outline"].includes(artifactType) && (key === undefined || key === null || key === "")) {
      throw codedError("ARTIFACT_KEY_REQUIRED", `${artifactType} requires key.`, { artifactType });
    }
    return resolveInside(projectDir, resolver(key));
  }

  async writeArtifact({ projectId, artifactType, key, content, expectedSha256 = null }) {
    const projectDir = await this.requireProject(projectId);
    if (typeof content !== "string" || !content.trim()) throw codedError("ARTIFACT_CONTENT_REQUIRED", "Artifact content is required.");
    if (content.length > this.config.maxArtifactChars) throw codedError("ARTIFACT_TOO_LARGE", "Artifact content exceeds configured limit.", { actualChars: content.length, maxChars: this.config.maxArtifactChars });
    return this.withProjectLock(projectDir, async () => {
      await this.recoverPendingTransactionsUnlocked(projectDir);
      const artifactPath = this.artifactPath(projectDir, artifactType, key);
      const current = await readTextOr(artifactPath, "");
      const currentSha256 = current ? sha256(current) : null;
      if (expectedSha256 && expectedSha256 !== currentSha256) {
        throw codedError("ARTIFACT_CAS_MISMATCH", "Artifact changed since it was read.", { expectedSha256, currentSha256 });
      }
      if (current) {
        const versionKey = safeKey(`${artifactType}-${String(key ?? "default")}`, "artifact version key");
        const versionPath = resolveInside(projectDir, `versions/artifacts/${versionKey}/${nowIso().replace(/[:.]/g, "-")}-${currentSha256.slice(0, 12)}.md`);
        await atomicWrite(versionPath, current);
      }
      const normalized = `${content.trim()}\n`;
      await atomicWrite(artifactPath, normalized);
      const state = await this.reconcileStateUnlocked(projectDir);
      if (["creative-brief", "story-engine", "novelty-report", "premise", "world", "world-rules", "characters", "master-outline", "writing-rules", "genre-profile", "volume-outline", "chapter-outline"].includes(artifactType)) state.phase = "planning";
      state.revision = Number(state.revision ?? 0) + 1;
      state.updatedAt = nowIso();
      await writeJson(resolveInside(projectDir, "state.json"), state);
      return { projectId: normalizeProjectId(projectId), artifactType, key: key ?? null, path: path.relative(projectDir, artifactPath).replaceAll("\\", "/"), sha256: sha256(normalized), previousSha256: currentSha256 };
    });
  }

  async readArtifact({ projectId, artifactType, key }) {
    const projectDir = await this.requireProject(projectId);
    const artifactPath = this.artifactPath(projectDir, artifactType, key);
    if (!(await exists(artifactPath))) return { found: false, artifactType, key: key ?? null };
    const content = await fs.readFile(artifactPath, "utf8");
    return { found: true, artifactType, key: key ?? null, content, sha256: sha256(content) };
  }

  async writeIdeaBank({ projectId, candidates, selectedId = null, expectedRevision = null }) {
    const projectDir = await this.requireProject(projectId);
    if (!Array.isArray(candidates) || candidates.length < 1 || candidates.length > 30) throw codedError("INVALID_IDEA_CANDIDATES", "candidates must contain 1-30 idea candidates.");
    return this.withProjectLock(projectDir, async () => {
      await this.recoverPendingTransactionsUnlocked(projectDir);
      const bankPath = resolveInside(projectDir, "creative/idea-bank.json");
      const bank = await readJsonOr(bankPath, { schemaVersion: ENGINE_SCHEMA_VERSION, revision: 0, candidates: [], selectedId: null });
      if (expectedRevision !== null && Number(expectedRevision) !== Number(bank.revision ?? 0)) throw codedError("IDEA_BANK_REVISION_MISMATCH", "Idea bank changed since it was read.", { expectedRevision, actualRevision: bank.revision ?? 0 });
      const byId = new Map((bank.candidates ?? []).map((item) => [item.id, item]));
      for (const candidate of candidates) {
        if (!candidate || typeof candidate !== "object" || Array.isArray(candidate)) throw codedError("INVALID_IDEA_CANDIDATE", "candidate must be an object.");
        const id = safeKey(candidate.id, "candidate id");
        for (const field of ["title", "hook", "premise", "storyEngine"]) if (typeof candidate[field] !== "string" || !candidate[field].trim()) throw codedError("IDEA_FIELD_REQUIRED", `candidate.${field} is required.`, { field });
        const previous = byId.get(id) ?? {};
        const status = candidate.status ?? previous.status ?? "draft";
        if (!["draft", "shortlisted", "selected", "rejected"].includes(status)) throw codedError("INVALID_IDEA_STATUS", `Unsupported idea status: ${status}`, { status });
        byId.set(id, {
          ...previous,
          ...sanitizeForJson(candidate, 100000),
          id,
          title: candidate.title.trim(),
          hook: candidate.hook.trim(),
          premise: candidate.premise.trim(),
          storyEngine: candidate.storyEngine.trim(),
          protagonist: String(candidate.protagonist ?? "").trim(),
          coreConflict: String(candidate.coreConflict ?? "").trim(),
          worldMechanism: String(candidate.worldMechanism ?? "").trim(),
          cost: String(candidate.cost ?? "").trim(),
          endingQuestion: String(candidate.endingQuestion ?? "").trim(),
          referenceDistance: String(candidate.referenceDistance ?? "").trim(),
          strengths: normalizeStringArray(candidate.strengths, "candidate.strengths", 20, 1000),
          risks: normalizeStringArray(candidate.risks, "candidate.risks", 20, 1000),
          scores: candidate.scores ? scoreIdea(candidate.scores) : previous.scores ?? null,
          status,
          updatedAt: nowIso()
        });
      }
      if (selectedId !== null && selectedId !== undefined && selectedId !== "") {
        const normalizedSelected = safeKey(selectedId, "selected idea id");
        if (!byId.has(normalizedSelected)) throw codedError("SELECTED_IDEA_NOT_FOUND", `Selected idea does not exist: ${normalizedSelected}`);
        bank.selectedId = normalizedSelected;
        for (const candidate of byId.values()) candidate.status = candidate.id === normalizedSelected ? "selected" : candidate.status === "selected" ? "shortlisted" : candidate.status;
      }
      bank.schemaVersion = ENGINE_SCHEMA_VERSION;
      bank.revision = Number(bank.revision ?? 0) + 1;
      bank.candidates = [...byId.values()].sort((left, right) => left.id.localeCompare(right.id));
      bank.updatedAt = nowIso();
      await writeJson(bankPath, bank);
      return { projectId: normalizeProjectId(projectId), candidateCount: bank.candidates.length, selectedId: bank.selectedId ?? null, revision: bank.revision, path: "creative/idea-bank.json" };
    });
  }

  async reviewCreativity({ projectId, candidateId, scores, strengths = [], risks = [], rationale = "", decision = "shortlist" }) {
    const projectDir = await this.requireProject(projectId);
    return this.withProjectLock(projectDir, async () => {
      await this.recoverPendingTransactionsUnlocked(projectDir);
      const bankPath = resolveInside(projectDir, "creative/idea-bank.json");
      const bank = await readJsonOr(bankPath, { schemaVersion: ENGINE_SCHEMA_VERSION, revision: 0, candidates: [], selectedId: null });
      const id = safeKey(candidateId, "candidate id");
      const candidate = (bank.candidates ?? []).find((item) => item.id === id);
      if (!candidate) throw codedError("IDEA_NOT_FOUND", `Idea candidate does not exist: ${id}`, { id });
      if (!["shortlist", "reject", "select"].includes(decision)) throw codedError("INVALID_CREATIVITY_DECISION", `Unsupported creativity decision: ${decision}`, { decision });
      const scored = scoreIdea(scores);
      candidate.scores = scored;
      candidate.strengths = normalizeStringArray(strengths, "strengths", 20, 1000);
      candidate.risks = normalizeStringArray(risks, "risks", 20, 1000);
      candidate.review = { rationale: String(rationale).trim(), decision, reviewedAt: nowIso() };
      candidate.status = decision === "select" ? "selected" : decision === "reject" ? "rejected" : "shortlisted";
      if (decision === "select") {
        bank.selectedId = id;
        for (const item of bank.candidates) if (item.id !== id && item.status === "selected") item.status = "shortlisted";
      }
      bank.revision = Number(bank.revision ?? 0) + 1;
      bank.updatedAt = nowIso();
      await writeJson(bankPath, bank);
      return { projectId: normalizeProjectId(projectId), candidateId: id, decision, scores: scored, selectedId: bank.selectedId ?? null, revision: bank.revision };
    });
  }

  async recordCausalEvent({ projectId, event, expectedRevision = null }) {
    const projectDir = await this.requireProject(projectId);
    if (!event || typeof event !== "object" || Array.isArray(event)) throw codedError("INVALID_CAUSAL_EVENT", "event must be an object.");
    return this.withProjectLock(projectDir, async () => {
      await this.recoverPendingTransactionsUnlocked(projectDir);
      const eventId = safeKey(event.eventId, "event id");
      if (typeof event.summary !== "string" || !event.summary.trim()) throw codedError("CAUSAL_EVENT_SUMMARY_REQUIRED", "event.summary is required.");
      const status = event.status ?? "planned";
      if (!["planned", "occurred", "cancelled"].includes(status)) throw codedError("INVALID_CAUSAL_EVENT_STATUS", `Unsupported causal event status: ${status}`, { status });
      const chapter = event.chapter === undefined || event.chapter === null ? null : parseChapter(event.chapter);
      const bodySha256 = String(event.bodySha256 ?? "").trim().toLowerCase();
      if (["occurred", "cancelled"].includes(status) && (chapter === null || !/^[a-f0-9]{64}$/.test(bodySha256))) {
        throw codedError("CAUSAL_BODY_BINDING_REQUIRED", "Occurred or cancelled causal events require chapter and bodySha256.", { eventId, status });
      }
      if (chapter !== null && bodySha256) await this.assertCommittedBodyBinding(projectDir, chapter, bodySha256);
      const graphPath = resolveInside(projectDir, "story/causal-events.json");
      const graph = await readJsonOr(graphPath, { schemaVersion: ENGINE_SCHEMA_VERSION, revision: 0, events: [] });
      if (expectedRevision !== null && Number(expectedRevision) !== Number(graph.revision ?? 0)) throw codedError("CAUSAL_LEDGER_REVISION_MISMATCH", "Causal ledger changed since it was read.", { expectedRevision, actualRevision: graph.revision ?? 0 });
      const index = (graph.events ?? []).findIndex((item) => item.eventId === eventId);
      const previous = index >= 0 ? graph.events[index] : {};
      const normalized = {
        ...previous,
        ...sanitizeForJson(event, 100000),
        eventId,
        summary: event.summary.trim(),
        chapter,
        bodySha256: bodySha256 || null,
        status,
        preconditions: normalizeStringArray(event.preconditions ?? previous.preconditions, "event.preconditions", 50, 1000),
        causes: normalizeStringArray(event.causes ?? previous.causes, "event.causes", 50, 128).map((item) => safeKey(item, "cause event id")),
        enables: normalizeStringArray(event.enables ?? previous.enables, "event.enables", 50, 128).map((item) => safeKey(item, "enabled event id")),
        actorGoals: normalizeStringArray(event.actorGoals ?? previous.actorGoals, "event.actorGoals", 30, 1000),
        stateChanges: normalizeStringArray(event.stateChanges ?? previous.stateChanges, "event.stateChanges", 50, 1000),
        trigger: String(event.trigger ?? previous.trigger ?? "").trim(),
        action: String(event.action ?? previous.action ?? "").trim(),
        cost: String(event.cost ?? previous.cost ?? "").trim(),
        outcome: String(event.outcome ?? previous.outcome ?? "").trim(),
        updatedAt: nowIso()
      };
      if (normalized.causes.includes(eventId) || normalized.enables.includes(eventId)) throw codedError("CAUSAL_SELF_REFERENCE", "A causal event cannot reference itself.", { eventId });
      if (index >= 0) graph.events[index] = normalized;
      else graph.events.push(normalized);
      if (graph.events.length > this.config.maxLedgerEntries) throw codedError("LEDGER_LIMIT_EXCEEDED", "Causal ledger exceeds configured entry limit.");
      graph.events.sort((left, right) => (left.chapter ?? 999999) - (right.chapter ?? 999999) || left.eventId.localeCompare(right.eventId));
      graph.schemaVersion = ENGINE_SCHEMA_VERSION;
      graph.revision = Number(graph.revision ?? 0) + 1;
      graph.updatedAt = nowIso();
      await writeJson(graphPath, graph);
      return { projectId: normalizeProjectId(projectId), eventId, status, chapter, eventCount: graph.events.length, revision: graph.revision, path: "story/causal-events.json" };
    });
  }

  async upsertForeshadowing({ projectId, entry, expectedRevision = null }) {
    const projectDir = await this.requireProject(projectId);
    if (!entry || typeof entry !== "object" || Array.isArray(entry)) throw codedError("INVALID_FORESHADOWING_ENTRY", "entry must be an object.");
    return this.withProjectLock(projectDir, async () => {
      await this.recoverPendingTransactionsUnlocked(projectDir);
      const id = safeKey(entry.id, "foreshadowing id");
      const status = entry.status ?? "planned";
      if (!["planned", "open", "advanced", "paid", "cancelled"].includes(status)) throw codedError("INVALID_FORESHADOWING_STATUS", `Unsupported foreshadowing status: ${status}`, { status });
      const type = entry.type ?? "plot";
      if (!["plot", "character", "world", "theme", "prop", "information"].includes(type)) throw codedError("INVALID_FORESHADOWING_TYPE", `Unsupported foreshadowing type: ${type}`, { type });
      const plantedChapter = entry.plantedChapter === undefined || entry.plantedChapter === null ? null : parseChapter(entry.plantedChapter);
      const sourceChapter = entry.sourceChapter === undefined || entry.sourceChapter === null ? null : parseChapter(entry.sourceChapter);
      const bodySha256 = String(entry.bodySha256 ?? "").trim().toLowerCase();
      if (status !== "planned" && (sourceChapter === null || !/^[a-f0-9]{64}$/.test(bodySha256))) {
        throw codedError("FORESHADOW_BODY_BINDING_REQUIRED", "Non-planned foreshadowing updates require sourceChapter and bodySha256.", { id, status });
      }
      if (sourceChapter !== null && bodySha256) await this.assertCommittedBodyBinding(projectDir, sourceChapter, bodySha256);
      let payoffWindow = null;
      if (entry.payoffWindow !== undefined && entry.payoffWindow !== null) {
        if (!entry.payoffWindow || typeof entry.payoffWindow !== "object" || Array.isArray(entry.payoffWindow)) throw codedError("INVALID_PAYOFF_WINDOW", "entry.payoffWindow must be an object.");
        const start = parseChapter(entry.payoffWindow.start);
        const end = parseChapter(entry.payoffWindow.end);
        if (end < start) throw codedError("INVALID_PAYOFF_WINDOW", "Foreshadowing payoffWindow.end must be at or after start.");
        payoffWindow = { start, end };
      }
      const ledgerPath = resolveInside(projectDir, "story/foreshadowing.json");
      const ledger = await readJsonOr(ledgerPath, { schemaVersion: ENGINE_SCHEMA_VERSION, revision: 0, entries: [] });
      if (expectedRevision !== null && Number(expectedRevision) !== Number(ledger.revision ?? 0)) throw codedError("FORESHADOW_LEDGER_REVISION_MISMATCH", "Foreshadowing ledger changed since it was read.", { expectedRevision, actualRevision: ledger.revision ?? 0 });
      const index = (ledger.entries ?? []).findIndex((item) => item.id === id);
      const previous = index >= 0 ? ledger.entries[index] : {};
      const normalized = {
        ...previous,
        ...sanitizeForJson(entry, 100000),
        id,
        type,
        status,
        plantedChapter,
        sourceChapter,
        bodySha256: bodySha256 || null,
        reinforceChapters: normalizeChapterList(entry.reinforceChapters ?? previous.reinforceChapters, "entry.reinforceChapters"),
        payoffWindow: payoffWindow ?? previous.payoffWindow ?? null,
        prerequisites: normalizeStringArray(entry.prerequisites ?? previous.prerequisites, "entry.prerequisites", 50, 1000),
        surfaceMeaning: String(entry.surfaceMeaning ?? previous.surfaceMeaning ?? "").trim(),
        hiddenMeaning: String(entry.hiddenMeaning ?? previous.hiddenMeaning ?? "").trim(),
        readerAwareness: String(entry.readerAwareness ?? previous.readerAwareness ?? "unknown").trim(),
        characterAwareness: sanitizeForJson(entry.characterAwareness ?? previous.characterAwareness ?? {}, 50000),
        payoffPlan: String(entry.payoffPlan ?? previous.payoffPlan ?? "").trim(),
        notes: String(entry.notes ?? previous.notes ?? "").trim(),
        updatedAt: nowIso()
      };
      if (index >= 0) ledger.entries[index] = normalized;
      else ledger.entries.push(normalized);
      if (ledger.entries.length > this.config.maxLedgerEntries) throw codedError("LEDGER_LIMIT_EXCEEDED", "Foreshadowing ledger exceeds configured entry limit.");
      ledger.entries.sort((left, right) => (left.plantedChapter ?? 999999) - (right.plantedChapter ?? 999999) || left.id.localeCompare(right.id));
      ledger.schemaVersion = ENGINE_SCHEMA_VERSION;
      ledger.revision = Number(ledger.revision ?? 0) + 1;
      ledger.updatedAt = nowIso();
      await writeJson(ledgerPath, ledger);
      return { projectId: normalizeProjectId(projectId), id, status, revision: ledger.revision, path: "story/foreshadowing.json" };
    });
  }

  async foreshadowingDue({ projectId, chapter, horizon = 3 }) {
    const projectDir = await this.requireProject(projectId);
    const state = await readJson(resolveInside(projectDir, "state.json"));
    const current = chapter === undefined || chapter === null ? state.nextChapter : parseChapter(chapter);
    const boundedHorizon = Math.min(20, Math.max(0, Number(horizon)));
    const ledger = await readJsonOr(resolveInside(projectDir, "story/foreshadowing.json"), { entries: [] });
    const active = (ledger.entries ?? []).filter((item) => !["paid", "cancelled"].includes(item.status));
    const due = active.filter((item) =>
      (item.status === "planned" && item.plantedChapter !== null && item.plantedChapter <= current)
      || (item.reinforceChapters ?? []).includes(current)
      || (["open", "advanced"].includes(item.status) && item.payoffWindow?.start <= current)
    );
    const overdue = active.filter((item) => ["open", "advanced"].includes(item.status) && item.payoffWindow?.end < current);
    const nextRelevantChapter = (item) => {
      const candidates = [
        item.status === "planned" ? item.plantedChapter : null,
        ...(item.reinforceChapters ?? []),
        item.payoffWindow?.start ?? null,
        item.payoffWindow?.end ?? null
      ].filter((value) => Number.isInteger(value) && value > current);
      return candidates.length ? Math.min(...candidates) : null;
    };
    const upcoming = active
      .map((item) => ({ ...item, nextRelevantChapter: nextRelevantChapter(item) }))
      .filter((item) => item.nextRelevantChapter !== null && item.nextRelevantChapter <= current + boundedHorizon)
      .sort((left, right) => left.nextRelevantChapter - right.nextRelevantChapter);
    return { projectId: normalizeProjectId(projectId), chapter: current, revision: ledger.revision ?? 0, due, overdue, upcoming };
  }

  async storyLedgerUpsert({ projectId, ledgerType, entry, expectedRevision = null }) {
    const relativePath = LEDGER_FILES[ledgerType];
    if (!relativePath) throw codedError("UNSUPPORTED_LEDGER_TYPE", `Unsupported ledger type: ${ledgerType}`, { ledgerType });
    const projectDir = await this.requireProject(projectId);
    return this.withProjectLock(projectDir, async () => {
      await this.recoverPendingTransactionsUnlocked(projectDir);
      const filePath = resolveInside(projectDir, relativePath);
      const ledger = await readJsonOr(filePath, ledgerTemplate());
      if (expectedRevision !== null && Number(expectedRevision) !== Number(ledger.revision ?? 0)) throw codedError("LEDGER_REVISION_MISMATCH", `${ledgerType} ledger changed since it was read.`, { expectedRevision, actualRevision: ledger.revision ?? 0, ledgerType });
      const normalized = normalizeLedgerEntry(ledgerType, entry);
      const state = await readJson(resolveInside(projectDir, "state.json"));
      if (Number(state.lastCommittedChapter ?? 0) > 0) {
        const fallbackChapter = ledgerType === "chapterSignature" ? normalized.chapter
          : ledgerType === "arcAudit" ? normalized.endChapter
            : ledgerType === "outlineDrift" ? normalized.checkpointChapter
              : normalized.payoffChapter ?? normalized.lastTouchedChapter ?? normalized.openedChapter ?? normalized.lastAdvancedChapter ?? null;
        const sourceChapter = entry.sourceChapter == null ? fallbackChapter : parseChapter(entry.sourceChapter);
        const bodySha256 = String(entry.bodySha256 ?? "").trim().toLowerCase();
        if (sourceChapter == null || !/^[a-f0-9]{64}$/.test(bodySha256)) {
          throw codedError("LEDGER_BODY_BINDING_REQUIRED", `${ledgerType} updates after the first commit require sourceChapter and bodySha256.`, { ledgerType });
        }
        await this.assertCommittedBodyBinding(projectDir, sourceChapter, bodySha256);
        normalized.sourceChapter = sourceChapter;
        normalized.bodySha256 = bodySha256;
      }
      const index = (ledger.entries ?? []).findIndex((item) => item.id === normalized.id);
      const previous = index >= 0 ? ledger.entries[index] : {};
      const merged = { ...previous, ...normalized, updatedAt: nowIso() };
      if (index >= 0) ledger.entries[index] = merged;
      else ledger.entries.push(merged);
      if (ledger.entries.length > this.config.maxLedgerEntries) throw codedError("LEDGER_LIMIT_EXCEEDED", `${ledgerType} ledger exceeds configured entry limit.`);
      ledger.schemaVersion = ENGINE_SCHEMA_VERSION;
      ledger.revision = Number(ledger.revision ?? 0) + 1;
      ledger.updatedAt = nowIso();
      await writeJson(filePath, ledger);
      return { projectId: normalizeProjectId(projectId), ledgerType, id: merged.id, revision: ledger.revision, path: relativePath, entry: merged };
    });
  }

  async storyLedgerQuery({ projectId, ledgerType, ids = [], status = null, chapter = null, horizon = 0, limit = 50 }) {
    const relativePath = LEDGER_FILES[ledgerType];
    if (!relativePath) throw codedError("UNSUPPORTED_LEDGER_TYPE", `Unsupported ledger type: ${ledgerType}`, { ledgerType });
    const projectDir = await this.requireProject(projectId);
    const ledger = await readJsonOr(resolveInside(projectDir, relativePath), ledgerTemplate());
    const entries = queryLedgerEntries(ledgerType, ledger.entries ?? [], { ids, status, chapter, horizon, limit });
    return { projectId: normalizeProjectId(projectId), ledgerType, revision: ledger.revision ?? 0, count: entries.length, entries };
  }

  async getCommittedChapterBody(projectDir, chapter) {
    const number = parseChapter(chapter);
    const chapterPath = resolveInside(projectDir, `chapters/chapter-${padChapter(number)}.md`);
    if (!(await exists(chapterPath))) throw codedError("CHAPTER_NOT_FOUND", `Chapter ${number} does not exist.`, { chapter: number });
    return parseChapterMarkdown(await fs.readFile(chapterPath, "utf8"), number);
  }

  async assertCommittedBodyBinding(projectDir, chapter, bodySha256) {
    const parsed = await this.getCommittedChapterBody(projectDir, chapter);
    if (parsed.bodySha256 !== bodySha256) throw codedError("SOURCE_BODY_HASH_MISMATCH", `Source hash does not match committed chapter ${chapter}.`, { chapter, expected: parsed.bodySha256, actual: bodySha256 });
    return parsed;
  }

  async dynamicStateUpdate({ projectId, chapter, bodySha256, sourceRef = "", characters = [], knowledge = [], inventory = [], locations = [], expectedRevision = null }) {
    const projectDir = await this.requireProject(projectId);
    const number = parseChapter(chapter);
    if (!/^[a-f0-9]{64}$/i.test(String(bodySha256 ?? ""))) throw codedError("INVALID_BODY_HASH", "bodySha256 must be a SHA-256 hex string.");
    return this.withProjectLock(projectDir, async () => {
      await this.recoverPendingTransactionsUnlocked(projectDir);
      await this.assertCommittedBodyBinding(projectDir, number, String(bodySha256).toLowerCase());
      const statePath = resolveInside(projectDir, "story/dynamic/state.json");
      const ledger = await readJsonOr(statePath, dynamicStateTemplate());
      if (expectedRevision !== null && Number(expectedRevision) !== Number(ledger.revision ?? 0)) throw codedError("DYNAMIC_STATE_REVISION_MISMATCH", "Dynamic state changed since it was read.", { expectedRevision, actualRevision: ledger.revision ?? 0 });
      const timestamp = nowIso();
      const binding = { chapter: number, bodySha256: String(bodySha256).toLowerCase(), sourceRef: String(sourceRef || `chapter:${number}`).trim(), updatedAt: timestamp };
      const updateCollection = (collectionName, items, idResolver) => {
        if (!Array.isArray(items) || items.length > 500) throw codedError("INVALID_DYNAMIC_STATE_UPDATES", `${collectionName} must be an array of at most 500 items.`, { collectionName });
        for (const raw of items) {
          if (!raw || typeof raw !== "object" || Array.isArray(raw)) throw codedError("INVALID_DYNAMIC_STATE_ENTRY", `${collectionName} entries must be objects.`, { collectionName });
          const safe = sanitizeForJson(raw, 50000);
          const id = idResolver(safe);
          ledger[collectionName][id] = { ...(ledger[collectionName][id] ?? {}), ...safe, ...binding };
        }
      };
      updateCollection("characters", characters, (item) => safeKey(item.characterId, "characterId"));
      updateCollection("knowledge", knowledge, (item) => safeKey(item.knowledgeKey ?? `${safeKey(item.knowerId, "knowerId")}::${safeKey(item.factId, "factId")}`, "knowledgeKey"));
      updateCollection("inventory", inventory, (item) => safeKey(item.itemId, "itemId"));
      updateCollection("locations", locations, (item) => safeKey(item.locationId, "locationId"));
      ledger.schemaVersion = ENGINE_SCHEMA_VERSION;
      ledger.revision = Number(ledger.revision ?? 0) + 1;
      ledger.updatedAt = timestamp;
      await writeJson(statePath, ledger);
      return {
        projectId: normalizeProjectId(projectId),
        chapter: number,
        bodySha256: binding.bodySha256,
        revision: ledger.revision,
        updatedCounts: { characters: characters.length, knowledge: knowledge.length, inventory: inventory.length, locations: locations.length },
        path: "story/dynamic/state.json"
      };
    });
  }

  async dynamicStateContext({ projectId, characterIds = [], knowledgeKeys = [], itemIds = [], locationIds = [] }) {
    const projectDir = await this.requireProject(projectId);
    const ledger = await readJsonOr(resolveInside(projectDir, "story/dynamic/state.json"), dynamicStateTemplate());
    const select = (collection, ids) => {
      if (!Array.isArray(ids) || ids.length === 0) return collection;
      const result = {};
      for (const rawId of ids) {
        const id = safeKey(rawId, "dynamic state id");
        if (collection[id] !== undefined) result[id] = collection[id];
      }
      return result;
    };
    return {
      projectId: normalizeProjectId(projectId),
      revision: ledger.revision ?? 0,
      characters: select(ledger.characters ?? {}, characterIds),
      knowledge: select(ledger.knowledge ?? {}, knowledgeKeys),
      inventory: select(ledger.inventory ?? {}, itemIds),
      locations: select(ledger.locations ?? {}, locationIds),
      updatedAt: ledger.updatedAt ?? null
    };
  }

  async memoryRecord({ projectId, records, expectedRevision = null }) {
    const projectDir = await this.requireProject(projectId);
    if (!Array.isArray(records) || records.length < 1 || records.length > 50) throw codedError("INVALID_MEMORY_RECORD_BATCH", "records must contain 1-50 items.");
    return this.withProjectLock(projectDir, async () => {
      await this.recoverPendingTransactionsUnlocked(projectDir);
      const memoryPath = resolveInside(projectDir, "story/memory/index.json");
      const memory = await readJsonOr(memoryPath, memoryTemplate());
      if (expectedRevision !== null && Number(expectedRevision) !== Number(memory.revision ?? 0)) throw codedError("MEMORY_REVISION_MISMATCH", "Memory index changed since it was read.", { expectedRevision, actualRevision: memory.revision ?? 0 });
      const byId = new Map((memory.records ?? []).map((item) => [item.id, item]));
      for (const raw of records) {
        if (!raw || typeof raw !== "object" || Array.isArray(raw)) throw codedError("INVALID_MEMORY_RECORD", "Memory records must be objects.");
        const id = safeKey(raw.id, "memory id");
        const tier = String(raw.tier ?? "long");
        if (!["short", "mid", "long"].includes(tier)) throw codedError("INVALID_MEMORY_TIER", `Unsupported memory tier: ${tier}`, { tier });
        const text = String(raw.text ?? "").trim();
        if (!text || text.length > 20000) throw codedError("INVALID_MEMORY_TEXT", "Memory text must be 1-20000 characters.", { id });
        const chapter = raw.chapter == null ? null : parseChapter(raw.chapter);
        const sourceSha256 = String(raw.sourceSha256 ?? raw.bodySha256 ?? "").trim().toLowerCase();
        if (chapter !== null && !/^[a-f0-9]{64}$/.test(sourceSha256)) throw codedError("MEMORY_BODY_BINDING_REQUIRED", "Memory records associated with a chapter require sourceSha256 or bodySha256.", { id, chapter });
        if (chapter !== null) await this.assertCommittedBodyBinding(projectDir, chapter, sourceSha256);
        const normalized = {
          ...sanitizeForJson(raw, 50000),
          id,
          tier,
          text,
          chapter,
          tags: normalizeStringArray(raw.tags, "memory.tags", 100, 200),
          sourceRef: String(raw.sourceRef ?? (chapter ? `chapter:${chapter}` : "")).trim(),
          sourceSha256: sourceSha256 || null,
          importance: raw.importance === undefined ? 5 : boundedNumber(raw.importance, { label: "memory.importance", min: 0, max: 10 }),
          updatedAt: nowIso()
        };
        byId.set(id, { ...(byId.get(id) ?? {}), ...normalized });
      }
      if (byId.size > this.config.maxMemoryRecords) throw codedError("MEMORY_LIMIT_EXCEEDED", "Memory index exceeds configured record limit.", { maxMemoryRecords: this.config.maxMemoryRecords });
      memory.records = [...byId.values()].sort((left, right) => (left.chapter ?? 999999) - (right.chapter ?? 999999) || left.id.localeCompare(right.id));
      memory.schemaVersion = ENGINE_SCHEMA_VERSION;
      memory.revision = Number(memory.revision ?? 0) + 1;
      memory.updatedAt = nowIso();
      await writeJson(memoryPath, memory);
      return { projectId: normalizeProjectId(projectId), recorded: records.length, totalRecords: memory.records.length, revision: memory.revision, path: "story/memory/index.json" };
    });
  }

  async memorySearch({ projectId, query, tiers = [], tags = [], chapterBefore = null, topK = 8 }) {
    const projectDir = await this.requireProject(projectId);
    const memory = await readJsonOr(resolveInside(projectDir, "story/memory/index.json"), memoryTemplate());
    const queryText = String(query ?? "").trim();
    if (!queryText) throw codedError("MEMORY_QUERY_REQUIRED", "query is required.");
    const tierSet = new Set((tiers ?? []).map(String));
    const tagSet = new Set((tags ?? []).map(String));
    const before = chapterBefore == null ? null : parseChapter(chapterBefore);
    let candidates = (memory.records ?? []).filter((item) => {
      if (tierSet.size && !tierSet.has(item.tier)) return false;
      if (tagSet.size && !(item.tags ?? []).some((tag) => tagSet.has(tag))) return false;
      if (before !== null && item.chapter !== null && item.chapter >= before) return false;
      return true;
    });
    const queryTokens = tokenizeForSearch(queryText);
    const queryFreq = new Map();
    for (const token of queryTokens) queryFreq.set(token, (queryFreq.get(token) ?? 0) + 1);
    const docs = candidates.map((item) => {
      const tokens = tokenizeForSearch(`${item.text}\n${(item.tags ?? []).join(" ")}`);
      const freq = new Map();
      for (const token of tokens) freq.set(token, (freq.get(token) ?? 0) + 1);
      return { item, tokens, freq };
    });
    const df = new Map();
    for (const token of queryFreq.keys()) {
      let count = 0;
      for (const doc of docs) if (doc.freq.has(token)) count += 1;
      df.set(token, count);
    }
    const nowChapter = before ?? Number.MAX_SAFE_INTEGER;
    const scored = docs.map((doc) => {
      let score = 0;
      for (const [token, qf] of queryFreq) {
        const tf = doc.freq.get(token) ?? 0;
        if (!tf) continue;
        const idf = Math.log((docs.length + 1) / ((df.get(token) ?? 0) + 1)) + 1;
        score += (1 + Math.log(tf)) * (1 + Math.log(qf)) * idf;
      }
      const tagBonus = (doc.item.tags ?? []).filter((tag) => tagSet.has(tag)).length * 1.5;
      const importanceBonus = Number(doc.item.importance ?? 5) * 0.05;
      const recencyBonus = doc.item.chapter && nowChapter !== Number.MAX_SAFE_INTEGER ? Math.max(0, 1 - Math.max(0, nowChapter - doc.item.chapter) / 100) * 0.25 : 0;
      return { ...doc.item, score: Math.round((score + tagBonus + importanceBonus + recencyBonus) * 10000) / 10000 };
    }).filter((item) => item.score > 0);
    scored.sort((left, right) => right.score - left.score || Number(right.chapter ?? 0) - Number(left.chapter ?? 0));
    const limit = Math.max(1, Math.min(50, Number(topK ?? 8)));
    return { projectId: normalizeProjectId(projectId), query: queryText, revision: memory.revision ?? 0, candidateCount: candidates.length, results: scored.slice(0, limit) };
  }

  async prepareLogicAudit({ projectId, chapter }) {
    const projectDir = await this.requireProject(projectId);
    const { state, projectConfig, recoveredTransactions } = await this.recoverProjectForRead(projectDir);
    const current = chapter === undefined || chapter === null ? state.nextChapter : parseChapter(chapter);
    const readOptional = async (relativePath, maxChars) => {
      const filePath = resolveInside(projectDir, relativePath);
      return (await exists(filePath)) ? clip(await fs.readFile(filePath, "utf8"), maxChars) : "";
    };
    const graph = await readJsonOr(resolveInside(projectDir, "story/causal-events.json"), { events: [] });
    const relevantEvents = (graph.events ?? []).filter((item) => item.status === "planned" || (item.chapter !== null && item.chapter >= Math.max(1, current - 5) && item.chapter <= current + 2)).slice(-150);
    const recentContinuity = [];
    for (let number = Math.max(1, current - 5); number < current; number += 1) {
      const deltaPath = resolveInside(projectDir, `continuity/deltas/chapter-${padChapter(number)}.json`);
      if (await exists(deltaPath)) recentContinuity.push(await readJson(deltaPath));
    }
    const promises = await this.storyLedgerQuery({ projectId, ledgerType: "promise", chapter: current, horizon: 5, limit: 100 });
    const opposition = await this.storyLedgerQuery({ projectId, ledgerType: "oppositionClock", chapter: current, horizon: 5, limit: 100 });
    const relationships = await this.storyLedgerQuery({ projectId, ledgerType: "relationship", limit: 200 });
    const dynamicState = await this.dynamicStateContext({ projectId });
    return {
      projectId: normalizeProjectId(projectId),
      chapter: current,
      recoveredTransactions,
      worldRules: await readOptional("blueprint/world-rules.md", 10000),
      storyEngine: await readOptional("blueprint/story-engine.md", 6000),
      causalEvents: relevantEvents,
      recentContinuity,
      foreshadowing: await this.foreshadowingDue({ projectId, chapter: current, horizon: 3 }),
      promises,
      oppositionClocks: opposition,
      relationships,
      dynamicState,
      auditContract: {
        categories: projectConfig.quality.requiredAuditCategories,
        requiredCategories: projectConfig.quality.requiredAuditCategories,
        requireCompleteChecks: projectConfig.quality.requireCompleteAuditChecks,
        requiredDecision: "pass|revise|block",
        rule: "A pass decision cannot contain error, block or fatal severity issues.",
        serverLengthGate: {
          metric: "Han characters in trimmed chapter body",
          minimum: projectConfig.writingContract.minHanChars,
          targetMin: projectConfig.writingContract.targetMinHanChars,
          targetMax: projectConfig.writingContract.targetMaxHanChars,
          rule: projectConfig.writingContract.minHanChars > 0 ? `A passing precommit audit and chapter commit require at least ${projectConfig.writingContract.minHanChars} Han characters.` : "Han-character hard minimum is disabled for this project."
        },
        integrityGate: "Commit body SHA-256 must exactly match the body that received the passing precommit audit.",
        qualityGateRequired: projectConfig.quality.requireQualityGate
      }
    };
  }

  async recordChapterAudit({ projectId, chapter, stage = "precommit", decision, content = "", checks = {}, issues = [], summary = "" }) {
    const projectDir = await this.requireProject(projectId);
    const number = parseChapter(chapter);
    if (!["precommit", "postcommit"].includes(stage)) throw codedError("INVALID_AUDIT_STAGE", `Unsupported audit stage: ${stage}`, { stage });
    if (!["pass", "revise", "block"].includes(decision)) throw codedError("INVALID_AUDIT_DECISION", `Unsupported audit decision: ${decision}`, { decision });
    return this.withProjectLock(projectDir, async () => {
      await this.recoverPendingTransactionsUnlocked(projectDir);
      const projectConfig = await this.readProjectConfig(projectDir);
      const trimmedContent = typeof content === "string" ? content.trim() : "";
      if (stage === "precommit" && trimmedContent.length < this.config.minChapterChars) {
        throw codedError("PRECOMMIT_CONTENT_TOO_SHORT", `Precommit audit content must contain at least ${this.config.minChapterChars} raw characters.`, { rawChars: trimmedContent.length, minimumRawChars: this.config.minChapterChars });
      }
      const contentHanChars = countHanChars(trimmedContent);
      const hardMin = projectConfig.writingContract.minHanChars;
      if (stage === "precommit" && hardMin > 0 && contentHanChars < hardMin) {
        throw codedError("CHAPTER_LENGTH_BELOW_MINIMUM", `Precommit body has ${contentHanChars} Han characters; minimum is ${hardMin}.`, { hanChars: contentHanChars, minimumHanChars: hardMin, targetMinHanChars: projectConfig.writingContract.targetMinHanChars });
      }
      if (!checks || typeof checks !== "object" || Array.isArray(checks)) throw codedError("INVALID_AUDIT_CHECKS", "checks must be an object.");
      if (!Array.isArray(issues) || issues.length > 100) throw codedError("INVALID_AUDIT_ISSUES", "issues must be an array of at most 100 items.");
      const normalizedIssues = issues.map((issue) => {
        if (!issue || typeof issue !== "object" || Array.isArray(issue)) throw codedError("INVALID_AUDIT_ISSUE", "audit issue must be an object.");
        if (!LOGIC_AUDIT_CATEGORIES.includes(issue.category)) throw codedError("UNSUPPORTED_AUDIT_CATEGORY", `Unsupported audit category: ${issue.category}`, { category: issue.category });
        const severity = String(issue.severity ?? "note").toLowerCase();
        if (!["note", "warning", "error", "block", "fatal"].includes(severity)) throw codedError("INVALID_AUDIT_SEVERITY", `Unsupported audit severity: ${severity}`, { severity });
        return { category: issue.category, severity, evidence: String(issue.evidence ?? "").trim(), repair: String(issue.repair ?? "").trim() };
      });
      const checkAnalysis = analyzeAuditChecks(checks, projectConfig.quality.requiredAuditCategories, projectConfig.quality.requireCompleteAuditChecks);
      if (decision === "pass" && normalizedIssues.some((item) => BLOCKING_SEVERITIES.has(item.severity))) throw codedError("PASS_AUDIT_HAS_BLOCKING_ISSUES", "A passing audit cannot contain error, block or fatal issues.");
      if (decision === "pass" && projectConfig.quality.requireCompleteAuditChecks && !checkAnalysis.pass) {
        throw codedError("AUDIT_CHECK_COVERAGE_INCOMPLETE", "A passing audit must include all required categories with non-blocking results.", { missing: checkAnalysis.missing, failing: checkAnalysis.failing, coverage: checkAnalysis.coverage });
      }
      const timestamp = nowIso();
      const contentSha256 = trimmedContent ? sha256(trimmedContent) : null;
      const auditId = `audit-ch${padChapter(number)}-${stage}-${timestamp.replace(/[:.]/g, "-")}-${(contentSha256 ?? "none").slice(0, 12)}`;
      const audit = {
        schemaVersion: ENGINE_SCHEMA_VERSION,
        engineVersion: ENGINE_VERSION,
        auditId,
        chapter: number,
        stage,
        decision,
        contentSha256,
        contentChars: trimmedContent.length,
        contentHanChars,
        writingContract: projectConfig.writingContract,
        serverGate: { minHanChars: hardMin, targetMinHanChars: projectConfig.writingContract.targetMinHanChars, targetMaxHanChars: projectConfig.writingContract.targetMaxHanChars, lengthPass: hardMin <= 0 || contentHanChars >= hardMin },
        checks: sanitizeForJson(checks, 200000),
        checkCoverage: checkAnalysis,
        issues: normalizedIssues,
        summary: String(summary).trim(),
        auditedAt: timestamp
      };
      const relativePath = `story/audits/chapter-${padChapter(number)}-${stage}.json`;
      const historyRelativePath = `story/audits/history/chapter-${padChapter(number)}/${auditId}.json`;
      await writeJson(resolveInside(projectDir, historyRelativePath), audit);
      const committed = await this.getCommittedChapterBody(projectDir, number).catch(() => null);
      const staged = Boolean(committed && committed.bodySha256 !== contentSha256);
      if (!staged) await writeJson(resolveInside(projectDir, relativePath), audit);
      return { projectId: normalizeProjectId(projectId), chapter: number, stage, decision, issueCount: normalizedIssues.length, contentChars: trimmedContent.length, contentHanChars, lengthGate: audit.serverGate, checkCoverage: checkAnalysis, contentSha256, auditId, staged, path: staged ? historyRelativePath : relativePath, historyPath: historyRelativePath };
    });
  }

  async recordChapterQuality({ projectId, chapter, content, writerSessionId, continuityReview, readerReview, genreGate, signature, summary = "" }) {
    const projectDir = await this.requireProject(projectId);
    const number = parseChapter(chapter);
    const trimmedContent = assertBodyPayload(content, number, this.config.rejectEmbeddedChapterHeading);
    const bodySha256 = sha256(trimmedContent);
    const writerId = String(writerSessionId ?? "").trim();
    if (!writerId) throw codedError("WRITER_SESSION_REQUIRED", "writerSessionId is required.");
    const continuity = normalizeReviewer(continuityReview, "continuity-auditor", bodySha256);
    const reader = normalizeReviewer(readerReview, "reader-editor", bodySha256);
    if (continuity.reviewerSessionId === writerId || reader.reviewerSessionId === writerId || continuity.reviewerSessionId === reader.reviewerSessionId) {
      throw codedError("REVIEW_SESSION_NOT_INDEPENDENT", "Writer, Continuity Auditor and Reader Editor must use three distinct session IDs.", { writerSessionId: writerId, continuitySessionId: continuity.reviewerSessionId, readerSessionId: reader.reviewerSessionId });
    }
    if (!genreGate || typeof genreGate !== "object" || Array.isArray(genreGate)) throw codedError("GENRE_GATE_REQUIRED", "genreGate must be an object bound to the reviewed chapter body.");
    const normalizedGenre = sanitizeForJson(genreGate, 100000);
    if (normalizedGenre.bodySha256 !== bodySha256) throw codedError("GENRE_GATE_BODY_HASH_MISMATCH", "Genre gate does not match the supplied chapter body.", { expected: bodySha256, actual: normalizedGenre.bodySha256 ?? null });
    const genreHardBlock = normalizedGenre.severeDrift === true || normalizedGenre.hardBlock === true || normalizedGenre.pass === false || normalizedGenre.genrePass === false;
    if (normalizedGenre.pass !== true && normalizedGenre.genrePass !== true) throw codedError("GENRE_GATE_NOT_PASS", "genreGate must explicitly pass.");
    if (!signature || typeof signature !== "object" || Array.isArray(signature)) throw codedError("SIGNATURE_REQUIRED", "signature must be an object bound to the reviewed chapter body.");
    const normalizedSignature = sanitizeForJson(signature, 100000);
    if (normalizedSignature.bodySha256 !== bodySha256) throw codedError("SIGNATURE_BODY_HASH_MISMATCH", "Chapter signature does not match the supplied chapter body.", { expected: bodySha256, actual: normalizedSignature.bodySha256 ?? null });
    if (Object.keys(normalizedSignature).filter((key) => key !== "bodySha256").length === 0) throw codedError("SIGNATURE_CONTENT_REQUIRED", "signature must contain chapter experience or structure evidence.");
    const qualityPass = continuity.pass && reader.pass && !genreHardBlock;
    if (!qualityPass) throw codedError("CHAPTER_QUALITY_GATE_FAILED", "Independent quality gate did not pass.", { continuityPass: continuity.pass, readerPass: reader.pass, genreHardBlock });
    return this.withProjectLock(projectDir, async () => {
      await this.recoverPendingTransactionsUnlocked(projectDir);
      const projectConfig = await this.readProjectConfig(projectDir);
      const hanChars = countHanChars(trimmedContent);
      if (projectConfig.writingContract.minHanChars > 0 && hanChars < projectConfig.writingContract.minHanChars) throw codedError("CHAPTER_LENGTH_BELOW_MINIMUM", "Quality receipt body is below the project hard minimum.", { hanChars, minimumHanChars: projectConfig.writingContract.minHanChars });
      const timestamp = nowIso();
      const qualityId = `quality-ch${padChapter(number)}-${timestamp.replace(/[:.]/g, "-")}-${bodySha256.slice(0, 12)}`;
      const receipt = {
        schemaVersion: ENGINE_SCHEMA_VERSION,
        engineVersion: ENGINE_VERSION,
        qualityId,
        chapter: number,
        bodySha256,
        hanChars,
        writerSessionId: writerId,
        continuityReview: continuity,
        readerReview: reader,
        genreGate: { ...normalizedGenre, bodySha256, hardBlock: genreHardBlock },
        signature: { ...normalizedSignature, bodySha256 },
        qualityPass: true,
        summary: String(summary).trim(),
        recordedAt: timestamp
      };
      const relativePath = `story/quality/chapter-${padChapter(number)}.json`;
      const historyRelativePath = `story/quality/history/chapter-${padChapter(number)}/${qualityId}.json`;
      await writeJson(resolveInside(projectDir, historyRelativePath), receipt);
      const committed = await this.getCommittedChapterBody(projectDir, number).catch(() => null);
      const staged = Boolean(committed && committed.bodySha256 !== bodySha256);
      if (!staged) await writeJson(resolveInside(projectDir, relativePath), receipt);
      return { projectId: normalizeProjectId(projectId), chapter: number, bodySha256, hanChars, qualityPass: true, continuitySessionId: continuity.reviewerSessionId, readerSessionId: reader.reviewerSessionId, qualityId, staged, path: staged ? historyRelativePath : relativePath, historyPath: historyRelativePath };
    });
  }

  async prepareChapter(projectId, { profile = "compact", role = "writer" } = {}) {
    if (!new Set(["compact", "full"]).has(profile)) {
      throw codedError("INVALID_PREPARE_PROFILE", "profile must be compact or full.", { profile });
    }
    if (!new Set(["writer", "continuity-auditor", "reader-editor"]).has(role)) {
      throw codedError("INVALID_PREPARE_ROLE", "role must be writer, continuity-auditor or reader-editor.", { role });
    }
    const projectDir = await this.requireProject(projectId);
    const { project, state, projectConfig, recoveredTransactions } = await this.recoverProjectForRead(projectDir);
    const chapter = state.nextChapter;
    await this.assertPreviousClosureComplete(projectDir, chapter, projectConfig);
    const outlinePath = resolveInside(projectDir, `outlines/chapter-${padChapter(chapter)}.md`);
    if (!(await exists(outlinePath))) return { ready: false, reason: "missing_chapter_outline", chapter, requiredArtifact: { artifactType: "chapter-outline", key: String(chapter) } };
    const readOptional = async (relativePath, maxChars) => {
      const filePath = resolveInside(projectDir, relativePath);
      return (await exists(filePath)) ? clip(await fs.readFile(filePath, "utf8"), maxChars) : "";
    };
    const recent = [];
    for (let number = Math.max(1, chapter - 5); number < chapter; number += 1) {
      const summaryPath = resolveInside(projectDir, `summaries/chapter-${padChapter(number)}.json`);
      const deltaPath = resolveInside(projectDir, `continuity/deltas/chapter-${padChapter(number)}.json`);
      recent.push({ chapter: number, summary: (await exists(summaryPath)) ? await readJson(summaryPath) : null, continuityDelta: (await exists(deltaPath)) ? await readJson(deltaPath) : null });
    }
    const previousChapter = chapter > 1 ? await readOptional(`chapters/chapter-${padChapter(chapter - 1)}.md`, 7000) : "";
    const ideaBank = await readJsonOr(resolveInside(projectDir, "creative/idea-bank.json"), { candidates: [], selectedId: null });
    const selectedIdea = (ideaBank.candidates ?? []).find((item) => item.id === ideaBank.selectedId) ?? null;
    const logicAudit = await this.prepareLogicAudit({ projectId, chapter });
    const signatures = chapter > 1
      ? await this.storyLedgerQuery({ projectId, ledgerType: "chapterSignature", chapter: chapter - 1, limit: 10 })
      : await this.storyLedgerQuery({ projectId, ledgerType: "chapterSignature", limit: 10 });
    const dynamicState = await this.dynamicStateContext({ projectId });
    const shortMemory = await this.memorySearch({ projectId, query: `${project.title} 第${chapter}章 ${await fs.readFile(outlinePath, "utf8")}`, tiers: ["short"], chapterBefore: chapter, topK: 5 }).catch(() => ({ results: [] }));
    const midMemory = await this.memorySearch({ projectId, query: `${project.title} ${project.genre} 主线 人物 关系 当前阶段`, tiers: ["mid"], chapterBefore: chapter, topK: 12 }).catch(() => ({ results: [] }));
    const longMemory = await this.memorySearch({ projectId, query: `${await fs.readFile(outlinePath, "utf8")}`, tiers: ["long"], chapterBefore: chapter, topK: 8 }).catch(() => ({ results: [] }));
    const context = {
      project: { id: project.id, title: project.title, genre: project.genre, premise: project.premise },
      projectConfig,
      recoveredTransactions,
      chapter,
      chapterOutline: await fs.readFile(outlinePath, "utf8"),
      structureFingerprint: await readOptional("analysis/structure-fingerprint.md", 7000),
      creativeBrief: await readOptional("blueprint/creative-brief.md", 5000),
      selectedIdea,
      storyEngine: await readOptional("blueprint/story-engine.md", 7000),
      noveltyReport: await readOptional("blueprint/novelty-report.md", 5000),
      premise: await readOptional("blueprint/premise.md", 5000),
      world: await readOptional("blueprint/world.md", 9000),
      worldRules: await readOptional("blueprint/world-rules.md", 9000),
      characters: await readOptional("blueprint/characters.md", 9000),
      masterOutline: await readOptional("blueprint/master-outline.md", 9000),
      writingRules: await readOptional("blueprint/writing-rules.md", 6000),
      previousChapter,
      recent,
      causalEvents: logicAudit.causalEvents,
      foreshadowing: logicAudit.foreshadowing,
      promises: logicAudit.promises,
      relationships: logicAudit.relationships,
      oppositionClocks: logicAudit.oppositionClocks,
      dynamicState,
      memory: { short: shortMemory.results, mid: midMemory.results, long: longMemory.results },
      recentSignatures: signatures.entries,
      auditContract: logicAudit.auditContract,
      auditRequired: projectConfig.quality.requireChapterAudit,
      qualityGateRequired: projectConfig.quality.requireQualityGate
    };
    const compactSections = {
      writer: [
        `# 《${project.title}》第${chapter}章 Writer 精简资料包`,
        "\n## 本章篇幅与类型规格\n", JSON.stringify({ writingContract: projectConfig.writingContract, genreProfile: projectConfig.genreProfile }, null, 2),
        "\n## 本章大纲\n", context.chapterOutline,
        "\n## 创作发动机与写作规则\n", context.storyEngine, context.writingRules,
        "\n## 世界硬规则与当前人物\n", context.worldRules, context.characters,
        "\n## 上一章末尾\n", context.previousChapter,
        "\n## 最近摘要与当前状态\n", JSON.stringify({ recent, dynamicState }, null, 2),
        "\n## 本章相关记忆与长线任务\n", JSON.stringify({ memory: context.memory, causalEvents: context.causalEvents, foreshadowing: context.foreshadowing, promises: context.promises, relationships: context.relationships, oppositionClocks: context.oppositionClocks }, null, 2),
        "\n## Writer 随稿审计契约\n", JSON.stringify(context.auditContract, null, 2)
      ],
      "continuity-auditor": [
        `# 《${project.title}》第${chapter}章 Continuity Auditor 精简资料包`,
        "\n## 本章大纲与上一章末尾\n", context.chapterOutline, context.previousChapter,
        "\n## 世界硬规则与当前状态\n", context.worldRules, JSON.stringify(dynamicState, null, 2),
        "\n## 最近连续性变化\n", JSON.stringify(recent, null, 2),
        "\n## 因果、伏笔、承诺、关系与对手压力\n", JSON.stringify({ causalEvents: context.causalEvents, foreshadowing: context.foreshadowing, promises: context.promises, relationships: context.relationships, oppositionClocks: context.oppositionClocks }, null, 2)
      ],
      "reader-editor": [
        `# 《${project.title}》第${chapter}章 Reader Editor 精简资料包`,
        "\n## 本章类型体验与篇幅规格\n", JSON.stringify({ writingContract: projectConfig.writingContract, genreProfile: projectConfig.genreProfile }, null, 2),
        "\n## 本章大纲\n", context.chapterOutline,
        "\n## 创作核心与写作规则\n", context.creativeBrief, context.storyEngine, context.writingRules,
        "\n## 最近章节节奏指纹\n", JSON.stringify(context.recentSignatures, null, 2)
      ]
    };
    if (profile === "compact") {
      return { ready: true, chapter, profile, role, packet: compactSections[role].join("\n") };
    }
    const packet = [
      `# 《${project.title}》第${chapter}章写作资料包`,
      "\n## 项目级写作规格\n", JSON.stringify(projectConfig, null, 2),
      "\n## 本章大纲\n", context.chapterOutline,
      "\n## 创作核心与选定创意\n", context.creativeBrief, JSON.stringify(context.selectedIdea, null, 2), context.storyEngine,
      "\n## 原创性压力测试\n", context.noveltyReport,
      "\n## 原创作品设定\n", context.premise, context.world, context.characters,
      "\n## 世界硬规则、代价与限制\n", context.worldRules,
      "\n## 全书主线\n", context.masterOutline,
      "\n## 写作规则\n", context.writingRules,
      "\n## 上一章末尾\n", context.previousChapter,
      "\n## 最近章节摘要与连续性变化\n", JSON.stringify(recent, null, 2),
      "\n## 当前人物、知识、物品与地点状态\n", JSON.stringify(dynamicState, null, 2),
      "\n## 三级历史记忆候选\n", JSON.stringify(context.memory, null, 2),
      "\n## 最近章节指纹\n", JSON.stringify(context.recentSignatures, null, 2),
      "\n## 相关因果事件\n", JSON.stringify(context.causalEvents, null, 2),
      "\n## 本章伏笔任务与逾期提醒\n", JSON.stringify(context.foreshadowing, null, 2),
      "\n## Promise、关系与对手压力\n", JSON.stringify({ promises: context.promises, relationships: context.relationships, oppositionClocks: context.oppositionClocks }, null, 2),
      "\n## 提交前逻辑与质量审计契约\n", JSON.stringify(context.auditContract, null, 2)
    ].join("\n");
    return { ready: true, chapter, profile, role, packet, context };
  }

  async buildForeshadowingLedgerAfterChanges(projectDir, chapter, bodySha256, changes, timestamp) {
    const ledgerPath = resolveInside(projectDir, "story/foreshadowing.json");
    const ledger = await readJsonOr(ledgerPath, { schemaVersion: ENGINE_SCHEMA_VERSION, revision: 0, entries: [] });
    if (changes.length === 0) return { ledger, changed: false };
    const next = structuredClone(ledger);
    for (const change of changes) {
      let entry = (next.entries ?? []).find((item) => item.id === change.id);
      if (!entry) {
        entry = {
          id: change.id,
          type: "plot",
          status: "planned",
          plantedChapter: null,
          reinforceChapters: [],
          payoffWindow: null,
          prerequisites: [],
          surfaceMeaning: "",
          hiddenMeaning: "",
          readerAwareness: "unknown",
          characterAwareness: {},
          payoffPlan: "",
          notes: "",
          createdFromContinuityDelta: true
        };
        next.entries.push(entry);
      }
      if (change.action === "open") {
        entry.status = "open";
        entry.plantedChapter ??= chapter;
      } else if (change.action === "advance") {
        entry.status = "advanced";
        entry.lastAdvancedChapter = chapter;
      } else if (["close", "payoff"].includes(change.action)) {
        entry.status = "paid";
        entry.payoffChapter = chapter;
      } else if (change.action === "cancel") {
        entry.status = "cancelled";
        entry.cancelledChapter = chapter;
      }
      if (change.note) {
        const marker = `[chapter:${chapter}|action:${change.action}] ${change.note}`;
        const lines = String(entry.notes ?? "").split("\n").filter(Boolean);
        if (!lines.includes(marker)) lines.push(marker);
        entry.notes = lines.join("\n");
      }
      entry.updatedAt = timestamp;
      entry.sourceChapter = chapter;
      entry.bodySha256 = bodySha256;
    }
    next.entries.sort((left, right) => (left.plantedChapter ?? 999999) - (right.plantedChapter ?? 999999) || left.id.localeCompare(right.id));
    next.schemaVersion = ENGINE_SCHEMA_VERSION;
    next.revision = Number(next.revision ?? 0) + 1;
    next.updatedAt = timestamp;
    return { ledger: next, changed: true };
  }

  async verifyAuditForBody(projectDir, chapter, bodySha256, hanChars, projectConfig) {
    if (!projectConfig.quality.requireChapterAudit) return null;
    const auditRelativePath = `story/audits/chapter-${padChapter(chapter)}-precommit.json`;
    const auditPath = resolveInside(projectDir, auditRelativePath);
    let resolvedRelativePath = auditRelativePath;
    let audit = await readJsonOr(auditPath, null);
    if (!audit || audit.contentSha256 !== bodySha256) {
      const historyDirRelative = `story/audits/history/chapter-${padChapter(chapter)}`;
      const historyDir = resolveInside(projectDir, historyDirRelative);
      const names = (await fs.readdir(historyDir).catch(() => [])).filter((name) => name.endsWith(".json")).sort().reverse();
      audit = null;
      for (const name of names) {
        const candidate = await readJson(resolveInside(historyDir, name));
        if (candidate.stage === "precommit" && candidate.contentSha256 === bodySha256) {
          audit = candidate;
          resolvedRelativePath = `${historyDirRelative}/${name}`;
          break;
        }
      }
    }
    if (!audit) throw codedError("PRECOMMIT_AUDIT_NOT_FOUND", `Chapter ${chapter} requires a passing precommit audit for the supplied body.`, { chapter, bodySha256 });
    if (audit.decision !== "pass") throw codedError("PRECOMMIT_AUDIT_NOT_PASS", `Chapter ${chapter} audit decision is ${audit.decision}, not pass.`, { chapter, decision: audit.decision });
    const blockingIssues = Array.isArray(audit.issues) ? audit.issues.filter((item) => BLOCKING_SEVERITIES.has(String(item?.severity ?? "").toLowerCase())) : [];
    if (blockingIssues.length > 0) throw codedError("PRECOMMIT_AUDIT_HAS_BLOCKING_ISSUES", `Chapter ${chapter} passing audit contains ${blockingIssues.length} blocking issue(s).`, { chapter, blockingIssueCount: blockingIssues.length });
    if (audit.contentSha256 !== bodySha256) throw codedError("PRECOMMIT_BODY_HASH_MISMATCH", `Chapter ${chapter} content does not match the passing precommit audit.`, { chapter, auditedSha256: audit.contentSha256 ?? null, commitSha256: bodySha256 });
    const hardMin = projectConfig.writingContract.minHanChars;
    if (hardMin > 0 && (audit.contentHanChars !== hanChars || audit.serverGate?.lengthPass !== true || hanChars < hardMin)) {
      throw codedError("PRECOMMIT_LENGTH_PROOF_MISMATCH", `Chapter ${chapter} precommit audit does not contain a matching server-side length proof.`, { chapter, auditHanChars: audit.contentHanChars ?? null, commitHanChars: hanChars, minimumHanChars: hardMin });
    }
    if (projectConfig.quality.requireCompleteAuditChecks) {
      const analysis = audit.checkCoverage ?? analyzeAuditChecks(audit.checks ?? {}, projectConfig.quality.requiredAuditCategories, true);
      if (!analysis.pass) throw codedError("PRECOMMIT_AUDIT_CHECKS_INCOMPLETE", "Stored precommit audit does not cover all required categories.", { missing: analysis.missing, failing: analysis.failing });
    }
    return { ...audit, relativePath: resolvedRelativePath };
  }

  async verifyQualityForBody(projectDir, chapter, bodySha256, projectConfig) {
    if (!projectConfig.quality.requireQualityGate) return null;
    const qualityRelativePath = `story/quality/chapter-${padChapter(chapter)}.json`;
    const qualityPath = resolveInside(projectDir, qualityRelativePath);
    let resolvedRelativePath = qualityRelativePath;
    let quality = await readJsonOr(qualityPath, null);
    if (!quality || quality.bodySha256 !== bodySha256) {
      const historyDirRelative = `story/quality/history/chapter-${padChapter(chapter)}`;
      const historyDir = resolveInside(projectDir, historyDirRelative);
      const names = (await fs.readdir(historyDir).catch(() => [])).filter((name) => name.endsWith(".json")).sort().reverse();
      quality = null;
      for (const name of names) {
        const candidate = await readJson(resolveInside(historyDir, name));
        if (candidate.bodySha256 === bodySha256) {
          quality = candidate;
          resolvedRelativePath = `${historyDirRelative}/${name}`;
          break;
        }
      }
    }
    if (!quality) throw codedError("QUALITY_RECEIPT_NOT_FOUND", `Chapter ${chapter} requires a passing independent quality receipt for the supplied body.`, { chapter, bodySha256 });
    if (quality.qualityPass !== true) throw codedError("QUALITY_RECEIPT_NOT_PASS", `Chapter ${chapter} quality receipt is not pass.`, { chapter });
    if (quality.bodySha256 !== bodySha256) throw codedError("QUALITY_BODY_HASH_MISMATCH", `Chapter ${chapter} quality receipt does not match the commit body.`, { expected: bodySha256, actual: quality.bodySha256 });
    if (!quality.continuityReview?.pass || !quality.readerReview?.pass || quality.genreGate?.hardBlock === true) throw codedError("QUALITY_RECEIPT_INVALID", "Stored quality receipt no longer satisfies required gates.", { chapter });
    const ids = [quality.writerSessionId, quality.continuityReview?.reviewerSessionId, quality.readerReview?.reviewerSessionId];
    if (ids.some((item) => !item) || new Set(ids).size !== 3) throw codedError("QUALITY_REVIEW_SESSION_INVALID", "Stored quality receipt does not contain three independent session IDs.", { chapter, ids });
    return { ...quality, relativePath: resolvedRelativePath };
  }

  initialClosureRecord(chapter, bodySha256, continuityDelta, timestamp, foreshadowingApplied, requestId = "") {
    const operations = {};
    const map = {
      causalEvents: "causalEvents",
      foreshadowing: "foreshadowing",
      promisePayoff: "promises",
      relationshipGraph: "relationships",
      oppositionClocks: "oppositionClocks",
      chapterSignature: "signature",
      dynamicState: "dynamicState",
      memoryIndex: "memoryRecords"
    };
    for (const operation of CLOSURE_OPERATIONS) {
      const payloadKey = map[operation];
      const present = continuityDelta[payloadKey] !== undefined && continuityDelta[payloadKey] !== null;
      if (operation === "foreshadowing" && foreshadowingApplied) {
        operations[operation] = { status: "completed", evidence: "story/foreshadowing.json", reason: "Applied atomically during commit." };
      } else if (present) {
        operations[operation] = { status: "pending", evidence: null, reason: "Continuity delta supplied; durable ledger update still required." };
      } else {
        operations[operation] = { status: "pending", evidence: null, reason: "An explicit completed or justified skipped decision is required." };
      }
    }
    const pending = Object.values(operations).filter((item) => item.status === "pending").length;
    return {
      schemaVersion: ENGINE_SCHEMA_VERSION,
      chapter,
      chapterNo: chapter,
      requestId: String(requestId ?? "").trim() || null,
      bodySha256,
      status: pending === 0 ? "complete" : "pending",
      operations,
      createdAt: timestamp,
      updatedAt: timestamp
    };
  }

  async commitChapter({ projectId, expectedChapter, title, content, summary, continuityDelta = {}, requestId = "" }) {
    const projectDir = await this.requireProject(projectId);
    const chapter = parseChapter(expectedChapter);
    const normalizedTitle = normalizeTitle(title, chapter, this.config.rejectEmbeddedChapterHeading);
    const trimmedContent = assertBodyPayload(content, chapter, this.config.rejectEmbeddedChapterHeading);
    if (trimmedContent.length < this.config.minChapterChars) throw codedError("CHAPTER_CONTENT_TOO_SHORT", `Chapter content must contain at least ${this.config.minChapterChars} raw characters.`, { rawChars: trimmedContent.length, minimumRawChars: this.config.minChapterChars });
    const normalizedSummary = String(summary ?? "").trim();
    if (!normalizedSummary) throw codedError("CHAPTER_SUMMARY_REQUIRED", "Chapter summary is required.");
    if (!continuityDelta || typeof continuityDelta !== "object" || Array.isArray(continuityDelta)) throw codedError("INVALID_CONTINUITY_DELTA", "continuityDelta must be a JSON object.");
    const normalizedDelta = sanitizeForJson(continuityDelta, this.config.maxContinuityDeltaChars);
    const foreshadowingChanges = normalizeForeshadowingChanges(normalizedDelta.foreshadowing);
    const bodySha256 = sha256(trimmedContent);
    const hanChars = countHanChars(trimmedContent);
    const requestString = String(requestId ?? "").trim();
    if (!requestString) throw codedError("REQUEST_ID_REQUIRED", "requestId is required for a crash-recoverable chapter commit.");
    const requestHash = requestString ? sha256(requestString) : "";
    const requestRelativePath = requestHash ? `requests/commits/${requestHash}.json` : "";
    const fingerprint = requestFingerprint({ chapter, title: normalizedTitle, content: trimmedContent, summary: normalizedSummary, continuityDelta: normalizedDelta, operation: "commit" });

    return this.withProjectLock(projectDir, async () => {
      await this.initializeOptionalLedgers(projectDir);
      await this.recoverPendingTransactionsUnlocked(projectDir);
      if (requestRelativePath && await exists(resolveInside(projectDir, requestRelativePath))) {
        const previous = await readJson(resolveInside(projectDir, requestRelativePath));
        if (previous.requestFingerprint !== fingerprint) throw codedError("IDEMPOTENCY_PAYLOAD_MISMATCH", "The same requestId was already used with a different chapter payload.", { chapter, requestId: requestString });
        return { ...previous.result, idempotentReplay: true };
      }
      const state = await this.reconcileStateUnlocked(projectDir);
      if (state.nextChapter !== chapter) throw codedError("EXPECTED_CHAPTER_MISMATCH", `Expected next chapter is ${state.nextChapter}, not ${chapter}.`, { expected: state.nextChapter, provided: chapter });
      const projectConfig = await this.readProjectConfig(projectDir);
      await this.assertPreviousClosureComplete(projectDir, chapter, projectConfig);
      const hardMin = projectConfig.writingContract.minHanChars;
      if (hardMin > 0 && hanChars < hardMin) throw codedError("CHAPTER_LENGTH_BELOW_MINIMUM", `Chapter ${chapter} has ${hanChars} Han characters; minimum is ${hardMin}.`, { chapter, hanChars, minimumHanChars: hardMin, targetMinHanChars: projectConfig.writingContract.targetMinHanChars, targetMaxHanChars: projectConfig.writingContract.targetMaxHanChars });
      const audit = await this.verifyAuditForBody(projectDir, chapter, bodySha256, hanChars, projectConfig);
      const quality = await this.verifyQualityForBody(projectDir, chapter, bodySha256, projectConfig);
      const chapterRelativePath = `chapters/chapter-${padChapter(chapter)}.md`;
      if (await exists(resolveInside(projectDir, chapterRelativePath))) throw codedError("CHAPTER_ALREADY_EXISTS", `Chapter ${chapter} already exists.`, { chapter });
      const timestamp = nowIso();
      const transactionId = `commit-ch${padChapter(chapter)}-${sha256(`${normalizeProjectId(projectId)}:${chapter}:${requestString || bodySha256}:${fingerprint}`).slice(0, 24)}`;
      const chapterMarkdown = `# 第${chapter}章 ${normalizedTitle}\n\n${trimmedContent}\n`;
      const foreshadowingResult = await this.buildForeshadowingLedgerAfterChanges(projectDir, chapter, bodySha256, foreshadowingChanges, timestamp);
      const closure = this.initialClosureRecord(chapter, bodySha256, normalizedDelta, timestamp, foreshadowingResult.changed, requestString);
      const nextState = {
        ...state,
        schemaVersion: ENGINE_SCHEMA_VERSION,
        revision: Number(state.revision ?? 0) + 1,
        phase: "writing",
        integrityStatus: "clean",
        lastCommittedChapter: chapter,
        nextChapter: chapter + 1,
        updatedAt: timestamp
      };
      const result = {
        projectId: normalizeProjectId(projectId),
        confirmed: true,
        chapter,
        chapterNo: chapter,
        requestId: requestString,
        title: normalizedTitle,
        path: chapterRelativePath,
        nextChapter: chapter + 1,
        audit: audit?.relativePath ?? null,
        quality: quality?.relativePath ?? null,
        closure: `story/closures/chapter-${padChapter(chapter)}.json`,
        contentHanChars: hanChars,
        contentSha256: bodySha256,
        bodySha256,
        serverGate: {
          engineVersion: ENGINE_VERSION,
          minHanChars: hardMin,
          targetMinHanChars: projectConfig.writingContract.targetMinHanChars,
          targetMaxHanChars: projectConfig.writingContract.targetMaxHanChars,
          lengthPass: hardMin <= 0 || hanChars >= hardMin,
          auditVerified: projectConfig.quality.requireChapterAudit ? Boolean(audit) : false,
          qualityVerified: projectConfig.quality.requireQualityGate ? Boolean(quality) : false,
          crashRecoverableTransaction: true,
          requestIdPayloadBound: Boolean(requestString)
        },
        transactionId,
        committedAt: timestamp,
        idempotentReplay: false
      };
      const writes = [];
      writes.push(await this.buildTransactionWrite(projectDir, chapterRelativePath, chapterMarkdown, null));
      writes.push(await this.buildTransactionWrite(projectDir, `summaries/chapter-${padChapter(chapter)}.json`, `${JSON.stringify({ schemaVersion: ENGINE_SCHEMA_VERSION, chapter, title: normalizedTitle, summary: normalizedSummary, bodySha256, hanChars, committedAt: timestamp }, null, 2)}\n`, null));
      writes.push(await this.buildTransactionWrite(projectDir, `continuity/deltas/chapter-${padChapter(chapter)}.json`, `${JSON.stringify({ ...normalizedDelta, schemaVersion: ENGINE_SCHEMA_VERSION, chapter, bodySha256, committedAt: timestamp }, null, 2)}\n`, null));
      writes.push(await this.buildTransactionWrite(projectDir, `chapters/meta/chapter-${padChapter(chapter)}.json`, `${JSON.stringify({ schemaVersion: ENGINE_SCHEMA_VERSION, chapter, revision: 1, title: normalizedTitle, bodySha256, hanChars, auditId: audit?.auditId ?? null, qualityId: quality?.qualityId ?? null, requestId: requestString || null, committedAt: timestamp, updatedAt: timestamp }, null, 2)}\n`, null));
      writes.push(await this.buildTransactionWrite(projectDir, `story/closures/chapter-${padChapter(chapter)}.json`, `${JSON.stringify(closure, null, 2)}\n`, null));
      if (foreshadowingResult.changed) writes.push(await this.buildTransactionWrite(projectDir, "story/foreshadowing.json", `${JSON.stringify(foreshadowingResult.ledger, null, 2)}\n`));
      writes.push(await this.buildTransactionWrite(projectDir, "state.json", `${JSON.stringify(nextState, null, 2)}\n`));
      writes.push(await this.buildTransactionWrite(projectDir, `receipts/commits/chapter-${padChapter(chapter)}.json`, `${JSON.stringify(result, null, 2)}\n`, null));
      if (requestRelativePath) writes.push(await this.buildTransactionWrite(projectDir, requestRelativePath, `${JSON.stringify({ schemaVersion: ENGINE_SCHEMA_VERSION, requestId: requestString, requestFingerprint: fingerprint, result, recordedAt: timestamp }, null, 2)}\n`, null));
      const manifest = await this.prepareTransaction(projectDir, { transactionId, kind: "chapter-commit", projectId: normalizeProjectId(projectId), chapter, requestId: requestString || null, payloadFingerprint: fingerprint, writes, result });
      return this.applyTransactionUnlocked(projectDir, manifest);
    });
  }

  async commitStatus({ projectId, chapter = null, requestId = "" }) {
    const projectDir = await this.requireProject(projectId);
    const requestString = String(requestId ?? "").trim();
    const number = chapter == null ? null : parseChapter(chapter);
    return this.withProjectLock(projectDir, async () => {
      const recoveredTransactions = await this.recoverPendingTransactionsUnlocked(projectDir);
      if (requestString) {
        const requestPath = resolveInside(projectDir, `requests/commits/${sha256(requestString)}.json`);
        if (await exists(requestPath)) {
          const receipt = await readJson(requestPath);
          if (number !== null && Number(receipt.result?.chapter) !== number) {
            return { status: "not_found", source: "request-chapter-mismatch", recoveredTransactions, chapter: number, chapterNo: number, requestId: requestString };
          }
          return { status: "committed", source: "request-receipt", idempotent: true, recoveredTransactions, ...receipt.result };
        }
      }
      if (number !== null) {
        const receiptPath = resolveInside(projectDir, `receipts/commits/chapter-${padChapter(number)}.json`);
        if (await exists(receiptPath)) {
          const receipt = await readJson(receiptPath);
          if (requestString && receipt.requestId !== requestString) {
            return { status: "not_found", source: "request-mismatch", recoveredTransactions, chapter: number, chapterNo: number, requestId: requestString };
          }
          return { status: "committed", source: "chapter-receipt", recoveredTransactions, ...receipt };
        }
        const chapterPath = resolveInside(projectDir, `chapters/chapter-${padChapter(number)}.md`);
        if (await exists(chapterPath)) {
          const parsed = await this.getCommittedChapterBody(projectDir, number);
          return { status: "chapter_file_present_without_receipt", source: "chapter-file", recoveredTransactions, chapter: number, contentSha256: parsed.bodySha256, contentHanChars: parsed.hanChars };
        }
      }
      const pending = [];
      for (const name of (await fs.readdir(resolveInside(projectDir, "transactions/pending"))).filter((item) => item.endsWith(".json"))) {
        const manifest = await readJson(resolveInside(projectDir, `transactions/pending/${name}`));
        if ((number === null || manifest.chapter === number) && (!requestString || manifest.requestId === requestString)) pending.push({ transactionId: manifest.transactionId, status: manifest.status, chapter: manifest.chapter, appliedWrites: manifest.appliedWrites, totalWrites: manifest.writes?.length ?? 0 });
      }
      return { status: pending.length ? "pending" : "not_found", projectId: normalizeProjectId(projectId), chapter: number, requestId: requestString || null, recoveredTransactions, pending };
    });
  }

  async assertPreviousClosureComplete(projectDir, chapter, projectConfig) {
    const number = parseChapter(chapter);
    if (!projectConfig.quality.requireClosureReceipt || number <= 1) return null;
    const previousChapter = number - 1;
    if (previousChapter < projectConfig.enforcement.closureFromChapter) return null;
    const relativePath = `story/closures/chapter-${padChapter(previousChapter)}.json`;
    const closurePath = resolveInside(projectDir, relativePath);
    if (!(await exists(closurePath))) {
      throw codedError("PREVIOUS_CHAPTER_CLOSURE_NOT_FOUND", `Chapter ${previousChapter} closure receipt is required before chapter ${number}.`, { previousChapter, chapter: number });
    }
    const closure = await readJson(closurePath);
    if (closure.status !== "complete") {
      throw codedError("PREVIOUS_CHAPTER_CLOSURE_INCOMPLETE", `Chapter ${previousChapter} closure is ${closure.status}, not complete.`, {
        previousChapter,
        chapter: number,
        closureStatus: closure.status,
        pendingOperations: Object.entries(closure.operations ?? {}).filter(([, value]) => value?.status !== "completed" && value?.status !== "skipped").map(([key]) => key)
      });
    }
    return { ...closure, relativePath };
  }

  async assertClosureEvidenceBinding(projectDir, operation, evidence, chapter, bodySha256) {
    const evidencePath = resolveInside(projectDir, evidence);
    let data;
    try {
      data = await readJson(evidencePath);
    } catch {
      throw codedError("CLOSURE_EVIDENCE_INVALID", `${operation} evidence must be readable JSON.`, { operation, evidence });
    }
    const matches = (item) => item && typeof item === "object"
      && Number(item.sourceChapter ?? item.chapter ?? 0) === chapter
      && String(item.bodySha256 ?? item.sourceSha256 ?? "").toLowerCase() === bodySha256;
    let candidates = [];
    if (operation === "causalEvents") candidates = data.events ?? [];
    else if (["foreshadowing", "promisePayoff", "relationshipGraph", "oppositionClocks", "chapterSignature"].includes(operation)) candidates = data.entries ?? [];
    else if (operation === "dynamicState") candidates = Object.values({ ...(data.characters ?? {}), ...(data.knowledge ?? {}), ...(data.inventory ?? {}), ...(data.locations ?? {}) });
    else if (operation === "memoryIndex") candidates = data.records ?? [];
    if (!matches(data) && !candidates.some(matches)) {
      throw codedError("CLOSURE_EVIDENCE_BODY_BINDING_MISMATCH", `${operation} evidence is not bound to chapter ${chapter} and its current body hash.`, { operation, evidence, chapter, bodySha256 });
    }
  }

  async recordChapterClosure({ projectId, chapter, bodySha256, operations = {}, note = "" }) {
    const projectDir = await this.requireProject(projectId);
    const number = parseChapter(chapter);
    const normalizedHash = String(bodySha256 ?? "").trim().toLowerCase();
    if (!/^[a-f0-9]{64}$/.test(normalizedHash)) throw codedError("INVALID_BODY_HASH", "bodySha256 must be a SHA-256 hex string.");
    if (!operations || typeof operations !== "object" || Array.isArray(operations)) throw codedError("INVALID_CLOSURE_OPERATIONS", "operations must be an object.");
    const unsupported = Object.keys(operations).filter((key) => !CLOSURE_OPERATIONS.includes(key));
    if (unsupported.length) throw codedError("UNSUPPORTED_CLOSURE_OPERATION", "operations contains unsupported closure operation names.", { unsupported, supported: CLOSURE_OPERATIONS });

    return this.withProjectLock(projectDir, async () => {
      await this.recoverPendingTransactionsUnlocked(projectDir);
      await this.assertCommittedBodyBinding(projectDir, number, normalizedHash);
      const relativePath = `story/closures/chapter-${padChapter(number)}.json`;
      const closurePath = resolveInside(projectDir, relativePath);
      const timestamp = nowIso();
      const meta = await readJsonOr(resolveInside(projectDir, `chapters/meta/chapter-${padChapter(number)}.json`), {});
      const closure = await readJsonOr(closurePath, this.initialClosureRecord(number, normalizedHash, {}, timestamp, false, meta.requestId));
      if (closure.bodySha256 && closure.bodySha256 !== normalizedHash) {
        throw codedError("CLOSURE_BODY_HASH_MISMATCH", `Chapter ${number} closure receipt is bound to a different body.`, { expected: normalizedHash, actual: closure.bodySha256 });
      }
      closure.operations ??= {};
      for (const operation of CLOSURE_OPERATIONS) {
        closure.operations[operation] ??= { status: "skipped", evidence: null, reason: "No applicable durable update was declared." };
      }
      for (const [operation, raw] of Object.entries(operations)) {
        const value = typeof raw === "string" ? { status: raw } : raw;
        if (!value || typeof value !== "object" || Array.isArray(value)) throw codedError("INVALID_CLOSURE_OPERATION", `${operation} closure update must be an object or status string.`, { operation });
        const status = String(value.status ?? "").trim().toLowerCase();
        if (!['pending', 'completed', 'skipped', 'failed'].includes(status)) throw codedError("INVALID_CLOSURE_STATUS", `Unsupported closure status: ${status}`, { operation, status });
        const evidence = value.evidence == null ? null : String(value.evidence).trim().replaceAll("\\", "/");
        const reason = String(value.reason ?? value.note ?? "").trim();
        if (status === "completed" && !evidence) throw codedError("CLOSURE_EVIDENCE_REQUIRED", `${operation} requires evidence when marked completed.`, { operation });
        if (status === "skipped" && !reason) throw codedError("CLOSURE_SKIP_REASON_REQUIRED", `${operation} requires a reason when marked skipped.`, { operation });
        if (evidence) {
          const evidencePath = resolveInside(projectDir, evidence);
          if (!(await exists(evidencePath))) throw codedError("CLOSURE_EVIDENCE_NOT_FOUND", `Closure evidence does not exist: ${evidence}`, { operation, evidence });
          if (status === "completed") await this.assertClosureEvidenceBinding(projectDir, operation, evidence, number, normalizedHash);
        }
        closure.operations[operation] = { status, evidence, reason, updatedAt: timestamp };
      }
      const values = Object.values(closure.operations);
      closure.schemaVersion = ENGINE_SCHEMA_VERSION;
      closure.engineVersion = ENGINE_VERSION;
      closure.bodySha256 = normalizedHash;
      closure.status = values.some((item) => item.status === "failed") ? "failed" : values.some((item) => item.status === "pending") ? "pending" : "complete";
      closure.note = String(note ?? "").trim();
      closure.updatedAt = timestamp;
      if (closure.status === "complete") closure.completedAt = timestamp;
      else delete closure.completedAt;
      await writeJson(closurePath, closure);
      return {
        projectId: normalizeProjectId(projectId),
        confirmed: closure.status === "complete",
        closurePass: closure.status === "complete",
        chapter: number,
        chapterNo: number,
        requestId: closure.requestId ?? meta.requestId ?? null,
        bodySha256: normalizedHash,
        status: closure.status,
        pendingOperations: Object.entries(closure.operations).filter(([, value]) => value.status === "pending").map(([key]) => key),
        failedOperations: Object.entries(closure.operations).filter(([, value]) => value.status === "failed").map(([key]) => key),
        path: relativePath,
        closure
      };
    });
  }

  async chapterClosureStatus({ projectId, chapter }) {
    const projectDir = await this.requireProject(projectId);
    const number = parseChapter(chapter);
    return this.withProjectLock(projectDir, async () => {
      await this.initializeOptionalLedgers(projectDir);
      const recoveredTransactions = await this.recoverPendingTransactionsUnlocked(projectDir);
      await this.reconcileStateUnlocked(projectDir);
      const relativePath = `story/closures/chapter-${padChapter(number)}.json`;
      const closurePath = resolveInside(projectDir, relativePath);
      if (!(await exists(closurePath))) return { projectId: normalizeProjectId(projectId), chapter: number, found: false, status: "not_found", recoveredTransactions };
      const closure = await readJson(closurePath);
      const current = await this.getCommittedChapterBody(projectDir, number).catch(() => null);
      return {
        projectId: normalizeProjectId(projectId),
        chapter: number,
        chapterNo: number,
        requestId: closure.requestId ?? null,
        confirmed: closure.status === "complete" && Boolean(current && current.bodySha256 === closure.bodySha256),
        closurePass: closure.status === "complete" && Boolean(current && current.bodySha256 === closure.bodySha256),
        found: true,
        status: closure.status,
        bodyBindingValid: Boolean(current && current.bodySha256 === closure.bodySha256),
        pendingOperations: Object.entries(closure.operations ?? {}).filter(([, value]) => value?.status === "pending").map(([key]) => key),
        failedOperations: Object.entries(closure.operations ?? {}).filter(([, value]) => value?.status === "failed").map(([key]) => key),
        recoveredTransactions,
        path: relativePath,
        closure
      };
    });
  }

  async readChapter({ projectId, chapter }) {
    const projectDir = await this.requireProject(projectId);
    const number = parseChapter(chapter);
    return this.withProjectLock(projectDir, async () => {
      await this.initializeOptionalLedgers(projectDir);
      const recoveredTransactions = await this.recoverPendingTransactionsUnlocked(projectDir);
      await this.reconcileStateUnlocked(projectDir);
      const chapterRelativePath = `chapters/chapter-${padChapter(number)}.md`;
      const chapterPath = resolveInside(projectDir, chapterRelativePath);
      if (!(await exists(chapterPath))) return { projectId: normalizeProjectId(projectId), found: false, chapter: number, recoveredTransactions };
      const markdown = await fs.readFile(chapterPath, "utf8");
      const parsed = parseChapterMarkdown(markdown, number);
      const meta = await readJsonOr(resolveInside(projectDir, `chapters/meta/chapter-${padChapter(number)}.json`), null);
      const summary = await readJsonOr(resolveInside(projectDir, `summaries/chapter-${padChapter(number)}.json`), null);
      const continuityDelta = await readJsonOr(resolveInside(projectDir, `continuity/deltas/chapter-${padChapter(number)}.json`), null);
      const closure = await readJsonOr(resolveInside(projectDir, `story/closures/chapter-${padChapter(number)}.json`), null);
      return {
        projectId: normalizeProjectId(projectId),
        found: true,
        chapter: number,
        title: parsed.title,
        body: parsed.body,
        content: markdown,
        contentSha256: parsed.bodySha256,
        contentHanChars: parsed.hanChars,
        revision: meta?.revision ?? 1,
        meta,
        summary,
        continuityDelta,
        closure,
        recoveredTransactions,
        path: chapterRelativePath
      };
    });
  }

  async reviseChapter({
    projectId,
    chapter,
    title,
    content,
    summary = "",
    continuityDelta = {},
    changeNote = "",
    expectedBodySha256 = null,
    expectedRevision = null,
    requestId = ""
  }) {
    const projectDir = await this.requireProject(projectId);
    const number = parseChapter(chapter);
    const normalizedBody = assertBodyPayload(content, number, this.config.rejectEmbeddedChapterHeading);
    if (normalizedBody.length < this.config.minChapterChars) throw codedError("REVISED_CONTENT_TOO_SHORT", `Revised content must contain at least ${this.config.minChapterChars} raw characters.`, { rawChars: normalizedBody.length, minimumRawChars: this.config.minChapterChars });
    if (!continuityDelta || typeof continuityDelta !== "object" || Array.isArray(continuityDelta)) throw codedError("INVALID_CONTINUITY_DELTA", "continuityDelta must be a JSON object.");
    const normalizedDelta = sanitizeForJson(continuityDelta, this.config.maxContinuityDeltaChars);
    const requestString = String(requestId ?? "").trim();
    if (!requestString) throw codedError("REQUEST_ID_REQUIRED", "requestId is required for a crash-recoverable chapter revision.");
    const requestRelativePath = requestString ? `requests/revisions/${sha256(requestString)}.json` : "";

    return this.withProjectLock(projectDir, async () => {
      await this.initializeOptionalLedgers(projectDir);
      await this.recoverPendingTransactionsUnlocked(projectDir);
      const current = await this.getCommittedChapterBody(projectDir, number);
      const currentMetaPath = resolveInside(projectDir, `chapters/meta/chapter-${padChapter(number)}.json`);
      const currentMeta = await readJsonOr(currentMetaPath, {
        schemaVersion: ENGINE_SCHEMA_VERSION,
        chapter: number,
        revision: 1,
        title: current.title,
        bodySha256: current.bodySha256,
        hanChars: current.hanChars,
        committedAt: null,
        updatedAt: null
      });
      const currentRevision = Number(currentMeta.revision ?? 1);
      const projectConfig = await this.readProjectConfig(projectDir);
      const normalizedTitle = title === undefined || title === null || String(title).trim() === ""
        ? current.title
        : normalizeTitle(title, number, this.config.rejectEmbeddedChapterHeading);
      const newBodySha256 = sha256(normalizedBody);
      const newHanChars = countHanChars(normalizedBody);
      const hardMin = projectConfig.writingContract.minHanChars;
      if (hardMin > 0 && newHanChars < hardMin) throw codedError("CHAPTER_LENGTH_BELOW_MINIMUM", `Revised chapter ${number} has ${newHanChars} Han characters; minimum is ${hardMin}.`, { chapter: number, hanChars: newHanChars, minimumHanChars: hardMin });
      const existingSummary = await readJsonOr(resolveInside(projectDir, `summaries/chapter-${padChapter(number)}.json`), null);
      const normalizedSummary = String(summary ?? "").trim() || String(existingSummary?.summary ?? "").trim();
      if (!normalizedSummary) throw codedError("CHAPTER_SUMMARY_REQUIRED", "A revision must preserve or supply a chapter summary.");
      const fingerprint = requestFingerprint({ chapter: number, title: normalizedTitle, content: normalizedBody, summary: normalizedSummary, continuityDelta: normalizedDelta, operation: "revise" });
      if (requestRelativePath && await exists(resolveInside(projectDir, requestRelativePath))) {
        const previous = await readJson(resolveInside(projectDir, requestRelativePath));
        if (previous.requestFingerprint !== fingerprint) throw codedError("IDEMPOTENCY_PAYLOAD_MISMATCH", "The same revision requestId was used with a different payload.", { chapter: number, requestId: requestString });
        return { ...previous.result, idempotentReplay: true };
      }
      if (projectConfig.quality.requireRevisionCas) {
        if (!expectedBodySha256 && expectedRevision === null) throw codedError("REVISION_CAS_REQUIRED", "Revision requires expectedBodySha256 or expectedRevision.", { chapter: number, currentBodySha256: current.bodySha256, currentRevision });
        if (expectedBodySha256 && String(expectedBodySha256).toLowerCase() !== current.bodySha256) throw codedError("REVISION_BODY_CAS_MISMATCH", "Chapter body changed since it was read.", { chapter: number, expectedBodySha256, actualBodySha256: current.bodySha256 });
        if (expectedRevision !== null && Number(expectedRevision) !== currentRevision) throw codedError("REVISION_NUMBER_CAS_MISMATCH", "Chapter revision changed since it was read.", { chapter: number, expectedRevision, actualRevision: currentRevision });
      }
      let audit = null;
      if (projectConfig.quality.requireRevisionAudit) {
        audit = await this.verifyAuditForBody(projectDir, number, newBodySha256, newHanChars, {
          ...projectConfig,
          quality: { ...projectConfig.quality, requireChapterAudit: true }
        });
      }
      const quality = projectConfig.quality.requireQualityGate ? await this.verifyQualityForBody(projectDir, number, newBodySha256, projectConfig) : null;
      const timestamp = nowIso();
      const nextRevision = currentRevision + 1;
      const versionStamp = timestamp.replace(/[:.]/g, "-");
      const backupRelativePath = `versions/chapters/chapter-${padChapter(number)}/rev-${String(currentRevision).padStart(4, "0")}-${versionStamp}.md`;
      const chapterRelativePath = `chapters/chapter-${padChapter(number)}.md`;
      const chapterMarkdown = `# 第${number}章 ${normalizedTitle}\n\n${normalizedBody}\n`;
      const state = await this.reconcileStateUnlocked(projectDir);
      const nextState = {
        ...state,
        schemaVersion: ENGINE_SCHEMA_VERSION,
        revision: Number(state.revision ?? 0) + 1,
        integrityStatus: "review-required",
        lastRevisedChapter: number,
        lastRevisionBodySha256: newBodySha256,
        updatedAt: timestamp
      };
      const closure = this.initialClosureRecord(number, newBodySha256, normalizedDelta, timestamp, false, requestString);
      const transactionId = `revise-ch${padChapter(number)}-r${String(nextRevision).padStart(4, "0")}-${sha256(`${requestString || newBodySha256}:${fingerprint}`).slice(0, 20)}`;
      const result = {
        projectId: normalizeProjectId(projectId),
        confirmed: true,
        chapter: number,
        chapterNo: number,
        requestId: requestString,
        title: normalizedTitle,
        revision: nextRevision,
        previousBodySha256: current.bodySha256,
        contentSha256: newBodySha256,
        bodySha256: newBodySha256,
        contentHanChars: newHanChars,
        audit: audit ? `story/audits/chapter-${padChapter(number)}-precommit.json` : null,
        quality: quality ? `story/quality/chapter-${padChapter(number)}.json` : null,
        backup: backupRelativePath,
        closure: `story/closures/chapter-${padChapter(number)}.json`,
        integrityStatus: nextState.integrityStatus,
        transactionId,
        revisedAt: timestamp,
        idempotentReplay: false
      };
      const writes = [];
      writes.push(await this.buildTransactionWrite(projectDir, backupRelativePath, current.rawMarkdown, null));
      writes.push(await this.buildTransactionWrite(projectDir, chapterRelativePath, chapterMarkdown, await this.currentFileFingerprint(resolveInside(projectDir, chapterRelativePath))));
      writes.push(await this.buildTransactionWrite(projectDir, `summaries/chapter-${padChapter(number)}.json`, `${JSON.stringify({ schemaVersion: ENGINE_SCHEMA_VERSION, chapter: number, title: normalizedTitle, summary: normalizedSummary, bodySha256: newBodySha256, hanChars: newHanChars, revision: nextRevision, revisedAt: timestamp, changeNote: String(changeNote ?? "").trim() }, null, 2)}\n`));
      writes.push(await this.buildTransactionWrite(projectDir, `continuity/deltas/chapter-${padChapter(number)}.json`, `${JSON.stringify({ ...normalizedDelta, schemaVersion: ENGINE_SCHEMA_VERSION, chapter: number, bodySha256: newBodySha256, revision: nextRevision, revisedAt: timestamp }, null, 2)}\n`));
      writes.push(await this.buildTransactionWrite(projectDir, `chapters/meta/chapter-${padChapter(number)}.json`, `${JSON.stringify({ ...currentMeta, schemaVersion: ENGINE_SCHEMA_VERSION, chapter: number, revision: nextRevision, title: normalizedTitle, bodySha256: newBodySha256, hanChars: newHanChars, auditId: audit?.auditId ?? null, qualityId: quality?.qualityId ?? null, previousBodySha256: current.bodySha256, requestId: requestString || null, updatedAt: timestamp }, null, 2)}\n`));
      if (audit) {
        const { relativePath: _auditSource, ...auditRecord } = audit;
        writes.push(await this.buildTransactionWrite(projectDir, `story/audits/chapter-${padChapter(number)}-precommit.json`, `${JSON.stringify(auditRecord, null, 2)}\n`));
      }
      if (quality) {
        const { relativePath: _qualitySource, ...qualityRecord } = quality;
        writes.push(await this.buildTransactionWrite(projectDir, `story/quality/chapter-${padChapter(number)}.json`, `${JSON.stringify(qualityRecord, null, 2)}\n`));
      }
      writes.push(await this.buildTransactionWrite(projectDir, `story/closures/chapter-${padChapter(number)}.json`, `${JSON.stringify(closure, null, 2)}\n`));
      writes.push(await this.buildTransactionWrite(projectDir, "state.json", `${JSON.stringify(nextState, null, 2)}\n`));
      writes.push(await this.buildTransactionWrite(projectDir, `receipts/revisions/chapter-${padChapter(number)}-rev-${String(nextRevision).padStart(4, "0")}.json`, `${JSON.stringify({ ...result, changeNote: String(changeNote ?? "").trim(), requestId: requestString || null }, null, 2)}\n`, null));
      if (requestRelativePath) writes.push(await this.buildTransactionWrite(projectDir, requestRelativePath, `${JSON.stringify({ schemaVersion: ENGINE_SCHEMA_VERSION, requestId: requestString, requestFingerprint: fingerprint, result, recordedAt: timestamp }, null, 2)}\n`, null));
      const manifest = await this.prepareTransaction(projectDir, { transactionId, kind: "chapter-revision", projectId: normalizeProjectId(projectId), chapter: number, requestId: requestString || null, payloadFingerprint: fingerprint, writes, result });
      return this.applyTransactionUnlocked(projectDir, manifest);
    });
  }

  async projectIntegrityCheck({ projectId, repair = false }) {
    const projectDir = await this.requireProject(projectId);
    return this.withProjectLock(projectDir, async () => {
      await this.ensureProjectDirectories(projectDir);
      await this.initializeOptionalLedgers(projectDir);
      const recoveredTransactions = await this.recoverPendingTransactionsUnlocked(projectDir);
      const errors = [];
      const warnings = [];
      const repairs = [];
      const numbers = await listChapterNumbers(projectDir);
      for (let index = 0; index < numbers.length; index += 1) {
        if (numbers[index] !== index + 1) errors.push({ code: "CHAPTER_SEQUENCE_GAP", chapter: numbers[index], message: `Expected chapter ${index + 1}, found ${numbers[index]}.` });
      }
      const projectConfig = await this.readProjectConfig(projectDir);
      const chapterBindings = new Map();
      for (const number of numbers) {
        let parsed;
        try {
          parsed = await this.getCommittedChapterBody(projectDir, number);
          chapterBindings.set(number, parsed.bodySha256);
        } catch (error) {
          errors.push({ code: error.code ?? "CHAPTER_PARSE_FAILED", chapter: number, message: error.message });
          continue;
        }
        const relativeBase = `chapter-${padChapter(number)}`;
        const summaryPath = resolveInside(projectDir, `summaries/${relativeBase}.json`);
        const deltaPath = resolveInside(projectDir, `continuity/deltas/${relativeBase}.json`);
        const metaPath = resolveInside(projectDir, `chapters/meta/${relativeBase}.json`);
        const closurePath = resolveInside(projectDir, `story/closures/${relativeBase}.json`);
        const receiptPath = resolveInside(projectDir, `receipts/commits/${relativeBase}.json`);
        const summary = await readJsonOr(summaryPath, null);
        const delta = await readJsonOr(deltaPath, null);
        let meta = await readJsonOr(metaPath, null);
        const closure = await readJsonOr(closurePath, null);
        const receipt = await readJsonOr(receiptPath, null);
        const metadataEnforced = number >= projectConfig.enforcement.metadataFromChapter;
        if (!summary) (metadataEnforced ? errors : warnings).push({ code: "SUMMARY_MISSING", chapter: number, path: `summaries/${relativeBase}.json`, legacyGrandfathered: !metadataEnforced });
        else if (summary.bodySha256 && summary.bodySha256 !== parsed.bodySha256) errors.push({ code: "SUMMARY_BODY_HASH_MISMATCH", chapter: number, expected: parsed.bodySha256, actual: summary.bodySha256 });
        if (!delta) (metadataEnforced ? errors : warnings).push({ code: "CONTINUITY_DELTA_MISSING", chapter: number, path: `continuity/deltas/${relativeBase}.json`, legacyGrandfathered: !metadataEnforced });
        else if (delta.bodySha256 && delta.bodySha256 !== parsed.bodySha256) errors.push({ code: "CONTINUITY_BODY_HASH_MISMATCH", chapter: number, expected: parsed.bodySha256, actual: delta.bodySha256 });
        if (!meta) {
          if (repair) {
            meta = { schemaVersion: ENGINE_SCHEMA_VERSION, chapter: number, revision: 1, title: parsed.title, bodySha256: parsed.bodySha256, hanChars: parsed.hanChars, migratedAt: nowIso(), updatedAt: nowIso() };
            await writeJson(metaPath, meta);
            repairs.push({ code: "META_CREATED", chapter: number, path: `chapters/meta/${relativeBase}.json` });
          } else (metadataEnforced ? errors : warnings).push({ code: "CHAPTER_META_MISSING", chapter: number, path: `chapters/meta/${relativeBase}.json`, legacyGrandfathered: !metadataEnforced });
        }
        if (meta) {
          if (meta.bodySha256 !== parsed.bodySha256) errors.push({ code: "META_BODY_HASH_MISMATCH", chapter: number, expected: parsed.bodySha256, actual: meta.bodySha256 });
          if (Number(meta.hanChars) !== parsed.hanChars) errors.push({ code: "META_HAN_COUNT_MISMATCH", chapter: number, expected: parsed.hanChars, actual: meta.hanChars });
        }
        const currentRevision = Number(meta?.revision ?? 1);
        const closureEnforced = projectConfig.quality.requireClosureReceipt && (number >= projectConfig.enforcement.closureFromChapter || currentRevision > 1);
        if (!closure) {
          (closureEnforced ? errors : warnings).push({ code: "CLOSURE_MISSING", chapter: number, path: `story/closures/${relativeBase}.json`, legacyGrandfathered: !closureEnforced });
        } else {
          if (closure.bodySha256 !== parsed.bodySha256) errors.push({ code: "CLOSURE_BODY_HASH_MISMATCH", chapter: number, expected: parsed.bodySha256, actual: closure.bodySha256 });
          if (closureEnforced && closure.status !== "complete") errors.push({ code: "CLOSURE_INCOMPLETE", chapter: number, status: closure.status });
          else if (closure.status !== "complete") warnings.push({ code: "CLOSURE_INCOMPLETE", chapter: number, status: closure.status });
        }
        if (currentRevision > 1) {
          const revisionReceiptPath = `receipts/revisions/${relativeBase}-rev-${String(currentRevision).padStart(4, "0")}.json`;
          const revisionReceipt = await readJsonOr(resolveInside(projectDir, revisionReceiptPath), null);
          if (!revisionReceipt) errors.push({ code: "REVISION_RECEIPT_MISSING", chapter: number, revision: currentRevision, path: revisionReceiptPath });
          else if (revisionReceipt.contentSha256 !== parsed.bodySha256) errors.push({ code: "REVISION_RECEIPT_HASH_MISMATCH", chapter: number, revision: currentRevision, expected: parsed.bodySha256, actual: revisionReceipt.contentSha256 });
          if (!receipt) warnings.push({ code: "ORIGINAL_COMMIT_RECEIPT_MISSING", chapter: number, path: `receipts/commits/${relativeBase}.json` });
        } else {
          if (!receipt) warnings.push({ code: "COMMIT_RECEIPT_MISSING", chapter: number, path: `receipts/commits/${relativeBase}.json` });
          else if (receipt.contentSha256 && receipt.contentSha256 !== parsed.bodySha256) errors.push({ code: "COMMIT_RECEIPT_HASH_MISMATCH", chapter: number, expected: parsed.bodySha256, actual: receipt.contentSha256 });
        }
        const hardMin = projectConfig.writingContract.minHanChars;
        const lengthEnforced = number >= projectConfig.enforcement.lengthFromChapter || currentRevision > 1;
        if (lengthEnforced && hardMin > 0 && parsed.hanChars < hardMin) errors.push({ code: "CHAPTER_BELOW_CURRENT_MINIMUM", chapter: number, hanChars: parsed.hanChars, minimumHanChars: hardMin });
        else if (!lengthEnforced && hardMin > 0 && parsed.hanChars < hardMin) warnings.push({ code: "LEGACY_CHAPTER_BELOW_CURRENT_MINIMUM", chapter: number, hanChars: parsed.hanChars, minimumHanChars: hardMin, legacyGrandfathered: true });
        const auditEnforced = projectConfig.quality.requireChapterAudit && (number >= projectConfig.enforcement.auditFromChapter || currentRevision > 1);
        if (auditEnforced) {
          const audit = await readJsonOr(resolveInside(projectDir, `story/audits/${relativeBase}-precommit.json`), null);
          if (!audit) errors.push({ code: "AUDIT_MISSING", chapter: number });
          else if (audit.contentSha256 !== parsed.bodySha256 || audit.decision !== "pass") errors.push({ code: "AUDIT_BINDING_INVALID", chapter: number, decision: audit.decision, bodySha256: audit.contentSha256 });
        }
        const qualityEnforced = projectConfig.quality.requireQualityGate && (number >= projectConfig.enforcement.qualityFromChapter || currentRevision > 1);
        if (qualityEnforced) {
          const quality = await readJsonOr(resolveInside(projectDir, `story/quality/${relativeBase}.json`), null);
          if (!quality) errors.push({ code: "QUALITY_RECEIPT_MISSING", chapter: number });
          else if (quality.bodySha256 !== parsed.bodySha256 || quality.qualityPass !== true) errors.push({ code: "QUALITY_BINDING_INVALID", chapter: number, qualityPass: quality.qualityPass, bodySha256: quality.bodySha256 });
        }
      }

      const dynamic = await readJsonOr(resolveInside(projectDir, "story/dynamic/state.json"), dynamicStateTemplate());
      for (const [collectionName, collection] of Object.entries({ characters: dynamic.characters ?? {}, knowledge: dynamic.knowledge ?? {}, inventory: dynamic.inventory ?? {}, locations: dynamic.locations ?? {} })) {
        for (const [id, item] of Object.entries(collection)) {
          if (!item.chapter || !item.bodySha256) continue;
          const currentHash = chapterBindings.get(Number(item.chapter));
          if (!currentHash) warnings.push({ code: "DYNAMIC_SOURCE_CHAPTER_MISSING", collection: collectionName, id, chapter: item.chapter });
          else if (currentHash !== item.bodySha256) errors.push({ code: "DYNAMIC_STATE_STALE_BINDING", collection: collectionName, id, chapter: item.chapter, expected: currentHash, actual: item.bodySha256 });
        }
      }
      const memory = await readJsonOr(resolveInside(projectDir, "story/memory/index.json"), memoryTemplate());
      for (const record of memory.records ?? []) {
        if (!record.chapter) continue;
        if (!record.sourceSha256) {
          errors.push({ code: "MEMORY_BODY_BINDING_MISSING", id: record.id, chapter: record.chapter });
          continue;
        }
        const currentHash = chapterBindings.get(Number(record.chapter));
        if (!currentHash) warnings.push({ code: "MEMORY_SOURCE_CHAPTER_MISSING", id: record.id, chapter: record.chapter });
        else if (currentHash !== record.sourceSha256) errors.push({ code: "MEMORY_STALE_BINDING", id: record.id, chapter: record.chapter, expected: currentHash, actual: record.sourceSha256 });
      }
      const causal = await readJsonOr(resolveInside(projectDir, "story/causal-events.json"), { events: [] });
      for (const event of causal.events ?? []) {
        if (!["occurred", "cancelled"].includes(event.status)) continue;
        if (!event.chapter || !event.bodySha256) errors.push({ code: "CAUSAL_BODY_BINDING_MISSING", id: event.eventId });
        else if (chapterBindings.get(Number(event.chapter)) !== event.bodySha256) errors.push({ code: "CAUSAL_STALE_BINDING", id: event.eventId, chapter: event.chapter, expected: chapterBindings.get(Number(event.chapter)) ?? null, actual: event.bodySha256 });
      }
      const foreshadowing = await readJsonOr(resolveInside(projectDir, "story/foreshadowing.json"), { entries: [] });
      for (const entry of foreshadowing.entries ?? []) {
        if (entry.status === "planned") continue;
        if (!entry.sourceChapter || !entry.bodySha256) errors.push({ code: "FORESHADOW_BODY_BINDING_MISSING", id: entry.id });
        else if (chapterBindings.get(Number(entry.sourceChapter)) !== entry.bodySha256) errors.push({ code: "FORESHADOW_STALE_BINDING", id: entry.id, chapter: entry.sourceChapter, expected: chapterBindings.get(Number(entry.sourceChapter)) ?? null, actual: entry.bodySha256 });
      }
      for (const ledgerType of Object.keys(LEDGER_FILES)) {
        const ledger = await readJsonOr(resolveInside(projectDir, LEDGER_FILES[ledgerType]), ledgerTemplate());
        for (const entry of ledger.entries ?? []) {
          if (ledgerType === "promise" && entry.status === "planned") continue;
          if (ledgerType === "oppositionClock" && entry.status === "planned") continue;
          const chapter = Number(entry.sourceChapter ?? entry.chapter ?? entry.endChapter ?? entry.checkpointChapter ?? 0);
          if (!chapter || !entry.bodySha256) {
            errors.push({ code: "LEDGER_BODY_BINDING_MISSING", ledgerType, id: entry.id });
            continue;
          }
          const currentHash = chapterBindings.get(chapter);
          if (!currentHash) warnings.push({ code: "LEDGER_SOURCE_CHAPTER_MISSING", ledgerType, id: entry.id, chapter });
          else if (currentHash !== entry.bodySha256) errors.push({ code: "LEDGER_STALE_BINDING", ledgerType, id: entry.id, chapter, expected: currentHash, actual: entry.bodySha256 });
        }
      }

      const statePath = resolveInside(projectDir, "state.json");
      const state = await readJson(statePath);
      const last = numbers.at(-1) ?? 0;
      if (state.lastCommittedChapter !== last || state.nextChapter !== last + 1) {
        if (repair) {
          state.lastCommittedChapter = last;
          state.nextChapter = last + 1;
          state.revision = Number(state.revision ?? 0) + 1;
          state.updatedAt = nowIso();
          repairs.push({ code: "STATE_PROGRESS_REPAIRED", lastCommittedChapter: last, nextChapter: last + 1 });
        } else errors.push({ code: "STATE_PROGRESS_MISMATCH", expectedLastCommittedChapter: last, actualLastCommittedChapter: state.lastCommittedChapter, expectedNextChapter: last + 1, actualNextChapter: state.nextChapter });
      }
      const pendingTransactions = (await fs.readdir(resolveInside(projectDir, "transactions/pending"))).filter((name) => name.endsWith(".json"));
      if (pendingTransactions.length) errors.push({ code: "PENDING_TRANSACTIONS_REMAIN", transactions: pendingTransactions });
      const integrityPass = errors.length === 0;
      state.integrityStatus = integrityPass ? (warnings.length ? "warning" : "clean") : "error";
      state.lastIntegrityCheckAt = nowIso();
      state.lastIntegrityErrorCount = errors.length;
      state.lastIntegrityWarningCount = warnings.length;
      if (repair || state.integrityStatus !== (await readJson(statePath)).integrityStatus) await writeJson(statePath, state);
      return {
        projectId: normalizeProjectId(projectId),
        engineVersion: ENGINE_VERSION,
        checkedChapters: numbers.length,
        integrityPass,
        status: state.integrityStatus,
        errorCount: errors.length,
        warningCount: warnings.length,
        repairCount: repairs.length,
        recoveredTransactions,
        errors,
        warnings,
        repairs,
        checkedAt: state.lastIntegrityCheckAt
      };
    });
  }
}
