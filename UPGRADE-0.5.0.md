# Upgrade to Novel Engine 0.5.0

0.5.0 is based on the complete 0.4.10 implementation. It does not replace the existing Audit, Quality, Commit, Closure or Integrity gates.

## New tool

`novel_finalize_chapter` provides one recoverable entry for the post-writer production chain:

```text
17-category Audit -> independent Quality -> idempotent Commit
-> durable ledgers/state/memory -> Closure -> Integrity
```

The tool first reconciles `requestId`. If Commit already succeeded, it verifies the canonical body hash and resumes from durable derived records without generating or reviewing the chapter again.

This is intentionally described as `recoverable-idempotent`, not as a database-wide atomic transaction. Every underlying write continues to use the proven project lock, CAS, request receipt and crash-recoverable commit implementation from 0.4.10.

## Compatibility

- Existing projects and novel data remain in place.
- Engine schema remains `2`.
- Default writing contract remains `2000 / 2600 / 3200` Han characters.
- Existing 34-step manual production remains supported as a fallback.
- Do not delete project data during upgrade or uninstall.

## Verification

```bash
npm run verify
npm run pack:check
openclaw config validate
openclaw plugins inspect novel-engine --runtime --json
```

The runtime inventory must include `novel_finalize_chapter` in addition to the existing Novel Engine tools.
