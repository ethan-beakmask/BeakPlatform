# Changelog

本檔記錄 secstack 整體部署變更,涵蓋 sec-vm(192.168.0.20)及其相依的 Proxmox host(192.168.0.100)上跟 stack 運維有關的設定。
格式參考 [Keep a Changelog](https://keepachangelog.com/),日期 ISO 8601。

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
