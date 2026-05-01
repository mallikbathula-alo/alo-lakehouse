#!/usr/bin/env bash
# Tag + generate and upload release notes in one step
# Usage: ./scripts/cd/tag_with_release_doc.sh patch|minor|major dev|prod
set -euo pipefail

TYPE="${1:-patch}"
ENV="${2:-prod}"

PREV=$(git describe --tags --abbrev=0)

bash "$(dirname "$0")/tag.sh" "$TYPE"

LATEST=$(git describe --tags --abbrev=0)
bash "$(dirname "$0")/release_doc.sh" "$ENV" "$PREV" "$LATEST"
