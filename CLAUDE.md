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
| 節點型別規格（AiAgent / SqlExecutor / OsExecutor / 盤點） | `dev-notes/AI_NODE_SECURITY.md`、`dev-notes/SQL_EXECUTOR_SPEC.md`、`dev-notes/OS_EXECUTOR_SPEC.md`、`dev-notes/NODE_TEST_INVENTORY.md` |

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

**GitHub 推送必須使用過濾腳本：**
- **push** → `git push origin main` (Forgejo，直接推)
- **push github** → `bash scripts/push_github.sh` (GitHub，過濾推送)
- **push both** → 先 `git push origin main`，再 `bash scripts/push_github.sh`
- **禁止** 直接執行 `git push github main`，會把 CLAUDE.md 等內部檔案推上去
- 過濾腳本要求工作區乾淨，有未 commit 的變更時先 `git stash --include-untracked`，推完再 `git stash pop`
- GitHub 的 history 與 origin 不同步是正常的（過濾 commit），不要 merge github/main 回 local

### 2. 更新追蹤
- 完成 BBN 待辦（PF-xx）時，回寫該原子標註完成狀態
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

### 使用者手冊有兩個出口，同一批來源（2026-08-13 起）

`docs/manual/` 八章的 md 同時餵給兩個地方，**寫一次、兩邊生效**：

| 出口 | 特性 |
|---|---|
| 站內 `/help/`（Flask，`doc_catalog_service.py`） | **依登入帳號動態過濾**標題清單 |
| MkDocs 站（`mkdocs build`） | 靜態全集，每頁自動標「適用對象」 |

**站內可見性直接複用選單雙鑰匙**——frontmatter 寫
`nav_menu: <menu_items.code>`，該選單對此帳號可見則文件可見。
不要另建權限判定，也不要自己查 `MenuPermission` / `MenuRoleRequirement`。
跨階角色、企業間差異、模組合約授權全部自動生效（實測 lion 企業的管理員
比 beluga 少 4 篇，因為 lion 沒有弱點管理模組授權）。

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

待辦事項以 **BBN 待辦為主**（ref_code `PF-xx`，`project_tasks` 查詢、
`note_search("PF-xx")` 取全文）。Forgejo Issues 已全數移回 BBN，若見殘留直接忽略，
不需搬移或關閉（用戶會自行在 BBN 新增）。
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

**`roles` 表沒有 `user_type` 欄位**——角色可以被指派給任何身分，含 EXTERNAL，
UI 與服務層都不阻擋（實測把 `FLOW_DESIGNER` 指派給 EXTERNAL 帳號成功、無警告）。

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

### PERM-04: 模組 ACL 是 fail-open，新企業預設全開（2026-08-23 實測）

`ModuleAccessService.check_user_access()` 第 96~97 行：

```python
if count == 0:
    return True  # 無 ACL = 不限制
```

所以 **`@module_access_required(mod)`（`check_acl=True`）在該企業沒有任何
`module_access_control` 記錄時，效力等同 `check_acl=False`**——只驗合約。
建立企業時**不會**自動 seed ACL，所以新企業就是這個狀態。

實測（TEST00：有 form_workflow 有效合約、零 ACL 記錄）的純員工、無任何角色：

```
/api/workflows/data/org-tree        -> 200  全企業組織樹
/api/workflows/data/org-roles       -> 200  全企業角色清單
/api/workflows/data/org-api-keys    -> 200  企業 API Key 清單
/api/workflows/data/sql-procedures  -> 200  SqlExecutor 白名單 SP 定義
```

對照組 BELUGA（有設 ACL）同批端點對 EXTERNAL 與純員工全部 403。

**判讀既有程式時的意義**：看到 `@module_access_required('x')` 不要當成「已經有人在守」，
它只在該企業設過 ACL 時才是防線。完整分級與 334 支清單見
`dev-notes/PF145_MODULE_API_KEY1_AUDIT.md`，重跑用
`venv/bin/python scripts/audit_module_api_gates.py`。

要不要改成 fail-closed 是**全平台變更**（會擋掉所有沒設 ACL 的企業），
屬待辦 PF-145 階段三，不要在改某支 API 時順手做。

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
`MODEL_RESOURCE_TYPE_MAP` → 建對應 permission code（`{resource_type}:read` 等，
參考 `scripts/migrations/075_seed_resource_crud_permissions.py`）→
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

**雷三：已註冊 model 改走 gateway 也不是等價替換。**
`list()` / `filter()` 對 `LIST_RBAC_ENFORCED_MODELS` 內的 model 自動檢查
`{resource_type}:read`，而可直接改的那 11 種**全部都在那份清單裡**。
`User.query.filter_by(...)` → `ResourceGateway.filter(User, ...)` 之後，
該端點的呼叫者需要持有 `user:read`——EMPLOYEE／EXTERNAL 可達的端點會 403。
呼叫端本來就不該持有該權限時，用 `check_permission=False` 並在該行寫明理由。

#### 改完必須實測（單元測試抓不到）

測試庫是 `db.create_all()` 建的空表、**沒有 RBAC seed**，權限鏈上的問題在測試裡
一律表現為既有的那個 failed（`test_admin_required_for_admin`，PF-34），
不會因為你改壞而多紅一條。**一定要用該端點的實際使用者身分實測**：

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
就是這樣才被發現的，修法見 `scripts/migrations/113_form_center_menu_external_users.py`。

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
- 範例：`scripts/migrations/099_merge_platform_help_menu.py`（含 `--dry-run`，冪等）

**模組選單「刪掉定義」不等於選單會消失**（2026-08-17 踩到）：
`flask module sync` 只做 create / update / unchanged
（`backend/app/services/module_menu_service.py` 沒有任何刪除路徑），
所以從 `MODULE_INFO['menu_items']` 拿掉一項之後，既有 DB 記錄照樣留著、
選單照樣顯示。**要另寫 migration 把該 `code` 的 `menu_items` 設 `is_deleted`**
（範例：`scripts/migrations/104_retire_od_intake_keys_menu.py`）。

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

### VERIFY-01: 驗收規範（瀏覽器實測 + 留證，主 Claude 專屬職責）

> 2026-08-06 起，原 VERIFY-01（瀏覽器實測）／VERIFY-02（留證）／VERIFY-03（AI 自檢不算數）
> 三條合併於此。舊文件引用到 VERIFY-02／VERIFY-03 時一律看本節。

**一、使用者要點的東西，curl 驗完還要用 chrome-devtools 實際點一次。**
curl 對「連結、按鈕、select 初次渲染值」有結構性盲區：

- 用 curl 測連結時都是自己帶完整路徑，永遠測不出網址少了前綴（FRONT-10 的成因）
- select 顯示錯值（FRONT-08）在 HTML 原始碼裡看不出來，要渲染後才知道
- `BkCaps.can()` 漏注入（FRONT-09）的症狀是「按鈕點了沒反應、console 不報錯」

**二、AI 產出的自我檢查表不算驗收。**
codex／subagent 開不了瀏覽器（chrome-devtools MCP **只有主 Claude 有**），
它的「自我檢查七項全過」只證明程式碼有寫，不證明串得起來——
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

**時間差運算（SLA 倒數、逾時判定、滾動 24h 視窗）不受此條影響**，維持 UTC——
那是兩個時間點相減，與時區無關。只有「切在某個日曆日邊界」才要換算。

**手打 SQL 查「最近 N 分鐘」時 `now()` 是台北時間，而欄位存 naive UTC**
（2026-08-24 踩到）：`created_at > now() - interval '15 minutes'` 會被 8 小時偏移吃掉，
**回 0 筆**，看起來像「功能沒動作」。查近 7 天沒事是因為 7 天遠大於 8 小時，
所以這個坑只在短時窗出現。正確寫法：

```sql
WHERE created_at > (now() AT TIME ZONE 'UTC') - interval '15 minutes'
```


## 資料庫資訊

- **Host**: localhost
- **Port**: 5432
- **Database**: beakplatform_dev
- **User**: beakplatform
- **Password**: postgres123（開發環境）
- **本機資料皆為測試資料**：變更後可忽略舊資料，不用修正舊資料，除非用戶要求

### 造／清測試帳號（2026-08-23 試誤才弄對）

- `POST /api/users/` 必填四項：`native_name` / `english_name` / `username` /
  `employee_id`（少了只回「本國姓名、英文姓名、帳號為必填」，不會列出 employee_id）。
  **它會忽略 `user_type`，一律建成 EMPLOYEE 並順帶指派 `EMPLOYEE` 角色** ——
  要 EXTERNAL 測試帳號得建完再用 SQL 改 `user_type`、補 `EXTERNAL_USERS`、
  拿掉那筆 `EMPLOYEE` 指派（不拿掉會讓 Key2 測試多一個變因）。是不是缺陷見待辦 **PF-150**
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

### 實體層清理：檔案與目錄會跟著刪，資料庫刻意不刪（2026-08-28 PF-166 起）

唯一實作是 `backend/app/services/org_physical_cleanup_service.py`，
**路由層不自己組路徑、不自己刪檔**。「清理企業孤兒資料」卡片下半有「實體資源」區塊
（端點 `/hostconfig/physical-orphans/preview|execute`）。

五件猜不到的：

- **順序不能改**：實體檔案與 `db_name` 必須在**刪表之前**收集
  （`platform_files.storage_ref` 一旦硬刪就查不到該刪哪些檔），
  而 `encrypted_storage/<sc>` 與 EDL 目錄必須在 **commit 之後**才刪——
  企業還在 DB 時，每分鐘一次的 `scripts/cron/od_render_edl.py` 會把 EDL 目錄寫回來
- **企業獨立資料庫（`org_<數字>`）一律不由 web 端刪**（Ethan 2026-08-28 定調），
  只回 `manual_required` 附一行 `sudo -u postgres dropdb <name>` 讓管理員自己執行。
  不要「順手」給它加執行按鈕
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

### 比對「乾淨安裝」與 dev 的 schema（2026-08-29 起，PF-168 用得到）

`scripts/init_database.sh` 走的是 **`db.create_all()`（從 ORM model 建表）**，
不是跑 migration。所以 dev（121 個 migration 疊出來）與外部使用者的全新安裝
**schema 不一樣，而且沒有任何機制會發現**。要判斷現況差多少就跑這段，
全程約 2 分鐘（本 session 實際跑過三次）：

```bash
cd /opt/BeakPlatform-dev
sudo -u postgres psql -c "DROP DATABASE IF EXISTS beakplatform_freshcheck;" \
  -c "CREATE DATABASE beakplatform_freshcheck OWNER beakplatform;"
set -a && source .env && set +a
export DATABASE_URL="postgresql://beakplatform:postgres123@localhost:5432/beakplatform_freshcheck"
export SKIP_MODULE_SYNC=1
cd backend && ../venv/bin/python -c "
from app import create_app, db
app = create_app()
with app.app_context(): db.create_all()"
# 比對（表清單；欄位把 tables 換成 columns、選 table_name||'.'||column_name||':'||data_type）
cd /opt/BeakPlatform-dev
for d in beakplatform_dev beakplatform_freshcheck; do
  PGPASSWORD=postgres123 psql -h localhost -U beakplatform -d $d -t -A -c \
    "SELECT table_name FROM information_schema.tables
     WHERE table_schema='public' AND table_type='BASE TABLE';" > /tmp/t_$d.txt
done
python3 -c "
d=set(x.strip() for x in open('/tmp/t_beakplatform_dev.txt') if x.strip())
f=set(x.strip() for x in open('/tmp/t_beakplatform_freshcheck.txt') if x.strip())
print('dev 有 fresh 沒有:', sorted(d-f)); print('fresh 有 dev 沒有:', sorted(f-d))"
sudo -u postgres psql -c "DROP DATABASE beakplatform_freshcheck;"
```

**比對一律用 python 的 set 差集，不要用 `comm`**——psql 的 `ORDER BY` 走
collation，與 `sort` 的順序不一致，`comm` 會噴 "not in sorted order"
並給出錯誤結果（2026-08-29 踩過）。

**`freshcheck` 是拋棄式的獨立庫，與 `beakplatform_test` 無關**，
跑測試時同時建它不會互相卡鎖。

2026-08-29 現況：dev 105 表 / 乾淨安裝 101 表，差 4 張
（3 張 spec_formulate 模組 model 因 `SKIP_MODULE_SYNC=1` 不載入、
`schema_migrations` 是登記表本身）。**數字會腐爛，自己跑。**

**`schema_migrations` 不能用來判斷「這個庫跑到哪一版」**：
檔案系統 118 個 / DB 登記 121 筆，084 以後的 SQL migration 全數未登記，
DB 卻登記著檔案系統早已不存在的檔名。修它是 PF-168 的一部分。

### 每個 session 都會撞一次的欄位名（2026-08-09 逐一試誤才弄對）

寫 SQL 前先看這張表，可省掉一輪 `column ... does not exist`：

| 想查的東西 | 錯的猜法 | 實際欄位 |
|---|---|---|
| 使用者姓名 | `users.name` / `full_name` | **`users.display_name`** |
| 表單模板是否發行 | `fw_form_templates.status` | **`is_published`**（發行快照在 `fw_published_form_workflows.status='Published'`） |
| API Key 是否可用 | `api_keys.is_active` | **`api_keys.status`**（`active` / `suspended`） |
| 角色是否唯一 | `roles.code` 唯一 | **只有 `secure_code` 唯一**，`ix_roles_code` 是非唯一索引 —— 不同企業的 `SECURITY_STAFF` 是兩筆不同 secure_code |
| 角色綁哪種身分 | `roles.user_type` | **沒有這個欄位**；角色與 user_type 無關聯，任何角色都能指派給任何身分（見 PERM-03） |
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
| 角色指派是否生效 | `user_role_assignments.is_active` | **沒有這個欄位**；用 `is_deleted` ＋ `valid_from` / `valid_until`（date） |
| 模組 ACL 的表 | `module_access_controls`（複數） | **`module_access_control`**（單數）；`target_type` 是 `ROLE` / `ACCOUNT`，值放 `target_secure_code` |
| 表單模板的欄位定義 | `fw_form_templates.form_schema` | **`schema`**（jsonb）；另有 `builder_config` / `allowed_editors` |
| 使用者的員工編號 | `users.employee_number` / `emp_no` | **`users.employee_id`**（varchar 50，組織內唯一）；**兩帳號制的管理員帳號 2026-08-23 起才有號**——新企業由 `_create_default_numbering_rules()` 的第 6 條規則自動發 `ADM001`，既有企業已由 `scripts/migrations/112_backfill_org_admin_employee_id.py` 回填；SYSTEM_ADMIN 型帳號刻意不發（平台級身分不屬企業人事編制） |
| 企業獨立資料庫的庫名 | `fw_org_databases.database_name` | **`db_name`**（另有 `org_id` / `db_host` / `db_port` / `is_ready`）；注意「記錄在、實體庫不在」是既有狀態（本機 `org_14`），反向不一致兩個方向都要查 |
| migration 登記表的欄位 | `schema_migrations.version` | **`schema_migrations.filename`**（含副檔名，例 `116_xxx.py`）；PF-162 卡片裡那句 `INSERT INTO schema_migrations (version)` 是錯的，照抄會拿到 `column "version" does not exist` |
| 編號規則的流水號 counter | `user_numbering_rules.current_counter` / `.code` | **兩個都不存在**；該表只有 `id / secure_code / org_secure_code / name / description / elements / is_active / usage_scope / default_for` 等，**流水號設定與計數藏在 `elements` 這個 jsonb 內**（`components` 陣列裡 `type='sequence'` 的項目）。要看「號碼有沒有被消耗」一律查 `used_user_numbers`，不要找 counter 欄位 |
| 企業獨立資料庫登記表的必填欄位 | 只填 `org_secure_code` / `org_id` / `db_name` | 還要 **`secure_code`**、**`admin_user`**、**`admin_password_enc`**、**`sync_user`**、**`sync_password_enc`** 五個 NOT NULL（2026-08-29 造測試資料時逐一撞出來，錯誤訊息一次只報一個）。查全部必填：`SELECT column_name FROM information_schema.columns WHERE table_name='fw_org_databases' AND is_nullable='NO';` |

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
    -c "SELECT secure_code FROM users WHERE email='ethan@lion.com' AND is_deleted=false;")
  curl -s -c cj.txt -X POST "$BASE/dev/quick-login" \
    -H 'Content-Type: application/json' -d "{\"user_id\":\"$USC\"}"
  # ORG_ADMIN admin-ethanyu@beluga.com 的 user_id 是 jIYEQ-_lZMZNBkVy-hijal
  # EMPLOYEE ethanyu@beluga.com（持 FLOW_DESIGNER + SECURITY_STAFF，測 Key2 場景用）
  #          的 user_id 是 FhsmtyPjsnXYotN-iz_Q-X
  ```
- 常用 API 回應格式備忘：`GET /api/menu` 回 `{menu:[...]}`（樹狀，key 是 `menu` 不是 items）；
  權限中央 API（/api/permissions/*）的企業參數名是 `org_code`（不是 org）
- curl 打非 exempt 的 POST API 需要 CSRF token，從任一登入後頁面的 meta 取（登入回應不含 token）：
  ```bash
  TOKEN=$(curl -s -b cj.txt -c cj.txt "$BASE/dashboard" | grep -o 'csrf-token" content="[^"]*' | cut -d'"' -f3)
  curl -s -b cj.txt -X POST "$BASE/api/xxx" -H 'Content-Type: application/json' -H "X-CSRFToken: $TOKEN" -d '{...}'
  ```

### open_defense / 資安堆疊（備忘已移出，2026-08-30）

動 `modules/open_defense/`、查事件、或改 `.20` 的設定之前先讀：

| 要做什麼 | 讀哪份 |
|---|---|
| 平台側架構、intake、路由、案件、處置中心 | `dev-notes/OPEN_DEFENSE_ARCHITECTURE.md`（第 13 節是從本檔移入的操作備忘：ClickHouse 查詢、三種處置流程、protected targets、intake HMAC 金鑰、EDL 黑名單） |
| `.20` 主機（Vector / Suricata / CrowdSec / od-bridge / ClickHouse）與埠、SSH、風險定調 | `dev-notes/SEC_STACK_ARCHITECTURE.md`（第 11 節同上） |
| `.20` 設定檔權威副本 | `sec-vm-bootstrap/`（**兩邊都要改**，repo 副本不是快照） |

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
以及「NoCode 選單刻意隱藏中」的現況（看不到選單不是壞了）。

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
| End 的 `finish_mode` | `detach`（預設，直接結束）／`cancel`（結束並取消所有未完成節點）／`strict`（等全部完成） | 有並行分支一律用 `cancel`，否則計時分支殘留 |
| 並行分支各自走 End | End 是**流程級**結束，任一分支走到就整個流程 COMPLETED | 另一條的簽核任務會被 executor 視為流程已結束 |
| `AlertBroadcast.broadcast_code` | **不做變數替換**（只有 title/message 有），同 code 覆蓋前一則並清掉已讀記錄 | 它是「最新一則橫幅」不是每案通知，別拿來當逐案稽核 |
| `fw_workflow_templates.timeout_minutes` | 只被寫入 `timeout_at`（`workflow_engine.py:124-139`），**全專案沒有任何地方讀它** | 填了不會有任何效果，逾時要用流程內 Delay 節點 |
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

```bash
bash scripts/run_tests.sh                     # 全部，約 9 分鐘
bash scripts/run_tests.sh -k menu -q
bash scripts/run_e2e.sh                       # Playwright，需服務在跑
```

**基準不寫死數字**（會腐爛）：動工前先跑一次記下當時數字，改完再比對。
以下三個非綠是長期已知、不列入退步：

| 項目 | 狀態 | 成因 |
|---|---|---|
| `test_auth_interceptor.py::...::test_admin_required_for_admin` | failed | 測試庫沒有 RBAC seed（PF-34） |
| `test_od_protected_targets.py`（2 error） | error | 只在完整跑時出現，單獨跑該檔 56 passed＝測試間污染 |
| `test_e2e_portal_cancel.py` | skipped | 寫死的驗收頁 2026-08-03 已消失，永久 skip |

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
| SqlExecutor 白名單（執行時重查、唯讀交易、schema 常數） | `dev-notes/SQL_EXECUTOR_SPEC.md` |
| OsExecutor / FileRead | `dev-notes/OS_EXECUTOR_SPEC.md`（第十四節是實作後記，與規格本文有六處差異，以後記為準） |

**OsExecutor（NT-28）與 FileRead（NT-29）2026-08-30 上線，出廠三道全關**：
`.env` 開關（`OS_NODE_ENABLED` / `FILE_READ_NODE_ENABLED`，**兩者刻意獨立**）、
企業授權（見下條）、`workflow_node_definitions.is_active=false`。
部署說明在 `docs/install/os_node.md`（會推 GitHub）。

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
| graph 寫入（7 個入口，含 publish） | `api/workflows.py` ×4、`api/workflow_routes.py` ×2、`api/mappings.py::publish_mapping` |
| handler 執行期（唯一防線） | `os_executor_handler` / `file_read_handler` |

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
  `file_read_base_dirs` / `file_read_org_base_dirs` 不受影響，那是目錄限制
- **`require_system_admin` 不是替代方案**：它的判準是帳號 user_type 而非企業，
  且只擋設計器可見性、不擋 graph 寫入與 publish。理由詳見
  `dev-notes/OS_EXECUTOR_SPEC.md` 第二節（該節 2026-08-31 更正過一次
  ——「SYSTEM_ADMIN 沒有 form_workflow 合約」是錯的，實際卡在模組 ACL）

**這兩個節點的失敗不會讓 queue 變成 FAILED**：四分法
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

不要為了「修好 502」去改 nginx、重啟 gunicorn 或復活 unit。
重裝步驟與必須沿用的 `ENCRYPTION_MASTER_KEY` 見 BBN 待辦 **PF-39**
（`note_search("PF-39")`），舊 unit 原檔備份在
`/opt/tmp/backup/systemd-beakplatform-20260805/`。

`scripts/init_database.sh` 的路徑一律由 `${BASH_SOURCE[0]}` 推導 `REPO_ROOT`、
`DB_NAME` 從該 repo `.env` 的 `DATABASE_URL` 解析（`DB_NAME` 環境變數可覆寫），
一份腳本 dev 與正式環境通用。**禁止再往裡面寫死 `/opt/BeakPlatform` 或 `-dev`。**

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
| SqlExecutor 三條硬規則、節點執行與 End 三模式（77 行） | `SQL_EXECUTOR_SPEC.md`、`NODE_TEST_INVENTORY.md` 附錄 |

**留下的判準是「不讀到會不會做錯，而做錯時症狀認不認得出來」**——
症狀靜默的（流程變數寫錯地方、重啟 executor 卡死節點、撞開發庫跑測試）留在本檔；
認得出症狀的搬走，靠指針命中。日後新增備忘沿用這條判準。

*前次 2026-08-06：分流細節至 `dev-notes/`、取消工單格式、PERM-02 改為預設套用 D2*
