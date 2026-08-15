# Architecture

> 全套堆疊的設計、資料流、與分工。所有實作細節請對照 `docker-compose.yml`、`vector/vector.yaml`、`od-bridge/`。

## 核心理念

1. **All-Apache/MIT/MPL** —— 任何人可商業打包再發行,無 GPL 嵌入污染問題。
2. **OCSF 為內部 schema** —— 上下游元件可任意替換,只要產出/消費 OCSF。
3. **Pull-only executor** —— BeakPlatform 永遠不主動 push 決策出去,執行端拉。
4. **Stateless bridge** —— bridge 重啟不漏不重(冪等 + 樂觀鎖)。
5. **enforcement_points 自由字串** —— 不綁特定廠牌,任何整合方都能加標籤。

## 三大角色

```
┌────────────── 偵測 (Detection) ──────────────┐
│ Cloudflare Tunnel  (cloudflared)             │
│   ↓                                           │
│ WAF (nginx + libmodsec3 + OWASP CRS)         │
│ Suricata (network IDS, ens18 passive)        │
│ Falco (container/host behaviour, optional)   │
│ CrowdSec (behavioural blocking + community)  │
│   ↓ (logs/audit/events)                      │
│ Vector (collect + normalize → OCSF)          │
│   ↓                                           │
└──────────────────────────────────────────────┘
                  ↓
┌────────────── 案件流程 (Casework) ─────────────┐
│ BeakPlatform                                   │
│   POST /api/open_defense/intake  (HMAC)       │
│   → form_instance + workflow                  │
│   → human / AI 決策                           │
│   → workflow node `decision_writer`           │
│   → table  od_defense_decisions               │
│   GET  /api/open_defense/decisions  (JWT)     │
│   PATCH /api/open_defense/decisions/<sc>      │
│   cron: TTL 過期自動下 unblock 決策           │
└────────────────────────────────────────────────┘
                  ↓
┌────────────── 處置 (Enforcement) ──────────────┐
│ od-bridge executor                             │
│   poll /decisions → process_decision           │
│     ├─ nftables  (host-level drop, ipset)     │
│     ├─ crowdsec  (LAPI decision → bouncers)   │
│     └─ cloudflare (API → WAF custom rule)     │
│   PATCH applied/partial/failed                │
└────────────────────────────────────────────────┘
```

## 元件對照

| 元件 | 角色 | 監聽 | 跑在 |
|---|---|---|---|
| **cloudflared** | Tunnel connector | (出站 only) | container |
| **waf-nginx** | WAF + reverse proxy | `:8080` | container |
| **suricata** | network IDS,sniff `ens18` | (raw) | container,`network_mode: host` |
| **crowdsec** | behavioural rules + LAPI | `:8081→8080` | container |
| **vector** | collect/normalize/route | `:8688`(test in) | container |
| **clickhouse** | events / findings 儲存 | `:8123` HTTP, `:9000` native | container |
| **od-bridge** | webhook proxy + executor + 內建 stats UI | `:8500` | container,`network_mode: host` |
| **grafana** | 儀表板(SIEM dashboard) | `:3000` | container |
| **portainer** | Docker 管理 web UI | `:9443`(HTTPS) | container |
| **evebox** | Suricata alerts viewer | `:5636`(HTTPS) | container |

`network_mode: host` 兩個服務:
- **suricata** —— 要 raw socket 抓 host 介面流量
- **od-bridge** —— `nft` 必須跑在 host netns 才能影響 host iptables/nftables

## 資料流(三條獨立路徑)

### 路徑 A:外部攻擊 → 案件建立(intake)

```
attacker
  → Cloudflare edge (TLS termination, WAF v1)
    → cloudflared tunnel (QUIC)
      → waf-nginx :8080 (HTTP, plaintext between)
        → ModSec inspects request
          ├─ block (403) + write /var/log/modsec/audit.log
          └─ pass-through to backend
              → app VM
        Vector tails /var/log/modsec/audit.log (file source)
        Vector transform: ModSec JSON → OCSF web_activity
        Vector sink http: POST od-bridge :8500/events
        od-bridge ingest: HMAC-sign + POST BP /api/open_defense/intake
        BP creates form_instance + starts workflow
        BP returns case_secure_code
```

同樣路徑也接:
- Suricata EVE alerts(`/var/log/suricata/eve.json`)→ Vector → bridge → BP
- 任何外部 source 直接 POST `bridge :8500/events`(OCSF JSON)→ bridge 簽 → BP

### 路徑 B:BP 決策 → 落地阻擋(executor)

```
BP workflow / human-decision / TTL-cron auto-unblock
  → INSERT od_defense_decisions (status=pending)

od-bridge executor (every 5s):
  POST /sa/login  → JWT (cached 15 min)
  GET  /decisions?status=pending&limit=100
  for each decision matching MY_ENFORCEMENT_POINTS:
    PATCH status=picked_up   (optimistic lock)
    invoke enforcer:
      nftables.apply()    → nft add element inet secstack blocklist { ip timeout Ns }
      crowdsec.apply()    → POST LAPI /v1/decisions
      cloudflare.apply()  → (placeholder, needs API token)
    PATCH status=applied + application_result
```

### 路徑 C:歷史 SIEM 查詢

```
Vector(同一 transform 的另一條 sink)
  → ClickHouse INSERT secstack.events  (one wide row per OCSF event)
  → SummingMergeTree MV: events_per_minute(per source/class aggregate)

Query:
  SELECT … FROM secstack.events WHERE source_system='coraza' …
  HTTP 8123 / native 9000
```

## 認證邊界

| 邊界 | 認證方式 | 何時驗 |
|---|---|---|
| 任何 → bridge `:8500/events` | **none(LAN trust)**,bridge 自己重簽 HMAC 後送 BP | 入口 |
| bridge → BP `/intake` | **HMAC-SHA256**(契約 §3.1):`sha256=hex(HMAC(secret, "{ts}\n{body_raw}"))` | 每筆 |
| bridge → BP `/sa/login` | `sa_id` + `sa_secret`(plain JSON) | 取 JWT |
| bridge → BP `/decisions` | **JWT Bearer**(15 分鐘) | 每次 |
| Cloudflare → cloudflared | tunnel token + edge handshake | 連線 |
| nft enforcer → host | `cap_add: NET_ADMIN` + host netns | 每次 |
| crowdsec enforcer → LAPI | machine_id + password(初次註冊存 `state/`) → JWT | 連線 |

## 網路拓樸

```
[Internet]
   ↓ (Cloudflare edge,4 個 QUIC connectors)
[cloudflared container] - secstack network
   ↓
[waf-nginx :8080] - secstack network
   ↓ HTTP
[backend (BP / app VM 192.168.0.16:8000)]   ← 透過 LAN

[sec-vm host] (192.168.0.20)
 ├─ ens18 (LAN)        ─ Suricata sniff
 ├─ docker0/secstack network (172.18.0.0/16)
 │   ├─ clickhouse
 │   ├─ vector
 │   ├─ crowdsec
 │   ├─ waf-nginx
 │   └─ cloudflared
 └─ host netns         ─ od-bridge,suricata
                       ─ nftables `inet secstack` table
```

`network_mode: host` 的 od-bridge 透過 host 與 BP VM 通信(LAN 直接),也直接呼叫 host 的 `nft` CLI。

## 儲存與保留

| 資料 | 在哪 | 保留期 | 大小估算 |
|---|---|---|---|
| OCSF events (raw + 結構化) | ClickHouse `secstack.events` | TTL 90 天 | ZSTD 壓縮 ~10:1 |
| 決策歷史 | ClickHouse `secstack.findings`(若 bridge 寫入) | 365 天 | 小 |
| 即時聚合 | ClickHouse MV `events_per_minute` | 跟 events 同 | 極小 |
| Suricata eve.json | docker volume `suricata-logs` | 軟限制(rotate 自行設定) | 高流量會大 |
| ModSec audit.log | bind mount `./waf/log/audit.log` | 同上 | 攻擊量決定 |
| CrowdSec decisions | docker volume `crowdsec-data` | TTL 由 decision 自帶 | 小 |
| Cloudflared logs | container stdout | 記憶體環形(docker logs) | — |
| Bridge logs | container stdout | docker logs 預設 | — |

## 設計分工(誰負責什麼)

| 範圍 | 負責方 |
|---|---|
| 事件偵測規則 | Suricata ET Open / OWASP CRS / Falco / CrowdSec scenarios |
| 事件正規化(OCSF) | Vector (VRL transforms) |
| 案件編排與決策 | BeakPlatform(form + workflow + RBAC) |
| 決策記錄(SoT) | BeakPlatform `od_defense_decisions` |
| 決策執行 | od-bridge executor + enforcers |
| 阻擋實際落地 | nftables / CrowdSec bouncers / Cloudflare WAF |
| TTL 撤銷 | BeakPlatform cron(發 unblock 決策),executor 落地 |

## 可擴充點

- 新事件源:寫一個 Vector source + transform 到 OCSF
- 新 enforcer:在 `od-bridge/od_bridge/enforcers/` 加 `xxx.py`,實作 `apply(decision, cfg)`
- 新 enforcement_point 標籤:契約 §6.3 是字串自由,不需任何 schema 變更
- 多 domain WAF:`docker-compose.yml` 複製 `waf-nginx` service,改 BACKEND
- 多 sec-vm:每個自己 SA + intake key,共用 BP

## 不該做的事

- ❌ BP 主動發 outbound webhook 給 executor(契約 §1 明文反對,改用拉模式)
- ❌ Bridge 直接執行 SQL 進 BP DB(繞過 RLS、audit、secure_code 生成)
- ❌ Executor 自行決定何時 unblock(必須等 BP cron 下 unblock 決策)
- ❌ 共用 SA 給多台 sec-vm(quota 互吃,日誌不易追)
- ❌ 在 docker-compose 中對含 `x-show` 元素設 inline display(不適用,但類似邊角應留意)
