# Portable Hard-Lock Prompt Assembly Protocol

Read this file before emitting **every** final copy-ready image prompt.

## 1. Zero-context target assumption

Assume the destination model sees only:

- the exact prompt copied now;
- the images actually attached now;
- the explicit generation parameters entered now.

It does not know a prior chat, asset filename, Scene ID, `AST-01`, `V02`, “上一张图” or an OpenClaw state file unless those contents are included or uploaded.

Therefore every final prompt must be independently usable.

---

## 2. Hard-lock banner and exact required order

Every final prompt must start with:

```text
【PORTABLE HARD LOCK｜独立可用｜禁止删减】
LOCK_ID: {lock_id_or_UNSAVED}

【STYLE LOCK｜固定原文】
{style_lock_text}

【SCENE DNA｜固定原文】
{scene_dna_lock_text}

【SPATIAL LOCK｜固定原文】
{spatial_lock_text}

【CONTINUITY LOCK｜固定原文】
{continuity_lock_text}
```

The lock bodies are immutable canonical payloads.

Rules:

1. Keep the headings exactly as written.
2. Keep the four bodies character-for-character identical across all assets until explicit revision.
3. Never summarize, paraphrase, translate, reorder, merge or “优化” them.
4. Never omit them because a layout/master/previous view is supplied.
5. Never place current-camera or current-action details inside the frozen lock bodies.
6. A `LOCK_ID` alone never replaces the actual lock text.
7. `AST-01` and the first geometry asset also require the full four locks.

---

## 3. What belongs in the four locks

### STYLE LOCK

Only fixed visual-medium information:

- style family;
- 2D/3D/photographic medium;
- realism level;
- modelling/rendering/brushwork language;
- material quality;
- palette and light character;
- incompatible style exclusions.

Do not put object positions or camera instructions here.

### SCENE DNA

The immutable identity of the place:

- Scene ID/name and world/era;
- environment type;
- fixed A-H landmark names;
- signature architecture/object design;
- asymmetric identity fingerprints;
- scale anchors;
- time, season, weather, ground state;
- fixed physical world-light state.

### SPATIAL LOCK

The immutable physical topology:

- world origin and orientation;
- landmark positions/relations;
- entrances and connections;
- roads, corridors, rooms, stairs, bridges, rivers and route geometry;
- for multi-room interiors: level IDs, room adjacency, portal IDs and vertical connectors;
- distances, widths, bends and elevations;
- anchor triangle;
- sun azimuth/elevation when required to prevent screen-relative drift.

### CONTINUITY LOCK

The invariants and allowed changes:

- exact same physical place;
- no architecture redesign;
- no landmark relocation/deletion/duplication;
- no topology, scale, material, season, weather or physical-light change;
- no whole-scene mirror;
- only camera, natural occlusion, perspective and moving-subject state may change;
- failed images cannot enter the reference chain.

---

## 4. Complete final structure

After the four locks, use this exact section order:

```text
【CURRENT ASSET】
Asset ID: {asset_id}
Asset name: {asset_name}
Task: {task}
Expected use: {purpose}

【WORLD RELATIONSHIPS FOR THIS VIEW】
{asset-specific world relations that do not contradict SPATIAL LOCK; for interiors include current level/zone, source zone, destination zone, active connector and legal topology path}

【CAMERA SETUP】
Position: {camera_position}
Look-at / direction: {camera_direction}
Height: {camera_height}
Shot / FOV: {shot_size_and_fov}
Lens/perspective: {lens_instruction}
Action-axis side: {when relevant}

【VISIBLE / OCCLUDED LANDMARKS】
Must be visible: {must_visible}
May be naturally occluded: {may_occlude}
Shared with previous accepted view: {shared_landmarks}

【REFERENCE INPUTS｜需实际上传】
R1: {actual image to attach} — controls {role}; must not copy {forbidden_role}.
R2: {actual image to attach} — controls {role}; must not copy {forbidden_role}.

If any named reference is not actually attached in this request, do not pretend it has been seen. Use the four fixed lock blocks above as the fallback scene definition.

【MOVING SUBJECT / TRANSITION】
{omit only when no subject or transition exists}

【TARGETED RESTRICTIONS】
{six to ten asset-specific failure modes}

This is the exact same physical location viewed from the specified camera. Preserve the frozen four-lock payload, world geometry, scale and identity fingerprints. Allow physically correct perspective, parallax and occlusion. Do not redesign the scene or copy another view's screen composition.
```

The final copy-ready content must be one code block. Do not put the four locks in a separate block from the current asset.

---

## 5. Reference-upload card outside the prompt

Before the code block, show a concise card:

```text
【本张必须上传的参考图】
R1：L01 — 空间拓扑权威
R2：B01 — 体块与高差权威（复杂3D时）
R3：M01 — 外观、材质、色彩权威
R4：V02 — 相邻视角共享地标（如有）
R5：SUB01 — 移动主体身份（如有）
```

Use “必须上传” or “建议上传”. Never claim that a picture was supplied unless the current request actually contains it.

Asset names are not references by themselves. The target model must receive the actual image.

---

## 6. AST naming rule

Some workflows use `AST-01`, `AST-02`, `AST-03` instead of L/M/V IDs. The naming scheme changes nothing.

Every AST prompt must still include:

- hard-lock banner;
- Lock ID;
- complete STYLE LOCK;
- complete SCENE DNA;
- complete SPATIAL LOCK;
- complete CONTINUITY LOCK;
- all dynamic sections.

Invalid:

```text
请参考 AST-01，生成 AST-02 南门外。
```

Still invalid:

```text
保持上一张的风格和场景一致，生成南门外。
```

Valid: a full hard-lock prompt that additionally says the actual AST-01 image must be uploaded and defines its role.

---

## 7. Bilingual output rule

Default to one Chinese prompt.

If the user asks for Chinese and English:

- produce two separate final prompts;
- each prompt must be independently portable;
- each must repeat the complete four locks;
- the English lock bodies must be frozen as their own approved English canonical payload, not a fresh translation on every asset;
- do not provide one full version and one abbreviated version.

---

## 8. Asset-specific notes

### L01/F01/Z01/C01/S01

- near-vertical orthographic/topological view;
- clear footprints, portals, paths and boundaries;
- no dramatic perspective;
- no dependence on AI-rendered readable labels;
- include route/elevation cues when needed.

### B01

- neutral clay/blockout representation;
- exact volume, levels, stairs and cliffs;
- minimal decoration;
- geometry authority only, never final material authority.

### M01

- natural establishing perspective;
- architecture/material/palette authority;
- inherit L01/B01 geometry;
- prevent layout/blockout visual style leakage;
- no fisheye merely to fit all anchors.

### P01

Use a meaningful reverse/oblique camera to prove:

- side/back architecture;
- portal/path continuity;
- fingerprints on the correct physical sides;
- fixed world-space sunlight.

### Key asset

Inspect an accepted object; do not redesign it. Include nearby context and scale.

### Multi-view

Specify exact world position, look direction, height, FOV, required landmarks and allowed occlusion. “换一个角度” is insufficient.

### Shot

Include previous end state, current start/end state, screen direction, action axis and route-proving background anchors.

---

## 9. Prompt size guidance

Portable hard-lock prompts are intentionally longer.

Preferred:

- with actual references: roughly 800-1800 Chinese characters;
- text-only fallback: roughly 1100-2400 Chinese characters.

Do not shorten by deleting locks. Remove decorative synonyms and irrelevant negative phrases first.

---

## 10. Hard-lock preflight

Before output, silently check:

- [ ] banner is first;
- [ ] `LOCK_ID:` exists;
- [ ] exact STYLE heading exists once;
- [ ] exact Scene DNA heading exists once;
- [ ] exact Spatial heading exists once;
- [ ] exact Continuity heading exists once;
- [ ] all four bodies are non-empty;
- [ ] order is correct;
- [ ] bodies exactly match canonical state;
- [ ] dynamic sections exist;
- [ ] references say actual upload is required;
- [ ] no unresolved “同上 / 如上 / 沿用前文” dependency;
- [ ] no symbolic reference is treated as visually accessible;
- [ ] prompt works in a fresh model chat.

If any check fails, rebuild. Do not output the incomplete prompt.


## 11. Indoor transition preflight

For `TRxxA/B/C` or any cross-room/cross-floor camera, silently verify:

- source and destination zones exist;
- active connector links those exact zones;
- current camera is on the declared side of the connector;
- opposite-side door/opening identity is unchanged;
- source/destination room Masters are listed as actual uploads when available;
- stair direction, landing and floor elevation agree with S01;
- no object requested as visible is behind a locked opaque wall.

If a required connector is absent, do not invent it. Return `TOPOLOGY_GAP` in planning output or create the missing geometry authority before emitting a final transition prompt.
