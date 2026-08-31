import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { promises as fs } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const required = [
  "package.json", "package-lock.json", "openclaw.plugin.json", "README.md", "UPGRADE-0.4.6.md", "AUDIT-REPORT.md",
  "src/index.js", "src/engine.js", "src/utils.js", "dist/index.js", "dist/engine.js", "dist/utils.js",
  "skills/novel-author/SKILL.md", "test/engine.test.js"
];
const failures = [];
for (const relativePath of required) {
  try { await fs.access(path.join(root, relativePath)); }
  catch { failures.push(`Missing required file: ${relativePath}`); }
}
if (failures.length) {
  console.error(failures.join("\n"));
  process.exit(1);
}
const pkg = JSON.parse(await fs.readFile(path.join(root, "package.json"), "utf8"));
const manifest = JSON.parse(await fs.readFile(path.join(root, "openclaw.plugin.json"), "utf8"));
if (manifest.id !== "novel-engine") failures.push(`Manifest id must be novel-engine, got ${manifest.id}`);
if (manifest.version !== pkg.version) failures.push(`Manifest/package version mismatch: ${manifest.version} != ${pkg.version}`);
if (pkg.main !== "./dist/index.js") failures.push("package.json main must be ./dist/index.js");
for (const relativePath of ["src/index.js", "src/engine.js", "src/utils.js", "dist/index.js", "dist/engine.js", "dist/utils.js"]) {
  try { execFileSync(process.execPath, ["--check", path.join(root, relativePath)], { stdio: "pipe" }); }
  catch (error) { failures.push(`Syntax check failed: ${relativePath}\n${error.stderr?.toString() ?? error.message}`); }
}
const hash = (value) => createHash("sha256").update(value).digest("hex");
for (const name of ["index.js", "engine.js", "utils.js"]) {
  const src = await fs.readFile(path.join(root, "src", name));
  const dist = await fs.readFile(path.join(root, "dist", name));
  if (hash(src) !== hash(dist)) failures.push(`dist/${name} is not synchronized with src/${name}; run npm run build.`);
}
const indexSource = await fs.readFile(path.join(root, "src/index.js"), "utf8");
const registered = [...indexSource.matchAll(/name:\s*"(novel_[a-z0-9_]+)"/g)].map((match) => match[1]);
const uniqueRegistered = [...new Set(registered)];
const contracts = manifest.contracts?.tools ?? [];
const missingContracts = uniqueRegistered.filter((name) => !contracts.includes(name));
const staleContracts = contracts.filter((name) => !uniqueRegistered.includes(name));
if (registered.length !== uniqueRegistered.length) failures.push("Duplicate registered tool names detected.");
if (missingContracts.length) failures.push(`Tools missing from manifest contracts: ${missingContracts.join(", ")}`);
if (staleContracts.length) failures.push(`Manifest contracts without registration: ${staleContracts.join(", ")}`);
for (const name of contracts) {
  if (manifest.toolMetadata?.[name]?.optional !== true) failures.push(`toolMetadata.${name}.optional must be true.`);
}
if (failures.length) {
  console.error(failures.join("\n"));
  process.exit(1);
}
console.log(`Package check passed: ${pkg.name}@${pkg.version}, ${contracts.length} tools.`);
