#!/usr/bin/env bash
# Emergency Bug Fix — fast-track a patch release from current HEAD
set -euo pipefail

echo "⚠️  Emergency Bug Fix — patching from current HEAD"
read -r -p "Confirm EBF patch release? (yes/no): " CONFIRM
[[ "$CONFIRM" == "yes" ]] || { echo "Aborted."; exit 1; }

bash "$(dirname "$0")/tag.sh" patch
echo "🚑 EBF patch tag pushed."
