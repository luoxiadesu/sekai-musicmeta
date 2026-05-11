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

## 同步方式

> 上游 Cloudflare 拦了 GitHub Actions 的 IP，所以只能本地跑。

手动一键同步（拉数据 + 仅在变化时 commit + push）：

```bash
bash scripts/sync.sh
```

只本地更新不推送：

```bash
SKIP_PUSH=1 bash scripts/sync.sh
```

可选：用 crontab 自动跑，例如每小时第 7 分：

```cron
7 * * * * cd /home/luoxia/dev/mycode/sekai-musicmeta && bash scripts/sync.sh >> /tmp/sekai-musicmeta-sync.log 2>&1
```

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
