#!/usr/bin/env bash
# ai-ecosystem installer (from a git checkout). Interactive by default.
#   ./install.sh                                   # guided: targets, scope, profile
#   ./install.sh --target claude,cursor --profile web-app --scope project --yes [--sync] [--dry-run]
#   ./install.sh uninstall | update | validate | sync | list
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
command -v python3 >/dev/null || { echo "python3 (3.8+) is required" >&2; exit 1; }
exec python3 "$ROOT/scripts/ai_ecosystem.py" "$@"
