#!/usr/bin/env bash
# 拉取 5 个 musicmeta，仅在变化时 commit + push。
# 跳过 push: SKIP_PUSH=1 bash scripts/sync.sh
# 只下载和校验，不 commit/push: FETCH_ONLY=1 bash scripts/sync.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
cd "$REPO_DIR"

SRC="${SRC:-https://sekai-data.3-3.dev}"
OUT="${OUT:-data}"
UA="${UA:-Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36}"
mkdir -p "$OUT"
TEMP_DIR="$(mktemp -d "$OUT/.sync.XXXXXX")"
trap 'rm -rf -- "$TEMP_DIR"' EXIT

files=(
  "music_metas.json"
  "music_metas-cn.json"
  "music_metas-tc.json"
  "music_metas-en.json"
  "music_metas-kr.json"
)

curl_args=(
  --fail --location --silent --show-error
  --retry "${CURL_RETRIES:-3}" --retry-delay 5
  --connect-timeout 10 --max-time "${CURL_MAX_TIME:-60}"
  --user-agent "$UA" --header "Accept: application/json"
)
# VPN 模式固定解析结果并绑定隧道，避免使用 runner 的代理或 IPv6 出口。
if [[ -n "${VPN_RESOLVE:-}" ]]; then
  curl_args+=(--ipv4 --noproxy '*' --resolve "$VPN_RESOLVE" --interface "${VPN_INTERFACE:?}")
fi

for f in "${files[@]}"; do
  echo "Fetching $f ..."
  curl "${curl_args[@]}" -o "$TEMP_DIR/$f" "${SRC%/}/$f"
  python3 - "$TEMP_DIR/$f" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as stream:
    data = json.load(stream)
if not isinstance(data, list) or not data:
    raise SystemExit(f"Invalid musicmeta (expected a non-empty list): {sys.argv[1]}")
if not all(
    isinstance(row, dict)
    and type(row.get("music_id")) is int
    and isinstance(row.get("difficulty"), str)
    and row["difficulty"]
    for row in data
):
    raise SystemExit(f"Invalid musicmeta entries: {sys.argv[1]}")
PY
done

# 所有下载均成功后再替换，失败的节点不会留下半套数据。
paths=()
for f in "${files[@]}"; do
  mv -- "$TEMP_DIR/$f" "$OUT/$f"
  paths+=("$OUT/$f")
done

if [[ "${FETCH_ONLY:-0}" == "1" ]]; then
  echo "All musicmeta files downloaded and validated."
  exit 0
fi

if [[ -z "$(git status --porcelain -- "${paths[@]}")" ]]; then
  echo "No changes."
  exit 0
fi

git add -- "${paths[@]}"
git commit --only -m "chore: sync musicmeta $(date -u +%FT%TZ)" -- "${paths[@]}"

if [[ "${SKIP_PUSH:-0}" == "1" ]]; then
  echo "Committed locally; SKIP_PUSH=1 set, not pushing."
  exit 0
fi

git push
echo "Pushed."
