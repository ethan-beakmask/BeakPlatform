# Integrated-WAF 防禦節點

把一台 Ubuntu 主機變成 BeakPlatform 的「防禦端」：WAF、網路 IDS、事件正規化、
封鎖落地，並透過 Cloudflare Tunnel 對外提供被保護的網站。偵測到的事件送進
BeakPlatform（管制端）建立資安案件，平台核可的封鎖決策再回到本機落地。

```
Internet → Cloudflare → cloudflared → WAF(nginx+ModSecurity+CRS) → 你的網站
                                        │ 告警                    ▲
   Suricata（監聽網卡）───────────────► Vector → od-bridge ──事件──► BeakPlatform
                                        │                          │
                                        ▼                       決策│
                                    ClickHouse   nftables / CrowdSec / EDL ◄──┘
```

**安裝與操作說明：`docs/install/integrated_waf.md`**（在 BeakPlatform repo 內）。

最短路徑：

```bash
# 管制端（BeakPlatform 主機）：發憑證、產生開通字串
cd /opt/BeakPlatform && set -a && source .env && set +a
venv/bin/python scripts/od_node_pairing.py --org <企業網域> --base-url http://<平台IP>:<埠>/beakplatform --provision --apply

# 防禦端（另一台 Ubuntu）
curl -fsSL \
    https://raw.githubusercontent.com/ethan-beakmask/BeakPlatform/main/Integrated-WAF/install.sh -o /tmp/install.sh
sudo bash /tmp/install.sh --pair '<開通字串>' --backend http://<被保護網站IP>:<埠> \
     --cf-api-token <Cloudflare API Token> --cf-hostname www.example.com \
     --welcome-hostname www.example.com --backend-path /beakplatform
```

上面這組參數的結果：`https://www.example.com/` 是歡迎頁，`https://www.example.com/beakplatform/` 是被保護的網站，兩者都經過 WAF。

| 檔案 | 用途 |
|---|---|
| `install.sh` | 一鍵安裝／重新設定／驗證／更新／移除 |
| `COMPONENTS.md` | 內容物清單、各元件版本與授權、單獨安裝指令、著作權聲明（中英） |
| `welcome/` | 歡迎頁樣板（`--welcome-hostname` 啟用，有獨立 WAF） |
| `cf_tunnel.py` | 用 Cloudflare API 自動建 tunnel、ingress、DNS（選用，不用 API 也能在後台手動做） |
| `nftables.sh` | 產生主機防火牆（封鎖 set、自鎖保險、來源管制） |
| `standby.sh` | 防禦端熱備狀態、接手、釋放與封鎖狀態匯入匯出 |
| `failover.sh` | 管理機執行的兩節點切換協調工具 |
| `nftset_elems.py` | 將 nftables set JSON 轉回可匯入的元素行 |
| `docker-compose.yml` | 全部服務；參數都在 `.env` |
| `.env.example` | 參數說明 |
| `vector/vector.yaml` | 事件正規化與封頂規則 |
| `suricata/`、`waf/`、`crowdsec/`、`clickhouse/`、`grafana/` | 各元件設定 |
| `od-bridge/` | 自寫的橋接程式（Apache 2.0） |

授權：本目錄 Apache 2.0；其他元件依各自上游授權（Vector MPL 2.0、ClickHouse Apache 2.0、
Suricata GPLv2 以獨立程序執行、OWASP CRS Apache 2.0、CrowdSec MIT、cloudflared Apache 2.0）。
