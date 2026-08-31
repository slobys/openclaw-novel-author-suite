---
name: "resumable-workflow-handoff"
description: "Resume paused or asynchronous multi-stage creative workflows from validated checkpoints through controlled continuation and closure."
---

# Resumable Workflow Handoff

Use this procedure when a multi-stage creative workflow must continue asynchronously or resume after a pause or interruption.

1. Define the completion target and control boundary. Record artifact-level acceptance checks, durable constraints, the explicit stop boundary, and excluded actions. Convert requirements such as dimensions or aspect ratio into checks against produced artifacts. **Check:** durable project state names the target, checks, boundary, and exclusions.

2. Checkpoint each stage atomically. Store outputs, stage status, validation evidence, and the first unfinished stage in one durable progress record. Classify each stage as completed, partial, not started, running, or held without relying on chat history. **Check:** the checkpoint has one unambiguous resume cursor and evidence for every completed stage.

3. Apply control changes before reporting them. For a pause, stop or hold owned workers, queue entries, and continuation watches that could cross the boundary; verify downstream submission state; retain validated artifacts and prepared job packages. For a stage remake, freeze the superseded branch, recoverably archive its assets and uncommitted jobs, retain only permitted continuity references, create fresh context at the requested phase, and hold later stages. **Check:** unavoidable activity is listed, no superseded entry can run, only the intended entry remains active, and the checkpoint names retained and archived material.

4. Validate the handoff before dispatch. Confirm that every claimed artifact exists and passes its stage gate. Persist a continuation contract beside the checkpoint containing the project location, governing procedure, progress owner, delivery target, authoritative workflow or job identifier, first unfinished stage, durable constraints, stop boundary, and permission for the next dispatch. If dispatch creates an identifier, add it before the turn ends. **Check:** durable state identifies the validated checkpoint, accepted job, record to close, delivery target, and dispatch boundary.

5. Arrange continuation when the workflow will outlive the foreground turn. Use an available push-based completion or watch path routed to the recorded delivery target. Track these states separately:
   - **Accepted:** the control plane acknowledged the continuation.
   - **Live:** the callback or watch path remains active.
   - **Processing:** downstream evidence identifies the active stage, such as an executor-issued task identifier, output location, or processing manifest.
   Treat hook receipt or a phase-start label without downstream evidence as accepted, not processing. Reconcile durable state with one queue or control-plane snapshot, including the active stage, completed and active counts, next-stage cursor, and entries beyond the stop boundary. **Check:** continuation is accepted, execution claims cite stage-linked evidence, durable state and the control plane agree, and no entry crosses the boundary.

6. Resume from durable evidence. Reread the governing procedure, continuation contract, and checkpoint. Corroborate callback evidence with workflow state, rerun relevant artifact gates, and inventory completed, running, pending, and held outputs. Continue at the first unfinished stage without repeating validated work; keep later stages held until their boundary opens. **Check:** callback evidence, gate results, queue state, and the resume cursor agree before checkpoint advancement.

7. Report only the highest state proved at each execution layer. Distinguish preparation, dispatch, active stage work, downstream submission, downstream generation, and final completion when those layers exist. Advance each layer only from its own evidence: a running queue plus stage artifacts may prove active stage work while an unsubmitted downstream job remains not started. Include the continuation identifier when available, scope completion counters to their bounded objective, and name the unfinished stage and next trigger. **Check:** the headline and details agree, every status names its layer and evidence, and no upstream state is presented as downstream or final completion.

8. Close and deliver idempotently. After the final artifact passes its gates, mark waiting steps complete, persist closure time and completed state, and remove obsolete continuation watches. If legacy checkpoints lack an owner, match records by stable workflow identifier, close each matching record waiting only for the final artifact, and persist the resolved owner. Resolve artifact links in the recipient's active workspace; create and verify a review copy there when a source is outside it. Deliver through the recorded path. **Check:** repeated closure preserves the completed state, no matching record remains waiting, no obsolete watch remains active, every link is previewable, and delivery states the final checkpoint and excluded actions.
