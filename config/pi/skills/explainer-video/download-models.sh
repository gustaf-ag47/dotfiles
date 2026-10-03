#!/bin/bash
# Download Kokoro TTS model weights (~338MB) next to this script.
# Idempotent: skips files that already exist.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/models"
BASE="https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"

mkdir -p "$DIR"
for f in kokoro-v1.0.onnx voices-v1.0.bin; do
    if [ -f "$DIR/$f" ]; then
        echo "exists: $DIR/$f"
    else
        echo "downloading $f ..."
        curl -L --fail -o "$DIR/$f" "$BASE/$f"
    fi
done
echo "done."
