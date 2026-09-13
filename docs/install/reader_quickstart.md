# 兩台主機練習環境：安裝 SOP

**這份是給讀者照抄的最短路徑。** 目標：一台平台（管制端）＋一台防禦節點（WAF），
內網就能跑完「攻擊事件 → 資安案件 → 簽核 → 封鎖落地」整圈，不需要網域、不需要公網 IP。
整個過程只會下三次指令，其餘都在瀏覽器裡操作。

## 零、你要先準備的

| 項目 | 規格 |
|---|---|
| 主機 A（平台） | Ubuntu 22.04／24.04，2 vCPU、4 GB、20 GB 磁碟，固定內網 IP |
| 主機 B（防禦節點） | Ubuntu 22.04／24.04，2 vCPU、6 GB、30 GB 磁碟，固定內網 IP，可連 Internet |
| 兩台都要 | 一個能 `sudo` 的帳號；主機 B 能連到主機 A 的平台埠（預設 8000） |
| GitHub PAT | 一把有 `repo` 權限的 Personal Access Token（程式碼在私有 repo，兩台安裝都用同一把） |
| 一組密碼 | 至少 12 碼、含大小寫、數字、特殊符號（例 `Practice2026#Ok`）。**同一組密碼會用在系統管理員與示範企業所有帳號** |

負載是 1～3 人練習用，上表已經寬鬆。時鐘不必對時，但兩台差超過 5 分鐘簽章會失敗（NTP 通常已開）。

## 一、主機 A：裝平台（一行，約 3～5 分鐘）

```bash
curl -sL -H "Authorization: token <你的PAT>" \
  https://raw.githubusercontent.com/ethan-beakmask/BeakPlatform/main/scripts/install.sh \
  | sudo GITHUB_TOKEN=<你的PAT> ADMIN_INITIAL_PASSWORD='<你的密碼>' INSTALL_DEMO=1 bash
```

`INSTALL_DEMO=1` 讓安裝結束後自動多做兩件事：建立示範企業 DemoSOC（含資安人員、事件路由、處置流程），
以及發一組給防禦節點用的開通字串。

跑完畫面最下方會有兩段，**整段複製存起來**（也存在 `/opt/BeakPlatform/demo-credentials.txt`，只有 root 讀得到）：

```text
[INFO] 全新安裝完成
  URL:  http://<主機A IP>:8000
  系統企業: sys-xxxxxxxxxxxx
  管理員:   admin@sys-xxxxxxxxxxxx
  ...
[INFO] 示範企業與防禦節點開通資訊
  示範企業: DEMOSOC / demo-soc.example
  登入網址: http://<主機A IP>:8000/beakplatform/auth/org/demo-soc.example/login
  示範企業管理員: admin-admin.ops@demo-soc.example
  示範帳號共用密碼: <你的密碼>
  防禦節點開通字串: ODN1.....
  WAF 主機執行指令: sudo bash install.sh --pair 'ODN1....' --backend http://<被保護網站IP>:<埠>
```

**檢查點**：瀏覽器開 `http://<主機A IP>:8000/beakplatform/auth/login` 看得到登入頁。
網址一定要帶 `:8000` 和 `/beakplatform`，少一個都是 404。

### 第一次登入要知道的三個帳號

| 帳號 | 用途 | 第一次登入會發生什麼 |
|---|---|---|
| `admin@sys-xxxx` | 系統管理員（管所有企業） | 強制改密碼 |
| `enterprise@sys-xxxx` | 系統預設企業的原始管理員 | 強制改密碼 → 進「初始設定精靈」建一個綁定成員的新管理員，原始帳號自動停用。**練習用不必碰它** |
| `admin-admin.ops@demo-soc.example` | 示範企業管理員 | 直接進儀表板，已過精靈 |

**練習從示範企業開始**，用「登入網址」那個 URL 登入示範企業管理員即可。
資安人員帳號 `linda.hu@demo-soc.example`、資安主管 `kevin.ye@demo-soc.example`，密碼同一組。

## 二、主機 B：裝防禦節點（一行，約 3～6 分鐘）

**以下在主機 B 上執行。**把主機 A 總結裡的「WAF 主機執行指令」貼到主機 B，補上 PAT 與被保護網站位址：

```bash
curl -fsSL -H "Authorization: token <你的PAT>" \
  https://raw.githubusercontent.com/ethan-beakmask/BeakPlatform/main/ITHome2026-WAF/install.sh -o install.sh
sudo GITHUB_TOKEN=<你的PAT> bash install.sh \
  --pair 'ODN1....' \
  --backend http://<主機A IP>:8000 \
  --admin-ips <你的工作機IP> \
  --yes
```

- `--backend` 填要被 WAF 保護的網站。練習時直接填平台本身（主機 A）最省事
- `--admin-ips` 是允許進 Grafana／EveBox／Portainer 管理介面的來源；不給也能裝，預設放行平台主機與你 ssh 進來的那台
- 這台會自己裝 docker 並拉映像檔，讀者不需要碰 docker
- 裝完的入口：WAF `http://<主機B IP>:8080/`、Grafana `:3000`、EveBox `:5636`、Portainer `https://…:9443`、
  od-bridge 狀態 `:8500/stats`、**EDL 黑名單 `:8500/edl`／白名單 `:8500/edl/allow`**（一行一個 IP 的純文字，防火牆可直接當外部動態清單抓）。
  **這些埠只對主機 A 與 `--admin-ips` 的來源開放**，其他機器連不到；要加來源改 `.env` 的 `ADMIN_IPS` 後 `--reconfigure`

跑完印出各服務網址與密碼，接著驗證：

```bash
sudo bash /opt/ithome2026-waf/install.sh --verify        # 全綠才往下
sudo bash /opt/ithome2026-waf/install.sh --test-event    # 送一筆假攻擊事件進平台
```

**檢查點**：回主機 A 的平台，用示範企業資安人員登入，「開放防禦 → 資安案件處置中心」出現一張標題含 `TEST-` 的案件。
從 `--admin-ips` 那台機器開 `http://<主機B IP>:8080/?id=1' OR 1=1--` 應該得到 403，那是 WAF 在擋。

## 三、用指令建一張案件（選用，示範外部系統對接）

1. 用示範企業管理員登入，「系統安全 → API Key 管理」新增一把，授權範圍勾「資安」分類。
   `secret` 只顯示一次，按 [複製] 存起來。
2. 在任何有 Python 3 的機器（主機 A 上就有）：

```bash
export BP_BASE_URL='http://<主機A IP>:8000/beakplatform'
export BP_KEY_ID='ak_xxxxxxxx'
export BP_SECRET='<剛複製的 secret>'
python3 /opt/BeakPlatform/scripts/bp_trigger.py --list
python3 /opt/BeakPlatform/scripts/bp_trigger.py \
  --form-code SEC_INCIDENT_RESPONSE --subject 'TEST-手動建單' \
  --field finding_title='TEST-手動建單' --field source_system=manual \
  --field severity_id=3 --field actor_ip=203.0.113.42 --field target_host=demo.internal
```

回 `HTTP 201` 就成功，案件處置中心會多一張。細節與錯誤碼見 `api_trigger.md`。

## 四、要收到系統信才做（選用）

忘記密碼、新帳號通知這類信需要 SMTP。用系統管理員到「主機設定 → 發信服務」填一組 Gmail 應用程式密碼即可，
步驟見 `mail_smtp.md`。練習流程本身不需要它。

## 五、卡住時先看這裡

| 症狀 | 原因與處置 |
|---|---|
| 主機 A 安裝的 `curl` 回 404 | PAT 沒帶、或 header 寫錯。`-H "Authorization: token <PAT>"` 那行不能省 |
| 開網址是 404 | 少了 `:8000` 或 `/beakplatform` |
| 主機 B `--verify` 說平台連不到 | 主機 A 有防火牆時要放行主機 B 的 IP 打 8000；症狀是逾時不是 401 |
| od-bridge 一直 401 | 開通字串貼錯或貼到舊的。回主機 A 跑 `sudo bash /opt/BeakPlatform/scripts/install.sh --demo` 重發一組，再 `--reconfigure` |
| `--test-event` 回 `422 no_mapping` | 示範企業沒有事件路由。用 `--demo` 裝的不會發生；手動建企業的請看 `ithome2026_waf.md` 步驟一的 `--provision` |
| 看不到 `TEST-` 案件 | 登入的帳號不是示範企業的資安人員（案件在 DemoSOC 底下，系統管理員看不到） |
| 示範企業帳號登入回改密碼頁 | 用錯帳號：示範企業帳號不會強制改密，會的是 `admin@sys-xxxx` 與 `enterprise@sys-xxxx` |
| 忘記示範密碼 | `sudo cat /opt/BeakPlatform/demo-credentials.txt` |

## 六、重來一次

主機 A：`echo YES | sudo bash /opt/BeakPlatform/scripts/install.sh --uninstall`（會刪資料庫與目錄，不備份），再跑第一節。
主機 B：`sudo bash /opt/ithome2026-waf/install.sh --uninstall --purge`，再跑第二節。
主機 A 重裝後系統企業代碼與開通字串都會變，主機 B 要用新的字串重裝或 `--reconfigure`。
