#!/bin/sh
# Builds the MiaUI v1.0.3 performance update from this repo, on any host with Docker:
#   perf-update/output/minarch.elf
#   perf-update/output/minui.elf
#   perf-update/output/pcsx_rearmed_libretro.so
#   perf-update/output/miaui-v1.0.3-perf-collections.zip   (Updater.pak, official update format)
#
# The toolchain is Debian bookworm's arm-linux-gnueabihf gcc (glibc 2.36), so the binaries
# load on MiaUI's glibc 2.37. Newer toolchains (glibc 2.38+) make binaries MiaUI can't load.
set -e

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/.." && pwd)"
CACHE="$HERE/cache"
OUT="$HERE/output"
mkdir -p "$CACHE" "$OUT"

PCSX_HASH=$(sed -n 's/^pcsx_rearmed_HASH *= *//p' "$REPO/cores/makefile")
[ -n "$PCSX_HASH" ] || { echo "pcsx_rearmed_HASH missing in cores/makefile"; exit 1; }

if [ ! -d "$CACHE/pcsx_rearmed/.git" ]; then
	git clone -q https://github.com/libretro/pcsx_rearmed "$CACHE/pcsx_rearmed"
fi
git -C "$CACHE/pcsx_rearmed" fetch -q origin
git -C "$CACHE/pcsx_rearmed" checkout -q "$PCSX_HASH"

if [ ! -d "$CACHE/libretro-common/.git" ]; then
	git clone -q https://github.com/libretro/libretro-common "$CACHE/libretro-common"
fi
LRC_HASH=$(git -C "$REPO" ls-tree HEAD src/minarch/libretro-common | awk '{print $3}')
git -C "$CACHE/libretro-common" checkout -q "$LRC_HASH"

docker run --rm \
	-v "$REPO:/repo:ro" -v "$CACHE:/cache:ro" -v "$OUT:/out" \
	-e PCSX_HASH="$PCSX_HASH" \
	debian:bookworm sh /repo/perf-update/docker/build-all.sh

ls -l "$OUT"
