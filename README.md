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

## GitHub Actions 每日同步

`.github/workflows/sync.yml` 每天 **UTC 00:17（北京时间 08:17／日本时间 09:17）** 检查一次；GitHub 定时任务可能延迟。也可以在 Actions → Sync musicmeta → Run workflow 手动触发，勾选 `force_vpn` 可跳过直连、专门测试 VPN Gate。

工作流先尝试直连上游；失败后通过 [VPN Gate 官方 CSV API](https://www.vpngate.net/api/iphone/) 获取 OpenVPN 节点，优先日本、韩国，并分散选择不同网段，最多尝试 6 个节点。无需配置 VPN 账号或 Secrets。

- 每个节点最多等待 35 秒连接、180 秒下载，整个任务最多运行 30 分钟。
- 仅上游域名解析出的 IPv4 地址走 VPN，下载绑定 VPN 网卡；GitHub 通信保持原有路由。下载保留 HTTPS 证书校验。
- 五个区服全部下载并通过 JSON 结构校验后才替换数据。有变化时由 `github-actions[bot]` 提交并推送；无变化不提交。
- 节点失败会清理隧道后换节点；全部失败则任务报错并保留原数据。公共节点也可能被 Cloudflare 拦截，无法保证每次成功。

工作流需要 `contents: write` 权限，并允许 Actions 向默认分支推送。定时工作流须位于默认分支；公开仓库连续 60 天没有活动时，GitHub 可能停用定时任务，需在 Actions 页面重新启用。

VPN 配置从 API 中提取连接地址和证书后重新生成，不执行节点提供的脚本，也不接受节点推送的默认路由或 DNS。VPN Gate 的旧客户端证书需要 OpenVPN 的兼容设置，已限定在 VPN 连接配置内。

可在工作流下载步骤的 `env` 中设置：

| 变量 | 默认值 | 含义 |
|---|---|---|
| `VPNGATE_COUNTRIES` | `JP,KR` | 优先国家，其他国家仍作为后备 |
| `VPNGATE_MAX_NODES` | `6` | 每次最多尝试的节点数 |
| `VPNGATE_CONNECT_TIMEOUT` | `35` | 单节点连接超时（秒） |
| `VPNGATE_FETCH_TIMEOUT` | `180` | 单节点整批下载超时（秒） |

## 本地同步

依赖 Bash、curl、Python 3、Git；仅 VPN 脚本额外需要 Linux、OpenVPN 2.5+ 和免密 sudo。

手动一键同步（拉数据 + 仅在变化时 commit + push）：

```bash
bash scripts/sync.sh
```

只本地更新不推送：

```bash
SKIP_PUSH=1 bash scripts/sync.sh
```

上面的命令仍会创建本地提交。只下载和校验，不提交、不推送：

```bash
FETCH_ONLY=1 bash scripts/sync.sh
```

开发检查（不访问外部网络、不修改仓库数据）：

```bash
python3 -m unittest discover -s tests -v
bash -n scripts/sync.sh
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
