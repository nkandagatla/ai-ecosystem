#!/usr/bin/env bash
# ai-ecosystem installer. Usage: ./install.sh --ide cursor,claude --profile web-app [--target DIR] [--sync] [--dry-run] [--uninstall]
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
command -v python3 >/dev/null || { echo "python3 is required" >&2; exit 1; }
for a in "$@"; do [ "$a" = "--sync" ] && "$ROOT/scripts/sync-cloud-skills.sh"; done
exec python3 "$ROOT/scripts/ai_ecosystem.py" "$@"
