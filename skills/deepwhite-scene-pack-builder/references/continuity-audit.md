# Continuity Audit and Repair

Read this file when a generated image is supplied, the user asks to check it, or reports drift.

## Score

Score each category from 0 to 5:

1. topology and world geometry — weight 30%;
2. landmark identity/fingerprints — 20%;
3. camera plausibility and required visibility — 15%;
4. style/material consistency — 15%;
5. physical light/environment — 10%;
6. moving-subject identity and route — 10% when present; otherwise redistribute to geometry.

Convert to 100.

- 90–100: lock;
- 80–89: lock with minor note if the deviation cannot contaminate later references;
- 65–79: repair/regenerate before advancing;
- below 65: reject and regenerate from permanent anchors.

Any critical failure overrides the numeric score.

## Critical failures

- road, room, gate or portal topology changed;
- main building moved or mirrored;
- fixed landmark duplicated/deleted;
- identity fingerprint moved to the wrong physical side;
- impossible camera position;
- subject teleported or crossed an obstacle;
- physical sun direction contradicts the world frame.

## Audit output

Keep it concise:

```text
结论：未通过（72/100）
关键错误：D道路在古树前错误左转；B门楼被镜像；光线问题为次要。
可保留：主屋材质、树干指纹、天气。
处理：不要把此图传给下一张；以 L01 + M01 重生 V03。
```

Then output a minimal-delta repair prompt.

## Minimal-delta repair

A repair prompt must:

1. name the exact wrong relation;
2. restate the correct world-space relation;
3. preserve everything that already passed;
4. use L01 + M01 rather than the failed image for geometry/mirror failures;
5. avoid rewriting the whole scene unless multiple critical failures exist.

Example:

```text
Regenerate V03 only. Preserve the accepted architecture, materials, season and camera height. Correct one geometry error: after leaving B_GATE, D_ROAD must continue east for 18 m and turn northeast on the far side of E_TREE; it must not turn left before the tree. Keep the chipped west gatepost and the forked trunk on their original physical sides. Use L01 as geometry authority and M01 as appearance authority. Do not use the failed V03 as a reference.
```

## Locking

When passed, record:

- asset ID;
- accepted file/reference identifier if available;
- score;
- any tolerated minor drift;
- date/sequence;
- next ready asset.
