#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
RHWP="$ROOT/rhwp/upstream"
FONTS="$RHWP/fonts/kice-hft"

if [ ! -f "$RHWP/Cargo.toml" ]; then
  git -C "$ROOT" submodule update --init rhwp/upstream
fi

mkdir -p "$FONTS"
find "$FONTS" -maxdepth 1 -type l -delete 2>/dev/null || true
for f in "$ROOT"/output_ttf/*.ttf; do
  [ -e "$f" ] || continue
  ln -sf "$f" "$FONTS/$(basename "$f")"
done

printf 'rhwp upstream: '
git -C "$RHWP" rev-parse --short HEAD
printf 'KICE/HFT fonts linked: '
find "$FONTS" -maxdepth 1 -type l | wc -l
