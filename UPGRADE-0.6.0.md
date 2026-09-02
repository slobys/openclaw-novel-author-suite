# Upgrade to Novel Engine 0.6.0

Novel Engine 0.6.0 is a performance release on top of the recoverable 0.5.0 finalizer. It does not remove the 17-category chapter audit, either independent reviewer, canonical body-hash binding, Quality, Commit, Closure or Integrity.

## What changed

- `novel_prepare_chapter` defaults to `balanced-fast` and creates one reusable context snapshot for all three role packets.
- Writer, Continuity Auditor and Reader Editor packets have hard character caps of 16,000, 8,000 and 6,000.
- Passing checks use compact `"pass"` values; descriptions and repair evidence belong in `issues`.
- The two reviewers may run in parallel after the final body hash is frozen.
- `novel_finalize_chapter` accepts `productionProfile: "balanced-fast"` and runs chapter-scoped Integrity on ordinary chapters.
- Full-project Integrity still runs for chapter 1, every fifth chapter, strict mode and explicit diagnostics.

## Compatibility

- Engine schema remains version 2.
- Existing projects, chapters, ledgers, receipts and request IDs remain valid.
- `productionProfile` defaults to `strict` when omitted so older callers retain the previous full-project Integrity behavior.
- No project-data migration is required.

## Safe rollout

1. Stop active writing jobs and confirm the last committed chapter has complete Closure.
2. Run the fixed-tag installer.
3. Start a fresh Novel Author main session so it receives the updated workflow and tool schemas.
4. Confirm `novel_prepare_chapter` returns `profile: "balanced-fast"` and packet-size metadata.
5. Use `productionProfile: "balanced-fast"` only through the V6.1 Agent workflow.

Rollback is safe because this release does not change the persisted project schema.
