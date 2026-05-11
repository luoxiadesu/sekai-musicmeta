#!/usr/bin/env bash
# 本地手动同步：拉取 5 个 musicmeta，仅在变化时 commit + push。
# 跳过 push: SKIP_PUSH=1 bash scripts/sync.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
cd "$REPO_DIR"

SRC="${SRC:-https://sekai-data.3-3.dev}"
OUT="${OUT:-data}"
UA="${UA:-Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36}"
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
       -A "$UA" -H "Accept: application/json" \
       -o "$OUT/$f.tmp" "$SRC/$f"
  python3 -c "import json,sys; json.load(open('$OUT/$f.tmp'))"
  mv "$OUT/$f.tmp" "$OUT/$f"
done

if [[ -z "$(git status --porcelain "$OUT/")" ]]; then
  echo "No changes."
  exit 0
fi

git add "$OUT/"
git commit -m "chore: sync musicmeta $(date -u +%FT%TZ)"

if [[ "${SKIP_PUSH:-0}" == "1" ]]; then
  echo "Committed locally; SKIP_PUSH=1 set, not pushing."
  exit 0
fi

git push
echo "Pushed."
