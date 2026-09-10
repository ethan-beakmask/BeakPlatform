# sec-vm（`.20`）架構與運維手冊

**最後更新：2026-09-10（ITHome2026-WAF 讀者版一鍵安裝、`.20` 換裝、dmz-web tunnel 與 www 歡迎頁上線；2026-08-15 PF-104 建立）**
**權威範圍**：本檔記錄跑在 `.20`（sec-vm）上、BeakPlatform-dev **之外**的 Open Defense
安全棧（Vector、Suricata、Coraza WAF、CrowdSec、ClickHouse、Grafana、EveBox、
od-bridge）。平台側（`.16`，`/opt/BeakPlatform-dev` 內）的程式架構在
`dev-notes/OPEN_DEFENSE_ARCHITECTURE.md`，那份不含本檔內容，兩邊互補。

**取代對象**：本檔取代 2026-08-15 前的外部文件
`/opt/Ethan_Lab/ITHome-2026/CLAUDE.md`（PF-104 收斂）。
該外部檔案與其所在目錄**已於 2026-08-15 依用戶指示整個刪除**，
最終備份 `/opt/tmp/backup/ITHome-2026-final-20260815.tar.gz`（8.4MB / 107 項，
含不入庫的 `CREDENTIALS.md` 與 `.env`）。**本檔即唯一權威，沒有第二份可對照。**

**為什麼要分兩份**：`.16` 與 `.20` 各自會改，混在一份必定漂移。

> **2026-09-10 起 `.20` 已換裝成 `ITHome2026-WAF/`（`/opt/ithome2026-waf`），`sec-vm-bootstrap/` 退役封存在
> `dev-notes/archive/sec-vm-bootstrap-retired-20260910/`。** 本檔第 12 節之前凡提到
> `sec-vm-bootstrap/`、`~/sec-vm-bootstrap`、`vector.production.yaml`、`nftables-bootstrap.sh`、
> 「scp 後 md5 比對」的段落都是歷史，現在的對應是：設定檔權威 `ITHome2026-WAF/`；
> `.20` 部署目錄 `/opt/ithome2026-waf`（`.env` 與 `generated/` 為主機專屬）；
> 改設定流程 = 改 `ITHome2026-WAF/` → rsync 到 `.20:/opt/ithome2026-waf` → `sudo bash install.sh --reconfigure`；
> 防火牆由 `nftables.sh` 依 `.env` 產生（不再手改 heredoc）；vector 設定是 `vector/vector.yaml`
> 一份（值來自 `.env`）。埠、來源管制、ClickHouse 白名單、時區等環境事實不變。
> 遷移憑證 `/opt/tmp/verify/20260910-dot20-migrate.log`（ClickHouse 8206 筆歷史資料保留、
> 既有 intake key／SA／CrowdSec machine／EDL state 沿用，Internet 端 SQLi 403 → `.16` 建案）。

---

## 多租戶佈署架構定案（2026-08-16，Ethan 拍板）

### 定位變更：`.20` 不是平台的一部分

**`.20` 這整套是「每家企業一份的邊緣元件（collector）」，營運商自己這台只是第一個實例。**
企業無力維運時由營運商**代管**——代管的是 N 個各自獨立的小盒子
（**single-tenant instance, multi-instance**），不是一個大盒子服務 N 家。

本檔其餘章節的敘述仍以現況（單一實例）撰寫，**改寫隨第二段（PF-118）進行**；
看到「平台外組件」這類舊措辭時以本節為準。

分界線是把三件事拆開：

| 事情 | 集中還是分散 |
|---|---|
| 正規化規則（PA / Fortinet / CEF / LEEF → OCSF 的 parser） | **集中維護**（產品價值；各企業自寫必然品質不一、共同軸線對不上），**分散執行** |
| 執行位置與資料落地 | **分散**（原始日誌含內網 IP／帳號／URL，離開企業邊界即進入委外與個資合規面） |
| 傳輸憑證 | **企業自持，per-org** |

### 為什麼否決「跨企業集中受理中心」

1. **憑證集中 ＝ 跨租戶橫向移動樞紐**。集中式那台須同時持有 N 家 intake key，
   被打下來即取得 N 家的事件注入權——而事件驅動自動封鎖決策，
   **注入權在本系統等於處置權**
2. **現況 throttle 在多租戶下直接是跨租戶 DoS**。Vector 的 `intake_global_throttle`
   是全域 8 筆/60 秒、不分 key（PF-103 實測 5610 → 17 筆）。集中式要修得做公平排隊
   與 per-org 配額；多實例自動解決——各自的閥門管各自的水
3. **故障域與升級節奏**：集中式單點故障波及全部租戶，parser 一改全部同時受影響

集中式唯一真優點是跨企業威脅情資關聯——**用 IoC 摘要上報（IP／hash／rule_id，
不含原始 payload）即可達成**，資料量差數個量級且不涉日誌主權。

### 一併定調的四件事

- **保護判定只在平台端做一次**（PF-83 的「唯一判定實作」延續）。
  collector 只執行已核可的決策、**不帶本地保護清單**，避免兩份要同步
- **聚合鍵不加 `source_system`**。IDC↔HQ 備援時同一攻擊從兩個來源進來會自動併成一案，
  正是要的行為
- **同企業多台 collector 之間採君子協定**（相同架構同管理域，攻陷第二台的邊際成本很低）。
  `od_intake_keys.allowed_source_systems` 目前**未在 intake 時強制比對**——
  文件一律寫「已知未生效、優先度低」，**不要寫成「刻意不檢查」**。
  未來要補時與備援不衝突（該欄位是 list，HQ 那把可同時列 IDC 與 HQ）
- **「公開 IP 當內部主機」的方向性識別留給資安人員調查**，本系統不做

**跨企業隔離不受上述任何一條影響**：租戶歸屬取自驗簽後的 key 記錄
`g.api_key.org_secure_code`（`backend/app/security/decorators.py:372`），
**不是從 body 宣稱的**。這條要守住，未來不得讓 body 指定 org。

### 主機需求

**第一段（PF-116／PF-117）純平台端改動，不需要任何新主機。**

第二段要開第二台 collector，理由是**一台驗不出多實例**：

| | `.20`（現有＝營運商自家實例） | 第二台（模擬客戶端） |
|---|---|---|
| 元件 | Vector + Suricata + CrowdSec + od-bridge + EDL enforcer + ClickHouse | **只裝 Vector + od-bridge** |
| 規格 | 現況 | 2 vCPU / 2GB RAM / 20GB disk |
| 綁定企業 | beluga（營運商） | lion（測試租戶，合約已建） |

不裝 Suricata／ClickHouse 是刻意的：要驗的三件事都在傳輸與歸屬面——
**參數化是否真的做到**（換一組參數就能起第二台）、**兩把 key 各自歸屬正確**、
**lion 的事件不會跑進 beluga**。

**不要用「在 `.20` 上跑第二個 Vector 實例」代替**——那只驗得到資料面隔離，
驗不到單租戶實例的本意（OS 級隔離、獨立故障域、獨立升級節奏），
而那正是否決集中式的理由。省下的資源不值得讓驗證失真。

### 連帶要決定的產品分級（第二段設計題）

ClickHouse 要不要每家一份？現況它在 `.20` 存全量事件（180 天分層保留）。
事件湖跟著實例走才符合資料主權的一致性，但小企業未必需要。建議分級：

- **基本版**：Vector + od-bridge，事件直送平台、不留本地湖
- **進階版**：加 ClickHouse 本地事件湖

第二台正好就是「基本版」的第一個實例，順便驗證這個分級成立。

### 分段與待辦對應

| 段 | 內容 | 待辦 |
|---|---|---|
| 第一段（ITHome 比賽前，約 2 晚） | 既有缺陷修復，與架構決策無關、本來就該做 | **PF-116**（`execution_code` 序號池跨企業共用）、**PF-117**（protected-targets per-org 化 + 停止外洩平台反代位址） |
| 第二段（ITHome 比賽後） | collector 產品化（`sec-vm-bootstrap` 參數化、parser 套件版本化、多實例代管） | **PF-118** |

第二段有一部分依賴第一段：PF-117 的 fail-safe 設計要先落地，
collector 端才知道該不該帶本地清單（已定調不帶）。

**動工規格不在本檔**：本節只記決策與範圍。三張待辦的完整規格
（精確檔案路徑行號、已驗證的盤點結論、已排除的誤判、驗收步驟）在 BBN，
用 `note_search("PF-117")` 取全文，決策脈絡與支撐事實見知識原子 **#5204**。
**不要只憑本節動工**——例如 PF-116 的「全專案 56 處 `execution_code` 只有 2 處是
查詢條件」這類已驗證結論只寫在卡片裡，重查一次要花掉一輪。

### 開第二台之前要先決定的事（2026-08-16 尚未決定，不是遺漏）

以下每一項都還沒答案，**照本節動工的人不必去別處找，那裡也沒有**——
要嘛問 Ethan，要嘛在開機當下決定並回頭補進本節：

- **主機身分**：IP／hostname、OS 版本、由誰建（Proxmox VM）、登入方式與 sudo 權限
- **網路**：需開放的埠與方向、能否直連 `.16:7000`、走 LAN 或 Cloudflare、
  要不要納入 `.20` 那套 nftables 白名單模式
- **部署路徑**：`.20` 是 `~/sec-vm-bootstrap/`，第二台是否沿用同路徑與同一套 compose
- **lion 的 intake key 怎麼發**：建立、保存、輪替的流程（`od_intake_keys` 已有
  `expires_at` 與 `revoke_key()`，缺的是流程）
- **`source_system` 命名規則**：多實例後它同時是路由條件與 `allowed_source_systems`
  的比對對象，命名要先定好再鋪開

（本清單來自 2026-08-16 的 codex 冷讀。冷讀另外列出的「PF-1xx 規格缺失」
是它讀不到 BBN 造成的，不是本檔缺口。）

---

## 元件與職責（三段式架構）

| 段 | 元件（跑在 `.20`） | 職責 |
|---|---|---|
| 偵測 | Coraza WAF（nginx+ModSec+CRS）、Suricata、CrowdSec、Falco（未啟用） | 產生告警 |
| 正規化/儲存 | Vector（轉 OCSF）、ClickHouse | 統一 schema、歷史 SIEM |
| 案件流程 | BeakPlatform（`.16`，webhook intake → 表單 workflow → 決策 DB） | 人/AI 決策、TTL 自動 unblock |
| 自動處置 | od-bridge executor | 落地到 nftables / CrowdSec / Cloudflare / EDL |

刻意設計成「一張 ClickHouse 寬表 + 一張決策表 + 一個 webhook」，元件想換就換；
授權全 Apache/MIT/MPL，無 GPL 嵌入問題。

**自寫程式只有 od-bridge**（`sec-vm-bootstrap/od-bridge/`，Python，EDL enforcer +
Stats/Forwards/Decisions 三頁 in-memory UI，重啟清零）。其餘六個 Web UI
（Grafana、EveBox、ClickHouse Play、Portainer 等）全是元件自帶介面，本 stack
只負責把它們接起來、產生設定檔。

## 設定檔權威副本

`.20:~/sec-vm-bootstrap/` 是**實際部署**（docker compose 掛載中，改行為要在 `.20`
上直接改）。版控的權威副本在本專案頂層 **`sec-vm-bootstrap/`**（PF-104 起，
`scripts/push_github.sh` 的 `EXCLUDE_DIRS` 已排除，不會推上 GitHub）。

**副本不含**：`.env`（只留 `.env.example`）、`CREDENTIALS.md`、
`suricata/rules/*.rules`（上游 ET 規則集，42M×2，可重新下載）、
`waf/log/`（執行期 log）、各種 `.bak.*`。這些留在 `.20` 本機，不進版控。

**方向固定是「先改 `.16` repo，再同步到 `.20`」**（2026-08-16 冷讀指出本段
原本沒講清楚，兩邊都像權威）。PF-112 的實際流程可照抄：

```bash
# 1. 改 /opt/BeakPlatform-dev/sec-vm-bootstrap/ 底下的檔案
# 2. 送過去（docs/ 是 root-owned，要 sudo cp）
scp -i ~/.ssh/company-wsl <files> ethan@192.168.0.20:/tmp/
ssh -i ~/.ssh/company-wsl ethan@192.168.0.20 \
  'cp -a /tmp/<file> ~/sec-vm-bootstrap/<路徑>/ && cd ~/sec-vm-bootstrap && \
   sudo docker compose up -d --build <service>'
# 3. md5 兩邊比對（少了這步就會出現「改了但沒生效」）
md5sum /opt/BeakPlatform-dev/sec-vm-bootstrap/<file>
ssh -i ~/.ssh/company-wsl ethan@192.168.0.20 'md5sum ~/sec-vm-bootstrap/<file>'
```

反過來直接改 `.20` 再回填容易漏檔，不要那樣做。

**改 `sec-vm-bootstrap/` 時會撞到的兩件事**（2026-08-16 PF-112 試誤）：

- **`vector/vector.yaml` 在 `.16` 與 `.20` 都是指向 `vector.production.yaml` 的
  symlink**，實際生效的是 production 那份。改設定只要改 production
  （與 research），`vector.yaml` 不必也不該改成實體檔
- **`.20` 的 `sec-vm-bootstrap/docs/` 是 root-owned**，`scp` 進 `/tmp` 後
  要 `sudo cp -a` 才蓋得過去。直接 `cp` 會拿到 `Permission denied`，
  而且若寫在一長串 `&&` 裡很容易被忽略過去（od-bridge 程式與 vector 設定
  則是 ethan-owned，不需 sudo）

`.20` 的服務密碼在 `.20:~/sec-vm-bootstrap/CREDENTIALS.md` 與 `.20:~/sec-vm-bootstrap/.env`；
BeakPlatform 的資料庫連線在 `/opt/BeakPlatform-dev/.env`。
**平台 UI 的登入帳密不在本專案文件內，需要時直接問用戶。**

## 環境事實

```
.16 (BeakPlatform)  管線接收端，dev 實例 :7000（systemd beakplatform-dev.service）
.20 (sec-vm)        Suricata / Coraza WAF / Vector / ClickHouse / CrowdSec / od-bridge
                     ssh -i ~/.ssh/company-wsl ethan@192.168.0.20（ethan 有 sudo NOPASSWD）
.100 (Proxmox 母機)  `ssh root@192.168.0.100`（2026-09-08 起 .16 的
                     ~/.ssh/id_ed25519 已佈署，免密碼）。密碼登入仍開著但
                     **22 埠只放行 .10 與 .16**，其餘來源連不到——見下方
                     「網路隔離：Proxmox 防火牆」。2026-08-16 記的「無法登入」
                     是當時用 company-wsl 那把金鑰的結果，已過時。
                     需要「非白名單來源」做驗證時仍不要指望它，
                     改在 .16 臨時借一個 secondary IP（見 CONFIGURATION.md 的
                     ingest 面來源管制段）
```

### `.66` 的定位（2026-09-08 Ethan 明確定調）

**`.66`（BP-EndUser）是對外的【公開服務】，不是靶機。**
它跑的是本專案 push 到 GitHub 後照客戶路徑安裝的產品實例，用途就是提供服務。
公開服務必然會被掃描與攻擊，那是風險不是目的；`.20` 的 WAF 偵測這些流量並產生
資安事件送進平台，是產品本身的正常運作。**不要把它描述成「為了產生資安事件而
架的靶機」，也不要為此主動製造攻擊流量**——真實的入口鏈（CF edge → cloudflared
→ WAF → `.66`）本來就會被真實流量走過，那才是「機制是否正常」的自然驗證來源。

### 網路隔離：Proxmox 防火牆（2026-09-08 建立）

`.16` / `.20` / `.66` 都是同一台 Proxmox（`.100`）上的 VM，掛在單一 `vmbr0`
直接橋接實體網卡，**與 `.10`（Ethan 的 Windows 工作機）同一個 L2 廣播域**。
Proxmox 預設不隔離 VM，加固前實測從 `.66` 可直接連 `.100:8006`、`.100:22`、
`.10:445`、`.10:3389`、`.20:8123`。

現在由 Proxmox 防火牆（host 端 tap 介面，VM 內部繞不過）阻斷：

| 對象 | 規則 |
|---|---|
| `.100` 入站 | 只有 `.10` 全開、`.16` 僅 22；管理埠（8006/22/3128/5900-5999/60000-60050）其餘來源一律 DROP |
| `.20`、`.66` 出站 | DROP 到 `.100` 與 `.10`；`.66` 另外 DROP 到 `.20` |

**完整規範、三個踩過的坑（`host.fw` 不吃 policy_in、management ipset 自動含整個網段
且無法用 `[IPSET management]` 覆蓋、VM 需要 `firewall=1` 旗標）寫在全域
`~/.claude/knowledge_base/configurations/system_configs/network_architecture.md`
的「Layer 0」一節**——那是系統層事實，本檔不留會漂移的副本。

`.20` 的 nft `ingest_guard` 仍然是 `.20` 自己那一層，兩者不重疊：
Proxmox 那層管「VM 之間」，nft 管「誰能連進 `.20` 的服務」。

**脫敏原則**：IP / port / 帳號 / 範例密碼**只要不 push 到 GitHub 都無妨**（教材
用途，測試環境）。發布到對外管道（如技術文章）前需人工過濾。本檔與
`sec-vm-bootstrap/` 都在 `EXCLUDE_DIRS`／頂層排除清單內，正常操作不會外流；
`CREDENTIALS.md` 例外——那是跨機器主鑰匙清單，任何情況下都不進版控（連
`dev-notes/` 也不要）。

### 驗證用指令

```bash
# Vector 拓樸與吞吐（免 SSH，API 對 LAN 開放）
# 注意：GraphQL 的 components 查詢回傳不完整，必須用 sources/transforms/sinks 分別查
curl -s -X POST http://192.168.0.20:8686/graphql -H 'Content-Type: application/json' \
  -d '{"query":"{transforms{edges{node{componentId metrics{receivedEventsTotal{receivedEventsTotal} sentEventsTotal{sentEventsTotal}}}}}}"}'

# 觸發一次真實 WAF 告警（在 .20 上）→ 應建立案件
curl -H 'Host: beakmask.org' -H 'Cf-Connecting-Ip: 203.0.113.99' \
  "http://127.0.0.1:8080/?id=1%27%20OR%20%271%27=%271"

# .16 查最新 intake（用 postgres 系統帳號，不必密碼；
# 寫成 psql -h localhost -U beakplatform 會停在密碼提示）
sudo -n -u postgres psql -d beakplatform_dev -c \
  "SELECT id,source_system,case_secure_code,received_at FROM od_intake_events ORDER BY id DESC LIMIT 5;"

# 灌合成事件進管線（繞過 Suricata/Coraza，測 Vector→bridge→.16 那一段）
# PF-109 起 8688 只綁 127.0.0.1，必須在 .20 上打，從 .16 會連線逾時
ssh -i ~/.ssh/company-wsl ethan@192.168.0.20 \
  "curl -s -X POST -H 'Content-Type: application/json' --data @event.json http://127.0.0.1:8688/"
```

### 資料庫欄位與查詢陷阱（每個 session 都會撞）

| 你以為的 | 實際的 |
|---|---|
| `od_intake_events.actor_ip` | **不存在**。攻擊者 IP 在 `raw_body->'actor'->>'ip'`，rule_id 在 `raw_body->'finding'->>'rule_id'` |
| `fw_form_instances.execution_code` | **不在這張表**，`OD-YYYYMMDD-NNNN` 在 `fw_workflow_instances.execution_code` |
| `users.name` / `users.full_name` | **都不存在**，欄位是 `display_name` |
| `fw_form_templates.status` | **不存在**（發行狀態看 `fw_published_form_workflows.status`） |
| `od_service_accounts.name_hint` | **不存在**，欄位是 `name` |
| `workflow_snapshot` 可直接用 jsonb 函式 | **是 json 不是 jsonb**，要先 `::jsonb` 才能用 `jsonb_array_elements` |
| 節點在 `workflow_snapshot->'graph'->'elements'->'nodes'` | 實際是 `->'graph'->'nodes'`，且 `id`/`label` 在**節點頂層**、設定在 `->'config'` |

### 跑 BeakPlatform 的 standalone script／flask shell

直接跑會死在 `ValueError: SECRET_KEY environment variable is required`。
必須先載入 `.env`：

```bash
cd /opt/BeakPlatform-dev/backend
set -a; source /opt/BeakPlatform-dev/.env; set +a
FLASK_APP=app /opt/BeakPlatform-dev/venv/bin/python <script>
```

### 時區：`.16` 與 `.20` 不同（跨主機比對必踩）

`.16` 是 **UTC+8**（CST），`.20` 是 **UTC**。同一件事在兩邊的 log 差 8 小時。
DB 的 `received_at` / `expires_at` 存 UTC。

**因此 `WHERE received_at > now() - interval '15 minutes'` 會查不到剛進來的事件**
（`now()` 回台北時間，欄位是 naive UTC，差 8 小時＝永遠不在窗內）。
剛做完的動作要驗證時，直接取最新幾筆最省事：

```sql
SELECT received_at, source_system, event_class, case_secure_code IS NOT NULL AS has_case
FROM od_intake_events ORDER BY received_at DESC LIMIT 5;
```

要真的用時間窗就寫 `now() at time zone 'Asia/Taipei'`（或 `at time zone 'UTC'`
視 DB 時區設定而定，用前先 `SELECT now(), now() at time zone 'UTC';` 對一次）。

### `.20` 的絕對路徑與容器名（別用 `~` 猜）

```bash
# compose 工作目錄（ethan 的家目錄下）
/home/ethan/sec-vm-bootstrap
# 所有操作都要先 cd 進去，docker compose 才找得到 .env 與 compose 檔

docker ps --format '{{.Names}}\t{{.Status}}'
# secstack-od-bridge-1 / secstack-vector-1 / secstack-suricata-1
# secstack-clickhouse-1 / secstack-crowdsec-1 / secstack-waf-nginx-1
# secstack-evebox-1 / secstack-grafana-1 / secstack-portainer-1

docker logs --tail 50 secstack-od-bridge-1     # 決策落地與 EDL 的即時狀況
```

### 封鎖是否真的落地：三個判準各查各的

```bash
# 1. kernel 端（.20）——表名 inet secstack，set 名 blocklist / blocklist6 / allowlist
sudo nft list set inet secstack blocklist
# 元素會顯示 `<IP> timeout 5m expires 4m42s`，倒數歸零後 kernel 自動剔除
# allowlist 是自鎖保險（192.168.0.16 / .10 / .100），命中者永遠不會被封

# 2. EDL 端（.20）——預期是純 IP、一行一個、零註解；空清單回空內容不是 404
curl -s http://192.168.0.20:8500/edl | od -c

# 3. 平台端（.16）——application_result 才看得到 enforcer 的真實回報
sudo -n -u postgres psql -d beakplatform_dev -c \
  "SELECT id,action,target_value,status,enforcement_points,application_result
   FROM od_defense_decisions ORDER BY id DESC LIMIT 5;"
```

**`status=applied` 不代表真的封成**：曾有 `failed` 案例，`application_result`
裡才看得到 `nft: No such file or directory`。**一律看到第三欄為止。**

### 從 intake 事件追到案件、節點、簽核者

```bash
sudo -n -u postgres psql -d beakplatform_dev -c "
SELECT e.id, e.source_system, e.event_class, e.case_secure_code,
       wi.execution_code, wi.status, wi.current_node_id
FROM od_intake_events e
LEFT JOIN fw_workflow_instances wi ON wi.secure_code = e.case_secure_code
ORDER BY e.id DESC LIMIT 5;"

# 案件停在哪個節點、誰能簽（assignees 是節點啟動當下的快照，不會隨角色異動更新）
sudo -n -u postgres psql -d beakplatform_dev -c "
SELECT q.node_id, q.node_type, q.status,
       (q.result::jsonb)->'data'->>'assignee_type' AS a_type,
       (q.result::jsonb)->'data'->'assignees'      AS assignees
FROM fw_node_execution_queue q
WHERE q.workflow_instance_secure_code='<wi_secure_code>' ORDER BY q.id;"
```

### 決策的生命週期與到期回收

- 執行端 service account：`sa_executor_secvm_01_<後綴>`（`od_service_accounts`），
  `allowed_enforcement_points` **必須含該 EP，否則決策根本不會被派送過去**
- od-bridge executor 每 **5 秒** 輪詢 `/api/open_defense/decisions?status=pending`
- 到期回收由 `.16` 的 `/etc/crontab` **每分鐘**跑 `od_expire_decisions.py`：
  把過期的 block 轉 `expired` 並自動產生一筆 `unblock` 決策
- 要驗完整閉環，TTL 設 120～300 秒再等 cron 跑；log 在
  `/opt/tmp/BeakPlatform-dev-cron-od_expire_decisions.log`

### od-bridge 的埠別

| 埠 | 服務 |
|---|---|
| `.20:8500` | **od-bridge**（`/stats` `/forwards` `/decisions` `/edl` `/edl/allow` `/state/nft` `/health`） |
| `.20:8688` | Vector 的合成事件注入口 |
| `.20:8686` | Vector GraphQL API |
| `.20:8080` | WAF（**2026-09-08 起**反向代理到 `http://192.168.0.66:8000`＝BP-EndUser 客戶模擬環境；`.66` 的 80 埠是 nginx default site 回 404，平台在 8000，所以埠號不能省。舊值 `.16:80` 的對外服務已於 2026-08-05 退役） |
| `.20:8123` | ClickHouse HTTP（帳號層白名單，見下方「ClickHouse 存取」） |
| `.20:9000` | ClickHouse native |
| `.20:3000` | Grafana |
| `.20:5636` | EveBox（自簽 TLS） |

od-bridge `/events` 需 `Authorization: Bearer`；`/health` 免驗。

### `.20` 幾乎每個埠都有來源管制，測試前先確認你在白名單內

**PF-109（ingest 面）與 PF-107（SSH + 管理面）之後，`.20` 對 LAN 只剩 ClickHouse
走另一套機制，其餘全部收在 nftables 白名單裡。** 不知道這件事的症狀是
**連線逾時而不是 403**——跟「服務掛了」長得一模一樣，會白花很多時間查錯地方。

| 埠 | 誰打得到 | 手段 |
|---|---|---|
| `22` sshd | `.10` / `.16` / `.100` | nft `ssh_guard_input`（PF-107） |
| `3000` Grafana | `.10` / `.16` / `.100` | nft `mgmt_guard_forward`（PF-107） |
| `5636` EveBox | `.10` / `.16` / `.100` | 同上 |
| `8080` WAF | `.16` / `.10` / `.100`，加 `.20` 本機的 `127.0.0.1` | nft `ingest_guard_forward`（PF-109） |
| `8123` / `9000` ClickHouse | 綁 LAN IP + **帳號層**網路白名單 | `clickhouse/users.d/`，不在 nft chain 內 |
| `8500` od-bridge | 只有 `.16`，加 docker bridge（vector 走這條） | nft `ingest_guard_input`（PF-109） |
| `8686` Vector API | `.10` / `.16` / `.100` | nft `mgmt_guard_forward`（PF-107） |
| `8688` vector 注入口 | **只有 `.20` 本機**（ports 綁 `127.0.0.1`） | docker-compose + nft 雙保險 |
| `9443` Portainer | `.10` / `.16` / `.100` | nft `mgmt_guard_forward`（PF-107） |

- 上表「Vector 的合成事件注入口」那條在 `.16` 上已經**打不進去**，
  要灌合成事件得先 `ssh .20` 再打 `127.0.0.1:8688`
- **od-bridge 的 stats UI 從 `.10` 的瀏覽器連不到是刻意的**，不是壞了
- 四條 nft chain 都以 `iifname != "ens18" accept` 開頭，所以本機打
  `127.0.0.1:8080`（走 lo）與 vector→`host.docker.internal:8500` 這兩條內部路徑
  不受影響。**反過來說，從本機打 8080 的探測完全繞過防火牆判定**——
  已廢除的 canary 就是這樣只驗到 WAF 容器活著（見下方廢除說明）
- **hook 選錯的症狀是 counter 恆為 0，不會報錯**：docker 發布的埠（3000/5636/8080/
  8686/8688/9443）走 DNAT 後進 **forward**；host network 的服務（sshd 22、
  od-bridge 8500）進 **input**。加新埠時先看它是不是 docker 發布的
- 規則定義在 `sec-vm-bootstrap/nftables-bootstrap.sh`（同時寫 `/etc/nftables.conf`，
  開機由 `nftables.service` 還原）。**改埠或搬服務時，這裡與 compose 兩處都要改**
- 判斷「連不上是被擋還是服務掛了」，看 counter 有沒有跳：
  `sudo nft list chain inet secstack mgmt_guard_forward | grep counter`
- **22 埠的 drop 另外有 log**（`ssh_guard_input`，rate limit 20/分鐘）。
  counter 只給數字、給不出來源，所以那條加了 log——規則上線半小時內 drop counter
  就跳到 5（一次 TCP SYN 重傳序列的量），來源當時查不出來。查法：

  ```bash
  sudo journalctl -k --since '-1 day' | grep SSHGUARD_DROP
  ```

  管理面那條沒有 log（目前 drop 恆為 0），要加就照 `ssh_guard_input` 的樣子寫

**管理面為什麼也要收（PF-107）**：這四個之中 **EveBox 與 Vector API 完全無認證**
（EveBox 的 compose 明寫 `--no-auth`），Portainer 掛著 `/var/run/docker.sock`
拿下就等同 `.20` 的 root，而 Grafana 的 admin 密碼在 PF-107 之前一直是清冊裡的樣板值。
換密碼堵的是「用預設密碼登入」，堵不住無認證的那兩個，也堵不住暴力破解與未知 CVE。

**SSH 為什麼是收 IP + 走金鑰，而不是輪替密碼（Ethan 2026-08-16 定調）**：
密碼一定會流進對話記錄與交接文件，交談式 AI 遲早讓它再外洩一次；
金鑰不會被寫進文件，IP 白名單也不會因為誰讀了某份文件而失效。
所以 `.20` 的 `ethan` OS 密碼**刻意不輪替**（現值只有 Ethan 知道，
清冊裡那個 `P@ssw0rd` 早在 2026-05-17 就失效了，2026-08-16 實測密碼登入被拒）。

**2026-08-16 起 sshd 已停用密碼認證，只收公鑰**
（設定副本 `sec-vm-bootstrap/ssh/00-pf107-hardening.conf`）。所以現在有兩層，
症狀不同、處理方式也不同：連線逾時＝nftables 擋的；
`Permission denied (publickey)`＝sshd 擋的。

檔名的 `00-` 前綴是必要的：`sshd_config` 是 **first obtained value wins**，
而 `.20` 的 `50-cloud-init.conf` 寫死 `PasswordAuthentication yes`。
排在它後面的檔案會被靜默蓋過，**`sshd -t` 仍會通過、也不會有警告**——
驗證一定要看 `sudo sshd -T | grep -i passwordauthentication` 的展開值，不是看檔案。

副作用（預期，非待修）：`claude` 那個 OS 帳號沒有 `~/.ssh/authorized_keys`，
本設定生效後它完全失去遠端入口，只剩主控台。

**自鎖風險**：`ssh_guard_input` 的 priority（-150）早於 `chain input`（-100）的
`allowlist accept`，所以那道自鎖保險**救不了**被 ssh_guard drop 的來源。
最後退路是 PVE Web UI（`192.168.0.100`）→ VM 110 → Console，不經過網路堆疊；
console 登入要 `ethan` 的 OS 密碼（只有 Ethan 知道，不在任何文件裡）。

### 只想改一條 chain、不想清掉 blocklist 的做法

`nftables-bootstrap.sh` 是 `delete table` + 重建整張表，會清空 `blocklist` /
`blocklist6` 的動態元素（od-bridge 的封鎖決策就落在那兩個 set，
`enforcers/` 只碰 `blocklist` / `blocklist6` / `input` 這三個名字）。
改單一 chain 時用這個手法，其他 chain 與 set 完全不動：

```bash
# 1. 只重建目標 chain（delete + create 在同一個 nft transaction 裡，是原子的）
sudo nft -f - <<'NFT'
delete chain inet secstack ssh_guard_input
table inet secstack {
    chain ssh_guard_input {
        type filter hook input priority -150; policy accept;
        iifname != "ens18" accept
        tcp dport 22 ip saddr { 192.168.0.10, 192.168.0.16, 192.168.0.100 } counter accept
        tcp dport 22 limit rate 20/minute log prefix "SSHGUARD_DROP " level info
        tcp dport 22 counter drop
    }
}
NFT

# 2. 【必做】同步回 /etc/nftables.conf，否則重開機退回舊規則、而且不會有任何徵兆
#    做法是改 nftables-bootstrap.sh 的 heredoc，再從它重生 conf（不執行 nft -f）
sudo python3 - <<'PYEOF'
import re, pathlib
src = pathlib.Path("/home/ethan/sec-vm-bootstrap/nftables-bootstrap.sh").read_text()
m = re.search(r"cat > \"\$CONF\" <<.NFT.\n(.*?)\nNFT\n", src, re.S)
assert m, "抓不到 heredoc"
pathlib.Path("/etc/nftables.conf").write_text(m.group(1) + "\n")
PYEOF
sudo nft -c -f /etc/nftables.conf     # 語法檢查

# 3. 驗證 conf 那一段真的套得起來（-c 只驗語法，驗不到 runtime 衝突）
#    抽出該 chain 單獨套用，counter 歸零即證明重建過，blocklist 不受影響
```

**改規則前先掛自動還原**（PF-107 用的手法，nftables 與 sshd 同樣適用）：

```bash
sudo cp /etc/nftables.conf /root/nftables.conf.bak.$(date +%Y%m%d-%H%M%S)
sudo systemd-run --on-active=120 --unit=nft-rollback \
  /usr/sbin/nft -f /root/nftables.conf.bak.<剛才的時間戳>
# ... 改規則、驗證 ...
sudo systemctl stop nft-rollback.timer      # 通過才撤銷
```

`systemd-run --on-active` 是 transient timer，**不依賴你的 SSH session 存活**，
比 `nohup sleep` 可靠。想驗證 drop 分支就得站到被拒絕的那一側，
沒有這道保險就不敢做，而不敢做的結果是規則永遠只驗過 accept 那一半。

為什麼要管：Suricata 的 xff 模組與（修正前的）vector modsec transform 都沒有
「信任代理比對」，誰打得到 `.20` 誰就能把 `actor_ip` 填成任意第三方位址，
讓 CrowdSec 去封它——實測讓真實 AWS 位址 `3.3.3.3` 被 ban。`allowlist` 自鎖保險
只擋得住「封掉自己」，擋不住「封掉外部關鍵服務」（DNS、更新來源、上游 API）。

Coraza 那條線另外在 vector 端補了信任代理比對（`ocsf_from_modsec` 的
`trusted_ingress`，只認 `192.168.0.16` 與 `172.18.0.1`）。**Suricata 線補不了**：
`src_ip` 在 Suricata 內部就被 overwrite，eve.json 不留原始 TCP source，
改 `mode: extra-data` 又會讓 CrowdSec 改封 cloudflared@`.16` 自己。

**TZ-01 陷阱**：`received_at` 存 UTC，psql `now()` 回本地時間。
用 `received_at > now() - interval '30 minutes'` 會因 8 小時時差**查不到剛寫入的資料**，
一律改用 `ORDER BY id DESC LIMIT n`。跨主機比對時間戳一律換算成 UTC。

### 測試時會白忙一場的四個陷阱

1. **Suricata 看不到 `127.0.0.1`**：它監聽 `ens18`。打 localhost 永遠零告警。
2. **HOME_NET 是 `192.168.0.0/16`**：從 `.16` 打 `.20` 屬 HOME→HOME，
   `ET SCAN` 那類 `$EXTERNAL_NET -> $HOME_NET` 規則**永遠不觸發**。
   要示範 Suricata 就用出站規則（在 `.20` 上跑）：
   ```bash
   curl -s -o /dev/null --max-time 8 -A "Mozilla/5.0 dropper.exe" http://example.com/
   # → sid 2013224 ET HUNTING，會一路走到 .16 建案
   ```
3. **throttle 會吃掉測試流量**：同 `source|rule_id|actor_ip` 在窗內有配額
   （suricata 1 筆/3600 秒、coraza 5 筆/300 秒），另有**全域 8 筆/60 秒**封頂。
   要連續測就換不同來源 IP。
4. **`203.0.113.1` 曾是合成演習（canary）專用來源 IP，該機制已於 2026-09-07 廢除**。
   兩端的排程與腳本都已移除，這個 IP 從此不會再有新事件；
   DB 內既有 183 張演習案件刻意保留不清。廢除理由與實測數據見下方
   「合成演習（canary）已於 2026-09-07 廢除」一節。
   2026-08-16 的「演習視同作戰、每天 24 張演習單是刻意的訓練負載」定案
   **隨機制一併作廢**，不要照著做。
   vector 的 `intake_canary_route`（豁免全域 throttle）結構保留但不再命中任何事件。

5. **`POST /events` 需要 bearer token**（PF-112，2026-08-16 起）：
   手動灌事件進 od-bridge 少帶 header 一律 401，而 401 與「服務掛了」
   在只看 curl 結果時長得很像。
   ```bash
   TOKEN=$(grep '^BRIDGE_INGEST_TOKEN=' ~/sec-vm-bootstrap/.env | cut -d= -f2-)
   curl -X POST http://127.0.0.1:8500/events -H "Authorization: Bearer $TOKEN" ...
   ```

6. **自製合成事件很容易被 intake_filter 靜默丟掉**（測 vector→bridge 那段時）：
   - `actor.ip` 要用**公網**位址（`203.0.113.42` 之類）。內網 actor + 內網 target
     會被 `internal_actor && internal_target` 整批 drop
   - `source_system` **不要寫 `suricata`**，除非 `severity_id >= 2`——
     `low_sev_suricata` 會把 `sev <= 1` 的 suricata 事件 drop 掉
   - throttle key 是 `source_system|finding.rule_id|actor.ip`，
     重複測要換 `rule_id`，否則第二筆之後靜默消失
   - 事件到得了 bridge 不代表平台會建案：欄位不合 intake 契約時
     bridge log 會顯示 `forwarded ... status=400`（那是平台回的，不是 bridge 的錯）

**驗真實路徑最快的一招是手動打一次兩條探測**（原 canary 腳本的內容，
機制已廢除但指令本身仍是驗管線最省事的方式）：

```bash
# 路徑 A：Coraza / WAF（期望 HTTP 403）
ssh -i ~/.ssh/company-wsl ethan@192.168.0.20 \
  'curl -s -o /dev/null -w "%{http_code}\n" -m 10 -H "Host: beakmask.org" \
     -H "Cf-Connecting-Ip: 203.0.113.1" -A "OD-Probe/1.0" \
     "http://127.0.0.1:8080/?id=1%27%20OR%201=1--"'
# 路徑 B：Suricata（必須是 HOME→EXTERNAL 出站，觸發 sid 2013224）
ssh -i ~/.ssh/company-wsl ethan@192.168.0.20 \
  'curl -s -o /dev/null -m 10 -A "Mozilla/5.0 probe.exe" http://example.com/'
# 約 20 秒後看 bridge 有沒有把兩條路徑都送上去（期望 status=200）
ssh -i ~/.ssh/company-wsl ethan@192.168.0.20 \
  'docker logs secstack-od-bridge-1 --since 3m 2>&1 | grep -E "forwarded|401"'
```

**這兩條探測的驗證範圍有限，不要把它當成端到端驗證**：路徑 A 打
`127.0.0.1:8080` 走 lo，四條 nft chain 都以 `iifname != "ens18" accept` 開頭，
等於防火牆判定與真實入口鏈（CF edge → cloudflared `.16` → nginx `.20:8080`）
全部繞過，只驗得到「WAF 容器還活著」。這正是原 canary 被廢除的主因之一。

### 合成演習（canary）已於 2026-09-07 廢除

**現況：兩端的排程、腳本、heartbeat 全部移除**，備份在
`/opt/tmp/backup/od-canary-retire-20260907/`（含兩支腳本、`.16` crontab 原檔、
歷史 log；`.20` 上另有一份同名目錄）。DB 內既有 183 張演習案件
（`actor_ip=203.0.113.1` 或 `rule_id=2013224`，2026-05-09 ~ 2026-09-07）
刻意保留不清。

**廢除理由**（Ethan 2026-09-07 定調）：

1. **驗證範圍不對**。路徑 A 打 `127.0.0.1:8080` 走 lo，防火牆判定與整條真實入口鏈
   完全沒被覆蓋，只驗到「WAF 容器還活著」。要驗的是真實入口鏈到案件產生的端到端，
   而那條鏈只有真實對外流量走得到。
2. **每小時的頻率換不到偵測能力**。它防的失效（靜默斷流）以天甚至月為單位，
   每天一次照樣抓得到；每小時只換來每天 24 張無人消費的演習單與告警疲勞——
   收到告警的人問的是「這正常嗎」而不是「去排查」，這時候監控價值已經是負的。
3. **發動端與被檢查對象同生共死**。檢查器在 `.16`（對），發動端卻在 `.20` 自己身上。
   2026-09-07 實測到的失效正是這個後果：`.20` 上與偵測完全無關的 log 輪替
   把 canary 那一行 truncate 掉，告警卻長成「2/2 條偵測路徑沒有產生案件」，
   訊息裡的四步排查全部會回報正常，排查方向被帶偏。

**廢除當下的實測數據**（留給日後設計新演習時當基準）：

| 項目 | 數值 |
|---|---|
| 近 7 天 canary 應到筆數 | 336（168 小時 × 2 路徑） |
| ClickHouse 實收 | 43（通過率 13%） |
| `.16` `od_intake_events` 實收 | 42（od-bridge → `.16` 這段零損耗） |
| 同期 ClickHouse 全部事件 | 46（其中 43 筆落在第 17 分＝canary，真實攻擊流量近乎為零） |

**根因（未修，Ethan 決定不修）**：`/etc/cron.hourly/` 下 `secstack-canary`（先跑）
與 `secstack-rotate-logs`（後跑，相隔不到 1 秒）由 run-parts 在同一分鐘執行，
而 rotate 是 `cp` + `: > file`。Vector log 每小時 :17 固定出現
`Stopped watching file` → 3~4 秒後 `Found new file to watch`，
canary 在 :17:01 寫入的那行在被讀走之前就被清空。
**canary 廢除後這個競態仍在**，它一樣會吃掉每小時 :17 分那一秒寫入的真實事件
（目前該時段幾乎沒有真實流量，所以實際損失為零）。

`sec-vm-bootstrap/host-cron/README.md` 原本寫 copy + truncate「沒有『重新發現新檔』
的空窗，也不會重讀整個舊檔」——**前半與 2026-09-07 實測不符**，已在該檔更正。

### `.16` 服務的執行方式（會影響能不能重啟、改了程式碼何時生效）

```bash
# BeakPlatform 由 systemd 管理，非 debug 模式，改 Python/模板要重啟才生效
sudo systemctl restart beakplatform-dev.service
systemctl is-active beakplatform-dev.service
# 權威說明見 /opt/BeakPlatform-dev/CLAUDE.md 的「服務啟動」段
# 踩坑：若有人手動 flask run 佔住 7000 埠，systemd 會 crash loop（is-active 卡在 activating）
#       用 ss -tlnp | grep :7000 找出佔埠 PID kill 掉，服務即自動接手
# 健康檢查：curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:7000/beakplatform/ → 302

# 工作流執行器（.16 效能瓶頸所在，無併發上限）
pgrep -af workflow_executor_main.py
# 過載止血：停止派發新進程但不中斷既有的，消化完再 CONT
sudo kill -STOP <PID> ; sudo kill -CONT <PID>
```

**清理測試案件的陷阱**：聚合生效後（同 `actor_ip` + `rule_id`、60 分鐘窗），
一張案件可能同時關聯測試事件與真實事件。
用「事件 correlation_id 反查 case_secure_code 再刪案件」會誤傷——已誤刪過演習（canary）案件。

## 要改行為時，改哪個檔案

`.20` 上的執行環境全部需 ssh 進去改，**權威副本同步在本專案 `sec-vm-bootstrap/`**
（改完務必用下表方式驗證生效，再同步回本專案；比對用 `diff` 或 md5）：

| 要改的行為 | 檔案 | 改完怎麼生效 |
|---|---|---|
| 事件過濾、throttle（含全域封頂與 `intake_canary_route` 豁免分流，該分流已無事件命中）、OCSF 映射 | `.20:~/sec-vm-bootstrap/vector/vector.production.yaml`（`vector.yaml` 是它的 symlink） | `docker exec secstack-vector-1 vector validate /etc/vector/vector.yaml` 通過後 `docker kill -s HUP secstack-vector-1`，不必重啟容器 |
| Suricata 規則啟用/停用 | `.20:~/sec-vm-bootstrap/suricata/rules/suricata.rules`（停用是行首加 `# DISABLED <日期> <原因>: `，此檔不進版控） | `docker kill -s USR2 secstack-suricata-1`，用 `docker exec secstack-suricata-1 tail /var/log/suricata/suricata.log` 確認 `rules successfully loaded` 的數字有變 |
| eve.json / modsec log 輪替 | `.20:/etc/cron.hourly/secstack-rotate-logs`（權威副本 `sec-vm-bootstrap/host-cron/`） | 每小時自動跑；手動 `sudo /etc/cron.hourly/secstack-rotate-logs`，看 `/opt/tmp/sec-vm-rotate-logs.log` |
| 案件聚合窗、白名單、案件流程 | `.16:/opt/BeakPlatform-dev/modules/open_defense/services/intake_service.py` | **要手動重啟 dev 實例**（見上） |
| EDL 內容／格式、封鎖落地行為 | `.20:~/sec-vm-bootstrap/od-bridge/od_bridge/enforcers/`（權威副本 `sec-vm-bootstrap/od-bridge/`） | `docker compose up -d --build od-bridge`，用 `curl -s http://192.168.0.20:8500/edl \| od -c` 驗實際位元組 |
| nftables 封鎖表結構、自鎖 allowlist、**ingest 埠**（`ingest_guard_forward` / `ingest_guard_input`）、**SSH 與管理面**（`ssh_guard_input` / `mgmt_guard_forward`）的來源管制 | `sec-vm-bootstrap/nftables-bootstrap.sh` → 產生 `.20:/etc/nftables.conf` | 推上 `.20` 後 `sudo bash ~/sec-vm-bootstrap/nftables-bootstrap.sh`（寫檔＋套用）。**副作用：它 `delete table` + `create table`，會清空 `blocklist` 現有元素**——執行前先 `nft -j list set inet secstack blocklist` 記下來，之後 `nft add element` 補回。**不可加 `flush ruleset`**（會清掉 docker 的 nat/filter）。只想改規則不想清 blocklist 時：用 heredoc 餵 `nft -f -` 單獨重建那一條 chain（PF-107 用的手法），改完再把新版 heredoc 同步進本檔的腳本，否則重開機會退回舊規則 |
| 各服務對 LAN 的暴露面（ports 綁 `0.0.0.0` 還是 `127.0.0.1`） | `.20:~/sec-vm-bootstrap/docker-compose.yml` | `docker compose up -d <service>`（會 recreate 容器；vector 的 file source 有 checkpoint，重建不會漏事件） |
| ClickHouse 保留期與報表維度 | `sec-vm-bootstrap/clickhouse/init.sql` | `docker exec secstack-clickhouse-1 clickhouse-client -d secstack --multiquery --queries-file <檔案>` |
| Grafana datasource／dashboard | `sec-vm-bootstrap/grafana/provisioning/` | `docker compose up -d --force-recreate grafana` |

`.20` 上 `docker-compose.yml`、`vector/`、`suricata/` 是 docker 掛載中的**執行環境**，
不是文件，不可搬走；改完務必驗證生效，再同步回本專案。

## ClickHouse 存取

`.20:~/sec-vm-bootstrap/clickhouse/users.d/zz-network-allowlist.xml` 對 `secstack`
帳號設有網路白名單（PF-104 實查，2026-08-15）：

```xml
<clickhouse><users><secstack><networks replace="replace">
  <ip>127.0.0.1</ip><ip>::1</ip><ip>172.18.0.0/16</ip>
  <ip>192.168.0.100</ip><ip>192.168.0.10</ip><ip>192.168.0.16</ip>
</networks></secstack></users></clickhouse>
```

port 綁在 LAN IP（`docker ps` 顯示 `192.168.0.20:8123->8123/tcp`），但 `secstack`
帳號只接受這六個來源。**`192.168.0.16` 已在白名單內**——平台端要連 ClickHouse
（PF-106）不需要動任何網路設定，只需注意下一條。

**禁止用 URL query 或 `curl -u` 帶密碼查 ClickHouse**：那是明文過 LAN，且會觸發
Suricata `ET INFO Outgoing Basic Auth Base64 HTTP Password detected unencrypted`
（2026-08-15 查證時實際打出十幾筆這種告警）。平台端接 ClickHouse 一律走設定管理，
改用 `X-ClickHouse-User` / `X-ClickHouse-Key` header，禁止硬編碼、禁止 URL query 帶密碼。

## Grafana

Dashboard `secstack-overview`（六個 panel：Events last 1h / High-severity last 1h /
Events by source last 24h / Events per minute by class / Top attacker IPs last 24h /
Top WAF rules last 24h）。

**PF-104 修復的兩個 bug**（2026-08-15，已驗證六個 panel 都有資料，
證據見 `/opt/tmp/verify/20260815-pf104-grafana-fix.log`）：

1. **datasource uid 對不上**：`grafana/provisioning/datasources/clickhouse.yaml`
   原本沒寫 `uid:`，Grafana 自動配了隨機 uid；`dashboards/secstack-overview.json`
   六個 panel 卻寫死引用 `uid: "ClickHouse-secstack"`（那是 datasource 的 *name*
   不是 uid）。修法：datasource yaml 加一行 `uid: ClickHouse-secstack`，
   使其與 dashboard 引用一致。
2. **（原工單未記載，PF-104 執行時新發現）`CLICKHOUSE_PASSWORD` 沒有傳進
   Grafana 容器**：修好第 1 個 bug 後，panel 從「datasource not found」變成
   ClickHouse 回 `code 516 Authentication failed`。根因是
   `docker-compose.yml` 的 `grafana.environment` 只設了 `GF_SECURITY_ADMIN_*`
   等變數，沒有 `CLICKHOUSE_PASSWORD`——datasource yaml 裡的
   `secureJsonData.password: ${CLICKHOUSE_PASSWORD}` 只能取用「Grafana 容器自己
   的環境變數」，不是 host 的 `.env`（docker-compose 的 `${VAR}` 語法只在組譯
   compose 檔時生效，不會自動穿透進容器）。修法：`grafana.environment` 加一行
   `CLICKHOUSE_PASSWORD: ${CLICKHOUSE_PASSWORD}`。
   **這個 bug 在 bug 1 存在時完全不可見**——datasource 都找不到時，
   查詢根本不会走到認證這一步，所以工單原文只記錄了 bug 1。

兩次都用 `docker compose up -d --force-recreate grafana` 生效，皆已在
`.20:~/sec-vm-bootstrap/docker-compose.yml` 與 `grafana/provisioning/datasources/clickhouse.yaml`
同步修改（兩份原檔各自留了 `.bak.<timestamp>` 於 `.20` 本機，未進版控）。

Grafana admin 密碼目前仍是 `.env` 裡的預設值（未輪替）——服務層密碼輪替評估後
判定風險/複雜度不對稱（`GF_SECURITY_ADMIN_PASSWORD` 只在資料庫初始化當下生效，
之後改 `.env` 不會回頭改掉既有 admin 使用者的密碼，需要額外用 `grafana-cli` 或
UI 手動改），PF-104 未執行，留待用戶決定是否列入下一張工單。

## 【強制】禁止偽造驗證結果（但 ssh／高權限操作是許可的）

**被禁止的是「製造出機制沒真的跑過的成功結果」，不是 ssh。**

- 驗收要的是**開發成果的真實結果**，不是設計的結果
- 例：驗證阻擋機制，重點是**機制**而非阻擋。手動去加規則然後宣稱通過＝偽造；
  機制失敗時要**如實回報並修正程式**
- **判準**：用 ssh／手動去**修好機制** → 可以；用 ssh／手動**代替機制產生結果**
  再宣稱驗證通過 → 禁止

**ssh 進 `.20` 做任務所需一律許可**，含改設定、安裝軟體、sudo 高權限操作。
不要把這條誤讀成「不准 ssh」——那會讓 session 不敢做該做的修復，反而有害。

**適用對象**：這條主要用來**提防子 agent、舊版模型與 codex**。
異常時的 session 自己不會自覺，驗收其他 AI 產出時優先查：
它宣稱的成功，是機制跑出來的還是手動補出來的？

## 相關文件

- 平台側 open_defense 模組架構：`dev-notes/OPEN_DEFENSE_ARCHITECTURE.md`
- `.20` 設定檔權威副本：頂層 `sec-vm-bootstrap/`（`README.md` / `docs/` 內有
  安裝、重建、監控、踩坑等九份細節文件）
- PF-105（Suricata xff 設定，同批設定檔內）
- PF-106（平台案件頁串查 ClickHouse，承接「方便看 `.20` 資料的 UI」需求）
- PF-104（本檔的建立工單，BBN atom #5188）

---

## 11. 從 CLAUDE.md 移入：`.20` 存取與風險定調（2026-08-30）

> 原本在 `CLAUDE.md` 的「open_defense 開發備忘」小節（72 行）。
> 平台側架構見 `OPEN_DEFENSE_ARCHITECTURE.md`。

### open_defense 開發備忘

**平台側架構的權威文件是 `dev-notes/OPEN_DEFENSE_ARCHITECTURE.md`（2026-08-10 建立），
動這個模組前整份讀完。** 平台外組件（`.20` 的 Vector / Suricata / CrowdSec /
od-bridge / EDL enforcer / ClickHouse）的權威**已於 2026-08-15（PF-104）收進本 repo**：
架構與運維看 `dev-notes/SEC_STACK_ARCHITECTURE.md`，設定檔副本在 `sec-vm-bootstrap/`
（**已列入 `push_github.sh` 的 `EXCLUDE_DIRS`，不會外流**）。
改 `.20` 的設定時**兩邊都要改**，repo 副本不是快照而是權威副本。
舊路徑 `/opt/Ethan_Lab/ITHome-2026/` **已於 2026-08-15 刪除**
（最終備份 `/opt/tmp/backup/ITHome-2026-final-20260815.tar.gz`），看到一律視為過時。

**`.20` 幾乎每個埠對 LAN 都已收窄（PF-109 收 ingest 面、PF-107 收 SSH 與管理面），
症狀是逾時不是 403**：

| 埠 | 從 `.16` 打得到嗎 |
|---|---|
| `22` sshd | 可以（`.16`/`.10`/`.100` 在 nft 白名單內） |
| `3000` Grafana、`5636` EveBox、`8686` Vector API、`9443` Portainer | 可以（同上三台） |
| `8080` WAF | 可以（同上三台） |
| `8123`/`9000` ClickHouse | 可以（走帳號層網路白名單，不是 nft chain） |
| `8500` od-bridge（stats UI / `/edl`） | 可以（**只有 `.16`**；從 `.10` 的瀏覽器連不到是刻意的） |
| `8688` vector 合成事件注入口 | **不行**，已綁 `127.0.0.1`，要先 ssh 進 `.20` 再打 |

「連線逾時」跟「服務掛了」長得一模一樣，不知道這件事會查錯方向。
要分辨是不是被擋，看 counter 有沒有跳：
`sudo nft list chain inet secstack mgmt_guard_forward | grep counter`。
規則在 `sec-vm-bootstrap/nftables-bootstrap.sh`，完整說明見
`dev-notes/SEC_STACK_ARCHITECTURE.md`。

**`.20` 的 sshd 只收公鑰，密碼認證已停用**（PF-107，2026-08-16）：

`.16` 進 `.20` 一律 `ssh -i ~/.ssh/company-wsl ethan@192.168.0.20`，
**任何形式的密碼登入都不會成功**，不要試、也不要為了「試出密碼」去猜。
舊文件裡的 `P@ssw0rd` 在 2026-05-17 就已失效（用戶自行改過），
現在連密碼這個認證方法本身都不再提供。

排查時先用症狀分辨是哪一層擋的，兩者處理方式完全不同：

| 症狀 | 哪一層 |
|---|---|
| 連線逾時 | nftables（來源不在 `.10`/`.16`/`.100` 白名單） |
| `Permission denied (publickey)` | sshd（沒有可用金鑰） |

**`ethan` 的 OS 密碼刻意不輪替**（Ethan 2026-08-16 定調）：密碼一定會流進
對話記錄與交接文件，交談式 AI 遲早讓它再外洩一次；金鑰不會被寫進文件，
IP 白名單也不會因為誰讀了某份文件而失效。所以那條路走的是「收 IP + 走金鑰」，
而不是「換一個更長的密碼」。**未來 session 不要把「OS 密碼未輪替」重新當成待辦。**

設定片段的權威副本在 `sec-vm-bootstrap/ssh/`（含部署與自動還原手法），
**檔名的 `00-` 前綴是必要的**——`50-cloud-init.conf` 寫死
`PasswordAuthentication yes`，排在它後面的檔案會被靜默蓋過去，`sshd -t` 還是會過。

**「`.16` 內部主機的縱深不足」是已知且已接受的狀態（Ethan 2026-08-16 決定）**：

PF-109 收窄網段、**PF-112（2026-08-16）已補上協定層認證**：`.20:8500` 的
`POST /events` 現在要求 `Authorization: Bearer <BRIDGE_INGEST_TOKEN>`（token 只在
`.20` 的 `.env`，fail-closed，`/health` 免驗），vector 的 `bridge_intake` sink 帶靜態
header。**不是 HMAC**——實測 vector 0.41.1 的 http sink headers 不做模板替換，
且先 batch 再編碼，VRL 算不出最終 body 的簽章。od-bridge 其餘端點
（`/stats`、`/forwards`、`/decisions`、`/edl` 等）**仍無認證，但都是 GET 讀取面**。

風險敘述**到「能在 `.16` 上發封包的人可以拿到 token 後注入事件」為止**，
不要再往上推導。理由是用戶明確定調的：

- **內部主機本來就該有自己的防護**（OS 加固、帳號管理、EDR、網段隔離、備援），
  那是基礎設施的職責，**不能也不該由本專案自行開發來補**
- 本專案的主要目的不是把 `.16` 做成堡壘，這件事**已非主要目的**

**寫給未來 session**：看到「縱深不足」四個字不要自動升級成高風險、不要主動擴大範圍、
不要提議在平台內實作主機加固。要動 PF-112 就照工單做那一件事。
真的發現新的獨立風險，先問用戶，不要自己接著往下修。

---

## 12. 讀者版一鍵安裝 `ITHome2026-WAF/`（2026-09-10 建立，會推上 GitHub；當日先叫 defense-node，Ethan 裁示改名：內容幾乎都是別人的專案，不冠 Beak）

**`sec-vm-bootstrap/` 是 `.20` 這台的部署副本（含內部 IP，不推 GitHub）；
`ITHome2026-WAF/` 是它的參數化產品版（不含任何內部 IP，推 GitHub 給 ITHome 讀者）。**
兩者結構相同、設定檔內容相同，差別只在「值來自 `.env`」與「安裝流程自動化」。
**`.20` 已於 2026-09-10 換裝完成**（Ethan 裁示），`sec-vm-bootstrap/` 同日退役。

| 檔案 | 說明 |
|---|---|
| `ITHome2026-WAF/install.sh` | 一鍵安裝／`--reconfigure`／`--verify`／`--test-event`／`--update`／`--uninstall`。從 GitHub 用 sparse-checkout 只抓 `ITHome2026-WAF/` |
| `ITHome2026-WAF/cf_tunnel.py` | Cloudflare API：建 tunnel、PUT ingress（`hostname → http://waf-nginx:8080`）、CNAME、取 connector token。只需 Zone: Read／DNS: Edit／Tunnel: Edit，account 由 zone 反查（Token 列不出 `/accounts` 也能用） |
| `ITHome2026-WAF/nftables.sh` | 依 `.env` 產生 `/etc/nftables.conf`（allowlist／blocklist／ingest／mgmt／SSH guard），重建前保存 blocklist 元素再補回 |
| `scripts/od_node_pairing.py`（平台端） | 一行建 API Key（od_intake scope）＋ service account，打包成 `ODN1.<base64url json>` 開通字串；`--provision` 時先呼叫 `provision_od_intake_for_org.py` |
| `docs/install/ithome2026_waf.md` | 讀者文件（公開，不含內部 IP） |

**與 `.20` 現況的三個差異（刻意的）**：

1. **cloudflared 是 compose 服務、固定 IP `172.18.0.250`**（`profiles: [tunnel]`），ingress 直接指
   docker 服務名 `waf-nginx:8080`。Vector 的 `trusted_ingress` 因此只信這個 IP
   （`.20` 那份信的是 `192.168.0.16` 與 `172.18.0.1`）。想從管理機帶假 header 測試要在 `.env`
   加 `TRUSTED_INGRESS_EXTRA=172.18.0.1`
2. **ClickHouse 綁 0.0.0.0 不綁本機 IP**，來源限制只靠帳號層白名單——這樣換 IP 不必重建容器
   （驗收流程「`.13` 改成 `.20` 的 IP」只需 `--reconfigure`，實測連 reconfigure 都不必，服務照常）
3. **`CROWDSEC_LAPI_URL=http://127.0.0.1:8081`**。`.20` 的 `.env` 寫 `http://crowdsec:8080`，但 od-bridge
   是 host network，那個名稱解析不到——`.20` 的 CrowdSec enforcer 其實從未成功過（沒有決策帶
   crowdsec EP 時看不出來）。`.20` 要修就改 `.env` 這一行
4. `intake_canary_route` 已拆掉（結構直接 throttle → clean），內網判定改用 `ip_cidr_contains` 精確比對 RFC1918

### Cloudflare 現況（2026-09-10）

| 項目 | 值 |
|---|---|
| tunnel | `dmz-web`（`7431403b-cdac-4b4c-97de-9f77b976168c`，remote-managed，2026-09-08 建） |
| ingress | **只有 `www.beakmask.org` 一個 hostname（Ethan 2026-09-10 定調：`.66` 的對外是 www，`app.beakmask.org` 已移除含 CNAME）**，兩條規則依序比對：`path ^/beakplatform(/\|$)` → `http://waf-nginx:8080`（→ `.66:8000`）；其餘路徑 → `http://waf-welcome:8080`（歡迎頁，內容只有「歡迎到 www.beakmask.org」，獨立 WAF 容器，audit log `audit-welcome.log`，事件 `target.service=waf-welcome`）；其餘 hostname 404。`.env`：`CF_HOSTNAME=WELCOME_HOSTNAME=www.beakmask.org`、`WAF_BACKEND_PATH=/beakplatform` |
| DNS | `www.beakmask.org` CNAME → `<tunnel id>.cfargotunnel.com`（zone `beakmask.org`，proxied）。**`.16` 本機解析 www 只拿到 IPv6、curl 會 000**（`.16` 沒有 IPv6 出口），從 `.16` 測要 `--resolve www.beakmask.org:443:$(dig @1.1.1.1 +short www.beakmask.org \| head -1)` |
| connector | **`.20`** 的 `secstack-cloudflared-1`（換裝後上線，`www.beakmask.org` 對外服務中）；`.13` 那個已 `compose stop`，做頂替驗收時 `--reconfigure` 會帶起來 |
| API Token | 沿用 `/opt/CFTunnel/config-ho-gate.ini` 的 `api_token`（權限夠用，不必另建） |

換 hostname：`python3 ITHome2026-WAF/cf_tunnel.py setup --hostname <新名> --tunnel-name dmz-web`，
舊的 `cf_tunnel.py remove --hostname <舊名>`（連 CNAME 一起刪）。`.66` 的 `system_base_url` 仍是
`http://192.168.0.66:8000`，要讓平台寄出的連結指向對外網址時改成 `https://www.beakmask.org`（未動，Ethan 決定）。

### `.13` 現況與 Ethan 的驗收步驟

`.13`（ubuntu24，`ethan` / `P@ssw0rd`、sudo NOPASSWD，`.16` 的 `~/.ssh/company-wsl.pub` 已放進去）
已用 defense-node 裝好，綁 BELUGA（intake key `ak_824b6daff3b494ff`、SA `sa_defense_node_13_22baa3`，
開通字串在 `/opt/tmp/verify/20260910-defense-node-pairing.log`），backend `http://192.168.0.66:8000`。
安裝目錄 `/opt/ithome2026-waf`，密碼在它的 `.env`。

2026-09-10 已完整預演過一次（憑證 `/opt/tmp/verify/20260910-defense-node-13-install.log`）：
`.20` 關機 → `.13` 改 `192.168.0.20` → Internet 打 `https://app.beakmask.org/beakplatform/` 302 到
`.66` 登入頁、SQLi 探測 403 → `.16` 建案 `OD-20260909-0001`／`0002`（保留，是驗收證據）→
還原（`.13` 回 DHCP、`qm start 110`）。**兩個踩到的**：`.66` 對 `192.168.0.20` 有舊 MAC 的 ARP
快取，IP 剛換過去的前一兩分鐘 WAF → `.66` 會逾時，`sudo ip neigh flush to 192.168.0.20` 即好；
`.13` 的 netplan 是 cloud-init DHCP，換 IP 要整檔改成 static（備份在 `.13:/root/netplan-50-cloud-init.yaml.bak-defense`，
static 版在 `/root/netplan-as-20.yaml`），改完 `systemd-run --on-active=2 netplan apply` 免斷線。

Ethan 自己跑驗收時（每一條都是 2026-09-10 本 session 實跑過的指令，照抄）：

```bash
# 1. 關 .20（真正的防禦節點）
ssh -i ~/.ssh/company-wsl ethan@192.168.0.20 'sudo poweroff'
until ! ping -c1 -W1 192.168.0.20 >/dev/null 2>&1; do sleep 1; done

# 2. .13 換成 192.168.0.20（static 檔早已放在 .13:/root/netplan-as-20.yaml；systemd-run 延遲 2 秒套用，SSH 不會卡死）
ssh -i ~/.ssh/company-wsl ethan@192.168.0.13 \
  'sudo cp /root/netplan-as-20.yaml /etc/netplan/50-cloud-init.yaml && sudo chmod 600 /etc/netplan/50-cloud-init.yaml && sudo systemd-run --on-active=2 --unit=defense-ipswap /usr/sbin/netplan apply'
sleep 12
# 從此以後 .13 要用 192.168.0.20 連，host key 跟真 .20 不同，一律帶這兩個參數
S20="ssh -i $HOME/.ssh/company-wsl -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no ethan@192.168.0.20"
$S20 'hostname'                      # 應印 ubuntu24（不是 sec-vm）

# 3. 把 cloudflared 帶起來、重生防火牆（.13 平常刻意停著 cloudflared）
$S20 'sudo bash /opt/ithome2026-waf/install.sh --reconfigure --yes'
sshpass -p 'P@ssw0rd' ssh ethan@192.168.0.66 'sudo ip neigh flush to 192.168.0.20'   # .66 的 ARP 還記著真 .20 的 MAC，不清會逾時一兩分鐘

# 4. 從 Internet 打（在 .16 上跑就算：出口是家裡的公網 IP，CF-Connecting-IP 會是它）
#    .16 解析 www 只拿到 IPv6、沒有 IPv6 出口，所以 www 那條要 --resolve 指 IPv4
CFIP=$(dig @1.1.1.1 +short www.beakmask.org | grep -E '^[0-9.]+$' | head -1); R="--resolve www.beakmask.org:443:$CFIP"
curl -s $R https://www.beakmask.org/ | grep -o '<h1>[^<]*</h1>'                                  # 期望「歡迎到 www.beakmask.org」
curl -s -o /dev/null -w "%{http_code}\n" $R https://www.beakmask.org/beakplatform/               # 期望 302（到 .66 登入頁）
curl -s -o /dev/null -w "%{http_code}\n" $R "https://www.beakmask.org/?id=1%27%20OR%20%271%27=%271"                     # 期望 403（waf-welcome）
curl -s -o /dev/null -w "%{http_code}\n" $R "https://www.beakmask.org/beakplatform/?q=1%27%20UNION%20SELECT%201,2--"   # 期望 403（waf-nginx）
sleep 15
# 通過標準：下面最新兩筆的 actor 是家裡的公網 IP、host 都是 www、service 分別是 waf-welcome/waf-nginx、rule 942100、execution_code 非空
sudo -n -u postgres psql -d beakplatform_dev -tA -c "SELECT e.id, e.received_at, e.raw_body->'actor'->>'ip', e.raw_body->'finding'->>'rule_id', e.raw_body->'target'->>'host', e.raw_body->'target'->>'service', wi.execution_code FROM od_intake_events e LEFT JOIN fw_workflow_instances wi ON wi.secure_code=e.case_secure_code ORDER BY e.id DESC LIMIT 4;"
# UI 看案件：quick-login 用 ethanyu@beluga.com（user_id FhsmtyPjsnXYotN-iz_Q-X，持 SECURITY_STAFF）
#   → http://192.168.0.16:7000/beakplatform/open-defense/security-cases  （選單「開放防禦 → 資安案件處置中心」）
#   同 actor+rule 60 分鐘內會併進既有案件（例如 OD-20260909-0001），看 od_intake_events 的新列比看案件數可靠
```

還原（順序固定：先停 .13 的 cloudflared，再換回 IP，最後才開真 .20，避免兩台同時搶 tunnel 與 IP）：

```bash
$S20 'cd /opt/ithome2026-waf && sudo docker compose --profile tunnel stop cloudflared'
$S20 'sudo cp /root/netplan-50-cloud-init.yaml.bak-defense /etc/netplan/50-cloud-init.yaml && sudo chmod 600 /etc/netplan/50-cloud-init.yaml && sudo systemd-run --on-active=2 --unit=defense-iprestore /usr/sbin/netplan apply'
sleep 12; ssh -i ~/.ssh/company-wsl ethan@192.168.0.13 'ip -4 -br a show ens18'      # 應回到 192.168.0.13
sshpass -p 'P@ssw0rd' ssh ethan@192.168.0.66 'sudo ip neigh flush to 192.168.0.20'
ssh root@192.168.0.100 'qm start 110'
until ssh -i ~/.ssh/company-wsl -o ConnectTimeout=3 -o BatchMode=yes ethan@192.168.0.20 hostname 2>/dev/null; do sleep 3; done   # 應印 sec-vm
ssh -i ~/.ssh/company-wsl ethan@192.168.0.20 'cd /opt/ithome2026-waf && sudo bash install.sh --verify'
```

探測會讓小企業單人版流程對家裡的公網 IP 下 24h block（只影響直連 .20，LAN 與 tunnel 不受影響）。要提前解封走機制、不要手動 nft：

```bash
sudo -n -u postgres psql -d beakplatform_dev -tA -c "UPDATE od_defense_decisions SET expires_at = (now() at time zone 'utc') - interval '1 minute' WHERE action='block' AND status='applied' AND target_value='123.192.234.208' RETURNING id;"
# 等 1～2 分鐘，cron 的 od_expire_decisions.py 會產 unblock，executor 落地後：
ssh -i ~/.ssh/company-wsl ethan@192.168.0.20 'sudo nft list set inet secstack blocklist'
```

### 封鎖→到期→解封 的完整閉環也順帶驗過（2026-09-10）

小企業單人版流程對案件的 actor 自動下 24h block：`od_defense_decisions` 175／176 → `.20` nft blocklist
出現 `123.192.234.208`（Ethan 家的公網 IP，因為探測都是從 `.16` 出去的）。把兩筆 `expires_at` 改成過去
→ 每分鐘的 `od_expire_decisions.py` 產 unblock 177／178 → executor 落地 → blocklist 清空，全程沒碰 nft。
**測試探測會把自己的公網 IP 封 24h**，只影響直連 `.20` 的路徑（LAN 與 tunnel 都不受影響），
但驗收完記得看一眼 blocklist。

### Ethan 2026-09-10 裁示

- `.20` 換裝 defense-node：**已完成**（本節上方）
- WAF 對 5xx 回應產生的無規則編號事件：**保留不濾**，維運可用性也是 C.I.A. 的一環
- `.66` 的 `system_base_url`：在 `.66` 平台的「主機設定 → 伺服器設定 → 系統對外網址」填 `https://www.beakmask.org`（不含前綴），Ethan 自己決定何時改
- `.20:~/sec-vm-bootstrap_RETIRED_20260910` 已於 2026-09-10 依 Ethan 指示刪除；`~/sec-vm-bootstrap-20260815.tar.gz`（PF-104 時的最終備份，同樣含 CREDENTIALS.md）仍在，另一份在 `.16:/opt/tmp/backup/ITHome-2026-final-20260815.tar.gz`
- bpserv 的 GitHub PAT 已失效（2026-09-10 API 401），Ethan 表示先不動作
- 換裝時順帶產生的案件 `OD-20260909-0004`：Suricata sid 2049202（od-bridge 映像檔 build 時 pip 連 files.pythonhosted.org 的 ET INFO），一次性
- **cloudflared 真正的噪音是 sid 2047122**「ET INFO DNS Query to Cloudflare Tunneling Domain」：本機 cloudflared 每次重連查 `<tunnel id>.argotunnel.com` 就建一張案件（`OD-20260910-0005`，actor 192.168.0.20 → 1.1.1.1）。2026-09-10 加進 `suricata/disable.conf`，`install.sh --update-rules` 重載後不再觸發
