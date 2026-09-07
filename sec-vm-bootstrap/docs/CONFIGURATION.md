# Configuration — 所有參數來源與意義

## .env 變數

| 變數 | 必填 | 來源 | 範例 / 說明 |
|---|---|---|---|
| `BEAK_BASE_URL` | ✅ | 你部署的 BP 位置 | `http://192.168.0.16:7000/beakplatform`(注意 `/beakplatform` 是 nginx 路由前綴,**必須**帶) |
| `INTAKE_URL` | (auto) | 由 `BEAK_BASE_URL` 組成 | `${BEAK_BASE_URL}/api/open_defense/intake` |
| `SA_LOGIN_URL` | (auto) | 同上 | `${BEAK_BASE_URL}/api/open_defense/sa/login` |
| `DECISIONS_URL` | (auto) | 同上 | `${BEAK_BASE_URL}/api/open_defense/decisions` |
| `INTAKE_KEY_ID` | ✅ | BP admin 申請(契約 §3.1) | `ik_<redacted>` |
| `INTAKE_SECRET_B64` | ✅ | BP admin 申請,**只顯示一次** | `<REDACTED_INTAKE_SECRET_B64_見.20_CREDENTIALS.md>`(base64url,decode 後 32 byte HMAC key) |
| `SA_ID` | (空=disabled) | BP admin 申請 | `sa_executor_secvm_01_<redacted>`(尾巴 `_xxxxxx` 是 BP 強加的隨機後綴,**必須完整字串**) |
| `SA_SECRET` | (空=disabled) | 同上,**只顯示一次** | `<REDACTED_SA_SECRET_見.20_CREDENTIALS.md>` |
| `APPLIED_BY` | optional | 自訂 | `od-bridge@sec-vm`(寫入 PATCH 的 `applied_by` 欄位,給 BP 端追蹤誰執行) |
| `MY_ENFORCEMENT_POINTS` | optional | 自訂 | `crowdsec,nftables,cloudflare`(逗號分隔,bridge 只處理含這些 EP 的決策) |
| `POLL_INTERVAL` | optional | 自訂 | `5`(秒,executor 輪詢間隔) |
| `INGEST_LISTEN` | optional | 自訂 | `0.0.0.0:8500`(bridge ingest server) |
| `BRIDGE_INGEST_TOKEN` | ✅ | `openssl rand -hex 32` | `<見 .20 的 .env>`(vector → od-bridge `/events` 的 bearer token) |
| `CLICKHOUSE_DB` | optional | 自訂 | `secstack` |
| `CLICKHOUSE_USER` | optional | 自訂 | `secstack` |
| `CLICKHOUSE_PASSWORD` | ✅ | 自訂強密碼 | — |
| `GRAFANA_ADMIN_PASSWORD` | ✅ | 自訂強密碼 | Grafana 首次登入後仍會強制改 |
| `CLOUDFLARE_TUNNEL_TOKEN` | ✅ | Cloudflare Zero Trust UI | `eyJhIjoiYmI4...`(整段不能有換行) |
| `CROWDSEC_LAPI_URL` | optional | 自訂 | `http://crowdsec:8080`(secstack docker network 內名稱) |

### secret 處理

- `.env` 已加入 `.gitignore`,**勿** commit
- `od-bridge/state/crowdsec_machine.json` 也已 ignore(bootstrap 自動生成,內含 LAPI machine password)
- BP 端的 `INTAKE_SECRET_B64` 與 `SA_SECRET` 都是「**只能取一次**」設計,弄丟要重新申請新的

### 動態解密

`INTAKE_SECRET_B64` 是 base64url 編碼,bridge 啟動時用 `base64.urlsafe_b64decode()` 還原成 32-byte raw key,再進 HMAC-SHA256。**不要**自己先解碼後貼進 .env,vector/bridge 都預期看到 base64 字串。

## Port 表

### 偵測 / 處置層
| Port | 服務 | 用途 | 公開範圍 |
|---|---|---|---|
| 8080 | waf-nginx | WAF / 反代到 backend | 綁 0.0.0.0,但 nftables 只放行 `.16`/`.10`/`.100`(PF-109) |
| 8500 | od-bridge | ingest webhook + stats UI | 綁 0.0.0.0(host net),但 nftables 只放行 `.16` + docker bridge(PF-109) |
| 8688 | vector | http_test source(測試用) | **127.0.0.1 only**(PF-109 從 0.0.0.0 收回) |
| 8123 | clickhouse | SQL HTTP / Play UI | 127.0.0.1 only |
| 9000 | clickhouse | native protocol | 127.0.0.1 only |
| 8081 | crowdsec | LAPI(host 映射) | 127.0.0.1 only |
| —    | suricata | sniff(無對外 port) | host net |
| —    | cloudflared | 出站 only(QUIC) | — |

### UI 層(管理 / 可視化)
| Port | 服務 | 用途 | 公開範圍 |
|---|---|---|---|
| 3000 | grafana | 儀表板(內建 Secstack Overview) | 0.0.0.0 |
| 9443 | portainer | Docker 管理(HTTPS,self-signed) | 0.0.0.0 |
| 5636 | evebox | Suricata alerts viewer(HTTPS,self-signed) | 0.0.0.0 |
| 8686 | vector | GraphQL playground / metrics API | 0.0.0.0 |

> 完整 UI 表 + 預設帳密 + 鎖定建議見 [`UI.md`](UI.md)。
> 若 sec-vm 已有別人用某些 port,在 docker-compose.yml 改對應 service 的 ports 設定。

### ingest 面的來源管制(PF-109,2026-08-16)

8080 / 8500 / 8688 是三個「能影響案件內容」的入口,誰打得到誰就能偽造來源歸因、
讓 CrowdSec 封鎖任意第三方 IP。管制實作在兩處,**改埠或搬服務時兩處都要跟著改**:

| 埠 | 管制手段 | 位置 |
|---|---|---|
| 8080 | nftables `ingest_guard_forward`(允許 `.16`/`.10`/`.100`) | `nftables-bootstrap.sh` |
| 8688 | docker ports 綁 `127.0.0.1` + 上述 chain 雙保險 | `docker-compose.yml` |
| 8500 | nftables `ingest_guard_input`(只允許 `.16`) | `nftables-bootstrap.sh` |

兩條 chain 都以 `iifname != "ens18" accept` 開頭,所以本機打 `127.0.0.1:8080`
(走 lo)與 vector→`host.docker.internal:8500`(走 docker bridge)不受影響。
**反過來說,從 `.20` 本機發動的探測完全繞過這層判定**——2026-09-07 廢除的
hourly canary 就是因此只驗得到「WAF 容器還活著」。**`.10` 的瀏覽器連不到 od-bridge stats UI 是刻意的**,要看得先 SSH 進 `.20`。

驗證務必從被拒的一側測(只測「該通的通」不算驗證):

```bash
# 從 .16 臨時借一個非白名單來源 IP
sudo ip addr add 192.168.0.199/24 dev ens18 label ens18:pf109
for p in 22 8123 8080 8500 8688; do
  nc -s 192.168.0.199 -z -w 5 192.168.0.20 $p && echo "$p OPEN" || echo "$p BLOCKED"
done   # 預期:22/8123 OPEN,8080/8500/8688 BLOCKED
sudo ip addr del 192.168.0.199/24 dev ens18
```

## Volume / 路徑

| 路徑 | 類型 | 說明 |
|---|---|---|
| `clickhouse-data` | docker volume | 事件儲存,刪除 = 全清 |
| `clickhouse-logs` | docker volume | ClickHouse server 日誌 |
| `crowdsec-config` | docker volume | LAPI 設定 |
| `crowdsec-data` | docker volume | 決策 DB / metrics |
| `suricata-logs` | docker volume | EVE JSON + suricata.log |
| `vector-data` | docker volume | checkpoint(file source 進度) |
| `./waf/log/` | **bind mount**(host) | ModSec audit.log,**owned by uid 101**(nginx 容器內) |
| `./od-bridge/state/` | **bind mount**(host) | `crowdsec_machine.json`(LAPI 機器憑證) |

⚠️ `./waf/log/` 必須在 `bootstrap.sh` 預先 `chown 101:101`,否則 nginx 寫不進去 audit.log,WAF 可以擋但事件不會進管線。

## Container 特權

| 容器 | 特殊設定 | 為什麼 |
|---|---|---|
| od-bridge | `cap_add: NET_ADMIN`,`network_mode: host` | nft 命令必須影響 host netns |
| suricata | `cap_add: NET_ADMIN, SYS_NICE, NET_RAW`,`network_mode: host` | sniff host 介面 |
| crowdsec | (none) | 只開內部 LAPI |
| waf-nginx | (none),uid 101 | 標準 nginx |
| vector | (none) | 預設 |
| clickhouse | `ulimits.nofile: 262144` | CH 推薦設定 |

## Docker network 設計

兩條:
- `secstack`(default bridge) — clickhouse / vector / crowdsec / waf-nginx / cloudflared 之間
- **host** — od-bridge / suricata 直接用 host netns

跨網路:
- vector(secstack)→ od-bridge(host):透過 `extra_hosts: ["host.docker.internal:host-gateway"]` + `http://host.docker.internal:8500`
- od-bridge(host)→ crowdsec(secstack):透過 host 對外的 docker bridge gateway,實際走 `127.0.0.1:8081`(crowdsec 已 publish 到 host)

## Suricata 設定

- `suricata.yaml` 中 `HOME_NET`:`[192.168.0.0/16,10.0.0.0/8,172.16.0.0/12]` —— 所有私網
- 介面:`ens18`(預設 Ubuntu Proxmox VM 介面;若你的環境名稱不同,**改 docker-compose.yml 的 `command` 與 yaml 中 `af-packet` 區段**)
- 規則更新:`docker compose exec suricata suricata-update --no-test`,**必須加 `--no-test`** —— 預設配置會因 SCADA 規則(dnp3/modbus)觸發 `suricata -T` 失敗,但其他 4 萬條都正常,跳過自我檢測直接重載

## Vector 設定要點

- 所有 transform 走 VRL,字段是 `null` 或值,**不會**錯,所以 `??` 只用在會錯的函式上(`to_int(.x) ?? 0`,**不要** `to_int(.x ?? 0)`)
- ClickHouse sink 的時間欄位:必須是 `"YYYY-MM-DD HH:MM:SS.fff"`,不能用 ISO `"YYYY-MM-DDTHH:MM:SSZ"`
- IPv4 字串會自動轉 IPv6-mapped(`203.0.113.1` → `::ffff:203.0.113.1`),不必預處理
- `parse_json!()` 後 `.` 變成 object,所有 nested field 都是 fallible-by-existence 但 infallible-by-error
- `array(...) ?? []` 用來 narrow 任意值為 array(給 `length()` / `is_empty()` 吃)

## ModSec / OWASP CRS 設定

由 docker-compose 環境變數控:

| Env | 預設 | 意義 |
|---|---|---|
| `PARANOIA` | 1 | 1=寬鬆,4=偏執;先 1 再爬 |
| `ANOMALY_INBOUND` | 5 | 入站達此分數才阻擋 |
| `ANOMALY_OUTBOUND` | 4 | 出站達此分數才阻擋 |
| `MODSEC_RULE_ENGINE` | On | `DetectionOnly` 用於初期學習階段 |
| `MODSEC_AUDIT_ENGINE` | RelevantOnly | 只 log 4xx (非 404) 與 5xx |
| `MODSEC_AUDIT_LOG_FORMAT` | JSON | Vector 才能 parse_json |
| `BACKEND` | `http://192.168.0.16:8000` | upstream;**單一 backend**,多 domain 要複製 service |

## 多 sec-vm 共用同一 BP

- 每台 sec-vm **各自**申請 SA(`sa_executor_secvm_02_xxxxxx` 等),**不要共用** —— SA quota per `sa_id`,共用會互吃
- intake key 可共用或各自,看你想不想分流量歸因
- 對應的 `APPLIED_BY` 欄位每台改不同(`od-bridge@sec-vm-01` / `02`),BP 端能追蹤是哪台處理的
