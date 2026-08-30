---
name: deepwhite-shotlist-builder-zh-user
description: 将剧本或场景拆解为中文影视分镜、Seedance 2.0 视频提示词、直接文本提示词或分镜网页，并继承 Scene Asset Planner 的场景资产绑定。Use when the user uploads or references a screenplay, asks for shot breakdown, cinematic blocking, Seedance prompts, video prompt sheets, storyboard-aware prompts, asset-image comparison, or an HTML production page, and when an n8n_asset_generation_completed callback requires automatic ingestion of generated/reused asset images followed by AI-reviewed asset mapping, deterministic scene-to-location inheritance, spatial blocking, timing division, dispatcher-ready video prompt manifests, and text video-prompt delivery. Support both manual user-confirmed gates and AUTO_GATE_MODE evidence-based gates while enforcing Chinese output, exact scene asset binding, per-shot fields, prompt length control, and HTML QA when applicable.
---

# DeepWhite Shotlist Builder ZH User v2.8

作者：DeepWhite

Build Chinese production shotlist webpages for Seedance 2.0. Do not merely transcribe the script. Direct it: turn story beats into cinematography, spatial blocking, physical performance, lighting, background activity, and model-failure prevention.

## Gate Execution Mode

All confirmation gates must be satisfied. Select exactly one mode and record it before processing.

### MANUAL_GATE_MODE

Use this mode when the user directly invokes the skill, requests staged review, or no valid n8n completion event exists.

- Wait for `确认资产` after showing the asset mapping.
- Wait for `确认位置` after showing required blocking schemas.
- Wait for `确认时间划分` after showing the timing proposal.
- Wait for `确认提示词结构` only when the user changed the default prompt structure.
- Wait for `生成网页` or `只要文字提示词` before final delivery.

### AUTO_GATE_MODE

Use this mode only when all of the following are true:

- The incoming event is `n8n_asset_generation_completed`.
- The project has `AUTO_PRODUCTION_MODE` enabled.
- The callback contains non-empty `project_id`, `job_id`, and `status`.
- `status` is `completed` and `failed_count` is `0`.

In this mode, never ask the user to repeat gate confirmation phrases. Satisfy gates with validated files and AI review evidence instead.

Execute in this exact order:

1. Resolve exactly one project by matching `project_id` and `job_id` against `projects/*/dispatch/asset_jobs/*.json`.
2. Require `handoffs/scene_asset_handoff.json` for AUTO production. It must have `gate_passed == true`, a non-empty `source_plan_id`, and an exact binding for every screenplay scene in the selected scope. Never reconstruct location bindings from prose when this handoff exists.
3. Ignore any filesystem path supplied by the callback. Construct the result path only from the configured root `${OPENCLAW_ASSET_ROOT}/{project_id}/{job_id}/`.
4. Require both `result_manifest.json` and `.done` in that directory.
5. Require `manifest.status == completed`, `accepted_count == expected_count`, `failed_count == 0`, and every listed generated image to exist and be readable.
6. Create/enrich `assets/actual_asset_manifest.json`. Include both current n8n-generated assets and every `verified_reuse_asset_id` from the Scene Asset Handoff resolved through the series `asset_registry.json` / canonical `series_assets/` copy. Every referenced asset must have one unique `asset_id`, readable source path, category, source kind (`n8n_generated` or `series_reuse`), and approved/verified status.
7. Read every actual image that can be referenced downstream, including verified reuse assets. Create `assets/observed_asset_state.json` containing only objective visible traits needed downstream. Do not score image quality, redo n8n review, or request image regeneration.
8. Build `shots/shot_scene_bindings.json` by exact inheritance from `scene_asset_handoff.json`. Every shot must carry `scene_id`, `location_id`, `sub_location_id`, and one allowed `location_asset_id`; route scenes also require the matching `route_anchor_id`. No shot may invent, approximate, merge, or silently change a location binding.
9. Run the deterministic Scene Asset Binding Gate against `script/scene_index.json`. Require 100% authoritative Scene coverage, exact scene/location/sub-location/allowed-asset/route-anchor inheritance, and existence of every `location_asset_id` in `assets/actual_asset_manifest.json`. Write `gates/shot_scene_binding_gate.json`.
10. Use the actual image as authority for visible appearance, costume color, materials, and visible environment design. Continue using the confirmed script and continuity ledger as authority for plot facts, identity, relationships, timeline, injuries, prop state, and story causality.
11. Generate `shots/spatial_blocking.json`, then perform a separate AI review pass. Revise at most twice. A passed review is equivalent to `确认位置`. Spatial blocking must preserve the inherited location/sub-location identity.
12. Generate `shots/timing_plan.json`. Every final AUTO production prompt group must belong to exactly one `scene_id`, one inherited `location_asset_id`, and when applicable one `route_anchor_id`; crossing a Scene or route anchor always starts a new prompt group. Deterministically verify that every generated-video clip is an integer 4–15 seconds, all segments are contiguous/non-overlapping inside the scene, and their total equals the selected scope duration. Internal shots may be 1–3 seconds, but they must be embedded in a 4–15 second generated clip or generated at 4 seconds and trimmed later. Then perform a separate AI pacing review. Revise at most twice. A passed review is equivalent to `确认时间划分`.
13. Use the default prompt structure and record `已确认提示词结构：使用默认结构` unless project configuration explicitly supplies another already-approved structure.
14. Set delivery format to `只要文字提示词` unless the current project configuration explicitly overrides it.
15. Write all gate evidence to `review/video_prompt_gate_review.json`.
16. Proceed to final prompt generation only when `ready_for_video_prompt_generation` is `true`.
17. Save final text prompts to `video_prompts/video_prompt_sheet.md` and also write `video_prompts/video_prompt_manifest.json` containing dispatcher-ready clip records with `clip_id`, `scene_id`, `location_id`, `sub_location_id`, `location_asset_id`, `background_reference_mode`, `shot_ids`, `duration`, `reference_asset_ids`, and `prompt`.
18. Deterministically validate `scene_asset_handoff → environment_continuity_map → shot_scene_bindings → video_prompt_manifest`. Run `validate_environment_continuity.py` first and require `gates/environment_continuity_gate.json.passed=true`; then run Shot Scene Binding. Only after both pass may `project.json` be updated to `video_prompts_ready`.

Pause only when one of these blockers exists:

- The callback status is not `completed` or reports failed assets.
- The Scene Asset Handoff is missing, has `gate_passed != true`, lacks a selected-scope scene, or contains duplicate/ambiguous scene bindings.
- The manifest, `.done`, a required generated image, or a verified reusable asset is missing or unreadable.
- Asset IDs or filenames are missing, duplicated, ambiguous, or cannot map to exactly one upstream asset.
- Any shot does not inherit the exact `location_id` / `sub_location_id` / `primary_location_asset_id` required by its scene.
- Any AUTO prompt group spans multiple scenes or multiple location assets.
- The callback cannot resolve exactly one project.
- Spatial review still has Critical issues after two revisions.
- Timing review still has Critical issues after two revisions.
- Confirmed script/continuity facts and actual images contain a substantive conflict that cannot be resolved by the authority hierarchy above.

The gate evidence file must use this minimum structure:

```json
{
  "schema_version": "1.0",
  "mode": "AUTO_GATE_MODE",
  "project_id": "...",
  "job_id": "...",
  "gates": {
    "image_delivery": { "status": "passed", "confirmed_by": "system" },
    "asset_confirmation": { "status": "passed", "confirmed_by": "ai", "basis": "actual_images" },
    "scene_asset_binding": { "status": "passed", "confirmed_by": "deterministic_validator", "scene_coverage_ratio": 1.0, "shot_binding_ratio": 1.0 },
    "spatial_confirmation": { "status": "passed", "confirmed_by": "ai_reviewer", "revision_round": 1, "critical_issues": [] },
    "timing_confirmation": { "status": "passed", "confirmed_by": "ai_reviewer", "revision_round": 1, "critical_issues": [] },
    "delivery_format": { "status": "passed", "value": "text", "source": "automation_default" }
  },
  "ready_for_video_prompt_generation": true
}
```

## Non-Negotiable Gates

This skill has seven hard gates. Never skip them. In `MANUAL_GATE_MODE`, satisfy them through explicit user confirmation. In `AUTO_GATE_MODE`, satisfy them through validated evidence and AI review records.

1. **Asset Confirmation Gate**
   - In `MANUAL_GATE_MODE`, ask whether the user needs storyboard assets during asset preparation.
   - Storyboards may be images containing numbered frames, shot drawings, and text notes.
   - In `MANUAL_GATE_MODE`, after the user uploads images, output an asset mapping table including storyboards if present.
   - In `MANUAL_GATE_MODE`, ask the user to reply `确认资产` or provide corrections.
   - In `MANUAL_GATE_MODE`, do not write prompts or generate HTML until the user confirms the asset mapping.
   - In either mode, stop on ambiguous, missing, duplicated, or extra filenames. Ask the user only in `MANUAL_GATE_MODE`; report an automation blocker in `AUTO_GATE_MODE`.
   - In `AUTO_GATE_MODE`, do not ask for `确认资产`. Require the completed n8n manifest, build the unique actual-image mapping, inspect the actual images, and record the passed gate in `review/video_prompt_gate_review.json`.
   - Use `reference/ASSET_CONFIRMATION.md` and `reference/STORYBOARD_ASSETS.md`.

2. **Scene Asset Binding Gate**
   - In `AUTO_GATE_MODE`, `handoffs/scene_asset_handoff.json` is mandatory and must have `gate_passed == true`.
   - Use `script/scene_index.json` as the authoritative coverage denominator. For every selected-scope scene, inherit `scene_id → location_id → sub_location_id → primary/allowed location assets → route anchors`.
   - Every shot must inherit an allowed asset into `shots/shot_scene_bindings.json`; route scenes also inherit the matching `route_anchor_id`. Never infer a substitute from prompt wording, filename similarity, or visual resemblance.
   - Every inherited `location_asset_id` must exist in the enriched `assets/actual_asset_manifest.json`. Verified series-reuse assets must be resolved into that manifest before this gate runs.
   - A prompt group/clip may contain multiple shots, but all included shots must share one `scene_id`, one `location_asset_id` and one route anchor when applicable. Scene or route-anchor changes split prompt groups.
   - Run `scripts/validate_shot_scene_bindings.py` and require `scene_coverage_ratio == 1.0`, `shot_binding_ratio == 1.0`, and `prompt_binding_ratio == 1.0`.
   - Save the validator report to `gates/shot_scene_binding_gate.json`. Do not continue when it fails.
   - In `MANUAL_GATE_MODE`, enforce this gate whenever a Scene Asset Handoff is supplied. If no handoff exists, legacy manual work may continue, but it must not claim deterministic scene-asset binding.
   - Use `reference/SCENE_ASSET_BINDING.md` and `reference/VIDEO_PROMPT_HANDOFF.md`.

3. **Spatial Confirmation Gate**
   - Before writing prompts for any scene containing two or more story characters, any important character relationship, any key prop on a specific surface, or any camera geometry that affects the shot, produce a top-down blocking schema.
   - In `MANUAL_GATE_MODE`, ask the user to reply `确认位置` or provide corrections.
   - In `MANUAL_GATE_MODE`, do not write prompts or generate HTML until the user confirms the required spatial blocking.
   - In `AUTO_GATE_MODE`, do not ask for `确认位置`. Generate `environment_continuity_map` with predecessor references, route direction, landmark world relationships, scale/parallax and occlusion evidence; run `validate_environment_continuity.py`, then a separate AI review. Revise up to two times and continue only after both evidence files pass.
   - Use `reference/SPATIAL_BLOCKING.md` and `reference/ENVIRONMENT_CONTINUITY_GATE.md`.

4. **Timing Division Confirmation Gate**
   - Before writing prompts or generating HTML, propose how the selected plot scope will be divided into time segments and how many video prompts it will produce.
   - Each prompt may cover at most 15 seconds of video.
   - Do not over-segment. Merge continuous beats when they share characters, location, mood, and camera logic, as long as the prompt remains clear and <=15 seconds.
   - In `MANUAL_GATE_MODE`, ask the user to reply `确认时间划分` or provide corrections.
   - In `MANUAL_GATE_MODE`, do not write prompts or generate HTML until the user confirms the time division and prompt count.
   - In `AUTO_GATE_MODE`, do not ask for `确认时间划分`. Run deterministic duration/coverage validation plus a separate AI pacing review, revise up to two times, and continue only after the evidence file records a passed gate.
   - Use `reference/PROMPT_TIMING.md` and `reference/PROMPT_DENSITY.md`.

5. **Prompt Structure Confirmation Gate**
   - When the user asks to change the final video-prompt structure, update the proposed structure and show the user the exact template.
   - In `MANUAL_GATE_MODE`, ask the user to reply `确认提示词结构` or provide corrections.
   - In `MANUAL_GATE_MODE`, do not install or treat the changed structure as final until the user confirms.
   - In `AUTO_GATE_MODE`, use and record the default structure unless the project already contains a different explicitly approved structure.
   - Use `reference/PROMPT_PATTERNS.md`.

6. **Delivery Format Confirmation Gate**
   - In `MANUAL_GATE_MODE`, ask whether the user wants an HTML webpage or direct text prompts before final output.
   - In `MANUAL_GATE_MODE`, ask the user to reply `生成网页` or `只要文字提示词`.
   - If the user chooses text-only, output prompts directly in chat and do not generate HTML.
   - If the user chooses webpage, generate the stable Chinese HTML and run HTML QA.
   - In `AUTO_GATE_MODE`, do not ask this question. Use `只要文字提示词` unless project configuration explicitly overrides it.
   - Use `reference/DELIVERY_FORMAT.md`.

7. **HTML QA Gate** (only when the user chooses webpage)
   - Before delivering the HTML, render or inspect the generated page for layout stability.
   - The page must not use `rowspan` or `colspan` for prompt grouping.
   - Long Chinese prompt text must wrap inside its container without overlapping adjacent columns.
   - Fix layout issues in the HTML before delivery.
   - Use `reference/HTML_QA.md` and `templates/HTML_TEMPLATE.md`.

If a later user message supplies new assets, changes storyboard use, changes scope, changes positions, changes style, changes rhythm/pacing, changes delivery format, or changes final prompt structure, invalidate the relevant gate. In `MANUAL_GATE_MODE`, reconfirm with the user. In `AUTO_GATE_MODE`, regenerate and re-review the affected evidence before continuing.

## Output Language

The final HTML webpage must be entirely in Simplified Chinese:

- Chinese UI labels, headers, scene titles, metadata, table headings, action cells, scene-text cells, asset lists, prompt labels, buttons, empty states, filters, and notes.
- Chinese Seedance prompt blocks.
- Chinese action summaries and scene summaries.
- Translate dialogue into Chinese unless the user explicitly asks to preserve the original spoken language. If original-language dialogue is required for lip-sync or performance, keep only the quoted spoken line in that language and write all surrounding direction in Chinese.
- Use English only for filenames, model-specific tokens, or user-requested technical terms.

## Style Source

Do not use a fixed default style. Do not assume the original skill's director style.

Derive style in this order:

1. User's explicit style direction.
2. Uploaded style references: previous shotlist HTML, director notes, mood board, visual references, look bible, sample prompts, screenshots.
3. The screenplay itself: genre, period, locations, emotional register, camera language, recurring motifs.

Before prompt writing, confirm the style source in Chinese. In `MANUAL_GATE_MODE`, ask one short style question and stop if no useful style can be inferred. In `AUTO_GATE_MODE`, derive the style from confirmed project material and actual images, record the source in the gate review, and pause only if no defensible style source exists.

## Phase 1 — Read Script

Read the entire script and identify:

- Scene numbers and scene headers
- Characters and first appearances
- Locations
- Significant props and readable text
- Dialogue and action beats
- Mood and emotional register
- Style signals from script and references

## Phase 2 — Request Assets

In `AUTO_GATE_MODE`, skip the manual request/upload conversation. Read the completed n8n result manifest and `handoffs/scene_asset_handoff.json`. Build an enriched `assets/actual_asset_manifest.json` that includes both current generated assets and every verified series-reuse asset needed by the handoff, inspect all downstream-referenceable images, build `assets/observed_asset_state.json`, build and validate `shots/shot_scene_bindings.json`, and continue to Phase 3 only when both the asset gate and Scene Asset Binding Gate pass.

In `MANUAL_GATE_MODE`, use the following request flow.

Output a Chinese asset list grouped by category:

```markdown
**人物**
- 角色名：一句话外观和叙事功能

**场景**
- 场景名：空间结构和主要视觉特征

**道具**
- 道具名：尺寸、文字、材质、使用场景

**风格参考（可选）**
- 参考名：用途

**故事板 / 分镜图（可选）**
- 询问用户是否需要上传带编号的故事板图片。故事板可以包含分镜图、镜头编号、动作说明、文字说明。
```

End with:

```text
请生成并上传这些参考图。文件名尽量让我能直接对应，例如 roko.png、apartment.png、polaroid_nov14.png。
另外，你是否需要使用故事板/分镜图参考？如果需要，请上传带编号的故事板图片，例如 storyboard_01.png、SB_03.png。故事板可包含分镜图和文字信息，但最终视频画面不会保留故事板编号、标注、线段或台词框。
上传后请告诉我先做哪些场景。
```

In `MANUAL_GATE_MODE`, stop and do not continue to Phase 3 in the same turn. In `AUTO_GATE_MODE`, this stop rule does not apply after validated n8n asset ingestion.

## Phase 3 — Confirm Scope, Assets, Style, and Positions

In `AUTO_GATE_MODE`:

1. Confirm the scene scope from the project configuration and current script scope.
2. Require `handoffs/scene_asset_handoff.json` and confirm its selected-scope scene coverage is 100%.
3. Use the enriched `assets/actual_asset_manifest.json` as the asset mapping source.
4. Use `assets/observed_asset_state.json` for visible appearance and material facts.
5. Use `shots/shot_scene_bindings.json` as the only location-binding authority at shot level.
6. Confirm the style source from project requirements, actual assets, and script signals.
7. Create `shots/spatial_blocking.json` for every required scene while preserving the inherited `location_id`, `sub_location_id`, and `location_asset_id`.
8. Run a separate spatial review against the script, continuity ledger, actual asset state, camera axis, screen direction, character relationships, key-prop placement, and inherited scene asset identity.
9. Revise up to two times. Record `spatial_confirmation.status = passed` before continuing.

In `MANUAL_GATE_MODE`, use the following confirmation flow.

When the user uploads images or provides asset files:

1. Confirm the scene scope in Chinese.
2. Output the required asset confirmation table from `reference/ASSET_CONFIRMATION.md`, including storyboard files and storyboard frame numbers if present.
3. Ask for `确认资产`.
4. Confirm style source in Chinese.
5. Create top-down spatial blocking schemas for all required scenes using `reference/SPATIAL_BLOCKING.md`.
6. Ask for `确认位置`.

In `MANUAL_GATE_MODE`, do not start prompt writing until the user has confirmed both required gates:

```text
已确认资产：是
已确认位置：是 / 本次范围无需位置图，原因：...
已确认风格：是
```

If a scene truly does not need spatial confirmation, state the reason explicitly. Example: `单人无关键道具的纯表情特写，无需位置图。`

## Phase 4 — Confirm Time Division and Prompt Count

Only after asset/style/position gates are complete:

1. Break the selected plot into proposed prompt groups using `reference/PROMPT_DENSITY.md`.
2. Assign a time plan to each proposed prompt group using `reference/PROMPT_TIMING.md`.
3. Output a Chinese timing proposal table that shows plot segment, time range, estimated duration, prompt count, and grouping reason.
4. In `AUTO_GATE_MODE`, ensure every proposed generated clip is an integer 4–15 seconds. Internal shots may be shorter than 4 seconds, but a standalone n8n video task may not.
5. Every prompt group must belong to exactly one `scene_id` and one `location_asset_id`; do not group across a scene/location boundary even when total duration is short.
6. Ensure the proposal does not over-segment the plot. Merge short adjacent beats when they form one continuous emotional or action unit.
7. In `MANUAL_GATE_MODE`, ask the user to reply `确认时间划分` or tell you where to merge/split, then stop without writing prompts or HTML in the same turn.
8. In `AUTO_GATE_MODE`, write the proposal to `shots/timing_plan.json`; deterministically verify duration arithmetic, 4–15-second generated-clip limits, scene/location binding, contiguity, non-overlap, total duration, and beat coverage; then run a separate AI pacing review.
9. In `AUTO_GATE_MODE`, revise up to two times and record `timing_confirmation.status = passed` before continuing.

In `MANUAL_GATE_MODE`, proceed only after the user confirms:

```text
已确认时间划分：是
```

## Phase 5 — Confirm Final Prompt Structure

In `AUTO_GATE_MODE`, use the default prompt structure and record `已确认提示词结构：使用默认结构`, unless the current project already contains another explicitly approved structure.

In `MANUAL_GATE_MODE`, if the user has changed the final prompt structure in this project or skill version, show the exact final prompt template and ask for:

```text
确认提示词结构
```

In `MANUAL_GATE_MODE`, proceed to formal prompt writing only after confirmation. In `AUTO_GATE_MODE`, proceed after the prompt-structure evidence is recorded.

## Phase 6 — Confirm Delivery Format

In `AUTO_GATE_MODE`, set delivery format to `只要文字提示词`, record `delivery_format.value = text`, and continue without asking the user. Allow an explicit project-level override to select HTML.

In `MANUAL_GATE_MODE`, ask before final output:

```text
请确认最终交付形式：回复 `生成网页`，我会输出完整中文 HTML 分镜提示词表；回复 `只要文字提示词`，我会不生成网页，直接输出按顺序排列的文字提示词。
```

In `MANUAL_GATE_MODE`, stop until the user confirms. This stop rule does not apply in `AUTO_GATE_MODE` after the delivery-format evidence passes.

## Phase 7 — Generate Final Output

In `AUTO_GATE_MODE`, first verify that `review/video_prompt_gate_review.json` has `ready_for_video_prompt_generation: true` and `gates/environment_continuity_gate.json.passed=true`. Do not generate final prompts when either precondition fails.

Only after the gates are complete:

1. Use the confirmed time division and prompt count. Do not invent new prompt groups silently.
2. Write Chinese Seedance 2.0 prompts using `reference/PROMPT_PATTERNS.md`, `reference/STYLE_BLOCK.md`, `reference/CAMERA_EMOTION.md`, and `reference/MICRO_BEATS.md`.
3. If storyboards are actually used in a prompt or shot, cite the storyboard frame numbers used.
4. If no storyboard is used in a prompt or shot, omit all storyboard-related labels, placeholders, and warnings from that prompt or shot. Never write `故事板参考：本条不使用故事板。`, `故事板参考：无。`, or any equivalent unused-storyboard note.
5. Keep each copyable video prompt body within 2200 Chinese characters. If a draft is longer, compress it before delivery using the reduction rules in `reference/PROMPT_PATTERNS.md`.
6. If delivery format is `只要文字提示词`, output direct text prompt blocks. In `AUTO_GATE_MODE`, save the complete result to `video_prompts/video_prompt_sheet.md` and create `video_prompts/video_prompt_manifest.json` using `reference/VIDEO_PROMPT_HANDOFF.md`.
7. In the AUTO manifest, every `clip_id` must be dispatcher-ready and carry the exact inherited `scene_id`, `location_id`, `sub_location_id`, `location_asset_id`, optional `route_anchor_id`, `background_reference_mode`, `shot_ids`, `duration`, `reference_asset_ids`, and final `prompt`. Use `location_asset` mode by default. Use `scene_keyframe` only when an approved keyframe exists and its metadata traces back to the same `location_asset_id`.
8. Run `scripts/validate_shot_scene_bindings.py` against the Scene Asset Handoff, enriched actual asset manifest, shot bindings, and video prompt manifest. Do not mark the project ready if validation fails.
9. If the user chose `生成网页`, assemble the webpage with `templates/HTML_TEMPLATE.md`; each prompt group must include a per-segment asset-image comparison table outside the copyable prompt body.
10. Use the stable group-row layout. Do not use `rowspan` or `colspan`.
11. Run the HTML QA checklist from `reference/HTML_QA.md`.
12. Save as `Shotlist_<scope>_ZH_v2_8.html`.
13. Deliver the final HTML.
14. In `AUTO_GATE_MODE`, update `project.json` with `video_prompt_status: ready`, `project_status: video_prompts_ready`, the saved prompt path, and `video_prompt_manifest_path`.
15. Stop before video generation, ComfyUI production, automatic rendering, or external publishing.

## Prompt Rules

- Handles renumber per prompt. Declare handles at the start of every prompt.
- In AUTO production, every final prompt group is scene/route-anchor bound. It must have exactly one `scene_id`, `location_id`, `sub_location_id`, `location_asset_id` and, when applicable, `route_anchor_id`, inherited from `shots/shot_scene_bindings.json`. Never let prompt prose override these machine bindings.
- A hard location cut or scene change always ends the current prompt group and starts a new one.
- Every prompt starts with `不要出现BGM，不要出现字幕`.
- Immediately after that, write style before handles using exactly these four headings: `【全局画质】`、`【人物材质】`、`【灯光与风格】`、`【核心特效】`.
- All four style modules must be written in Chinese. Do not use English labels such as `Photorealistic`, `Texture`, `Lighting`, `Visual Style`, or `VFX` in final prompts; translate their control intent into Chinese.
- `【全局画质】` controls overall realism and generation direction: real-film photography, high resolution, large-format feeling, real physics, non-game, non-3D-render, non-animation/illustration, or any other direction required by the user/materials/script.
- `【人物材质】` controls close-up human realism: pores, fine hair, skin blood color, wetness, sweat, wounds, lip texture, eye redness, subsurface scattering, body strain, and other skin/body-surface details. Do not repeat character identity, full costume, or plot background here.
- `【灯光与风格】` controls light, color, mood, cinematic feeling, and visual taste: key/fill/negative fill, contrast, color tendency, grain, representative film influence if provided, and spatial contrast. It must come from user requirements, references, or script analysis.
- `【核心特效】` controls the most memorable visual mechanism in the prompt. If there is a VFX element, write its shape, material, color, movement, particles/fluid/energy behavior, generation/dissipation, and physical interaction with characters/environment. If there is no supernatural VFX, write the core physical visual mechanism such as underwater resistance, smoke, real fire, rain splash, glass breakage, dust, or impact debris.
- Then declare handles. Do not put handles before the four style headings.
- Do not include a standalone `时间安排：` paragraph in the copyable video prompt body; timing stays in the HTML timing column and timing proposal.
- Do not include the global line `⚠️对白规则：`.
- Before every shot's `机位：`, write `画面动作概述：...`, including the character state.
- After `画面动作概述：...` and before `机位：`, write `画面构图：...` as the initial composition, using screen zones and spatial locks first: left/center/right third, upper/lower area, foreground/midground/background, frame occupancy, negative space, contact points, occlusion, and relative front/behind/left/right relationships.
- Percentage anchors are optional assistance only, not mathematical guarantees. If used, follow screen coordinates: x=0% left edge, x=50% center, x=100% right edge; y=0% top edge, y=50% center, y=100% bottom edge. Write them as approximate anchors such as `身体中心约在x=32%` or `脚靠近y=88%`.
- Every shot must keep the fixed internal field order: `画面动作概述：` → `画面构图：` → `机位：` → `动作：` → `音效：`. If a storyboard is actually used, add `故事板参考：SB-xx。` before `画面动作概述：`.
- Every shot must include `音效：...`. If a sound continues through the whole scene, describe it under `环境活动 / 全场音效：...`.
- Each copyable final prompt body must be no more than 2200 Chinese characters. When HTML is requested, show the approximate character count and manual trimming suggestions outside the copyable prompt block.
- When HTML is requested, each prompt group must include a Chinese asset-image comparison table for that segment: asset handle, asset name, original file/image number, type, segment use, used shots, and notes.
- When storyboard assets are used in a specific prompt/shot, that prompt/shot must cite storyboard frame numbers and explicitly forbid storyboard marks from appearing in the final video.
- When storyboard assets are not used in a specific prompt/shot, omit all storyboard-related content completely. Do not write `故事板参考：本条不使用故事板。`, `故事板参考：无。`, `未使用故事板`, or any equivalent placeholder.
- Do not append `15秒。21:9。` or any equivalent fixed footer to every prompt.
- Every final prompt group must have explicit timing metadata: scene-relative time range, estimated duration, and internal shot durations.
- Every prompt must cover at most 15 seconds of video.
- Avoid excessive fragmentation. Prefer one coherent 8-15 second prompt over several tiny prompts when the plot beat, location, characters, and emotional movement are continuous.
- Duration and aspect ratio may appear as metadata, HTML fields, prompt header tags, or per-shot notes, but not as mandatory closing text.
- Style must come from user/materials/script analysis.
- Camera movement must track emotion.
- No generic emotions: decompose emotion into muscles, breath, eyes, skin, posture, and timing.
- Every prompt with spatial relationships must mirror the approved top-down schema.
- Spatial descriptions must include main relative relationships such as in front of, behind, left/right of, facing, occluding, next to, above/below, and distance when relevant.
- Add `⚠️` warnings for likely model failures and `⚠️⚠️⚠️` for critical failures.

## Iteration Rules

When the user requests changes after delivery:

- Edit the HTML file directly.
- If changes affect assets, invalidate and return to Asset Confirmation Gate.
- If changes affect scene/location/sub-location assignment or location assets, invalidate the Scene Asset Binding Gate and require a regenerated/passed Scene Asset Handoff before continuing.
- If changes affect positions, invalidate and return to Spatial Confirmation Gate.
- If changes affect style, invalidate and reconfirm style.
- If changes affect storyboard use or storyboard frame mapping, invalidate and return to Asset Confirmation Gate.
- If changes affect pacing, duration, scene scope, or number of prompts, invalidate and return to Timing Division Confirmation Gate.
- If changes affect delivery format, invalidate and return to Delivery Format Confirmation Gate.
- In `MANUAL_GATE_MODE`, request the corresponding user confirmation again.
- In `AUTO_GATE_MODE`, regenerate the affected artifact, rerun its independent review, update `review/video_prompt_gate_review.json`, and continue without asking unless a blocker remains after two revisions.
- Re-run HTML QA before redelivery.

## AUTO_GATE_MODE Output Map

- `assets/actual_asset_manifest.json` — enriched unique asset mapping, including current generated assets and verified reusable assets
- `assets/observed_asset_state.json` — objective visible traits extracted from all downstream-referenceable images
- `shots/shot_scene_bindings.json` — exact shot-level inheritance from Scene Asset Handoff
- `gates/shot_scene_binding_gate.json` — deterministic scene/location/asset binding validation report
- `shots/spatial_blocking.json` — AI-generated and AI-reviewed spatial plan
- `gates/environment_continuity_gate.json` — route-anchor and landmark continuity evidence
- `shots/timing_plan.json` — validated timing division, prompt count, and scene-bound grouping
- `review/video_prompt_gate_review.json` — auditable gate evidence
- `video_prompts/video_prompt_sheet.md` — final text-only video prompts
- `video_prompts/video_prompt_manifest.json` — dispatcher-ready structured clip handoff

## File Map

- `reference/ASSET_CONFIRMATION.md` — mandatory asset mapping format and gate language
- `reference/STORYBOARD_ASSETS.md` — storyboard asset rules, frame-number use, and no-markup warnings
- `reference/DELIVERY_FORMAT.md` — choose webpage or direct text prompts
- `reference/SPATIAL_BLOCKING.md` — mandatory top-down position confirmation
- `reference/HTML_QA.md` — layout QA checklist before delivery
- `reference/PROMPT_TIMING.md` — per-prompt time ranges and internal shot-duration rules
- `templates/HTML_TEMPLATE.md` — stable Chinese webpage template without rowspan/colspan
- `reference/STYLE_BLOCK.md` — user/material-derived style construction
- `reference/PROMPT_PATTERNS.md` — prompt structure and warnings
- `reference/CAMERA_EMOTION.md` — camera-emotion mapping
- `reference/MICRO_BEATS.md` — actor performance micro-beats
- `reference/PROMPT_DENSITY.md` — prompt grouping rules
- `reference/PLAN_TYPES.md` — Chinese visible shot-plan labels
- `reference/SCENE_ASSET_BINDING.md` — strict Scene Asset Planner inheritance and reuse-asset resolution rules
- `reference/VIDEO_PROMPT_HANDOFF.md` — dispatcher-ready clip manifest schema and scene-bound grouping rules
- `scripts/validate_shot_scene_bindings.py` — deterministic end-to-end binding gate
- `scripts/validate_environment_continuity.py` — deterministic route/environment continuity gate
- `templates/shot_scene_bindings.example.json` — shot inheritance example
- `templates/video_prompt_manifest.example.json` — dispatcher-ready prompt manifest example
