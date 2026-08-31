# Indoor Multi-Room and Multi-Floor Protocol

Read this file for any interior with more than one functional area, any corridor route, any stair/elevator movement, or any exterior-to-interior transition.

## 1. Classification

- `INTERIOR_SINGLE_ROOM`: one enclosed/open room; no route crosses a portal.
- `INTERIOR_MULTI_ROOM`: two or more connected rooms on one level.
- `INTERIOR_MULTI_LEVEL`: route or views span two or more floor elevations.
- `MIXED_EXT_INT`: courtyard/street/garage connects to foyer/interior through a locked exterior portal.

Do not create a new Scene ID merely because the camera crosses a door inside one building. Keep one Scene ID when all zones share one fixed coordinate system. Create a new Scene ID only for a substantially separate location.

## 2. Stable hierarchy IDs

Use stable IDs independent of Chinese display names:

- `BLD01`: building or primary interior shell;
- `LV01`, `LV02`: floors/levels;
- `RM01...`: rooms and spatial zones, including corridors and landings;
- `PT01...`: doors, openings, sliding partitions, archways and thresholds;
- `STA01...`: stairs;
- `ELV01...`: elevators;
- `WIN01...`: important fixed windows when they control light or identity.

The same physical connector keeps the same ID from both sides.

## 3. Zone record

Each room/zone should define:

- level ID;
- function/name;
- world origin or boundary;
- approximate width, depth and clear height;
- principal orientation;
- floor, wall and ceiling materials;
- fixed doors/windows;
- fixed furniture anchors;
- two to four asymmetric identity fingerprints;
- neighbouring zones.

Example:

```json
{
  "id": "RM01",
  "level_id": "LV01",
  "name": "挑空客厅",
  "kind": "living-room",
  "origin_m": [0, 0, 0],
  "dimensions_m": [8.4, 6.8, 6.6],
  "orientation_deg": 0,
  "anchor_ids": ["A", "B", "C", "WIN01"],
  "fingerprints": ["电视墙右端竖向深古铜格栅", "主沙发左后角设独立弧形落地灯"]
}
```

## 4. Connector record

A portal/connector should define:

- stable ID and kind;
- source and destination zones;
- world position and orientation;
- width, height and depth/threshold;
- source-wall and destination-wall identity;
- door swing/open state or opening shape;
- frame, handle, threshold and trim material;
- two asymmetric fingerprints;
- intended sightline;
- passable subjects.

For stairs also define:

- lower and upper levels/zones;
- lower and upper landing positions;
- straight/L/U/spiral configuration;
- number of flights and intermediate landings;
- ascent direction;
- railing side/material;
- opening in slab/ceiling;
- headroom and light source.

## 5. Connectivity graph

The `SPATIAL LOCK` must contain a compact but complete graph for critical zones, for example:

```text
LV01：RM01客厅经PT01开放门洞向西连接RM02餐厅；RM01经PT02北侧门洞连接RM03走廊。
跨层：RM03北端经STA01两跑折返楼梯上行至LV02的RM04平台；RM04经PT03东侧木门连接RM05主卧。
```

No prompt may invent a missing edge. If a user asks to travel between disconnected zones, return `TOPOLOGY_GAP` and propose the smallest connector or new zone needed.

## 6. Authority assets and queue

### Multi-room, one level

1. `F01` complete floor plan
2. `C01` room/portal connectivity map
3. `E01...` important door/opening/wall elevations
4. `B01` optional blockout for open-plan/double-height complexity
5. `M01...Mxx` room Masters
6. `P01...Pxx` reverse proof views
7. `K01...` key furniture and connector assets
8. `V01...` standard cameras
9. `TRxxA/B/C` transition triplets
10. `CVxx` later custom views

### Multi-level

Add:

- one `Fxx` per level;
- `S01` vertical section/level-stack diagram;
- stair/elevator connector asset and lower/upper landing proof views.

## 7. Transition triplet protocol

### A — Approach

- source room identity is clear;
- active connector is visible and matches its asset;
- destination can be naturally glimpsed through it;
- camera remains on source side.

### B — Threshold / Landing

- camera lies on or immediately beside the connector plane;
- both source and destination geometry are compatible;
- door frame/threshold/stair railing matches A;
- no wall thickness or floor elevation contradiction.

### C — Destination reveal

- destination room becomes the main subject;
- the same connector remains behind or at one edge;
- source-room clue remains visible when physically possible;
- camera orientation proves the route rather than teleporting.

For stairs, use additional intermediate landing frames if a single threshold frame cannot explain the turn.

## 8. Room-local context in portable prompts

Keep the four global locks immutable. Add current-room detail dynamically under `WORLD RELATIONSHIPS FOR THIS VIEW`:

```text
当前楼层：LV01
当前区域：RM01客厅
来源区域：RM01客厅
目标区域：RM02餐厅
活动连接器：PT01开放门洞
合法拓扑路径：RM01 → PT01 → RM02
本机位位于PT01东侧1.5米，仍在RM01内；不得越过北侧PT02或看到被实体墙遮挡的厨房。
```

This keeps each prompt portable without rewriting the canonical four-lock payload.

## 9. Reference roles

For a room transition, prefer actual uploads:

- relevant `Fxx`: plan/topology only;
- `C01`: portal adjacency only;
- `S01`: floor heights/stair relation only;
- source-room `Mxx`: source appearance;
- destination-room `Mxx`: destination appearance;
- connector `Kxx`: exact door/opening/stair identity;
- previous accepted transition: local overlap only.

Do not upload every unrelated room image. Too many irrelevant references can weaken the current camera instruction.

## 10. Reference coverage grades

- `GREEN`: plan + both relevant room Masters + connector identity are available.
- `YELLOW`: topology is known, but one side or connector elevation is incomplete; local design may drift.
- `RED`: target room, connector or floor relation is absent; create missing F/C/S/M/K authority first.

Do not claim strong continuity for RED coverage.

## 11. Custom camera validation

A custom camera is legal only when:

- its position lies in a defined zone or connector volume;
- it is not inside a wall, cabinet, sofa or closed door leaf;
- its target has a physical sightline;
- requested visible/hidden objects agree with walls and portals;
- height and lens are plausible for the intended shot.

Apply the smallest correction if the user's position is nearly legal; explain the offset briefly.

## 12. Mixed exterior/interior

The exterior gate or front door is a connector between an exterior zone and an interior zone. Lock it from both sides:

- same width/height/frame/handle;
- same threshold and step count;
- compatible exterior and interior wall thickness;
- consistent daylight direction through the opening;
- approach, threshold and reveal assets.

## 13. Failure classes

Major failures requiring regeneration:

- a door moves to another wall;
- corridor turns the wrong way;
- destination room appears through the wrong portal;
- stair rises in the opposite direction;
- upper landing connects to the wrong room;
- furniture blocks a route that was previously passable;
- opposite-side view changes portal size or identity;
- floor height or double-height void contradicts section authority.
