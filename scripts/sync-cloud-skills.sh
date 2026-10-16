#!/usr/bin/env bash
# Fetch/update nkandagatla/ai-cloud-skills into vendor/ai-cloud-skills (used for `external_skills` in profiles).
# Alternative: git submodule add https://github.com/nkandagatla/ai-cloud-skills vendor/ai-cloud-skills
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
URL="${AI_CLOUD_SKILLS_URL:-https://github.com/nkandagatla/ai-cloud-skills.git}"
DEST="$ROOT/vendor/ai-cloud-skills"
if [ -d "$DEST/.git" ] || [ -f "$DEST/.git" ]; then
  git -C "$DEST" pull --ff-only
else
  mkdir -p "$ROOT/vendor"; git clone --depth 1 "$URL" "$DEST"
fi
echo "ai-cloud-skills ready at $DEST"
