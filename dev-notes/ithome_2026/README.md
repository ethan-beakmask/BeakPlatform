# ITHome 2026 鐵人賽 30 篇連載

本目錄放連載的草稿、素材與進度追蹤。**在 `dev-notes/` 底下，不會推上 GitHub**
（`scripts/push_github.sh` 的 `EXCLUDE_DIRS` 已含 `dev-notes`），草稿裡的內網 IP、
主機路徑、密碼討論不會外流。發表是貼到 iThome 網站，不從 repo 提供。

- `IThome_30Topic.txt` — 30 篇的原始構想（編號 / 主題 / 主軸 / 要項），
  原檔在 `/opt/Ethan_Lab/ITHome_2026_鐵人賽/`
- 該原目錄另有一批 claude.ai 討論產出的**資安分析工具**
  （XFF、釣魚信件、WAF ASM、SBOM），是建立案件前的獨立程式，
  **刻意不搬進本 repo**，只在文章中引用

## 對照盤點（2026-08-20）

`OK` 現成可示範｜`小改` 半天內｜`缺` 需開發｜`文` 純理論或敘事，不吃功能｜`外` 公司現成程式帶回去識別化

| # | 主題 | 狀態 | 依據 |
|---|---|---|---|
| 1 | 預設企業與預設表單流程（織夢） | 文 | 純紙上談兵；手冊 01/04 章 14 頁可當素材 |
| 2 | 安裝與驗證 | 小改 | `install.sh` / `verify_install.sh` / `export_factory_defaults.py` 都在；缺出廠資料包 |
| 3 | SOC 機制簡介 | OK | 三個 SOC 流程都在 beluga，路由 11 條，`od_intake_send_event.py` 可發動 |
| 4 | 系統級管理員 | OK | 手冊 02 章 11 頁 |
| 5 | 企業級管理員 | OK | 手冊 03 章 21 頁（含核決權限、TG/Email） |
| 6 | 軟體防火牆 .20 | OK | `sec-vm-bootstrap/bootstrap.sh`；已定調抓畫面即可 |
| 7 | 人員表單 | 小改 | FormAdapter/TG/Mail 現成；SQL Sync **已驗證可用**（見下） |
| 8 | 完全自動表單 | **缺** | SqlExecutor 要補 handler + 範例 SP |
| 9 | 人機混合（三個 SOC 流程） | OK | 同 #3 |
| 10 | L1→AI→L2→L3→派工 | **缺** | AI node + 流程發動 node |
| 11 | Gmail 收信聚合 | 外 | 公司有半套（收信到拆信）；平台無 IMAP |
| 12 | 情資信件自動化／黑名單 | 外 | 公司現成 |
| 13 | 資安案件共同基本資料預查 | 外 | 依賴 #14~17 先完成 |
| 14 | VirusTotal / AbuseIPDB 多 key 輪流 | 外 | 公司用兩年穩定 |
| 15 | IPinfo | 外 | 同上 |
| 16 | XFF 與 AS code | 外 | 另有 `xff_intel` DB（11 張表，beakmask 專案）+ 36KB 討論稿 |
| 17 | DNS / Domain 情報 | 外 | 同上 |
| 18 | 開發 AI 流程元件 | **缺** | 開發過程即文章內容；順便查設計器 node 清單缺漏 |
| 19 | AI 元件應用 | **缺** | #18 完成後把 AI node 插進 SOC 流程 |
| 20 | 案件資料庫分析 | 文 | 只講理論 + 流程圖 |
| 21 | SSH 進 Splunk 查案 | 外 | 展示擴充性，各家環境不同、另案處理 |
| 22 | ELK 查案 | 外 | 同上 |
| 23 | PortScan 案件 | 小改 | OD 聚合 + ClickHouse 有真實資料 |
| 24 | VPN 案件審查 | 外 | 方法論為主 |
| 25 | 弱點掃描三種安裝／OpenVAS 整合 | OK | `beakrisk.service` 在跑、`vulnmgmt` DB 在、`agent/gvm_commands.py` 有 GVM 整合 |
| 26 | 弱點審查與判定 | OK | 風險調整簽核已有 |
| 27 | 大量排程管理 | 文 | 平台無排程 UI；走全域 heartbeat 規範寫方法論 |
| 28 | 排程維護案件流程 | 小改 | 排程異常用 intake 送案，零平台開發 |
| 29 | 報表與 Dashboard | 小改 | 新增一頁；考慮 Sankey / Network Graph 撐場面 |
| 30 | 結語 | 文 | |

## 待開發清單（賽前）

依 Ethan 2026-08-20 定調，只剩三個 node + 一頁 dashboard：

| 項目 | 規格 | 支撐篇章 |
|---|---|---|
| ~~**AI node**~~ | **2026-08-20 完成**。實作與實測紀錄見 `ai_node_findings.md` | 8, 10, 18, 19 |
| **SqlExecutor** | 補後端 handler。呼叫**平台主庫**的白名單 SP，用平台主帳號 `beakplatform`，強制帶 org_code，白名單存 DB 表。企業獨立庫**不碰**（企業自寫 SP 有提權風險） | 7, 8 |
| **流程發動 node** | HttpRequest 包裝成固定用途：下拉自己企業的配對清單（標記有無發行，未發行＝測試用）、顯示表單必填欄位、資料齊全就單獨觸發流程，**不理會原流程是否結束**。要不要等待由設計師拖拉節點自行決定 | 10 |
| **Dashboard** | 新增一頁，內容到時再定 | 29 |

**接收端已現成**：`/api/trigger/form`（`modules/form_workflow/api/external_trigger.py:109`，
走 HMAC + rate limit + scope），流程發動 node 打的就是它。

## AI node 已完成（2026-08-20）

節點型別 `AiAgent`，檔案：

| 檔案 | 內容 |
|---|---|
| `modules/form_workflow/services/node_handlers/ai_agent_handler.py` | handler 主體（沙箱 CLI、canary、規則層、解碼、輸出過濾） |
| `.../node_handlers/factory.py` | 註冊（handler 從 22 個增為 23 個） |
| `.../js/wf-node-ai-agent.js` | 設計器屬性面板 |
| `.../js/wf-accordion.js`、`wf-save.js`、`workflow_designer.html` | 面板 dispatch／存檔／載入三處接線 |
| `scripts/migrations/105_seed_ai_agent_node.sql` | 節點定義（category=整合） |
| `backend/tests/test_ai_agent_node.py` | 30 個測試，全部做過 mutation 驗證 |

**一手實測結論在 `ai_node_findings.md`**，那是第 18 篇的主要素材：
`claude -p` 是 agent 不是 API（預設繼承全部 MCP 工具與全域 CLAUDE.md）、
`--tools ""` 與 `--allowedTools ""` 差一個字卻是全關 vs 全開、
驗證只能看副作用不能問它自己有什麼工具、模型自己拒答時 fallback 如何生效、
mutation 抓到一個假測試、外部顧問建議裡的一條錯誤。

**隔離用原廠的 `--safe-mode` + `--tools ""` 兩個參數就夠**，
不需要專用 HOME、不需要 MCP 空設定、不需要工具黑名單、
**沒有任何要預先建立的目錄**。第一輪手工搭的那整套已於 2026-08-20 移除——
那段「花六輪試誤搭出來的東西原廠一個參數就解決」本身就是文章素材。

## 手冊已補（2026-08-21）

「不用再改程式」的四項功能已寫進使用者手冊第 4 章（`docs/manual/04_form_workflow/`）：

| 頁 | 對應篇 |
|---|---|
| `workflows.md`（補寫） | 7, 8, 10 的共同底稿 |
| `ai_agent_node.md`（新） | 18, 19 |
| `sql_executor_node.md`（新） | 8 |
| `ai_usage.md`（新，PF-141 結案） | 18, 19 |
| `mappings.md`（補寫，含 SQL 同步啟用） | 7 |

驗收留證 `/opt/tmp/verify/20260821-manual-ch04.log`。第 23、28 篇是純敘事，
用現成功能即可，沒有對應的手冊頁。

## 已排除

**Condition / Switch 不在參賽範圍**，已在 `workflow_node_definitions` 設
`is_active=false`（否則設計器拖得出來、點開沒面板、跑起來 error，寫文件時會被
誤當成已完成的功能）。賽後開發，備忘見 **PF-131**（含 Branch 的多參數與防呆需求）。

## 賽前已完成的驗證

**SQL Sync 端對端通過**（2026-08-20，證據 `/opt/tmp/verify/20260820-sync-worker.log`）：
建 `beakplatform-dev-sync-worker.service` 並啟動 → 啟用某配對的 SQL 同步 → 自動在
`org_106` 建 `form_86_v3` 與 `form_86_v3_approvals` → 手動 enqueue 一筆已核准表單 →
worker 5 秒內消化 → 資料落地，`textField` 是**簽核者改過的終態值**。

`enqueue_sync_safe()` 掛在 `workflow_engine.py:477`，註解「流程結束時寫入企業 DB
（終態資料，含簽核者修改）」——**第 7 篇那一半的開發量是零**。

兩個要記得的：**SQL 同步啟用後不可關閉**（`mappings.py:439` 硬擋）；
配對的 `sql_sync_enabled` 預設 false，所以 worker 起來後沒事做是預期狀態。

**全庫軟刪除已實體清除**（830 筆，26 張表），出廠資料包做 diff 時不會夾帶墓碑記錄。
工具 `scripts/purge_soft_deleted.py`（預設 dry-run，`--apply` 才寫入）。

## 未處理的已知項目

清除軟刪除後留下**指向不存在流程實例的歷史記錄**，全是終態、executor 不會撿，
但對出廠資料包的 diff 是噪音：

| 表 | 筆數 |
|---|---|
| `fw_node_execution_logs` | 1217 |
| `fw_node_execution_queue` | 574（全部 SUCCESS/CANCELLED） |
| `fw_approval_records` | 37 |

**根因已查明並記成 PF-133**：`/hostconfig/data-maintenance` 的清除功能本身是完整的
（有 `PURGE_ORPHAN_CLEANUP` 對照表，可指定子表 delete 或 set_null），
但那張表只涵蓋平台核心表 ＋ `fw_form_templates` / `fw_workflow_templates`，
**實例層（`fw_form_instances` / `fw_workflow_instances`）與整個 `dc_*`、`od_*` 都沒登記**。
架構問題是那張表硬編碼在平台層，模組要登記得去改 `backend/app/web/hostconfig.py`。

## 完整測試基準（2026-08-20 實測）

`bash scripts/run_tests.sh -q`：**1 failed, 541 passed, 2 skipped, 2 errors（8分29秒）**
證據 `/opt/tmp/verify/20260820-full-tests.log`。

| 項目 | 判定 |
|---|---|
| `test_auth_interceptor.py::test_admin_required_for_admin` failed | **已知基準**（PF-34，測試庫無 RBAC seed） |
| `test_e2e_portal_cancel.py` skipped | **已知基準**（寫死的驗收頁已不存在） |
| `test_portal_file_stage_a.py` 1 skipped | 既有 |
| `test_od_protected_targets.py` 2 errors | **測試間污染，不是回歸**。單獨跑該檔 **56 passed**（59 秒）。CLAUDE.md 的歸因順序第 1 條就命中，不需追查功能 |

CLAUDE.md 現行的已知非綠清單**只列了前兩項**，`test_od_protected_targets` 這兩個
error 在完整跑時才出現、單獨跑就消失，下個 session 看到會誤判成自己弄壞的。

## 相關 BBN 待辦

- **PF-131** 賽後開發 Condition／Switch + Branch 多參數防呆
- **PF-132** AI node 安全補強建議（Fable 5 產出，全文
  `dev-notes/Ai_node_security_requirements.md`，鐵人賽期間當**教材**用，不要求全實作）
- **PF-133** 資料維護的孤兒清理表缺三大塊（fw 實例子表、全部 `dc_*`、全部 `od_*`）
- **PF-124** 平台 API 未走 ResourceGateway 的既有技術債基準
