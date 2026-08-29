# Security

## Trust boundary

OpenClaw plugins execute inside the Gateway process. Review `install.sh`, the pinned Git tag and the plugin source before installation. The one-click command intentionally uses a versioned URL instead of `main`.

## Data handling

The installer never uploads project data. It does not copy or delete `memory/`, `exports/`, `.novel-runtime/`, sessions, credentials or `~/.openclaw/data/novels`.

## Reporting

Please open a GitHub security advisory for vulnerabilities. Do not include API keys, private novel content, session transcripts or a complete `openclaw.json` in public issues.
