---
name: "openclaw-missing-reply-diagnosis"
description: "Diagnose OpenClaw replies that disappear or fail to persist by correlating model completion, transcript storage, and Gateway evidence."
---

# Diagnose Missing OpenClaw Assistant Replies

Use this procedure when an assistant reply streams briefly, disappears after reload, or is absent from session history.

## Procedure

1. Identify the affected session and time window.
   Record the agent, session, adjacent user messages, and timestamps needed to correlate evidence.
   Complete when one exact message window is selected.

2. Check whether generation completed.
   Inspect the native model rollout or task record for a complete assistant payload and completion marker in that window.
   Complete when generation is classified as present or absent from direct model evidence.

3. Check canonical transcript persistence.
   Inspect the OpenClaw session store for the same window and compare event order around the adjacent user messages.
   Complete when the corresponding assistant event is found or its absence is demonstrated.

4. Correlate Gateway evidence.
   Review Gateway events at matching timestamps for session-history, transcript-mirror, or harness-hook errors.
   Use these events to localize the failing boundary rather than as sole proof.
   Complete when relevant Gateway evidence is linked to the same message window or explicitly found absent.

5. Rule out broad storage damage.
   Run the supported SQLite integrity check and OpenClaw health diagnostics, including plugin diagnostics when the affected path uses a plugin.
   Complete when database integrity and relevant health checks have recorded outcomes.

6. Classify the failure from the combined evidence.
   - Missing native payload: investigate generation or model execution.
   - Native payload present but assistant transcript event absent: investigate transcript mirroring or persistence.
   - Native payload and transcript event present but the reply is not rendered after reload: investigate history retrieval or presentation.
   Complete when the classification cites at least two independent evidence layers.

7. Report the narrowest supported conclusion and verification gate.
   State what completed, where the reply stopped, and which evidence proves that boundary.
   Treat any unexecuted repair as a proposed next step, and verify a repair only after a fresh reply appears in the native rollout, persisted transcript, and reloaded client history.
   Complete when the report separates diagnosis, proposed action, and post-repair proof.

## Evidence Matrix

| Layer | Question | Strong evidence |
|---|---|---|
| Native rollout | Did the model generate the reply? | Complete assistant payload plus completion marker |
| Session store | Was the reply persisted? | Assistant event in the expected sequence |
| Gateway | Where did handoff fail? | Timestamp-correlated mirror, history, or hook event |
| Client reload | Can history reproduce the reply? | Reply remains visible after history reload |

A transient streamed rendering shows delivery in progress; it does not prove durable transcript persistence.
