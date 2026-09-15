# Integrated-WAF：WAF 節點熱備（warm standby）切換

這份文件說明如何把兩台防禦端做成「兩台主機、三個 IP」的熱備架構：兩台各有自己的管理 IP，
另有一個服務 IP 只放在現役節點。被保護網站與管制端防火牆只放行服務 IP，切換時用
`failover.sh` 在管理機上把服務 IP、cloudflared、od-bridge 與本機封鎖狀態搬到另一台。

範例：

| 用途 | 範例 |
|---|---|
| 防禦端 A 管理 IP | `192.168.1.11` |
| 防禦端 B 管理 IP | `192.168.1.12` |
| 服務 IP | `192.168.1.20` |
| 被保護網站 | `http://192.168.1.30:8000` |

---

## 一、為什麼切換點是 cloudflared 不是 IP

Cloudflare Tunnel 的流量不是依照防禦端主機 IP 決定，而是分給所有在線的 cloudflared connector。
如果兩台防禦端同時跑 cloudflared，Cloudflare 會把一部分請求送到沒有服務 IP 的待命節點；
那台節點的 WAF 往後端轉發時，來源不會是服務 IP，被保護網站若只放行服務 IP，就會逾時或被擋。

所以熱備切換要同時搬兩件事：

- **服務 IP**：只有現役節點持有，WAF 轉發與 od-bridge 對外連線的來源都要是它
- **cloudflared**：只有現役節點啟動，避免 Cloudflare 把請求分到待命節點

「來源是服務 IP」在 Linux 上其實是三件事，`standby.sh takeover` 一次做完：

| 誰發出的流量 | 來源 IP 由誰決定 | takeover 做什麼 |
|---|---|---|
| 主機自己（od-bridge 是 host network） | 路由的 `src` | 把子網路由與 default 路由的 `src` 改成服務 IP |
| 容器（WAF、Vector）經 docker MASQUERADE | **網卡的 primary 位址**，不看路由 `src` | 另加一條 SNAT：docker 網段出站一律改寫成服務 IP |
| 鄰居的 ARP 快取 | 誰最後回答 ARP | 開 `arp_notify` 送 gratuitous ARP，**再用 `arping` 以服務 IP 為 sender 對閘道、被保護網站、管制端各發一次 ARP 請求** |

第三列也不能省：不少家用路由器忽略 gratuitous ARP，快取要等 60～90 秒才老化。這段時間 cloudflared
出站解析不到 DNS、Cloudflare 回 530，看起來像 tunnel 壞了，其實只是路由器還把服務 IP 記在舊節點的 MAC 上。
ARP「請求」的 sender 欄位幾乎所有裝置都採信，所以 takeover 主動對會回應我們的鄰居各發一次請求
（`install.sh` 會裝 `iputils-arping`；沒有 arping 時退回「清本機鄰居快取 + 以服務 IP ping 一下」）。

第二列是最容易漏的：服務 IP 是後加上去的 secondary 位址，只改路由 `src` 時主機自己連得到後端、
WAF 容器卻連不到，症狀是「歡迎頁正常、被保護網站的路徑逾時」，而且 WAF log 只看得到 upstream timeout。

兩台防禦端自己的管理 IP 永遠保留，SSH 與維運都走管理 IP。服務 IP 只代表「現在誰在服務流量」。

## 二、熱備的定義與邊界

這套做法是 warm standby，不是雙活。

兩台都常駐的服務：

- WAF / welcome WAF
- Suricata
- Vector
- ClickHouse
- Grafana / EveBox / Portainer（若有啟用）
- CrowdSec LAPI

只能一台跑的服務：

- `cloudflared`：避免 Cloudflare Tunnel 把流量分到兩台
- `od-bridge`：管制端的封鎖決策用樂觀鎖先搶先贏，兩台同時輪詢會各自拿到不同一半決策

切換時 `failover.sh` 會先從舊節點匯出 nftables `blocklist` / `blocklist6` 與 EDL 狀態，
再匯入新節點，讓新節點接手時保留目前仍有效的封鎖清單。這個複製只在切換當下發生；
平時待命節點不會同步封鎖狀態。

不複製的資料：

- ClickHouse / Grafana 歷史資料：各台保留自己的本機紀錄
- CrowdSec 決策資料：由各台自己的 CrowdSec 維護
- CrowdSec machine 憑證：每台自己的 `od-bridge/state/crowdsec_machine.json`，不可互相覆蓋

## 三、準備第二台

第二台防禦端用和第一台相同的安裝方式。開通字串可以重用同一份，也可以在管制端另發一份。

重要的是下列參數必須和第一台一致：

- `--backend`
- `--cf-api-token` / `--cf-hostname`，或手動 tunnel 設定對應的 hostname
- `--welcome-hostname`
- `--backend-path`

範例：

```bash
sudo bash install.sh \
    --pair 'ODN1....' \
    --backend http://192.168.1.30:8000 \
    --cf-api-token <Cloudflare API Token> --cf-hostname app.example.com \
    --welcome-hostname app.example.com --backend-path /app \
    --admin-ips <管理機IP>
```

安裝完成後，立刻讓第二台進入待命：

```bash
sudo bash /opt/ithome2026-waf/standby.sh release --service-ip 192.168.1.20
```

被保護網站與管制端防火牆只需要放行服務 IP。兩台管理 IP 只要管理機能 SSH 進去即可
（SSH 帳號要能 `sudo -n`）。**兩台的管理 IP 都用固定 IP**，理由見第六節。

### 管理機的組態檔

`failover.sh` 的參數全部放組態檔，命令列只說「做什麼」。把 `failover.conf.example` 複製成
`failover.conf` 放在 `failover.sh` 旁邊（或 `/etc/ithome2026-waf/failover.conf`）：

```bash
SERVICE_IP="192.168.1.20"          # 服務 IP
NODE_A="192.168.1.11"; NODE_A_NAME="primary"    # 節點 A 的管理 IP 與你要叫它的名字
NODE_B="192.168.1.12"; NODE_B_NAME="standby"
SSH_USER="ubuntu"                  # 兩台防禦端的 SSH 帳號
SSH_OPTS_STR="-i ~/.ssh/waf-node"  # 額外 ssh 參數
INSTALL_DIR="/opt/ithome2026-waf"
LOG_DIR="/var/log/ithome2026-waf"  # 每次切換的完整輸出落地在這裡（failover-<日期>.log）
```

`failover.conf` 含內網 IP，不要進版控（repo 的 `.gitignore` 已排除）。

## 四、切換與切回

在管理機執行（組態檔放好之後，四個動作就是全部）：

```bash
bash /opt/ithome2026-waf/failover.sh status          # 兩台誰持有服務 IP、cloudflared / od-bridge / blocklist
bash /opt/ithome2026-waf/failover.sh dry-run         # 只做前置檢查，不切換
bash /opt/ithome2026-waf/failover.sh switch          # 切到「現在沒持有服務 IP」的那台
bash /opt/ithome2026-waf/failover.sh to standby      # 切到指定節點（組態檔的名字、A/B、或 IP）
```

確認計畫後輸入 `yes`（排程或流程節點用 `--yes` 跳過詢問），工具會：

1. 取得兩台狀態，只允許一台持有服務 IP；目標的 cloudflared 必須是停的
2. 比對兩台 `.env` 的公開服務設定（`--force` 可跳過）
3. 從舊節點匯出 blocklist（含剩餘 timeout）與 EDL 狀態
4. 停舊節點 cloudflared / od-bridge，釋放服務 IP、刪 SNAT、路由 src 改回管理 IP
5. 新節點做 ARP 重複位址偵測、綁服務 IP、改路由 src、加 SNAT、對鄰居宣告 MAC、匯入狀態、
   啟動 od-bridge / cloudflared
6. 在管理機用 curl 驗證 WAF 與 SQLi 403

輸出最後會印出「服務中斷約 N 秒」，量的是「舊節點開始釋放」到「新節點 cloudflared 向 Cloudflare
註冊完成」。實測一次來回約 15～20 秒：cloudflared 註冊本身只要 2～4 秒，其餘是停容器、SSH 往返與 ARP 宣告。
切回只要把 `to` 換成另一台，或再跑一次 `switch`。

### 現役節點整台失聯時

這才是熱備真正要處理的情境。`failover.sh` 對連不上的節點不會中止，會標成「失聯」並視為沒人持有
服務 IP，然後把活著的那台當目標：

```bash
bash /opt/ithome2026-waf/failover.sh switch --yes
```

失聯節點上的封鎖清單複製不到，新節點從空清單開始（24 小時封鎖本來就會到期，平台的決策紀錄仍在）。
實測從下指令到 cloudflared 註冊完成約 10～15 秒。

### 腦裂防護：掛掉的舊現役修好重開之後

舊現役重開機時，它的開機 unit 會先做 ARP 重複位址偵測：服務 IP 已經有別台在回應，就**不接手**、
標記 fence，等 docker 起來後把自己的 cloudflared / od-bridge 停掉，乖乖當待命（`status` 會顯示
`fenced`）。要讓它回到現役，照常 `failover.sh to <它>` 即可。同樣的偵測也在手動 `standby.sh takeover`
時生效，確定對方真的死了才用 `--force` 硬接。

## 五、驗證

看兩台目前誰是現役：

```bash
bash /opt/ithome2026-waf/failover.sh status
```

從管理機打服務 IP（管理機要在防禦端的 `--admin-ips` 內，否則 8080 會被來源管制擋下而逾時）：

```bash
curl -i http://192.168.1.20:8080/
curl -i "http://192.168.1.20:8080/?id=1%27%20OR%201=1--"
```

第二個請求應該回 403。

在現役防禦端看封鎖清單：

```bash
sudo nft list set inet secstack blocklist
sudo nft list set inet secstack blocklist6
```

## 六、開機與 netplan apply 注意事項

服務 IP 不寫進 netplan，避免和 cloud-init 或使用者自己的 netplan 設定互相覆蓋。
`standby.sh takeover` 會寫入 systemd oneshot unit：

```text
waf-service-ip.service
```

它會在 `network-online.target` 與 `nftables.service` 之後、`docker.service` 之前重做 takeover 的
網路部分（服務 IP、路由 `src`、容器出站 SNAT），讓現役節點重開機後自動回到現役狀態。
這個 unit 裡**不能碰 docker CLI**：docker 用 socket activation，unit 裡呼叫 `docker compose` 會去等
`docker.service`，而 `docker.service` 又排在本 unit 之後，開機就卡死（`TimeoutStartSec=90` 是最後保險）。
`standby.sh` 在 docker 沒啟動時一律回報容器 `stopped`，不去問 docker。
SNAT 規則放在獨立的 `ip wafsvc` 表，`install.sh --reconfigure` 重建主機防火牆時不會動到它。

兩台的**管理 IP 一律用固定 IP**。管理 IP 走 DHCP 時，續租會讓 networkd 重建路由，
`src` 靜默退回管理 IP，現役節點會在不知不覺中失去後端連線。

**改了 `.env` 要兩台都跑 `install.sh --reconfigure`。** `failover.sh` 只比對 `.env` 的五個公開服務鍵，
不比對已經產生的 nginx 設定；`.env` 改了卻沒 reconfigure 的那台，切過去會用舊設定服務
（實測：歡迎頁與路徑分流沒生效，只有後端那條路徑正常）。而且**在待命節點跑 `--reconfigure` 會把
cloudflared 也帶起來**（`.env` 的 `COMPOSE_PROFILES` 含 `tunnel`），跑完立刻 `standby.sh release` 讓它回到待命。

任何 `netplan apply` 之後，服務 IP 可能被拿掉。這不是永久故障，重跑 takeover 即可：

```bash
sudo bash /opt/ithome2026-waf/standby.sh takeover --service-ip 192.168.1.20
```

takeover 是冪等的；服務 IP 已存在時會顯示已綁定並繼續確認路由與服務狀態。

## 七、常見問題

| 症狀 | 原因與處理 |
|---|---|
| 兩台都持有服務 IP | 這是雙現役，`failover.sh` 會中止。先到不該現役的那台執行 `standby.sh release --service-ip 192.168.1.20` |
| 目標 cloudflared 沒停 | 代表目標不是乾淨待命，可能已經有 connector 在線。先在目標執行 `standby.sh release`，確認 `--status` 顯示 stopped |
| `.env` 不一致 | `CF_HOSTNAME`、`WELCOME_HOSTNAME`、`WAF_BACKEND_PATH`、`WAF_BACKEND_URL`、`BEAK_BASE_URL` 必須一致。修正後再切換；確定要略過可加 `--force` |
| ARP 沒更新 | takeover 會先開 `arp_notify`，加服務 IP 時 kernel 會送 gratuitous ARP；若有 `arping` 會再補送。管理機可用 `ip neigh show 192.168.1.20` 看 MAC 是否改到新節點 |
| 切換後 Cloudflare 回 530、cloudflared log 出現 DNS `server misbehaving` | 新節點出站被路由器的舊 ARP 快取吃掉，等它老化（約 60～90 秒）就會自己好。新版 takeover 會用 arping 主動宣告，若仍發生，到新節點 `sudo arping -c 2 -I <網卡> -s <服務 IP> <閘道>` |
| 冷啟動沒人持有服務 IP | 用 `switch --yes`（一台失聯時自動選活著的那台）或 `to <節點> --yes` |
| 一台 `status` 顯示 `fenced` | 它開機時發現服務 IP 已被別台持有，已自動退為待命。這是腦裂防護正常運作，不是故障 |
| 切換工具回報失敗，但對外服務其實正常 | 多半是「新節點 cloudflared 120 秒內沒看到註冊訊息」——先跑 `status` 與 curl 確認實況再決定要不要回退，不要照著回退指令反射動作 |
| 歡迎頁正常、被保護網站的路徑逾時 | 容器出站來源不是服務 IP。到現役節點看 `sudo nft list table ip wafsvc` 是否有 `snat to <服務 IP>`；沒有就重跑 `standby.sh takeover` |
| SQLi 驗證不是 403 | 先確認打的是服務 IP 的 `8080`，再看現役節點 `docker compose logs waf-nginx` 與 `WAF_RULE_ENGINE` 是否為 `On` |
