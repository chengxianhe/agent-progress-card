#!/usr/bin/env bash
set -euo pipefail
CARD_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CARD_RESOURCES="${1:?Pass the app Resources directory}"
CARD_ICONSET="$CARD_ROOT/build/AppIcon.iconset"
mkdir -p "$CARD_ICONSET" "$CARD_RESOURCES"
for CARD_SIZE in 16 32 128 256 512; do
  sips -z "$CARD_SIZE" "$CARD_SIZE" "$CARD_ROOT/desktop/Assets/AppIcon.png" \
    --out "$CARD_ICONSET/icon_${CARD_SIZE}x${CARD_SIZE}.png" >/dev/null
  CARD_RETINA=$((CARD_SIZE * 2))
  sips -z "$CARD_RETINA" "$CARD_RETINA" "$CARD_ROOT/desktop/Assets/AppIcon.png" \
    --out "$CARD_ICONSET/icon_${CARD_SIZE}x${CARD_SIZE}@2x.png" >/dev/null
done
iconutil -c icns "$CARD_ICONSET" -o "$CARD_RESOURCES/AppIcon.icns"
cp "$CARD_ROOT/desktop/Assets/AppIcon.png" "$CARD_RESOURCES/AppIcon.png"
