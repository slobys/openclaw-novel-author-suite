#!/usr/bin/env bash
set -Eeuo pipefail

REPOSITORY="slobys/openclaw-novel-author-suite"
NOVEL_REF="${NOVEL_AUTHOR_INSTALL_REF:-v0.4.5}"
DRAMA_REF="${DRAMA_PIPELINE_INSTALL_REF:-drama-v1.1.0}"
choice="${1:-}"

log() { printf '[openclaw-suite-selector] %s\n' "$*"; }
die() { printf '[openclaw-suite-selector] ERROR: %s\n' "$*" >&2; exit 1; }

if [[ -z "${choice}" ]]; then
  if [[ ! -r /dev/tty ]]; then
    die "No interactive terminal. Run again with: bash -s -- 1, 2, 3 or 4"
  fi
  {
    printf '\n请选择操作：\n'
    printf '  1) 安装/更新 小说创作版\n'
    printf '  2) 安装/更新 小说转 AI 漫剧版\n'
    printf '  3) 安全卸载 小说创作版\n'
    printf '  4) 安全卸载 小说转 AI 漫剧版\n'
    printf '\n请输入 1、2、3 或 4：'
  } >/dev/tty
  IFS= read -r choice </dev/tty
fi

case "${choice}" in
  1)
    name="安装/更新：小说创作版"
    action="install"
    script_url="https://raw.githubusercontent.com/${REPOSITORY}/${NOVEL_REF}/install.sh"
    ;;
  2)
    name="安装/更新：小说转 AI 漫剧版"
    action="install"
    script_url="https://raw.githubusercontent.com/${REPOSITORY}/${DRAMA_REF}/install.sh"
    ;;
  3)
    name="安全卸载：小说创作版"
    action="uninstall"
    script_url="https://raw.githubusercontent.com/${REPOSITORY}/${NOVEL_REF}/uninstall.sh"
    ;;
  4)
    name="安全卸载：小说转 AI 漫剧版"
    action="uninstall"
    script_url="https://raw.githubusercontent.com/${REPOSITORY}/${DRAMA_REF}/uninstall.sh"
    ;;
  *)
    die "Invalid choice: ${choice}. Please enter 1, 2, 3 or 4."
    ;;
esac

log "Selected: ${name}"
log "Script: ${script_url}"

if [[ "${OPENCLAW_SUITE_SELECTOR_DRY_RUN:-0}" == "1" ]]; then
  exit 0
fi

if [[ "${action}" == "uninstall" && "${OPENCLAW_SUITE_CONFIRM_UNINSTALL:-0}" != "1" ]]; then
  if [[ ! -r /dev/tty ]]; then
    die "Uninstall requires confirmation. Set OPENCLAW_SUITE_CONFIRM_UNINSTALL=1 and run again."
  fi
  {
    printf '\n安全卸载会移除或停用公共程序文件，但保留项目、正文、memory、会话和生成结果。\n'
    printf '确认继续吗？请输入 y 或 N：'
  } >/dev/tty
  IFS= read -r confirm </dev/tty
  case "${confirm}" in
    y|Y|yes|YES) ;;
    *) log "Cancelled."; exit 0 ;;
  esac
fi

command -v curl >/dev/null 2>&1 || die "Missing required command: curl"
command -v bash >/dev/null 2>&1 || die "Missing required command: bash"
curl -fsSL "${script_url}" | bash
