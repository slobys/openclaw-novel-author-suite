---
name: "pre-dispatch-production-session"
description: "Initialize production sessions before formal dispatch while preserving checkpoints and preventing premature side effects."
---

# Pre-dispatch production session

Use this procedure when a production episode needs a visible owner and status before its formal dispatch arrives.

## Procedure

1. Record the project identifier, episode label, expected dispatcher, and the boundary that must remain on hold. Complete when all four intake fields are explicit.
2. Check the durable session store for a matching visible production session and read the latest project checkpoint before claiming ownership. Reuse the matching session and preserve its checkpoint state. Do not invent or record a planned session key that is absent from the store. Complete when one existing canonical session, its durable key, and one takeover point are identified.
3. Update the canonical session metadata so its label, category, and persistence state identify the exact production unit. Initialize its progress card, then verify the durable session store contains a `session_progress_cards` row for that exact key; a session that merely exists but owns no card is not a valid progress-card owner. Return the verified durable key in the downstream handoff so later producers use the same key for progress-card ownership, mirroring, and callback handoff. Complete when the visible session clearly maps to the project and episode, owns the card record, and every later owner reference names that verified key.
4. Select the progress-card state from the request. Publish the standard waiting-state card with the project identifier, formal dispatch prerequisite, and held actions; when the request explicitly requires a reset, publish an empty card instead. Complete when the returned card payload matches the selected branch.
5. Hold all production phases, external automation, and downstream dispatch until the formal dispatch event arrives. Complete when initialization has made no production-side-effect calls.
6. When the formal dispatch arrives, re-read the project checkpoint, lock state, external-submission evidence, and live session trajectory immediately before the first project write. Compare these authoritative planes with the visible session and progress card; treat a visible `running` marker as advisory rather than proof of active execution. If dispatch receipt is confirmed but the expected dispatcher has not yet created the initial project checkpoint, keep the visible session read-only, publish a waiting-for-checkpoint state, and wait for its handoff; a missing checkpoint alone does not clear takeover. If the authoritative state is terminal, verify its completion status, completed progress state, closed-card flag, successful output evidence, failure count, and next-dispatch boundary. Mirror that terminal state only into the canonical progress card; make no project writes or dispatch calls. Otherwise, if any checkpoint or trajectory changed since the takeover read, treat the dispatcher as active: mirror the new authoritative state, make no project writes or dispatch calls, and wait for its next handoff. Complete when dispatch initialization is held read-only pending its first checkpoint, terminal closure is reconciled without crossing its dispatch boundary, active ownership is confirmed from durable activity, or one unchanged checkpoint is cleared for takeover.
7. Recover an unchanged checkpoint with a stale owner marker from the earliest incomplete phase. Reverify that phase's gate, reuse any prepared payload and job identifier, and check the task output and callback evidence for prior side effects before submitting. Preserve the existing submission if side effects exist; submit once only when they are absent. Synchronize the visible progress card from the resulting durable state. Complete when recovery either adopts the proved existing submission or advances once from a side-effect-safe phase with the card aligned.
8. Build one concise visible confirmation from the returned session and card state. Include the canonical project identifier, the actual waiting or empty state, and the held actions; do not infer a status absent from the result. Complete when exactly one final confirmation matches the tool response.

## Verification

Confirm that the visible session maps to the requested production unit, the card is either the requested empty state or names the same unit, the checkpoint remains available for takeover, and no work beyond session initialization has started.
