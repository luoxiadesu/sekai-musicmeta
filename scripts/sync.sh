#!/usr/bin/env bash
set -euo pipefail

SRC="${SRC:-https://sekai-data.3-3.dev}"
OUT="${OUT:-data}"
mkdir -p "$OUT"

files=(
  "music_metas.json"
  "music_metas-cn.json"
  "music_metas-tc.json"
  "music_metas-en.json"
  "music_metas-kr.json"
)

for f in "${files[@]}"; do
  echo "Fetching $f ..."
  curl -fL --retry 3 --retry-delay 5 --max-time 60 \
       -o "$OUT/$f.tmp" "$SRC/$f"
  python3 -c "import json,sys; json.load(open('$OUT/$f.tmp'))"
  mv "$OUT/$f.tmp" "$OUT/$f"
done

echo "Done."
