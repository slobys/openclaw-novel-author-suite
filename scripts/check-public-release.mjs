import fs from "node:fs/promises";
import path from "node:path";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const forbiddenSegments = new Set([".git", "node_modules", "memory", "exports", ".novel-runtime", "__pycache__", "data", "novels"]);
const forbiddenSuffixes = [".tgz", ".zip", ".tar.gz", ".pyc"];
const contentPatterns = [
  [/gho_[A-Za-z0-9]+/g, "GitHub token"],
  [/github_pat_[A-Za-z0-9_]+/g, "GitHub fine-grained token"],
  [/sk-[A-Za-z0-9_-]{16,}/g, "API key"],
  [/\bcomedy_game_01\b/g, "private project id"],
  [/\/home\/naiyou\b/g, "private NAS path"],
];

const violations = [];

async function trackedFiles() {
  try {
    return execFileSync("git", ["-C", root, "ls-files", "-z"], { encoding: "utf8" }).split("\0").filter(Boolean);
  } catch {
    throw new Error("Run this check inside the release Git repository.");
  }
}

for (const relative of await trackedFiles()) {
    const segments = relative.split("/");
    if (segments.some((segment) => forbiddenSegments.has(segment))) {
      violations.push(`forbidden tracked path: ${relative}`);
      continue;
    }
    if (forbiddenSuffixes.some((suffix) => relative.endsWith(suffix))) {
      violations.push(`forbidden tracked artifact: ${relative}`);
      continue;
    }
    const full = path.join(root, relative);
    const stat = await fs.stat(full);
    if (stat.size > 2_000_000) continue;
    const text = await fs.readFile(full, "utf8").catch(() => "");
    if (relative === "scripts/check-public-release.mjs") continue;
    for (const [pattern, label] of contentPatterns) {
      pattern.lastIndex = 0;
      if (pattern.test(text)) violations.push(`${label}: ${relative}`);
    }
}
if (violations.length) {
  console.error(violations.join("\n"));
  process.exit(2);
}
console.log("public release tree is clean");
