---
name: "episode-production-closure"
description: "Verify a completed episode and series boundary before closing progress or allowing another episode dispatch."
---

# Episode Production Closure

Use this procedure when an episode reports completion and the production must stop at that episode or close a series boundary.

## Procedure

1. Read the declared stop boundary and dispatch policy before checking outputs. Record whether the next episode is held for an explicit user command; the boundary and next-dispatch rule are unambiguous.

2. Verify the final video through separate technical and content-acceptance gates. Confirm the expected file exists and capture its resolution, aspect ratio, duration, size, and checksum. Compare the result with the approved direction and latest user review. If a substantive content issue remains, restore progress to pending correction and preserve the next-dispatch hold; closure is eligible only when both gates pass.

3. Reconcile generation totals and assembly coverage with the final artifact. For a partial rerender, verify the final manifest includes every retained shot plus each replacement in the intended order; treat replacement-job success as input completion, not episode completion. Match every completion marker and composed artifact to its scope, and require episode-level assembly evidence before accepting the episode. Confirm expected outputs, completed outputs, and failures agree with the episode result; the manifest accounts for every required shot and no unexplained output or failure remains.

4. Verify the episode and series state separately. Confirm the episode is complete, then confirm any required series commit has a completion status, marker, and timestamp; both lifecycle layers have evidence.

5. Reconcile progress-card state with production state. Confirm the card is closed, no waiting step or blocked reason remains, and ownership or callback handoff points to the intended production session; the status surfaces agree.

6. Prove the dispatch boundary from authoritative queue and gate state. When the next episode requires an explicit user command, confirm it is absent from both ready and running queues, reconcile the queue's running count with those entries, and confirm the next-episode gate records that hold. Also confirm no duplicate submission occurred; closure has not created an unintended downstream job.

7. Report only the verified closure facts: artifact summary, generation totals, episode and series completion, progress closure, dispatch status, and current pause or handoff state. The report contains evidence for every closure claim and no claim of future work.
