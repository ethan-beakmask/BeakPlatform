# BeakPlatform - Claude Code 專案規範

## 這份文件的範圍（2026-07-29 重整）

本檔只放**「不知道就會做錯」的規範與環境事實**。細節與可重複使用的內容已分流：

| 找什麼 | 去哪 |
|---|---|
| 派工給 codex 時要貼的規範片段 | **`dev-notes/codex_spec/`**（frontend / i18n / security / portal / _footer） |
| 檔案上傳下載的完整 API 用法 | `dev-notes/FILE_SERVICE.md` |
| 改哪些檔案（任務導向） | `dev-notes/manifests/README.yaml` → 對應 manifest |
| 安全踩坑清單 | `dev-notes/manifests/SECURITY_PITFALLS.md` |
| 權限模型定版 | `dev-notes/PERMISSION_MODEL.md`、`dev-notes/COMPONENT_VISIBILITY_GUIDE.md` |
| Page IR schema 與各 widget 欄位（含 menu） | `dev-notes/PAGE_IR_SPEC.md`、`dev-notes/PAGE_IR_LAYOUT_ENGINES.md` |
| 共用元件（引用語意） | `dev-notes/SHARED_COMPONENTS_SPEC.md` |
| 頁面版面樣板庫（複製語意） | `dev-notes/PAGE_TEMPLATE_SPEC.md` |
| 用 API 操作 NoCode 子系統的實測陷阱 | `dev-notes/codex_spec/portal.md` 尾段 |
| 名詞對照 | `dev-notes/GLOSSARY.md` |
| 跨 session 待辦與決策脈絡 | BeakBroodNest 知識庫（`note_search` / `note_get`） |
| NoCode Builder / portal 的開發備忘 | `dev-notes/NOCODE_PORTAL_NOTES.md`、`dev-notes/PORTAL_ACCOUNT_SPEC.md` |
| open_defense 平台側 / `.20` 資安堆疊 | `dev-notes/OPEN_DEFENSE_ARCHITECTURE.md`、`dev-notes/SEC_STACK_ARCHITECTURE.md` |
| 測試（pytest 環境、`test_client` 坑、Playwright） | `dev-notes/TESTING_NOTES.md` |
| 流程設計器、graph 操作、publish | `dev-notes/WORKFLOW_DESIGNER_NOTES.md` |
| 企業行事曆（投影來源、受眾規則、二三期入口） | `dev-notes/CALENDAR_SPEC.md`（PF-229） |
| 企業專屬資料庫（建立／刪除／健康／佈建憑證） | `dev-notes/ORG_DATABASE_LIFECYCLE.md`（PF-256） |
| 集團共用資料庫為什麼不在了（看到 `cg_*`／`conglomerate` 殘留先讀這份） | `dev-notes/CONGLOMERATE_SHARED_DB_RETIRED.md`（PF-269，2026-09-13 刻意移除，集團分群保留） |
| 節點型別規格（AiAgent / SysSqlExecutor / OsExecutor / 盤點） | `dev-notes/AI_NODE_SECURITY.md`、`dev-notes/SQL_EXECUTOR_SPEC.md`、`dev-notes/OS_EXECUTOR_SPEC.md`、`dev-notes/NODE_TEST_INVENTORY.md` |

**維護原則**：新的踩坑先問「這是 codex 猜不到的專案特有事實，還是通用工程常識？」
前者才寫進來；屬於「派工時要貼給 codex」的，寫進 `dev-notes/codex_spec/` 並在本檔留指針。

**寫進本檔的門檻（2026-08-30 起）**：本檔每個 session 全文載入，所以判準不是
「這段重不重要」，而是**「不讀到會不會做錯，而做錯時症狀認不認得出來」**。
症狀靜默的留在本檔；認得出症狀的寫進 `dev-notes/`，本檔只留一行
「症狀 → 去哪查」的指針。模組專屬的深度細節一律走後者。

## 開發模式（Codex-first，2026-08-05 定版）

**本專案的標準開發迴路：主 Claude 寫 spec → `codex exec` 實作 → 主 Claude 驗收。**
呼叫規範（sandbox 參數、timeout、stdin 餵 prompt）見
`~/.claude/knowledge_base/standards/coding_standards/codex_first_policy.md`。

### 組 spec 的固定步驟

1. **檔案清單**：讀 `dev-notes/manifests/README.yaml` → 對應 manifest，spec 中列出精確檔案
   路徑與現有結構說明（codex 對專案無記憶，context 要餵足）
2. **規範片段**：依觸及範圍貼 `dev-notes/codex_spec/` 對應檔（frontend / i18n / security /
   portal），**`_footer.md` 每次必貼**。codex 不讀 CLAUDE.md——沒貼進 prompt 的規範
   一律視同不存在
3. **本檔的專案特有事實**（nginx 前綴、CSS 變數白名單、TZ-01、FILE-01 等）凡與任務
   相關，逐條複製進 spec，不能只給檔案路徑

### 驗收（主 Claude 專屬職責，不可外包）

- **VERIFY-01**（見下方同名章節）：codex 開不了瀏覽器，它的自我檢查表不算驗收。
  互動元素一律由主 Claude 用 chrome-devtools 實際點過，輸出落地 `/opt/tmp/verify/`
- **反向檢查先於功能測試**：每個抽象層搜尋「繞過它的直接寫法」（全域 CLAUDE.md
  Agent 協作規範）
- codex 常見瑕疵必查：死碼、拆字串規避檢查、manifest 只刪不補、裸中文未包 gettext、
  沒重啟服務就宣稱驗證通過
- **同義重複的測試案例**（2026-08-16 PF-117 實例）：spec 列了 10 條測試要求，codex 交出
  10 個函式，但其中兩個**主體一字不差**（只有函式名不同）。測試數字增加、全綠、
  自我檢查表也勾得起來，實際上少驗了一種場景。驗收時把新增測試的**斷言內容**
  掃一遍，不要只數函式個數
- **「機制對、目標錯」是最難抓的一類**（2026-08-06 批次 3 實例）：spec 要求
  「編輯共用元件時隱藏 table 的『列動作』『列連結目標』」，codex 用了正確的
  `x-show="!sharedComponentEditor.open"`，卻加在隔壁的「每頁筆數」「預設排序欄位」上。
  grep 條件字串會命中、`node --check` 會過、codex 的自我檢查表也會勾——
  **只有逐一列出受影響欄位的可見性才看得出來**。驗收互動 UI 時的通用手法：
  `evaluate_script` 回傳每個欄位的 label + `offsetParent === null`（是否隱藏），
  拿這份清單對 spec，不要只確認「條件有加」
- 退回上限 2 次，之後改由 Claude 依既有規範直接實作

### Claude 直接動手的例外

約 10 行內微改、codex 連續失敗 2 次、配額耗盡/限流、緊急修復、純文件/設定變更。

## 專案定位

**BeakPlatform 是一個多租戶權限管理平台**

這是一個**純平台**，核心功能：
- 安全控制（認證、授權、攔截）
- 多租戶隔離（企業資料隔離、RLS）
- RBAC 權限系統
- 動態選單系統
- 組織架構管理（部門、群組、角色）
- 人資架構管理（職等、職系、職稱）

**業務功能透過「模組」掛載，不在平台內實作。**

---

## 溝通對照表

用戶提到系統功能時，參照 `dev-notes/GLOSSARY.md` 快速定位。

用戶溝通慣例：
- `/path/` — URL 路徑（如 `/menu/` = `http://192.168.0.16:7000/beakplatform/menu/`，**app 掛在 nginx 的 `/beakplatform` 前綴下，缺前綴會 404**）
- `'名詞'` — 功能名稱或字串，多名詞時混用 `""` 區別
- `[按鈕]` — UI 按鈕或超連結元素
- `(URL)` — 從瀏覽器複製的完整 URL

---

## 每次對話必做

### 1. Git Commit (對話結束)
**每次對話結束前**：

```bash
cd /opt/BeakPlatform-dev
git add -A
git commit -m "類型: 簡短摘要

- 完成項目 1
- 完成項目 2

Generated with Claude Code"
```

**注意：commit 和 push 是兩件事。只 commit，不主動 push。用戶說 push 才 push。**

**多個 session 併行同一個 repo 時，`git commit` 會夾帶別人的變更。**
`git commit` 不帶路徑時提交的是**整個 staged 區**，不是你剛 `add` 的那幾個檔案；
上面的 `git add -A` 更是連別人改到一半的檔案一起收。
2026-09-08 實例：留守審查的 session 只 `git add` 一份設計文件就 commit，
把執行 session 先前已 staged 的兩個無關檔案刪除一併提交，
使另一件工作（canary 廢除）被拆散在兩個不相關的 commit ＋ 一半留在工作區——
**症狀靜默，不看 diffstat 不會發現**，而且那半件工作 push 出去就是「腳本被刪卻沒有任何說明」。

- commit 前先 `git status --short`，第一欄有標記的就是已 staged（本 session 沒動過的也算）
- 只想提交特定檔案時用 `git commit <path>...`，不要 `git add <path> && git commit`
- 回報「工作區乾淨」之前，真的跑一次 `git status --short`

**GitHub 推送必須使用過濾腳本：**
- **push** → `git push origin main` (Forgejo，直接推)
- **push github** → `bash scripts/push_github.sh` (GitHub，過濾推送)
- **push both** → 先 `git push origin main`，再 `bash scripts/push_github.sh`
- **禁止** 直接執行 `git push github main`，會把 CLAUDE.md 等內部檔案推上去
- 過濾腳本要求工作區乾淨，有未 commit 的變更時先 `git stash --include-untracked`，推完再 `git stash pop`
- GitHub 的 history 與 origin 不同步是正常的（過濾 commit），不要 merge github/main 回 local

### 2. 更新追蹤
- 完成 BBN 待辦（PF-xx）時，**必須呼叫 `note_task_status(ref="PF-xx", status="completed")`**——
  只改標題成「[已解決]」、貼「已完成」標籤或追加內文，待辦狀態仍是 `planning`，
  `project_tasks` 會繼續把它列在待辦（2026-09-04 PF-239／PF-240 就是這樣漏掉的）
- 如果涉及架構變更，更新相關文件

---

## 文件目錄：docs/ 與 dev-notes/（2026-08-13 拆分）

**`docs/` 會推上 GitHub 公開，`dev-notes/` 不會。放錯目錄等於直接外流。**

`scripts/push_github.sh` 的 `EXCLUDE_DIRS` 只排除 `dev-notes`，
沒有第二道防線——沒有白名單、沒有內容掃描，目錄就是唯一的分界。

| 目錄 | 內容 | 讀者 |
|------|------|------|
| `docs/` | 使用者手冊、操作指南、作業流程、站內 help 素材 | 客戶、企業管理員、一般員工 |
| `dev-notes/` | 規格書、handoff、踩坑筆記、manifests、codex spec、架構設計 | 開發者、維護的 AI session |

任一項成立就寫進 `dev-notes/`：

- 提到內部 IP、主機名、`/opt/...` 路徑、埠號、資料庫名
- 描述「為什麼這樣寫」而不是「使用者怎麼操作」
- 是給下一個 session 的交接（`handoff_*`、`HANDOFF_*`）
- 是實作規格（`*_SPEC.md`）或模組清單（`manifests/`）
- 引用尚未發行或未定案的設計

**不確定就放 `dev-notes/`。** 事後從 dev-notes 搬進 docs 是零成本的，
反向則是已經外流了。

2026-08-13 之前寫在 `docs/` 的 54 項全數移入 `dev-notes/`，
只有使用者文件留下（當時是 `docs/help/` 與 `docs/guides/`，
後者已於 2026-08-14 併入 `docs/manual/`，見下方「使用者手冊有兩個出口」）。
其他 session 若記得舊路徑，一律以現況為準，不要搬回去。

### 要寫使用者文件時

**先讀 `dev-notes/DOCS_AUTHORING_SPEC.md`**，裡面有 frontmatter 規格
（`title` / `audience` / `requires` / `produces` / `covers` / `nav_menu` /
`visible_user_types` / `visible_roles` / `order`）、可用語法、建置驗收指令，
以及三處不可擅改的 `mkdocs.yml` 設定。

**兩個出口支援的 markdown 語法不一樣，而且不會報錯**（2026-08-17 實測）：
站內 `/help/` 只掛 `extra` + `sane_lists` + `admonition`
（`doc_catalog_service.py`），所以 **content tabs（`=== "標題"`）與
「縮排在 admonition 內的 fenced code」在站內完全不渲染**——`=== "標題"` 原樣印出、
指令擠成一行無法複製，但 MkDocs 站一切正常、`--strict` 也不會抓到。
**程式碼區塊一律寫在提示卡外面，不要用 tabs。**

新增或修改程式後，用這個確認有沒有文件跟著過期：

```bash
./venv-docs/bin/python scripts/docs_impact.py --docs docs --base origin/main
```

`--verify-covers` 只比對 **git 追蹤中**的檔案：新檔案 commit 前會被判成「失效的 covers」，
不是路徑寫錯，先 `git add` 再驗（2026-09-02 踩到）。

### 使用者手冊有兩個出口，同一批來源（2026-08-13 起）

`docs/manual/` 八章的 md 同時餵給兩個地方，**寫一次、兩邊生效**：

| 出口 | 特性 |
|---|---|
| 站內 `/help/`（Flask，`doc_catalog_service.py`） | **依登入帳號動態過濾**標題清單 |
| MkDocs 站（`mkdocs build`） | 靜態全集，每頁自動標「適用對象」 |

**站內可見性直接複用選單雙鑰匙**——frontmatter 寫
`nav_menu: <menu_items.code>`，該選單對此帳號可見則文件可見。
不要另建權限判定，也不要自己查 `MenuPermission` / `MenuRoleRequirement`。
跨階角色、企業間差異、模組合約授權全部自動生效（2026-08 實測：沒有弱點管理模組授權的
企業，其管理員看到的篇數比有授權的少 4 篇。當時的對照企業已刪除，要重現請自己找兩家
模組授權不同的企業比對）。

**但這個可見性不是保密機制，唯一目的是降噪**（用戶 2026-08-14 定調）：
`docs/` 全是操作說明、沒有機密，全部公開到 Internet 都可接受；
過濾只是為了**不讓使用者看見與自己無關的過多文件而產生困擾與誤解**。
因此判斷一頁該不該過濾，問的是「這個人看到會不會困惑」而非「有沒有資格知道」；
漏過濾一頁不是資安事件，不必回頭補強。MkDocs 站沒有權限機制、`docs/` 整包上
GitHub，**這兩件事是預期行為不是缺口**。完整條文見
`dev-notes/DOCS_AUTHORING_SPEC.md` 第八節開頭。
（真正的機密分界線是 `docs/` 對 `dev-notes/`，那條才是安全邊界。）

**`nav_menu` 綁錯 code 的症狀是「這頁誰都看不到」，而且不會報錯。**
新增頁面後用該功能的實際使用者身分開一次 `/help/` 確認標題有出現。

```bash
# 新增頁面後必做兩件事
NO_MKDOCS_2_WARNING=1 ./venv-docs/bin/mkdocs build --strict   # nav 漏加不會報錯但站上點不到
# 然後用對應身分登入 http://192.168.0.16:7000/beakplatform/help/ 確認標題出現
```

**站內單頁的網址是 `/help/manual/<doc_id>`，而 doc_id 本身以 `manual/` 開頭**，
所以正確網址長成雙層：`/beakplatform/help/manual/manual/03_org_setup/users`。
這不是筆誤，curl 驗證時少一層會拿到 404。

**頁面右上角 [?]（開對應手冊頁）由各頁模板自己宣告**，沒有自動反查：

```jinja
{% block help_doc %}manual/02_platform_admin/organizations{% endblock %}
```

doc_id 不存在時按鈕不顯示（`manual_doc_exists`）。語系變體檔 `<stem>.<lang>.md`
（`en` / `ja` / `zh-cn`）只採用 `title` 與內文，可見性與排序一律看 zh-TW 主檔，
缺該語系自動回退並提示。決策脈絡見知識庫 #5177，完整規格見
`dev-notes/DOCS_AUTHORING_SPEC.md`。

**`manual_doc_exists()` 只看檔案在不在、不看身分，但單頁路由 `manual_doc()` 會依身分
過濾並 404**。所以同一個模板服務兩種身分時，寫死單一 doc_id 會讓其中一種身分
「按鈕看得到、點下去 404」，必須在 block 裡分流（`login_failures.html` 是現成範例）：

```jinja
{% block help_doc %}{% if is_system_admin %}manual/02_platform_admin/login_failures_local{% else %}manual/05_security_ops/login_failures{% endif %}{% endblock %}
```

**[?] 只在有宣告的頁面出現**（2026-08-15 盤點：繼承 `layouts/base.html` 的頁面模板
122 個，已綁 9 個）。在別的功能頁找不到按鈕是預期狀態，不要去改 `base.html` 或
`doc_catalog_service` 找原因。另有一套**舊的**頁內說明（右下浮動鈕 + modal，
來源 `docs/help/<menu_code>.md`，會依 endpoint／path 反查）**2026-08-14 已在
`layouts/base.html` 註解停用**，程式與 `/help/page/` 路由都還在——去留見知識庫 #5181。

`/help/concepts` 是舊的平台概念說明（`org_admin.html`，限管理員），
掛在左側目錄最下方，不屬於 `docs/manual/`。

**手冊支援三層（章 → 節 → 頁），但只到三層**（2026-08-14 起，第一個節是
`docs/manual/05_security_ops/soc_planning/`）。節＝章底下的子目錄，
**一定要有 `index.md`**，否則整節不出現在目錄上、只留一行 warning。
節總覽與章總覽的動態內容規則相反：章總覽整段取代、節總覽保留原文再接清單。
完整規則（frontmatter、排序、頁間相對連結改寫、mermaid 兩個出口）
見 `dev-notes/DOCS_AUTHORING_SPEC.md` 第八節。

`docs/guides/` 已於 2026-08-14 併入 `docs/manual/`（commit `5a5da751`），
**現在 `docs/` 底下只剩 `manual/`（MkDocs 制度）與 `help/`（舊的頁內說明，另案處理）**。
原本那兩篇的現址：

| 舊路徑 | 現路徑 |
|---|---|
| `docs/guides/OD_WORKFLOW_VARIANTS.md` | `docs/manual/05_security_ops/soc_planning/workflow_variants.md` |
| `docs/guides/SOC_ROLE_DESIGN_GUIDE.md` | `docs/manual/05_security_ops/soc_planning/role_design.md` |

**`docs/help/` 的三個檔副檔名是 `.md`，但整份檔案就是一塊 YAML**
（frontmatter 結束在最後一行，Markdown 正文全塞在 `sections[].body`，
由 `help_service.py` 依 `audience` 過濾後組出畫面）。
它與 `docs/manual/` 的「YAML frontmatter + Markdown 正文」是兩種格式，
不要拿手冊的寫法去改它。

## BBN 白板已人機分離（2026-08-07，由 BeakBroodNest 端變更）

BeakBroodNest 把人類白板與 AI 白板拆成兩套，本專案的白板換了：

| 項目 | 舊 | 新 |
|---|---|---|
| BeakPlatform 專案白板 | canvas 29 / slug `tMU_fnXu` | **canvas 72 / slug `2a_YbjqA`** |
| 舊白板 | — | 改名 `👤 BeakPlatform`，清掉 `code` 與 `project_path`，成為使用者自用白板 |

- `project_tasks(cwd='/opt/BeakPlatform-dev')` 已自動指向新白板，**待辦、`PF-xx` 短代號、發號計數器全部照舊**，呼叫方式不用改
- **禁止使用記憶或舊文件裡的 slug `tMU_fnXu` 寫卡**，那會污染使用者的自用白板。一律用 `project_tasks` 當下回傳的 slug
- 使用者原本建的「claude建的卡片」群組（67 張）已整批搬到新白板，群組本身已刪除

### AI 可見性：`canvases.audience` 三態

`human`（使用者自用，AI 預設不讀）/ `ai`（AI 工作區）/ `shared`（雙方共用）。

- `note_search` 與 `note_overview` 預設排除「只出現在 `human` 白板上」的卡片；排除生效時回傳帶 `human_boards_hidden`
- 要查使用者白板內容：`note_search(..., include_human_boards=True)`
- **`shared` 只解除讀取隔離，不解除人機分離**：AI 讀得到，但使用者的卡仍不得改內容、不得搬位置、不得改白板名稱
- 判定**不掛 `owner`**。`atom.owner` 是建立者兼寫入權限閘門，不是受眾；而且 `source='ai'` 也不代表內容是 AI 產出 —— 使用者常把 Claude 的回答貼進自己白板當筆記
- 詳細規範在 `/opt/BeakBroodNest/CLAUDE.md` 與 `/opt/BeakBroodNest/docs/PROJECT_FACTS.md`，設計理由見 BBN 知識庫 atom 5082

---

## Manifest 優先的檔案定位（2026-08-06 放寬措辭）

**manifest 的用意是避免盲猜，不是禁止思考。**
動程式之前先查 manifest，是因為它已經把某個功能牽涉的 route／api／service／
model／template／js 列齊了——比自己從零搜尋更快也更不會漏。
（Codex-first 模式下，manifest 同時是「組 codex spec 檔案清單」的起點。）

### 流程

1. **收到任務** → 讀 `dev-notes/manifests/README.yaml` 找到目標 manifest
2. **讀 manifest** → 取得檔案清單，優先只讀這些檔案
3. **不足時可自行搜尋**（grep/glob），但**要在回覆裡說明搜了什麼、為什麼 manifest
   不夠**，並把找到的檔案補進對應 manifest——漏列會一直漏下去
4. 定位完成後把檔案清單與結構說明寫進 codex spec（Claude 直接動手的例外則自行修正）

**manifest 涵蓋不到的任務不必硬套**：全域性的檢查（例如「全專案還有幾處
`remote_addr`」）、文件整理、跨模組稽核，本來就沒有對應 manifest，直接搜尋即可。

### 已知落差（別以為 manifest 是完備的）

`workspace.html`、`page_template_service.py` 這類日常會改的檔案就不在
`mod-nocode-builder.yaml` 裡。**manifest 沒列 ≠ 不該讀**，只代表它待補。

### 這條仍是硬禁止

- **禁止** 修改 `security-core.yaml` 列出的安全核心檔案（除非用戶明確要求）

### 安全防雷

修改程式前必須查閱 `dev-notes/manifests/SECURITY_PITFALLS.md`，確認不踩以下坑：
- 租戶隔離（org_secure_code 過濾）
- 帳號狀態過濾（is_deleted + is_active）
- ResourceGateway 使用（**平台** API 且 model 已註冊才強制；模組 API 見 TENANT-02）
- 雙鑰匙選單安全（MenuPermission + MenuRoleRequirement）
- 時區處理（TZ-01 規範）

### 任務怎麼來（2026-08-06 起，取消工單格式）

用戶以口語交辦，或指向 BBN 待辦原子（`PF-xx`）。
**沒有固定工單格式**——本專案是有因果脈絡的中級以上專案，
規格與決策脈絡在 BBN 原子裡，填欄位式的工單只適合無因果關係的單一任務。
（原 `dev-notes/manifests/TICKET_TEMPLATE.md` 已刪除。）

---

## 當前開發階段

平台基礎建設與模組化標準已完成。目前處於**功能完善階段**。

待辦事項以 **BBN 待辦為主**（ref_code `PF-xx`）。Forgejo Issues 已全數移回 BBN，
若見殘留直接忽略，不需搬移或關閉（用戶會自行在 BBN 新增）。

**用戶只丟一個 `PF-xx` 時，取全文的最省路徑是
`note_task_update(ref="PF-xx")`（不帶任何欄位，只回狀態與 `atom_id`）→ `note_get(atom_id)`**
（2026-09-04 試誤）。`note_search("PF-xx")` 常回 0 筆——它只搜標題與內文，
ref_code 不在搜尋範圍，內文沒寫到自己代號的原子就搜不到；`project_tasks` 則已超過
工具輸出上限（約 15 萬字元）、整包落地成檔案才能用 python 依 `ref_code` 篩。
要列全部待辦才用 `project_tasks`。
架構與模組化標準詳見 `dev-notes/PLATFORM_MODULARIZATION_PLAN.md`。

---

## 安全標準 (必須遵守)

### AUTH-01: 全域認證攔截
- 所有請求經過 `before_request` 認證檢查
- 未登入訪問非白名單路由 → 401

### AUTH-02: 統一認證 Decorator
```python
@public_route          # 公開路由
@login_required        # 需要登入
@admin_required        # 需要企業管理員
@system_admin_required # 需要系統管理員
```

### AUTH-04: `must_change_password` 由攔截器強制（2026-09-04 PF-243 起）

`users.must_change_password` 為真的帳號，`auth_interceptor` 只放行
`/auth/change-password`、`/auth/logout`、`/auth/password-policy`（加上靜態檔與 `@public_route`）：
**頁面請求 302 到改密頁，API 請求 403 `{"error":"password_change_required","redirect":...}`**。
判定在 AUTH-03（原始管理員初始設定）之後、PageRoleGuard 之前；原始管理員走精靈時另放行精靈路徑。
2026-09-04 之前只有登入回應帶 redirect、伺服器端不攔，拿暫時密碼的人可以不改密照用。

三件會撞到的：

- **自動化以暫時密碼帳號登入後打任何 API 都是 403**，先 `POST /auth/change-password`（JSON 帶
  `current_password` / `new_password` / `confirm_password`，token 從改密頁的 hidden input 取，該頁沒有 meta token）
- 任何會設 `must_change_password=True` 的路徑（新帳號通知信、忘記密碼暫時密碼、管理員重設）從此真的會擋人；
  bpserv 出廠的 `enterprise@sys-...` 就是這種帳號，部署此版後首次登入會被強制改密
- 改密頁的「強制模式」（無取消連結）同時看 session flag 與 DB 旗標，quick-login 進來也會是強制模式

### PERM-01: 權限模型（4+1）
- 四層 user_type 硬界線（角色永不跨層）+ NoCode 公開資料隔離區
- 選單/頁面 = 雙鑰匙（Key1 user_type 層界 + Key2 角色，僅 EMPLOYEE/EXTERNAL 吃 Key2）；欄位 = EGRESS-01
- `menu_items.required_permission` 已退役不再影響選單；permission code 僅存在 API/資源層
- 定版文件：`dev-notes/PERMISSION_MODEL.md`（bypass 規則、功能開放多層 SOP、已知備忘）
- 權限管理 UI 統一入口：`/access/` 權限管理中心（功能授權/角色/帳號配角色/健檢；
  舊 `/permissions/`、`/roles/`、`/admin/account-roles/` 已退役，`/menu/` 只管選單結構）；
  規格 `dev-notes/ACCESS_CENTER_SPEC.md`
- **頁面路由一律自己掛身分 decorator；雙鑰匙是額外一層，不是唯一一層。**
  單頁專屬資料 API 掛 `@page_keys_required('<menu_code>')`

  > 2026-08-23 修訂。原文是「Phase B 起頁面路由**不掛**身分 decorator：
  > url 型選單路徑前綴即 PageRoleGuard 領地」。前半是無條件的祈使句、
  > 後半才有條件，於是被當成通則沿用——**這就是 PF-148 那批破口的來源**。
  > 實際上專案裡絕大多數頁面本來就有掛 decorator，只有新寫的模組頁照著這句話沒掛。
- **雙鑰匙領地的實際範圍，取決於選單的 `link_type`**（2026-08-23 實測，
  現況 route 型 30 個 / url 型 26 個）：
  - `link_type='url'` → 守整個**路徑前綴**，子頁一起守
  - `link_type='route'` 且 `link_target` 是 Flask **endpoint 名** →
    `PageRoleGuard._find_matching_menu_items()` 走**精確比對**，領地只有那一個 endpoint。
    同 blueprint 的詳細頁／編輯頁（例 `/spec-formulate/<sc>/edit`）
    **完全不進雙鑰匙判定，直接放行**

  所以「隔壁那條有守」不能當成這條也有守的理由。盤點與處置見待辦 **PF-148**
- 新增或改動路由後必須更新守門宣告表（見 **PERM-05**），漏掛守門會被測試抓到
- Phase D 元件級：動作按鈕一律包 `{% if can('<permission_code>') %}`（JS 用 `BkCaps.can()`），
  對應動作 API 掛 `@permission_required('<permission_code>')`（capability_service）；
  指引 `dev-notes/COMPONENT_VISIBILITY_GUIDE.md`（四層防線總表 + NoCode_Builder 消費規則）

### PERM-02: D2 元件級一律預設套用（2026-08-06 起，取消事前詢問）

**凡觸及「頁面模板、動作按鈕（增刪改查/簽核/撤銷等）、動作型 API」，
一律直接依 D2 標準實作，不必先問用戶。** 只有用戶明說「這次不要套」才不套。

- D2 標準 = 按鈕包 `can()`（JS 用 `BkCaps.can()`）、對應動作 API 掛
  `@permission_required`、code 沿用 API 層既有 permission code
  （詳見 `dev-notes/COMPONENT_VISIBILITY_GUIDE.md` §2.5）
- **前端隱藏不是防線**：API 沒掛檢查，F12 改一下照樣打得進去。兩件事必須成對
- 純資料修正、CSS、i18n、文件等不觸及按鈕/動作 API 的變更本來就不涉及 D2

**NoCode 的兩面都不得省**（用戶 2026-08-06 特別指明，因為 portal 對 Internet 開放）：

| 面 | 世界 | 等價機制 |
|---|---|---|
| 管理端（設計器、工作區、共用元件／樣板 API） | 平台 | D2 本身：`can()` + `@permission_required('nocode_builder.manage')` |
| portal 公開頁 | portal | widget／頁面 access_matrix + portal 權限碼制，判定失敗一律 404、解析不到一律 fail-closed |

**在 portal 側掛平台的 `@permission_required` 是無效的**（portal 帳號不在平台
`users` 表裡）——那邊的元件級控制走 access_matrix，規則見
`dev-notes/codex_spec/portal.md` 與 `dev-notes/PORTAL_ACCOUNT_SPEC.md`。

**修訂緣由**：原規定是「動工前先問用戶是否依 D2 進行」。D2 已是定版標準，
每次停下來問與「規格明確就直接執行」相衝突，且新程式碼沒有理由用舊模式。

### PERM-03: 角色制 API 不含 Key1，改守門前先讀這段（2026-08-23 起）

**`roles` 表沒有 `user_type` 欄位**（角色的另一個維度是**單位**：`user_role_assignments.unit_secure_code`，簽核授權 2026-09-05 PF-247 起以 (角色, 單位) 判定，見 `dev-notes/ROLE_UNIT_APPROVAL_DESIGN.md`），但 2026-09-01（PF-145 階段三之二）起
**指派時擋跨層**：層界維度用既有的 `roles.scope_type`——EXTERNAL 帳號只能拿
`scope_type='EXTERNAL'` 的角色，內部帳號不得拿外部範圍角色，雙向都擋。
唯一實作 `role_assignment_service.ensure_role_layer_compatible()`（access center
指派走它；部門三支 POST 端點另有 EMPLOYEE-only 守門）。**新增任何會寫
`user_role_assignments` 的路徑都要呼叫它**——直接 `UserRoleAssignment(...)` 建構
不會過這道檢查（既有的 org_admins／external_users／`_assign_default_role` 是
按 user_type 固定配對，安全來自結構不是檢查）。2026-09-01 之前任何角色都能
指派給任何身分（實測把 `FLOW_DESIGNER` 指派給 EXTERNAL 帳號成功、無警告）。

而 `/api/` 在 `PageRoleGuard.SKIP_PREFIXES` 內，**API 完全不吃雙鑰匙**，
只吃 decorator。兩者相加的後果：

| decorator | 有沒有 user_type 硬檢查 |
|---|---|
| `@admin_required` / `@system_admin_required` | **有**（`is_org_admin or is_system_admin`） |
| `@require_permission` / `@require_any_permission` | **沒有**，只查 permission code |
| `@page_keys_required('<menu_code>')` | **有**，Key1 + Key2 與所屬選單頁一致 |

**所以「把 `@admin_required` 的端點改成角色制」不是等價替換，是擴大攻擊面。**
EXTERNAL 帳號一旦拿到內部角色，頁面被 Key1 擋下（302 強制登出），
API 卻整組打得進去。2026-08-23 PF-142 第一版就踩到（`/api/units/departments`、
`/api/users` 換成模組端點），同 session 修掉。

**單一頁面專屬的資料／動作 API 一律掛 `@page_keys_required('<menu_code>')`**，
不要自己寫 user_type 判斷。跨頁共用的 GET 掛了會誤擋（例：表單中心的
`fc-data-loader.js` 也在用 `GET /api/form-workflow/categories`），要另外判斷。

已知未修的同類破口與系統性盤點在待辦 **PF-145**，架構分析見知識庫 atom 5246。
另有一個顯示層不一致：`_menu_tree.py::get_user_menu_tree` 的
`allowed = perm_governed_codes | module_injected_codes`，第二個來源
**不經 MenuPermission**，所以有模組 ACL 的 EXTERNAL 帳號**看得到**模組選單、
點進去才被擋（症狀是「看得到點不了」）。

### PERM-04: 模組 ACL 是 fail-closed，預設 ACL 由合約種入（2026-09-01 PF-145 階段三之一起）

`ModuleAccessService.check_user_access()` **零筆 ACL 記錄＝拒絕**
（此前是 fail-open「無 ACL＝不限制」，2026-09-01 前的文件與 atom 描述已過時）。
`@module_access_required(mod)`（`check_acl=True`）從此在任何企業都是實際防線；
ORG_ADMIN 仍由 decorator 層放行（在 ACL 檢查之前），所以清空 ACL 的效果是
「僅管理員可用」而不是鎖死。

配套的預設 ACL 種入，唯一實作 `ModuleAccessService.seed_org_module_acl()`：

- 各模組在 MODULE_INFO 宣告 `default_acl_roles`（皆為出廠角色）：
  `form_workflow=['FLOW_DESIGNER','FORM_DESIGNER']`、`nocode_builder=['SUBSYS_DESIGNER']`、
  `spec_formulate=['SPEC_DESIGNER']`、`vuln_lifecycle=['RISK_CONTROLLER']`、
  `open_defense=['SECURITY_STAFF']`
- 觸發點與模組預設角色相同：**合約建立**（`create_contract` →
  `ModuleRoleService.seed_contract_module_roles`）與 **`flask module sync`**。
  啟動時的自動同步**不含**這一步（與角色補種一樣只在 CLI sync 做）
- **該 (企業, 模組) 已有任何未刪除 ACL 記錄就整組跳過**——已設定的企業不覆蓋。
  推論：企業把某模組 ACL 全數刪除後，下次 `flask module sync` 會重新種回預設；
  要做到「僅管理員可用」得留至少一筆無人持有的目標，或改用角色成員管理
- 系統企業（SYSTEM）刻意不種（沿用 ModuleRoleService 的既有排除），
  其 ACL 現況是刻意配置
- 既有企業已由 `scripts/migrations/legacy/135_seed_module_acl_fail_closed.py` 補種
  （zero-record 規則，BELUGA 已設定的模組未動）

**終端用戶面不受影響**：表單中心等走 `check_acl=False`（僅驗合約），
fail-closed 只影響 `check_acl=True` 的設計類 API。已知的既有不一致
`GET /api/form-workflow/categories`（check_acl=True 但被表單中心的
fc-data-loader.js 使用，純員工 403、畫面靜默少了分類篩選）**維持原樣**，
現在所有企業行為一致（原本只有 BELUGA 如此），詳見知識庫 #5248。

完整分級與盤點清單見 `dev-notes/PF145_MODULE_API_KEY1_AUDIT.md`（其中
「ACL 是 fail-open」的描述是 2026-08-23 的歷史現況），重跑用
`venv/bin/python scripts/audit_module_api_gates.py`。

**反過來的症狀：`SYSTEM_ADMIN` 帳號打模組 API 常常 403，而原因是 ACL 不是合約**
（2026-08-31 實測）。系統企業**免合約**（`module_access_service.py:225-232` 的
`if org_sc == SYSTEM_ORG_CODE: return True`），但系統企業自己**有** ACL 記錄時，
`admin@system.local` 沒有那些角色就會被 `check_user_access()` 擋下。
本機實測 `GET /api/workflows/data/node-definitions` 對 SYSTEM_ADMIN 回 403，
同企業的 ORG_ADMIN 回 200，成因就是系統企業有 2 筆 `form_workflow` 的 ROLE 型 ACL。

**影響設計決策**：需要 SYSTEM_ADMIN 操作的管理頁與其 API **不能放在
`modules/*/api/` 底下**（`@module_access_required` 會擋），要放平台層。
平台層 import 模組 model 是既有做法（前例
`backend/app/defaults/api_key_request_defaults.py`）。

### PERM-05: 新增路由必須在守門宣告表登記（2026-08-23 起）

全平台每個 Flask endpoint 的守門責任記在
`backend/app/security/route_guard_table.yaml`（2026-08-23 建立時 831 筆，**數字會腐爛，
要現況跑 `--stats`**），由 `scripts/route_guard_inventory.py --update` 維護。

**新增或修改任何路由後必須跑一次 `--update`**，否則
`backend/tests/test_route_guard_table.py` 會紅（它同時驗「有沒有登記」與
「登記的守門與程式碼是否一致」）。表記的是**守門責任歸屬**，不是「誰進得來」——
後者隨企業合約與 ACL 資料而變，禁止寫進表。維護方式與複審流程見
`dev-notes/ROUTE_GUARD_TABLE_SPEC.md`。

### TENANT-01: 強制企業隔離
- 所有查詢包含 `org_secure_code` 過濾
- PostgreSQL RLS 作為最後防線

### TENANT-02: ResourceGateway 要求（2026-08-16 依實況改為分層）

**要求依「該 model 有沒有註冊進 gateway」而不同，不是一句「API 層禁止 `Model.query`」。**

| 範圍 | 要求 |
|---|---|
| 平台 API（`backend/app/api/`）且 model 已註冊 | **必須**走 `ResourceGateway` |
| 模組 API（`modules/*/api/`），model 未註冊 | 走「顯式 `org_secure_code` 過濾 ＋ 身分閘門 ＋ RLS」 |

**為什麼模組 API 不是走 gateway**：`backend/app/security/resource_gateway.py` 的
`MODEL_RESOURCE_TYPE_MAP` 只列平台 model（User / Organization / Role / MenuItem /
Contract 等），**一個模組 model 都沒有**；該檔註解寫明「未列入本表且未列入
`RBAC_EXEMPT_MODELS` 的 model 經過 gateway 會被 fail-closed 拒絕」。
也就是說模組 model 現在**根本走不進 gateway**，把呼叫端改成 gateway 只會拿到 403/500。

模組 API 要改走 gateway 的前置作業（缺一不可）：註冊 model 進
`MODEL_RESOURCE_TYPE_MAP` → 把 `{resource_type}:read/create/update/delete` 四個 code
加進 `backend/app/models/permission.py` 的 `DEFAULT_PERMISSIONS`（2026-09-04 PF-241 起
`tests/test_permission_defaults.py` 會逼你補：map 裡任一種缺四碼就紅）→
決定要不要進 `LIST_RBAC_ENFORCED_MODELS`。

**模組 API 的實質要求（這才是驗收時該查的）**：

- 每個查詢都以 `org_secure_code` 作為**實際 filter 條件**（不是只出現在附近）
- org 值只能來自 `current_user.org_secure_code` / `g.api_key.org_secure_code` /
  service account，**禁止從 request body 或 query string 取**——那是越權，
  是這條規範真正要防的東西
- 每支端點有身分閘門（`@page_keys_required` / `@permission_required` /
  `@admin_required` / `@service_account_required` / `@webhook_hmac_required` /
  `@module_access_required`），公開端點另須 rate limit
- 表有 RLS policy 當最後防線

**2026-08-16 盤點**：

| 位置 | `Model.query` | ResourceGateway |
|---|---|---|
| `backend/app/api` | 129 | 158 |
| `nocode_builder/api` | 24 | 128 |
| `form_workflow/api` | 237 | 2 |
| `open_defense/api` | 38 | 0 |
| `spec_formulate/api` | 37 | 0 |

`open_defense/api` 那 38 處**逐處查過**：全部以 org 為 filter 條件、org 值全來自
登入身分或 API key、每支端點都有閘門——**結構上沒走 gateway，實質隔離沒有破口**。
（脈絡見待辦 **PF-123**。數字會腐爛，要判斷現況自己數：
`grep -rn "\.query\b" --include=*.py modules/<模組>/api | wc -l`。）

**semgrep 規則 `beakplatform-direct-model-query-in-api` 的 paths 已同步限縮到
`backend/app/api/`**（2026-08-16，原本是 `**/api/*.py`）。限縮後實測：
平台 API 命中 **91** 條、模組 API **0** 條：

```bash
semgrep --config .semgrep/beakplatform-security.yaml --metrics=off --quiet --json \
  modules/open_defense/api backend/app/api
```

那 91 條是**平台 API 的既有技術債**（規則是 WARNING 級），基準與完整分類記在待辦
**PF-124**（含重新盤點的可執行腳本——數字會腐爛，不要相信寫死的 91）。

#### 新 API 與既有技術債怎麼處理（Ethan 2026-08-16 定調）

- **新寫的平台 API 一律走 `ResourceGateway`**，不要製造新的技術債。
  model 還沒註冊就先註冊（前置作業見上面），不是拿「既有的也沒走」當理由跳過
- **日後修改功能時遇到未走 gateway 的，直接改走 gateway，不必先問**。
  但這條授權**只涵蓋平台 API 且該 model 已註冊 `MODEL_RESOURCE_TYPE_MAP`** 的情況
  （2026-08-16 是 71 條 / 11 種：User、Role、Organization、SmtpConfig、
  RecipientGroup、TelegramConfig、UserRoleAssignment、UserNumberingRule、
  OrganizationalUnit、MenuItem、Contract）
- **未註冊的 model（當時 20 條 / 12 種）不在授權範圍**：註冊 model 會連動
  permission code 與 `LIST_RBAC_ENFORCED_MODELS`，是要單獨評估的變更
- **模組 API 一律不改**（會被 fail-closed 拒絕，見本節上半）

#### 【硬禁止】不要為了改一支 API 而去動註冊表

**禁止**在「順手改成 gateway」的過程中修改
`MODEL_RESOURCE_TYPE_MAP`、`LIST_RBAC_ENFORCED_MODELS`、`RBAC_EXEMPT_MODELS`。
這三張表是**全平台生效**的，改它們不是改一支 API，是改所有走 gateway 的路徑。
要動就當成獨立任務、單獨評估、單獨驗收。

未註冊的 model（2026-08-16 是 12 種：LookupItem、EgressFieldPolicy、
BroadcastAcknowledgment、EgressTierThreshold、StoreItem、StoreInstallation、
AuditLog、SystemSetting、PasswordResetToken、Conglomerate、MenuRoleRequirement、NRule）
**維持現狀就是正確的**，不是待辦。

#### 三層雷（前兩層會讓所有身分都進不去，含管理員）

**雷一：未註冊的 model 走 gateway 會直接被拒。**
`_check_collection_permission()` 第 5 條：有用戶上下文即 fail-closed 拒絕
（`Unregistered model for ResourceGateway list RBAC`）；`get()` 路徑則在
`_check_view_permission()` 因 `resource_type is None` 拋 `PermissionDeniedError`。
所以把未註冊 model 的查詢「順手改成 gateway」，**當場就壞**。

**雷二：註冊了 model 卻沒建 permission code，連 ORG_ADMIN 與 SYSTEM_ADMIN 都被擋。**
這是雷一的直覺解法（「那我把它註冊起來就好了」）踩下去的地方。
`PermissionService.check()` 的順序是**先查 permission 定義、查不到就 return False**
（`permission_service.py:121-125`），**ORG_ADMIN 的 bypass 在下一步、根本輪不到**；
SYSTEM_ADMIN 依 SEC-02 早已不享特權。2026-08-16 實測
（`/opt/tmp/verify/20260816-tenant02-permission-chain.log`）：

```
check("lookup_item:read")  ORG_ADMIN -> allowed=False (Unknown permission)
                           SYSTEM_ADMIN -> allowed=False (Unknown permission)
check("user:read")         ORG_ADMIN -> allowed=True   SYSTEM_ADMIN -> allowed=True
```

症狀是**整個端點對每一種身分都 403**，而錯誤訊息只說「沒有權限」，
看起來像權限設定錯誤而不像程式改壞。

**同一個雷的另一種踩法：定義只種在 dev、沒進出廠定義**（2026-09-04 PF-241）。
`MODEL_RESOURCE_TYPE_MAP` 裡 17 種（work_schedule、job_level、smtp_config、
user_role_assignment 等）的 code 是 2026-07 用 legacy migration 075 種進 dev 的，
`DEFAULT_PERMISSIONS` 一直沒跟上，fresh install（bpserv）的基本班表、職等職稱、
代理授權、SMTP／Telegram 設定組、角色指派這些管理頁對 ORG_ADMIN 也 403，
dev 上永遠重現不出來。**驗新 permission code 一律用拋棄式庫走一次
`INIT_DB_YES=1 DB_NAME=freshcheck ADMIN_INITIAL_PASSWORD=<pw> bash scripts/init_database.sh`
再比對 code 集合**，不要只看 dev。

**雷三：已註冊 model 改走 gateway 也不是等價替換。**
`list()` / `filter()` 對 `LIST_RBAC_ENFORCED_MODELS` 內的 model 自動檢查
`{resource_type}:read`，而可直接改的那 11 種**全部都在那份清單裡**。
`User.query.filter_by(...)` → `ResourceGateway.filter(User, ...)` 之後，
該端點的呼叫者需要持有 `user:read`——EMPLOYEE／EXTERNAL 可達的端點會 403。
呼叫端本來就不該持有該權限時，用 `check_permission=False` 並在該行寫明理由。

#### 改完必須實測（單元測試抓不到）

測試庫是 `db.create_all()` 建的空表。2026-09-06（PF-34）起 `admin_client` 依賴的
`rbac_seed` fixture 會種入**出廠權限定義**（`DEFAULT_PERMISSIONS`），ORG_ADMIN 的 bypass
在測試裡走得通；但**沒有角色與 `user_role_assignments`**，EMPLOYEE／EXTERNAL 的權限鏈
在測試裡一律是「User has no roles」，改壞了不會多紅一條。
**一定要用該端點的實際使用者身分實測**：

```bash
BASE=http://192.168.0.16:7000/beakplatform
curl -s -c cj.txt -X POST "$BASE/dev/quick-login" -H 'Content-Type: application/json' \
  -d '{"user_id":"<該身分的 user secure_code>"}'
curl -s -b cj.txt -o /dev/null -w '%{http_code}\n' "$BASE/api/<改過的端點>"
```

端點若有多種身分可達（例如 ORG_ADMIN 與 EMPLOYEE 都看得到的清單），**每種都要測**。

**寫給未來 session**：看到模組 API 用 `Model.query` **不要當成缺陷回報、不要建工單、
也不要順手改**。要確認的是上面那四項實質要求。真要把模組納入 gateway 是跨 5 個模組、
300+ 處的獨立工程，不該由「發現某支 API 沒走 gateway」觸發。

### URL-01: 對外識別碼一律用 secure_code

- **禁止**在 URL、API 路徑與回應中出現自增 ID（`users/12` 這種）
- 動態組 SQL 一律走參數化；NoCode 側動態表名／欄名必須先過白名單比對

### URL-02: 給使用者看的對外網址一律走 `external_url()`（2026-08-23 起）

**禁止**用 `url_for(..., _external=True)` 或 `request.host_url` 組「要給使用者點、
複製或寄出去」的網址。唯一實作是 `backend/app/utils/external_url.py`：

```python
from app.utils.external_url import build_external_url   # Python
{{ external_url(url_for('auth.org_login', domain_name=x)) }}   {# Jinja2 global #}
```

值來自系統設定 `system_base_url`（完整 base URL，例 `http://192.168.0.16:7000`，
不含尾斜線與 `/beakplatform` 前綴），在 `/hostconfig/server-settings` 的
「系統對外網址」設定。**未設定一律回 `None`，呼叫端要顯示「尚未設定」而不是
退回猜一個網址**——錯網址比沒網址更難查（PF-143 的誤判就是這樣來的）。

**為什麼不能用 request 推導**：nginx 的 `proxy_set_header Host $host` 不帶埠號，
所以 `_external=True` 產出的是 `http://192.168.0.16/...`（缺 `:7000`，點了連不上）；
正式環境走 Cloudflare 時 `request.host` 又是內部反代位址。兩條路都拿不到對外網址。

`url_for()` 不加 `_external=True` 時**已含 `script_root`**，`build_external_url()`
內部會判斷避免疊成 `/beakplatform/beakplatform/...`，呼叫端不必自己處理。

**順帶一提平台跑在 http，`navigator.clipboard` 是 `undefined`**（非安全上下文）。
複製功能一律用 `Utils.copyToClipboard()`（`backend/app/static/js/app.js`，
已含 textarea + `execCommand` fallback），**不要自己呼叫
`navigator.clipboard.writeText`**——那在本機一律失敗。
`api-keys.js::copySecret()` 就是這樣壞的，尚未修。

**但 `app.js` 不在 `layouts/base.html`**（2026-08-28 踩到，本檔原本寫「已全域載入」
是錯的）。它由需要的頁面各自 `<script>` 引入，2026-08-28 的實況是三頁：
`personal_settings.html`、`organizations/list.html`、`hostconfig/data_maintenance.html`。
**在別的頁面用 `Utils` 會噴 `Utils is not defined`**，而且症狀藏在 Alpine 裡——
畫面正常、按鈕點下去沒反應，只有 console 有一行
`Alpine Expression Error: Utils is not defined`。用到就記得在該頁的
`{% block scripts %}` 補一行載入。

### DATA-01: 帳號查詢必須過濾刪除與停用
- **所有查詢用戶/帳號的地方**，必須同時過濾 `is_deleted=False` 和 `is_active=True`
- 包含但不限於：用戶列表、組織樹、簽核人選擇、角色成員解析、部門成員解析
- 關聯查詢（如透過角色/部門取用戶）需 JOIN User 表確認帳號狀態

### DATA-02: 新增「建立帳號」或「重新啟用帳號」的路徑必須掛人數上限（2026-08-30 PF-174 起）

`Organization.user_limit` 從 2026-08-30 起**真的會擋**（此前寫好但沒人呼叫）。
唯一實作是 `backend/app/models/organization.py`：

```python
DEFAULT_ORG_USER_LIMIT = 50                              # 全平台唯一預設值來源
USER_LIMIT_COUNTED_USER_TYPES = ('EMPLOYEE', 'EXTERNAL')  # 只算這兩種
counts_toward_user_limit(user_type) -> bool
org.can_create_user(user_type=None) -> bool               # 不計入的身分一律回 True
org.get_active_user_count()                               # is_active ＋未刪除＋非服務帳號
```

**計數刻意排除三種帳號，三個理由各不相同**：

| 排除 | 理由 |
|---|---|
| `ORG_ADMIN` | 綁定一個企業成員帳號，計入等於同一個人算兩次 |
| `SYSTEM_ADMIN` | 平台級身分，不屬企業人事編制 |
| `is_service_account=True` | NoCode portal 公用送件帳號無法登入（`password_hash='!nologin'`），且 `/external-users` 列表刻意過濾它（`web/external_users.py:158`）——計入會佔掉一個**使用者看不到也管不到**的名額 |

**新增任何會建立或重新啟用帳號的路徑時，一律掛檢查**（現有八處：
`web/users.py` 的 create／import／toggle_status／edit_user、
`web/external_users.py` 的 create／toggle_status、`api/users.py` 的 create／update）。
漏掛不會報錯，症狀是那條路徑成為繞過上限的後門。
**`web/org_admins.py` 與 `web/sys_accounts.py` 刻意不掛**——它們建的身分不計入，
擋了會變成「不計入卻擋得住」，而且 `initial_setup()` 是企業沒有管理員時的救援路徑。

三件猜不到的：

- **檢查要放在「消耗掉不可逆資源」之前**。外部廠商那支若放在
  `NumberingService.get_next_number(consume=True)` 之後，被擋的請求會白白吃掉一個編號
- **批次匯入是整批拒絕**（Ethan 定案）：跑完整份 CSV 算出實際會建立的筆數，
  超限就 `rollback()` 一筆不建。**不要提早 break**——`_import_single_user()` 內的
  `flush()` 讓後續列的重複帳號檢查仍然正確，提早跳出會算錯筆數
- **既有企業沒有 backfill**，所以本機 BELUGA 是 `6 / 5` 的超限狀態（刻意保留，
  現成的「既有企業撞牆」測試案例）。降低上限時也不檢查目前使用量——
  既有帳號照常使用，只有會增加人數的動作被擋

決策脈絡與完整驗收記錄見 BBN 待辦 **PF-174**（`note_search("PF-174")`）。

### EGRESS-01: 資料出口政策

設有出口政策的資源，欄位依 (角色, 語境) 呈現 clear / masked / hidden。
規格：`dev-notes/EGRESS_POLICY_SPEC.md`，防雷：`dev-notes/manifests/SECURITY_PITFALLS.md` 第 9 節。

- API 序列化：to_dict 之後過 `egress_service.apply(resource, context, items)`
- 後端模板：`egress_value()` / `egress_visibility()` template globals + `BkEgress.bind()`
- **禁止** list 回應內嵌預載 detail 資料（master-detail 必須分開請求）
- **禁止** 繞過 `POST /api/egress/reveal` 另開端點回傳 masked 欄位真值

### MENU-01: 選單項目新增規範

**新增 menu_items 記錄時，必須遵守以下規則：**

**link_type 有效值**（`_resolve_link()` in `menu_service.py` 只認以下值）：

| link_type | link_target 格式 | 說明 |
|-----------|-----------------|------|
| `url` | `/security/alert-broadcasts/` | 直接 URL 路徑（最常用） |
| `route` | `admin.settings` 或 `/path/` | Flask endpoint 名稱，或以 `/` 開頭的路徑 |
| `page` | `page_secure_code` | 動態頁面，自動加 `/p/` 前綴 |
| `divider` | （空） | 分隔線 |
| `header` | （空） | 群組標題 |

**其他 link_type 值（如 `path`）會導致 href 變成 `#`，選單點了沒反應。**

**參考既有同類選單**：新增前先查 DB 中同層級或同功能的選單用什麼 link_type，照著用。
```sql
SELECT code, link_type, link_target FROM menu_items WHERE parent_secure_code = '目標父選單SC';
```

**禁止事項**：
- **禁止** 為了「選單無法點擊」而修改 `menu_service.py` 的 `_resolve_link()` -- 問題一定出在 DB 的 link_type 設定
- **禁止** 為了選單顯示問題而修改權限控制邏輯（`auth_interceptor`、`page_permission_service`、`page_role_guard`）-- 這些是安全核心，選單顯示異常的根因是 DB 資料設定錯誤

**`menu_items` 與 Key1 是全域單一筆，只有 Key2 是 per-org**（2026-08-23 踩到）：

| 東西 | 是否 per-org |
|---|---|
| `menu_items`（含模組選單） | **否**，全平台一筆，`org_secure_code` 指向系統企業 |
| Key1 `menu_permissions` | **否**，掛在 menu 的 secure_code 上 |
| Key2 `menu_role_requirements` | **是**，帶 `org_secure_code`，各企業獨立 |

所以查 Key2 現況**一定要 `GROUP BY` 企業**，不分組會把各企業的角色 `string_agg`
成一串，看不出「只有某一家缺一筆」。`form_workflow.center` 的出廠預設漏了
`EXTERNAL_USERS`（新企業的廠商進不了表單中心、被 302 強制登出且不報錯）
就是這樣才被發現的，修法見 `scripts/migrations/legacy/113_form_center_menu_external_users.py`。

**改選單一定是「DB + 出廠預設」兩件事**（2026-08-13 踩到）：
`backend/app/defaults/menu_defaults.py` 的 `CORE_MENUS` 與 `MENU_ROLE_DEFAULTS`
是**新建企業時的出廠值**。只寫 migration 改 DB，現有企業會對、
**新建的企業會長回舊的樣子**，而且不會有任何錯誤訊息。

- `CORE_MENUS` 的 `_user_types_override` 不寫時走該檔的預設推導，
  要開放給多個 user_type 時**明寫**，不要賭預設值
- `MENU_ROLE_DEFAULTS` 是雙鑰匙 Key2 的出廠值，**禁止列入 header 型 code**
  （結構元素不吃 Key2，種了只會產生永不被讀取的死資料）
- 遷移腳本沿用既有 `menu_items.secure_code` 原地改 `code`，
  可省下重建 `menu_permissions` / `menu_role_requirements`；
  逐企業補 `menu_role_requirements` 時記得 **`roles.code` 跨企業不唯一**，
  要用該企業自己的 role secure_code
- 範例：`scripts/migrations/legacy/099_merge_platform_help_menu.py`（含 `--dry-run`，冪等）

**模組選單「刪掉定義」不等於選單會消失**（2026-08-17 踩到）：
`flask module sync` 只做 create / update / unchanged
（`backend/app/services/module_menu_service.py` 沒有任何刪除路徑），
所以從 `MODULE_INFO['menu_items']` 拿掉一項之後，既有 DB 記錄照樣留著、
選單照樣顯示。**要另寫 migration 把該 `code` 的 `menu_items` 設 `is_deleted`**
（範例：`scripts/migrations/legacy/104_retire_od_intake_keys_menu.py`）。

**連帶要檢查 `docs/manual/**` 有沒有頁面 `nav_menu` 綁著那個 code**——
站內 `/help/` 的可見性只看該 code 是否可見，綁到已刪除的 code 會讓整頁
**對所有人消失且不報任何錯**。

### FILE-01: 檔案上傳/下載統一規範

**所有檔案操作必須透過 `file_service`，禁止自行實作上傳/下載邏輯。**

- 加密由 `storage_type` 自動決定（`form_attachment` / `subsystem_file` 走 AES-256-GCM），
  程式不需手動呼叫加密函式
- 前端一律用 `BkFileAttachment` 元件，不要自己寫上傳 API 呼叫
- **禁止**繞過 `file_service` 直接讀寫 uploads/ 或 encrypted_storage/
- **禁止**手動呼叫 `crypto/engine.py`
- **禁止**將 `ENCRYPTION_MASTER_KEY` 硬編碼或寫入版控

完整 API 用法、context_type 對應表、金鑰架構：**`dev-notes/FILE_SERVICE.md`**

**回送檔案內容時 `Content-Type` 一律用 `file_service.get_serve_mime(record)`**
（副檔名 → MIME 白名單），**禁止使用 `platform_files.mime_type`**——
該欄位存的是上傳時 multipart 宣告的值，**完全由上傳者控制**。
2026-08-05 因此修掉一個儲存型 XSS：傳 `.png` 卻宣告 `Content-Type: text/html`
（或直接傳 `.svg`），serve 端原樣回送，JS 就在平台同源執行。
`nosniff` 擋不住（型別是攻擊者明確宣告的，nosniff 反而確保照他說的渲染），
全域 CSP 的 `unsafe-inline` 也擋不住。修補配套三件，缺一不可：

```python
mimetype=file_service.get_serve_mime(record)          # 白名單推導
g._bk_strict_file_csp = True                          # → default-src 'none'; sandbox
if ext in file_service.FORCE_DOWNLOAD_EXT:            # 目前是 {'svg'}
    headers['Content-Disposition'] = _make_cd_header(record.original_name)
```

`<img src>` 不理會 `Content-Disposition`，所以 SVG 加 attachment **不會**弄壞
logo／背景（已實測）。詳見知識庫 #5048。

**通用上傳端點只收兩種 context_type**（PF-43，2026-08-05 起）：
`/api/files/upload` 只接受 `file_service.GENERIC_UPLOAD_CONTEXT_TYPES`
＝ `{'form_attachment', 'subsystem_file'}`，其餘一律 400。
在此之前它只有 `@login_required`、不檢查 context_type 與身分的關係，
任何登入帳號（含 EXTERNAL）都能寫入 `org_logo` / `nc_background` /
`wf_background` 這三個 `PUBLIC_CONTEXT_TYPES`（匿名可讀、**無租戶隔離**）。
**新增 context_type 時要一併決定它走哪個端點**——通用端點只放通用附件，
其餘各自建專屬端點並自行授權（`org_logo`→`/api/enterprise-settings/logo`、
`nc_background`→`/api/nocode-builder/backgrounds/upload`、
`wf_background`→`/api/form-workflow/backgrounds/upload`、
`portal_file`→`/api/nocode-builder/sub-systems/<ss>/portal-files`）。
未知 context_type 一律拒絕不只是授權問題：`CONTEXT_ALLOWED_EXT.get()` 對未知鍵回
`None`，副檔名白名單會**整個被跳過**。

**PF-43 的另一半尚未做**：讀取端 `/api/files/<sc>/serve` 仍是無語境的全域路徑，
`PUBLIC_CONTEXT_TYPES` 的檔案在任何子系統路徑下都取得到。

### NET-01: 來源 IP 一律走 `get_client_ip()`（2026-08-05 起）

**禁止直接讀 `request.remote_addr`、`X-Forwarded-For`、`CF-Connecting-IP`，
也禁止用 flask_limiter 的 `get_remote_address`。**
唯一實作是 `backend/app/security/client_ip.py`：

```python
from app.security.client_ip import get_client_ip    # 一般用途，可能回 None
from app.security.client_ip import client_ip_key    # 限流 key_func 用，保證回字串
```

平台有兩條互斥的信任鏈（**這是環境事實，猜不到**）：

```
LAN 直連    訪客 → nginx 192.168.0.16:7000 → Flask
Cloudflare  訪客 → CF edge → cloudflared(.16) → nginx 192.168.0.20:8080
                  → nginx 192.168.0.16:7000 → Flask
```

`create_app()` 掛的 `ProxyFix(x_for=1)` 取 XFF 最右一筆＝「直連我方 nginx 的對象」：
LAN 路徑得到真實訪客 IP，**Cloudflare 路徑恆為 `192.168.0.20`**，真實訪客 IP
只存在於 `CF-Connecting-IP`。因此信任邊界看直連對象：`remote_addr` 落在
`TRUSTED_PROXY_IPS`（config.py，預設 `192.168.0.20`，env 可覆寫）時才採信該 header，
否則一律用 `remote_addr` —— 直連者自帶 header 偽造不了。

**為什麼這條非寫不可**：此前全專案缺 ProxyFix，`remote_addr` 恆為 `127.0.0.1`，
造成三個機制**靜默失效且不報錯**：`dev.internal_network_only` 內網判定恆真、
未認證限流全站共用單一 bucket、`api_key_service.check_source_ip()` 的來源 IP
限制形同虛設。改用 `remote_addr` 而不處理 CF 分支則會走向另一個極端：
所有外網訪客塌縮成 `192.168.0.20` 一個身分。

**回傳 None 的處理**：`get_client_ip()` 在無 request 語境會回 `None`，
呼叫點若假設是字串（字串格式化、DB 非空欄位、比對）必須自己給 fallback；
限流 key_func 一律用 `client_ip_key()`（保證回字串）。

**哪些該改**：只要該值代表「請求從哪裡來」就要改——稽核 `ip_address=`／
`source_ip=`、log 訊息裡的來源、任何 IP 比對或分桶。測試檔裡刻意造的
`REMOTE_ADDR` environ 不算。

**本機模擬兩條路徑驗收**（不必真的走 Cloudflare，本 session 驗證過可用）：

```python
from app import create_app
from app.security.client_ip import get_client_ip
app = create_app('development')
# 經 CF：remote_addr 為可信代理，採信 header
with app.test_request_context('/', environ_base={'REMOTE_ADDR': '192.168.0.20'},
                              headers={'CF-Connecting-IP': '203.0.113.7'}):
    assert get_client_ip() == '203.0.113.7'
# 非可信代理送同一個 header：必須被忽略
with app.test_request_context('/', environ_base={'REMOTE_ADDR': '192.168.0.50'},
                              headers={'CF-Connecting-IP': '203.0.113.7'}):
    assert get_client_ip() == '192.168.0.50'
```

記錄用途的 `remote_addr` 尚未全面收斂，見待辦 **PF-36**（內含完整 grep 指令與驗收步驟）。
**不要相信任何寫死的「還剩 N 處」**——動工前自己數：

```bash
grep -rn "remote_addr" --include=*.py backend/app modules | grep -v client_ip.py
```

（`config.py` / `__init__.py` 的 ProxyFix 設定與 `client_ip.py` 本身不算待改項。）

### 開發工具 `/dev/*` 的三層防護（別再重查一次）

`/dev/quick-login` 這類工具的「僅限內網」由 iptables → nginx → `dev.py::internal_network_only`
三層構成，**真正在管來源 IP 的是 iptables**。現行白名單、新增裝置的指令、
「連線逾時而非 403」的判別方式，全部寫在全域
`~/.claude/knowledge_base/configurations/system_configs/network_architecture.md`
的 Layer 1 段——**這是系統層事實，不要在本檔另存一份會漂移的副本**。

---

## 模組靜態檔案規範

模組的 JS/CSS/圖片等靜態資源由 `module_loader.py` 自動註冊 serve。

**目錄結構：**
```
modules/<module_name>/static/modules/<module_name>/
  ├── js/           # JavaScript
  ├── css/          # 樣式表
  └── icons/        # 圖示
```

**存取 URL：** `/static/modules/<module_name>/js/xxx.js`

**禁止** 將模組靜態檔案複製到 `backend/app/static/`。
`backend/app/static/` 只放平台級資源（themes.css、vendor/、auth.js 等）。
模組資源一律放在 `modules/<name>/static/` 下，由 module_loader 自動 serve。

### VENDOR-01: 換 vendor 套件檔案時要同步版本標記（2026-08-14 起）

`/api/system-settings/package-versions` 顯示的 vendor 版本是**從 minified 檔內容
用正則抓的**，抓不準是常態，而且**錯了不會報錯**：

- GridStack 13.0.2 的 dist 內仍寫 `GDRev="13.0.1"`（上游打包漏更新）
  → 頁面恆顯示「可更新」，升幾次都一樣
- mermaid 實際是 10.9.1，卻被抓到內嵌依賴的 `version="3.0.9"`
  → 顯示的版本與事實無關，也就查不出它其實落後一個 major

所以**換檔案後一律同步更新版本標記**（`_ss_packages.py` 會優先採用）：

| 套件型態 | 標記位置 |
|---|---|
| 目錄型（`vendor/gridstack/`） | `vendor/<套件>/VERSION`，第一行 `X.Y.Z`（後面可接註記） |
| 單檔型（`vendor/mermaid.min.js`） | `vendor/versions.json` 的 `{"<key>": "X.Y.Z"}` |

- key 是目錄名／檔名第一個 `.` 之前的小寫（`_get_vendor_key()`）
- 開頭不是 `X.Y.Z` 一律忽略、退回內容偵測（抓錯版本比抓不到更糟）；
  沒列的套件行為完全不變（ace、bootstrap、alpine 等抓得準的不必列）
- 新增 vendor 套件時記得一併加進 `VENDOR_META`（npm 名稱），否則查不到最新版，
  狀態會一直停在 `checking`

---

## 前端開發規範

### FRONT-01: JS/CSS 分離原則

**HTML 模板中禁止大量內嵌 JS/CSS。**

| 類型 | 規範 |
|------|------|
| CSS | 抽為 `.css` 靜態檔 |
| JS 邏輯 | 抽為 `.js` 靜態檔 |
| 膠水碼（初始化、Jinja2 變數注入） | 可留在 HTML，不超過 30 行 |

平台層：`backend/app/static/js|css/`；模組層：`modules/<name>/static/modules/<name>/js|css/`

需要把 Jinja2 變數帶進 JS 時用 window bridge（`window.__PAGE_CONFIG = {...}`）。
JS 與 Jinja2 深度交織無法乾淨分離時，才保留 `{% include "_xxx_methods.html" %}` partial。

抽離模式範例與完整說明：**`dev-notes/codex_spec/frontend.md`**


### FRONT-02: HTML 模板行數上限

- 單一 HTML 模板不應超過 **500 行**（含 HTML + 內嵌 JS/CSS）
- 超過時必須拆分：CSS → 靜態檔、模態框 → `_*_modals.html`、JS → `.js` 靜態檔或 `_*_methods.html` partial
- 參考已完成的拆分模式：`form_center.html`、`departments.html`、`form_designer.html`

### FRONT-03: Node Type 定義禁止硬編碼

- **禁止**在 API 程式碼中硬編碼 node type 定義
- `workflow_node_definitions` DB 表是 **single source of truth**
- API 透過 `WorkflowNodeDefinition` ORM Model 查詢
- 新增 node type 流程見 `dev-notes/archive/NODE_TYPE_NORMALIZATION_PLAN.md`

### FRONT-04: Code 欄位自動建議規範

需要唯一識別碼的建立表單，統一 UX：輸入名稱 → debounce 500ms → `POST /api/code/generate`
取得建議值當 placeholder → 手動輸入時 `POST /api/code/validate` 即時驗證 →
留空提交時後端採用建議值。不強制大小寫轉換。

前端引入 `/static/js/code-input.js` 的 `codeInputMixin(entityType)`，
標準區塊 HTML 用 `{% include "partials/_code_input.html" %}`。

### FRONT-05 / FRONT-06 / FRONT-08: 前端框架陷阱

以下三條寫錯會造成排版錯亂或功能靜默失效，**派工給 codex 時必須貼進 prompt**
（完整說明與範例在 `dev-notes/codex_spec/frontend.md`）：

- **FRONT-05**：CSS 全寬規則必須排除 radio/checkbox
  （`input:not([type="radio"]):not([type="checkbox"])`），否則同列文字被擠成直排
- **FRONT-06**：有 `x-show` 的元素禁止 inline style 設 `display`
  （x-show 還原時會清掉，佈局遺失）
- **FRONT-08**：select 綁動態 `x-for` options 時，option 必須加
  `:selected="<值> === <狀態>"`，否則初次渲染顯示第一個選項
  （症狀：一進頁面顯示錯的，手動改一次就正常，極易漏看）


### FRONT-07: 模組 CSS 命名與排版規範

**平台未載入 Bootstrap。** 全域 CSS 只有 `common.css` + `base-layout.css`，
提供 `.btn` / `.data-table` / `.form-control` / `.modal-overlay`，**沒有 Grid 系統**。

- 禁止 `row` / `col-md-*` / `card` / `table-sm` / `mb-3` / `d-flex` 等 Bootstrap class
  （寫了完全無效果，排版會全部擠在一起）
- 排版用 CSS Grid / Flexbox；模組 class 加前綴（`wks-`、`ird-`、`fw-`、`pir-`）

**CSS 變數白名單**（只能用這些，禁止自創）——權威來源是
`backend/app/static/css/common.css` 的 `:root`，2026-08-14 校對後的完整清單：

```
主色    --color-primary  --color-primary-hover  --color-primary-light
語意色  --color-danger   --color-danger-hover   --color-danger-light
        --color-success  --color-success-hover  --color-success-light
        --color-warning  --color-warning-hover  --color-warning-light
        --color-info     --color-info-hover     --color-info-light
文字    --color-text  --color-text-secondary  --color-text-muted
背景    --color-bg  --color-bg-white  --color-bg-light  --color-bg-header
邊框    --color-border  --color-border-light
其他    --border-radius  --border-radius-lg
        --font-size-base  --font-size-sm  --font-size-xs
```

（2026-08-14 前本檔只列 8 個，漏掉語意色與尺寸變數——但那些在 15 個既有 CSS
檔裡早就在用。**看到舊版 8 個清單的 codex spec 或文件一律以本表為準**。）

**這條管的是「引用全站色票」，不禁止區域變數**：在自己的 scope 定義、
自己使用的版面變數（如 `platform-manual.css` 頂端的 `--manual-shell-max`）
沒有 fallback 風險，而且能把散落的尺寸集中成一處。判別方式：
**別人定義的（`common.css` 的 `:root`）必須照白名單，自己定義自己用的可以。**

自創 `--text-primary`、`--surface-color` 這類不存在的變數時，CSS fallback 值會生效，
曾造成整頁深色 fallback、白底白字。**派工給 codex/agent 時必須在 prompt 明列此白名單。**

版型範例：`modules/form_workflow/static/modules/form_workflow/css/fw-dashboard.css`


### FRONT-09: D2 的 `BkCaps.can()` 需要頁面注入 `__PAGE_CAPS`

`capability.js` 的 `BkCaps.can(code)` 讀 `window.__PAGE_CAPS`，
**該變數由各頁面自行注入，沒有全域預設值**。漏注入時 `can()` 恆為 `false`，
症狀是**按鈕點下去完全沒反應、console 也不報錯**。

```python
from app.services.capability_service import build_caps
return render_template('...', page_caps=build_caps(['module.permission_code']))
```
```html
<script>window.__PAGE_CAPS = {{ page_caps | default({}) | tojson }};</script>
```

模板層的 `{% if can('...') %}` 走後端 Jinja2 global，**與此無關**——
所以會出現「按鈕有渲染出來但點了沒用」的矛盾現象，這正是漏注入的特徵。
（`layouts/base.html` 已載入 capability.js，不必重複引入。）


### FRONT-11: 不繼承 `layouts/base.html` 的獨立整頁必須自己載 i18n.js

`__()` 定義在 `backend/app/static/js/i18n.js`，**由 `layouts/base.html` 載入**。
自己寫 `<!DOCTYPE html>` 的獨立整頁（例：`pages/admin/initial_setup.html`）
若用了 `__()`，`__` 根本不存在，症狀是 **Alpine 噴 `__ is not defined`、
該元素永遠空白**，其餘部分正常，不開 F12 看不出來。

照抄 base.html 的寫法，位置在 `alpine.min.js` **之前**：

```html
<script src="{{ url_for('static', filename='js/i18n.js') }}"></script>
{% set _locale = current_locale|default('zh-TW') %}
{% if _locale != 'zh-TW' %}
<script src="{{ url_for('main.i18n_dict_js', locale=_locale) }}"></script>
{% endif %}
```

語系字典路由 `/i18n/<locale>.js` 掛 `@public_route`，
不會被 auth_interceptor 的初始設定攔截擋掉。

全專案掃描指令（2026-08-23 執行結果只有 `initial_setup.html` 一個，已修；
其餘 `__()` 命中項全是被 include 進 base 衍生頁的 `_` 前綴 partial，那些是好的）：

```bash
for f in $(grep -rLn "extends" --include=*.html backend/app/templates modules/*/templates); do
  if grep -qi "<!DOCTYPE" "$f" && grep -q "__(" "$f" && ! grep -q "js/i18n.js" "$f"; then echo "$f"; fi
done
```


### FRONT-10: 後端組「指向本頁」的網址必須帶 `request.script_root`

app 掛在 nginx 的 `/beakplatform` 前綴下，而 **Flask 的 `request.path` 不含該前綴**。
只用 `request.path` 組出的 `/public/portal/...` 在瀏覽器上會被當成缺前綴的
絕對路徑而 404。

```python
# 錯：點下去 404
f"{request.path}?{urlencode(args)}"
# 對
f"{request.script_root}{request.path}?{urlencode(args)}"
```

Page IR 的排序連結**從第一版起就是壞的**，直到 2026-07-29 才發現
（`renderer._self_url()` 已修）。原因見下條。

**這條同樣適用於 model 的 `to_dict()` 與 URL property**（2026-08-30 又踩一次）：
`fw_workflow_backgrounds` / `DcBackground` 的 `to_dict()['url']` 與
`PlatformFile.serve_url` / `download_token_url` 從 2026-04-04 起就寫死
`/api/files/<sc>/serve`，症狀是**流程設計器底圖與企業 logo 全部破圖、
畫面沒有任何錯誤訊息，只有 F12 看得到一串 404**。四處已修，寫法是：

```python
from flask import has_request_context, request
prefix = request.script_root if has_request_context() else ''
```

`has_request_context()` 不可省——model 也會被背景任務（executor、cron）呼叫，
直接讀 `request` 會拋 `RuntimeError`。

**新增任何「回給前端的 URL 欄位」時套用同一個寫法。** 判別方式：
`grep -rnE "f?['\"]/api/" --include=*.py backend/app modules | grep -v script_root`。

### FRONT-12: form.io 自訂元件要在兩個模板都掛 script（2026-08-27 起）

平台層的 form.io 自訂元件放在 `backend/app/static/js/formio-*.js`，
一律用 `Formio.use({components: {...}})` 外掛註冊（升級 form.io 不受影響），
**禁止改 form.io 本體**。現有三支：

| 檔案 | 元件 type | 值 |
|---|---|---|
| `formio-user-picker.js` | `userPicker` | `users.secure_code`（字串） |
| `formio-form-picker.js` | `formPicker` | `fw_form_templates.secure_code` **陣列**（PF-160 授權表單） |
| `formio-form-title.js` | — | 表單名稱 |
| `formio-my-role-picker.js` | `myRolePicker` | `[{role_secure_code, unit_secure_code, role_name, unit_name}]`（PF-251 代理指定申請單，後兩個是顯示快照） |

**新增元件時 `form_designer.html` 與 `form_center.html` 兩處都要加 `<script>`**——
兩邊的 script 清單各自維護（與 `_ir_designer_body.html` 的雙宿主同一個坑）。
只掛設計器的話，**表單中心的填寫頁該欄位不會渲染，而且不報錯**。

其餘三件：`builderInfo.group` 用 `'custom'`（面板顯示為「平台元件」）；
元件內的 `__()` 字串要補進 `backend/app/static/i18n/en.json`（否則英文介面顯示中文）；
多值元件把 `emptyValue` 定義成 `[]` 就能吃 form.io 內建的 required 檢查
（lodash `isEmpty([])` 為 true），不必自己寫驗證。

**要讓 form.io 內建 `datetime` 元件輸出純日期字串（`"2026-12-31"`），
必須設 `widget.saveAs: 'text'` ＋ `enableTime: false` ＋ `format: 'yyyy-MM-dd'`**
（2026-08-27 實測，PF-160 申請單）。缺 `saveAs: 'text'` 時它輸出的是 ISO 8601
（含時間與時區偏移），後端凡是拿 `strptime('%Y-%m-%d')` 解的都會失敗。
**送出後查一次 `fw_form_instances.form_data` 的實際值再接流程**，
畫面上顯示的日期看不出這個差別。

**自訂元件的唯讀檢視（簽核頁、已完成單）有兩個症狀靜默的坑**（2026-09-08 PF-251 第 4 期實測）：

1. **選項清單依「登入者」載入的元件，簽核者永遠解析不出申請人選的東西**。
   `myRolePicker` 的來源是 `/api/my-proxy-assignments/my-roles`（本人的角色），簽核者開單時載入的是
   自己的清單，比對不到申請人的 role sc → 只能顯示 secure_code，等於要對方盲簽。
   **解法是送出時把顯示名稱一起快照進值裡**（`role_name`／`unit_name`），唯讀時優先用快照、
   再退回選項比對、最後才印 sc；後端只讀 secure_code，多出來的顯示欄位一律忽略。
   `formPicker` 用 `beneficiaryKey` 指向表單內的對象欄位重新載入選項，是同一個問題的另一種解法。
2. **元件沒有覆寫 `setValue` 就不會重繪**。Form.io 先 `attach()` 再由 submission 設值，
   `attach` 當下 `dataValue` 還是空的，畫面就停在空狀態——實測簽核者看到「已選 0 個角色」而值其實有兩筆。
   覆寫 `setValue` 後呼叫自己的重繪函式即可，**但只在唯讀時重繪**：可編輯時每次勾選都重建整個清單，
   會讓捲動位置與焦點跳掉（實測連續勾第二項會失敗）。

兩者**單元測試都抓不到**，要在表單中心用另一個帳號開簽核頁才看得出來。

### VERIFY-01: 驗收規範（瀏覽器實測 + 留證，主 Claude 專屬職責）

> 2026-08-06 起，原 VERIFY-01（瀏覽器實測）／VERIFY-02（留證）／VERIFY-03（AI 自檢不算數）
> 三條合併於此。舊文件引用到 VERIFY-02／VERIFY-03 時一律看本節。

**一、使用者要點的東西，curl 驗完還要用 chrome-devtools 實際點一次。**
curl 對「連結、按鈕、select 初次渲染值」有結構性盲區：

- 用 curl 測連結時都是自己帶完整路徑，永遠測不出網址少了前綴（FRONT-10 的成因）
- select 顯示錯值（FRONT-08）在 HTML 原始碼裡看不出來，要渲染後才知道
- `BkCaps.can()` 漏注入（FRONT-09）的症狀是「按鈕點了沒反應、console 不報錯」

**二、AI 產出的自我檢查表不算驗收。**
codex 開不了瀏覽器；**subagent 其實有 chrome-devtools**（2026-09-07 實測確認，本檔原本寫「只有主 Claude 有」已不符實），但全機共用同一個 Chrome 實例，所以瀏覽器工作必須序列派工。
無論誰跑的，AI 自己的「自我檢查七項全過」只證明程式碼有寫，不證明串得起來——
而且**讀起來像已驗收，比「沒測」更危險**。
2026-08-04 menu 設計器面板那批 codex 自述七項全過，實測抓到兩個 P1：底圖下拉存錯 sc
（選了完全沒反應也不報錯）、「不使用底圖」寫空字串違反 schema pattern（整頁存不了，
400 還指向不相干的 widget）。
→ 凡 AI 產出的前端與跨層串接，checklist 逐項自己跑，不採信回報。

**三、驗收的原始輸出一律落地到 `/opt/tmp/verify/<日期>-<主題>.log`。**

```bash
mkdir -p /opt/tmp/verify
curl ... 2>&1 | tee -a /opt/tmp/verify/20260801-file-authz.log
bash scripts/run_tests.sh tests/test_xxx.py -q 2>&1 | tee -a /opt/tmp/verify/20260801-file-authz.log
```

**留證用 `evaluate_script` 取 `innerText` 或結構化 JSON，不要用截圖。**
DOM 狀態類斷言（class 有沒有、按鈕文字、哪個卡片 active、欄位可見性）這樣做比截圖
更精確、可 grep、也更適合寫進 log：

```
evaluate_script(function="() => document.querySelector('.modal-overlay').innerText")
```

**但可見性不要用 `offsetParent === null` 判 `position: fixed` 的元素**（2026-08-16 踩到）：
CSS 規範下 fixed 元素的 `offsetParent` **恆為 `null`**，開著的 `.modal-overlay`
會被判成「隱藏」。fixed 元素一律用 `getComputedStyle(el).display` ＋
`getBoundingClientRect()` 的寬高；它的子元素不是 fixed，`offsetParent` 對子元素仍準確。

**驗「複製」按鈕不要看 UI 的『已複製』回饋文字**（2026-08-27 踩到）：
那類回饋多半只維持 1~2 秒（`setTimeout` 還原），而 chrome-devtools 的
click → evaluate 往返常常超過，於是看到的永遠是原本的「複製」，
會誤判成按鈕壞掉。可靠做法是掛探針再點：

```
addEventListener('click', ...) 計數  +  包一層 document.execCommand 記錄回傳值
→ 實測得到 clicked=1, copyResult=true 才算真的複製成功
```

（平台跑在 http，`navigator.clipboard` 是 undefined，複製一律走
`Utils.copyToClipboard()`；它內部 fallback 到 `execCommand`。）

**`resize_page` 只對「當下選中的分頁」生效**（2026-09-08 踩到）：
指定了 `pageId` 也一樣，若那個分頁不是 selected，回傳看起來成功但
`window.innerWidth` 完全沒變，於是窄畫面測試在測一個根本沒縮小的視窗。
先把多餘分頁 `close_page` 掉、確認目標分頁是 selected 再 resize，
或量完 `window.innerWidth` 確認真的變了才採信結果。

**企業管理頁（`/organizations/`）的清單是前端渲染，curl 抓不到**（2026-09-07 踩到）：
`curl` 拿到的 HTML 裡一家企業代碼都沒有，容易誤判成「清單是空的」或「權限有問題」。
這頁一律用 chrome-devtools 驗收。同理，任何 Alpine 渲染的清單頁都要這樣驗。

**2026-08-04 起 `take_screenshot` 在本機一律逾時**（`Page.captureScreenshot timed out`，
png / jpeg 皆然，各卡滿 120s 才失敗，試過三次）——**修好之前不要再浪費 120s 去試**。
（它另有一個限制：只能寫 workspace root 內，要先存專案內再 `mv` 到 `/opt/tmp/verify/`。）

**為什麼非留證不可**：2026-08-01 對四個 session 做事後幻覺稽核
（363 條事實斷言逐條查證，見知識庫 #4957），41 條判定為 UNVERIFIABLE——
絕大多數是瀏覽器實測與 rate-limit 觀察，**輸出當下就沒落地，事後無論花多少成本都查不回來**。
「我測過了」若沒有留下輸出，事後與「我以為我測過了」無法區分。
留證的成本是一個 `tee`，缺證的成本是整段驗收失去可覆核性。

### CACHE-01: 靜態資源 Cache-Busting

**Flask 全站機制，確保 JS/CSS 變更後瀏覽器立即載入新版，無需 F5。**

實作位置：`backend/app/__init__.py` 的 `register_static_cache_busting()`

| 層 | 覆蓋範圍 | 原理 |
|---|---|---|
| `url_defaults` | `url_for('static', ...)` 引入的檔案 | 自動附加 `?v=<啟動時間戳>`，重啟服務即換版本號 |
| `after_request` | 裸路徑 `/static/...` 引入的檔案 | JS/CSS 回應加 `Cache-Control: no-cache, must-revalidate`，強制條件請求 |

**開發時注意事項：**
- 兩種引入方式都已涵蓋，新增模板時用哪種都可以
- 檔案有變更 -> 瀏覽器拿 200 新內容；沒變更 -> 304（不浪費頻寬）
- 重啟 Flask 後版本號自動更新

---

## 多語系規範 (I18N-01)

平台支援 zh-TW（原文即 key）+ en。**所有新 user-facing 字串必須包翻譯函式**：
Python `_('中文')`、Jinja2 `{{ _('中文') }}`、JS `__('中文')`。

**四條地雷**（違反會 500 或讓功能失效）：
- msgid 含字面 `%` 必須寫 `%%`（flask_babel 一律做 % 插值）
- **禁止**包裹參與 `==`/`===` 比較的字串與機器可讀錯誤碼（包了前端比對即失效）
- **禁止**包裹 logger/console 訊息、寫入 DB 的資料值、email 主旨內文
- pybabel update 的 fuzzy 配對幾乎全錯，必須逐條重翻並清 fuzzy flag

**extract 必須帶齊全部已包裹模組目錄**（open_defense / vuln_lifecycle / spec_formulate /
nocode_builder / form_workflow）——少帶任何一個，該模組 msgid 會被打成 obsolete
並喪失翻譯（已發生過事故）。新模組包裹後要加進清單。

完整指令、JS 字典規則、FormIO locale 陷阱：**`dev-notes/codex_spec/i18n.md`**
進度計畫：`dev-notes/I18N_PLAN.md`


## 時區處理規範 (TZ-01)

**DB 一律存 UTC**（`datetime.utcnow()`，欄位 `timestamp without time zone`）。
純日期欄位（`effective_from`、合約日期）不涉及時區，直接存日曆日期。

顯示時區優先序由 `auth_interceptor.py` 設定：**用戶個人 > 企業設定 > `Asia/Taipei`**（`g.timezone`）。

| 位置 | 必須 | 禁止 |
|---|---|---|
| 後端模板 | `{{ dt\|tz_format('%Y-%m-%d %H:%M') }}` | `dt.strftime()`（會顯示 UTC） |
| 前端 JS | `BkTime.format(dateStr, 'short')` | `new Date(x).toLocaleString()`（會用瀏覽器時區） |
| 後端 API 回格式化字串 | 先 `.replace(tzinfo=UTC).astimezone(user_tz)` 再 strftime | 直接 strftime |

`BkTime` 由 `timezone.js` 在 base.html 全域載入，style 可用 `full`/`short`/`date`/`time`。

**存在性判斷一律寫 `typeof BkTime !== 'undefined'`，禁止寫 `window.BkTime`**
（2026-08-17 踩到）：`timezone.js` 是 `const BkTime = (function () {...})()`，
而全域 `const` **不會**成為 `window` 的屬性。寫成
`(window.BkTime && BkTime.format) ? ... : iso` 的判斷恆為 false，
一路 fallback 成原樣輸出 DB 的 naive UTC 字串——畫面看起來「有值、格式也像」，
只是時間差 8 小時，沒有任何錯誤訊息。`api-keys.js` 因此壞了很久才被發現。

**自行做時間運算時（SLA 倒數、時間差）**：DB 回的 ISO 字串是 naive UTC（無 `Z` 後綴），
直接 `new Date(iso)` 會被當本地時間、差 8 小時（已踩過：SLA 顯示逾時 465 分）：

```javascript
const iso = s.endsWith('Z') ? s : s + 'Z';   // naive UTC 補 Z
const deadline = new Date(iso).getTime() + slaMinutes * 60000;
```

**統計的「今日／本週」日界一律用顯示時區換算，禁止 `utcnow().replace(hour=0, ...)`**
（2026-08-12 起）。DB 存的是 naive UTC，但使用者看到的日期是 `g.timezone` 的日曆日：
台北 08:00 之前，UTC 日界涵蓋的其實是「當地昨天 08:00 起」。處置中心的「今日新案」
就因此長期與清單對不上（顯示 7，當地今天只有 1 筆）。唯一實作：

```python
from app.utils.timezone import local_day_start_utc
today_start = local_day_start_utc(getattr(g, 'timezone', 'Asia/Taipei'), datetime.utcnow())
```

**合約效期的「今日」依企業時區（2026-09-02 PF-125 起）**：`Contract.is_active` / `is_expired` /
`is_not_started` / `days_remaining` 與 `ModuleAccessService` 的合約檢查一律走
`Organization.local_today()`（`app.utils.timezone.local_today()`），**禁止 `date.today()`**。
成因：bpserv 這類 UTC 時鐘的主機，台北 00:00～08:00 建立「起日＝今天」的合約會被判
「尚未生效」，EMPLOYEE 開模組頁一律 403、隔天早上自己好，沒有任何錯誤訊息。
跨企業彙總（企業列表的有效合約數、`ModuleRoleService` 的 org→modules）用 UTC ±1 天寬鬆視窗
查出來再以 `contract.is_active` 過濾。`generate_contract_number()` 的日期戳刻意維持伺服器日期。

**時間差運算（SLA 倒數、逾時判定、滾動 24h 視窗）不受此條影響**，維持 UTC——
那是兩個時間點相減，與時區無關。只有「切在某個日曆日邊界」才要換算。

**手打 SQL 查「最近 N 分鐘」時 `now()` 是台北時間，而欄位存 naive UTC**
（2026-08-24 踩到）：`created_at > now() - interval '15 minutes'` 會被 8 小時偏移吃掉，
**回 0 筆**，看起來像「功能沒動作」。查近 7 天沒事是因為 7 天遠大於 8 小時，
所以這個坑只在短時窗出現。正確寫法：

```sql
WHERE created_at > (now() AT TIME ZONE 'UTC') - interval '15 minutes'
```

**同一個坑的日界變體：`created_at >= CURRENT_DATE` 在台北 08:00 之前會漏掉「今天」建的資料**
（2026-09-03 清測試資料時 `DELETE ... WHERE created_at >= CURRENT_DATE` 回 `DELETE 0`，
資料明明就在）。要抓「最近建的」一律用 UTC 時窗，不要用日曆日。


## 資料庫資訊

- **Host**: localhost
- **Port**: 5432
- **Database**: beakplatform_dev
- **User**: beakplatform
- **Password**: postgres123（開發環境）
- **本機資料皆為測試資料**：變更後可忽略舊資料，不用修正舊資料，除非用戶要求

### 行事曆：投影只有一個實作、寫入只有一個實作（PF-229 第一期 2026-09-02、第二期 2026-09-03）

`/calendar/`（企業）與 `/calendar/me`（個人）畫面上的事件全是
`backend/app/services/calendar_projection_service.py` 從六種來源投影出來的：`calendar_events`（手建）、
班表假日、代理指派（`user_role_assignments` 的 proxy 列，同一對人同效期合併一筆，`source_type='proxy'`）、限期職位、公告廣播、流程佇列（**只有** Delay 到期、只給管理員）。
**待簽核任務刻意不投影**（Ethan 2026-09-03 定案：沒有確定開始時間的是待辦不是行事曆，表單量大且已有表單中心），
第一期曾投影過、同日移除，不要加回來。
受眾與遮罩**只在** `calendar_visibility.apply_visibility()` 判定——新增來源時產出正規化 dict 並填 `audience`，
不要在外面另寫 if。寫入（第二期起）**只走** `calendar_event_service.CalendarEventService`
（`POST/PUT/DELETE /api/calendar/events`，掛 `@page_keys_required('calendar_me')`），
org 與 owner 一律取自登入身分、payload 給了也忽略。五件猜不到的：

- **`PRIVATE` 對 ORG_ADMIN 也隱藏**（Ethan 定案，避免變成監控工具）；`BUSY` 他人只拿到 `masked=true`、無 title，
  且**同一人重疊或相接的 BUSY 會合併成一筆** `source_type='busy'`（`_merge_masked()`，key 是 `busy:<owner>:<n>`）。
  代理／職位這類自帶受眾的來源對非受眾是「不顯示」，不是遮罩
- **PERSONAL 只有本人能改，ORG_ADMIN 改別人的個人事件也是 404**；ORG 事件只有 ORG_ADMIN 能建改刪且一律 `PUBLIC`
  （payload 給 `PRIVATE` 會被靜默改成 PUBLIC，不報錯）。判定在 service 的 `_get_editable_event()`，不在 decorator
- **`LEAVE`／`TRIP` 個人事件會同步寫 `schedule_adjustments`（`adjust_type='LEAVE'`、`status='APPROVED'`、
  **時段級**（2026-09-03 B 項起）：`original_periods`＝底、`adjusted_periods`＝扣掉當日請假聯集後的剩餘、全天＝`[]`、NULL＝整天請假的相容語意；`calendar_event_secure_code` 指回事件）**，`ScheduleService.get_work_periods()` 從此看得到請假（LEAVE 列優先於同日其他調整；resync 算底一律用 `get_base_work_periods()`）。
  改期／改型別／刪除時走同一支 `resync_leave_adjustments()` 軟刪除或復活（該表有
  `(user, date, type)` 唯一約束，硬刪再插會撞，所以一律復活）；`calendar_event_secure_code IS NULL` 的列是
  表單或人工建的，**行事曆絕不動它**
- API 的 `start`/`end` 是**企業時區當地日曆日**（寫入時全天用 `YYYY-MM-DD`、非全天 `YYYY-MM-DDTHH:MM`），
  回應的 `start_local` / `start_date` 也已換算完，前端一律不做時區運算；轉換函式集中在 `app/utils/calendar_time.py`
- **新增平台選單對既有環境不會自動出現**：`seed_platform_menus()` 非 force 模式見到任何選單就整批跳過。
  補種走 `venv/bin/python scripts/seed_missing_platform_menus.py --dry-run` → `--apply`（通用、冪等，含所有企業 Key2）。
  bpserv 這類已安裝環境 `--update` 後也要跑一次，否則選單不在、`page_keys_required` 對 EMPLOYEE 一律 403。
  **第二期在 bpserv 還要補 `schedule_adjustments.calendar_event_secure_code` 欄位**（`--update` 的 create_all 只補新表不補欄位；bpserv 已於 2026-09-03 PF-232 補齊，連同該表的唯一約束；其他既有環境的升級 SQL 在 `dev-notes/CALENDAR_SPEC.md` 第六節）

投影規則表、時區處理、前端行為與已知取捨見 `dev-notes/CALENDAR_SPEC.md`。
班表假日 API 2026-09-02 起收下 `COMP_OFF`（視同休假），`saveHoliday()` 改用 `result.imported` 回報。

### 假日表與預設班表（PF-235，2026-09-04）：發佈是「複製進班表」，不是讀取端多查一張表

三層：客製班表（帳號指定，最優先）> 企業假日表（`holiday_calendars` 底稿，發佈後才生效）> 企業預設班表
（建企業時 `ScheduleService.ensure_default_schedule()` 依企業設定 `country` 自動種，週休依 `regions.py` 對照）。
**發佈＝把 PUBLISHED 條目寫進所選班表的 `schedule_holidays` 並標 `holiday_calendar_secure_code`**（NULL＝手動列），
`WorkSchedule.get_day_periods()`／`ScheduleService`／行事曆投影一行未改。唯一實作
`backend/app/services/holiday_calendar_service.py`，規則與已知取捨在 `dev-notes/CALENDAR_SPEC.md` 第八節。四件靜默的：

- **手動列永遠贏**，自訂表 > 政府表；**下架較高優先的表不會恢復被它取代的列**，那天就沒假日，要重發佈政府表
- 班表假日頁 PUT 任何欄位都會把來源清成 NULL（變手動列），之後發佈不再覆蓋它——這是設計，不是漏更新
- 「從網路取得台灣行事曆」是伺服器端抓 jsDelivr 固定 URL（`TW_GOV_CALENDAR_URL`），封閉網路一律回 502 `fetch_failed`，改用上傳；
  資料出處與授權寫在主機設定「套件版本」分類的「外部資料來源與授權」卡片（`_ss_packages.py::DATA_SOURCES`），不要複製 URL 到別處
- **既有環境（bpserv）升級三步**：`--update` 的 create_all 只建兩張新表；`schedule_holidays.holiday_calendar_secure_code` 欄位＋索引要手動 ALTER
  （SQL 在 CALENDAR_SPEC 第八節）；再跑 `venv/bin/python scripts/seed_default_work_schedules.py --apply` 補預設班表，
  否則沒班表的企業發佈時沒有目標可勾、行事曆也永遠沒國定假日

`DEFAULT_TW_HOLIDAYS_2026` 與 `holidays.js::importTWHolidays()` 已刪除；看到舊文件寫「[匯入台灣假日] 只有 2026 年資料」一律過時。

### 特定代理（PF-71，2026-09-04 起）：限定「表單模板 secure_code」，判定在 task_authorizer 的 scope 一層

**2026-09-07 PF-251 第 3b 期起 `delegations` 整套退役**（`/delegations/` 頁、`Delegation` 讀寫、`/api/my-delegations`、gateway 登記、`DELEGATED` 權限條件全數移除；表與 model 檔留一版考古，程式不得再讀寫）。限定表單改存 `user_role_assignments.allowed_form_templates`（proxy／standby 列），判定在 `role_holding_service.holds()` 的 `form_template_sc_of` 回呼（仍走 `actor['_form_template_cache']`）。下面這段是 PF-71 當時對舊表的實作，僅供考古。

`delegations.allowed_process_types` 從此存 **JSON 陣列的 `fw_form_templates.secure_code`**（管理員頁多選下拉，員工自助 API 仍只建 FULL）。
`build_actor()` 多回 `delegation_scopes`（授權人 → `None`＝不限表單／set＝限定表單），`resolve_acting_identity()` 在身分比對成立後
再看 scope：任務的 `form_instance_secure_code` → `FwFormInstance.form_template_secure_code`，結果快取在 `actor['_form_template_cache']`，
**只有 actor 有 SPECIFIC 授權人才查**。空清單、解析失敗、任務沒有表單實例一律不放行（fail-closed）；同一授權人另有 FULL 則不限。
驗收憑證 `/opt/tmp/verify/20260904-pf71.log`（詳情端點 200／403 矩陣；OD 案件不進表單中心待簽清單，用詳情端點判定）。

**平台層（`backend/app/web`、`api`）要用模組 model 一律在函式內 import**：`modules` 套件是 app 啟動時由 `module_loader` 才插進
`sys.path`，寫在模組層級的 `from modules.form_workflow.models import ...` 會讓 **flask 起不來、systemd crash loop、nginx 恆 502**，
而 `cd backend && python -c "import app"` 與 pytest 都測不出來（conftest 已把 repo root 放進 sys.path）。測試檔頂端要用
`modules` 時照 `test_task_authorizer_delegate_from.py` 先 `sys.path.insert(0, repo_root)`。2026-09-04 PF-71 踩到。

### 造／清測試帳號（2026-08-23 試誤才弄對）

- **要一整家可登入的範例企業，用 `scripts/seed_demo_org.py`（2026-09-13 PF-272／PF-224）**：
  `venv/bin/python scripts/seed_demo_org.py --apply --password '<12 碼過政策>'` 建 DemoSOC
  （code `DEMOSOC`、domain `demo-soc.example`、五個模組合約、13 位員工、已過精靈的
  `admin-admin.ops@demo-soc.example`、資安人員 linda.hu／jason.ling、資安主管 kevin.ye、
  OD 受理鏈路＋SOC 團隊版（sev>=3 路由已啟用）＋單人版＋差旅費人事取值示範）。domain 已存在
  exit 2，移除靠硬刪除企業。dev 庫 2026-09-13 已建一份（管理員 quick-login 見 DB；密碼
  `DemoSoc-Staff2026#`）；codex 驗證時另留了一家 `DEMOCORP`／`demo-corp.example`，可硬刪
- 精靈邏輯唯一實作已抽成 `backend/app/services/org_initial_setup_service.py::complete_initial_setup()`，
  `seed_test_companies.py` 每家 `admin_member` 也走它自動過精靈（管理員密碼常數 `SEED_ADMIN_PASSWORD`，
  舊敘述「BRIGHTCODE／SHIELDEDGE 未過精靈」對重建後的企業不再成立）


- `POST /api/users/` 必填四項：`native_name` / `english_name` / `username` /
  `employee_id`（少了只回「本國姓名、英文姓名、帳號為必填」，不會列出 employee_id）。
  **身分參數名是 `role` 不是 `user_type`**（`user_type` 會被靜默忽略——刻意設計，
  PF-150 已於 2026-09-01 依 2026-08-23 重評結論關單）：`role: "external"` 建
  EXTERNAL 並自動配 `EXTERNAL_USERS` 角色、`org_admin` 建 ORG_ADMIN、
  預設 `user`＝EMPLOYEE 配 `EMPLOYEE` 角色（`_get_user_type_from_role` /
  `_assign_default_role`）。要 EXTERNAL 測試帳號傳 `role: "external"` **加 `email`
  （完整 Email，如 `gg@gmail.com`；`username` 可省略，會等於 Email）**，
  不必再用 SQL 改。2026-09-02 起外部廠商的 `username` 一律等於完整 Email
  （之前取 `@` 前段，同企業兩個 gg 會撞唯一索引）；員工／共用登入頁的
  `_do_login()` 同日起排除 EXTERNAL，廠商只能從廠商登入頁以 Email 登入
- 硬刪一個測試帳號要**按 FK 順序清四張表**，少一張就被擋，
  而錯誤訊息只說 "still referenced" 不會一次列出全部：

```
user_role_assignments -> audit_logs -> used_user_numbers -> users
```

（試建**企業**則不能用 SQL 硬刪，走 `/organizations/` 列表頁最下方的「永久刪除已軟刪除的企業」，見 PF-145 交接檔。）

### 企業清理與主機清理是兩頁，判準是操作對象（2026-08-29 PF-170 起）

**分界線：操作對象是不是一家「還存在於 `organizations` 表」的企業。**
是 -> 企業管理；不是（殘留、無主、跨企業）-> 主機資料清理。
**不要把兩者搬回同一頁**，2026-08-29 之前它們就是混在一起的。

| 頁面 | 卡片 | 清什麼 |
|---|---|---|
| `/organizations/`（列表頁最下方，預設收合） | 永久刪除已軟刪除的企業 | 該企業在**所有**帶 `org_secure_code` 的表裡的資料 ＋ 企業本身 ＋ 它的檔案與目錄 |
| `/hostconfig/data-maintenance`（**主機資料清理**） | 清除標記刪除的資料 | 各表中 `is_deleted=true` 的個別記錄（與企業存不存在無關） |
| 同上 | 清理企業孤兒資料 | `org_secure_code` 指向**已不存在企業**的殘留（歷史漏刪造成）＋ 無主檔案與孤兒目錄 |

端點也跟著搬了：硬刪除是 **`/organizations/hard-delete/preview|execute`**，
`/hostconfig/hard-delete/*` 已 404。舊文件與舊卡片指的都是搬遷前的位置。

**刪除核心是共用的**：`backend/app/services/org_data_purge_service.py`
（表清單掃描、刪除順序、三趟重試、statement builder），企業硬刪除與孤兒清理
兩邊都 import 它，**禁止各自複製**。

**表清單不再手工維護**：`get_org_scoped_tables()` 從 `information_schema` 動態掃出
所有帶 `org_secure_code` 的表（2026-08-28 是 94 張），只有真正有 FK 依賴的順序寫在
`HARD_DELETE_ORDER`，其餘動態帶入，再用**三趟重試**自我修復順序問題
（實測把順序整個反過來仍全刪乾淨）。**新增模組表不必再改任何檔案。**
沒有 `org_secure_code` 的 4 張表走 `HARD_DELETE_INDIRECT` 的父表過濾。

**`pages/hostconfig/index.html` 已刪除**（PF-170）：`hostconfig.index` 只做
`redirect` 到 server-settings、從未 render 過那個模板，但裡面有兩張卡片的完整複本。
endpoint 本身仍被 `portal_base.html` 與 `dev/index.html` 引用，所以**端點還在**。

三件猜不到的：

- **判定成功不能只看 `success`，它恆為 true**。要看 `has_errors` / `errors`
  （2026-08-28 新增的欄位）。改版前錯誤只藏在 `deleted_counts` 的 `(錯誤)` 鍵裡：
  實測有 logo 的企業會撞 `platform_files` 的 FK，**企業根本沒刪掉卻回成功**
  （`/opt/tmp/verify/20260828-pf165-harddelete.log`）
- 改版前漏列 54 張模組表，所以 **2026-08-28 之前刪掉的企業一定留了孤兒**。
  本機那 1099 筆已用「清理企業孤兒資料」清掉
- **系統企業的 `code` 是 `SYSTEM`、`secure_code` 是 `system.local`**——
  看到 `org_secure_code='SYSTEM'` 的記錄一律是把 code 誤當 secure_code 寫入的孤兒，
  不是刻意的系統級資料（本機 `fw_node_execution_logs` 有過 9 筆）

### 實體層清理：檔案、目錄與企業專屬資料庫都會跟著刪（2026-08-28 PF-166、2026-09-12 PF-256）

唯一實作是 `backend/app/services/org_physical_cleanup_service.py`，
**路由層不自己組路徑、不自己刪檔**。「清理企業孤兒資料」卡片下半有「實體資源」區塊
（端點 `/hostconfig/physical-orphans/preview|execute`）。

五件猜不到的：

- **順序不能改**：實體檔案與 `db_name` 必須在**刪表之前**收集
  （`platform_files.storage_ref` 一旦硬刪就查不到該刪哪些檔），
  而 `encrypted_storage/<sc>` 與 EDL 目錄必須在 **commit 之後**才刪——
  企業還在 DB 時，每分鐘一次的 `scripts/cron/od_render_edl.py` 會把 EDL 目錄寫回來
- **企業專屬資料庫（`org_<數字>`）2026-09-12 起由 web 端連帶刪除**
  （硬刪除時連同 `bfadmin_*` / `bfsync_*` 一起）。2026-08-28「一律不由 web 端刪、
  只回 `manual_required` 讓管理員自己 `dropdb`」的決定已推翻——當時的技術理由
  「刪庫需要 superuser」是錯的（`org_<id>` 的 owner 就是 `bfadmin_<id>`）。
  `manual_required` 現在只剩「登記在、實體庫不存在」這種不一致，不再列待刪項。
  **順序**：收集 db_name ＋ owner 憑證在刪表之前，實際 DROP 在 commit 之後，
  庫沒刪成功就絕對不刪角色。細節見 `dev-notes/ORG_DATABASE_LIFECYCLE.md`
- **孤兒目錄的判定是「目錄名不在 `organizations.secure_code` 全集內」，
  刻意不加 `is_deleted` 條件**——軟刪除的企業還沒硬刪，它的檔案不是孤兒。
  也因為判定依賴這個查詢，**新增的端點必須跟既有四個一樣先下
  `SET LOCAL app.is_system_admin = 'true'`**，否則哪天那兩張表加了 RLS
  就會把使用中的企業目錄判成孤兒刪掉（`organizations` 與 `platform_files`
  現在沒有 RLS，所以這是防未來的，不是現在的破口）
- **`backend/uploads/` 的無主檔案是全域概念、不屬於任何企業**（扁平目錄、
  隨機檔名，DB 記錄沒了就認不出原主），所以它只出現在孤兒清理那張卡片，
  不會出現在「刪某企業」的流程裡
- 有 `platform_files` 記錄的檔案一律走 `file_service.delete_file()`（FILE-01），
  只有無主檔案才能 `os.remove`；路徑一律先過 `safe_child_dir()`

### Schema 權威是 ORM model，migration 制度已廢止（2026-09-01 PF-168 起）

兩條建庫路徑已收斂為一條：**`db.create_all()` 是唯一權威**，dev 庫已於
2026-09-01 一次性收斂到與 model 一致（含 timestamptz 轉 timestamp、jsonb 對齊、
死欄位清除；記錄在 `scripts/migrations/legacy/136_pf168_dev_convergence.sql`）。
137 支歷史 migration 與 `run_migrations.py` 全部封存在
`scripts/migrations/legacy/`（含兩個模組的 migrations 目錄），**僅供考古，
不要對任何資料庫執行**；`schema_migrations` 表已自 dev 庫刪除。
文件裡引用 `scripts/migrations/legacy/0xx`／`1xx` 的舊路徑一律到 `legacy/` 底下找。

開發時改 schema 的規則（詳見 `scripts/migrations/README.md`）：

1. 改 ORM model（新表由 create_all 建出，新欄位要自己對 dev 庫下一次性 SQL）
2. 跑守恆檢查，**有差就紅**（約 1~2 分鐘，改 model／加表／動 DB 物件後必跑）：

```bash
bash scripts/check_schema_drift.sh          # --show-indexes / --show-defaults 看警告明細
```

3. 動了 `workflow_node_definitions`（新節點型別）要重跑
   `venv/bin/python scripts/export_node_definitions_seed.py`，
   否則**全新安裝的設計器不會出現新節點且不報錯**
4. create_all 建不出來的 DB 物件（schema／role／ACL）與出廠資料，
   加進 `scripts/sql/`（現有：`fw_sp_setup.sql`、`seed_workflow_node_definitions.sql`、
   `seed_node_org_grants.sql`、`seed_menu_defaults.sql`、`seed_rbac_defaults.sql`）
   並登記到 `backend/app/defaults/bootstrap.py` 的 `SQL_EXTRAS`（見下段）。
   **只有需要 superuser 的物件**（目前僅 `fw_sp_setup.sql`）才留在 shell

### 安裝／升級的 DB 初始化只有一個入口：`scripts/bootstrap_db.py`（2026-09-02 PF-211 起）

`install.sh`（全新安裝與 `--update`）與 `init_database.sh` 都不再各自串 create_all、
heredoc 建企業、`init_menus.py`、`init_permissions.py`、`flask module sync`、
`seed_system_org_defaults.py`——那套曾經兩邊各一份、PF-210 就是兩份 heredoc 分歧出來的 bug。
現在：

| 誰 | 做什麼 |
|---|---|
| shell（`install.sh` / `init_database.sh`） | 只做需要 **postgres superuser** 的事：建 DB 使用者與資料庫、`pgcrypto`、`scripts/sql/fw_sp_setup.sql`；然後呼叫 bootstrap |
| `scripts/bootstrap_db.py --fresh` | create_all → 驗證 fw_sp 已就緒 → 系統企業＋出廠角色＋SYSTEM_ADMIN → 4 支 SQL extras → 平台選單（force）→ 平台權限 → 模組同步（force）→ 系統企業出廠資料 |
| `scripts/bootstrap_db.py --update` | create_all（只補新表）→ 驗證 fw_sp → 系統企業必須已存在 → SQL extras → 平台選單（非 force，已有就跳過）→ 平台權限（逐 code 補缺；**2026-09-04 PF-241 起才真的逐 code**，之前 `force=False` 是「DB 已有任何系統權限就整批跳過」，本欄卻一直這樣寫）→ 模組同步（非 force）。**刻意不建企業、不種出廠資料**（不回填既有環境） |

唯一實作是 `backend/app/defaults/bootstrap.py::run_bootstrap()`，順序有依賴不可調換
（受限節點授權需要 `is_system_org` 的企業先存在；平台選單必須在模組同步之前，
否則模組選單先佔位會讓平台選單被誤判「已存在」而整批跳過；出廠資料的 Key2
需要模組選單已存在）。`init_menus.py` / `init_permissions.py` /
`seed_system_org_defaults.py` 仍在，但只是薄殼維運入口，邏輯在
`backend/app/defaults/platform_menu_defaults.py` / `permission_defaults.py` /
`system_org_defaults.py`；`flask module sync` 與 bootstrap 共用
`ModuleSyncService.sync_all()`（權限、選單、lookup、模組預設角色四段，
漏一段就會像 PF-210 那樣分歧）。

三件猜不到的：

- **bootstrap 以應用帳號執行、不 sudo**（install.sh 裡是 `beakplatform` 服務帳號），
  SQL extras 走 `psql` 子程序、密碼只經 `PGPASSWORD`。所以 `fw_sp_setup.sql`
  不能塞進 `SQL_EXTRAS`——它要 CREATE ROLE，app 角色做不到；bootstrap 只在第二步
  `verify_superuser_objects()` 檢查 schema `fw_sp` 存在且 owner 是 `fw_sp_owner`，
  沒有就直接退出並印出該用 postgres 執行的指令
- **任一步失敗即非零退出，`install.sh` 因 `set -e` 立刻中止**。改版前 install.sh 對
  選單／權限／模組同步／出廠資料全部 `|| log_warn "跳過"`，半套安裝會被回報成成功
- 管理員密碼只從 `ADMIN_INITIAL_PASSWORD` 環境變數讀（fresh 模式建 `admin` 與
  `enterprise` 兩個帳號都用它），不接受命令列參數

守恆檢查的警告區（索引 800+ 筆、server default 500+ 筆、fw_sp 的 demo 函式）
是已知不列入判定的差異；**只有硬判定區（表／欄位／型別／NOT NULL／fw_sp ACL）
出現差異才是回歸**。`freshcheck` 是拋棄式獨立庫，與 `beakplatform_test` 無關。

欄位級的升級機制（公開後既有環境的升級）**刻意不存在**——2026-09-01 時點
沒有任何已安裝的外部環境。首次需要時另行設計（候選 alembic），
不要復活 `run_migrations.py`。

### 每個 session 都會撞一次的欄位名（2026-08-09 逐一試誤才弄對）

寫 SQL 前先看這張表，可省掉一輪 `column ... does not exist`：

| 想查的東西 | 錯的猜法 | 實際欄位 |
|---|---|---|
| 使用者姓名 | `users.name` / `full_name` | **`users.display_name`** |
| 表單模板是否發行 | `fw_form_templates.status` | **`is_published`**（發行快照在 `fw_published_form_workflows.status='Published'`） |
| API Key 是否可用 | `api_keys.is_active` | **`api_keys.status`**（`active` / `suspended`） |
| 角色是否唯一 | `roles.code` 唯一 | **只有 `secure_code` 唯一**，`ix_roles_code` 是非唯一索引 —— 不同企業的 `SECURITY_STAFF` 是兩筆不同 secure_code |
| 角色綁哪種身分 | `roles.user_type` | **沒有這個欄位**；層界看 `roles.scope_type`——2026-09-01（PF-145 階段三之二）起指派時擋跨層：EXTERNAL 帳號只能拿 `scope_type='EXTERNAL'` 的角色，雙向都擋（見 PERM-03）。用 SQL 直寫指派仍繞得過，造測試資料時自己對齊 |
| 一個帳號「是不是 ORG_ADMIN」 | 看它有沒有 `ORG_ADMIN` 角色 | **`user_type` 與角色 code 是兩回事，但四個名字完全相同**：`SYSTEM_ADMIN` / `ORG_ADMIN` / `EMPLOYEE` / `EXTERNAL_USERS` 出廠時每家企業都會建同名角色。身分硬界線一律看 `users.user_type`，角色看 `user_role_assignments`→`roles.code`（2026-08-24 用戶與 AI 都在此混淆過） |
| OD 路由規則的條件 | `od_form_template_mappings.conditions` | **`match_rules`**（jsonb） |
| intake 事件的處理狀態 | `od_intake_events.status` | **沒有這個欄位**；有沒有建成案件看 `case_secure_code IS NOT NULL` |
| intake 事件的來源 IP | `od_intake_events.actor_ip` | **沒有這個欄位**。全部欄位只有 `correlation_id / intake_key_secure_code / source_system / event_class / severity_id / raw_body / signature_verified / case_secure_code / received_at`——IP 埋在 `raw_body` 的 OCSF JSON 裡，要查 IP 一律去 `.20` ClickHouse 的 `events.actor_ip` |
| 資安案件的分類前綴 | `SECCAT%` | **`CAT_SECURITY_%`**（`security_center.py::SECURITY_CATEGORY_PREFIX`） |
| 選單項目的顯示名稱 | `menu_items.name` / `display_name` | **`menu_items.title`**（另有 `title_en` / `title_zh_cn` / `title_i18n`） |
| 發行快照指向的表單 | `fw_published_form_workflows.form_template_secure_code` | **`source_form_template_secure_code`**（流程那邊同理是 `source_workflow_template_secure_code`） |
| 節點執行紀錄指向的流程 | `fw_node_execution_logs.workflow_instance_secure_code` | **`workflow_instance_id`（bigint，指向 `fw_workflow_instances.id`）**；同專案的 `fw_node_execution_queue` 卻是 `workflow_instance_secure_code`，兩張表不一致 |
| 表單同步佇列的目標表 | `fw_sync_queue.table_name` | **沒有這個欄位**；表名在 `fw_sql_form_registries.table_name`，queue 只存 `form_instance_secure_code` + `published_secure_code` |
| 選單 Key1 是否可見 | `menu_permissions.is_visible` | **沒有這個欄位**；有記錄＝該 user_type 可見，只有 `menu_secure_code` + `user_type` + `conditions` |
| 節點執行 log 的欄位 | `fw_node_execution_logs.level` / `.message` / `.data` | **`log_level` / `log_message` / `log_data`**（2026-09-01 撞過）；Telegram 送達憑證在 `log_data` 的 `message_id` |
| 角色指派是否生效 | `user_role_assignments.is_active` | **沒有這個欄位**；用 `is_deleted` ＋ `valid_from` / `valid_until`（date） |
| 角色指派的單位維度 | 以為角色是全企業一個扁平集合 | **`user_role_assignments.unit_secure_code`**：NULL＝全企業（對任何單位都算持有），有值＝只在該單位持有（`DEPT_MANAGER@行銷部門`）。簽核授權（PF-247）依此判定：ROLE 型角色由後代單位往祖先套圈（軟體部成員也是資訊群成員），POSITION 型（主管、副主管、代理人）不套圈。查「誰是某部門主管」一律 `role_secure_code`＋`unit_secure_code` 一起下，只用 code 會把全公司的主管都撈進來 |
| 角色指派的性質（正式／代理／候補） | 去查 `roles` 或 `delegations` | **`user_role_assignments.assignment_kind`**（`regular`／`proxy`／`standby`，2026-09-06 PF-251 第 1 期起；被代理人在 `acting_for_user_secure_code`、限定表單在 `allowed_form_templates` jsonb、來源在 `source_ref`）。`delegations` 已於 2026-09-07（PF-251 第 3b 期）退役，表與 model 檔留考古、程式不再讀寫。用 SQL 直插指派列時 `assignment_kind` 有 DB 預設 `'regular'`，其餘四個 NOT NULL 欄位照下方那列補 |
| 流程節點怎麼拿到「表單欄位」的值 | 以為 FormAdapter 的 `DYNAMIC` 可以直接指欄位名 | **`DYNAMIC` 走 `BaseNodeHandler.get_var()`，只查流程變數、不讀表單欄位**：要先放 `OpFieldRead` 把欄位讀成流程變數。它會同時寫 `<form_code>_<field>` 與 `<field>` 兩個名字，而**那個 `form_code` 取的是 `form_instance.form_template_secure_code`**（`fieldread_handler.py:38`），不是表單模板的 code——所以出廠 graph 只能用不帶前綴的簡單名（2026-09-08 PF-251 第 4 期踩到，寫錯的症狀是簽核者解析為空、每張單都被 PF-226 退回申請人，而單元測試抓不到） |
| 某人的直屬主管 | `employee_positions.direct_manager_secure_code` | **欄位已於 2026-09-05（PF-247 第 4 期）DROP**，人對人指標退役；直屬主管由 `app.services.unit_resolver.resolve_direct_manager()` 從 `DEPT_MANAGER@單位` 推導（本人是主管或職缺就往上一層，副主管代理人不算）。`dotted_line_manager_secure_code`（虛線主管）仍在。既有環境升級要手動 DROP，create_all 不刪欄位 |
| 模組 ACL 的表 | `module_access_controls`（複數） | **`module_access_control`**（單數）；`target_type` 是 `ROLE` / `ACCOUNT`，值放 `target_secure_code` |
| 表單模板的欄位定義 | `fw_form_templates.form_schema` | **`schema`**（jsonb）；另有 `builder_config` / `allowed_editors` |
| 使用者的員工編號 | `users.employee_number` / `emp_no` | **`users.employee_id`**（varchar 50，組織內唯一）；**兩帳號制的管理員帳號 2026-08-23 起才有號**——新企業由 `_create_default_numbering_rules()` 的第 6 條規則自動發 `ADM001`，既有企業已由 `scripts/migrations/legacy/112_backfill_org_admin_employee_id.py` 回填；SYSTEM_ADMIN 型帳號刻意不發（平台級身分不屬企業人事編制） |
| 企業獨立資料庫的庫名 | `fw_org_databases.database_name` | **`db_name`**（另有 `org_id` / `db_host` / `db_port` / `is_ready`）；注意「記錄在、實體庫不在」是既有狀態（本機 `org_14`），反向不一致兩個方向都要查 |
| migration 登記表 | 查 `schema_migrations` | **表已於 2026-09-01（PF-168）自 dev 庫刪除**，migration 制度廢止、model 即權威；查到引用它的舊文件一律過時 |
| 編號規則的流水號 counter | `user_numbering_rules.current_counter` / `.code` | **兩個都不存在**；該表只有 `id / secure_code / org_secure_code / name / description / elements / is_active / usage_scope / default_for` 等，**流水號設定與計數藏在 `elements` 這個 jsonb 內**（`components` 陣列裡 `type='sequence'` 的項目）。要看「號碼有沒有被消耗」一律查 `used_user_numbers`，不要找 counter 欄位 |
| 企業獨立資料庫登記表的必填欄位 | 只填 `org_secure_code` / `org_id` / `db_name` | 還要 **`secure_code`**、**`admin_user`**、**`admin_password_enc`**、**`sync_user`**、**`sync_password_enc`** 五個 NOT NULL（2026-08-29 造測試資料時逐一撞出來，錯誤訊息一次只報一個）。查全部必填：`SELECT column_name FROM information_schema.columns WHERE table_name='fw_org_databases' AND is_nullable='NO';` |
| 代理授權是否生效 | `delegations.status='ACTIVE'`（表已於 2026-09-07 PF-251 3b 退役，只剩考古資料） | **代理改看 `user_role_assignments`**：`assignment_kind='proxy' AND is_deleted=false AND CURRENT_DATE BETWEEN valid_from AND valid_until`（日界是企業時區，Python 端 `UserRoleAssignment.is_valid_on(org.local_today())`）；被代理人在 `acting_for_user_secure_code`，自助建立的 `source_ref='self:<sc>'`、遷移來的 `migration:pf251:<delegation sc>` |
| 行事曆事件的擁有者／可見性 | `calendar_events.user_secure_code` / `is_public` | **`owner_user_secure_code`**（PERSONAL 必填，ORG 為 NULL）／**`visibility`**（`PUBLIC` / `BUSY` / `PRIVATE`）；`calendar_kind` 是 `ORG` / `PERSONAL`。時間欄位 `starts_at` / `ends_at` 存 naive UTC |
| SMTP 設定組的主機欄位 | `smtp_configs.host` / `port` | **`smtp_host` / `smtp_port`**（另有 `use_tls` / `use_ssl` / `use_app_password` / `provider_type`；2026-09-04 PF-228 起 dev SYSTEM／BELUGA 與 bpserv SYSTEM／DEMOSOC 各一筆 `lionsecbot@gmail.com`、皆 is_default 且實寄過。要給別的測試企業補同一組就跑 `venv/bin/python scripts/seed_smtp_test_config.py --orgs <CODE,...> --apply`——它在同一個 DB 內把系統企業的預設設定組複製過去，Fernet 鑰匙由 `SECRET_KEY` 派生、各企業共用，所以不經手明文、bpserv 也不必重打應用程式密碼） |
| 用 SQL 造測試角色指派（mutation 驗證常用） | 只填 user/role/org 三個 secure_code | 還要 **`secure_code`**、**`assigned_at`**、**`created_at`**、**`updated_at`** 四個 NOT NULL（DB 無預設、只有 ORM 預設；2026-09-01 與 2026-09-05 各撞一次，錯誤一次只報一個）。`assigned_by` 填可辨識標記（如 `PF145-S5-TEST`），事後 `DELETE FROM user_role_assignments WHERE assigned_by='<標記>'` 一次撤乾淨；成功範例在 `/opt/tmp/verify/20260901-pf145-stage5.log` |
| 系統設定的鍵值 | `system_settings.setting_key` / `setting_value` | **`key` / `value`**（另有 `value_type` / `category` / `secure_code`）。2026-09-07 撞過 |
| SysSqlExecutor 白名單的程序名 | `fw_sql_procedures.procedure_name` / `sp_name` | **`code`（流程 config 引用的鍵）與 `function_name`（實際 PG 函式名）是兩個欄位**；另有 `result_mode`（`scalar`／`row`／`rows`）／`result_columns`／`max_rows`。2026-09-07 連撞兩次 |
| 表單／流程的分類 | `fw_categories.code` / `category_type` | **兩個都不存在**。只有 `secure_code` / `name` / `parent_secure_code`，可見範圍靠三個布林 `show_in_form_design` / `show_in_workflow_design` / `show_in_form_center`。2026-09-07 撞過 |
| 流程變數的欄位 | `fw_workflow_variables.variable_name` / `variable_value` | **`var_name` / `var_value`**。2026-09-07 PF-252 撞過 |
| 誰能改 `fw_sp` 裡的預存程序 | 以為 `beakplatform` 可以 | **不行**，該 schema 的 owner 是 `fw_sp_owner`，平台帳號連 DROP 自己不擁有的函式都會被拒（`must be owner of function`）。要 `sudo -u postgres psql -d beakplatform_dev`。這是刻意的權限隔離，不是設定錯誤 |
| 企業專屬資料庫何時建立 | 以為只有按需建立 | **2026-09-12（PF-256）起建立企業時就建**（`org_database_service.ensure_org_database()`，在 org commit 之後；建庫失敗不擋企業建立但一定回報）。按需的兩個舊觸發點仍在（表單配對啟用 SQL Sync、規格制定建實體表）。NoCode 子系統用的是 SQLite，不走這裡。**佈建憑證不需要 superuser**（`SYNC_PG_ADMIN_URL` 指向 `<db_user>_prov`，只要 LOGIN+CREATEDB+CREATEROLE），健康狀態看 `/organizations/databases` 頂端的「資料庫健康狀態」——登記與實體庫不一致、孤兒庫、孤兒角色、佈建連線異常都在那裡，也在那裡修。完整規則見 `dev-notes/ORG_DATABASE_LIFECYCLE.md` |

### 驗英文介面：沒有切換語系的 API，要改 DB 欄位（2026-08-29 試誤）

`/api/personal-settings/language` **不存在**（回 `{"error":"Not found"}`）。
語系來源是 `auth_interceptor.py:115` 的 `current_user.interface_language`
（欄位在 `users.interface_language`，null 時回退企業設定）。
自動化驗收英文介面的做法是直接改 DB 再重登，**驗完記得改回 NULL**：

```bash
PGPASSWORD=postgres123 psql -h localhost -U beakplatform -d beakplatform_dev -q -c \
  "UPDATE users SET interface_language='en' WHERE email='admin@system.local';"
# 重跑 quick-login 取得新 session 後抓頁面，檢查 body 內殘留的中文
# （HTML 註解要先用 re.sub(r'<!--.*?-->', '', ...) 去掉，否則註解裡的中文會誤報）
PGPASSWORD=postgres123 psql -h localhost -U beakplatform -d beakplatform_dev -q -c \
  "UPDATE users SET interface_language=NULL WHERE email='admin@system.local';"
```

判讀基準：body 內只剩**資料值**（使用者 display_name 之類）是中文才算通過。

### 每個 session 也會猜錯一次的 URL（2026-08-20 補）

blueprint 的 `url_prefix` 與模組名不一致，照模組名猜必 404：

| 想開的頁 | 錯的猜法 | 實際路徑（都要加 nginx 的 `/beakplatform` 前綴） |
|---|---|---|
| 表單中心 | `/form-workflow/center` | **`/forms/center`**（`form_workflow/web/__init__.py:17` 的 prefix 是 `/forms`） |
| 流程**設計器** | `/forms/workflows` | **`/forms/workflows/<workflow_template_secure_code>`**；不帶 sc 的是**列表頁**，兩者都回 200，很容易誤判成「設計器沒壞」 |
| 配對 API | `/api/form-workflow/...` | **`/api/mappings/...`** |
| **提交表單觸發流程（已登入）** | `/api/form-workflow/submit` | **`/api/form-center/submit`**（POST JSON，`@csrf.exempt`，body 要 `published_secure_code` + `subject` + `form_data`；少了 `subject` 回 400）。**需要登入 session** |
| **外部系統觸發流程（無 session）** | `/api/form-center/submit` | **`/api/trigger/form`**（見下方專段）——前者掛 `@module_access_required`，第一行就檢查 `current_user.is_authenticated`，外部拿 API Key 打**恆 401** |
| 弱點管理各頁 | `/vuln-lifecycle/assets` | **`/vuln/assets`**（`vuln_lifecycle/web/__init__.py` 的 prefix 是 `/vuln`；API 那邊反而是 `/api/vuln-lifecycle/...`，兩者不一致） |
| 規格制定的 API | `/api/spec-formulate/specs` | **`/api/spec-formulate/schema/specs`**（路由全寫在 `schema.py` 的 `register(bp)` 內，bp 是 `schema_bp`） |
| **表單**設計器 | `/forms/form-designer` | **`/forms/templates/<form_template_secure_code>`**（`/forms/templates/new` 是新建，兩者都要設計權限——純 EMPLOYEE 開會 **403**，用 ORG_ADMIN 或持 FORM_DESIGNER 的帳號） |
| 流程設計器**底圖**清單 | `/api/form-workflow/backgrounds` | **`/api/workflows/backgrounds`**（上傳是同一前綴的 `/upload`；`backgrounds.py` 的 blueprint prefix 就是 `/api/workflows/backgrounds`） |
| 企業 logo 的資訊與上傳 | `/api/enterprise-settings/logo` | **`/api/admin/settings/logo`**（`enterprise_settings.py` 的 blueprint prefix 是 `/api/admin/settings`，與檔名不一致） |
| 本人領取自己的 API Key | `/security/api-keys`（那是管理員面） | **`/personal-settings`** 最下方「我的 API Key」區塊；API 是 `/api/my-api-keys`（清單／`<key_sc>/claim`／`<key_sc>/regenerate`），授權條件是**本人**（`applicant_user_secure_code` ＋ `org_secure_code` 雙條件）而不是 permission code |
| 員工替**自己**指定代理人 | 個人設定裡直接建立（2026-09-08 PF-251 第 4 期起已移除，`POST /api/my-proxy-assignments` 與 `/candidates` 皆 404） | **送「代理指定申請單」給代理人同意**：個人設定「我的代理指派」的 [指定代理人] 連到 `/forms/center?fill=<published_sc>`（出廠表單 code `PROXY_REQUEST`／流程 `PROXY_REQUEST_FLOW`，新企業自動種、既有企業跑 `scripts/examples/provision_proxy_request_flow.py --org <org> --apply`）。代理人在表單中心待簽清單按 [同意代理]，`OpProxyGrant` 節點才建 proxy 列（`source_ref=flow:<execution_code>`，執行當下用 `proxyable_regular_assignments()` fail-closed 重驗一次）；[拒絕] 不建任何列。個人設定只剩清單、撤銷（我授出的）與放棄（我代理的）：`GET /api/my-proxy-assignments`、`GET /my-roles`、`POST /<assignment_sc>/revoke`。管理員替別人建代理仍走權限中心「帳號配角色」。規格見 `dev-notes/ROLE_PROXY_ASSIGNMENT_DESIGN.md` 3.9 與第十一節「第 4 期」 |
| 職級職稱／班表這批管理頁 | `/admin/job-levels/`、`/admin/positions/`、`/admin/work-schedules/` | **`/job-levels/`（`/job-levels/matrix` 是職級職稱矩陣）、`/positions/`、`/job-families/`、`/job-titles/`、`/job-approval-categories/`**，只有班表頁掛在 `/admin/settings/work-schedules`（API 才是 `/api/admin/work-schedules`）。不確定就查 `backend/app/security/route_guard_table.yaml` 該 blueprint 的 `- /` 列（2026-09-04 PF-241 驗收時猜錯三個） |
| 職位（任職卡）新增頁 | `/positions/new` | **`/positions/create`**（`web/positions.py` 的 route 是 `/create`；`/new` 回 404 是路徑錯不是守門，2026-09-06 bpserv 驗收猜錯） |
| 帳密登入端點（對非 dev 庫驗登入時，如 fresh install 驗收） | `/login`（回 401） | **`/auth/login`**——GET 登入頁；POST JSON 版 body 是 `account` + `password`（`account` 格式 `username@domain`，例 `admin@system.local`），`@csrf.exempt`。成功回 200，`must_change_password` 帳號會回改密碼 redirect（2026-09-01 PF-168 驗收實測）。dev 庫日常自動化仍一律走 quick-login |

### 外部系統用 API Key 發動表單流程：`/api/trigger/form`（2026-08-13 起）

**這支端點不在任何 manifest、也沒出現在本檔其他地方，是 2026-08-25 誤判過一次才補的。**
當時只查 `/api/form-center/submit`（需登入）就下結論「平台不支援外部觸發」，
實際上通用閘道早就做完了。

| | |
|---|---|
| 實作 | `modules/form_workflow/api/external_trigger.py`（`url_prefix='/api/trigger'`） |
| 規格 | `dev-notes/API_KEY_TRIGGER_SPEC.md`（P1/P2/P3 全部完成） |
| 端點 | `POST /api/trigger/form` 發動；`GET /api/trigger/forms` 列出該 key 可發動的表單 |
| 認證 | `@api_key_hmac_required`（平台 `api_keys` 表，UI 在 `/security/api-keys`） |
| 授權 | `scopes.form_category`（父分類自動含子分類）或 `scopes.form` 直綁 published SC |

**簽章金鑰是 base64 解碼後的 raw bytes**，不是 UI 顯示的那串字（與 od intake 同一個坑，
見上方「HMAC 金鑰是 raw bytes」）。直接拿字串當金鑰恆得 401，而平台對所有認證失敗
一律回同一個 `auth_failed`，從回應完全看不出原因。

可執行的驗證腳本（2026-08-25 實測成功，直接改 `KEY_ID` 就能跑）：
`/opt/BeakVulnRT/tools/trigger_form_probe.py`。實測行為：

```
正常觸發          201 + form_instance_secure_code / serial_number / execution_code
scope 外的表單    404 form_not_found（不洩漏存在與否）
錯誤簽章          401 auth_failed
未知欄位          400 unknown_field + 回傳 allowed_keys 供對接
```

**`extract_schema_field_keys` 曾對 textarea 的整數 `rows` 屬性崩潰**
（form.io 的 table 元件 rows 是二維陣列、textarea 的 rows 是整數），
含 textarea 的表單一律 500。2026-08-25 修（commit `14e97f7b`）。
同一個函式也被 `nocode_builder/web/portal_public.py` 兩處使用（portal 公開表單提交，
對 Internet 開放），而表單中心 `fc_fill.py` **不使用**它——
所以瀏覽器提交一直正常，這個 bug 才存在半個月沒被發現。

**`od_intake_events.case_secure_code` 指向 `fw_workflow_instances`，不是 form_instance。**
要拿到表單得再 join 一層，直接 join `fw_form_instances` 會全部 NULL：

```sql
FROM od_intake_events e
JOIN fw_workflow_instances wi ON wi.secure_code = e.case_secure_code
JOIN fw_form_instances fi     ON fi.secure_code = wi.form_instance_secure_code
```

**案件有兩個編號，UI 上顯示的是後者**：`fw_form_instances.serial_number`
（`OD-20260809-4A6CA828`）與 `fw_workflow_instances.execution_code`
（`OD-20260809-0003`）。用畫面上看到的號碼查 `serial_number` 會查不到。

---

## 備忘

### Forgejo
- **Repo**: http://192.168.0.16:3000/forgejoadmin/BeakPlatform（URL 與 API Token 見全域 CLAUDE.md）

### 開發測試登入（本開發機獨有）
- **快速切換帳號（免密碼）**: `http://192.168.0.16:7000/beakplatform/dev/quick-login`，點帳號即登入
- **用完必按該頁 [登出] 按鈕**（曾發生登出不乾淨，該按鈕即為補救設計）
- **自動化一律走 quick-login，不要用帳密登入**：現有測試帳號的密碼多已失效
  （`admin-ethanyu@beluga.com` / `ApiKeyTest2026` 2026-08-03 實測 401），
  SYSTEM_ADMIN `admin@system.local` 密碼不明——**猜密碼會觸發鎖定**
- curl 快速切換**任意帳號**（免密碼免 CSRF，POST JSON 版，E2E 多帳號矩陣測試首選）:
  ```bash
  BASE=http://192.168.0.16:7000/beakplatform
  USC=$(psql -h localhost -U beakplatform -d beakplatform_dev -t -A \
    -c "SELECT secure_code FROM users WHERE email='ethanyu@beluga.com' AND is_deleted=false;")
  curl -s -c cj.txt -X POST "$BASE/dev/quick-login" \
    -H 'Content-Type: application/json' -d "{\"user_id\":\"$USC\"}"
  # SYSTEM_ADMIN admin@system.local     的 user_id 是 nH5liUKQikH1NM2osVVXuF
  # ORG_ADMIN admin-ethanyu@beluga.com 的 user_id 是 jIYEQ-_lZMZNBkVy-hijal
  # EMPLOYEE ethanyu@beluga.com（持 FLOW_DESIGNER + SECURITY_STAFF，測 Key2 場景用）
  #          的 user_id 是 FhsmtyPjsnXYotN-iz_Q-X
  # 廠商登入頁（/auth/org/<domain>/public/login，POST JSON {"email","password"}）的測試帳號
  # （2026-09-02 建）：gg@gmail.com 在 BELUGA / SYSTEM 各一個、BELUGA 另有
  # gg@other-vendor.com，密碼都是 VendorTest2026#Ok；在哪家的 URL 登入就落在哪家
  # 挑測試帳號的通則：對照「該帳號實際持有的角色」與場景所需權限來選，
  # 不要憑 user_type 或帳號名假設——角色會合法改變授權結果，
  # 選錯樣本會得到假通過（2026-09-02 驗 ACL 場景踩過）
  ```
- **範例企業（`scripts/seed_test_companies.py --run` 建的三家）**，2026-09-02 起有完整人資結構：
  部門成員關係與部門主管角色（每人 `DEPT_MEMBER`＋`DEPT_EMPLOYEE`／`DEPT_MANAGER@部門`，直屬主管由此推導；2026-09-05 PF-247 第 4 期前是任職卡指標，既有企業補種走 `--sync-dept-roles`，冪等）、6 核決類別 × 10 職等上限、兼任與代理職位、合約含 `form_workflow`。
  **建好後預設 `admin@<domain>` 會被初始設定精靈擋住**（兩帳號制，PF-224 要自動化）；
  GHTRAVEL 已過精靈：`admin-gh.admin@ghtravelexample.com.zz` / `GhAdmin2026#Test`
  （quick-login user_id `S_m2bCV9HTkAKGbYzBaODr`），BRIGHTCODE／SHIELDEDGE 仍是
  `admin@<domain>` / `Test1234!` 未過精靈。GHTRAVEL 與 BRIGHTCODE 已用
  `scripts/examples/provision_hr_lookup_demo.py --org <code> --apply` 佈建「差旅費申請（人事取值示範）」：
  領隊翎柏瑞（quick-login `oTBMqW0roaniN3UFhyKmZh`，L200）申請 30 萬 → 派直屬主管燁凱文（L500）、
  500 萬 → 派處長霄雅慧（L700）。提交走 `POST /api/form-center/submit`，body 要 `published_secure_code`
  （GHTRAVEL 是 `NfrmHdR6pVWLo2L2eCttCA`）+ `subject` + `form_data`
  **管理員帳號不要自己用 SQL 撈**：兩帳號制的企業裡
  `SELECT ... WHERE user_type='ORG_ADMIN'` 可能撈到不能登入的那一筆（原始 admin），
  quick-login 回 401（2026-08-31 在已刪除的 LION 企業踩過）。用上面寫死的 user_id。
- 常用 API 回應格式備忘：`GET /api/menu` 回 `{menu:[...]}`（樹狀，key 是 `menu` 不是 items）；
  權限中央 API（/api/permissions/*）的企業參數名是 `org_code`（不是 org）
- curl 打非 exempt 的 POST API 需要 CSRF token，從任一登入後頁面的 meta 取（登入回應不含 token）：
  ```bash
  TOKEN=$(curl -s -b cj.txt -c cj.txt "$BASE/dashboard" | grep -o 'csrf-token" content="[^"]*' | cut -d'"' -f3)
  curl -s -b cj.txt -X POST "$BASE/api/xxx" -H 'Content-Type: application/json' -H "X-CSRFToken: $TOKEN" -d '{...}'
  ```
  **沒帶 token 時回的是 400，不是 403 —— 這會蓋掉授權判定**（CSRF 檢查在
  `before_request`，比 decorator 早）。跑「哪種身分打得進去」的矩陣時若忘了帶
  token，會看到每一種身分都回 400，看起來像守門完全沒生效，實際上根本還沒走到
  守門那一步（2026-08-31 驗 PF-185 時踩過）。**測授權一律先取 token。**
  **表單型 POST（非 API，如 `/positions/create`）的 token 是頁面裡的 hidden input**，
  `grep -o 'name="csrf_token" value="[^"]*'` 在有 modal 的頁面會命中**兩個**，不加 `head -1`
  會把兩個 token 串成一個送出、回 400（2026-09-03 驗 PF-229 第三期時踩過）。

### bpserv 測試機（2026-09-01 建立，2026-09-02 PF-211 後重裝，install.sh 全新安裝的驗證環境）

**【bpserv 部署凍結，Ethan 2026-09-13 定調】每個任務做完不要跑 `--update`。**
`.16`（dev）這一波修改全部完成後才一次更新 bpserv，中間的任務只做 dev 驗收與 commit。
每個會影響既有環境的任務要把「`--update` 之後還要手動做的事」記進下表，
解凍時照表逐項執行，漏一項就是靜默的半套升級：

**2026-09-13 晚間 Ethan 改定：解凍方式是「`--uninstall` 後從 GitHub 全新安裝」，不跑 `--update`。**
下表各列在全新安裝上自然成立（集團共用 DB 已不存在、SysSqlExecutor 定義出廠即新名、
NOCODE_BUILDER_MENU 由 install.sh 寫入），只剩 PF-266 的 origin 格式驗證改在重裝後補跑一次 `--update` 驗。
表保留供考古。

| 累積待做（解凍時依序執行） | 來源 | 指令／說明 |
|---|---|---|
| 退役集團共用 DB：軟刪選單、DROP 兩表、DROP 六欄 | PF-269（2026-09-13） | `venv/bin/python scripts/retire_cg_shared_db.py --dry-run` → `--apply`；細節 `dev-notes/CONGLOMERATE_SHARED_DB_RETIRED.md` |
| SqlExecutor → SysSqlExecutor：節點定義、graph／發行快照／執行紀錄字串、系統企業授權、節點 icon 路徑 | PF-254 第一階段（2026-09-13） | `venv/bin/python scripts/migrate_sqlexecutor_to_sys.py --dry-run` → `--apply`（冪等，第二次全 0）；bpserv 沒有 node展覽館 示範流程，預期只有 node_definitions 1／系統企業授權 1 |
| 驗 PF-266（origin URL 自我修復）：**這批改了 `install.sh` 本身，`--update` 要跑兩次** | PF-266（2026-09-13） | 第一次 `--update` 前先把 bpserv 的 origin 改回舊格式重現：`git -C /opt/BeakPlatform remote set-url origin "https://<PAT>@github.com/ethan-beakmask/BeakPlatform.git"`，第二次 `--update` 應印「remote URL 為舊格式（缺 x-access-token: 前綴），自動修正」且不再要密碼；驗完 `note_task_status(ref="PF-266", status="completed")` |
| `OD_SA_JWT_SECRET` 補產生：**bpserv 已於 2026-09-13 手動補**（`.env.bak-20260913-odsa` 是補之前的備份），`--update` 應印不出「缺少 OD_SA_JWT_SECRET」而直接跳過；驗的是新段落的冪等，不是補值 | 讀者路徑驗證（2026-09-13，見 `dev-notes/SEC_STACK_ARCHITECTURE.md` 第 12 節「讀者路徑端對端驗證」） | 跑完 `--update` 後 `sudo grep -c '^OD_SA_JWT_SECRET=' /opt/BeakPlatform/.env` 必須是 1 |
| NoCode 解除隱藏 | PF-271（2026-09-13） | bpserv `.env` 加 `NOCODE_BUILDER_MENU=on` 後 `sudo systemctl restart beakplatform`；bpserv 沒有那三筆選單，重啟時模組同步會自建；DemoSOC 無 nocode 合約，選單不會出現是預期 |

（下表「部署狀態」欄記的是凍結前最後一次 `--update` 的狀態，凍結期間不會再往前推。）


Ethan 提供的 Proxmox VM，用途是驗證「讀者照裝」路徑與 fresh 環境行為，
**憑證都是測試用途、Ethan 明示可放本檔**（本檔不推 GitHub）：

| 項目 | 值 |
|---|---|
| SSH | `sshpass -p 'P@ssw0rd' ssh ethan@192.168.0.66`（sudo NOPASSWD；Ubuntu 24.04，hostname bpserv，固定 IP netplan + cloud-init 網路接管已停用；**系統時鐘是 UTC**，`uptime` 顯示的時間比台北慢 8 小時） |
| 平台 URL | `http://192.168.0.66:8000/beakplatform`（**80 埠是 nginx default site 回 404，必帶 :8000**；無前綴也 404） |
| 系統企業 | code `SYSTEM`，SYSTEM_ORG_CODE＝`sys-1271967103b6`（install.sh 隨機產生，**每次重裝都會變**，與 dev 的 `system.local` 不同） |
| 帳號 | 出廠兩個：`admin@sys-1271967103b6`（SYSTEM_ADMIN，**密碼 2026-09-02 已改為 `BpservTest2026Changed`**，must_change 已清）與 `enterprise@sys-1271967103b6`（ORG_ADMIN，ADM001，is_original_admin，密碼仍是 `BpservTest2026BpservTest2026`、仍 `must_change_password`）。2026-09-02 重裝前的 `ethan` / `admin-ethan` 已不存在 |
| 示範企業 DemoSOC（2026-09-02 PF-125 走查建立） | code `DEMOSOC`，domain `demo-soc.example`，sc `ugRNno6lA97ZicqIbBvBEb`；合約兩份（含 form_workflow + open_defense，第一份 start 2026-09-02 建立當下被 UTC 日界判「尚未生效」，見 PF-125 追記）。帳號：`soc1@demo-soc.example`（EMPLOYEE，持 SECURITY_STAFF + SOC_SUPERVISOR）與 `admin-soc1@demo-soc.example`（ORG_ADMIN），密碼同為 `DemoSoc-Staff2026#`；原始 `admin@demo-soc.example` 已停用。三個 OD 流程由 `provision_od_intake_for_org.py` ＋ `provision_od_workflow_variants.py --with-routing` 建出，SOC 團隊版路由已啟用（sev>=3）；intake API Key `ak_475b051bb6c2f424`（secret 在 `/opt/tmp/verify/20260902-pf125-bpserv-soc.log`）。`.env` 已加 `OD_EDL_OUTPUT_DIR=/opt/BeakPlatform/data/edl`、`OD_EDL_ALLOWED_IPS=192.168.0.16,192.168.0.10`（無 cron，EDL 要手動跑 `scripts/cron/od_render_edl.py`）。已完成案件 OD-20260901-0001（封鎖 203.0.113.42）／0002（放行 198.51.100.77）。**2026-09-13 起另有防禦節點憑證**（`od_node_pairing.py` 發的）：API Key `ak_38dc044f67de1601`（scope coraza/suricata/vector）＋服務帳號 `sa_defense_node_21_36a0bd`，開通字串與 secret 在 `/opt/tmp/verify/20260913-od-node-bpserv-demosoc.log`；當天用 `.21` 待命機端對端驗過後已把 `.21` 指回 `.16`，這組憑證現在沒有節點在用。`.env` 同日手動補了 `OD_SA_JWT_SECRET`（此前缺，SA 登入恆 500）。當天留下的案件 OD-20260913-0001～0004（0001／0004 已結案，0002／0003 仍 WAITING） |
| 登入 | 無 quick-login（dev 機限定），走 `POST /auth/login` JSON（`{"account":"admin@sys-1271967103b6","password":"..."}`，成功回 200 + 改密 redirect，錯密碼 401）。**chrome-devtools 也走這條**：登入頁是三段驗證碼表單，不要填表單，先 `new_page` 開 `/auth/login`，再 `evaluate_script` 內 `fetch('/beakplatform/auth/login', {method:'POST', ...JSON})` 建 session，之後 `navigate_page` 到目標頁即已登入（2026-09-04 PF-239 實測） |
| DB | `sudo -u postgres psql -d beakplatform`（beakplatform 帳號密碼同 dev 慣例）。**經 sshpass 遠端下 SQL 一律用 heredoc**（`ssh ... sudo -u postgres psql -d beakplatform -tA <<'SQL' ... SQL`）：單行 `psql -c 'SELECT ...'` 的引號會被遠端 shell 拆掉，症狀是 `Peer authentication failed for user "<SQL 的第二個字>"`（2026-09-04 撞了三次） |
| 服務 | `sudo systemctl restart beakplatform`（unit 名無 `-dev`） |
| 重裝（讀者路徑，2026-09-02 實跑成功） | 先 `echo YES \| sudo bash /opt/BeakPlatform/scripts/install.sh --uninstall`（會刪目錄、DB、服務帳號，不備份），再用 PAT 從 GitHub API 抓 install.sh：`curl -sfL -H "Authorization: Bearer $PAT" -H "Accept: application/vnd.github.raw" "https://api.github.com/repos/ethan-beakmask/BeakPlatform/contents/scripts/install.sh?ref=main" -o install.sh`，然後 `sudo env GITHUB_TOKEN=$PAT ADMIN_INITIAL_PASSWORD=<密碼> bash install.sh`（環境變數要走 `sudo env`，不要 `sudo -E`；全程約 3 分鐘，pip 佔大半）。重裝後 SYSTEM_ORG_CODE 會變，記得回來改本表 |
| 更新 | `sudo bash /opt/BeakPlatform/scripts/install.sh --update`（拉 GitHub 過濾鏡像；`.git/config` 的 origin 已帶 PAT，不會再問 token。**PAT 於 2026-09-13 前已提早失效**——原記載的到期日 2026-10 初不可信，症狀是 `--update` 第 1/4 步 `could not read Password`；同日已換新 PAT。**寫 origin URL 一律用 `https://x-access-token:<PAT>@github.com/...`**，`https://<PAT>@github.com/...`（install.sh:434 的寫法）只有 username 沒有 password，git 在無 tty 環境必定停下來要密碼而失敗） |
| 發信服務（2026-09-02 PF-218 收尾） | bpserv 沒裝 E-MailRelay，`mail_primary_service=smtp`、不併發；系統級 SMTP 設定組 `lionsecbot`（sc `isB6udCQ3VKrwoAHRG1PL8`，Gmail 應用程式密碼，is_default）。忘記密碼等系統信會真的寄出（自寄到 `lionsecbot@gmail.com`）。指定 E-MailRelay 會被 400 擋下，這是預期行為不是故障。2026-09-04 PF-228 起 DemoSOC 也有企業層設定組 `W9jW0-0t2oRt9xe4nabnDw`（由 `seed_smtp_test_config.py --orgs DEMOSOC` 從 SYSTEM 複製，admin-soc1 實寄成功） |
| 部署狀態 | **2026-09-13 00:33–00:38 以 GitHub `d430b383`（＝dev `aa5f3888`，PF-256＋PF-262＋PF-264）跑兩次 `--update`，4/4 通過**：無 schema 變更。**這批改了 install.sh 本身，所以必須跑兩次**——第一次是舊 shell 配新 Python，`ensure_org_databases` 回 `{skipped: True, reason: SYNC_PG_ADMIN_URL 未設定}`並只印 WARNING 不中止（這是刻意設計）；第二次新 shell 才建佈建角色、補寫 `.env` 兩個變數，`ensure_org_databases` 才變成 `{checked: 2, ok: 2, failed: 0}`。結果：`beakplatform_prov`（super=f／createdb=t／createrole=t，**非 superuser**）、`SYNC_PG_ADMIN_URL` 指向它、`SYNC_CREDENTIAL_KEY` 自動產生；org_1／org_2 owner=`bfadmin_N`、**pgcrypto extowner 也是 `bfadmin_N`**（去 superuser 化實證，PG16.15 上成立）、PUBLIC CONNECT 已撤。驗收：建企業 PF256T 回應帶 `database:{db_name:org_3,status:ok}`，硬刪除後 org_3 與 `bfadmin_3`／`bfsync_3` 零殘留；DROP org_2 造降級後讀取類 API 200 回空、寫入類 503「企業專屬資料庫目前無法使用」、頁面仍 200，健康頁顯示 `missing_database` ＋降級紀錄（時間／次數／PG 原文）；UI [補建] 實際點過（confirm 1 次、provision 1 次、異常歸零）；孤兒庫與孤兒角色的偵測與刪除全通過，fail-closed 三條（非 `org_` 命名 400、企業仍存在 400、使用中角色拒絕）。回歸基準 OD-20260903-0002 仍 RUNNING、`node-FormAdapter-L2` 仍 WAITING，與部署前一字不差。**已知邊界：孤兒庫的 owner 不是 `bfadmin_N` 時（例如歷史上用 postgres 手動建的）`beakplatform_prov` 無權 DROP，UI 只回「刪除孤兒資料庫失敗」不說原因，要 superuser 手動刪。**憑證 `/opt/tmp/verify/20260913-pf256-bpserv.log`。更早：**2026-09-08 03:0x 以 GitHub `c4e5ca35`（＝dev `39e74a62`，PF-251 四期＋補丁 3a-1）跑 `--update` 4/4 通過**：手動七行 ALTER（`user_role_assignments` 五欄位＋部分索引、`fw_approval_records.acted_as_kind`，見 `scripts/migrate_proxy_assignments.py` 檔頭）；`migrate_proxy_assignments.py --apply`（roles_created 2／renamed 4／gate_snapshots 1／proxy_roles_deleted 4／condition_retired 1，delegation 與 proxy_rows 皆 0，第二次全 0）；**`provision_proxy_request_flow.py --org demo-soc.example --apply`**（`--org` 只吃 secure_code 或 domain_name，**不吃企業 code**；`--update` 不回填既有企業的出廠表單，漏跑則個人設定的 [指定代理人] 不渲染）。`OpProxyGrant` 節點定義由 SQL extras 自動帶入、不必手動種。驗收：回歸基準 OD-20260903-0002 的 WAITING 任務部署前後一字不差（soc1 200／admin-soc1 403）；`/delegations/`、`/api/my-delegations`、`/api/my-proxy-assignments/candidates` 皆 404；端到端跑完一張代理指定申請單（soc1 送單→DYNAMIC 解析→admin-soc1 同意→建 2 列 proxy→結果寫回，驗完已清）。系統企業刻意未種出廠申請單。憑證 `/opt/tmp/verify/20260908-pf251-bpserv.log`。更早：**2026-09-06 00:10 以 GitHub `056a052d`（＝dev `09014ce7`，PF-247 五期＋4a）跑 `--update` 4/4 通過**：手動 SQL 兩句（`ALTER TABLE fw_approval_records ADD COLUMN acted_as_role_code VARCHAR(50)`、`ALTER TABLE employee_positions DROP COLUMN direct_manager_secure_code`）已下；驗收：既有 OD-20260903-0002 WAITING 任務（ROLE 無 spec key＝舊路徑）soc1 200／admin-soc1 403 與修前一致；`/positions/`、`/positions/create` 無直屬主管欄位；`/api/workflows/data/units` 200（DemoSOC 1 個單位）、`/data/roles` 帶 `role_type`。**ALTER 後第一個登入請求 500**（`psycopg2 SSL SYSCALL error: EOF detected`，連線池撞到失效連線），重試即 200，不是回歸——以後下 ALTER 一律接著 restart 再驗。角色@單位已於 2026-09-06 13:38 以 PF-248 在 bpserv 實測（臨時建部門＋三帳號跑矩陣 #1／#7／#2、self_target 預設退回、`resolve_direct_manager()`，全 PASS，測資已清），憑證 `/opt/tmp/verify/20260906-pf248-bpserv-roleunit.log`；順帶抓到 **PF-249**（刪單位不連帶軟刪除單位角色指派與成員關係，bpserv 殘留已 SQL 清掉）。憑證 `/opt/tmp/verify/20260906-pf247-bpserv.log`。更早：**2026-09-04 20:00 以 GitHub `e2525e78`（＝dev `94c91285`，含 PF-71）跑 `--update` 4/4 通過（PF-71）**：無 schema 變更。admin-soc1 登入後 `/delegations/create` 200 且含 `allowed_form_templates` 多選。憑證 `/opt/tmp/verify/20260904-pf71-bpserv.log`。更早：**2026-09-04 18:07 以 GitHub `e63bc7eb`（＝dev `26b48416`）跑 `--update` 4/4 通過（PF-235）**：create_all 建出 `holiday_calendars`／`holiday_calendar_entries`；手動 ALTER 補 `schedule_holidays.holiday_calendar_secure_code`＋索引；`seed_default_work_schedules.py --apply` 結果 exists=1（DemoSOC 原有 `PF239DemoSocStdSched01` 為預設）、系統企業跳過。admin-soc1 實測 fetch-taiwan 2026 → 201（draft 22）、發佈到預設班表 inserted 22、假日列 22 且帶來源名稱、企業行事曆 2026-01-01 出現開國紀念日、底稿編輯頁 200、班表頁有「假日表（企業級）」區塊。**留下已發佈的 2026 政府假日表**（sc `B6c_XrYkLxGU4dhzEpe34u`）供後續驗收。憑證 `/opt/tmp/verify/20260904-pf235-bpserv.log`。更早：**2026-09-04 08:31 以 GitHub `e1689fd9`（＝dev `890105b9`，程式內容同 `4004deb0`＝dev `1b656545`）跑 `--update` 4/4 通過（PF-231／PF-243，本單 PF-244）**：無 schema 變更。驗收 A（AUTH-04）：出廠 `enterprise@sys-1271967103b6` 因 `is_original_admin` 且精靈未過，**AUTH-03 先於 AUTH-04 生效**，dashboard 與 `/api/menu` 都 302 到 `/admin/initial-setup`，不是改密頁——這是程式順序的預期行為，**驗 AUTH-04 要用非原始管理員帳號**：改以 `soc1` 暫設 `must_change_password=true`（驗完已還原 false）實測 dashboard／`/calendar/me` 302 到改密頁、`/api/menu` 403 `password_change_required`、改密頁 200。驗收 B（PF-231）：admin-soc1 以 API 建密碼留空成員 201、`password_notification.sent=true`、DB 該列 `must_change_password=t`、`backup_email_1` 正確，隨後 DELETE 200 軟刪除（`pf231testc0833`）。憑證 `/opt/tmp/verify/20260904-pf244-bpserv.log`。更早：**2026-09-04 02:12 以 GitHub `f4f3146d`（＝dev `e49d9d2a`）跑 `--update` 4/4 通過（PF-228／PF-242）**：無 schema 變更；隨後種入 DemoSOC SMTP 設定組並實寄成功（憑證 `/opt/tmp/verify/20260904-pf228-bpserv.log`）。更早：**2026-09-04 01:37 以 GitHub `6535eb5b`（＝dev `88740182`）跑 `--update` 4/4 通過（PF-241）**：「平台權限: permissions_created 68」，bpserv 資源型 code 集合與 dev 完全一致（各 116）、sys_perms 62→130（出廠計數列第 8 欄從此是 130）；admin-soc1 `GET /api/admin/work-schedules` 200（修前 403），chrome-devtools 開 `/admin/settings/work-schedules` 列出「標準班表（PF-239 驗收）」，`/job-levels/`、`/positions/`、`/job-families/`、`/job-titles/`、`/job-approval-categories/`、`/delegations/`、`/api/duties/`、`/api/roles/` 全 200。憑證 `/opt/tmp/verify/20260904-pf241.log`。**原子 PF-241 寫的 `/admin/job-levels/`、`/admin/positions/` 不存在**（404 是路徑錯不是守門，真實路徑見下方 URL 猜錯表）。更早：**2026-09-04 01:00 以 GitHub `9e8e9257`（＝dev `750c306c`）跑 `--update` 4/4 通過（PF-239）**，本期無 schema 變更。驗收五項全過（憑證 `/opt/tmp/verify/20260904-pf239-bpserv.log`）：soc1 個人設定頁有「我的代理授權」、LEAVE 事件回的 `delegation_hint.create_url` 指向 personal-settings；admin-soc1 以代理身分簽 OD 案件後 `fw_approval_records.delegate_from_*`＝soc1、案件中心簽核歷程顯示「（代 資安一號 簽核）」（**這段歷程只在案件仍有待簽節點且本人可簽時才載入**，已結案的案件看不到，`sc-cases.js` 只在 `waiting_node && can_act` 時抓 pending-tasks 詳情）；非全天請假 `adjusted_periods=["13:00-18:00"]`；time-context admin 200／soc1 403；設計器簽核節點「打開設定 → 基本設定」分頁有「簽核逾時」。**順帶抓到 PF-241**：fresh install 缺 17 種資源型 permission code，`/api/admin/work-schedules` 對 ORG_ADMIN 恆 403，DemoSOC 預設班表 `PF239DemoSocStdSched01`（STD，週一～五 09-12／13-18）因此是 SQL 直插的。留下的測試資料：代理授權 soc1→admin-soc1（FULL，至 09-05）、案件 OD-20260903-0001（COMPLETED，allow）／0002（L2 待簽，資安主管）。另：bpserv 沒有獨立 executor unit，節點由 gunicorn 進程內撿起（`systemctl list-units beakplatform*` 只有一個 unit，這是正常的）。更早：2026-09-03 07:41 以 GitHub `70f5de6c`（＝dev `d7660a93`）跑 `--update` 4/4 通過（PF-232）**，隨後 `seed_missing_platform_menus.py --apply` 補種 `calendar_menu` / `calendar` / `calendar_me` 三筆選單（Key2 SYSTEM＋DEMOSOC 各 4 筆），並手動對 `schedule_adjustments` 補 `calendar_event_secure_code` 欄位＋索引＋`(user_secure_code, adjust_date, adjust_type)` 唯一約束（create_all 三者都不補；dev 庫的約束是 PF-168 收斂時就有的，bpserv 是 fresh 建的所以缺）。soc1 建 LEAVE 事件 201 → `schedule_adjustments` 同步列出現 → DELETE 200 → 同步列軟刪除，憑證 `/opt/tmp/verify/20260903-pf232-bpserv-calendar.log`。更早：2026-09-02 16:18 以 GitHub `f29e60f1`（＝dev `b45848de`）跑 `--update` 4/4 通過。更早：以 GitHub `6ea7fde3`（＝dev `3ad7bc23`，PF-211）全新重裝，出廠計數 `17\|17\|55\|0\|6\|25\|5\|62\|13\|2` 與 dev 拋棄式庫走 `init_database.sh` 完全一致；重裝後又跑過一次 `--update`（新的 1/4~4/4 路徑）確認冪等。**不要再用 tar/scp 手動同步 dev 檔案**——那是 PF-211 之前沒有可靠更新路徑時的權宜做法，現在直接 `push github` 後 `--update` |

**`install.sh --update` 是「舊 shell 邏輯 ＋ 新 Python」**（2026-09-02 實測）：
`git reset --hard` 換掉的是磁碟上的 install.sh，記憶體裡正在跑的仍是舊版
（bash 持有舊 inode），所以某次更新若改了 install.sh 本身，那些 shell 層變更
要**下一次** `--update` 才會生效。驗新的 shell 路徑一律跑兩次 `--update`。

### open_defense / 資安堆疊（備忘已移出，2026-08-30）

動 `modules/open_defense/`、查事件、或改 `.20` 的設定之前先讀：

| 要做什麼 | 讀哪份 |
|---|---|
| 平台側架構、intake、路由、案件、處置中心 | `dev-notes/OPEN_DEFENSE_ARCHITECTURE.md`（第 13 節是從本檔移入的操作備忘：ClickHouse 查詢、三種處置流程、protected targets、intake HMAC 金鑰、EDL 黑名單） |
| `.20` 主機（Vector / Suricata / CrowdSec / od-bridge / ClickHouse）與埠、SSH、風險定調 | `dev-notes/SEC_STACK_ARCHITECTURE.md`（第 11 節同上） |
| **`.20` 從 2026-09-11 起是浮動服務 IP**：真 sec-vm 的管理 IP 是 **`.21`**、備援機 `.13`，誰持有 `.20` 誰在服務（cloudflared＋od-bridge 只在持有者上跑）。維運 ssh 走 `.21`／`.13`，切換一律用 `ITHome2026-WAF/failover.sh`，不要手動改 netplan 或 `ip addr` | `dev-notes/SEC_STACK_ARCHITECTURE.md` 第 12 節「熱備（warm standby）切換」 |
| `.20` 設定檔權威 | **`ITHome2026-WAF/`**（2026-09-10 起；`.20` 的部署在 `.20:/opt/ithome2026-waf`，只有 `.env` 與 `generated/` 是主機專屬）。改設定＝改 `ITHome2026-WAF/` → rsync 到 `.20:/opt/ithome2026-waf` → `sudo bash install.sh --reconfigure`。舊的 `sec-vm-bootstrap/` 已退役封存在 `dev-notes/archive/sec-vm-bootstrap-retired-20260910/`（`.20` 本機是 `~/sec-vm-bootstrap_RETIRED_20260910`） |

**讀者版一鍵安裝在 repo 頂層 `ITHome2026-WAF/`（2026-09-10 起，會推 GitHub）**：
平台端配對腳本 `scripts/od_node_pairing.py`，讀者文件 `docs/install/ithome2026_waf.md`。
**`.20` 已於 2026-09-10 換裝成 defense-node**（cloudflared 也在 `.20` 上跑、
`app.beakmask.org` 對外），tunnel 現況、`.13` 測試節點、驗收步驟都在
`dev-notes/SEC_STACK_ARCHITECTURE.md` 第 12 節。

**留在本檔的只有這條**：以下六個檔案是各自領域的**唯一實作**，
新增功能一律加在這裡，**不要各自重寫**（繞過的後果寫在上面兩份文件裡）：

```
modules/form_workflow/services/task_authorizer.py       簽核授權（判定點 12 處）
modules/open_defense/services/routing_service.py        intake 事件 -> form_template 路由
modules/open_defense/services/payload_profile_service.py 原生 payload 正規化
modules/open_defense/services/protected_target_service.py 封鎖目標保護清單（PF-83）
modules/open_defense/services/edl_service.py            平台端 EDL 黑名單（PF-154）
wf-dnd-nodes.js::resolveNodeIconUrl()                   流程設計器節點圖示 URL
```

**共同軸線 6 個 key 是相容性契約**：`severity_id` / `actor_ip` / `target_host` /
`source_system` / `finding_rule_id` / `occurred_at`。SLA、聚合降噪、風險分數、
處置中心清單全部讀這組，**改名等於同時弄壞四個機制**。

**事件的真實權威是 `.20` 的 ClickHouse，不是平台的 `od_intake_events`**——
後者是被 vector 全域 throttle（8 筆/60 秒）過的子集，
做任何攻擊面統計一律查 ClickHouse。

### NoCode Builder / Portal（備忘已移出，2026-08-30）

**動 `modules/nocode_builder/`、`/public/portal/` 或 Page IR 之前，
先讀 `dev-notes/NOCODE_PORTAL_NOTES.md`**（317 行，原本在本檔）。
裡面是「不讀就會做錯而且不報錯」那類：2026-08-03 定案的架構原則
（子系統資料自給自足、跨界解析一律 fail-closed）、兩個帳號世界的分離、
現有示範子系統與 portal 測試帳號、`portal.db` schema 版本、
頁面存活的雙路徑 OR 判定、三個版面引擎、共用元件的展開點，
以及 NoCode 選單已於 2026-09-13 解除隱藏的現況與過程。
**已知資安缺口見 PF-271，鐵人賽期間（至 2026-10）不修 nocode 程式碼，看到不要當新發現回報。**

規格另見 `dev-notes/PORTAL_ACCOUNT_SPEC.md`、`dev-notes/PAGE_IR_SPEC.md`、
`dev-notes/SHARED_COMPONENTS_SPEC.md`、`dev-notes/codex_spec/portal.md`。

### SQL Sync：worker 是獨立服務，且啟用後不可關閉（2026-08-20 補）

- 服務 `beakplatform-dev-sync-worker`（unit 在 `scripts/systemd/`，2026-08-20 建立）。
  沒跑的話 `fw_sync_queue` 只會累積不會消化
- 配對的 `fw_form_workflow_mappings.sql_sync_enabled` **預設 false**，
  所以 worker 起來後完全沒事做是預期狀態、不是故障
- **啟用後無法關閉**（`api/mappings.py:439` 硬擋）。啟用時會自動在企業獨立資料庫
  （`org_<org_id>`）建 `<table>` 與 `<table>_approvals` 兩張表
- enqueue 掛在 `workflow_engine.py:477`，**流程結束時**才寫（終態資料，含簽核者修改）
- 企業獨立資料庫用 `beakplatform` 帳號**連不進去**（權限不足），
  要查得 `sudo -u postgres psql -d org_<id>`

### 駁回按鈕接了出線就不會記成駁回（設計流程時會踩到）

> 2026-08-30 刪除原本的「一律走到 End 節點收尾（2026-08-27 定調）」原則，
> Ethan 判定已不符實。並行分支的收尾方式以下方「流程 graph 的引擎行為」
> 那張表為準（無出邊節點安全終止該分支，**不要指向 End**）。

`fc-approval.js:336-343` 只在「`target_edges` 為空且 `style=danger`」時才送
`decision='rejected'`，所以**駁回按鈕一旦接了出線，`fw_approval_records.action`
會記成 `approved`**，決策真相只留在流程變數與簽核意見裡。
這是全平台通例——OD 的「人工確認」、`WF2610385E` 的「退回」歷史記錄都是這樣。
設計器決策配對區的提示與 `formadapter_handler.py:148` 的註解描述的就是這個機制：

```
formadapter-decisions.js:321   ... | 未配對 = REJECTED 終態
formadapter_handler.py:148     # 驗證 target_edges 合法性（空 target_edges 表示終態）
```

要不要改成「接了邊也記得住駁回」，見待辦 **PF-164**（先讀完再動，不要自己開工）。

順帶兩個相關事實：
- 表單中心的狀態欄**只表示表單的運行狀態、不含決策狀態**，准駁要點進去看簽核意見
- `REJECTED` 在表單中心顯示「已退回」（`fc-utils.js:93`），
  流程管理頁顯示「已駁回」（`fw-instance-list.js` / `fw-dashboard.js`），
  兩處文字不一致是既有小瑕疵

### 流程 graph 的引擎行為（2026-08-13 實測，設計流程前必讀）

寫或改 `fw_workflow_templates.graph` 之前先看這張表，都是「存得進 DB、跑起來才炸」的：

| 行為 | 事實 | 後果 |
|---|---|---|
| Branch 命中多條規則 | **展開全部命中的規則**（`branch_handler.py:128-147`），不是 first-match-wins | 規則不互斥就會同時走多條路徑 |
| Branch 條件的 `logic` | 是 **group 切分符**：遇 `OR` 或掃到最後一條就收尾。group 內 AND、group 間 OR | 想寫「A 且 B」要兩條都標 AND |
| Branch 比較失敗 | 欄位缺值／型別不符一律回 False（`branch_handler.py:204-208`） | 可以刻意用來做 fail-safe，讓缺值案件落到 fallback |
| Branch 條件裡的變數前綴 | `_resolve_value()` 的快路徑原本只認 `f. / fi. / v. / form.`，`wi. / n. / t.` 全部落到流程變數查詢而**必定回空字串**（2026-08-13 修，改為委派 `replace_variables`） | 這類錯誤不報錯：條件恆 False、案件全部走 fallback，行為看起來還「正常」。用非 `f./v.` 前綴寫條件時務必做一次 mutation 驗證 |
| Branch 的 fallback（**2026-08-30 起**） | `action='route'` 走指定那條；**其餘一律不推進任何出邊**（回 `skip_advance`） | 改版前 `log` 與 `default` 都會走**所有**出邊（選項寫「走第一條出線」但實際走全部）。舊 graph 若還存著 `action='default'`，會自動落到「不推進」那條路 |
| 無出邊的節點 | 安全終止該分支，不報錯也不結束流程（`workflow_engine.py:360`） | 並行分支要靜靜收尾就指向這種節點，**不要指向 End** |
| End 的 `finish_mode` | `detach`（預設，直接結束）／`cancel`（**中止**：結束並取消所有未完成節點，終態記 CANCELLED）／`strict`（等全部完成） | **PF-200（2026-08-31）起 cancel＝中止語意，不再是「正常完工＋清分支」**。正常完工一律用 `detach`——`advance_workflow()` 已有終態檢查，計時分支到期後推不動、無副作用；但 detach 不會作廢等待中的簽核任務（會留在待辦）。舊建議「有並行分支一律用 cancel」已作廢 |
| **子流程裡的 End 三模式都有效（PF-200 起）**，`cancel` 只收「自己＋所有下層」（`scope='subtree'`，沿 `parent_instance_code` 遞迴），**上一層不受影響** | 上一層 SubFlow 節點被標 SUCCESS 並依 `resultRouting`（子流程節點 config，`{'completed':[edge],'cancelled':[edge]}`，未配置＝所有出邊）推進；同時寫父層流程變數 `${v.<節點ID>_result}`／`_child`。喚醒失敗改標父節點 FAILED（不再永久卡 WAITING）。SubFlow config 另有 `max_iterations` 迴圈上限（計數記在含節點的那一層） | **不要用 `root_instance_code` 撈子樹**——同一子流程模板可能在多條支線同時執行，會把主流程與其他支線一起收掉。2026-08-31 前的行為（子流程不讀 finish_mode）記在 `dev-notes/NODE_TEST_INVENTORY.md`「附：子流程的結束語意」（已過時，僅供考古） |
| 並行分支各自走 End | End 是**流程級**結束，任一分支走到就整個流程 COMPLETED | 另一條的簽核任務會被 executor 視為流程已結束 |
| **`End(cancel)` 記 CANCELLED（案件「已取消」）；`detach`／`strict` 記 COMPLETED（案件「已核准」）** | PF-200：`end_handler` 對 cancel 回報 `data.workflow_status='CANCELLED'`，`node_runner` 白名單採用；**Abandon 節點已刪除**（handler／factory／面板全拆，nodedef 軟刪除，migration 131） | 既有用 `End(cancel)` 當「正常完工＋清分支」的兩張資安處置範本已由 migration 132 連同 14 個發行快照改成 `detach`（`scripts/examples/od_workflow_graphs.py` 同步）。`complete_workflow()` 仍無條件 `enqueue_sync_safe()`，終態會 upsert 進企業獨立資料庫——所以終態記錯比以前更難回收，改 End 語意前先讀 `dev-notes/handoff_end_subflow_cancel_20260831.md` 第十節 |
| `AlertBroadcast.broadcast_code` | **不做變數替換**（只有 title/message 有），同 code 覆蓋前一則並清掉已讀記錄 | 它是「最新一則橫幅」不是每案通知，別拿來當逐案稽核 |
| 流程模板層級的逾時 | **不存在**（`timeout_minutes`／`timeout_at` 欄位與其唯一使用者 `WorkflowEngine.start_workflow` 死碼已於 2026-09-01 PF-168 刪除） | 逾時要用流程內 Delay 節點，或簽核節點自己的逾時（下一列） |
| **簽核節點逾時**（2026-09-03 PF-229 第三期第 2 項起） | `FormAdapter` config `timeout_enabled`／`timeout_minutes`／`timeout_mode`（`ABSOLUTE`／`WORKING`：只在簽核者班表內倒數、無班表退回 ABSOLUTE）／`timeout_path_id`；期限存在 `result.data.timeout_at`，executor 以 `formadapter_timeout_due_clause()` 喚醒（**不是**加進 node_type 清單、**不動** `scheduled_at`），逾時寫 `fw_approval_records.action='timeout'` 並走指定決策；未配對出線的決策＝REJECTED 終態 | 規格 `dev-notes/CALENDAR_SPEC.md` 六之七 |
| **簽核者解析為空**（2026-09-05 PF-226 起） | `FormAdapter.handle()` 第一次進關卡時，`assignees==[]` 且型別非 `ROLE`（DYNAMIC 變數為空、USER／INITIATOR／DEPARTMENT 解析成空）就依 config `no_assignee_action` 處置：`return`（預設、缺 key 亦同）寫 `fw_approval_records.action='no_assignee'`（簽核者「系統（找不到簽核人）」）並以 `complete_workflow`／`workflow_status='REJECTED'` 結束，表單中心顯示「已退回」；`fallback_role` 改成 `assignee_type='ROLE'`＋`no_assignee_role_secure_code`（同企業、未刪、啟用，查不到 fail-closed 退回），角色沒成員也進 WAITING，管理員補人即可簽（ROLE 授權是執行時比對）。**ROLE 型別解析成空清單刻意不觸發**；USER 型別指定到已停用帳號時 `assignees` 非空也不觸發（已知缺口，PF-246）。2026-09-05 之前的行為是佇列永遠 WAITING、無人可簽、不報錯 | 設計器 modal「找不到簽核人時」區塊；測試 `test_formadapter_no_assignee.py`；憑證 `/opt/tmp/verify/20260905-pf226.log` |
| **簽核者＝角色@單位**（2026-09-05 PF-247 第 1～5 期起） | FormAdapter `assignee_type='ROLE'` 的 config 多了 `unit_scope`（`GLOBAL`／`UNIT`＋`unit_secure_code`／`APPLICANT_UNIT`／`APPLICANT_ANCESTOR`＋`unit_levels_up`）、`absence_fallback`（POSITION 型角色的缺席順位：副主管永遠可簽、代理人一二僅主管缺席；**缺席＝職缺或主管當下請假**——`ScheduleService.is_on_leave()` 看 `schedule_adjustments` 的 LEAVE 列（行事曆 LEAVE／TRIP 事件會同步寫、人工列也算），`adjusted_periods` 為 `[]`／NULL＝整天，否則以企業時區當下是否落在「`original_periods` − `adjusted_periods`」內判定；沒班表的企業時段級請假等於整天）、`self_target_action`（申請人本人在快照內時：`escalate_or_return`（預設）／`escalate_or_self`／`self`，只對 POSITION 目標、只在 APPLICANT 範圍）。進關卡時 handler 把解析結果寫進 `result.data`：`assignee_unit_secure_code`／`assignee_unit_name`／`assignee_role_code`／`assignee_role_name`／`assignee_role_type`／`absence_fallback`／`self_target_escalated_levels`，**授權端 `task_authorizer` 只讀這些 key＋執行時身分即時判定**（直接持有／全企業超集／非 POSITION 套圈／POSITION 不套圈）；`assignees` 快照只供顯示與逾時參考人。舊式 `assignee_type='DEPARTMENT'` 退役為 `DEPT_MEMBER@unit` 別名（handler 端正規化成 ROLE，快照只認角色指派不看 `users.primary_unit`）。角色／單位／申請人單位解析失敗一律走 PF-226。以副主管／代理人身分放行時 `resolve_acting_identity()` 回 `acted_as_role_code`，寫進 `fw_approval_records.acted_as_role_code`（**既有環境要手動 `ALTER TABLE fw_approval_records ADD COLUMN acted_as_role_code VARCHAR(50);`**，create_all 不補欄位）。**第 4 期（決策點 8）起帶 `assignee_unit_secure_code` key 的 ROLE／DEPARTMENT 任務不看快照**（主管銷假、卸任、被撤角色即時失去簽核權；無 key 的舊佇列項與 USER／INITIATOR／DYNAMIC 仍快照放行）。**直屬主管一律由部門推導**：`unit_resolver.resolve_direct_manager()`／`iter_manager_chain()`（申請人單位 → `DEPT_MANAGER@單位` 持有者，本人或職缺往上、副主管代理人不算、不看請假；每站**單位指派優先**、全企業指派（unit NULL）僅該站沒有可用單位主管時候補——補丁 4a 起，此前兩類混排較早者贏），OpHrLookup 的 `hr_direct_manager*` 與核決鏈都吃它，多了 `hr_direct_manager_unit(_name)`／`hr_approver_unit(_name)`，主管沒有有效任職卡＝該站上限 0 繼續往上；任職卡 `employee_positions.direct_manager_secure_code` 已 DROP（**既有環境 `--update` 後手動 `ALTER TABLE employee_positions DROP COLUMN IF EXISTS direct_manager_secure_code;`**）。部門成員／主管角色的唯一寫入實作是 `backend/app/services/dept_membership_service.py`（API 與 `seed_test_companies.py --sync-dept-roles` 共用） | 設計 `dev-notes/ROLE_UNIT_APPROVAL_DESIGN.md`（第十一節有各期差異）；測試 `test_task_authorizer_role_unit.py`／`test_formadapter_role_unit.py`／`test_hr_lookup_node.py`；憑證 `/opt/tmp/verify/20260905-role-unit-phase*.log` |
| **代理／候補＝指派性質，順位已刪**（2026-09-06 PF-251 第 1 期起；共四期，第 2～4 期未做時本列描述的是「判定層」現況） | `user_role_assignments.assignment_kind`＝`regular`／`proxy`／`standby`（＋`acting_for_user_secure_code`／`allowed_form_templates`／`source_ref`／`grant_reason`）。`task_authorizer` 只剩「行為人今天持有有效的 (角色, 單位)」：proxy 與 regular 等價，standby 只在該 R@U **沒有任何可用的 regular／proxy 持有者**時生效（可用＝帳號啟用、指派今天有效、此刻未請假），standby 不套圈、proxy 套圈與否跟角色；限定表單對 proxy／standby 都生效，任務無表單＝不在範圍。上一列的「absence_fallback 缺席順位（副主管永遠可簽、代理人一二職缺時可簽）」**在判定層已不存在**（**第 2 期起 FormAdapter 也不讀了**：快照＝`role_holding_service.effective_holders()`，regular ∪ proxy，無可用持有者時 ∪ standby；`result.data` 不再有 `absence_fallback`、設計器勾選已移除；既有「DEPT_MANAGER＋非 false」關卡由 `migrate_proxy_assignments.py` 第四段改指 `DEPT_HEAD`，graph／cytoscape_config／發行快照四處一起改，**JSON 欄位就地改要 `flag_modified`**）。簽核記錄 `fw_approval_records.acted_as_kind`（regular／proxy／standby，快照命中 NULL）＋既有 `acted_as_role_code`（只在 proxy／standby 命中時有值；2026-09-06 前的舊列存缺席順位角色碼）；歷程文字四態：舊列「（以{角色名}身分）」／standby「（候補代理 {角色名}）」／proxy 只有「（代 X 簽核）」／regular 無標籤，角色名由 `approval_history.serialize_approval_history()` 後端查。新系統角色 `DEPT_HEAD`（部門主管，正副皆持有；第 1 期只由 `scripts/migrate_proxy_assignments.py` 回填，部門頁連帶授撤在第 3 期）、`DEPT_MANAGER` 顯示名改「部門正主管」。**兩個猜不到的**：`UserRoleAssignment.get_active_assignments()`（permission／menu／page guard 都走它）預設排除 standby；`resolve_role_holders()` 預設只算 regular（主管鏈不吃代理）。分期斷層已於 3a 收掉（PROXY 指派遷成 standby）；bpserv 四期完成才部署，ALTER 清單在設計文件第六節。**第 3a 期起（2026-09-06，寫入路徑）**：`DEPT_PROXY1/2` 角色退役（各企業軟刪、出廠不種、`DEPT_POSITION_ROLE_CODES` 只剩 HEAD／MANAGER／DEPUTY）；**決策點 K2**：部門頁「候補代理人」對三個主管角色各寫一列 standby，遷移腳本第五段把每列 PROXY 指派遷成三列；**proxy／standby 唯一寫入路徑是 `role_assignment_service.assign_role(kind=...)`**（授權者檢查 `_assert_can_grant`：ORG_ADMIN／SYSTEM_ADMIN，或該 R@U 的 regular 持有者且只能授出 proxy／standby，proxy 持有者不得再授出、非管理員不得指派 regular；proxy 必填 acting_for＋起迄日＋事由、acting_for 必須是 regular 持有者；撤銷改依 `assignment_secure_code`，同一人同角色可同時有 regular＋proxy 兩列）；正副主管連帶 `DEPT_HEAD@U` 只由 `dept_membership_service._sync_head()` 授撤（設正／副主管都撤 `DEPT_EMPLOYEE`，正副都卸才回復）；leadership API position 只剩 `manager`／`deputy`／`standby`（`proxy1`／`proxy2` 400），候補逐人移除走 `DELETE /api/units/<sc>/leadership/standby/<user>`，全部走服務（PF-250 已收）；直屬主管推導（決策點 J）每站看 MANAGER／DEPUTY／HEAD 三者 regular 持有者的**聯集**、代表人正主管優先（聯集是為了容忍未連帶 HEAD 的舊列）；`platform/data.py::_department_to_dict()` 的 `manager_code` 改由角色推導（原本讀不存在的欄位會 AttributeError）；權限中心可對任何角色（含部門角色）建 proxy／standby，被代理人下拉打 `GET /api/access/role-holders` | 設計 `dev-notes/ROLE_PROXY_ASSIGNMENT_DESIGN.md`（第十一節有各期差異）；判定核心 `backend/app/services/role_holding_service.py`；測試 `test_role_holding_service.py`／`test_task_authorizer_role_unit.py`；憑證 `/opt/tmp/verify/20260906-role-proxy-1.log` |
| `DecisionWriter.decided_via` 自動推斷 | 看 `last_completed_node_type`，並行分支下不可靠 | 一律在節點 config 明確標 `human` / `auto` |
| `DecisionWriter.target_value` 替換後為空 | 節點回 error、流程卡住 | 自動封鎖前必須先用 Branch 擋掉 `actor_ip` 為空的案件 |

executor 會撿 `status=WAITING` 且 `node_type in (Delay, End, ParallelJoin, OsExecutor)`
且 `scheduled_at` 到期的節點（`workflow_executor.py` 內**兩處**都有這份清單）。
**不在這份清單內的節點一旦進 WAITING 就再也不會被喚醒**——已刪除的 `Converge`
就是這樣死的（它回 `pending`，`node_runner` 設成 WAITING 卻不設 `scheduled_at`，
而第二條入線到達時 `advance_workflow` 看到已有 WAITING 就跳過不重建）。
**新增會回 `waiting`／`pending` 的節點型別時，這兩處清單一定要一起加。**
2026-08-30 OsExecutor 上線時又踩一次：併發上限回 `waiting` + `retry_after_seconds`，
規格寫「`node_runner.py:119` 已支援，不必改引擎」是對的，但漏了 executor 這兩處清單，
被擋下的節點就永遠停在 WAITING（實測憑證 `/opt/tmp/verify/20260830-osnode.log`）。

### 節點「成功但不推進」的唯一機制：`skip_advance`（2026-08-30 起）

回 `selected_edges: []` 沒有用——空 list 是 falsy，會落到「取所有出邊」。
要讓節點執行成功但不走任何出線，在 result 的 `data` 帶：

```python
'data': {'skip_advance': True, 'skip_advance_reason': '<原因>'}
```

`node_runner.advance_to_next_nodes()` 在解析 `selected_edges` 之前就攔下來。
目前兩個使用者：Branch 的 fallback（非 route）、ParallelJoin 的 `release_once`。

### 流程控制節點的現況（2026-08-30 整併後）

工具列只剩 **ParallelJoin / Delay / SubFlow / Branch** 四個。

| node_type | 狀態 | 要知道的事 |
|---|---|---|
| `Converge` / `Switch` / `Condition` | **已刪除** | 定義、handler、前端面板全數移除（migration 119）。模板與發行快照中皆無使用 |
| `ParallelFork` | **已退役** | 定義軟刪除、面板移除，但 **handler 與 factory 註冊刻意保留**——3 個模板與 16 筆發行快照仍含此節點，拿掉註冊會讓它們執行時拋 `ValueError`。**它本來就沒有任何功能**：`advance_to_next_nodes` 沒有 `selected_edges` 時本來就取所有出邊，任何節點接兩條出線都會並行 |

`ParallelJoin` 的 config：

| key | 預設 | 語意 |
|---|---|---|
| `join_mode` | `'ALL'` | `ALL`＝所有入線到齊才放行；`ANY`＝任一入線完成即放行 |
| `release_once` | `True` | 同一流程實例內只放行一次。**關掉的話每條入線到達都會再推進一次下游**，下游會被執行多次 |
| `enable_timeout` | `False` | 開啟後 `timeout_minutes`（預設 1）內未達成放行條件就走 `timeout_edge_id` |

**沒有 `join_mode` 欄位＝`ALL`**，既有 graph 行為完全不變。
`enable_timeout` 刻意維持預設關閉：開著而沒設 `timeout_edge_id` 時 handler 直接回 error。
**ANY 模式不會取消、也不干涉其他分支**（元件只負責元件自己），
其餘分支繼續各自執行到自己的終點。

**測 ANY 模式時流程尾端不要接 `End`**：End 是流程級結束，
executor 隨後會把未完成節點一律 cancel，就觀察不到第二條入線抵達時的行為。

### form_workflow 流程變數的儲存位置（寫錯地方＝流程引用不到）

**流程變數的權威儲存是 `fw_workflow_variables` 表，不是
`fw_workflow_instances.variables` JSONB。**

- `${v.xxx}` 走 `VariableService`，**只讀那張表**
- `${wi.xxx}` 只支援五個欄位（`base.py` 的
  `_WI_FIELDS = {'wi.code','wi.exec_code','wi.name','wi.status','wi.depth'}`）
- **兩條路都到不了 `variables` JSONB** —— 寫進 JSONB 只有自己查得到，
  流程設計者引用不到。要讓流程引用得到就用
  `VariableService.set_flow_var(instance_code, name, value, org_code)`
- 流程設計者設變數用既有的 **`OpSet`（設定變數）節點**

**`VariableService._cache` 是類別層級、無 TTL 的進程內快取。**
開發環境是 `flask run` 單進程 + 同進程 daemon thread 跑流程引擎，看不出問題；
多 worker 部署下，流程改了變數之後其他 worker 仍讀到舊值。
**用過期值做顯示只是難看，用過期值做授權判定就是漏洞** ——
授權判定一律繞過快取直接查 `FwWorkflowVariable`
（範例：`pageir_formflow_resources.is_submission_editable()`）。

### 跑測試（細節已移出，2026-08-30）

**一律用 `bash scripts/run_tests.sh`，不要自己 `source .env` 之後直接叫 pytest。**
後者的 `DATABASE_URL` 指向**開發庫**，而多個 app fixture 收尾會 `db.drop_all()`。
run_tests.sh 會把庫覆寫成拋棄式的 `beakplatform_test`。

**`beakplatform_test` 雖然叫「拋棄式」，但它是現役測試庫、而且 `run_tests.sh`
不會自動建立它**——連不上就印出建立指令並 `exit 1`。所以刪掉它等於
`bash scripts/run_tests.sh` 從此無法執行，直到有人手動 createdb。
它的體積會因為 `db.drop_all()` 不 VACUUM 而膨脹，**而且一次全量就膨脹到底**
（2026-09-06 實測：重建後 7.5 MB，跑完一次全量 71 MB / 0 張表）。膨脹的庫上跑全量
慢將近一倍（同一份程式 1111 個測試：乾淨庫 24 分 40 秒、80 MB 的庫 41 分 51 秒），
所以**全量前一律先重建**；要回收空間就 DROP 後立刻重建，不要只 DROP：

```bash
sudo -u postgres psql -c "DROP DATABASE beakplatform_test;" \
  -c "CREATE DATABASE beakplatform_test OWNER beakplatform;"
```


```bash
bash scripts/run_tests.sh                     # 全部，約 25 分鐘（乾淨測試庫；2026-09-06 1111 個測試實測，膨脹庫 42 分）
bash scripts/run_tests.sh tests/test_xxx.py -q     # 單檔：路徑寫 tests/…（相對 backend/）
bash scripts/run_tests.sh -k menu -q
bash scripts/run_e2e.sh                       # Playwright，需服務在跑
```

**單檔路徑寫成 `backend/tests/xxx.py` 會 `collected 0 items` 且 exit 0**（2026-09-02 踩到）：
看起來像全綠，實際上一個測試都沒跑。run_tests.sh 在 `backend/` 內執行，路徑要寫 `tests/xxx.py`。

**全量在跑的時候絕對不要併行跑單檔**（2026-09-12 踩到）：兩邊共用同一個
`beakplatform_test`，而多個 app fixture 收尾會 `db.drop_all()`，
於是**兩邊都會冒出與本次變更無關的 F／E**（當時是 `test_ai_usage_api` /
`test_ai_usage_quota` 各爆數筆）。症狀長得像功能回歸，實際上是互相把表刪掉，
而且全量那一輪整個作廢、要重跑 30 分鐘。要在全量期間確認某支測試，就等它跑完。

**基準不寫死數字**（會腐爛）：動工前先跑一次記下當時數字，改完再比對。
以下兩個非綠是長期已知、不列入退步（`test_admin_required_for_admin` 那個 failed
已於 2026-09-06 PF-34 解決，看到舊文件列它一律過時）：

| 項目 | 狀態 | 成因 |
|---|---|---|
| `test_od_protected_targets.py`（2 error） | error | 只在完整跑時出現，單獨跑該檔 56 passed＝測試間污染 |
| `test_e2e_portal_cancel.py` | skipped | 寫死的驗收頁 2026-08-03 已消失，永久 skip |

**測試裡需要 ORG_ADMIN 打 ResourceGateway 端點時用 `admin_client`**，它自帶出廠權限定義
（`rbac_seed` fixture，PF-34）。**不要再在測試裡 `Permission(...)` 手種出廠碼**，
會撞 `permissions.code` 唯一鍵（症狀 `UniqueViolation`，2026-09-06 清掉四個檔的五份複本）；
細節與例外見 `dev-notes/TESTING_NOTES.md`。

跑出基準外的失敗，歸因順序固定：**先重跑一次**（不同就是殘留/污染）→
**再看 log 有沒有 `Unknown permission code` / `Modules already loaded`**（環境訊息）→
都不是才當功能回歸。

細節在 **`dev-notes/TESTING_NOTES.md`**：測試庫重建、與其他腳本搶鎖的
`UniqueViolation` 處置、`test_client` 三個坑（URL 要自帶 `/beakplatform` 前綴、
模組 blueprint 只註冊在進程內第一個 app、quick-login 打不進去）、
Playwright E2E 的三條硬規則與 mutation 驗證。

### 流程設計器 / graph 操作 / publish（細節已移出，2026-08-30）

用腳本或 API 改 `fw_workflow_templates.graph`、新增節點型別或分類、
或要發行配對之前，先讀 **`dev-notes/WORKFLOW_DESIGNER_NOTES.md`**。
三個最常踩的（完整說明在該檔）：

- **`graph` 與 `cytoscape_config` 兩欄都要寫**——引擎讀前者、設計器讀後者，
  只寫一邊的症狀是「流程跑新版、設計器畫舊版」且不報錯
- **直接改 graph 不會 bump revision**，publish 會回「版本未變更」沿用舊快照；
  要先 `UPDATE ... SET revision = revision + 1`
- **新增節點分類要改四個地方**，漏 `categoryOrder` 那處會被靜默略過

節點型別本身的規格：`dev-notes/NODE_TEST_INVENTORY.md`（盤點與 NT-xx 編號）、
`dev-notes/SQL_EXECUTOR_SPEC.md`、`dev-notes/AI_NODE_SECURITY.md`、
`dev-notes/OS_EXECUTOR_SPEC.md`。

### 節點型別的規格文件（2026-08-30 移出）

**每個節點 = 一個獨立 OS subprocess**（`node_runner`），PID 記在
`fw_node_execution_queue.process_id`，stdout/stderr 全進 `DEVNULL`——
**節點執行細節不在 journal 裡**，只能靠 DB 狀態反推。

| 主題 | 文件 |
|---|---|
| 各節點驗證狀態、NT-xx 編號、End 三模式與取消語意 | `dev-notes/NODE_TEST_INVENTORY.md` |
| AiAgent 的隔離設計（`--safe-mode` / `--tools ""`）與移植性 | `dev-notes/AI_NODE_SECURITY.md` |
| AiAgent 用量與配額 | `dev-notes/AI_NODE_USAGE_QUOTA_SPEC.md` |
| SysSqlExecutor 白名單（執行時重查、唯讀交易、schema 常數） | `dev-notes/SQL_EXECUTOR_SPEC.md` |
| OpHrLookup 人事資料取值（NT-31，職位→流程變數、依金額沿主管鏈找核決人） | `dev-notes/HR_LOOKUP_NODE_SPEC.md`；示範流程可用 `scripts/seed_test_companies.py --run` 建的範例企業跑 |
| OsExecutor / OsFileRead | `dev-notes/OS_EXECUTOR_SPEC.md`（第十四節是實作後記，與規格本文有六處差異，以後記為準） |

**OsExecutor（NT-28）與 OsFileRead（NT-29）2026-08-30 上線，出廠三道全關**：
`.env` 開關（`OS_NODE_ENABLED` / `OS_FILE_READ_NODE_ENABLED`，**兩者刻意獨立**）、
企業授權（見下條）、`workflow_node_definitions.is_active=false`。
部署說明在 `docs/install/os_node.md`（會推 GitHub）。

### 【測系統級 node 前必讀】邊界單位是「企業」，不是帳號身分

**開發史（Ethan 2026-08-31 口述）**：系統級 node ＝系統管理員才能用，
但**系統級沒有流程設計 UI，這是分責不是錯誤**。所以有安裝時建立的
**「系統預設企業」**（`is_system_org=true`，code `SYSTEM` / sc `system.local`），
它代表平台自己，**是唯一能看見系統級節點的企業**。

**不知道這件事就會把測試結果判反**（把預設企業當一般企業，於是誤判成
「一般企業看得到系統級功能」或「連預設企業都看不見」）。所以：

- **驗系統級功能一律用系統預設企業的 ORG_ADMIN**（quick-login `UC1oK01uDeKbG2MDwBflGD`），
  **且必須與一般企業分開各測一次**
- `org_restricted` + grants（判準＝企業）是正確實作；`require_system_admin`
  （判準＝帳號 user_type）選錯維度，擋不住 API 且會與模組 ACL 疊成死鎖
  → **PF-188 於 2026-08-31 收斂完畢**：`require_system_admin` 的過濾邏輯已從
  `get_node_definitions()` 移除、全平台 0 筆為 true，**設成 true 不再有任何效果**。
  脈絡 `dev-notes/handoff_sys_level_nodes_20260831.md`，驗收
  `/opt/tmp/verify/20260831-pf188.log`
- **新增任何一道授權前先讀知識庫 atom #5326**（`note_get(5326)`）：
  多道授權的判準維度不一致時，交集可能是空集合而且不報錯

**系統預設企業的現成測試材料**（2026-08-31 PF-188 建立，省下每次重建的功夫）：

**node展覽館 從 2026-09-13（PF-272）起是全新安裝內建的**：`bootstrap_db.py --fresh` 最後一步
`seed_node_showcase`（runner `scripts/examples/node_showcase.py`，20 項＝B0 人資示範＋19 張節點示範，
任一項失敗整個 bootstrap 非零退出）。既有環境補種或重跑單項：
`venv/bin/python scripts/seed_node_showcase.py --apply [--only sqlexecutor]`（密碼從 `--password`
或 `ADMIN_INITIAL_PASSWORD` 取，dev 隨便給即可，只有 B0 建帳號時用到）。五件猜不到的：

- 分類**依名稱** `node展覽館` 在系統企業找、沒有就建（`ensure_showcase_category`），不再寫死 secure_code；
  每支 `provision_nodedemo_*.py` 拆成 `provision(org, apply, **opts)`＋薄殼 `main()`，module-level 不得 create_app
- 示範帳號 `demo-staff／demo-manager／demo-director@<系統企業 domain_name>`，密碼＝`ADMIN_INITIAL_PASSWORD`、
  `must_change_password=False`（dev 是 `@system.local`，bpserv 是 `@sys-xxxx`）
- SysTelegram／Email 示範引用的是**佔位設定組**（`node展覽館示範（請填入…）`，`is_active=False`），
  要真的寄得出去得到企業設定填真實值並啟用
- `fw_demo_inventory` 是正式 ORM model（`backend/app/models/fw_demo_inventory.py`，56 筆由 B8 種入），
  三支 `fw_sp.check_stock／low_stock_items／stock_qty` 在 `scripts/sql/fw_sp_setup.sql`——
  該檔在全新安裝時**先於 create_all** 執行，所以檔內有 `SET check_function_bodies = off;`，拿掉會在
  「relation fw_demo_inventory does not exist」炸掉（2026-09-13 踩到）
- `provision_nodedemo_waf_failover` 沒給 `--node` 時用佔位 `node-a／node-b`，`failover_dir` 由 `__file__`
  反推 `<安裝目錄>/ITHome2026-WAF`；讀者要用真名重跑 `seed_node_showcase.py --only waf_failover --node … --apply`


| 用途 | 識別碼 |
|---|---|
| 流程模板「系統級節點驗收流程」 | `nAOBJWuKBa969StsPwv5OA`（設計器 `/forms/workflows/<sc>`） |
| 它的配對（publish 用） | `oCQwRov2rMIS1jbSFeg9Yg` |
| 系統級 Telegram 設定組 | `c9WeYKveCBWxbn0t8kl6yn`「系統TG」，頻道「測試頻道」 |

**系統預設企業原本一個流程模板都沒有**，所以在此之前想測系統級節點得先自己建一個。

查目前有哪些受限節點與授權狀態，不必開頁面：

```bash
set -a && source .env && set +a && venv/bin/python scripts/node_grant.py list
```

### 節點型別的企業授權：受限節點只有被 grant 的企業看得到（2026-08-31 起）

`workflow_node_definitions.org_restricted = true` 的節點型別，必須在
`workflow_node_org_grants` 有該企業的記錄才可用。**出廠只有系統企業
（`organizations.is_system_org`）有 grant**，客戶企業連在設計器都看不到。
授權走 `/node-grants/`（選單「權限管理 → 節點授權」，`@system_admin_required`，
PF-185 於 2026-08-31 完成）或維運工具
`venv/bin/python scripts/node_grant.py grant <node_type> <org>`。

**唯一判定實作是 `modules/form_workflow/services/node_grant_service.py`**，
三個消費點都吃它，新增受限節點時三處都已自動涵蓋，不必各自加判斷：

| 消費點 | 位置 |
|---|---|
| 設計器面板可見性 | `api/workflows.py::get_node_definitions()` |
| graph 寫入（9 個入口，含 publish 與批次匯入） | 共用 helper `api/graph_authz.py::reject_unauthorized_graph_nodes()`（2026-09-01 PF-196 收斂，之前三個檔案各一份複本且批次匯入完全沒檢查）；批次匯入／批次另存走 per-item 判定 |
| 執行期 | 兩層（2026-09-01 PF-194 起）：`node_runner.execute_handler()` 在 `validate()` **之前**用 `find_runtime_denial()` 統一擋（只擋 restricted 且未授權，定義消失／查詢失敗刻意放行）；5 支受限 handler 內的 `is_node_allowed()` 保留為 fail-closed 最後防線。被擋時的回報格式由 `grant_denied_result()` hook 決定，Os 三兄弟覆寫維持四分法 |

**寫入路徑（grant / revoke）也收斂在同一支服務**：`grant_node_to_org()` /
`revoke_node_from_org()`，Web API 與 CLI 都呼叫它，錯誤用 `NodeGrantError.code`
（`node_not_found` / `node_not_restricted` / `org_not_found`）辨識。
**撤銷是軟刪除、再授權會新增一列**（partial unique index 只管
`is_deleted = false`），所以那張表本身就是授權歷史。

管理頁刻意**不新增 permission code**：`@system_admin_required` 已是身分硬界線，
而註冊了沒建 code 會讓端點對所有身分 403（TENANT-02 雷二）。
API 也**必須放平台層**（`backend/app/api/node_grants.py`）——SYSTEM_ADMIN 打
`modules/form_workflow/api/` 恆 403，成因見上方 PERM-04。

三件猜不到的：

- **`is_node_allowed()` 對「節點定義不存在或已軟刪除」回 False**（fail-closed）。
  否則把 `workflow_node_definitions` 那筆軟刪除就等於關掉授權閘門
- **舊的 `system_settings.os_node_allowed_orgs` / `file_read_allowed_orgs`
  已於 migration 122 刪除**，改動它們不會有任何效果（鍵根本不存在）。
  `os_file_read_base_dirs` / `os_file_read_org_base_dirs` 不受影響，那是目錄限制
- **`require_system_admin` 已退場，不要再拿它當替代方案**：它的判準是帳號 user_type
  而非企業，且只擋設計器可見性、不擋 graph 寫入與 publish。2026-08-31（PF-188）
  唯二使用它的 `SysTelegram` 與 `EmailRelay` 都改成 `org_restricted`，
  `get_node_definitions()` 的過濾邏輯也一併刪除。**欄位保留在 DB 與 model
  （Ethan 裁示），但已無任何程式讀它——設成 true 什麼都不會發生。**
  理由詳見 `dev-notes/OS_EXECUTOR_SPEC.md` 第二節（該節 2026-08-31 更正過一次
  ——「SYSTEM_ADMIN 沒有 form_workflow 合約」是錯的，實際卡在模組 ACL）

**系統級節點一律用 `Os` 前綴（Ethan 2026-08-31 定調的命名規範）**：
`OsExecutor` / `OsFileRead` / `OsFileWrite`，`display_name` 對應
「OS 命令」/「OS 檔案讀取」/「OS 檔案寫入」，`.env` 開關與 `system_settings`
的目錄白名單鍵也同步帶前綴（`OS_FILE_READ_NODE_ENABLED`、
`os_file_read_base_dirs` 等）。**新增碰觸作業系統的節點時沿用這個前綴。**
判準是「碰不碰作業系統」而不是「是不是管理員專用」——所以 `SysTelegram`、
`SysEmailRelay` 與 `SysSqlExecutor` 不在此列（碰的是外部服務或平台自己的資料庫，
不是 OS，用 `Sys` 前綴）。
`EmailRelay` 於 2026-08-31（PF-188）改名為 `SysEmailRelay`，
走 `scripts/migrations/legacy/130_sys_nodes_org_restricted.sql`。
**小寫的 `emailrelay` 一律不動**——那是外部服務 E-MailRelay 本身
（`emailrelay-submit`、`app.services.emailrelay_config`、spool 目錄、
`/api/system-settings/emailrelay`），與節點型別無關。
2026-08-31 之前叫 `FileRead` / `FileWrite`，改名走
`scripts/migrations/legacy/129_os_prefix_for_system_nodes.sql`（連 graph、發行快照、
執行紀錄、system_settings 鍵一起換——**node_type 是 factory 查 handler 的鍵，
graph 裡的舊字串沒換掉的話該流程執行時會拋 `ValueError`**）。

**OsFileWrite（NT-30）2026-08-31 上線，第三個受限節點**，同樣三道全關
（`OS_FILE_WRITE_NODE_ENABLED`、企業授權、`is_active=false`），
base_dir 用**獨立**的 `os_file_write_base_dirs` / `os_file_write_org_base_dirs`
（**不與 `os_file_read_*` 共用**——可讀不等於可寫）。規格
`dev-notes/OS_FILE_WRITE_SPEC.md`，部署 `docs/install/os_file_write_node.md`。

**受限節點現況共 6 個**（2026-09-13 PF-254 後）：`OsExecutor` / `OsFileRead` /
`OsFileWrite` / `SysTelegram` / `SysEmailRelay` / `SysSqlExecutor`。後三者
**沒有 `.env` 開關**（不碰 OS，只有企業授權這一道），出廠 `is_active=true`，
所以「未獲授權的企業看不到」是它們唯一的閘門。

**`SqlExecutor` 已於 2026-09-13（PF-254 第一階段）更名為 `SysSqlExecutor`**
並改成受限節點，分類從「整合」移到「系統」，連的仍是平台主庫。
**一般企業從此在設計器裡看不到任何 SQL 節點，這是預期狀態、不是缺陷**——
未獲授權的企業打 `/api/workflows/data/sql-procedures` 回 403、
graph 帶該節點寫入回 403「流程中含有本企業未獲授權的節點型別」。
既有環境升級要跑 `venv/bin/python scripts/migrate_sqlexecutor_to_sys.py --apply`
（`--dry-run` 預設、冪等），它同時換掉 graph／cytoscape_config／發行快照／
執行紀錄裡的舊 node_type 字串，並修正節點 icon 路徑——**icon 那段不能省**，
更名 `git mv` 了圖檔，漏了就是設計器畫布破圖而畫面不報錯。
（連 `AiAgent` 借用舊 `sqlexecutor.svg` 的歷史節點也一併導到 `aiagent.svg`。）
**企業級 SQL 節點（連企業專屬庫 `org_<id>`）Ethan 2026-09-13 決定不開發**——
第二視角 session 的注入實測證明 `org_N` 與平台主庫共用 postmaster 時，隔離只值
「PG 沒有低權 RCE ＋ 即時修補」，不是結構邊界；同日連集團共用 DB 也一併退役（PF-269）。
看到舊文件寫「鐵人賽後再評估」一律過時（決策脈絡見 BBN `PF-254`）。

**`SysTelegram` 的設定組下拉曾經恆為「無法載入設定」**：前端寫死
`/api/system/data/settings/telegram`，那支端點**從來不存在**（實測 404）。
2026-08-31 改成與一般 Telegram 共用 `/api/enterprise/data/settings/telegram/available`
（回「自己企業＋系統企業」的設定組）。handler 端的解析同樣限縮成這兩者——
**跨到別家一般企業的設定組會被擋**（實測 `找不到 Telegram 設定`），
同批一併修的還有 `email_handler` 的 `smtp_config_id` 與兩處 `RecipientGroup`
（原本都無 org 條件，且有可枚舉的整數 ID 向下相容，已移除）。

**它每次寫入前會把檔尾連續的所有換行位元組（`\r` `\n` 任意組合）truncate 掉**，
再依勾選補換行。PF-191（2026-08-31）起出廠預設多了 `newline_smart`
（「緊接上一筆，另起新行」，**缺 key＝啟用**）：截斷後檔案非空才補一個前置換行，
所以**出廠預設就是一筆一行**，舊的「連續寫入黏成一行」坑只在 `newline_smart=false`
＋只勾後面時存在（舊敘述「要一筆一行兩個都要勾」已過時）。`newline_smart` 啟用時
`newline_before` 完全無作用（面板反灰）；content 自身的尾端換行一律原樣寫入不清理，
content 帶 `\n` 結尾又勾 `newline_after` 會得到一個空行，這是刻意保留的能力。
實測見 `/opt/tmp/verify/20260831-filewrite.log` 與 `20260831-pf191-smart.log`。

**這三個節點的失敗不會讓 queue 變成 FAILED**：四分法
（`ok` / `exception` / `timeout` / `dispatched`）全部回 `status: 'success'`，
因為 `fail()` 會無條件重試 3 次，而有副作用的命令不能被平台自動重跑。
**症狀是流程管理頁一片綠、實際命令失敗過**——真相在流程變數
`<result_var>_result` 與 `fw_node_execution_logs`（level=ERROR）。
判斷節點成敗一律看那兩處，不要看 queue 的 status。

**改 handler 後 executor 要重啟才認得**，而重啟有代價——見下方「服務啟動」。

### 正式環境已退役（2026-08-05 起，看到 :8000 回 502 先讀這段）

`/opt/BeakPlatform` 已改名 `/opt/BeakPlatform_OLD`，三個 systemd unit
（`beakplatform.service` / `-executor` / `-sync-worker`）已 disable + 刪檔，
用戶將從 GitHub 重新安裝。**本機唯一活著的 BeakPlatform 是 `/opt/BeakPlatform-dev`。**

| 現象 | 是不是故障 |
|---|---|
| `192.168.0.16:8000` 回 502 | **預期**。nginx 設定與 iptables 白名單刻意保留（重裝後沿用），後端沒了 |
| 外網 Cloudflare `/beakplatform/` 不通 | **預期**，同上 |
| `systemctl status beakplatform.service` 查無此 unit | **預期**，已刪檔 |
| `psql -d beakplatform` 回 does not exist | **預期**，資料庫已於 2026-08-31 `DROP DATABASE`（見下段） |

**退役正式庫已刪除（2026-08-31，Ethan 核可）**：`beakplatform` 這個資料庫
（21MB / 97 張表 / 4 個帳號 / 2 家企業，最後一筆資料 2026-04-20）已 DROP。
起因是它成為實質的資料暴露面——**`beakplatform` 這個 DB role 同時是它、`vulnmgmt`、
`test_temp` 三個庫的 owner**，所以平台任何能控制 DSN 的路徑都讀得到那 97 張表
（含 `users`，實測讀出 4 筆）。因為是 owner，`REVOKE ... FROM PUBLIC` 對它無效，
只能刪。備份（含還原演練驗證）在
`/opt/tmp/backup/beakplatform-retired-db-20260831/`：

```bash
sudo -u postgres psql -c "CREATE DATABASE <新庫名> OWNER beakplatform;"
PGPASSWORD=postgres123 pg_restore -h localhost -U beakplatform -d <新庫名> \
  --no-owner --no-privileges /opt/tmp/backup/beakplatform-retired-db-20260831/beakplatform_full.dump
```

**PF-39 重裝不需要這個備份**——重裝走 `scripts/init_database.sh` 建新庫。
它只是萬一要回查舊正式環境資料時的退路。
`vulnmgmt` / `test_temp` 的共用 owner 是歷史債，Ethan 2026-08-31 決定**保持現況**，
不要再提報為缺陷。

不要為了「修好 502」去改 nginx、重啟 gunicorn 或復活 unit。
重裝步驟與必須沿用的 `ENCRYPTION_MASTER_KEY` 見 BBN 待辦 **PF-39**
（`note_search("PF-39")`），舊 unit 原檔備份在
`/opt/tmp/backup/systemd-beakplatform-20260805/`。

`scripts/init_database.sh` 的路徑一律由 `${BASH_SOURCE[0]}` 推導 `REPO_ROOT`、
`DB_NAME` 從該 repo `.env` 的 `DATABASE_URL` 解析（`DB_NAME` 環境變數可覆寫），
一份腳本 dev 與正式環境通用。**禁止再往裡面寫死 `/opt/BeakPlatform` 或 `-dev`。**

### 系統級發信只有一個入口：`EmailService`，而且會依主機設定二選一（2026-09-02 PF-218 起）

忘記密碼、暫時密碼、管理員密碼重設通知、登入救助警報、OS 節點失敗通知這類**系統信**
一律呼叫 `backend/app/services/email_service.py::EmailService`，它依 `system_settings` 的
`mail_primary_service`（`emailrelay` / `smtp`）與 `mail_send_both` 決定走 E-MailRelay
還是系統級 SMTP 預設設定組（`is_default` 且啟用），**沒指定就是寄不出去、不做 fallback**。
主機設定頁的 UI 已把 E-MailRelay 與 SMTP 合併成「發信服務」分類
（API `GET/PUT /api/system-settings/mail-service`，`_ss_mail_service.py`）。

三件猜不到的：

- **`send_email()` 回 False 就是真的沒寄出**，2026-09-02 之前它在 E-MailRelay 不可用時
  只把信印進 log 就 `return True`，呼叫端全部以為寄出去了。新增系統信呼叫端時
  **一定要接回傳值並反映到 UI 或 log**；要區分「全部失敗」與「併發時其中一路失敗」
  用 `send_email_detailed()`（`any_success` / `success`）
- **dev 機沒指定時所有系統信都會失敗**——`mail_primary_service` 是新鍵，
  全新環境出廠是未指定，忘記密碼頁會直接顯示「系統發信服務尚未就緒」
  （bpserv 2026-09-02 已指定 SMTP，見上方 bpserv 表）。
  dev 現況是 `emailrelay`、不併發。**dev 的 E-MailRelay 不是只進 spool**（2026-09-04 實測）：
  `/opt/emailrelay/etc/emailrelay.conf` 是 `forward-to smtp.gmail.com:587` ＋ `poll 10`，
  `emailrelay-submit` 寫進 `/opt/emailrelay/spool/` 的信最多 10 秒就被轉送到 Gmail 並從 spool 刪掉，
  所以系統信在 dev 也會真的寄到收件者；想從 spool 撈信件內文（例如抓暫時密碼）幾乎來不及，
  改看收件信箱。log 在 `/opt/emailrelay/logs/emailrelay-YYYYMMDD.log`，每封只留一行
  `smtp connection to <ip>:587`，數行數即封數。企業「密碼政策」分頁的黃色提示看的也是這個就緒狀態
  （API 回 `system_mail_ready`，`has_smtp` 已移除）
- 流程 `Email` 節點與受限節點 `SysEmailRelay` **不走**這個入口，那是流程設計者選的通道。
  dev 的系統級 SMTP 設定組 `lionsecbot@gmail.com` 密碼 2026-09-02 PF-218 收尾時已換成有效的
  （2026-09-04 再實打 `/api/system-settings/smtp/<sc>/test` 仍寄得出去）；本檔此前寫「已失效」
  是 2026-09-02 上午的舊況，PF-228 發單時照抄了一次，別再信

### 服務啟動

**`systemctl restart beakplatform-dev-executor` 會殺掉當下所有正在跑的節點進程**
（2026-08-30 實測）：unit 是 `KillMode=control-group`，而 node_runner 的
`start_new_session=True` **只脫離 process group，不脫離 cgroup**。
而全 repo **沒有 stale RUNNING 的回收機制**，被這樣殺掉的節點會**永遠卡在 RUNNING**、
流程就此靜止且不報錯。所以改 handler 要重啟 executor 之前，先確認沒有流程在跑：

```sql
SELECT node_type, node_id, started_at FROM fw_node_execution_queue WHERE status='RUNNING';
```

事後發現卡住的只能手動改回 PENDING 或標 FAILED。
要讓外部作業活過重啟只能另建 systemd unit 移出 executor 的 cgroup，
脈絡見 `dev-notes/OS_EXECUTOR_SPEC.md` 第七節。

- **正式管道是 systemd 服務**：`sudo systemctl restart beakplatform-dev.service`（重啟後 `systemctl is-active` 確認）
  - **`is-active` 回 active 時 Flask 可能還沒開始 listen，nginx 這段約 5~10 秒回 502**（2026-09-02 連踩兩次）。
    自動化驗收要先 `curl -s -o /dev/null -w '%{http_code}' $BASE/auth/login` 拿到 200 再開始，
    quick-login 也要在那之後才做（重啟前後的 session 都作廢）
- 開發服務以**非 debug 模式**跑，Python/模板變更**不會自動重載，必須重啟**
- **重啟後所有登入 session 立即失效**（開發環境 `SESSION_TYPE='cachelib'` 存在進程記憶體）。
  症狀是重啟後 curl 拿到的頁面沒有 navbar、或 `/help/` 回 401——不是功能壞了，
  重跑一次 quick-login 即可。用瀏覽器驗收時同理，重啟後要重新切身分
- **踩坑**：若曾手動 `flask run`，殘留進程會佔住 7000 埠導致 systemd 服務 crash loop（`is-active` 一直是 `activating`）。用 `ss -tlnp | grep :7000` 找出佔埠 PID kill 掉，服務即自動接手
- **flask CLI 必須先載入 .env**（缺 SECRET_KEY 直接 ValueError）：
  ```bash
  cd /opt/BeakPlatform-dev && set -a && source .env && set +a
  cd backend && ../venv/bin/flask module sync --force   # 同步模組選單/權限定義到 DB
  ```
  模組選單的 user_types 改在模組 `__init__.py` 定義後需跑此指令；啟動時的自動同步**不含**權限覆寫（僅 --force 才會）
- 手動啟動（僅除錯用，用完要 kill）：
```bash
cd /opt/BeakPlatform-dev
source venv/bin/activate
set -a && source .env && set +a
cd backend && flask run --host=127.0.0.1 --port=7000
```
- 對外經 nginx `192.168.0.16:7000/beakplatform` 反代，flask 只綁 127.0.0.1

---

*最後更新: 2026-08-30（二階段整理）*

*一、修三處自相矛盾*：`docs/guides/` 兩篇指向已刪目錄→改指
`docs/manual/05_security_ops/soc_planning/`；刪除「一律走到 End 節點收尾」原則
（與並行分支「不要指向 End」對撞，Ethan 判定不符實），保留仍成立的駁回記錄行為；
`docs/help/` 的「YAML」補上說明——那三個 `.md` 整份是 YAML，不是格式寫錯。

*二、備忘章瘦身 2760→1861 行*（token 約 5.1 萬→3.3 萬）。
搬出的內容一律在本檔留「症狀 → 去哪查」的指針，去處：

| 移出的內容 | 現在在哪 |
|---|---|
| NoCode Builder / Portal（317 行） | `dev-notes/NOCODE_PORTAL_NOTES.md`（新建） |
| ClickHouse 事件權威、三處置流程、protected targets、intake HMAC、EDL（210 行） | `dev-notes/OPEN_DEFENSE_ARCHITECTURE.md` 第 13 節 |
| `.20` 埠表、SSH 金鑰政策、風險定調（72 行） | `dev-notes/SEC_STACK_ARCHITECTURE.md` 第 11 節 |
| 測試細節、`test_client` 三坑、Playwright（147 行） | `dev-notes/TESTING_NOTES.md`（新建） |
| AiAgent 隔離設計與移植性（106 行） | `dev-notes/AI_NODE_SECURITY.md`（新建） |
| 設計器節點分類、腳本產 graph、publish 陷阱（90 行） | `dev-notes/WORKFLOW_DESIGNER_NOTES.md`（新建） |
| SysSqlExecutor 三條硬規則、節點執行與 End 三模式（77 行） | `SQL_EXECUTOR_SPEC.md`、`NODE_TEST_INVENTORY.md` 附錄 |

**留下的判準是「不讀到會不會做錯，而做錯時症狀認不認得出來」**——
症狀靜默的（流程變數寫錯地方、重啟 executor 卡死節點、撞開發庫跑測試）留在本檔；
認得出症狀的搬走，靠指針命中。日後新增備忘沿用這條判準。

*前次 2026-08-06：分流細節至 `dev-notes/`、取消工單格式、PERM-02 改為預設套用 D2*
