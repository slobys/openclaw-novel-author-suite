import { createHash, randomUUID } from "node:crypto";
import { promises as fs } from "node:fs";
import path from "node:path";

export const PROJECT_ID_PATTERN = /^[a-z0-9][a-z0-9_-]{1,63}$/i;
export const SAFE_KEY_PATTERN = /^[a-z0-9][a-z0-9_.:-]{0,127}$/i;

export function nowIso() {
  return new Date().toISOString();
}
export function padChapter(value) {
  return String(value).padStart(4, "0");
}

export function parseChapter(value) {
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed < 1 || parsed > 999999) {
    throw codedError("INVALID_CHAPTER_NUMBER", `Invalid chapter number: ${value}`, { value });
  }
  return parsed;
}

export function safeKey(value, label = "key", pattern = SAFE_KEY_PATTERN) {
  if (typeof value !== "string" || !pattern.test(value)) {
    throw codedError("INVALID_SAFE_KEY", `Invalid ${label}; use letters, numbers, underscore, hyphen, dot, colon only.`, { label, value });
  }
  return value;
}

export function normalizeProjectId(projectId) {
  if (typeof projectId !== "string" || !PROJECT_ID_PATTERN.test(projectId)) {
    throw codedError("INVALID_PROJECT_ID", "projectId must be 2-64 letters, numbers, underscore or hyphen.", { projectId });
  }
  return projectId.toLowerCase();
}

export function resolveInside(root, ...parts) {
  const resolvedRoot = path.resolve(root);
  const target = path.resolve(resolvedRoot, ...parts);
  if (target !== resolvedRoot && !target.startsWith(`${resolvedRoot}${path.sep}`)) {
    throw codedError("PATH_ESCAPE_BLOCKED", "Resolved path escapes the configured project root.", { root: resolvedRoot, target });
  }
  return target;
}

export function isInside(candidate, root) {
  const resolvedCandidate = path.resolve(candidate);
  const resolvedRoot = path.resolve(root);
  return resolvedCandidate === resolvedRoot || resolvedCandidate.startsWith(`${resolvedRoot}${path.sep}`);
}

export async function exists(filePath) {
  try {
    await fs.access(filePath);
    return true;
  } catch {
    return false;
  }
}

export async function readTextOr(filePath, fallback = "") {
  return (await exists(filePath)) ? fs.readFile(filePath, "utf8") : fallback;
}

export async function readJson(filePath) {
  let raw;
  try {
    raw = await fs.readFile(filePath, "utf8");
  } catch (error) {
    throw codedError("JSON_READ_FAILED", `Unable to read JSON file: ${filePath}`, { filePath, cause: error.message }, error);
  }
  try {
    return JSON.parse(raw);
  } catch (error) {
    throw codedError("JSON_CORRUPT", `Invalid JSON file: ${filePath}`, { filePath, cause: error.message }, error);
  }
}

export async function readJsonOr(filePath, fallback) {
  return (await exists(filePath)) ? readJson(filePath) : structuredClone(fallback);
}

async function fsyncDirectory(directory) {
  try {
    const handle = await fs.open(directory, "r");
    try {
      await handle.sync();
    } finally {
      await handle.close();
    }
  } catch {
    // Best effort. Some filesystems do not support fsync on directories.
  }
}

export async function atomicWrite(filePath, content, options = {}) {
  const directory = path.dirname(filePath);
  await fs.mkdir(directory, { recursive: true });
  const tempPath = `${filePath}.${process.pid}.${randomUUID()}.tmp`;
  const handle = await fs.open(tempPath, "wx", options.mode ?? 0o600);
  try {
    await handle.writeFile(content, "utf8");
    await handle.sync();
  } finally {
    await handle.close();
  }
  try {
    await fs.rename(tempPath, filePath);
    await fsyncDirectory(directory);
  } catch (error) {
    await fs.unlink(tempPath).catch(() => {});
    throw error;
  }
}

export async function writeJson(filePath, value) {
  await atomicWrite(filePath, `${JSON.stringify(value, null, 2)}\n`);
}

export function sha256(value) {
  return createHash("sha256").update(String(value)).digest("hex");
}

export function countHanChars(value) {
  if (typeof value !== "string" || !value) return 0;
  return (value.match(/\p{Script=Han}/gu) ?? []).length;
}

export function stableStringify(value) {
  const seen = new WeakSet();
  const normalize = (item) => {
    if (item === null || typeof item !== "object") return item;
    if (seen.has(item)) throw codedError("CIRCULAR_JSON", "Circular structures are not supported.");
    seen.add(item);
    if (Array.isArray(item)) {
      const result = item.map((entry) => normalize(entry));
      seen.delete(item);
      return result;
    }
    const result = {};
    for (const key of Object.keys(item).sort()) {
      const entry = item[key];
      if (entry !== undefined) result[key] = normalize(entry);
    }
    seen.delete(item);
    return result;
  };
  return JSON.stringify(normalize(value));
}

export function codedError(code, message, details = {}, cause = undefined) {
  const error = new Error(`${code}: ${message}`, cause ? { cause } : undefined);
  error.code = code;
  error.details = details;
  return error;
}

export function assertObject(value, label) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw codedError("INVALID_OBJECT", `${label} must be a JSON object.`, { label });
  }
  return value;
}

export function normalizeStringArray(value, label, maxItems = 100, maxLength = 2000) {
  if (value === undefined || value === null) return [];
  if (!Array.isArray(value) || value.length > maxItems || value.some((item) => typeof item !== "string" || item.length > maxLength)) {
    throw codedError("INVALID_STRING_ARRAY", `${label} must be an array of at most ${maxItems} strings, each at most ${maxLength} characters.`, { label });
  }
  return [...new Set(value.map((item) => item.trim()).filter(Boolean))];
}

export function normalizeChapterList(value, label) {
  if (value === undefined || value === null) return [];
  if (!Array.isArray(value) || value.length > 200) {
    throw codedError("INVALID_CHAPTER_LIST", `${label} must be an array of at most 200 chapter numbers.`, { label });
  }
  return [...new Set(value.map((item) => parseChapter(item)))].sort((left, right) => left - right);
}

export function clip(value, maxChars) {
  if (!value) return "";
  if (value.length <= maxChars) return value;
  const head = Math.floor(maxChars * 0.65);
  const tail = maxChars - head;
  return `${value.slice(0, head)}\n\n[...内容已按上下文预算省略...]\n\n${value.slice(-tail)}`;
}

export function sanitizeForJson(value, maxChars = 200000) {
  const encoded = stableStringify(value);
  if (encoded.length > maxChars) {
    throw codedError("JSON_PAYLOAD_TOO_LARGE", `JSON payload exceeds ${maxChars} characters.`, { actualChars: encoded.length, maxChars });
  }
  return JSON.parse(encoded);
}

export function firstNonEmptyLine(value) {
  return String(value ?? "").split(/\r?\n/).map((line) => line.trim()).find(Boolean) ?? "";
}

export function parseChapterMarkdown(markdown, chapter) {
  const normalized = String(markdown ?? "").replace(/\r\n?/g, "\n");
  const [firstLine = "", ...rest] = normalized.split("\n");
  const headingMatch = /^#\s*第\s*([0-9〇零一二三四五六七八九十百千万两]+)\s*章\s*(.*)$/u.exec(firstLine.trim());
  const title = headingMatch ? headingMatch[2].trim() : "";
  let body = headingMatch ? rest.join("\n") : normalized;
  body = body.replace(/^\s+/, "").replace(/\s+$/, "");
  return {
    chapter,
    title,
    body,
    bodySha256: sha256(body),
    hanChars: countHanChars(body),
    rawMarkdown: normalized
  };
}

export function tokenizeForSearch(text) {
  const normalized = String(text ?? "").toLowerCase().normalize("NFKC");
  const tokens = [];
  for (const word of normalized.match(/[a-z0-9_:-]{2,}/g) ?? []) tokens.push(word);
  const hanRuns = normalized.match(/\p{Script=Han}+/gu) ?? [];
  for (const run of hanRuns) {
    if (run.length === 1) tokens.push(run);
    for (const width of [2, 3]) {
      for (let index = 0; index + width <= run.length; index += 1) {
        tokens.push(run.slice(index, index + width));
      }
    }
  }
  return tokens;
}

export function boundedNumber(value, { label, min, max, integer = false, fallback = undefined }) {
  if (value === undefined || value === null || value === "") {
    if (fallback !== undefined) return fallback;
    throw codedError("MISSING_NUMBER", `${label} is required.`, { label });
  }
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed < min || parsed > max || (integer && !Number.isInteger(parsed))) {
    throw codedError("INVALID_NUMBER", `${label} must be ${integer ? "an integer" : "a number"} between ${min} and ${max}.`, { label, value });
  }
  return parsed;
}

export function isPidAlive(pid) {
  if (!Number.isInteger(pid) || pid <= 0) return false;
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    return error?.code === "EPERM";
  }
}
