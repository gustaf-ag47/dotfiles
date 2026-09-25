#!/bin/bash
set -euo pipefail

URL="${1:?usage: shot.sh <url> [out.png] [width] [height]}"
DOMAIN=$(echo "$URL" | sed -E 's|https?://||; s|/.*||; s|[^a-zA-Z0-9.-]||g')
OUT="${2:-/tmp/shot-$DOMAIN-$(date +%s).png}"
W="${3:-1440}"
H="${4:-2400}"

chromium --headless=new --disable-gpu --hide-scrollbars \
	--window-size="$W,$H" --virtual-time-budget=8000 \
	--screenshot="$OUT" "$URL" >/dev/null 2>&1

echo "$OUT"
