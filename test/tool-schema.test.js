import assert from "node:assert/strict";
import test from "node:test";
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
