# Scene Package Workflow

Read this file when creating a new scene, changing geometry, resuming from a manifest or exporting a full package.

## 1. Manifest content

A complete scene state contains:

- schema, Scene ID and revisions;
- user brief and inferred defaults;
- structured style/world/environment locks;
- a sealed Portable Hard-Lock `canonical_prompt_lock` whose four bodies are reused verbatim in every asset prompt;
- landmarks with world positions, dimensions and fingerprints;
- topology connections and zones;
- moving route/action axis when relevant;
- camera ledger;
- asset queue, dependencies, references, status and audit history.

Use `assets/scene-manifest.template.json` as the structure source.

## 2. Scene scope and geometry class

Choose the smallest scene that can remain one physical coordinate system.

- `SIMPLE_FLAT`: courtyard, village gate, straight street → L01 + M01.
- `COMPLEX_3D`: cliffs, multi-level temple, suspended platforms → L01 + B01 + M01.
- `INTERIOR_SINGLE_ROOM`: one room → F01 + optional E01/B01 + M01 + P01.
- `INTERIOR_MULTI_ROOM`: connected rooms on one level → F01 + C01 + per-zone M/P + transition triplets.
- `INTERIOR_MULTI_LEVEL`: one Fxx per floor + C01 + S01 + stair/elevator assets + per-zone M/P.
- `MIXED_EXT_INT`: exterior and interior zones joined by an explicitly locked gate/door portal.
- `MULTI_ZONE_EXTERIOR`: route spans distinct exterior areas → Z01 zone map + per-zone geometry/master + transition views.

Do not force a house interior, distant village and mountain valley into one Master merely because one action travels through them.

## 3. Coordinate system

Choose an obvious origin, usually the principal entrance centre or main-room centre.

Default:

- X increases east/right in the top-down plan;
- Y increases north/up;
- Z is elevation;
- unit is metres.

Coordinates are planning constraints, not survey data. For interiors include fixed `LVxx`, `RMxx`, `PTxx` and `STAxx/ELVxx` records. Every connector must have two valid endpoints and a world-space position.

## 4. Landmarks and scale

Create five to eight landmarks for most scenes. Each includes:

- ID and anchor type;
- world position/region;
- orientation and approximate dimensions;
- appearance/material;
- two to four immutable asymmetric fingerprints;
- expected views.

At least three major landmarks should form a non-collinear anchor triangle. Also lock a human-scale reference, door height, path width and major object sizes.

## 5. Topology

Represent traversable connections explicitly:

```json
{
  "from": "B_GATE",
  "to": "D_ROAD_BEND",
  "kind": "dirt-road",
  "width_m": 3.2,
  "direction": "east then northeast",
  "passable_by": ["person", "ox-cart"]
}
```

Prompts must not invent a connection absent from the topology graph. For multi-room interiors, validate graph reachability and preserve the same portal ID when seen from both sides.

## 6. Environment state

Lock physical state:

- time, season and weather;
- visibility and ground state;
- wind when cloth/foliage matters;
- sun azimuth/elevation in world coordinates;
- artificial light emitters.

A camera move changes screen appearance, not physical light.

## 7. Portable Hard-Lock Canonical Prompt

Create four compact immutable text fields:

- `style_lock_text`;
- `scene_dna_lock_text`;
- `spatial_lock_text`;
- `continuity_lock_text`;
- `lock_id` after sealing.

Every final asset prompt first includes `【PORTABLE HARD LOCK｜独立可用｜禁止删减】` and `LOCK_ID`, then maps these fields exactly to:

- `【STYLE LOCK｜固定原文】`;
- `【SCENE DNA｜固定原文】`;
- `【SPATIAL LOCK｜固定原文】`;
- `【CONTINUITY LOCK｜固定原文】`.

This is not the full Manifest. It is a stable, portable copy block designed to be pasted into every asset prompt and into another model with no chat history. Never regenerate or paraphrase its wording between assets. Reference images remain additive.

## 8. Camera ledger

Each camera needs:

- position/target;
- height, yaw/pitch and approximate FOV;
- shot size;
- visible and physically occluded anchors;
- anchors shared with previous view;
- continuity purpose;
- screen direction and action-axis side when relevant.

Adjacent views normally share at least two anchors. If physically impossible, use one portal/path anchor plus one distant anchor.

## 9. Dynamic queue

Use semantic IDs rather than fragile fixed numbering.

Core gates:

- `L01`, `F01...Fxx` or `Z01` — plan/geometry authority;
- `C01` — room/portal connectivity authority;
- `S01` — level-stack/stair section authority;
- `B01` — blockout/elevation authority only when required;
- `M01...Mxx` — appearance authority per zone;
- `P01...Pxx` — reverse/oblique proof views;
- `TRxxA/B/C` — source approach, threshold/landing and destination reveal.

Then add only useful assets:

- `A01...` key landmark close-ups;
- `V01...V06` final views;
- `SUB01` subject sheet;
- `R01` route/camera plan;
- `SH01...` continuous shot frames;
- `C01` contact sheet when references are limited.

Do not generate meaningless assets merely to reach a fixed count.

## 10. Dependencies

- M01 depends on accepted geometry authority and B01 when B01 is required;
- P01 depends on geometry + M01;
- final views depend on geometry + M01 + P01;
- shots depend on corresponding accepted view + SUB01 and previous accepted shot when relevant.

Only accepted assets can be stable references.

## 11. First response

Show:

- Scene ID, name, style, ratio, geometry class and inferred defaults;
- concise anchor table and route/action-axis summary;
- camera plan summary;
- asset queue;
- first asset reference card and complete Portable Hard-Lock Prompt containing the banner, Lock ID and all four lock blocks.

Keep the full Manifest hidden unless requested or saved. Compile the final Prompt from the sealed payload when tools exist; never hide, omit or paraphrase the banner, Lock ID or four lock blocks.

## 12. Resume

On `继续 <scene-id>`:

1. load `scene-packs/<scene-id>/scene.json`;
2. validate it; if sealed, verify `lock_id`;
3. show current asset, accepted authorities and blockers;
4. emit the next ready prompt only;
5. never rebuild Scene DNA from memory.


## 13. Indoor graph validation

For `INTERIOR_MULTI_ROOM`, `INTERIOR_MULTI_LEVEL` or `MIXED_EXT_INT`, read `{baseDir}/references/indoor-multizone.md`. Before sealing, validate all level, zone and connector IDs; confirm the graph is connected for required routes; and ensure floor-plan/connectivity/section authorities exist where required.
