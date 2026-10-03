#!/bin/bash
# Concat per-scene wavs in order and mux onto a manim render.
# Usage: mux.sh <video.mp4> <output.mp4> <s1.wav> <s2.wav> ...
set -euo pipefail
video="$1"; out="$2"; shift 2
n=$#
inputs=(); filter=""
i=0
for wav in "$@"; do
    inputs+=(-i "$wav")
    filter+="[$i]"
    i=$((i+1))
done
tmp=$(mktemp --suffix=.wav)
trap 'rm -f "$tmp"' EXIT
ffmpeg -y "${inputs[@]}" -filter_complex "${filter}concat=n=${n}:v=0:a=1[a]" -map "[a]" "$tmp"
ffmpeg -y -i "$video" -i "$tmp" -c:v copy -c:a aac "$out"
echo "wrote $out ($(ffprobe -v error -show_entries format=duration -of csv=p=0 "$out")s)"
