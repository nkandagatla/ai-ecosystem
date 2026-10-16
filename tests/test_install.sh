#!/usr/bin/env bash
# Every profile x target x scope in temp dirs: layout, idempotency, update, clean uninstall; plus the interactive flow.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; fail=0
chk(){ [ -e "$1" ] || { echo "MISSING $1"; fail=1; }; }
run(){ "$ROOT/install.sh" "$@" </dev/null >/dev/null 2>&1; }
for scope in project user; do
for prof in general web-app testing iac; do
  for ide in claude codex cursor copilot windsurf; do
    [ $scope = user ] && [ $ide = copilot ] && continue
    T=$(mktemp -d); echo "# mine" > "$T/AGENTS.md"; mkdir -p "$T/.claude" && echo "# mine" > "$T/.claude/CLAUDE.md"
    ARGS=(--target $ide --profile $prof --scope $scope --yes); [ $scope = user ] && ARGS+=(--home "$T") || ARGS+=(--dir "$T")
    run "${ARGS[@]}"
    if [ $scope = project ]; then
      chk "$T/AGENTS.md"; grep -q "# mine" "$T/AGENTS.md" || { echo "clobbered"; fail=1; }
      case $ide in
        claude) chk "$T/.claude/agents/developer.md"; chk "$T/CLAUDE.md"; chk "$T/.claude/skills/code-review-checklist/SKILL.md";;
        codex) chk "$T/.codex/skills/code-review-checklist/SKILL.md";;
        cursor) chk "$T/.cursor/agents/developer.md"; chk "$T/.cursor/rules/ai-ecosystem.mdc";;
        copilot) chk "$T/.github/copilot-instructions.md"; chk "$T/.github/agents/developer.agent.md";;
        windsurf) chk "$T/.windsurf/rules/ai-ecosystem.md";;
      esac
    else
      case $ide in
        claude) chk "$T/.claude/agents/developer.md"; grep -q "ai-ecosystem:begin" "$T/.claude/CLAUDE.md" || { echo "no block"; fail=1; };;
        codex) chk "$T/.codex/AGENTS.md"; chk "$T/.codex/skills/code-review-checklist/SKILL.md";;
        cursor) chk "$T/.cursor/agents/developer.md"; chk "$T/.cursor/skills/code-review-checklist/SKILL.md";;
        windsurf) chk "$T/.codeium/windsurf/memories/global_rules.md";;
      esac
    fi
    run "${ARGS[@]}"
    for f in $(grep -rl 'ai-ecosystem:begin' "$T" 2>/dev/null || true); do [ "$(grep -c 'ai-ecosystem:begin' "$f")" = 1 ] || { echo "duplicate block $f"; fail=1; }; done
    run "${ARGS[@]/--yes/--update}" --yes || { echo "update failed"; fail=1; }
    UA=(--uninstall --scope $scope); [ $scope = user ] && UA+=(--home "$T") || UA+=(--dir "$T")
    run "${UA[@]}"
    left=$(find "$T" -type f ! -name AGENTS.md ! -path "*/.claude/CLAUDE.md")
    [ -z "$left" ] || { echo "files left ($scope/$prof/$ide): $left"; fail=1; }
    for f in "$T/AGENTS.md" "$T/.claude/CLAUDE.md"; do [ "$(cat "$f" 2>/dev/null || echo '# mine')" = "# mine" ] || { echo "residue $f"; fail=1; }; done
    rm -rf "$T"
  done
done; done
# dry-run writes nothing
T=$(mktemp -d); run --target all --profile general --yes --dry-run --dir "$T"; [ -z "$(ls -A "$T")" ] || { echo "dry-run wrote files"; fail=1; }
# interactive flow via a pty: scope=project, targets 1,3 (claude,cursor), profile 2 (testing), no customize, proceed
if command -v script >/dev/null; then
  printf '1\n1,3\n3\nn\ny\n' | script -qec "$ROOT/install.sh --dir $T" /dev/null >/dev/null 2>&1 || true
  chk "$T/.claude/agents/tester.md"; chk "$T/.cursor/agents/tester.md"; [ ! -e "$T/.windsurf" ] || { echo "interactive over-installed"; fail=1; }
fi
[ $fail = 0 ] && echo "ALL TESTS PASSED" || { echo FAILED; exit 1; }
