#!/usr/bin/env bash
set -euo pipefail
CARD_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$CARD_ROOT"
mkdir -p build/verification
CARD_LOG=$(mktemp "$CARD_ROOT/build/verification/check.XXXXXX")
exec > >(tee "$CARD_LOG") 2>&1
printf 'Verification log: %s\n' "$CARD_LOG"
export PYTHONPATH="$CARD_ROOT/src"
python3 -m unittest discover -s tests -v
if [ "$(uname -s)" = Darwin ]; then
  bash desktop/build.sh
  bash desktop/build-wechat.sh
  bash scripts/test-native.sh
else
  printf 'Native build/tests: NOT RUN (requires macOS)\n'
fi
printf 'Verification completed successfully.\n'
