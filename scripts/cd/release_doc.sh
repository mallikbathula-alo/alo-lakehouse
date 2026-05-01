#!/usr/bin/env bash
# Generate release notes between two tags and upload to S3
# Usage: ./scripts/cd/release_doc.sh <env> [prev_tag] [latest_tag]
set -euo pipefail

ENV="${1:-prod}"
PREV="${2:-$(git describe --tags --abbrev=0 HEAD^)}"
LATEST="${3:-$(git describe --tags --abbrev=0 HEAD)}"

echo "Generating release notes: $PREV → $LATEST"

NOTES=$(git log "$PREV..$LATEST" --pretty=format:"- %s (%an)" --no-merges)
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

cat > /tmp/release_notes.md << EOF
# Release Notes — $LATEST

**Date:** $TIMESTAMP
**Range:** $PREV → $LATEST

## Changes

$NOTES
EOF

cat /tmp/release_notes.md

aws s3 cp /tmp/release_notes.md \
    "s3://alo-${ENV}-de-docs/releases/${LATEST}.md"

echo "✅ Release notes uploaded: s3://alo-${ENV}-de-docs/releases/${LATEST}.md"
