#!/usr/bin/env bash
# Runs the full test suite (kept for CI/backward compatibility).
set -euo pipefail
cd "$(dirname "$0")/.."
python3 scripts/ai_ecosystem.py validate
python3 -m unittest discover -s tests -v
