# Changelog

本檔記錄 secstack 整體部署變更,涵蓋 sec-vm(192.168.0.20)及其相依的 Proxmox host(192.168.0.100)上跟 stack 運維有關的設定。
格式參考 [Keep a Changelog](https://keepachangelog.com/),日期 ISO 8601。

## [2026-09-07]

### Removed
- **合成演習(canary)整套廢除** — Ethan 決定廢除,兩端的排程、腳本、heartbeat 全部移除:

  | 位置 | 移除項目 |
  |---|---|
  | `.20` | `/etc/cron.hourly/secstack-canary`、`/opt/tmp/sec-vm-canary.log`、`/opt/tmp/heartbeat/secstack-canary` |
  | `.16` | `/etc/crontab` 的每小時檢查排程、`scripts/cron/od_canary_check.py`、log 與 state 檔 |
  | repo | `sec-vm-bootstrap/host-cron/secstack-canary` |

  備份在兩台的 `/opt/tmp/backup/od-canary-retire-20260907/`。
  DB 內既有 183 張演習案件刻意保留不清。

  **廢除理由**:路徑 A 從 `.20` 本機打 `127.0.0.1:8080` 走 lo,而四條 nft chain
  都以 `iifname != "ens18" accept` 開頭——防火牆判定與真實入口鏈
  (CF edge → cloudflared `.16` → nginx `.20:8080`)完全沒被覆蓋,
  只驗得到「WAF 容器還活著」。**正確的演習應該從 internet 發動掃描。**
  另外每小時的頻率換不到偵測能力(靜默斷流以天為單位),只換來每天 24 張
  無人消費的演習單與告警疲勞。

  **vector 的 `intake_canary_route` 結構刻意保留**(條件寫死 TEST-NET-3 的
  `203.0.113.1`,不會命中真實流量;拆掉要改三處 input 連接,改錯即斷流)。
  未來新演習只需換 route 條件。

### Fixed (documentation)
- `host-cron/README.md` 原稱 copy + truncate「沒有重新發現新檔的空窗」——
  **實測不符**。Vector 每小時 :17 固定出現 `Stopped watching file` →
  3~4 秒後 `Found new file to watch`,truncate 當下未讀走的行永久遺失。
  這正是 canary 通過率只有 13%(近 7 天 336 次僅 43 次到 ClickHouse)的根因:
  run-parts 按字母序先跑 `secstack-canary`、不到一秒後跑 `secstack-rotate-logs`。
  **競態本身未修**(canary 已廢除,Ethan 決定不修);
  日後若仍在 `.20` 上發動演習,要把發動時間與輪替錯開。

## [2026-08-16]

### Security
- **PF-112:od-bridge `/events` 協定層認證** — `/events` 現在要求
  `Authorization: Bearer ${BRIDGE_INGEST_TOKEN}`,token 只放在 `.20` 的 `.env`。
  `BRIDGE_INGEST_TOKEN` 未設定時 fail-closed 並回 401;`/health` 維持免驗。
  vector 三份設定的 `bridge_intake` sink 已補上靜態 bearer header。

- **PF-107:樣板密碼收斂 + SSH／管理面來源管制** — 清冊裡標著「生產環境請換」的
  兩筆樣板密碼逐一實測後處理,並依用戶決策把 SSH 與管理面一併收進 nftables。

  | 項目 | 工單前提 | 實測 | 處置 |
  |---|---|---|---|
  | `.20` `ethan` OS 密碼 | 仍是 `P@ssw0rd` | **不是**(`sshpass` 密碼登入被拒;`passwd -S` 顯示 2026-05-17 由用戶自行改過) | **刻意不輪替**,改走收 IP + 金鑰 |
  | Grafana admin | 仍是樣板值 | 屬實(HTTP 200,`isGrafanaAdmin:true`) | 已輪替為 24 字元隨機值 |
  | Portainer admin | 未定 | 已初始化,非常見樣板值 | 不動,只收來源 |
  | CrowdSec LAPI machine | 未定 | `openssl rand -hex 24` 生成,非樣板 | 不動 |
  | `.20` `claude` OS 帳號 | 工單未提 | 存在,`NOPASSWD:ALL`、無 SSH key、密碼非 `P@ssw0rd` | 用戶決定不動;停用密碼認證後它會自動失去遠端入口 |

  - **不輪替 OS 密碼是用戶 2026-08-16 的決定**:密碼一定會流進對話記錄與交接文件,
    交談式 AI 遲早讓它再外洩一次;金鑰不會被寫進文件,IP 白名單也不會因為
    誰讀了某份文件而失效。所以那條路走的是「收 IP + 走金鑰」
  - **nftables 新增兩條 chain**(`nftables-bootstrap.sh`,已寫入 `/etc/nftables.conf`):

    | chain | hook | 管什麼 | 允許來源 |
    |---|---|---|---|
    | `ssh_guard_input` | input | 22 | `.10`/`.16`/`.100` |
    | `mgmt_guard_forward` | forward | 3000 / 5636 / 8686 / 9443 | `.10`/`.16`/`.100` |

    hook 不同不是筆誤:docker 發布的埠走 DNAT 後進 forward,host network 的
    sshd 進 input。**掛錯 hook 的症狀是 counter 恆為 0,不會報錯**
  - 管理面四個之中 **EveBox 與 Vector API 完全無認證**(EveBox 的 compose 明寫
    `--no-auth`),Portainer 掛著 `/var/run/docker.sock` 拿下即等同 root。
    換密碼堵不住這些,兩件事不互斥——這同時把 PF-113 一起做掉了
  - 新增第三把 SSH 金鑰 `ethan-win10->sec-vm-20260816-pf107` 給 `.10` 工作站,
    用戶當場在 Windows 測通(`ssh sec-vm`)後,**sshd 已停用密碼認證**
    (`ssh/00-pf107-hardening.conf`,`PasswordAuthentication no` +
    `KbdInteractiveAuthentication no` + `PermitEmptyPasswords no`)。
    驗證:兩把金鑰皆 OK;`ethan` 與 `claude` 的密碼登入都回
    `Permission denied (publickey).`(在此之前是 `(publickey,password)`)
  - **檔名的 `00-` 前綴是必要的**:`sshd_config` 是 first obtained value wins,
    `.20` 的 `50-cloud-init.conf` 寫死 `PasswordAuthentication yes`,
    排在它後面的檔案會被靜默蓋過去,而且 `sshd -t` 仍會通過、不會有警告
  - 改 sshd 前先掛了 `systemd-run --on-active=120` 的自動還原
    (設定寫錯到 sshd 起不來時金鑰也進不去,那時只剩 PVE console),
    驗證通過後才 `systemctl stop` 撤銷
  - 副作用(預期,非待修):`claude` 那個 OS 帳號沒有 `~/.ssh/authorized_keys`,
    自此完全失去遠端入口,只剩主控台

### Added
- **`ssh_guard_input` 的 drop 加了 log**(rate limit 20/分鐘,prefix `SSHGUARD_DROP`)。
  起因是規則上線半小時內 drop counter 就跳到 5(一次 TCP SYN 重傳序列的量),
  **counter 只給數字、給不出來源**,當下查不到是誰。查法:
  `sudo journalctl -k --since '-1 day' | grep SSHGUARD_DROP`。
  已用 `.16` 上臨時 alias IP `192.168.0.199` 驗過 log 會完整記下
  來源 IP／MAC／來源埠。管理面那條沒加(drop 恆為 0),要加照這個樣子寫
  - `CREDENTIALS.md` 從 `_OBSOLETE_DOCS_權威版在.16/` 移回
    `~/sec-vm-bootstrap/CREDENTIALS.md`(舊檔頭指向的 `.16` 路徑已於 2026-08-15 刪除,
    而現在的 repo 會推 GitHub,所以本檔刻意不跟過去)。改採「值只放 `.env`,
    清冊記在哪/怎麼輪替/誰依賴」,避免兩處明文不同步
  - `.16` 的 `scripts/push_github.sh` 掃描清單改為**從 gitignore 的檔案自動抽取**
    (`.env` + `scripts/.secrets-scan-extra`)。原設計要求「輪替後把新密碼加進清單」,
    照做等於把現行密碼 commit 進 repo 歷史——那正是該函式要防的事
  - 驗證(`/opt/tmp/verify/20260816-pf107-rotate.log`):Grafana 舊值 401 / 新值 200、
    ClickHouse datasource health OK;兩條 nft chain 各做一次 mutation
    (暫時把 `.16` 移出白名單,systemd-run 定時自動還原)——SSH 與四個管理埠
    在 mutation 期間全部連線逾時,還原後全部恢復;`/etc/nftables.conf` 實際
    `nft -f` 套用過(不只 `-c` 語法檢查),確認重開機後行為一致

- **PF-109:ingest 面的來源歸因偽造收斂** — 在此之前,任何能連到 `.20` 的主機都能
  讓 CrowdSec 封鎖任意第三方 IP(實測讓真實 AWS 位址 `3.3.3.3` 被 ban)。
  這是可被利用的 DoS 面:偽造成 DNS / 更新來源 / 上游 API 就能讓自家系統斷線,
  `allowlist` 自鎖保險只擋得住「封掉自己」,擋不住「封掉外部關鍵服務」。
  - 三個入口的偽造能力不同,盤點後一併處理:

    | 埠 | 偽造方式 | 處置 |
    |---|---|---|
    | 8080 waf-nginx | 偽造 `Cf-Connecting-Ip` → Suricata `src_ip` 被 overwrite + Coraza `actor_ip` | nftables `ingest_guard_forward`,只放行 `.16`/`.10`/`.100` |
    | 8688 vector | `http_test` source 直接 POST 任意 OCSF 事件(`actor_ip`/`source_system` 全自填,連 CRS 規則都不用觸發) | docker ports 從 `0.0.0.0` 收回 `127.0.0.1` |
    | 8500 od-bridge | `/events` **完全無認證**,且它持有平台 API key 會自動 HMAC 簽名轉送,繞過 vector 全部 filter 與 throttle | nftables `ingest_guard_input`,只放行 `.16` |

  - **vector 側補上信任代理比對**(`ocsf_from_modsec` 的 `trusted_ingress`):
    只有 `192.168.0.16`(cloudflared)與 `172.18.0.1`(docker bridge gateway,
    `.20` 本機經 docker-proxy)送來的 `Cf-Connecting-Ip` / `X-Forwarded-For`
    才採信,其餘以 TCP source 當 actor。`Cf-Ipcountry` 同源同理。
    這是 BeakPlatform `NET-01`(`client_ip.py` 比對 `TRUSTED_PROXY_IPS`)的同一個原則
  - **Suricata 線只能靠網段管制**:`src_ip` 在 Suricata 內部就被 xff 模組
    overwrite,eve.json 不留原始 TCP source;改 `mode: extra-data` 會讓 CrowdSec
    改封 cloudflared@`.16` 自己,等於用「不能封任何真實攻擊者」換「不能被偽造」
  - 兩條 nft chain 都以 `iifname != "ens18" accept` 開頭,hourly canary
    (`127.0.0.1:8080`)與 vector→`host.docker.internal:8500` 不受影響
  - 已知代價:od-bridge stats UI 從 `.10` 的瀏覽器連不到(要 SSH 進 `.20`)
  - 驗證(`/opt/tmp/verify/20260815-pf109-ingress-hardening.log`):
    修復前後同一條不可信路徑的 `actor_ip` 從偽造值 `198.51.100.88` 變成真實
    `172.18.0.5`;`nc -s 192.168.0.199` 從非白名單來源測得 22/8123 OPEN、
    8080/8500/8688 BLOCKED;canary `actor_ip` 仍為 `203.0.113.1`

### Known issues
- 已解決(PF-112):od-bridge `/events` 已加共享 bearer token 驗證;網段管制仍保留為外層防線。

## [2026-08-09]

### Fixed
- **nftables 落地層自 2026-07-15 起全數失效(靜默三週)** — `od_defense_decisions`
  id 19~23 全部 `status=failed`,錯誤都是
  `nft: Error: No such file or directory ... add element inet secstack blocklist`
  - 根因:`nftables-bootstrap.sh` 只在**執行時**於記憶體建表,
    而 `nftables.service` 為 disabled、`/etc/nftables.conf` 不存在 → **開機不還原**。
    .20 於 2026-07-15 02:30 重開機清空 ruleset,21:51 起每筆封鎖都失敗
  - 修法:`nftables-bootstrap.sh` 改為寫入 `/etc/nftables.conf` 並
    `systemctl enable --now nftables`
  - **刻意不使用 `flush ruleset`**:.20 的 `ip nat` / `ip filter` 由 docker(iptables-nft)
    管理,flush 會打斷所有 port forwarding。改用 `table` / `delete table` / `table`
    的慣用法只重建 `inet secstack` 一張表
  - 驗證:決策 → 12 秒內 `applied`,IP 真的進 kernel set 並倒數 TTL;
    到期後 kernel 自動剔除、BP 排程產生 unblock、executor 撤除,閉環完整

### Added
- `inet secstack` 新增 **`allowlist` set**(自鎖保險):`192.168.0.16` / `.10` / `.100`
  在 drop 規則之前 accept,避免一筆錯誤的封鎖決策把管線接收端或管理者 SSH 鎖死。
  這是保險,**不是**白名單機制(那是 PF-68 工單)
- **EDL enforcer**(`od-bridge/od_bridge/enforcers/edl.py`)— 把決策物化成 PAN-OS
  可抓取的 External Dynamic List
  - `GET /edl`(action=block)與 `GET /edl/allow`(action=allow),`text/plain`
  - reconciler 設計:狀態存 `state/edl/state.json`,每筆帶 `expires_at`,
    每次落地與每 60 秒 prune 重繪整份檔案 → 累加與時效同時成立
  - `unblock` 從兩份清單移除,冪等(不存在時回 `already_absent`)
  - 空清單回傳空內容而非 404(404 會讓 PAN-OS 沿用舊清單)
  - **輸出預設為純 IP、零註解**(`EDL_HEADER=0`):Palo Alto 文件定義的語法是
    `[位址][空格][註解]`,註解必須與位址同一行,整行 `#` 註解不在格式內。
    初版誤加了六行 `#` 表頭,已改為可選(`EDL_HEADER=1` 才輸出,僅供人工檢視)
  - `.env` 新增 `EDL_DIR` / `EDL_PRUNE_INTERVAL`,`MY_ENFORCEMENT_POINTS` 加上 `edl`
  - BP 端 service account `sa_executor_secvm_01_<redacted>` 的
    `allowed_enforcement_points` 補上 `edl`(否則決策不會被派送過來)

## [2026-05-10]

### Added
- `clickhouse/users.d/zz-network-allowlist.xml` — 限制 `secstack` user 來源 IP
  - 白名單:`127.0.0.1`, `::1`, `172.18.0.0/16`(docker bridge),`192.168.0.10`(NB),`192.168.0.16`(SOC),`192.168.0.100`(Proxmox host)
  - 用 `<networks replace="replace">` 屬性覆蓋(不是 append)image 預設的 `::/0`
  - 檔名用 `zz-` 前綴,確保在 image entrypoint 動態產生的 `default-user.xml` **之後**載入(ClickHouse alphabetically merge,後勝出)
- `docker-compose.yml` clickhouse 多掛 volume:
  ```yaml
  - ./clickhouse/users.d/zz-network-allowlist.xml:/etc/clickhouse-server/users.d/zz-network-allowlist.xml:ro
  ```

### Changed
- ClickHouse port binding(`docker-compose.yml`):
  - `127.0.0.1:8123:8123` → `192.168.0.20:8123:8123`
  - `127.0.0.1:9000:9000` → `192.168.0.20:9000:9000`
  - 綁 ens18 的 IP(不綁 docker0 等其他介面),配合 user-level 白名單做雙保險
- `.env` `CLICKHOUSE_PASSWORD` 從 `changeme_clickhouse` 換成 32 字元隨機(已交付給 user)
  - dependents(vector / grafana / od-bridge)讀 `${CLICKHOUSE_PASSWORD}` 環境變數,`docker compose up -d` 自動 recreate 套用

### Fixed
- **EveBox restart loop (exit 127)** — 純 .20 本機 yaml bug,**與其他主機(.10 / .16 / .100)無任何關聯,也不是 ClickHouse 改動造成**

  **因果鏈(避免誤讀)**:
  1. .20 上 `docker-compose.yml` 的 evebox block **某時間點之前** 就已被改壞 — `entrypoint` 不見了、`command:` 用 `>` folded scalar 變成單一字串。但因為當時 evebox 容器還在跑(用更早的好版本 yaml 啟動的),沒人發現
  2. 今天為了 ClickHouse 改 port + env,跑 `docker compose up -d`,docker 偵測到 compose 內容變動 → **整個 stack 全部 recreate** → evebox 被重建 → 套到壞掉的 yaml → exit 127
  3. 所以「ClickHouse 動作觸發」**≠**「ClickHouse 造成」。EveBox 跟 ClickHouse 沒任何資料 / 網路依賴(它自己 sqlite 存 suricata alerts),也不關 .10 / .16 / .100 任何設定的事
  4. 修法只動 .20 自己的 `docker-compose.yml`,沒動其他主機,沒改 ClickHouse 任何東西

  **yaml 改動**:
  - 加回 `entrypoint: ["/usr/bin/evebox"]`(原本沒有 → image 內建 `/docker-entrypoint.sh` 是 `exec "$@"`,找不到 `server` 指令)
  - `command:` 從 `>` folded scalar 改成 list 形式(原本折成單一字串塞給 docker,argv 變成 1 個元素)
  - 修後:
    ```yaml
    entrypoint: ["/usr/bin/evebox"]
    command: ["server", "--no-auth", "--datastore=sqlite",
              "--data-directory=/data", "--input=/var/log/suricata/eve.json",
              "--host=0.0.0.0", "--port=5636"]
    ```

  **教訓**:壞掉的 compose 檔在 stack 不重啟的情況下不會被偵測到;將來改 yaml 後可以先 `docker compose config` 預覽,或用 `docker compose up -d <service>` 只套用單一服務,降低「一次全爆」風險

### Operational
- **Portainer** — 重啟 `secstack-portainer-1` 重置 5 分鐘 setup window,在 `https://192.168.0.20:9443` 建立 admin 帳號(原 timeout 是首次部署 5 分鐘逾時鎖,非 bug)

### Backups(同目錄)
- `.env.bak.20260510-185412`
- `docker-compose.yml.bak.20260510-185412`

### Verification
- ClickHouse:.10 / .16 / .100 連線 OK,其他 IP 收到 `Authentication failed` 偽裝錯誤
- vector 持續寫入 `secstack.events`(從 372 → 377 筆短時間內驗證成長)
- EveBox `https://192.168.0.20:5636` 起服,從 EVE bookmark 150145 繼續處理

---

### Host setup — 192.168.0.100 (Proxmox)

跟 secstack 本身無關,但跟 daily ops 有關 — 把 Claude Code 在 .100 跑時的 OS 身分從 root 切換到 non-root 帳號(Claude CLI 拒絕以 root 啟動,每次要 enter 太煩)。

#### Added
- 新增 OS user `proxmox-ethan`(UID 1000,在 `root` group)
  - `useradd -m -s /bin/bash -G root proxmox-ethan`
  - **預設臨時密碼**已交付給 user(已知為 weak temp value,user 將自行 `passwd` 換掉)
- `/etc/sudoers.d/proxmox-ethan` — `proxmox-ethan ALL=(ALL) NOPASSWD:ALL`(visudo 驗證通過)
- 安裝 `sudo` 套件(`apt-get install -y sudo`,Proxmox minimal 預設沒裝,沒裝 sudoers 也沒用)

#### Migrated
- `/root/.claude/` → `/home/proxmox-ethan/.claude/`(9.9 MB,完整複製含 `.credentials.json` / `projects/-opt/` sessions / `projects/-opt/memory/` / plans / settings)
  - `chown -R proxmox-ethan:proxmox-ethan`
  - 目的:proxmox-ethan 啟動 Claude 時可直接接續對話 + memory,不用重登 Anthropic
  - **注意**:`/opt/.claude/settings.local.json` 是 project-level 設定(跟著 cwd,不跟 user),沒動
- `/root/.ssh/{id_rsa, id_rsa.pub, known_hosts}` → `/home/proxmox-ethan/.ssh/`(權限 700/600/644)
  - 同一把 RSA 4096 (`root@pve`) 共用;.20 上 ethan 的 `authorized_keys` 已含此 pubkey,不用再推

#### Memory sync
- `~/.claude/projects/-opt/memory/` 中的 `host_topology.md`、`ssh_sec_vm.md`、`MEMORY.md` 從 root 同步到 proxmox-ethan,反映新 OS user 設定
- 之後若仍以 root 跑 Claude 修改 memory,需手動同步到 proxmox-ethan(否則切換時 memory 漂移)

#### Verification
- `sudo -u proxmox-ethan ssh -o BatchMode=yes ethan@192.168.0.20 'whoami'` → `ethan`(SSH key 接續可用)
- `sudo -u proxmox-ethan sudo -n whoami` → `root`(NOPASSWD 工作)
- `id proxmox-ethan` → `uid=1000 ... groups=1000(proxmox-ethan),0(root)`

#### TODO(交還給 user)
- `passwd proxmox-ethan` 換掉預設臨時密碼
- (可選)考慮把 `proxmox-ethan` 也加到 PVE realm(`pveum user add proxmox-ethan@pam`),目前只是 OS-level user,不能登 Proxmox GUI
