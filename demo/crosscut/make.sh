#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Build the Crosscut reel.
#   demo/crosscut/make.sh pack                 # pack the synthetic bucket (once, ~3 min)
#   demo/crosscut/make.sh capture [seg ...]    # play the segments in Blender, save frames
#   demo/crosscut/make.sh edit                 # cards, captions, cross-fades -> out/crosscut.mp4
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/.." && pwd)
CACHE=$ROOT/cache/crosscut
CROSSCUT_TAG=${CROSSCUT_TAG:-v0.16.0}   # a released snapshot, so a reel never films work in progress
ADDON=$CACHE/addon/$CROSSCUT_TAG
BUCKET_BUILDER=${BUCKET_BUILDER:-$HOME/dev/blender-bucket-builder/bucket_builder}
mkdir -p "$CACHE"
case ${1:-} in
  pack)
    python3 "$ROOT/lib/parts.py" "$CACHE/unpacked.3mf"
    (cd "$BUCKET_BUILDER" && python3 -m pack pack "$CACHE/unpacked.3mf" --volume 380 284 190 --mode free \
       --gap 3 --wall-gap 5 --max-density 0 --time 180 --names --out "$CACHE/packed.3mf") | tee "$CACHE/pack.log" ;;
  capture)
    shift
    if [[ ! -d $ADDON/crosscut ]]; then
      mkdir -p "$ADDON"
      git -C "$ROOT/.." archive "$CROSSCUT_TAG" crosscut | tar -x -C "$ADDON"
    fi
    CROSSCUT=${CROSSCUT:-$ADDON/crosscut}
    # Full screen on a 1920x1080 desktop (the workstation's dummy plug), where a normal window
    # can't reach 1920x1080. On a bigger desktop, a window of 1920x1115 has that client area
    # below 30 px of decoration (the edit crops it).
    "$ROOT/lib/blender.sh" --addon crosscut="$CROSSCUT" --addon bucket_builder="$BUCKET_BUILDER" \
      --window-fullscreen --python "$HERE/shots.py" -- "$@" ;;
  edit)
    python3 "$HERE/edit.py" ;;
  *)
    sed -n 3,7p "$0"; exit 1 ;;
esac
