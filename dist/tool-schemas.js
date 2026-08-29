import { Type } from "typebox";

const Chapter = Type.Integer({ minimum: 1, maximum: 999999 });
const Sha256 = Type.String({ pattern: "^[a-fA-F0-9]{64}$" });
const ClosureOperationStatus = Type.Union([
  Type.Literal("pending"),
  Type.Literal("completed"),
  Type.Literal("skipped"),
  Type.Literal("failed")
]);

export const ClosureOperationInput = Type.Object({
  status: ClosureOperationStatus,
  evidence: Type.Optional(Type.String({ maxLength: 1000 })),
  reason: Type.Optional(Type.String({ maxLength: 5000 })),
  note: Type.Optional(Type.String({ maxLength: 5000 }))
}, {
  additionalProperties: false,
  description: "Closure operation receipt. completed requires evidence; skipped requires reason."
});

export const GenreGateInput = Type.Object({
  bodySha256: Sha256,
  pass: Type.Boolean({ description: "Explicit authoritative genre-gate result." }),
  genrePass: Type.Optional(Type.Boolean()),
  genreGatePass: Type.Optional(Type.Boolean()),
  hardBlock: Type.Optional(Type.Boolean()),
  severeDrift: Type.Optional(Type.Boolean()),
  chapterNo: Type.Optional(Chapter),
  metrics: Type.Optional(Type.Unknown()),
  warnings: Type.Optional(Type.Array(Type.String({ maxLength: 5000 }), { maxItems: 100 })),
  hardBlocks: Type.Optional(Type.Array(Type.String({ maxLength: 5000 }), { maxItems: 100 }))
}, {
  additionalProperties: true,
  description: "Genre gate bound to the exact canonical chapter body. bodySha256 and pass are required."
});

export const ChapterSignatureInput = Type.Object({
  bodySha256: Sha256,
  chapterNo: Type.Optional(Chapter),
  function: Type.Optional(Type.String({ maxLength: 5000 })),
  rhythm: Type.Optional(Type.String({ maxLength: 5000 })),
  experienceScores: Type.Optional(Type.Unknown()),
  hookType: Type.Optional(Type.String({ maxLength: 1000 }))
}, {
  additionalProperties: true,
  description: "Provisional chapter signature bound to the exact canonical chapter body; retain its real structure fields."
});
