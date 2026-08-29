# Upgrade to 0.4.5

0.4.5 fixes repeat installation on existing OpenClaw agents.

## Fixed

- Reads the real agent roster through `openclaw agents list --json`.
- Reuses the existing `novel-author` workspace instead of writing a version-specific agent config path.
- Supports both array and object-shaped agent-list JSON responses.
- Stops on an explicit workspace override conflict instead of silently moving an existing agent.
- Adds a repeat-install regression test while preserving memory and project data.

No novel project schema changed. Existing chapters, sessions, memory, Closure records and ledgers remain compatible.
