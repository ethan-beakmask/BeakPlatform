# UI / 操作介面總覽

> 給人類看的圖形介面、TUI、CLI、與直接打的 API 入口。從 LAN 任何一台機器都可以用 sec-vm IP `192.168.0.20` 連接。

## 一張表看完(瀏覽器導向)

| # | 工具 | URL | 預設帳/密 | 用途 |
|---|---|---|---|---|
| 1 | **Grafana** | http://192.168.0.20:3000 | `admin` / (預設值,見 .20 CREDENTIALS.md,不入庫) | 主要儀表板。內建 **Secstack Overview** 儀表板:事件流、攻擊熱圖、TopN IP/規則 |
| 2 | **Portainer** | https://192.168.0.20:9443 | 首次登入**自設** | 容器管理 web UI,看/重啟/exec 容器 |
| 3 | **EveBox** | https://192.168.0.20:5636 | 無認證(LAN trust) | Suricata alerts 專用 UI,過濾、搜尋、看封包詳情 |
| 4 | **ClickHouse Play** | http://192.168.0.20:8123/play | `secstack` / (預設值,見 .20 CREDENTIALS.md,不入庫) | SQL Web UI,語法高亮,查歷史事件 |
| 5 | **od-bridge Stats**(自家)| http://192.168.0.20:8500/stats | 無認證 | 5 秒自動刷新,intake/executor 即時計數 |
| 5a | ↳ Forwards | http://192.168.0.20:8500/forwards | — | 最近 50 筆 intake 轉送 |
| 5b | ↳ Decisions | http://192.168.0.20:8500/decisions | — | 最近 50 筆已執行決策 |
| 6 | **Vector Playground** | http://192.168.0.20:8686/playground | 無認證 | GraphQL 查 metrics |
| 7 | **BeakPlatform** | http://192.168.0.16:7000/beakplatform/forms/center | BP admin | 案件管理(BP VM 上,**不是本 stack**) |
| 8 | **Cloudflare Zero Trust** | https://one.dash.cloudflare.com | Cloudflare 帳號 | Tunnel 連線 / hostname 路由 |

> ⚠️ EveBox 用 self-signed TLS,瀏覽器會警告;Portainer 同。第一次點 `Advanced → Proceed`。

## 路徑速記

```
👀 看儀表板         → Grafana :3000
🐛 看 WAF 攻擊細節   → ClickHouse Play :8123/play
🛡️ 看 IDS alerts     → EveBox :5636
⚙️ 管 Docker 容器    → Portainer :9443
📡 看 bridge 健康    → od-bridge :8500/stats
📋 案件處置          → BeakPlatform :7000/beakplatform
🌐 看 tunnel 連線    → Cloudflare Zero Trust 後台
```

---

## 詳細介紹各個 UI

### 1. Grafana — 儀表板首選

開啟後第一次會強制改密碼。內建 datasource「ClickHouse-secstack」已自動配好,進 **Dashboards → Secstack Overview** 立刻有圖。

**已自動 provision 的內容:**
- Datasource:`grafana-clickhouse-datasource` 接到 `clickhouse:9000` native protocol
- Dashboard:`Secstack Overview`,六個 panel
  - Events (last 1h)
  - High-severity (last 1h)
  - Events by source(pie)
  - Events per minute by class(timeseries)
  - Top attacker IPs (last 24h)
  - Top WAF rules (last 24h)

**改密碼:**
編 `.env` 的 `GRAFANA_ADMIN_PASSWORD`,然後:
```bash
sudo docker compose up -d --force-recreate grafana
```

**加自己的 dashboard:**
直接在 UI 內建立,然後 `Save`。也可以丟 JSON 進 `grafana/provisioning/dashboards/` 自動載入。

### 2. Portainer — Docker 管理

第一次開 https://192.168.0.20:9443 會要求你建 admin 使用者。建好後:
- **Containers**:看每個服務狀態、啟停、log、exec(直接開 web shell 進容器)
- **Volumes / Networks / Images**:管理底層資源
- **Stacks**:把 docker-compose 視為一個 stack 管理(本機 stack 名稱 `secstack`)

### 3. EveBox — Suricata 專用

看 Suricata 的 alerts(目前因為 sec-vm L2 限制,大多是它自己的入站流量;cloudflared hostname 切到 sec-vm 後流量增加)。
- 左側分類過濾:Severity / Source IP / Signature
- Inbox 模式:像 email 一樣標 escalated / archive
- TLS 自簽憑證,瀏覽器接受即可

### 4. ClickHouse Play

語法:
```sql
-- 過去 24 小時各 source 命中
SELECT source_system, count() FROM secstack.events
WHERE event_time > now() - INTERVAL 24 HOUR
GROUP BY source_system;

-- WAF 高嚴重度命中明細
SELECT event_time, IPv6NumToString(actor_ip) AS ip,
       target_url, finding_rule_id, finding_title
FROM secstack.events
WHERE source_system = 'coraza' AND severity_id >= 4
ORDER BY event_time DESC LIMIT 100;
```

### 5. od-bridge Stats(專案自開發)

是我這次施工裡寫的小型運維儀表板,**重啟即清零**(in-memory)。三頁:

- `/stats` — 計數器:intake 2xx/4xx/5xx 統計、executor processed/applied/failed、SA token 倒數秒數
- `/forwards` — 最近 50 筆 intake 轉送,每筆 cid + src + upstream status + 時間
- `/decisions` — 最近 50 筆已處理決策,每筆 action + target + EPs + 結果

當你懷疑 BP 端有狀況、或想知道 SA login quota 還剩多少,先看這頁。

### 6. Vector Playground

進階用。`/playground` 是 GraphQL UI,可以查 Vector 內部 metrics:
```graphql
{
  components {
    edges {
      node {
        componentId
        on {
          ... on Source { metrics { receivedEventsTotal { receivedEventsTotal } } }
          ... on Sink   { metrics { sentEventsTotal     { sentEventsTotal } } }
        }
      }
    }
  }
}
```
日常用 `vector top` CLI 更方便。

---

## CLI(在 sec-vm 上 ssh 進去)

```bash
cd /home/ethan/sec-vm-bootstrap

# Vector TUI(像 htop,顯示每個 source/transform/sink 吞吐)
sudo docker compose exec vector vector top

# CrowdSec
sudo docker compose exec crowdsec cscli decisions list
sudo docker compose exec crowdsec cscli alerts list
sudo docker compose exec crowdsec cscli metrics
sudo docker compose exec crowdsec cscli decisions add --ip 1.2.3.4 --duration 1h --reason "manual"
sudo docker compose exec crowdsec cscli decisions delete --ip 1.2.3.4

# ClickHouse 互動式 client(歷史紀錄、TAB 補完)
sudo docker compose exec clickhouse clickhouse-client \
    --user secstack --password '<見 .20 .env 的 CLICKHOUSE_PASSWORD>' --multiline

# Suricata 線上指令
sudo docker compose exec suricata suricatasc -c "iface-list"
sudo docker compose exec suricata suricatasc -c "iface-stat ens18"

# nftables 即時阻擋名單(host 層)
sudo nft list set inet secstack blocklist
```

---

## 程式 / 自動化用的 API(無 UI)

| 端點 | 認證 | 用途 |
|---|---|---|
| `POST http://192.168.0.20:8500/events` | 無(LAN trust) | 推 OCSF JSON 進 bridge,bridge 簽 HMAC 後上送 BP |
| `POST http://192.168.0.20:8688/` | 無 | Vector http_test source(測試管線用,生產可關) |
| `GET http://192.168.0.20:8500/health` | 無 | bridge 存活檢查,回 `{"ok":true}` |
| `http://127.0.0.1:8123/?query=...` | BasicAuth secstack:* | ClickHouse SQL HTTP(僅本機可達) |
| `http://127.0.0.1:8081/v1/...` | machine creds → JWT | CrowdSec LAPI(僅本機可達) |
| `http://192.168.0.16:7000/beakplatform/api/open_defense/intake` | HMAC | BP intake API(契約 §4) |

---

## 預設密碼一覽(請立即換)

| 服務 | 預設值 | 在哪改 |
|---|---|---|
| Grafana admin | `admin` / (預設值,見 .20 CREDENTIALS.md,不入庫) | 首次登入強制改;或 `.env` 的 `GRAFANA_ADMIN_PASSWORD` |
| ClickHouse user | `secstack` / (預設值,見 .20 CREDENTIALS.md,不入庫) | `.env` 的 `CLICKHOUSE_PASSWORD`(細節見 `CREDENTIALS.md §4`) |
| Portainer admin | 首次自設 | UI 上設定 |
| EveBox | **無認證** | 命令列 `--no-auth` 拿掉再加 OAuth/Basic |

## 防護建議(LAN 以外想開)

預設這些 UI 都 bind 到 `0.0.0.0`,LAN 任何人都能連。要對外開放(例如外勤遠端管):

1. **不要直接對外** —— 加在 cloudflared 的 Public Hostname 後面,Zero Trust UI 設 hostname 指向(例如)`http://grafana:3000`
2. **走 Cloudflare Access** —— Zero Trust 設 application,要 SSO / device posture 才放行
3. **如本機加 reverse proxy + TLS + Basic Auth** —— 在 sec-vm 加一個 Caddy/Traefik 容器集中發 TLS + 認證

EveBox 因為**完全無認證**,千萬別對外暴露;若一定要,先在 Caddy 套一層 Basic Auth。

---

## 從 PVE host 怎麼連?

PVE host 在同 LAN(192.168.0.100),直接瀏覽器開上述 URL 即可。
也可以從 PVE host 用 SSH tunnel 把 UI 帶到你筆電:

```bash
# 在你筆電執行,把 sec-vm 的 Grafana 帶到本機 3000
ssh -L 3000:192.168.0.20:3000 root@192.168.0.100
# 然後筆電瀏覽器開 http://localhost:3000
```

需多 port 一次帶:
```bash
ssh -L 3000:192.168.0.20:3000 \
    -L 9443:192.168.0.20:9443 \
    -L 5636:192.168.0.20:5636 \
    -L 8500:192.168.0.20:8500 \
    -L 8123:192.168.0.20:8123 \
    root@192.168.0.100
```
