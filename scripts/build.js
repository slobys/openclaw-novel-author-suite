import { promises as fs } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const sourceDir = path.join(root, "src");
const distDir = path.join(root, "dist");
await fs.mkdir(distDir, { recursive: true });
for (const name of ["engine.js", "finalize.js", "index.js", "tool-schemas.js", "utils.js"]) {
  const source = path.join(sourceDir, name);
  const target = path.join(distDir, name);
  await fs.copyFile(source, target);
}
console.log("Built dist from src.");
