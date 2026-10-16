#!/usr/bin/env bash
# Installs every profile x IDE into temp dirs and asserts native layout; also tests idempotency and uninstall.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; fail=0
chk(){ [ -e "$1" ] || { echo "MISSING $1"; fail=1; }; }
for prof in general web-app testing infrastructure-as-code; do
  for ide in cursor claude copilot windsurf; do
    T=$(mktemp -d); echo "# mine" > "$T/AGENTS.md"
    "$ROOT/install.sh" --ide $ide --profile $prof --target "$T" >/dev/null
    chk "$T/AGENTS.md"; grep -q "# mine" "$T/AGENTS.md" || { echo "clobbered AGENTS.md"; fail=1; }
    case $ide in
      cursor) chk "$T/.cursor/agents/developer.md"; chk "$T/.cursor/rules/ai-ecosystem.mdc";;
      claude) chk "$T/.claude/agents/developer.md"; chk "$T/CLAUDE.md"; chk "$T/.claude/skills/code-review-checklist/SKILL.md" ;;
      copilot) chk "$T/.github/copilot-instructions.md"; chk "$T/.github/agents/developer.agent.md";;
      windsurf) chk "$T/.windsurf/rules/ai-ecosystem.md";;
    esac
    "$ROOT/install.sh" --ide $ide --profile $prof --target "$T" >/dev/null   # idempotent
    [ "$(grep -c 'ai-ecosystem:begin' "$T/AGENTS.md")" = 1 ] || { echo "duplicate block"; fail=1; }
    "$ROOT/install.sh" --uninstall --target "$T" >/dev/null
    [ "$(cat "$T/AGENTS.md")" = "# mine" ] || { echo "uninstall left residue ($prof/$ide)"; fail=1; }
    [ -z "$(find "$T" -type f ! -name AGENTS.md)" ] || { echo "files left ($prof/$ide)"; find "$T" -type f; fail=1; }
    rm -rf "$T"
  done
done
[ $fail = 0 ] && echo "ALL TESTS PASSED" || { echo FAILED; exit 1; }
