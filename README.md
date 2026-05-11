# sekai-musicmeta

镜像 [sekai-data.3-3.dev](https://sekai-data.3-3.dev) 的 musicmeta 数据，供 bot 拉取。

## 数据文件

| 路径 | 区服 |
|---|---|
| `data/music_metas.json`     | jp（默认/兜底） |
| `data/music_metas-cn.json`  | cn |
| `data/music_metas-tc.json`  | tw |
| `data/music_metas-en.json`  | en |
| `data/music_metas-kr.json`  | kr |

## 同步策略

GitHub Action 每小时第 7 分跑 `scripts/sync.sh`，**仅在数据变化时**才提交（见 `.github/workflows/sync.yml`）。也支持在 Actions 页面手动触发。

## bot 端配置

替换 `deck.music_meta_url` / `deck.music_meta_urls`：

```yaml
deck:
  music_meta_url: https://raw.githubusercontent.com/luoxiadesu/sekai-musicmeta/main/data/music_metas.json
  music_meta_urls:
    jp: https://raw.githubusercontent.com/luoxiadesu/sekai-musicmeta/main/data/music_metas.json
    cn: https://raw.githubusercontent.com/luoxiadesu/sekai-musicmeta/main/data/music_metas-cn.json
    tw: https://raw.githubusercontent.com/luoxiadesu/sekai-musicmeta/main/data/music_metas-tc.json
    en: https://raw.githubusercontent.com/luoxiadesu/sekai-musicmeta/main/data/music_metas-en.json
    kr: https://raw.githubusercontent.com/luoxiadesu/sekai-musicmeta/main/data/music_metas-kr.json
```
