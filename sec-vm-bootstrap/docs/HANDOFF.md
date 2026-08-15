# Handoff — 2026-05-10 收工狀態

> 給下一個接手的人(可能是你下次、可能是新 Claude 對話、可能是同事)。
> 這份是**「現在到底處於什麼狀態」**的快照,而不是設計或操作手冊。

## 1. 當前部署狀態(全綠)

10 個容器在 sec-vm `192.168.0.20` 上跑:

| 狀態 | 服務 | 對外 port | 備註 |
|---|---|---|---|
| 🟢 healthy | clickhouse | 127.0.0.1:8123/9000 | 90 天 TTL |
| 🟢 up | cloudflared | (出站) | 4 個 QUIC connector,**hostname 還沒切到 waf-nginx** |
| 🟢 up | crowdsec | 127.0.0.1:8081 | machine `od-bridge` 已註冊 |
| 🟢 up | suricata | host net `ens18` | ET Open 規則已 update,**只看到 sec-vm 自己流量** |
| 🟢 up | vector | :8686, :8688 | 接 Suricata + ModSec → OCSF → ClickHouse + bridge |
| 🟢 healthy | waf-nginx | :8080 | OWASP CRS,SQLi/XSS/PT 全擋 |
| 🟢 up | od-bridge | :8500 | ingest + executor 雙 task,新增 /stats UI |
| 🟢 up | grafana | :3000 | ClickHouse datasource + Secstack Overview dashboard 已 provision |
| 🟢 up | portainer | :9443 | Docker 管理 |
| 🟢 up | evebox | :5636 (HTTPS) | Suricata alerts viewer |

## 2. 開放但未完成 / 未驗證的事

### 必做才算上線
| 項目 | 為什麼還沒做 | 怎麼做 |
|---|---|---|
| **Cloudflare hostname 切到 waf-nginx** | 需要你在 Zero Trust UI 操作(我沒有 API token) | 見 `REBUILD.md` Phase 6;切完後 WAF 才會收到真實流量 |
| **Cloudflare API Token** | 你只給了 connector token | `cloudflare` enforcer 是 stub;沒 API token 收到 `cloudflare` EP 決策時回 `not_configured` |
| **預設密碼全換** | bootstrap 用 placeholder | Grafana / ClickHouse / EveBox(目前 no-auth)逐一加固 |
| **Forgejo push** | forgejo bind 127.0.0.1:3000 沒對外 | git remote 還沒設,程式碼只在 sec-vm 本地 + PVE host `/root/sec-vm-bootstrap/` |

### 已部分驗證但缺實戰流量
| 項目 | 已驗 | 缺 |
|---|---|---|
| Intake 路徑(coraza/vector/manual)| ✅ 200,case 進 BP | network_activity / process_activity / detection_finding **mapping 已加但未實測** |
| Executor 路徑 | ✅ block + unblock 兩輪都閉迴圈 | partial / failed 路徑未演練 |
| BP TTL cron unblock | ✅ 兩次 | 邊角:cron 跑時 BP 重啟、bridge 重啟 |
| WAF 阻擋 | ✅ SQLi/XSS/PT | 真實大流量、誤判處理流程 |
| Suricata IDS | 🟡 規則 4 萬條已載,但 sec-vm L2 看不到別人流量 | 等 hostname 切過後才有實際 alerts |
| crowdsec enforcer | ✅ apply 成功(實作完整) | unblock 測試只用 nftables,crowdsec 未實測 |
| cloudflare enforcer | ❌ stub only | 等 API token 才能寫實作 |

### 設計上選擇不做的
| 項目 | 為什麼 |
|---|---|
| Falco | docker-compose 註解中。需 kernel headers / eBPF,部署成本高,先延後 |
| 自己 SIEM 規則引擎 | 改用 BP 端 workflow 做關聯 + 案件,符合「不重複造輪」 |
| 自動 push 出去的 webhook | 契約 §1 明文反對,executor 永遠拉 |
| Logpush 從 Cloudflare → ClickHouse | 需要 Cloudflare Pro+,目前不需要 |

## 3. 關鍵設計決策紀錄(why 不在 code 裡)

| 決策 | 為什麼這樣選 |
|---|---|
| sec-vm 用 IP `192.168.0.20` 而非加入 `vmbr1` 內網 | BP 對接靠 LAN 直接 + Cloudflare Tunnel 出站,不需要 L3 NAT 中間層;架構更簡單,失敗點更少 |
| od-bridge 用 `network_mode: host` | 為了讓 nft enforcer 能影響 host netns,不必再用 nsenter 之類 hack |
| Vector 走 docker bridge network | 不需要 host net,而 ClickHouse 也在同 network 直連名稱解析簡單 |
| 用 `coraza` 字串標 source_system 不用 `modsecurity` | BP intake key 的 allowed_source_systems 沒有 modsecurity,coraza 同類接近且已被許可 |
| ClickHouse 只 bind 127.0.0.1 | 只給容器內部用 + sec-vm 上 SQL UI,不對外暴露 |
| WAF backend 預設 `:8000`(BP gunicorn) | 占位用,真實情境靠 cloudflared Zero Trust ingress 為主;多 domain 需多 WAF instance |
| EveBox `--no-auth` | LAN 內部用,不擋外部(預設 cloudflared 不路由它);要對外加 reverse proxy + auth |
| Grafana datasource 用 native protocol(:9000)而非 HTTP(:8123)| native 對大查詢更快,Grafana ClickHouse plugin 預設選項 |
| executor 處理 401 第一次只 invalidate token,連續 401 才退避 | 避開 SA login 限速 10/min,但又能快速從正常 token expiry 中恢復 |
| nftables enforcer 容忍 `does not exist` 與 `no such file` 兩種 nft 錯字串 | 不同 nftables 版本訊息可能不同 |
| docker-compose 不加 Falco | 降低初次部署複雜度與失敗風險 |
| 三組密鑰(intake / SA / tunnel)都放 .env,.env 在 .gitignore | 平衡可讀(本地查)vs 不外流;後續可改 secrets 管理服務 |

## 4. BP 端我這邊有依賴的承諾

(若 BP 改了這些,我這邊要跟著改)

- 端點路徑前綴 `/beakplatform/api/open_defense/*`
- HMAC 簽章演算法 `sha256=hex(HMAC-SHA256(secret, "{ts}\n{body_raw}"))`
- JWT 有效 15 分鐘,SA login 限速 10/min per IP
- 狀態機:`pending → picked_up → applied/partial/failed`,executor 不可寫 `expired/revoked`
- TTL 過期由 BP cron 主動下對應 `unblock` 決策(executor 不自行撤)
- `decided_via` 接受 `human/auto/ai` 三選一(其他值會被替換)
- intake 重送同 `correlation_id` 回 200 + `duplicate:true`(冪等)

## 5. 名詞速查(縮寫地獄解)

| 詞 | 意思 |
|---|---|
| **OCSF** | Open Cybersecurity Schema Framework,事件正規化標準,Apache 2.0 |
| **OD** | Open Defense — 本契約代號,BP 端模組名 / API 路徑前綴 |
| **BP** | BeakPlatform —— 案件流程引擎,本 stack 的對端 |
| **SA** | Service Account —— BP 端為 executor 開的程式帳號,JWT 認證 |
| **EP** | Enforcement Point —— 決策落地的地方(crowdsec / nftables / cloudflare / ...)|
| **bridge / od-bridge** | 我寫的 Python 程式,雙職:intake forwarder + decision executor |
| **enforcer** | bridge 內各 EP 的實作模組(`enforcers/nftables.py` 等) |
| **intake** | 事件「進」BP 的方向(外部 → bridge → BP) |
| **executor** | bridge 「拉決策出來」的方向(BP → bridge → enforcer) |
| **SC / secure_code** | BP 的 UUID-like 識別符,所有資源不用 auto-id 都用這個 |
| **case** | BP 端一筆 form_instance + workflow_instance 的整體 |
| **decision** | BP `od_defense_decisions` 表一筆紀錄,executor 拉的對象 |
| **CRS** | OWASP Core Rule Set —— ModSecurity 用的標準規則集 |
| **LAPI** | CrowdSec Local API —— bouncer / bridge 連 CrowdSec 的 HTTP 端 |
| **CRS Paranoia** | 1=寬鬆,4=偏執;誤判率指數成長 |
| **EVE** | Suricata 的 JSON 事件輸出格式 |
| **VRL** | Vector Remap Language —— Vector 內建的 transform DSL |
| **TTL** | Time To Live —— 決策過期秒數,kernel 與 BP cron 雙保險 |

## 6. 下次接手建議的優先順序

1. **切 Cloudflare hostname**(5 分鐘) → 讓真實流量進來
2. **看 Grafana 一週**,觀察 false positive,調 ModSec PARANOIA / 規則白名單
3. **拿 Cloudflare API token,實作 cloudflare enforcer** —— 寫 `enforcers/cloudflare.py` 真實版(IP List API)
4. **Forgejo 對外開,把 stack push 上去** —— 加版控
5. **重置所有預設密碼**(`CREDENTIALS.md §11` 的輪替建議)
6. **(視需求)加 Falco** —— 容器與 host syscall 行為偵測
7. **(視規模)第二台 sec-vm** —— 各自 SA / intake key,共用 BP

## 7. 收工檢查清單(我這次完成的)

- [x] sec-vm clone + Docker 安裝
- [x] 全 stack docker-compose 部署(10 容器)
- [x] BP 端 intake / SA login / GET decisions / PATCH 全部驗過
- [x] 端到端閉迴圈:block applied → expired → unblock applied
- [x] WAF SQLi/XSS/PT 阻擋驗過
- [x] od-bridge 內建 /stats /forwards /decisions HTML 頁
- [x] Grafana auto-provision dashboard
- [x] EveBox / Portainer / Vector playground 全活
- [x] 8 份文件:README + ARCH/REBUILD/CONFIG/BP/UI/PITFALLS/MON/OPS
- [x] HANDOFF.md(本檔)
- [x] CREDENTIALS.md(gitignored)
- [x] 38+ 條坑記錄到 PITFALLS.md
- [x] git repo 三次 commit(initial / docs / UI)

收工。
