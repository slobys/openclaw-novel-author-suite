---
name: "external-job-dispatch-recovery"
description: "Recover failed or ambiguous job dispatches without duplicate submissions by reconciling payload, side effects, and authoritative state."
---

# External Job Dispatch Recovery

Use this procedure when a webhook, gateway, or asynchronous job dispatch fails or leaves uncertain remote state.

## Procedure

1. Establish the current submission identity.
   Record the current task ID, payload revision, expected work count, dispatcher, and any superseded task IDs. Isolate superseded tasks from retries, watches, and callbacks.
   **Check:** one task ID maps unambiguously to the current payload and every obsolete ID is marked superseded.

2. Revalidate the submission package at the execution boundary.
   Run the payload, domain, and dry-run gates separately. Resolve reused inputs through the same path the dispatcher will use, then compare their identity, size, digest, and producer completion state with the payload. Verify required endpoints and credentials with presence-only or masked checks where the dispatcher actually executes. Use only a host-owned secure entry surface for protected values; close it after verification and rotate any value exposed in a transcript or log.
   **Check:** every gate has an outcome, all resolved inputs match the payload, required runtime inputs are present, and no protected value appears in the record.

3. Submit once through the formal dispatcher.
   Preserve its structured result, receipt, or deterministic state artifact. Classify the outcome as payload rejection, pre-network failure, request possibly sent, or accepted. When validation stops at one prerequisite, mark later prerequisites untested instead of inferring their state.
   **Check:** the failure stage and prerequisite states come from dispatcher evidence.

4. Reconcile side effects before any retry.
   Inspect the submission receipt, deterministic task location, progress artifact, project checkpoint, and owner-session state for the current task ID. Treat a prepared payload or `ready_to_submit` state as a handoff state, not proof of submission. Report “not submitted,” “not queued,” or “no charge” only when authoritative evidence proves the request stopped before network activity; otherwise keep remote state unknown until reconciled.
   **Check:** concrete state artifacts either prove no side effect or identify the existing submission, so a retry cannot duplicate work.

5. Preserve a recoverable blocker when submission stopped safely.
   Record the task ID, payload revision, passed gates, failure stage, and non-secret resume condition. After readiness is restored, rerun the gates. Reuse the task ID only for an unchanged payload; assign a new ID and supersede the old one when the payload changes.
   **Check:** the pending task can resume without rebuilding its package or confusing payload revisions.

6. Classify asynchronous state without overclaiming.
   Record transport acceptance, queue admission, provider task identity, active execution, numeric progress, and completion as separate fields. HTTP success without authoritative task state is `webhook_accepted_unverified`: preserve the receipt, block retry and dependent work, and name the evidence required to promote it. Matching queued and expected counts prove queue admission only; require provider running or progress evidence for active execution, and terminal result evidence for completion.
   **Check:** every status cites evidence for that exact lifecycle stage.

7. Reconcile visible ownership and progress.
   When the workflow exposes a durable progress card, resolve its owner from the canonical card record rather than session existence or project metadata. Repair stale owner references or visible phases from the same authoritative submission evidence before reporting status. Track announcement delivery separately from the underlying state mutation.
   **Check:** one canonical owner and one latest card revision agree with the authoritative task state.

8. Install a bounded condition watch when completion is asynchronous.
   Key it to the current task ID, canonical owner, and best authoritative state source. Wake only when the status signature changes; publish numeric completed/expected progress, ignore superseded tasks, route the terminal callback to the same owner, and disable the watch after one terminal reconciliation. If durable task state does not exist yet, watch for its creation without treating the receipt as execution proof.
   **Check:** unchanged state stays silent, changed state reaches the correct owner, and the watch terminates after success or failure.

9. Reconstruct the evidence timeline on wake or apparent stall.
   Order the receipt, authoritative progress, callback ingress, continuation activity, durable checkpoint, and visible card. Classify callback delivery, continuation, validation, and persistence separately. Treat a `running` marker as advisory. Continue dependent work only after the current task ID, completion marker, and result artifact validate; exit without action for a superseded task.
   **Check:** the timeline identifies the last proven stage and one accepted task can trigger at most one continuation and no duplicate submission.
