# Model and Cross-Model Reference Strategies

Read this file when the user names the image model, asks how many references to upload, switches to another model, copies prompts into a new conversation, or when reference support is limited.

## 1. Universal rule

Treat each target model as stateless unless its interface explicitly carries the project context and uploaded images forward.

A phrase such as `参考 AST-01` is meaningful only when the actual AST-01 image is attached in the current request. Prompt text, filenames and asset IDs do not create an invisible cross-model link.

Every portable hard-lock prompt must therefore begin with the hard-lock banner and include the four sealed invariant blocks:

- STYLE LOCK;
- SCENE DNA;
- SPATIAL LOCK;
- CONTINUITY LOCK.

Reference images improve fidelity but do not replace these blocks.

## 2. Cross-model handoff package

When moving from Model A to Model B, carry all of the following:

1. the current asset's complete portable prompt;
2. L01/F01/Z01 geometry image when the new asset depends on topology;
3. B01 blockout for complex 3D/elevation scenes;
4. M01 master for appearance/material/style;
5. the previous accepted view for adjacent overlap;
6. SUB01 for character/vehicle/creature identity when relevant.

The prompt must explicitly state each image's role. Do not rely on Model B to infer role from filenames.

## 3. Tier A — multiple image references

Upload roles separately when the interface permits:

1. L01/F01/Z01 — geometry authority;
2. B01 — volume/elevation authority when present;
3. M01 — appearance authority;
4. previous accepted view — adjacent overlap only;
5. SUB01 — subject identity.

If the model supports weighting:

- geometry and subject identity: high;
- master appearance: high;
- previous-view composition: medium, so it does not force a duplicate camera.

The hard-lock banner, Lock ID and four-lock payload remain mandatory.

## 4. Tier B — one image reference

Create one composite reference board outside the image model containing:

- the clean layout/floor plan;
- the blockout when required;
- a small master shot;
- the previous accepted view;
- a subject inset when needed.

Use clear panel separation. Label externally where possible. In the prompt, describe what each panel controls.

The composite is an evidence board, not the Scene DNA itself. Keep the four locks in the prompt.

## 5. Tier C — text-only or weak reference support

Expect lower spatial consistency. Use this fallback:

1. generate L01;
2. generate M01;
3. create a 2×3 multi-view contact sheet in one generation;
4. crop/use each panel as a visual anchor for separate full-resolution views;
5. audit every view before advancing.

The contact sheet helps identity but does not prove true geometry. L01 remains topology authority. Each full-resolution prompt still contains the hard-lock banner, Lock ID and complete four locks.

## 6. Contact-sheet prompt rules

- one scene, six clearly separated camera panels;
- consistent architecture/material/time;
- each panel has a distinct planned camera position;
- no decorative poster text;
- simple 2×3 grid with generous separators;
- do not treat the sheet as six independent scene designs;
- include the same four-lock header in the prompt.

## 7. Image-edit / outpaint workflows

When the model supports editing, camera changes are still not guaranteed by merely requesting “turn the camera”. Use layout and world relations.

- small camera moves: edit/outpaint may preserve identity;
- large reverse angles: use P01 proof-view plus L01/B01/M01;
- never let an edit preserve a wrong road or mirrored building merely because pixels are similar.

## 8. Seed reuse

A fixed seed may help style and local identity in some systems but does not lock 3D topology. Treat seed as secondary to layout, master, blockout, four-lock prompt and accepted reference inheritance.

## 9. Same model, new conversation

A new conversation is effectively a new model context unless the interface carries project state. Use the same procedure as cross-model handoff:

- complete portable prompt;
- actual reference images;
- explicit roles.

Do not assume a filename or prior chat title is retrievable.

## 10. Compact planning notes only

A persistent conversation may use compact **planning notes**, but no final/copy-ready image prompt may use a compact contract. Every final prompt remains `PORTABLE_HARD_LOCK`, even in the same conversation.

This avoids accidental reuse of a session-dependent prompt in a new window or another model.
