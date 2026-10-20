#!/usr/bin/env bash
# One-liner installer:
#   curl -fsSL https://raw.githubusercontent.com/nkandagatla/ai-ecosystem/main/get.sh | bash -s -- --target claude,cursor --profile web-app --yes
# Downloads a release/branch tarball to ~/.ai-ecosystem/src and runs install.sh with your arguments.
# Pin a version with AI_ECOSYSTEM_REF=v2.0.0 (default: main).
set -euo pipefail
REF="${AI_ECOSYSTEM_REF:-main}"
DEST="${AI_ECOSYSTEM_HOME:-$HOME/.ai-ecosystem}/src"
command -v python3 >/dev/null || { echo "python3 (3.8+) is required" >&2; exit 1; }
command -v curl >/dev/null || { echo "curl is required" >&2; exit 1; }
case "$REF" in v[0-9]*) URL="https://github.com/nkandagatla/ai-ecosystem/archive/refs/tags/$REF.tar.gz" ;;
  *) URL="https://github.com/nkandagatla/ai-ecosystem/archive/refs/heads/$REF.tar.gz" ;; esac
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
curl -fsSL "$URL" | tar -xz -C "$TMP" --strip-components=1
rm -rf "$DEST" && mkdir -p "$(dirname "$DEST")" && mv "$TMP" "$DEST" && trap - EXIT
echo "ai-ecosystem ($REF) -> $DEST"
# when piped (curl | bash) stdin is the script, so reattach the terminal for interactive prompts
if [ ! -t 0 ] && [ -r /dev/tty ]; then exec "$DEST/install.sh" "$@" < /dev/tty; fi
exec "$DEST/install.sh" "$@"
