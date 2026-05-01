#!/usr/bin/env bash
# Usage: ./scripts/cd/tag.sh patch|minor|major
set -euo pipefail

TYPE="${1:-patch}"
CURRENT=$(git describe --tags --abbrev=0 2>/dev/null || echo "v0.0.0")

IFS='.' read -r -a PARTS <<< "${CURRENT#v}"
MAJOR="${PARTS[0]:-0}"
MINOR="${PARTS[1]:-0}"
PATCH="${PARTS[2]:-0}"

case "$TYPE" in
    major) MAJOR=$((MAJOR + 1)); MINOR=0; PATCH=0 ;;
    minor) MINOR=$((MINOR + 1)); PATCH=0 ;;
    patch) PATCH=$((PATCH + 1)) ;;
    *) echo "Usage: $0 patch|minor|major" && exit 1 ;;
esac

NEW_TAG="v${MAJOR}.${MINOR}.${PATCH}"
echo "Tagging: $CURRENT → $NEW_TAG"
git tag -a "$NEW_TAG" -m "Release $NEW_TAG"
git push origin "$NEW_TAG"
echo "✅ Tag $NEW_TAG pushed."
