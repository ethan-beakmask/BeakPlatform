# ITHome2026-WAF：防禦節點一鍵安裝

**這是選用元件。** 要讓 BeakPlatform 自動收到網站與網路層的攻擊事件、建立資安案件、
再把核可的封鎖決策落地到防火牆，需要第二台主機當「防禦端」。本頁說明如何用一支
腳本把它裝起來，並和平台（管制端）串接。

這份文件寫給**安裝與維運人員**，不需要平台在執行中就能閱讀。

---

## 一、兩台主機各做什麼

| 主機 | 角色 | 裝什麼 |
|---|---|---|
| 管制端 | 已安裝 BeakPlatform 的主機 | 平台本體（見 `install.sh`）。收事件、跑案件流程、寫決策 |
| 防禦端 | 另一台 Ubuntu 22.04 / 24.04（2 vCPU、4 GB 以上，建議 6 GB） | WAF（nginx + ModSecurity + OWASP CRS）、Suricata、CrowdSec、Vector、ClickHouse、od-bridge、cloudflared，選用 Grafana / EveBox / Portainer |

```
Internet ─► Cloudflare ─► cloudflared ─► WAF(8080) ─► 被保護的網站（內網 IP:埠）
                                          │ 告警
   Suricata（監聽網卡） ────────────────► Vector ─► od-bridge ──事件──► 管制端 /api/open_defense/intake
                                          │                    ▲
                                          ▼                    │ 每 5 秒拉取封鎖決策
                                      ClickHouse    nftables / CrowdSec / EDL ◄──┘
```

被保護的網站可以是 BeakPlatform 自己，也可以是任何內網網站。對外只開 Cloudflare Tunnel，
防禦端本身不需要公網 IP、不需要開任何入站埠。

IP 都由你決定：平台在哪、被保護網站在哪、誰可以管理防禦端，全部是安裝參數。

## 二、前置條件

- 管制端已裝好 BeakPlatform，並且**另外建立一家企業**來接收案件（合約勾選
  `form_workflow` 與 `open_defense`）。**不要用安裝時自動建立的系統預設企業**：它代表平台
  本身，沒有資安人員角色、也沒有處置流程與路由，步驟一的 `--provision` 會直接失敗
- 這家企業至少要有一位持 `SECURITY_STAFF` 角色的成員（建合約時會自動種出這個角色，
  到「權限管理中心 → 帳號配角色」指派即可），案件才有人能簽核
- 防禦端可連 Internet（抓 docker 映像檔與 Suricata 規則）、可連到管制端的平台埠
- **管制端的主機防火牆要放行防禦端的 IP 打平台埠**（例如 iptables 只放行特定來源時，
  要補一條給防禦端），否則事件送不進去，症狀是連線逾時而不是 401
- 要對外提供服務時：一個託管在 Cloudflare 的網域。沒有網域也能裝，只是 WAF 只能從內網打到

## 三、步驟一：在管制端發憑證（一行）

```bash
cd /opt/BeakPlatform
set -a && source .env && set +a
venv/bin/python scripts/od_node_pairing.py \
    --org <企業網域或secure_code> \
    --base-url http://<平台IP>:<埠>/beakplatform \
    --provision --apply
```

- `--base-url` 是防禦端連回平台用的網址，含 `/beakplatform` 前綴
- `--provision`：企業還沒有事件路由時，先建立最小受理鏈路（資安分類、處置表單、
  簽核流程、catch-all 路由規則）。已有的企業會自動略過。
  **這條最小流程只有「人工簽核 → 結束」，不會產生封鎖決策**，防禦端因此永遠沒有東西
  可落地。要走完「案件 → 核可 → 防火牆封鎖」整圈，再多跑一支腳本建出含決策節點的
  流程，並到「開放防禦 / 事件路由設定」把它建的範例規則啟用：

  ```bash
  venv/bin/python scripts/examples/provision_od_workflow_variants.py \
      --org <企業secure_code> --with-routing --apply
  ```
- 產出**一行開通字串**（`ODN1.` 開頭），內含平台網址、事件受理金鑰與執行帳號。
  **只顯示一次**，複製起來給步驟二用；弄丟就重跑一次發新的（舊的到「安全中心 / API Key」
  與「開放防禦 / 服務帳號」停用）

## 四、步驟二：在防禦端執行安裝

```bash
curl -fsSL https://raw.githubusercontent.com/ethan-beakmask/BeakPlatform/main/ITHome2026-WAF/install.sh -o install.sh
sudo bash install.sh \
    --pair 'ODN1....' \
    --backend http://<被保護網站IP>:<埠> \
    --cf-api-token <Cloudflare API Token> --cf-hostname app.example.com \
    --admin-ips <你的工作機IP>
```

腳本會自動：裝 docker 與 nftables → 從 GitHub 取得 `ITHome2026-WAF/` → 寫 `.env` →
產生 Suricata / ClickHouse / 防火牆設定 → 下載 Suricata 規則（約 40 MB）→
啟動全部容器 → 建 ClickHouse 表 → 註冊 CrowdSec → 印出各服務網址與密碼 → 跑健康檢查。
全程約 3～6 分鐘，多數時間在抓映像檔。

### 參數

| 參數 | 說明 |
|---|---|
| `--pair` | 步驟一的開通字串。不用它時改給 `--base-url` / `--intake-key-id` / `--intake-secret` / `--sa-id` / `--sa-secret` |
| `--backend` | 【必填】被保護網站在內網的位址，例 `http://192.168.1.30:8000` |
| `--cf-api-token` + `--cf-hostname` | 用 Cloudflare API 自動建 tunnel、ingress、DNS。Token 權限：Account → Cloudflare Tunnel: Edit、Zone → DNS: Edit、Zone → Zone: Read |
| `--backend-path /app` | 歡迎頁與主站用同一個 hostname 時必填：只有這個路徑前綴導到被保護網站，根路徑與其他路徑是歡迎頁（例：`--cf-hostname www.example.com --welcome-hostname www.example.com --backend-path /beakplatform`） |
| `--welcome-hostname www.example.com` | 多開一個對外 hostname 當「歡迎頁」（一行歡迎詞的靜態頁），有自己的 WAF 容器，刺探它同樣會產生事件。搭配 `--cf-api-token` 自動加 ingress 與 DNS；手動建 tunnel 時 Service 填 `http://waf-welcome:8080` |
| `--tunnel-token` | 不想給 API Token 時，自己到 Zero Trust 後台建 tunnel、把 connector token 貼進來（見第七節） |
| `--admin-ips` | 允許管理防禦端的來源 IP（逗號分隔）。預設自動加入平台主機與「你 SSH 進來的那台」 |
| `--home-net` | Suricata 的內網範圍，預設 `[192.168.0.0/16,10.0.0.0/8,172.16.0.0/12]` |
| `--no-ui` | 不裝 Grafana / EveBox / Portainer |
| `--ssh-guard` | SSH 也只准 `--admin-ips` 連。**確定清單無誤再開**，鎖到自己只能從主機 console 救 |
| `--dir` | 安裝目錄，預設 `/opt/ithome2026-waf` |
| `--yes` | 非互動；缺必填參數直接報錯 |

所有值都存在 `<安裝目錄>/.env`，之後改檔案再執行 `--reconfigure` 即可，不必重裝。

## 五、驗證

```bash
sudo bash /opt/ithome2026-waf/install.sh --verify
```

會列出容器狀態、ClickHouse / od-bridge / WAF 健康、Vector 設定檔、平台是否連得到、
執行帳號是否登入成功、cloudflared 是否已註冊、主機防火牆是否就緒。
「WAF SQLi 探測 403」代表規則引擎在擋。

要看整條鏈到平台建案：

```bash
sudo bash /opt/ithome2026-waf/install.sh --test-event
```

它送一筆來源 `vector`、攻擊者 `203.0.113.42` 的測試事件進 Vector，幾秒後 od-bridge
應印出 `forwarded ... status=200`，平台的「開放防禦 / 資安案件處置中心」出現一張標題含
`TEST-` 的案件。看到 `status=422 no_mapping` 代表企業沒有事件路由（回步驟一加 `--provision`）。

接著到案件處置中心以資安人員身分打開那張案件，填寫處置意見後按「封鎖攻擊來源」。
幾秒內 od-bridge 應印出 `decision ... action=block target=ip/203.0.113.42`，防禦端執行
`sudo nft list set inet secstack blocklist` 會看到 `203.0.113.42 timeout 1h`，平台的
「開放防禦 / 防禦決策」該筆狀態為 `applied`。這一步需要流程含決策節點（見步驟一的說明）。

真實路徑的驗證：從 Internet 打 `https://<你的 hostname>/?id=1' OR 1=1--`，應得到 403，
幾秒後平台出現案件，攻擊者 IP 是你的公網 IP。正常請求則應看到被保護網站的畫面。

## 六、日常操作

```bash
cd /opt/ithome2026-waf
sudo bash install.sh --status          # 容器、封鎖中的 IP、tunnel 狀態
sudo bash install.sh --reconfigure     # 改了 .env 之後
sudo bash install.sh --update          # 從 GitHub 更新程式後重新套用
sudo bash install.sh --uninstall       # 停止（資料卷保留；加 --purge 連資料一起刪）
sudo docker compose logs -f od-bridge  # 事件轉送與決策落地
sudo nft list set inet secstack blocklist        # 目前被封的 IP（帶剩餘秒數）
curl http://<防禦端IP>:8500/edl                   # 給防火牆抓的黑名單（純 IP 一行一個）
```

Suricata 規則更新（會套用 `suricata/disable.conf` 的停用清單，裡面有三條誤判率極高的 TCP stream 規則，
以及一條會把本機 cloudflared 自己的 tunnel DNS 查詢當事件的 ET INFO 規則）：

```bash
sudo bash install.sh --update-rules
```

各服務入口（安裝完成時會印出密碼，也在 `.env` 裡）：

| 服務 | 位址 | 說明 |
|---|---|---|
| WAF | `http://<防禦端IP>:8080/` | 內網驗證用，正式流量走 tunnel |
| Grafana | `http://<防禦端IP>:3000/` | admin / `GRAFANA_ADMIN_PASSWORD` |
| EveBox | `http://<防禦端IP>:5636/` | Suricata 告警瀏覽，無密碼，靠來源限制 |
| Portainer | `https://<防禦端IP>:9443/` | 容器管理，首次開啟設密碼 |
| ClickHouse | `http://<防禦端IP>:8123/play` | secstack / `CLICKHOUSE_PASSWORD` |
| od-bridge | `http://<防禦端IP>:8500/stats` | `/forwards` `/decisions` `/edl` `/edl/allow` |

以上只有 `--admin-ips` 與平台主機能連，其他來源連線逾時是預期行為。

## 七、Cloudflare Tunnel 手動設定（不用 API Token 時）

1. Cloudflare Dashboard → Zero Trust → Networks → Tunnels → Create a tunnel → Cloudflared
2. 複製「Install and run a connector」頁面的 token，安裝時給 `--tunnel-token`
   （或之後填進 `.env` 的 `CLOUDFLARE_TUNNEL_TOKEN` 再 `--reconfigure`）
3. Public Hostname → Add：Subdomain 自選、Service 選 `HTTP`、URL 填 `waf-nginx:8080`
   （這是 docker 內的服務名稱，cloudflared 容器與 WAF 在同一個網段）

用 `--cf-api-token` 時上述三步由 `cf_tunnel.py` 自動完成；`python3 cf_tunnel.py status`
可查連線狀態，`python3 cf_tunnel.py remove --hostname 舊名稱` 可移除不要的 hostname（含 DNS）。
同一個 hostname 要同時放歡迎頁與被保護網站時，手動設定要建兩條 Public Hostname：
先建 Path 填 `beakplatform`（或你的前綴）指 `http://waf-nginx:8080`，再建不填 Path 的指 `http://waf-welcome:8080`。

## 七之一、內容物與授權

本安裝包幾乎全是別人的開源專案，只有 od-bridge 與幾支整合腳本是自己寫的。
每個元件的版本、授權、上游位址與單獨安裝指令，以及著作權聲明（中英對照），
見安裝目錄內的 `COMPONENTS.md`。

## 八、換 IP 或搬家

防禦端的設定不綁自己的 IP（服務綁 0.0.0.0，來源限制看的是對方的 IP），所以換 IP 只要：

1. 改主機 IP
2. `sudo bash /opt/ithome2026-waf/install.sh --reconfigure`（重新偵測網卡與 IP、重生防火牆、確認 tunnel 連上）
3. 管制端與被保護網站的防火牆若有來源 IP 白名單，改成新 IP

Cloudflare Tunnel 認的是 token 不是 IP，會自己重新連上。

若要做兩台防禦端共用一個服務 IP 的熱備切換，見 `docs/install/ithome2026_waf_standby.md`。

## 九、安全邊界（安裝完請讀）

- **能直連防禦端 8080 的人可以偽造攻擊者 IP**（自帶 `Cf-Connecting-Ip` header）。
  所以 8080 只放行平台與 `ADMIN_IPS`；Vector 也只採信 cloudflared 容器送來的歸因 header
- 8688（Vector 注入口）只綁本機，能打到它就能注入任意事件，不要改成對外
- EveBox 與 Vector API 沒有認證，Portainer 掛著 docker.sock（拿下等於 root）——
  全靠來源限制，`ADMIN_IPS` 不要填整個網段
- 平台核可的封鎖決策會直接落地到本機 nftables；`ADMIN_IPS` 與平台主機在自鎖保險名單內，
  永遠不會被封。要保護其他關鍵 IP（DNS、上游 API）請在平台的「保護目標」設定
- `.env` 含所有密碼與金鑰，權限 600，不要複製到別處

## 十、常見問題

| 症狀 | 原因與處理 |
|---|---|
| 平台連線 `HTTP 000` | 管制端防火牆沒放行防禦端 IP 打平台埠 |
| od-bridge 一直 `401` | 開通字串貼錯或該 API Key 已停用；重跑步驟一發新的，`--reconfigure` |
| `status=422 no_mapping` | 企業沒有事件路由；步驟一加 `--provision`，或在「開放防禦 / 事件路由設定」建規則 |
| 執行帳號登入 `429` | 短時間登入太多次，等 90 秒 |
| 執行帳號登入 `500`（od-bridge 印 `SA login 500: Internal server error`） | 管制端 `.env` 缺 `OD_SA_JWT_SECRET`（2026-09-13 之前的 `install.sh` 不會產生它）。在管制端重跑 `sudo bash /opt/BeakPlatform/scripts/install.sh --update` 會自動補上，或手動加一行 base64url 32 bytes 的值後 `systemctl restart beakplatform` |
| 案件核可了，防禦端沒有動作 | 流程沒有決策節點（`--provision` 的最小流程就是這樣），到「開放防禦 / 防禦決策」看不到任何一筆。依步驟一建含決策節點的流程並啟用路由 |
| 「放行」決策狀態變 `failed`、`unsupported_action:allow` | 2026-09-13 之前的版本會這樣，現在放行只配 EDL。平台端 `decision_writer_handler.py` 已改為寫入放行決策前自動只保留支援放行的執行點（目前只有 `edl`），nftables／crowdsec 不再配上去；升級平台版本即可，不必手動改流程 |
| WAF 正常請求 `502` | 防禦端連不到 `--backend`，先在防禦端 `curl` 那個位址；被保護網站若有 IP 白名單要放行防禦端 |
| WAF 正常請求 `000` | 被保護網站對根路徑不回應（很多站台刻意如此），改測實際頁面路徑 |
| Suricata 一直重啟 | `docker compose logs suricata`；常見是網卡名稱不對（`--iface`）或規則檔損毀（重跑規則更新） |
| 管理頁面連線逾時 | 你的來源不在 `ADMIN_IPS`；改 `.env` 後 `--reconfigure` |
| 誤判太多 | `.env` 改 `WAF_RULE_ENGINE=DetectionOnly` 觀察一天，或針對路徑在 `waf/modsec-overrides/` 放寬 |
| 被保護網站掛掉時平台出現一堆沒有規則編號的案件 | WAF 對 5xx 回應也會記錄。這是刻意的（後端異常也是事件），量由封頂規則控制 |
