#!/usr/bin/env bash
set -Eeuo pipefail

REPOSITORY="slobys/openclaw-novel-author-suite"
NOVEL_REF="${NOVEL_AUTHOR_INSTALL_REF:-v0.4.5}"
DRAMA_REF="${DRAMA_PIPELINE_INSTALL_REF:-drama-v1.0.1}"
choice="${1:-}"

log() { printf '[openclaw-suite-selector] %s\n' "$*"; }
die() { printf '[openclaw-suite-selector] ERROR: %s\n' "$*" >&2; exit 1; }

if [[ -z "${choice}" ]]; then
  if [[ ! -r /dev/tty ]]; then
    die "No interactive terminal. Run again with: bash -s -- 1  or  bash -s -- 2"
  fi
  {
    printf '\n请选择要安装的版本：\n'
    printf '  1) 小说创作版（Novel Author + Novel Engine）\n'
    printf '  2) 小说转 AI 漫剧版（Novel Producer + Drama Producer + 9 Skills）\n'
    printf '\n请输入 1 或 2：'
  } >/dev/tty
  IFS= read -r choice </dev/tty
fi

case "${choice}" in
  1)
    name="小说创作版"
    installer_url="https://raw.githubusercontent.com/${REPOSITORY}/${NOVEL_REF}/install.sh"
    ;;
  2)
    name="小说转 AI 漫剧版"
    installer_url="https://raw.githubusercontent.com/${REPOSITORY}/${DRAMA_REF}/install.sh"
    ;;
  *)
    die "Invalid choice: ${choice}. Please enter 1 or 2."
    ;;
esac

log "Selected: ${name}"
log "Installer: ${installer_url}"

if [[ "${OPENCLAW_SUITE_SELECTOR_DRY_RUN:-0}" == "1" ]]; then
  exit 0
fi

command -v curl >/dev/null 2>&1 || die "Missing required command: curl"
command -v bash >/dev/null 2>&1 || die "Missing required command: bash"
curl -fsSL "${installer_url}" | bash
