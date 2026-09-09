# Open Defense — OSS security stack

**端到端開源安全堆疊**:把任何中小企業 / 工程師家中的「實體機 + VM」組合,變成一座小型 SOC。
所有元件 Apache 2.0 / MIT / BSD / MPL 2.0,無商業授權陷阱,可自由打包再發行。

## 它做什麼

```
┌──────────── 偵測 ────────────┐    ┌────── 案件流程 ──────┐    ┌──── 自動處置 ────┐
│ Cloudflare Tunnel(隧道)    │    │ BeakPlatform        │    │ od-bridge       │
│         ↓                    │    │  ─ webhook intake   │    │  executor       │
│ WAF(nginx + ModSec + CRS)  │───►│  ─ 表單 + workflow  │───►│  ─ CrowdSec     │
│ Suricata(network IDS)      │    │  ─ 人/AI 決策       │    │  ─ nftables     │
│ Falco(容器/host 行為)      │    │  ─ 決策 DB          │    │  ─ Cloudflare   │
│ CrowdSec(行為封鎖 + 共享)  │    │  ─ TTL 自動 unblock │    │  (自家 app)     │
│         ↓                    │    └─────────────────────┘    └─────────────────┘
│ Vector(正規化 → OCSF)      │                ▲
│         ↓                    │                │ HMAC + JWT
│ ClickHouse(歷史 SIEM 儲存) │                │
└──────────────────────────────┘                │
                ▲                               │
                └─── od-bridge ingest ──────────┘
                     (HMAC 簽章 webhook proxy)
```

外面看到的:**告警 → 案件 → 決策 → 阻擋**全自動,可被人或 AI 介入。
開發者看到的:**一張 ClickHouse 寬表 + 一張決策表 + 一個 webhook**,工具想換就換。

## 元件清單與授權

| 元件 | 角色 | 授權 |
|---|---|---|
| **od-bridge**(本專案) | webhook proxy + decision executor | Apache 2.0 |
| **Vector** (Datadog) | log shipper + 正規化 | MPL 2.0 |
| **ClickHouse** | 事件儲存 / 查詢 | Apache 2.0 |
| **Suricata** | network IDS | GPLv2(僅作獨立 process) |
| **owasp/modsecurity-crs:nginx** | WAF (nginx + libmodsec + OWASP CRS) | Apache 2.0 |
| **CrowdSec** | 行為偵測 + 開源 EDL | MIT |
| **cloudflared** | Cloudflare Tunnel client | Apache 2.0 |
| **BeakPlatform** | 表單 / workflow / 決策中介 | 由 BeakPlatform 自行授權,**外部接 webhook 即可** |

**整合契約**:`/opt/open_defense_contract.md`(BeakPlatform 端發布)。
本 stack 的職責是**符合契約**的雙向接點,內部技術可任意替換。

## 快速啟動

需求:Ubuntu 22.04 / 24.04 LTS,有 sudo + Docker 環境。

```bash
git clone <this-repo> /home/ethan/sec-vm-bootstrap
cd /home/ethan/sec-vm-bootstrap

# 編輯 .env 填憑證(見下節)
cp .env.example .env
$EDITOR .env

# 一鍵起
sudo bash bootstrap.sh
```

完成後:
- WAF 在 `:8080`
- ClickHouse 在 `:8123`(SQL HTTP)
- bridge 在 `:8500`(intake webhook)
- vector 測試端口 `:8688`
- crowdsec LAPI 在 `:8081`

## .env 必填項

| 變數 | 來源 | 說明 |
|---|---|---|
| `BEAK_BASE_URL` | BP 部署位置 | 例 `http://192.168.0.16:7000/beakplatform` |
| `INTAKE_KEY_ID` + `INTAKE_SECRET_B64` | 向 BP 申請(契約 §3.1) | webhook HMAC 共享密鑰 |
| `SA_ID` + `SA_SECRET` | 向 BP 申請(契約 §3.2) | service account,executor 用 |
| `CLOUDFLARE_TUNNEL_TOKEN` | Zero Trust UI 建立 tunnel 後複製 | 連 Cloudflare 邊緣 |
| `MY_ENFORCEMENT_POINTS` | 本機要實作哪些 EP | 現值 `crowdsec,nftables,cloudflare,edl` |
| `EDL_DIR` | EDL enforcer 落地目錄(容器內) | 預設 `/state/edl` |
| `EDL_PRUNE_INTERVAL` | 多久剔除一次過期項(秒) | 預設 `60` |
| `EDL_HEADER` | EDL 檔是否加 `#` 註解表頭 | 預設 `0`(純 IP) |
| `CLICKHOUSE_PASSWORD` | 自訂 | DB password |

## EDL(External Dynamic List)

給 PAN-OS 之類「定期抓一份 IP 清單當政策」的設備用。兩個端點都是 `text/plain`：

```
http://192.168.0.20:8500/edl        <- action=block 的目標(接防火牆的 deny 規則)
http://192.168.0.20:8500/edl/allow  <- action=allow 的目標(接 allow 規則,擺在 deny 之上)
http://192.168.0.20:8500/state/nft  <- kernel nftables set 現況(JSON,供 BeakPlatform 對帳)
```

**它是 reconciler 不是 appender**：權威狀態在 `od-bridge/state/edl/state.json`,
每筆各自帶 `expires_at`;每次決策落地與每 60 秒的 prune 都重繪整份檔案。
新增的自然累加,到期的自然消失——**永遠不要改成 append,那樣過期項永遠刪不掉**,
正是黑名單長到防火牆載不進去的成因。

清單為空時回傳空內容而非 404:404 會讓 PAN-OS 保留上一份內容,
等於靜默沿用過期的封鎖清單。

**輸出格式預設是純 IP、一行一個、零註解**。Palo Alto 文件定義的 IP List 語法是
`[位址][空格][註解]`——**註解必須與位址同一行**,整行 `#` 開頭的註解不在文件格式內,
防火牆沒有義務接受(PAN-OS 6.1 以前甚至會把含註解的整行丟掉)。
要給人看的表頭可設 `EDL_HEADER=1`,但**不要用在防火牆真的會抓的那份**。

- [IP Address List (PAN-OS 11.1)](https://docs.paloaltonetworks.com/pan-os/11-1/pan-os-admin/policy/use-an-external-dynamic-list-in-policy/formatting-guidelines-for-an-external-dynamic-list/ip-address-list)

## 三個典型案例

### 1. SQLi 命中 → 自動封 IP

```
1. 攻擊者打 GET /?id=1' OR '1'='1
2. WAF 回 403,寫 /var/log/modsec/audit.log(JSON)
3. Vector 抓檔、轉 OCSF web_activity、推 od-bridge :8500
4. bridge 簽 HMAC、POST 到 BP /api/open_defense/intake
5. BP 建案件、跑 workflow(若設定 auto-block 規則)
6. workflow 末端寫 od_defense_decisions(action=block, target=ip, ep=[nftables,crowdsec], ttl=3600)
7. od-bridge executor 5 秒內輪詢拉到
8. nftables enforcer 加進 inet/secstack/blocklist set(timeout 3600s)
9. CrowdSec enforcer 經 LAPI 寫 decision(其他 bouncer 自動同步)
10. 1 小時後 BP cron 下 unblock,executor 撤掉
```

### 2. Suricata 偵測到內部主機外連 C2

同樣路徑,只是 `event_class=network_activity`,enforcement 可能是 `siem_tag` 或 `app_internal`。

### 3. 手動建決策(從 BP UI)

SOC 人員在表單上選「封鎖此 IP 6 小時」、按送出 → workflow 跑 `decision_writer` 節點 → executor 拉到 → 落地。**不需要原始事件,任何決策來源都通**。

## 多 domain WAF

`docker-compose.yml` 的 `waf-nginx` service 是單一 backend。多 domain 時複製此 service:

```yaml
waf-domain1:
  image: owasp/modsecurity-crs:nginx
  environment: { BACKEND: "http://app1:80", ... }
  ports: ["8080:8080"]

waf-domain2:
  <<: *waf-base   # YAML anchor 抽出共用部分
  environment: { BACKEND: "http://app2:80", ... }
  ports: ["8081:8080"]
```

然後在 Cloudflare Zero Trust UI:
- `domain1.example.com` → `http://waf-domain1:8080`
- `domain2.example.com` → `http://waf-domain2:8081`

## Cloudflare Tunnel 設定

1. Cloudflare Dashboard → Zero Trust → Networks → Tunnels → **Create a tunnel**
2. 選 Cloudflared,命名 `sec-vm`
3. 在「Install and run a connector」頁複製 token,貼進 `.env` 的 `CLOUDFLARE_TUNNEL_TOKEN`
4. 「Public Hostname」分頁 → Add a public hostname:
   - Subdomain + Domain 自選
   - Service: `HTTP`,URL: `waf-nginx:8080`(若多 domain 換對應 service 名稱)

## 操作

```bash
# 看狀態
sudo docker compose ps

# 看某個元件日誌
sudo docker compose logs -f od-bridge
sudo docker compose logs -f vector

# 看當前阻擋的 IP
sudo nft list set inet secstack blocklist

# ClickHouse 查事件
curl -s -u secstack:$(grep CLICKHOUSE_PASSWORD .env | cut -d= -f2) \
  "http://127.0.0.1:8123/?query=SELECT count() FROM secstack.events"

# 跑 Suricata 規則更新
sudo docker compose exec suricata suricata-update --no-test
sudo docker compose restart suricata
```

## 常見故障排除

| 症狀 | 可能原因 |
|---|---|
| bridge 502 upstream | sec-vm 連不到 BP `:7000`,檢查 BP 端 iptables 白名單 |
| executor 401 連續 | BP 端 `/api/open_defense/decisions` 沒接 SA JWT decorator |
| executor SA login 429 | 短時間 login 太多次(限速 10/min per IP),退避 90s |
| WAF 502 normal request | backend 不認 `_` host header,看實際 app 設定;設 `SERVER_NAME` |
| ClickHouse 沒新 row | Vector batch 5 秒才 flush,稍等;或看 `vector logs` 找 sink error |
| Suricata 沒 alert | 確認規則已 update;檢查 ens18 是否能 sniff 流量(同 L2 才看得到) |
| nftables enforcer permission denied | bridge 容器需 `cap_add: NET_ADMIN` 與 `network_mode: host` |

## 設計原則

1. **All-Apache/MIT/MPL** —— 絕無 GPL 嵌入問題,可自由商業打包
2. **OCSF 為內部 schema** —— 替換上下游不必改本體
3. **HMAC + JWT 雙端認證** —— 入口 webhook、出口拉決策
4. **Pull-only executor** —— BP 不發 outbound webhook,executor 永遠拉
5. **Stateless bridge** —— 任何時候 kill 重啟都不漏不重(冪等 correlation_id + 樂觀鎖 PATCH)
6. **enforcement_points 自由字串** —— 不綁特定廠牌,任何整合方都能加標籤

## 詳細文件

| 檔案 | 內容 |
|---|---|
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | 設計理念、資料流、認證邊界、儲存佈局 |
| [`docs/REBUILD.md`](docs/REBUILD.md) | 從零重建 9 個 phase(VM clone → tunnel hostname 切換) |
| [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md) | `.env` 變數、port、volume、特權、Vector / ModSec 細節 |
| [`docs/BEAKPLATFORM_INTEGRATION.md`](docs/BEAKPLATFORM_INTEGRATION.md) | 契約對接、URL prefix、HMAC / JWT、TTL unblock、已知 BP bug |
| [`docs/UI.md`](docs/UI.md) | **Web UI 入口表**(Grafana / Portainer / EveBox / ClickHouse Play / od-bridge / Vector)、CLI、API 端點、預設密碼 |
| [`docs/PITFALLS.md`](docs/PITFALLS.md) | 30+ 條實測踩到的坑與修法,分網路/CH/Vector/Suricata/WAF/Cloudflared/VM/SSH/executor/integration |
| [`docs/MONITORING.md`](docs/MONITORING.md) | 看得到 vs 看不到清單、推薦告警、視野盲區處理 |
| [`docs/OPERATIONS.md`](docs/OPERATIONS.md) | 日常運維:啟停、規則更新、修改、備份、升級、監控接入、緊急應變 |
| [`docs/HANDOFF.md`](docs/HANDOFF.md) | **接手必讀** — 當前狀態快照、未完成項目、設計決策紀錄、名詞速查、下次優先順序 |

## License

Apache 2.0(`od-bridge` 與本專案 stack 配置)。
其他元件依其上游授權,見上表。
