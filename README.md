# BeakPlatform

企業自動化執行框架（Enterprise Automation & Execution Framework）的運行平台。
以表單、流程、節點、案件、簽核紀錄與執行紀錄，實踐 **Trigger / Case / Node / Actor / Evidence / Lifecycle** 六個概念。

## 這是什麼

BeakPlatform 是以我的企業管理心得設計的理論框架的運行平台。
它是一套**可配合企業既有制度運作**、把事件、人工決策、資訊系統與自動化操作組合成可執行流程的**自動化流程執行框架**。

ISO 27001、SOC、ITSM、行政簽核、資產管理或企業內部程序，都只是它可以承載的流程之一。

流程可由人員、外部系統、AI 或事件發動（外部系統與 AI 走同一條 API Key 通道），
並允許人機、機人、機機與人人等節點在同一個案件生命週期內混合運作。

它不重新定義企業應該做什麼，而是處理另一個問題：

**企業決定要做的事情，要如何真正由人與機器共同執行、留下證據，並形成可持續改善的閉環。**

讓各種管理與稽核的理論得以在一個真正可安裝、可稽核的中型平台上落地。

BeakPlatform 是整合型的運作平台，不只是傳統的流程引擎、BPM 或電子簽核系統，
應視為基於企業管理框架設計的管制平台。最大的差別是：
四種發動模式都可以在完全沒有人員介入的情況下，全由程式或 AI 推進，而且過程有紀錄、能被稽核。

### 框架概念與平台實體對照

| 框架概念 | 平台上對應的東西 |
|---|---|
| Trigger | 表單中心送單、`/api/trigger/form`（API Key）、防禦節點事件受理 |
| Case | 流程實例、資安案件 |
| Node | 流程設計器裡的節點：人工簽核、AI 分析、OS 命令、SQL、Telegram、Email、分支、延遲、子流程 |
| Actor | 簽核者解析（角色＠單位、代理與候補）、執行帳號、API Key |
| Evidence | 簽核紀錄、節點執行紀錄、稽核日誌、決策落地回報 |
| Lifecycle | 案件從建立、處置、封鎖到到期解封的完整閉環 |

## 開發歷程與這一版

- 2025/09 開始構思與撰寫，2026/01 整個翻新、從零開發的新版以私有模式上傳 GitHub。
- 因參加 iThome 鐵人賽決定公開。本版為簡化讀者與用戶的技術負擔，
  移除或標記多項未完成功能、撰寫超簡單安裝，並追加一鍵安裝 WAF 防禦節點。
- 參賽以資安與管理為主軸，這版已內建大、中、小三個量級的 SOC 處置流程
  （SOC 團隊版、小企業單人版、最小版），約佔參賽一半的章節；
  另一半以資料分析經驗套入流程元件的應用當實例。
- 本版為參賽特化，介面或細節未盡完美，會在賽後繼續優化。

### 模組狀態

| 模組 | 狀態 |
|---|---|
| form_workflow（表單、流程、簽核、節點） | 穩定 |
| open_defense（事件受理、路由、案件處置、決策落地） | 穩定 |
| spec_formulate（規格制定） | 穩定 |
| vuln_lifecycle（弱點管理） | 未完成，選單已標記 |
| nocode_builder（NoCode 子系統） | 未完成，選單已標記，請勿用於正式環境 |

## 安裝

### 系統需求

- Ubuntu 22.04 / 24.04 LTS，可 sudo
- 安裝腳本會自動裝好 PostgreSQL、Redis、Nginx、Python 3

流程設計器的「AI 分析」節點會呼叫本機安裝的 Claude Code CLI，其他功能不需要它，
前置條件見 `docs/install/ai_node.md`。

### 一行安裝（含示範企業）

```bash
curl -sL https://raw.githubusercontent.com/ethan-beakmask/BeakPlatform/main/scripts/install.sh \
  | sudo ADMIN_INITIAL_PASSWORD='<你的密碼>' INSTALL_DEMO=1 bash
```

`INSTALL_DEMO=1` 會在平台裝完後建立示範企業 DemoSOC、示範帳號、資安事件受理流程，
並印出防禦節點的一次性開通字串（同時存在 `/opt/BeakPlatform/demo-credentials.txt`，僅 root 可讀）。
已安裝的主機可單獨執行 `sudo bash /opt/BeakPlatform/scripts/install.sh --demo`。

兩台主機（平台＋防禦節點）的完整練習 SOP 見 **`docs/install/reader_quickstart.md`**。

### 第一次登入

- 網址：`http://<主機IP>:8000/beakplatform`（安裝總結會印出）
- 系統管理員：`admin@<系統企業代碼>`（代碼由安裝腳本產生並印出），首次登入須改密碼
- 練習請從示範企業開始：`admin-admin.ops@demo-soc.example`，密碼同安裝時設定

### 服務管理

```bash
sudo bash /opt/BeakPlatform/scripts/install.sh --status
sudo bash /opt/BeakPlatform/scripts/install.sh --start
sudo bash /opt/BeakPlatform/scripts/install.sh --stop
sudo bash /opt/BeakPlatform/scripts/install.sh --update      # 更新程式並重啟，資料保留
sudo bash /opt/BeakPlatform/scripts/install.sh --uninstall   # 移除服務、目錄與資料庫
journalctl -u beakplatform -f
```

## 一鍵安裝 WAF 防禦節點（Integrated-WAF）

`Integrated-WAF/` 是一包「快速安裝與整合」的防禦節點：
WAF（nginx + ModSecurity + OWASP CRS）、Suricata、CrowdSec、Vector、ClickHouse，
以及自寫的 od-bridge，把事件送進 BeakPlatform 建立案件，並把平台的封鎖決策落地到 nftables、CrowdSec 與 EDL。

裡面的偵測與防禦元件都是各上游專案的成果，我只做了簡化安裝與配合 BeakPlatform 的整合調整。
內容物、版本、各元件授權與著作權聲明（中英）見 `Integrated-WAF/COMPONENTS.md`，
安裝說明見 `docs/install/ithome2026_waf.md`。

## 版權與授權

### 第三方元件

專案與文章中用到的 OWASP ModSecurity CRS、Suricata、Emerging Threats Open 規則、CrowdSec、
Vector、ClickHouse、cloudflared、nginx，以及其他所有非本人創作的軟體、規則與素材，
著作權均屬各原作者與專案所有，並依其各自的授權條款使用；本專案不主張任何所有權，也不改變它們的授權。
完整清單見 `Integrated-WAF/COMPONENTS.md`。

### 本專案

本專案以 Apache License 2.0 釋出。

- 完整授權條款見專案根目錄 [LICENSE](./LICENSE)
- Copyright 2026 Ethan Yu / 余瑞慶
- 你可以自由使用、修改、散佈，但須保留版權聲明、變更通知，並遵守 Apache 2.0 規範
- Apache 2.0 內含專利授權與訴訟保護條款，可降低未來專利糾紛風險

### 商標

「BeakMask」、「BeakPlatform」為 Ethan Yu / 余瑞慶 之商標，不在 Apache License 2.0 授權範圍內。
fork 或衍生作品請使用其他名稱以避免混淆。
