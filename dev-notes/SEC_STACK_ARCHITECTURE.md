# sec-vm（`.20`）架構與運維手冊

**最後更新：2026-08-15（PF-104 建立）**
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
.100 (Proxmox 母機)  **無法用同一把金鑰登入**（2026-08-16 實測 root/ethan 皆
                     Permission denied）。需要「非白名單來源」做驗證時不要指望它，
                     改在 .16 臨時借一個 secondary IP（見 CONFIGURATION.md 的
                     ingest 面來源管制段）
```

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
| `.20:8080` | WAF（反向代理到 `http://192.168.0.16:80`） |
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
- 四條 nft chain 都以 `iifname != "ens18" accept` 開頭，所以 canary（`127.0.0.1:8080`）
  與 vector→`host.docker.internal:8500` 這兩條內部路徑不受影響
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
4. **`203.0.113.1` 是 canary 專用來源 IP**：`host-cron/secstack-canary` 每小時
   自動打一次，有豁免全域 throttle。
   **不要排除它**——2026-08-16 用戶定案「演習視同作戰」，canary 案件照常進處置中心，
   由 SOC L1 簽「資安演練」結案，每天 24 張演習單是刻意的訓練負載。
   本文件原本寫「SOC 看板與報表要排除它」，該指示**已作廢**
   （權威說明在 `/etc/cron.hourly/secstack-canary` 的檔頭註解）。

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

**驗真實路徑最快的一招是手動觸發 canary**（比自製合成事件可靠，
因為它走的就是每小時在跑的那條）：

```bash
ssh -i ~/.ssh/company-wsl ethan@192.168.0.20 'sudo /etc/cron.hourly/secstack-canary'
# 約 20 秒後看 bridge 有沒有把兩條路徑都送上去（期望 status=200）
ssh -i ~/.ssh/company-wsl ethan@192.168.0.20 \
  'docker logs secstack-od-bridge-1 --since 3m 2>&1 | grep -E "forwarded|401"'
```

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
用「事件 correlation_id 反查 case_secure_code 再刪案件」會誤傷——已誤刪過 canary 案件。

## 要改行為時，改哪個檔案

`.20` 上的執行環境全部需 ssh 進去改，**權威副本同步在本專案 `sec-vm-bootstrap/`**
（改完務必用下表方式驗證生效，再同步回本專案；比對用 `diff` 或 md5）：

| 要改的行為 | 檔案 | 改完怎麼生效 |
|---|---|---|
| 事件過濾、throttle（含全域封頂）、canary 豁免、OCSF 映射 | `.20:~/sec-vm-bootstrap/vector/vector.production.yaml`（`vector.yaml` 是它的 symlink） | `docker exec secstack-vector-1 vector validate /etc/vector/vector.yaml` 通過後 `docker kill -s HUP secstack-vector-1`，不必重啟容器 |
| Suricata 規則啟用/停用 | `.20:~/sec-vm-bootstrap/suricata/rules/suricata.rules`（停用是行首加 `# DISABLED <日期> <原因>: `，此檔不進版控） | `docker kill -s USR2 secstack-suricata-1`，用 `docker exec secstack-suricata-1 tail /var/log/suricata/suricata.log` 確認 `rules successfully loaded` 的數字有變 |
| eve.json / modsec log 輪替 | `.20:/etc/cron.hourly/secstack-rotate-logs`（權威副本 `sec-vm-bootstrap/host-cron/`） | 每小時自動跑；手動 `sudo /etc/cron.hourly/secstack-rotate-logs`，看 `/opt/tmp/sec-vm-rotate-logs.log` |
| canary 打什麼 | `.20:/etc/cron.hourly/secstack-canary`（權威副本 `sec-vm-bootstrap/host-cron/`；**`.20` 上沒有 `~/sec-vm-bootstrap/host-cron/` 這個目錄**，同步時只 cp 到 `/etc/cron.hourly/`） | 同上，log 在 `/opt/tmp/sec-vm-canary.log` |
| canary 怎麼檢查、告警 | `.16:/opt/BeakPlatform-dev/scripts/cron/od_canary_check.py` | `/etc/crontab` 每小時；手動加 `--dry-run` 測 |
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
