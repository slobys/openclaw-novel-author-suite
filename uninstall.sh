#!/usr/bin/env bash
set -Eeuo pipefail

log() { printf '[novel-author-suite] %s\n' "$*"; }
command -v openclaw >/dev/null 2>&1 || { log 'OpenClaw is not installed.'; exit 1; }

openclaw plugins disable novel-engine >/dev/null 2>&1 || true
openclaw plugins uninstall novel-engine --force
openclaw config validate

if openclaw gateway restart --help 2>&1 | grep -q -- '--safe'; then
  openclaw gateway restart --safe
else
  openclaw gateway restart
fi

log 'Novel Engine removed.'
log 'The novel-author workspace, sessions and novel project data were intentionally preserved.'
