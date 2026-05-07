#!/usr/bin/env bash
# Rollback: re-tag the previous release and push to trigger prod deploy
set -euo pipefail

CURRENT=$(git describe --tags --abbrev=0)
PREVIOUS=$(git describe --tags --abbrev=0 "$CURRENT^")

echo "Rolling back from $CURRENT to $PREVIOUS"
read -r -p "Are you sure? (yes/no): " CONFIRM
[[ "$CONFIRM" == "yes" ]] || { echo "Aborted."; exit 1; }

ROLLBACK_TAG="${PREVIOUS}-rollback-$(date +%Y%m%d%H%M%S)"
git tag -a "$ROLLBACK_TAG" "$PREVIOUS^{}" -m "Rollback to $PREVIOUS"
git push origin "$ROLLBACK_TAG"
echo "✅ Rollback tag $ROLLBACK_TAG pushed — prod deploy triggered."
