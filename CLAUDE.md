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

**維護原則**：新的踩坑先問「這是 codex 猜不到的專案特有事實，還是通用工程常識？」
前者才寫進來；屬於「派工時要貼給 codex」的，寫進 `dev-notes/codex_spec/` 並在本檔留指針。

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
只有 `docs/help/` 與 `docs/guides/` 留下——那兩者本來就是使用者文件。
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

`docs/guides/` 已於 2026-08-14 併入 `docs/manual/`，**現在 `docs/` 底下
只剩 `manual/`（MkDocs 制度）與 `help/`（舊的頁內說明 YAML，另案處理）**。
看到舊路徑 `docs/guides/OD_WORKFLOW_VARIANTS.md` 一律視為過時。

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
- 詳細規範在 `/opt/BeakBroodNest/CLAUDE.md` 與 `dev-notes/PROJECT_FACTS.md`，設計理由見 BBN 知識庫 atom 5082

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
- Phase B 起頁面路由**不掛身分 decorator**：url 型選單路徑前綴即 PageRoleGuard 領地；
  單頁專屬資料 API 掛 `@page_keys_required('<menu_code>')`
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

### DATA-01: 帳號查詢必須過濾刪除與停用
- **所有查詢用戶/帳號的地方**，必須同時過濾 `is_deleted=False` 和 `is_active=True`
- 包含但不限於：用戶列表、組織樹、簽核人選擇、角色成員解析、部門成員解析
- 關聯查詢（如透過角色/部門取用戶）需 JOIN User 表確認帳號狀態

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


## 資料庫資訊

- **Host**: localhost
- **Port**: 5432
- **Database**: beakplatform_dev
- **User**: beakplatform
- **Password**: postgres123（開發環境）
- **本機資料皆為測試資料**：變更後可忽略舊資料，不用修正舊資料，除非用戶要求

### 每個 session 都會撞一次的欄位名（2026-08-09 逐一試誤才弄對）

寫 SQL 前先看這張表，可省掉一輪 `column ... does not exist`：

| 想查的東西 | 錯的猜法 | 實際欄位 |
|---|---|---|
| 使用者姓名 | `users.name` / `full_name` | **`users.display_name`** |
| 表單模板是否發行 | `fw_form_templates.status` | **`is_published`**（發行快照在 `fw_published_form_workflows.status='Published'`） |
| API Key 是否可用 | `api_keys.is_active` | **`api_keys.status`**（`active` / `suspended`） |
| 角色是否唯一 | `roles.code` 唯一 | **只有 `secure_code` 唯一**，`ix_roles_code` 是非唯一索引 —— 不同企業的 `SECURITY_STAFF` 是兩筆不同 secure_code |
| OD 路由規則的條件 | `od_form_template_mappings.conditions` | **`match_rules`**（jsonb） |
| intake 事件的處理狀態 | `od_intake_events.status` | **沒有這個欄位**；有沒有建成案件看 `case_secure_code IS NOT NULL` |
| intake 事件的來源 IP | `od_intake_events.actor_ip` | **沒有這個欄位**。全部欄位只有 `correlation_id / intake_key_secure_code / source_system / event_class / severity_id / raw_body / signature_verified / case_secure_code / received_at`——IP 埋在 `raw_body` 的 OCSF JSON 裡，要查 IP 一律去 `.20` ClickHouse 的 `events.actor_ip` |
| 資安案件的分類前綴 | `SECCAT%` | **`CAT_SECURITY_%`**（`security_center.py::SECURITY_CATEGORY_PREFIX`） |
| 選單項目的顯示名稱 | `menu_items.name` / `display_name` | **`menu_items.title`**（另有 `title_en` / `title_zh_cn` / `title_i18n`） |
| 發行快照指向的表單 | `fw_published_form_workflows.form_template_secure_code` | **`source_form_template_secure_code`**（流程那邊同理是 `source_workflow_template_secure_code`） |
| 節點執行紀錄指向的流程 | `fw_node_execution_logs.workflow_instance_secure_code` | **`workflow_instance_id`（bigint，指向 `fw_workflow_instances.id`）**；同專案的 `fw_node_execution_queue` 卻是 `workflow_instance_secure_code`，兩張表不一致 |
| 表單同步佇列的目標表 | `fw_sync_queue.table_name` | **沒有這個欄位**；表名在 `fw_sql_form_registries.table_name`，queue 只存 `form_instance_secure_code` + `published_secure_code` |

### 每個 session 也會猜錯一次的 URL（2026-08-20 補）

blueprint 的 `url_prefix` 與模組名不一致，照模組名猜必 404：

| 想開的頁 | 錯的猜法 | 實際路徑（都要加 nginx 的 `/beakplatform` 前綴） |
|---|---|---|
| 表單中心 | `/form-workflow/center` | **`/forms/center`**（`form_workflow/web/__init__.py:17` 的 prefix 是 `/forms`） |
| 流程**設計器** | `/forms/workflows` | **`/forms/workflows/<workflow_template_secure_code>`**；不帶 sc 的是**列表頁**，兩者都回 200，很容易誤判成「設計器沒壞」 |
| 配對 API | `/api/form-workflow/...` | **`/api/mappings/...`** |

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
  ```
- 常用 API 回應格式備忘：`GET /api/menu` 回 `{menu:[...]}`（樹狀，key 是 `menu` 不是 items）；
  權限中央 API（/api/permissions/*）的企業參數名是 `org_code`（不是 org）
- curl 打非 exempt 的 POST API 需要 CSRF token，從任一登入後頁面的 meta 取（登入回應不含 token）：
  ```bash
  TOKEN=$(curl -s -b cj.txt -c cj.txt "$BASE/dashboard" | grep -o 'csrf-token" content="[^"]*' | cut -d'"' -f3)
  curl -s -b cj.txt -X POST "$BASE/api/xxx" -H 'Content-Type: application/json' -H "X-CSRFToken: $TOKEN" -d '{...}'
  ```

### open_defense 開發備忘

**平台側架構的權威文件是 `dev-notes/OPEN_DEFENSE_ARCHITECTURE.md`（2026-08-10 建立），
動這個模組前整份讀完。** 平台外組件（`.20` 的 Vector / Suricata / CrowdSec /
od-bridge / EDL enforcer / ClickHouse）的權威**已於 2026-08-15（PF-104）收進本 repo**：
架構與運維看 `dev-notes/SEC_STACK_ARCHITECTURE.md`，設定檔副本在 `sec-vm-bootstrap/`
（**已列入 `push_github.sh` 的 `EXCLUDE_DIRS`，不會外流**）。
改 `.20` 的設定時**兩邊都要改**，repo 副本不是快照而是權威副本。
舊路徑 `/opt/Ethan_Lab/ITHome-2026/` **已於 2026-08-15 刪除**
（最終備份 `/opt/tmp/backup/ITHome-2026-final-20260815.tar.gz`），看到一律視為過時。

**`.20` 幾乎每個埠對 LAN 都已收窄（PF-109 收 ingest 面、PF-107 收 SSH 與管理面），
症狀是逾時不是 403**：

| 埠 | 從 `.16` 打得到嗎 |
|---|---|
| `22` sshd | 可以（`.16`/`.10`/`.100` 在 nft 白名單內） |
| `3000` Grafana、`5636` EveBox、`8686` Vector API、`9443` Portainer | 可以（同上三台） |
| `8080` WAF | 可以（同上三台） |
| `8123`/`9000` ClickHouse | 可以（走帳號層網路白名單，不是 nft chain） |
| `8500` od-bridge（stats UI / `/edl`） | 可以（**只有 `.16`**；從 `.10` 的瀏覽器連不到是刻意的） |
| `8688` vector 合成事件注入口 | **不行**，已綁 `127.0.0.1`，要先 ssh 進 `.20` 再打 |

「連線逾時」跟「服務掛了」長得一模一樣，不知道這件事會查錯方向。
要分辨是不是被擋，看 counter 有沒有跳：
`sudo nft list chain inet secstack mgmt_guard_forward | grep counter`。
規則在 `sec-vm-bootstrap/nftables-bootstrap.sh`，完整說明見
`dev-notes/SEC_STACK_ARCHITECTURE.md`。

**`.20` 的 sshd 只收公鑰，密碼認證已停用**（PF-107，2026-08-16）：

`.16` 進 `.20` 一律 `ssh -i ~/.ssh/company-wsl ethan@192.168.0.20`，
**任何形式的密碼登入都不會成功**，不要試、也不要為了「試出密碼」去猜。
舊文件裡的 `P@ssw0rd` 在 2026-05-17 就已失效（用戶自行改過），
現在連密碼這個認證方法本身都不再提供。

排查時先用症狀分辨是哪一層擋的，兩者處理方式完全不同：

| 症狀 | 哪一層 |
|---|---|
| 連線逾時 | nftables（來源不在 `.10`/`.16`/`.100` 白名單） |
| `Permission denied (publickey)` | sshd（沒有可用金鑰） |

**`ethan` 的 OS 密碼刻意不輪替**（Ethan 2026-08-16 定調）：密碼一定會流進
對話記錄與交接文件，交談式 AI 遲早讓它再外洩一次；金鑰不會被寫進文件，
IP 白名單也不會因為誰讀了某份文件而失效。所以那條路走的是「收 IP + 走金鑰」，
而不是「換一個更長的密碼」。**未來 session 不要把「OS 密碼未輪替」重新當成待辦。**

設定片段的權威副本在 `sec-vm-bootstrap/ssh/`（含部署與自動還原手法），
**檔名的 `00-` 前綴是必要的**——`50-cloud-init.conf` 寫死
`PasswordAuthentication yes`，排在它後面的檔案會被靜默蓋過去，`sshd -t` 還是會過。

**「`.16` 內部主機的縱深不足」是已知且已接受的狀態（Ethan 2026-08-16 決定）**：

PF-109 收窄網段、**PF-112（2026-08-16）已補上協定層認證**：`.20:8500` 的
`POST /events` 現在要求 `Authorization: Bearer <BRIDGE_INGEST_TOKEN>`（token 只在
`.20` 的 `.env`，fail-closed，`/health` 免驗），vector 的 `bridge_intake` sink 帶靜態
header。**不是 HMAC**——實測 vector 0.41.1 的 http sink headers 不做模板替換，
且先 batch 再編碼，VRL 算不出最終 body 的簽章。od-bridge 其餘端點
（`/stats`、`/forwards`、`/decisions`、`/edl` 等）**仍無認證，但都是 GET 讀取面**。

風險敘述**到「能在 `.16` 上發封包的人可以拿到 token 後注入事件」為止**，
不要再往上推導。理由是用戶明確定調的：

- **內部主機本來就該有自己的防護**（OS 加固、帳號管理、EDR、網段隔離、備援），
  那是基礎設施的職責，**不能也不該由本專案自行開發來補**
- 本專案的主要目的不是把 `.16` 做成堡壘，這件事**已非主要目的**

**寫給未來 session**：看到「縱深不足」四個字不要自動升級成高風險、不要主動擴大範圍、
不要提議在平台內實作主機加固。要動 PF-112 就照工單做那一件事。
真的發現新的獨立風險，先問用戶，不要自己接著往下修。

### 事件的真實權威是 `.20` 的 ClickHouse，不是平台的案件表（2026-08-15 起）

**平台 `od_intake_events` 只是被 throttle 過的子集，不能用來回答「有多少攻擊」。**
PF-103 實測：同一批 go-ftw 攻擊在 ClickHouse 是 **15 個 CRS 群 5610 筆**，
打進平台只有 **5 群 17 筆**——`.20` vector 的 `intake_global_throttle`
是全域 8 筆/60 秒、不分 key。**做任何攻擊面統計或關聯查詢一律查 ClickHouse。**

```bash
# 密碼在 .20:~/sec-vm-bootstrap/.env 的 CLICKHOUSE_PASSWORD
# 【一律用 header 認證】用 ?user=&password= 或 curl -u 會讓密碼明文過 LAN，
# 並觸發 Suricata ET INFO Outgoing Basic Auth 告警污染資料
curl -s "http://192.168.0.20:8123/?database=secstack" \
  -H "X-ClickHouse-User: secstack" -H "X-ClickHouse-Key: <pw>" \
  --data-binary "SELECT ... FROM events ... FORMAT PrettyCompact"
```

`192.168.0.16` 已在 ClickHouse 帳號層網路白名單內（`clickhouse/users.d/`），
平台端連線不需要改任何網路設定。平台側唯一的客戶端是
`modules/open_defense/services/clickhouse_client.py`，**禁止繞過它另建連線**。

**但「全量」有條件**：`events` 表原 TTL 只有 6 小時，2026-05-09~08-08 的事件
曾被刪光、2026-08-08 才從 eve.json 歸檔回灌並改成 180 天分層保留。
**跨越 2026-08-08 的時間窗不要宣稱「這段期間只有 N 筆」。**

留在本檔的是五個「唯一實作」，新增功能一律加在這裡，**不要各自重寫**：

| 檔案 | 管什麼 | 繞過的後果 |
|---|---|---|
| `modules/form_workflow/services/task_authorizer.py` | 簽核授權（快照 ∪ 當前角色 ∪ 生效中代理） | 判定點共 **12 處**，漏一處就出現「清單看得到但點不了」 |
| `modules/open_defense/services/routing_service.py` | intake 事件 → form_template 的規則式路由 | intake 是對外 webhook，各自查表會讓路由行為分歧 |
| `modules/open_defense/services/payload_profile_service.py` | 原生 payload 的路徑取值、扁平化、共同軸線正規化 | 各自攤平會讓 form_data 的 key 命名分歧，表單欄位對不上就整片空白 |
| `modules/open_defense/services/protected_target_service.py` | 封鎖目標的保護清單判定（PF-83） | 各自比對網段會讓「不得封鎖」的邊界分歧，而錯誤方向是封掉自家設備 |
| `wf-dnd-nodes.js::resolveNodeIconUrl()` | 流程設計器節點圖示 URL | 6 處曾各寫一份，導致所有從 DB 載入的 graph 節點全變空方框 |

- **共同軸線 6 個 key 是相容性契約**：`severity_id` / `actor_ip` / `target_host` /
  `source_system` / `finding_rule_id` / `occurred_at`。不論 OCSF 或原生 payload，
  intake 都會把它們正規化後寫進 `form_data`；SLA、聚合降噪、風險分數、
  處置中心清單全部讀這組。**改名等於同時弄壞四個機制**
- **nginx 前綴一律渲染時補、不寫進 DB**（`workflow_node_definitions` 與所有
  既有 graph 的 icon 都是 `/static/...` 無前綴，這是正確的存法）
- 資安案件處置中心的清單 API 是 `/api/open_defense/cases`（不在 `/admin` 底下）

**現有三個處置流程，各綁一張表單**（2026-08-13 建置，指南
`docs/guides/OD_WORKFLOW_VARIANTS.md`，建置腳本
`scripts/examples/provision_od_workflow_variants.py` + `od_workflow_graphs.py`）：

| 流程 | 表單 code | 適用編制 |
|---|---|---|
| `SEC_INCIDENT_FLOW`（原有） | `SEC_INCIDENT_RESPONSE` | 假設 15 分鐘內有人看，適合輪班 SOC |
| `SEC_IR_FLOW_SOC_TEAM` | `SEC_IR_SOC_TEAM` | 3~8 人輪班，簽核＋SLA 計時雙軌，逾時只催辦 |
| `SEC_IR_FLOW_SOLO` | `SEC_IR_SOLO` | 單人 8 小時班，夜間自動封鎖 TTL 24h 後人工複核 |

**一張 form_template 同時只有一個生效流程**——intake 是「依 form_template 取
**最新 Published** 的 `fw_published_form_workflows`」（`intake_service.py:314-319`）。
所以「切換流程」＝同一張表單重新發行綁不同 workflow；
「不同案件走不同流程」＝**必須不同的 form_template**，靠 `od_form_template_mappings`
的 `match_rules` + `priority` 分派。新表單的 `category_secure_code` 必須沿用資安分類
（`CAT_SECURITY_%`），否則案件不會出現在處置中心。

二線簽核角色是 `SOC_SUPERVISOR`（命名沿用 `docs/guides/SOC_ROLE_DESIGN_GUIDE.md`）。
**新增資安角色後必須把它加進 `menu_role_requirements`**（雙鑰匙 Key2），
否則只持有該角色的人看不到處置中心選單，簽核任務變成「清單看得到、點不進去」。

**真實 suricata 告警的 `actor_ip` 大量是 `192.168.0.20`**（近 200 筆裡佔 25 筆）——
那是本平台 Cloudflare 路徑上的 nginx，不是攻擊者。成因與 NET-01 同源：
Suricata 架在 `.20` 這個流量出口上，外部訪客經反代進來時它看到的來源就是代理自己。
**任何會自動處置 `actor_ip` 的流程都必須排除私有網段**，否則會反覆封鎖自家基礎設施，
而且無人時段的自動處置沒有人會發現（2026-08-13 差 12 分鐘就真的發生）。
小企業單人版的分流節點已內建這道排除（`od_workflow_graphs.py::PUBLIC_IP_REGEX`／
`PRIVATE_IP_REGEX`），這類案件改走人工路徑而非忽略。

**服務層保護已於 2026-08-13 完成（PF-83），流程怎麼寫都繞不過去**：

- `create_decision()` 是**唯一的 block 寫入點**——另外兩處直接 `OdDefenseDecision(...)`
  （`api/admin/decisions.py` 人工撤銷、`expiry_service.py` TTL 到期）都硬編碼
  `action='unblock'`，不必也不該加保護。**新增任何會寫 block 的路徑一律走
  `create_decision()`**，別自己 new model
- 只擋 `action='block'` 且 `target_type in (ip, ipv6, cidr)`；命中拋
  `ProtectedTargetError`（繼承 `DecisionValidationError`，既有 catch 接得住）
- 保護來源三層，**內建那層 2026-08-16（PF-117）起已 per-org 化**：
  該企業 `od_protected_targets` 裡 `origin='builtin'` 的 16 筆出廠條目
  （RFC1918／回送／link-local／CGNAT／群播／保留＋IPv6 ULA、link-local，**企業可個別停用**）
  ∪ 設定（`OD_PROTECTED_EXTRA_NETWORKS` env ＋ `TRUSTED_PROXY_IPS`）
  ∪ 企業自訂（同表 `origin='custom'`，管理頁 `/open-defense/protected-targets`）
- 出廠值在 `backend/app/defaults/od_protected_defaults.py`，建企業時自動 seed
  （`create_organization()` 與 `init_system_organization()` **兩處**都接了，後者不走前者）。
  `protected_target_service.BUILTIN_PROTECTED_NETWORKS` 只剩 fail-safe 用，
  兩份清單由測試把關不得漂移
- **fail-safe 的兩個查詢條件刻意不同，不要「順手統一」**：判斷要不要回退硬編碼常數看的是
  「該企業有沒有 builtin 記錄」（**不帶 `is_active`**），實際判定才只取 `is_active=True`。
  帶了 `is_active` 的話，企業合法地把 16 條全部停用會被誤判成 seed 漏掉而回退常數，
  使用者的停用被靜默忽略且不報錯
- **builtin 條目可停用、可改名稱備註，但不可刪除、不可改 `target_value`**（API 回 400）——
  刪掉後 fail-safe 會把它救回來，行為看起來像「刪不掉」
- `TRUSTED_PROXY_IPS` 那層**不 per-org**：企業把 `192.168.0.0/16` 停用後，
  平台反代仍受保護且網段遮蔽（`source='platform'`、`network=None`，PF-117 第 5 點）
- **保護比對用 `overlaps`、豁免比對用 `subnet_of`，兩者不對稱是刻意的**：
  前者用包含語意會漏掉封 `0.0.0.0/0`；後者用交集語意會讓「豁免一台內網主機」
  變成「整個 `/0` 都能封」。改動這兩個判定前先看
  `backend/tests/test_od_protected_targets.py`（含 mutation 驗證過的案例）
- `::ffff:192.168.0.20` 會正規化成 IPv4 再比對，否則那是一條繞過路徑
- **TEST-NET（`203.0.113.0/24` 等）刻意不納入內建清單**——端對端驗證拿它當
  「公網攻擊者」，保護了會讓驗證失真
- 正當的內網封鎖（例：內部被入侵主機要隔離）有兩條路：管理頁加一筆 `exempt`
  項目，或流程節點設 `allow_protected_target: true`（後者會在
  `decision_metadata.protected_override` 留稽核痕跡）。節點另有
  `on_protected: 'error'|'skip'`，預設 `error`（流程停住等人處理）
- **節點的這兩個設定目前只能改 graph JSON**：DecisionWriter 沒有設計器屬性面板，
  而 `config_schema` 沒有任何前端消費者（面板是 `wf-node-*.js` 的硬編碼 switch，
  現有分支只涵蓋 15 種節點型別）。migration 098 是為了讓 DB 定義完整，
  **不會讓設計器多出可設定的欄位**。補面板見待辦 PF-84

**`od_form_template_mappings` 是 `priority` 由大到小評估、命中即停**
（`routing_service.py::evaluate_routing_rules`，`order_by(priority.desc(), id.asc())`）。
`match_rules=[]` 且 `event_class=NULL` 即 catch-all。所以切換全站流程最省事又可逆的
做法是加一條 priority 極高的 catch-all，要切回去只要停用它，不必逐條改回原本
依 event_class 分派的四條 priority 0 規則。**切換後一定要試算確認命中**
（`evaluate_routing_rules(org, body, payload_kind)`），不要等真實事件進來才發現沒切成功。

**重複送測試事件時，聚合降噪會把「同 `finding.rule_id` + 同 `actor.ip` + 同
`target.host`」的事件併進既有案件**，不會開新案、不會重跑流程——拿到的是上一輪的
節點軌跡。驗證流程改動時三個鍵都要換（例：`rule_id` 加隨機後綴、`target.host` 帶
nonce），否則會誤判成「改了沒用」。

**打 intake webhook 做端對端測試時，API key 的 secret 用 `decrypt_secret()` 取回**
（secret 是加密存的，不是 hash——**不必為了測試另建一把 key**）：

```python
from app import create_app
from app.models.api_key import ApiKey
from app.services import api_key_service
app = create_app('development')
with app.app_context():
    rec = ApiKey.query.filter_by(key_id='ak_a9bf7cf8a60f7d97').first()
    secret = api_key_service.decrypt_secret(rec)      # bytes
```

簽章是 `sha256=<hex(HMAC-SHA256(secret, f"{ts}\n{body}"))>`，
headers 用 `X-BP-Key-Id` / `X-BP-Timestamp` / `X-BP-Signature`
（舊契約的 `X-OD-*` 仍相容）。body 必須與計算簽章時**同一份 bytes**，
不要 `json.dumps` 兩次（key 順序或空白不同就 401）。
跑腳本前要 `set -a && source .env && set +a`（缺 SECRET_KEY 會 ValueError）。

**HMAC 金鑰是 raw bytes，不是使用者拿到的那串字**（2026-08-17 踩到，
外部整合文件的 curl 範例錯了很久也沒人發現）：
`create_api_key()` 回傳、UI 顯示一次的 secret 是
`base64.urlsafe_b64encode(32 bytes)` 的**字串**，而驗簽用的是解碼後的 bytes
（`decrypt_secret()` 回的就是 bytes，所以上面那段測試碼是對的）。
外部整合者拿到的是字串，**必須先 `base64.urlsafe_b64decode` 再做 HMAC**：

```bash
KEY_HEX=$(printf '%s' "$SECRET" | python3 -c 'import base64, sys; s = sys.stdin.read().strip(); s += "=" * (-len(s) % 4); print(base64.urlsafe_b64decode(s.encode("ascii")).hex())')
SIG=$(printf '%s\n%s' "$TS" "$BODY" | openssl dgst -sha256 -mac HMAC -macopt hexkey:"$KEY_HEX" -hex | awk '{print $NF}')
```

直接把 base64 字串當金鑰會**恆得 401**，而平台對所有認證失敗一律回同一個
`auth_failed`（刻意不區分原因），從回應完全看不出是這個原因。

**兩支對外範例腳本（會推上 GitHub，改 intake 契約時要同步維護）**：

| 腳本 | 用途 |
|---|---|
| `scripts/examples/provision_od_intake_for_org.py` | 空白企業一次建起受理鏈路（分類／表單／流程／發行／catch-all 路由／API Key），冪等，`--org` 吃 secure_code 或 domain_name |
| `scripts/examples/od_intake_send_event.py` | 送 OCSF 事件的單檔 CLI（只用標準函式庫），`--dry-run` 對帳、`--print-curl` 產生等價指令，九種退出碼區分可否重試 |

**新企業的 OD 受理鏈路缺一不可有六件**：資安分類（secure_code 必須
`CAT_SECURITY_` 開頭，否則案件不會進處置中心）→ 表單 → 流程 → 配對發行
→ 路由規則 → API Key。缺任何一件事件都進不來，而 dashboard 與處置中心
就是恆為 0。使用者手冊第 9 章 `docs/manual/09_from_zero/` 是這條鏈路的 SOP。

### NoCode 選單目前刻意隱藏中（2026-08-07 起，鐵人賽期間）

**看不到「子系統開發模組」選單是預期狀態，不是壞了，不要去修。**
`MODULE_INFO['menu_items']` 由環境變數 `NOCODE_BUILDER_MENU` 控制（不等於 `on` 即為空），
既有三筆 `menu_items` 已設 `is_deleted=true`。模組本身照常載入——路由、API、portal
全部可用，直接輸入網址進得去。復原步驟與「為什麼用 is_deleted 而非 is_active」
見 `dev-notes/NOCODE_MENU_HIDE.md`。

### NoCode Builder / Portal 開發備忘（2026-07-28 起）

**環境事實：開發機上目前有一個可用的 NoCode 子系統**，由
`scripts/examples/provision_relief_donation_demo.py --force` 建置：

| 項目 | 值 |
|---|---|
| 子系統（published） | `HJGEoAh6PBv5IXNHhMTu5P`（急難救助物資捐贈） |
| portal_path_id | `HdjFFvF-` |
| welcome 頁（2026-08-04 起已 published，內含雙 menu 示範） | `QlqVasK5fsLFMfUpPEvvFz` |
| 我的捐贈登記（要 `donation.manage`） | `Gqm4tuQEsBgituXVaDrCrr` |
| 物資公佈欄（要 `bulletin.read`） | `Ogi303_5kwPZdEE2IildYG` |

另有一個 `DzSQ8oTRKCnMVbuxS-431u`（`Ethan的test`，draft，用戶自建，**不要動**）。
重建腳本會**產生全新識別碼**，跑過就要回頭更新本表。

**portal 測試帳號**（username 是完整 e-mail，密碼一律 `relief123456`）：

| username | 階級 | 管理角色 |
|---|---|---|
| `guest_demo@example.com` | GUEST (0) | — |
| `member_demo@example.com` | MEMBER (10) | — |
| `staff_demo@example.com` | STAFF (50) | — |
| `admin_demo@example.com` | ADMIN (90) | SYSTEM_ADMIN |
| `bulletin_mgr@example.com` | MEMBER (10) | BULLETIN_MANAGER |
| `auditor_demo@example.com` | MEMBER (10) | AUDITOR |
| `donor_a_pf13@example.com` / `donor_b_pf13@example.com` | MEMBER (10) | — |

`bulletin_mgr` / `auditor` 的管理角色刻意留在 MEMBER 階級，
才驗得出「管理角色是聯集、不隨階級繼承」；`donor_a` / `donor_b` **有捐贈資料**，
可驗列級隔離（兩人互相看不到對方）。

**識別碼被重建後怎麼重查**（provision 只印子系統 sc 與 path_id）：

```bash
PGPASSWORD=postgres123 psql -h localhost -U beakplatform -d beakplatform_dev -t -A -F'|' -c "
SELECT s.secure_code, s.name, s.status, n.secure_code AS node_sc, n.name, n.node_type,
       n.parent_secure_code, n.page_layout_secure_code
FROM dc_sub_systems s LEFT JOIN dc_site_map_nodes n
  ON n.sub_system_secure_code = s.secure_code AND n.is_deleted = false
WHERE s.is_deleted = false ORDER BY s.created_at DESC, n.display_order;"
# portal_path_id
PGPASSWORD=postgres123 psql -h localhost -U beakplatform -d beakplatform_dev -t -A -F'|' -c \
  "SELECT code, value_str FROM lookup_items WHERE value_str LIKE '%' ORDER BY id DESC LIMIT 20;"
# portal 帳號
sqlite3 /opt/BeakPlatform-dev/data/nocode_portals/<SS>/portal.db \
  "SELECT username, group_code, level_code, is_active FROM portal_users;"
```

**portal 帳號快速切換（開發工具，2026-08-03 起）**：
`/dev/portal-quick-login` 選子系統 + 帳號即免密碼切換，
之後走**正式**公開路由，列級擁有權／管理角色／個人覆寫全部真實生效
——這是 IR 設計器「預覽階級」做不到的（那是合成身分，`user_id=None`、`roles=[]`，
只驗得了階級/群組層的准入）。curl 版：

```bash
BASE=http://192.168.0.16:7000/beakplatform; SS=HJGEoAh6PBv5IXNHhMTu5P
USC=$(curl -s "$BASE/dev/portal-quick-login/users/$SS" | python3 -c \
  "import sys,json;d=json.load(sys.stdin);print([x['secure_code'] for x in d['data'] if x['username']=='member_demo@example.com'][0])")
curl -s -c q.txt -b q.txt -X POST "$BASE/dev/portal-quick-login" \
  -H 'Content-Type: application/json' \
  -d "{\"sub_system_sc\":\"$SS\",\"user_secure_code\":\"$USC\"}"
curl -s -b q.txt -o /dev/null -w '%{http_code}\n' "$BASE/public/portal/HdjFFvF-/p/$PAGE_SC"
```

**免密碼登入的邏輯一律留在 `backend/app/web/dev.py`**（該檔在 `push_github.sh`
排除清單、正式部署整個移除）。`portal_auth_service` 只提供
`build_session_data()` / `store_session()` 兩個**不含身分驗證語意**的介面。
**禁止**在正式服務層新增任何可免密碼登入的函式——那會被推上公開 repo，
等於在正式程式碼裡預留後門。

**架構原則（2026-08-03 用戶定案，違反者不是 bug 是架構錯誤）**：

- NoCode 子系統的資料**自給自足**。要與平台交換一律是**平台寫入、平台去讀**，
  不從 SQLite / NoCode 側取用平台資料（流程元件取資料算平台本身的功能，不在此限）。
  目的有二：把 NoCode 側的 SQL injection 受害範圍鎖在 SQLite 內攻不進平台；
  以及保持 **NoCode 本來就能獨立成單一專案**的可分離性（整合進 BeakPlatform 是產品策略）
- 因此 `registry.get_resource()` 在 portal 語境對無 prefix 的平台資源一律回 None
  （`backend/app/pageir/registry.py:46-47`）**是這條原則的實作，不要放寬**。
  症狀會是 `PageIrRenderError: Unregistered resource: user` → 422，
  正解是把頁面改綁 `portal:` / `formflow:` 資源，不是去改 registry
- **所有 nocode 子系統頁面一律以 portal 方式渲染**（員工也一樣，只是身分來源不同），
  平台端不存在「nocode 頁面」。故 `_ACTIONS`（平台側動作白名單）永遠是 0 筆，
  那是預期狀態不是待補項

**兩個帳號世界完全分離**，測試時 cookie jar 要分開（同一個 jar 也能並存，但別混淆）：

| | 平台世界 | Portal 世界 |
|---|---|---|
| 入口 | `/nocode/workspace/<sub_system_sc>`（統一工作區） | `/public/portal/<path_id>/...` |
| 帳號 | PostgreSQL `users` | 子系統 SQLite `portal.db` 的 `portal_users` |
| session | Flask-Login | `session['portal_sessions'][sub_sc]`（per 子系統並存） |
| 渲染語境 | `platform` | `portal`（互斥，跨界解析一律 fail-closed） |

```bash
# portal 帳號登入（表單 POST，非 JSON；用獨立 cookie jar）
curl -s -c p4_cj.txt -X POST "$BASE/public/portal/<path_id>/login" \
  -d 'username=<帳號>&password=<密碼>'

# portal 頁的 CSRF token 在頁面 meta（平台的 /dashboard 取不到 portal 用的）
TOKEN=$(curl -s -b p4_cj.txt "$BASE/public/portal/<path_id>/p/<page_sc>" \
  | grep -o 'csrf-token" content="[^"]*' | cut -d'"' -f3)

# 子系統 SQLite 直查（portal.db=帳號/群組/階級，portal_data.db=業務資料）
sqlite3 /opt/BeakPlatform-dev/data/nocode_portals/<sub_system_sc>/portal.db \
  "SELECT username, group_code, level_code FROM portal_users;"
```

- `path_id` 不等於 `sub_system_sc`，對照在 `lookup_items.value_str`：
  `SELECT code, value_str FROM lookup_items WHERE value_str='<sub_system_sc>';`
- **Page IR 設計器網址是 `/nocode/ir-designer/<page_layout_secure_code>`**
  （預覽是同路徑 `+ /preview`）。它吃的是**頁面** secure_code，不是子系統 sc，
  路由定義在 `modules/nocode_builder/web/__init__.py:42`
- **設計器模板已於 2026-08-04 拆分**（`_ir_designer_body.html` 只剩 4.5KB 外殼，
  舊文件與舊卡片都還指著它，照著找會找不到東西）：

  ```
  ir_designer.html
  └── _ir_designer_body.html          外殼 + 頂部工具列（預覽身分區塊）
      ├── _ir_designer_issue_modal.html
      ├── _ir_designer_save_template.html
      ├── _ir_designer_layout.html     版面編輯區
      └── _ir_designer_props.html      全部 widget 屬性面板（42KB，改屬性面板來這裡）
          ├── (import) _ir_designer_access_matrix.html   元件准入 macro render()
          └── (include) _ir_designer_menu.html           menu widget 面板
  ```

  元件准入是 `access_matrix.render(actions_expr, write_hint)` macro，
  在 props 內被呼叫四次（一般 widget／master_detail／actions／form），
  **改准入 UI 只要改 macro 一處**，不要在四個地方各改一份
- **`_ir_designer_body.html` 有兩個宿主頁，`<script>` 清單各自維護**
  （2026-08-06 踩到，commit `86a75b75`）：

  | 宿主 | 網址 | 特徵 |
  |---|---|---|
  | `ir_designer.html` | `/nocode/ir-designer/<頁sc>` | 單頁設計器，**沒有 Site Map** |
  | `workspace.html` | `/nocode/workspace/<子系統sc>` | 工作區「頁面設計」分頁，**內嵌整套設計器** |

  兩邊共用同一份 partial 與同一個 Alpine 元件 `irDesigner()`，
  但 `{% block scripts %}` 是各寫各的。**新增設計器要用的 JS 時兩邊都要加**——
  PF-29 加當時的 `shared-menu.js` 時只加了 `ir_designer.html`，
  導致工作區內該檔掛的全域恆 `undefined`，
  按[另存為共用選單]噴 `Cannot read properties of undefined (reading 'create')`。
  （該檔 2026-08-06 已更名 `shared-component.js`、全域改為 `BkSharedComponent`。）
  **日常用的是工作區那邊，冷門的單頁設計器反而是好的**，所以測試時要測工作區。
  現行依賴：`window.BkCaps`（base.html 的 capability.js）／`BkPageTemplate`
  （`page-template.js`）／`BkSharedComponent`（`shared-component.js`）
- **portal 頁是獨立模板 `portal_page_v3.html`，不繼承 `layouts/base.html`**。
  平台頁自動有的東西（`timezone.js`／`BkTime`、i18n、capability.js）在這裡
  **都要自己載入**。portal 又是公開路由，`auth_interceptor` 在設定
  `g.locale` / `g.timezone` 之前就 return 了，所以時區一律吃 fallback `Asia/Taipei`
- **這條對 portal 的錯誤頁與任何新增 portal 模板一律適用**，不只主頁。
  錯誤路徑最容易漏：`pageir/page_error.html` 繼承了 `layouts/base.html`，
  被 portal 端共用了很久，導致 portal 渲染失敗時**外部訪客拿到帶平台
  navbar／選單／`capability.js` 的頁面**（2026-08-03 commit `853b5aaf` 修，
  改用 `modules/nocode_builder/portal_page_error.html`）。
  **新增任何 portal 端要用的模板前，先確認它沒有 `{% extends "layouts/base.html" %}`。**
  平台世界的 `/p/` 與純平台預覽仍用原本的平台版錯誤頁，那是正確的
- **在 Page IR 頁面放 form.io 送出按鈕時必須寫 `"input": false`**，
  否則 payload 會多一個 `submit: true` 欄位，被後端欄位白名單擋成
  400 `unknown_field`
- **portal.db schema 現行版本 v4**。v3（PF-7，2026-08-03 起）新增六張權限碼制表
  `portal_permissions` / `portal_admin_roles` / `portal_role_permissions` /
  `portal_user_roles` / `portal_user_permissions` / `portal_level_permissions`；
  v4（PF-44 階段 A，2026-08-05 起）新增 `portal_files` / `portal_file_acl`
  （portal 檔案元件的歸屬與個別檔案 ACL，實體與加密仍在平台 `platform_files`）。
  升級由 `ensure_portal_schema()` 階梯式自動執行（0→2→3→4，冪等，**lazy**
  ——子系統被存取到才升，所以看到某個子系統還是舊版本不代表壞掉），
  **改 portal.db schema 一律加在該函式，不要另寫 migration 腳本**。
- **Page IR widget 的設定值一律直接掛在 widget 物件上**
  （`{"type": "file_box", "upload_by": "designer", ...}`），**沒有 `settings` 子物件**。
  這條對所有 widget 皆然，但 `file_box` 上已經有人猜錯過一次——
  讀成 `widget["settings"]` 時每個欄位都回退預設值，症狀是**設定看起來存了、
  行為卻永遠是預設值**（設計者上傳被判成 `upload_by=portal_user` 而全數 400）。
  有效權限計算的唯一實作是 `services/portal_permission_service.py`
  （階級 rank 向下繼承、管理角色聯集不繼承、個人 deny 最優先、停用帳號回空集合、
  匿名只吃階級權限），**禁止各處自行組 SQL 算權限**。
  access_matrix 規則**只認**權限碼制 `{"required_permissions": [...], "match_mode": "any"|"all"}`
  （PF-13，2026-08-03 起）。舊的 `{groups, min_level}` 形式已完全移除，寫入會被 400 擋下，
  runtime 判定回 `bad_matrix`（`group_denied` / `level_missing` / `level_denied` 三個 reason
  已不存在）。`portal_groups` / `portal_levels` 兩張表**仍在**——階級 rank 是
  `portal_level_permissions` 的權限來源，群組則降為單純的帳號屬性、不再參與准入判定。
  寫入端驗證有兩處，改格式要同時改：`api/site_map_api.py::_validate_access_matrix`
  與 `backend/app/pageir/schema_v3.json` 的 `$defs.portal_access_rule`。
  權限碼格式固定 `resource.action`（小寫 snake_case），與平台的 permission code 不共用。
  管理面（PF-8a/8b）在 `services/portal_permission_admin_service.py` +
  `api/portal_permission_api.py`（前綴 `/api/nocode-builder/sub-systems/<ss>/portal/...`）與
  工作區第四個分頁「權限矩陣」（`_workspace_perms.html` + `workspace-perms.js`）。
  角色／階級權限與帳號角色一律**整組覆寫**（PUT 全量 codes），不是增量。
  建立子系統會自動 seed 六個 `is_system` 管理角色；既有子系統在首次讀 permission-model 時補 seed。
  權限碼被角色／階級／個人覆寫／site map access_matrix 引用時**拒絕刪除（409）**。
- **Page IR v3 menu widget**：完整欄位規格見 `dev-notes/PAGE_IR_SPEC.md` §3.7
  （自動模式在 `dev-notes/SHARED_COMPONENTS_SPEC.md` §5）。三件最容易靜默失效的：
  - **items 是完全自訂的樹**，不跟著 site map 的結構與順序走（早期版本相反）。
    名稱與圖示仍即時取自 site map；節點被刪或停用時該項連同 children 整枝消失
  - **底圖存 `platform_files.secure_code`，不是 `DcBackground.secure_code`**
    （用 `/api/nocode-builder/backgrounds` 回應的 `platform_file_sc`）——
    存錯的症狀是「選了底圖完全沒反應、也不報錯」
  - 顏色一律 `^#[0-9a-fA-F]{6}$`，schema 與 renderer `_menu_style()` **兩道都要擋**
    （值最後會進 inline style）
- **Page IR v3 有三個版面引擎**（2026-08-05 起，定版 `dev-notes/PAGE_IR_LAYOUT_ENGINES.md`）：
  `page.engine` = `flow`（預設，即原本的縱向流 + layout widget 等分）／
  `grid`（矩陣切格合併，欄寬 fr、列高 px）／`free`（12 欄 × `row_unit` 自由放置）。
  **沒有 `engine` 欄位＝flow，既有 IR 一行都不用改。**
  核心約束：**三個引擎只差外殼，zone／frame 內部一律是既有 flow widget 序列**，
  `render_widget` macro 不因引擎而異，禁止跨引擎巢狀。
  `grid`／`free` 的窄螢幕行為是**水平捲動 + `min_width`，不塌不縮放**（設計者自己決定場景）。
  `pageir.css` 那條 720px 塌一欄的規則只作用於 flow 才輸出的 `--responsive` 變體，
  **新增任何會受該規則影響的 widget 時要記得跟著輸出這個 class**
  （master_detail 的 master 區塊就漏過一次）。
  **menu widget 的 provider 要求 render context 同時有 `sub_system_sc`、`portal_user`、
  `path_id`**（連結必須指向 `/public/portal/<path_id>/...`），少任何一個一律回空陣列，
  畫面上就是「沒有可顯示的項目」。IR 設計器預覽從 menu widget 上線起就漏傳 `path_id`，
  導致**預覽的選單永遠是空的**（2026-08-05 修，`web/__init__.py::ir_designer_preview`）。
  新增任何會呼叫 `set_render_context('portal', ...)` 的路徑時，
  對照 `portal_public.py` 的參數清單，不要只傳前兩個。
  設計器在 `/nocode/ir-designer/<page_sc>`：grid 用 `grid-layout-editor.js` 的
  `layoutOnly` 模式，free 用 GridStack。**zone／frame 消失時（合併、重建矩陣、刪除框）
  裡面的元件必須有去處**（併入接手的 zone 或回未放置清單），
  否則會靜默遺失且使用者無從察覺——這個坑 grid 與 free 各踩過一次。
- **portal 業務表有列級擁有權**（2026-07-30 起）：表固定有系統欄位 `portal_user_ref`
  （值 `u:<portal user_id>` / `g:<guest_token>`），視圖 `DcCrudView.row_owner_scope`
  預設 **`own`**（只能存取自己建的列），要共享的表必須明確設 `all`。
  `portal_user_ref IS NULL` 的舊列在 own 模式下誰都看不到——
  **「portal 頁表格突然空了」第一個要查的就是這個**，不是權限判定壞了。
  既有表補欄位用 `scripts/add_portal_user_ref.py --apply`（冪等）。
  細節與 `owner_ref` 傳參規則見 `dev-notes/codex_spec/portal.md`
- **判斷一個 NoCode 頁面「還活著」必須走雙路徑 OR**，只看 site map 會誤判：
  ```
  存活 = (有存活 dc_site_map_nodes 指向 且 該節點的子系統存活)
      OR (有存活 dc_sub_system_pages 掛載 且 該子系統存活)
  ```
  portal 頁**不一定掛在 site map 節點下**，可能只透過 `dc_sub_system_pages` 關聯。
  **反向也成立**：只掛在 site map 節點、沒有 `dc_sub_system_pages` 的頁（每個子系統的
  welcome 就是），只查 `DcSubSystemPage` 一樣會誤判。`/api/nocode-builder/pages/<sc>`
  的 `sub_system_secure_code` 就犯過這個錯，害設計器的 menu 面板選不到任何節點
  （2026-08-03 commit `d61b79fb` 改走 `get_owner_sub_system_codes()` 修正）。
  **同一個坑犯過第二次**：`ir_designer_preview()` 帶 `?sub=` 時也只查
  `dc_sub_system_pages`，導致**每個子系統的 welcome 頁 portal 預覽必然 404**
  （commit `93c648fa` 修）。
  **第三次、而且是在公開路由上**：`portal_public.py` 三處掛載判定
  （`portal_page` / `portal_widget_rows` / `_resolve_portal_widget_common`）
  同樣只查 `dc_sub_system_pages`，導致**每個子系統的 welcome 頁在正式 portal 上
  必定 404**，即使已 published。現收斂成單一 `_portal_page_mounted()`：雙路徑 OR，
  有掛載記錄但全部停用一律拒絕，走 site map 節點時可見性交給 `check_page_access`。
  凡是要判斷「這頁屬不屬於這個子系統」，
  一律用 `get_owner_sub_system_codes()`，不要自己查單一張表。
  2026-07-31 清孤兒時只看 site map，就這樣誤刪了兩個 published 驗收頁，
  其中一個是 `test_e2e_portal_cancel.py` 寫死依賴的
  `FORMTEST00000000000001`，**刪掉會讓 E2E 靜默 skip 而不是報錯**（至今未恢復）。
  此判定的**唯一實作**是
  `modules/nocode_builder/services/page_ownership_service.py`
  （`is_page_reachable()` / `get_owner_sub_system_codes()`），
  存取層、刪除級聯、清理腳本共用，**禁止各自重寫**。
  注意 `is_page_reachable()` 對「零關聯」回 `True`（純平台 IR 頁要放行），
  所以判斷「該不該刪這個頁」時條件要寫成
  `not is_page_reachable(sc) or not get_owner_sub_system_codes(sc)`。
  既有孤兒用 `scripts/cleanup_orphan_nocode_pages.py --dry-run/--apply`（冪等）清。
- **建立子系統會自動附贈一個 welcome 節點 + welcome 頁面**，
  且 **site map 只允許一個根頁面**（再建根節點會回 400
  「Site Map 只能有一個根頁面 (welcome)」，新節點要指定 `parent_secure_code`）。
  測級聯或建測試資料時會撞到。
- 權限判定失敗**一律回 404**（不洩漏存在與否）；查原因看
  `sudo journalctl -u beakplatform-dev.service --since "-5 min" | grep reason=`
- 權限模型與判定鏈：`dev-notes/PORTAL_ACCOUNT_SPEC.md`；
  完整交接與踩坑清單：`dev-notes/handoff_nocode_n1_n5.md`
- v2 `layout_json` 已退役，`/p/` 遇到會回 410；設計器只認 `ir_version: 3`
- **頁面版面樣板庫（PF-24~28、PF-32）＝複製語意**，規格 `dev-notes/PAGE_TEMPLATE_SPEC.md`。
  只有三件事在動工前非知道不可：
  - **同子系統套用完全不淨化**（menu 的 `items[].node`、`shared_ref`、access_matrix
    原封不動保留）。「另存為樣板」存的是**當下那頁的完整 IR**，內建樣板的「零綁定」
    是那六筆種子資料的內容、**不是會傳染的屬性**。跨子系統才淨化，唯一實作是
    `page_template_service.sanitize_template_ir()`，**禁止各處自行清理引用**
  - `instantiate` **只建 `DcPageLayout`**，site map 節點與子系統掛載是前端
    `workspace.js::finishPageCreation()` 接手做的
  - `scope='system'` 只能由 `scripts/seed_system_page_templates.py` 建立，API 一律 403

- **子系統層級共用元件＝引用語意**（2026-08-06 起，取代 PF-29 的「共用選單」）——
  改一次，所有引用它的頁面同步生效。**定版規格 `dev-notes/SHARED_COMPONENTS_SPEC.md`
  （資料模型、API、schema、設計器 UI、menu 自動模式全在裡面，動工前整份讀完）**。
  頁面端只寫 `{"type":"menu","id":"menu-1","shared_ref":"<sc>"}`。
  留在本檔的是四條「猜不到且錯了會靜默失效」：
  - **完全共用**：引用時一律取共用元件的值，**頁面端不覆寫任何欄位**。
    同一份選單要 A 頁橫式、B 頁縱式 → 建兩個共用元件
  - **唯一例外 `access_matrix` 是交集**：共用元件與頁面 widget 兩份都要通過才渲染。
    它是授權邊界不是外觀，取其一會讓某邊設定靜默失效
  - **展開只在 `renderer._prepare_widget` 開頭一處做**（dispatch 之前，所有型別共用），
    三個渲染入口都吃得到，**不要在入口各判一次**——這專案已因「三處各自查」
    在正式 portal 上全數 404 過。resolver 驗 ctx 的 `sub_system_sc` **與
    `org_secure_code`**，所以**每個 `set_render_context('portal', ...)` 呼叫點
    都必須傳 `org_secure_code`**，漏傳的路徑上共用元件會整批消失
  - 解析不到一律 **fail-closed：整個 widget 不渲染**（不是空選單），並記 warning
  - （舊的 `dc_shared_menus` 表與 `/shared-menus` 端點已停用、程式無殘留，
    看到舊名一律視為過時）

- **grid／free 引擎下，widget 只加進 `page.widgets` 不會顯示**，
  必須同時放進某個 `canvas.zones[].widget_ids`（free 是 `frames[]`）。
  `_canvas_widgets` 對未放置者靜默略過（只記 info log），
  症狀是「存了、DB 裡也有、畫面就是沒有」。用 API 直接改 IR 時最容易踩到。

### 用 API 操作 NoCode 子系統

前綴是 `/api/nocode-builder`（不是 `/api/nocode`）。**11 條實測陷阱
（CSRF 未豁免、發布狀態、回應 key、保留欄名、聚合能力缺口等）在
`dev-notes/codex_spec/portal.md` 尾段「以 API 操作子系統時的實測陷阱」**，
動手前整段讀完可省一輪除錯。
可執行範例：`scripts/examples/provision_relief_donation_demo.py`（建置）
與 `verify_relief_donation_demo.py`（端對端驗收）。

### 跑測試一律用 `scripts/run_tests.sh`（2026-08-05 起，強制）

```bash
cd /opt/BeakPlatform-dev
bash scripts/run_tests.sh                                  # 全部
bash scripts/run_tests.sh tests/test_pageir_shared_menu.py -q
bash scripts/run_tests.sh -k menu -q
```

**不要自己 `source .env` 之後直接叫 pytest。**
`TestingConfig` 的資料庫是 `os.getenv('DATABASE_URL', 'sqlite:///:memory:')`，
而 `.env` 的 `DATABASE_URL` 指向**開發庫 `beakplatform_dev`**；
`conftest.py` 與另外三個測試檔的 `app` fixture 收尾都會呼叫 **`db.drop_all()`**。
也就是說照舊寫法跑測試 ＝ 對開發資料庫 create_all + drop_all。
在 2026-08-05 之前一直沒毀掉資料，**只是因為 `drop_all()` 被 FK 相依擋下來而拋例外**
（那批 `ERROR at teardown` 就是它），不是有防護。

`scripts/run_tests.sh` 會在 source .env **之後**把 `DATABASE_URL` 覆寫成
拋棄式的 `beakplatform_test`。另有一道防呆在
`backend/tests/conftest.py::pytest_configure`：庫名不是 `_test` 結尾且非 sqlite
就直接 `pytest.exit`（放在 `pytest_configure` 而不是 app fixture，因為
`test_smoke.py` / `test_page_template_instantiate.py` / `test_page_template_scope.py`
各自定義的 app fixture 會覆蓋 conftest 的版本）。

測試庫不存在時（`beakplatform` 帳號沒有 CREATEDB 權限）：
```bash
sudo -u postgres createdb -O beakplatform beakplatform_test
```
本機 `ethan` 可直接 sudo、不需密碼。連線參數就是上面「資料庫資訊」那組
（`localhost:5432 / beakplatform / postgres123`）；`run_tests.sh` 可用
`TEST_DB_NAME` / `DB_USER` / `DB_PASS` / `DB_HOST` 環境變數覆寫。

**測試庫可以一直重複使用、不必每次重建**——每個 app fixture 都是
`create_all()` 開場、`drop_all()` 收尾。反過來說**不要拿它存任何想留的東西**。

**跑出基準以外的失敗時，歸因順序**（照這個順序查，不要跳）：
1. 先看是不是**測試資料殘留**——`bash scripts/run_tests.sh -q` 重跑一次，
   結果不同就是殘留或測試間互相污染，不是功能回歸
2. 再看 log 有沒有 `Unknown permission code` / `Modules already loaded`
   這類**環境訊息**（前者是測試庫缺 seed，見 PF-34）
3. 都不是才當作功能回歸，用 `git stash` 比對改動前後

**基準不寫死數字**（測試會持續新增，寫死的通過數必然腐爛而誤導）。
判斷有無退步的做法：**動工前先跑一次完整 `tests/` 記下當時的數字**，改完再跑一次比對。
完整跑約 4 分鐘。以下兩個非綠是**長期已知、成因明確**，不列入退步：

| 項目 | 狀態 | 成因 |
|---|---|---|
| `test_auth_interceptor.py::TestAuthDecorators::test_admin_required_for_admin` | failed | 測試庫是 `db.create_all()` 建的空表、**沒有 RBAC seed**（log 印 `Unknown permission code: user:read`），拿到 403 而非 200。要修就補 permission → role → `user_role_assignments` 整條鏈，權威清單在 `scripts/migrations/075_seed_resource_crud_permissions.py`（待辦 **PF-34**） |
| `test_od_protected_targets.py`（2 個 error） | error | **只在完整跑時出現，單獨跑該檔 56 passed** —— 是測試間污染，不是功能回歸。2026-08-20 實測確認（`/opt/tmp/verify/20260820-full-tests.log`）。看到它不要追功能，照上面歸因順序第 1 條處理即可 |
| `test_e2e_portal_cancel.py` | skipped | **永久 skip，重啟服務也救不回來**。它寫死 `PAGE_SC = "FORMTEST00000000000001"`，該驗收頁 2026-08-03 隨全面清除消失，測試在 line 87 就 skip。它另外掛 `pytest.mark.e2e`、服務沒起來也會 skip（line 238），但目前**先卡在找不到頁面**。要恢復必須重建驗收頁並改寫死的常數 |

寫「已知問題不要修」時務必連**成因與判別方式**一起寫，否則它會保護錯的東西——
先前那句「13 個 error 是 SQLite JSONB 問題，不要修」只在無 `DATABASE_URL` 時成立，
卻長期覆蓋掉「撞開發庫殘留」這組完全不同的錯誤，改用測試庫後其中
`tests/test_page_template_instantiate.py` 直接變成 14 passed。

### 瀏覽器互動的 E2E：Playwright（2026-08-12 起）

pytest 之外另有一組 **Playwright E2E**，測的是 curl 與 pytest 都測不到的東西
（連結前綴、按鈕可見性、點擊後有沒有發某支 API、console 有沒有紅字）。

```bash
cd /opt/BeakPlatform-dev
bash scripts/run_e2e.sh                    # 跑全部，輸出自動 tee 到 /opt/tmp/verify/
bash scripts/run_e2e.sh --headed           # 讓人看得到瀏覽器
bash scripts/run_e2e.sh -g "A. 點不可簽核"  # 其餘參數原樣傳給 npx playwright test
```

- 測試在 `tests/e2e/`（**不是** `backend/tests/`，那是 pytest 的領地）
- **需要服務在跑**（走 nginx `http://192.168.0.16:7000/beakplatform`），
  但不需要測試資料庫——它打的是開發庫，且**只讀不寫**
- Playwright 1.62.1 裝在 repo 根（`package.json` + `node_modules/`，均已 gitignore）
- 登入走 `/dev/quick-login`（`tests/e2e/helpers/login.js`），免密碼免 CSRF
- 現有覆蓋：`od-pf79.spec.js`（資安案件處置中心的可簽核／不可簽核兩條路徑、
  OD 四頁副標、intake-keys 的 nginx 前綴）

**寫新 E2E 時的三條硬規則**（AI 派工時要逐條貼進 spec，否則必漏）：

1. **禁止 `page.evaluate(() => el.click())`**，一律 `locator.click()`。
   後者會先跑 actionability checks（visible / stable 連兩幀 box 相同 / enabled /
   receives events 的 hit-test），DOM click 把這層整個拿掉，
   被 overlay 蓋住的按鈕照樣觸發＝測不出使用者點不點得到
2. **禁止 `waitForTimeout` 或任何固定 sleep**，用 web-first assertion 與 `waitForResponse`
3. **禁止寫死 secure_code / 案件編號 / 密碼**，識別碼一律從 API 動態挑；
   資料前提不成立時 `test.skip()` 並印中文說明，不要讓它變紅、也不要靜默 pass

**新測試第一次就全綠時，必須做一次 mutation 驗證**：把被測的修復暫時改回壞掉的樣子，
確認測試會紅。恆真斷言（locator 打錯 → count 恆 0、監聽器沒掛上 → 陣列恆空）
會穩定通過而什麼都沒驗，**讀起來像有保障，比沒測更危險**。
PF-79 這組就是這樣驗的（記錄在 `/opt/tmp/verify/20260812-e2e-od-pf79.log`）。

### AiAgent 節點：`claude -p` 是 agent 不是 API，一定要關掉自訂與工具（2026-08-20）

節點型別 `AiAgent`，handler
`modules/form_workflow/services/node_handlers/ai_agent_handler.py`。
它把流程資料交給本機 `claude -p` 分析，結果寫流程變數並可插一筆
`fw_approval_records`（`action='ai_note'`、`approver_secure_code=NULL`）。

**`claude -p` 不是「送字串到雲端再回傳」，是完整的 agent**
（回應 envelope 有 `num_turns`）。預設狀態下它會用工具、讀
`$HOME/.claude/CLAUDE.md`、繼承呼叫者的**全部 MCP server**
（beak_broodnest / chrome-devtools / Google Drive / SendMessage…）。
prompt 裡放的是攻擊者可控的資料，所以隔離不是選配。

**用原廠的兩個參數就夠，不要自己搭黑名單**：

```
--safe-mode     停用全部自訂（CLAUDE.md、skills、plugins、hooks、MCP servers、
                custom commands/agents…），一個參數全包
--tools ""      停用全部內建工具
```

**`--tools` 與 `--allowedTools` 是兩個不同參數。**
`--allowedTools ""` 會被當成「未指定」而**放行 Bash/Edit/Write**（實測踩過）；
`--tools ""` 才是明確的全部停用。寫錯這個等於完全沒設防，而且從回應看不出來。

2026-08-20 最嚴苛條件實測（真實 HOME、cwd 直接指在專案根目錄）：
`NO_CLAUDEMD` / `NO_MCP` / `NO_TOOLS`，要它建檔案時檔案不會出現。

**驗證一定要看副作用，不能問它「你有什麼工具」。**
實測中它回答「我將建立這個檔案」，但檔案根本沒出現——自我報告不可信。

其餘設計：cwd 用 `tempfile.TemporaryDirectory()` 每次動態建（無需預先建目錄）；
env 最小化只留 `HOME`（認證在 `$HOME/.claude/`）/ `PATH` / `LANG`；
CLI 路徑走 `AI_NODE_CLI_PATH` 環境變數 → `shutil.which('claude')` → `'claude'`。
**沒有任何要手動建立的目錄**，換機器直接可跑。

**AI 一律沒有寫入權**：它只出文字，所有寫入由 handler 做。規則層的
injection 偵測不經過 AI、直接生效，系統警示由 handler 在 AI 輸出**之後**拼接，
AI 移除不掉。改這個檔案前先讀檔頭那段安全設計說明。

**改 handler 後 executor 要重啟才認得**（`beakplatform-dev-executor` 是獨立進程）。

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

### form_workflow 發行（publish）陷阱
- `POST /api/mappings/<sc>/publish` 以表單/流程模板的 **version+revision** 判斷有無變更；
  直接改 `fw_workflow_templates.graph`（SQL 或 PUT API）**不會** bump revision，
  publish 會回「版本未變更」並沿用舊快照
- 解法：改完 graph 先 `UPDATE fw_workflow_templates SET revision = revision+1 WHERE ...` 再 publish
- intake / 表單中心都只讀 `fw_published_form_workflows` 最新 Published 快照，改模板不重發行等於沒改
- 流程變數：流程編號（OD-YYYYMMDD-NNNN）是 `${wi.exec_code}`；`${wi.code}` 是 workflow instance 的 secure_code，
  沒有 `${wi.execution_code}` 這個變數（替換結果為空字串）

### 流程 graph 的引擎行為（2026-08-13 實測，設計流程前必讀）

寫或改 `fw_workflow_templates.graph` 之前先看這張表，都是「存得進 DB、跑起來才炸」的：

| 行為 | 事實 | 後果 |
|---|---|---|
| Branch 命中多條規則 | **展開全部命中的規則**（`branch_handler.py:128-147`），不是 first-match-wins | 規則不互斥就會同時走多條路徑 |
| Branch 條件的 `logic` | 是 **group 切分符**：遇 `OR` 或掃到最後一條就收尾。group 內 AND、group 間 OR | 想寫「A 且 B」要兩條都標 AND |
| Branch 比較失敗 | 欄位缺值／型別不符一律回 False（`branch_handler.py:204-208`） | 可以刻意用來做 fail-safe，讓缺值案件落到 fallback |
| Branch 條件裡的變數前綴 | `_resolve_value()` 的快路徑原本只認 `f. / fi. / v. / form.`，`wi. / n. / t.` 全部落到流程變數查詢而**必定回空字串**（2026-08-13 修，改為委派 `replace_variables`） | 這類錯誤不報錯：條件恆 False、案件全部走 fallback，行為看起來還「正常」。用非 `f./v.` 前綴寫條件時務必做一次 mutation 驗證 |
| Branch 的 fallback `action='log'` | **不回 selected_edges → `advance_to_next_nodes` 取所有出邊**（`node_runner.py:237-243`） | 想「什麼都不做」不能靠 log fallback，會全部走一遍 |
| 無出邊的節點 | 安全終止該分支，不報錯也不結束流程（`workflow_engine.py:360`） | 並行分支要靜靜收尾就指向這種節點，**不要指向 End** |
| End 的 `finish_mode` | `detach`（預設，直接結束）／`cancel`（結束並取消所有未完成節點）／`strict`（等全部完成） | 有並行分支一律用 `cancel`，否則計時分支殘留 |
| 並行分支各自走 End | End 是**流程級**結束，任一分支走到就整個流程 COMPLETED | 另一條的簽核任務會被 executor 視為流程已結束 |
| `AlertBroadcast.broadcast_code` | **不做變數替換**（只有 title/message 有），同 code 覆蓋前一則並清掉已讀記錄 | 它是「最新一則橫幅」不是每案通知，別拿來當逐案稽核 |
| `fw_workflow_templates.timeout_minutes` | 只被寫入 `timeout_at`（`workflow_engine.py:124-139`），**全專案沒有任何地方讀它** | 填了不會有任何效果，逾時要用流程內 Delay 節點 |
| `DecisionWriter.decided_via` 自動推斷 | 看 `last_completed_node_type`，並行分支下不可靠 | 一律在節點 config 明確標 `human` / `auto` |
| `DecisionWriter.target_value` 替換後為空 | 節點回 error、流程卡住 | 自動封鎖前必須先用 Branch 擋掉 `actor_ip` 為空的案件 |

Delay 與 ParallelFork 都可用：executor 會撿 `status=WAITING` 且 `node_type in (Delay, End, ParallelJoin)`
且 `scheduled_at` 到期的節點（`workflow_executor.py:117-133`）。
`ParallelJoin` 另有 `enable_timeout` / `timeout_minutes` / `timeout_edge_id`，
但它要靠 Fork 的另一條分支推進才會開始計時。

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

*最後更新: 2026-08-06（A：清除已失效/自我矛盾條目——失效密碼、e2e skip 成因、
會腐爛的計數與測試基準、與全域 CLAUDE.md 重複的段落；
B：樣板庫→`dev-notes/PAGE_TEMPLATE_SPEC.md`、menu widget→`dev-notes/PAGE_IR_SPEC.md` §3.7、
API 陷阱→`dev-notes/codex_spec/portal.md`、iptables→全域 network_architecture.md，
共用元件段收斂為指針，VERIFY 三條合併；
C：取消工單格式、manifest 由「禁止自行 grep」放寬為「不足時可搜尋但要說明並回補」、
PERM-02 取消事前詢問改為預設套用 D2）*
