import assert from "node:assert/strict";
import { promises as fs } from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { pathToFileURL } from "node:url";
import { ChapterSignatureInput, ClosureOperationInput, GenreGateInput } from "../src/tool-schemas.js";

test("closure tool schema exposes one object branch instead of a string union", () => {
  assert.equal(ClosureOperationInput.type, "object");
  assert.equal(ClosureOperationInput.anyOf, undefined);
  assert.deepEqual(ClosureOperationInput.required, ["status"]);
  assert.deepEqual(ClosureOperationInput.properties.status.anyOf.map((entry) => entry.const), ["pending", "completed", "skipped", "failed"]);
});
test("quality tool schemas expose required canonical hash bindings", () => {
  assert.equal(GenreGateInput.type, "object");
  assert.deepEqual(GenreGateInput.required, ["bodySha256", "pass"]);
  assert.equal(GenreGateInput.properties.bodySha256.pattern, "^[a-fA-F0-9]{64}$");
  assert.equal(ChapterSignatureInput.type, "object");
  assert.deepEqual(ChapterSignatureInput.required, ["bodySha256"]);
  assert.equal(ChapterSignatureInput.properties.bodySha256.pattern, "^[a-fA-F0-9]{64}$");
});

test("registered foreshadowing tools expose optional planting hash without changing tool inventory", async (t) => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), "novel-schema-registration-"));
  t.after(() => fs.rm(root, { recursive: true, force: true }));
  // Only the host SDK entry wrapper is stubbed; TypeBox schemas and registration are real.
  const source = (await fs.readFile(new URL("../src/index.js", import.meta.url), "utf8"))
    .replace('import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";', "const definePluginEntry = (entry) => entry;")
    .replace('from "typebox"', `from ${JSON.stringify(import.meta.resolve("typebox"))}`)
    .replace(/from "(\.\/[^\"]+)"/g, (_match, relative) => `from ${JSON.stringify(new URL(relative, new URL("../src/index.js", import.meta.url)).href)}`);
  const modulePath = path.join(root, "entry.mjs");
  await fs.writeFile(modulePath, source);
  const { default: plugin } = await import(pathToFileURL(modulePath).href);
  const tools = new Map();
  plugin.register({ pluginConfig: { projectsRoot: path.join(root, "projects") }, registerTool(definition) { tools.set(definition.name, definition); } });
  assert.equal(tools.size, 34);
  for (const name of ["novel_artifact_write", "novel_artifact_read"]) {
    assert.ok(tools.get(name).parameters.properties.artifactType.anyOf.some((branch) => branch.const === "stage-plan"));
  }
  const entry = tools.get("novel_foreshadowing_upsert").parameters.properties.entry;
  const finalizeEntry = tools.get("novel_finalize_chapter").parameters.properties.foreshadowingEntries.items;
  for (const schema of [entry, finalizeEntry]) {
    assert.equal(schema.properties.plantedBodySha256.type, "string");
    assert.equal(schema.properties.plantedBodySha256.pattern, "^[a-fA-F0-9]{64}$");
    assert.equal(schema.required.includes("plantedBodySha256"), false);
  }
});
