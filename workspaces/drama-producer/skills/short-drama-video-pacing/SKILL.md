---
name: "short-drama-video-pacing"
description: "Diagnose and retune slow short-drama videos using beat density, timing constraints, and safe stale-output invalidation."
---

# Short-Drama Video Pacing

Use this procedure when character reactions, actions, or dialogue pauses make a generated short drama feel slow.

## Procedure

1. Record the project’s current generation and dispatch state before editing pacing controls. Complete when existing timing and prompt artifacts are identified and paused, dispatched, and undispatched work is explicitly accounted for.

2. Audit a representative completed episode or prompt set. Calculate total duration, count internal shots or action beats, derive average seconds per beat, and list wording that stretches reactions or actions. When the complaint spans episodes, also trace the planned location sequence across episode boundaries and count the environment references used by each episode. Complete when the diagnosis distinguishes local timing from repeated-location or over-fragmented story structure with measurements and artifact evidence.

3. Separate camera motion, environmental motion, in-place performance, and character displacement. For each intended travel beat, compare the character with a stable background landmark from start to end, count explicit displacement verbs, and identify blocking language that fixes the character in place; treat pans, zooms, and shot-size changes as camera motion rather than displacement. If the prompt suppresses travel required by the source, revise the blocking; if the episode source contains no travel because the journey is divided across boundaries, revise the episode partition instead of inventing movement. Complete when every motion beat is classified and the prompt’s positional change agrees with the source’s location progression.

4. Define a measurable pacing profile using the baseline below as the evidenced starting point. Assign each shot or beat at least one function: advance conflict, release information, deliver payoff, complete a reversal, or land a necessary emotion. Delete, merge, or compress beats that only display beauty or prolong an inert reaction. Complete when every retained beat has a named function and every applicable reaction, action, pause, beat-density, and wording constraint has a numeric limit or explicit exception rule.

5. Apply the same profile to every active workflow constraint and prompt-authoring instruction that governs video generation. Complete when the controlling locations agree on the pacing values and exceptions.

6. Invalidate timing plans and video prompts derived under the previous profile while preserving source story content and the current dispatch state. Complete when stale derived artifacts are marked for regeneration and no paused or undispatched work has been submitted accidentally.

7. Validate configuration and project state before any dispatch. Complete when the pacing controls load successfully, stale artifacts remain invalidated, and the recorded dispatch state is unchanged.

8. Regenerate and remeasure a representative prompt or segment before declaring the pacing change effective. Complete when it meets the selected profile, or when the result is explicitly labeled provisional because no regenerated sample is available.

## Baseline fast-drama profile

- Ordinary reaction: 0.3–0.8 seconds.
- Important reaction: 0.8–1.5 seconds.
- Ordinary action: 0.5–1.5 seconds.
- Ordinary dialogue pause: at most 0.2 seconds before and 0.3 seconds after.
- A 10–15 second segment: usually 4–6 internal shots or action beats.
- An ordinary reaction: at most 1–2 micro-performances.
- Slow-language cues such as “slowly,” “gradually,” or “extremely slowly”: reserve for climaxes or explicit dramatic holds.
- Environmental motion may remain slow; the character’s primary action and reaction follow the selected timing limits.
