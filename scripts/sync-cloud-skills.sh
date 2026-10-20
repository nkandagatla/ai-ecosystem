#!/usr/bin/env bash
# Fetch nkandagatla/ai-cloud-skills at the commit pinned in vendor.lock (use --latest to move the pin).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
exec python3 "$ROOT/scripts/ai_ecosystem.py" sync "$@"
