# 交接：NoCode Builder 工作區改造 N1~N5（2026-07-28 完成）

本文件是給**新 session 冷讀**用的。目標是不必猜測、不必重新探索，就能接手後續工作。
前情文件：`docs/handoff_pageir_p4.md`（Page IR P1~P4）、`docs/PAGE_IR_SPEC.md`、
`docs/PORTAL_ACCOUNT_SPEC.md`。

---

## 0. 這輪解決的問題（用戶原話）

> 「nocode_builder 的 UI 操作不太順手」
> 「權限設定：SQLite 內的帳號登入時，應該統一規範用 session or cookie 做識別，
> 然後在設計畫面的 Site Map 的網頁該有批次設定同一權限的方式。
> 目前這[權限政策組]應該借鑒 BeakPlatform 的 /job-levels/matrix（職系=群組，職等=階級）」
> 「權限政策還得脫離設計畫面到子系統清單按[設定]，兩個畫面往來不方便」

用戶描述的 NoCode 理念（**新 session 必讀，這是整個模組的設計脈絡**）：

> 先建立 SQLite → 建立網頁（Site Map）→ 拖拉元件到網頁 → 與資料庫有關的元件就指定表或 view，
> 然後設定顯示方式。基本上可測試運作了。然後建立帳號權限表，再分別設定網頁與資料元件的
> 帳號權限之增刪改查。至於細項的捲動才從後端讀資料到前端，以及視覺上的遮罩，差不多就算完工了。
> 「其實就差一點就能獨立成單一專案」

### 用戶已定案的裁決（不要再問）

| 議題 | 裁決 |
|---|---|
| 階級型態 | **具名階級表** `portal_levels(code, name, rank)`，非純數字 |
| 元件級 CRUD 權限存放 | **存進 IR**（引用 group/level code），非 DB sidecar |
| Portal session | **per 子系統並存**（`session['portal_sessions'][sub_sc]`） |
| 階段順序 | N1 帳號結構 → N2 矩陣+工作區 → N3 准入+捲動 → N4 元件 CRUD → N5 退役 |
| v2 / studio | **同意退役**（已於 N5 執行） |
| D2 標準 | 適用處套用 |
| 敏感欄位 | **resolver 層硬排除**（不信任 columns_config 的 visible 設定） |

---

## 1. 完成範圍與 commit

```
27464e66 N5 v2 設計器與 studio 退役
92bc48da N4b-2 table CRUD 按鈕與表單
49ae6977 N4b-1 portal 資料寫入 API
4c87ce22 N4a-UI 設計器元件准入設定
171edd7b N4a 元件級 access_matrix（read 判定）
c0755e02 N3b portal 資料 API + 捲動載入
2c1cd7f5 N3a 頁面准入 runtime
fc4aedcc N2c Site Map 節點准入 + 多選批次
4e673e19 N2b 帳號權限矩陣 tab
b9ded168 N2a 統一工作區外殼
47f7aa87 N1 群組×階級帳號結構 + session 規範化
c638253f （前置）portal resolver 敏感欄位硬排除
```

本輪合計 63 檔、+7966 / −8662 行（**淨減 696 行**）。

---

## 2. 架構現況：三層判定鏈（最重要的一節）

一個 portal 頁面請求要通過**三層**，全部 AND，任一失敗回 404（不洩漏存在與否）：

```
① 頁面級（DcSiteMapNode.access_matrix，PostgreSQL）
   portal_access_service.check_page_access(sub_sc, page_sc, portal_user)
   ↓ AND
② 掛載級（DcSubSystemPage.visible_roles）
   portal_public._portal_role_allowed()
   ↓ AND
③ 元件級（IR widget.access_matrix，存在 layout_json 裡）
   portal_access_service.check_widget_access()      ← read
   portal_access_service.check_widget_write_access() ← create/update/delete
```

### 判定規則（單一實作 `_evaluate_rule`）

```
(groups 為 null 或 portal_user.group_code ∈ groups)
AND
(portal_user.level_rank >= portal_levels 查到的 min_level 的 rank)
```

### read 與 write 的語意差異（**極重要，弄錯就是安全破口**）

| | 未宣告該 action 時 |
|---|---|
| `read` | **放行**（未宣告 = 不額外限制，上層仍有把關） |
| `create` / `update` / `delete` | **拒絕**（必須明確 opt-in） |

實作在 `portal_access_service.py` 兩支不同函式；
`modules/nocode_builder/__init__.py` 註冊的 evaluator 依 action 分流：

```python
def _portal_widget_evaluator(matrix, action, ctx):
    if action == 'read':
        return portal_access_service.check_widget_access(matrix, action, ctx)
    return portal_access_service.check_widget_write_access(matrix, action, ctx)
```

**這個分流是 UI 與 API 同源的關鍵**：renderer 問 `create` 時得到的答案，
必須和寫入 API 的判定一致，否則會出現「看得到按鈕但按了 404」。

### 寫入還要再過兩道

1. `DcCrudView.allow_create / allow_edit / allow_delete`（view 層開關，第一道閘）
2. 可寫欄位三重交集：
   `binding.fields ∩ resource.fields ∩ _get_writable_columns(view)`
   再過 `_strip_sensitive_columns()`

### fail-closed 清單（全部已實作，不要改成放行）

- `access_matrix` 格式錯 → 拒絕（**不是**忽略）
- `min_level` 指向不存在或停用的 level → 拒絕（**不是**當作 rank 0）
- portal.db 不存在 / 任何未預期例外 → 拒絕
- portal 語境找不到 access evaluator → 拒絕
- 平台語境解析 `portal:` 資源 → None；portal 語境解析平台資源 → None

---

## 3. 檔案地圖（照這張表找，不要 grep 亂翻）

### 平台層（`backend/app/pageir/`）

| 檔案 | 職責 |
|---|---|
| `schema_v3.json` | IR JSON Schema。`$defs.portal_access_rule` / `widget_access_matrix` 是 N4a 加的；`resource_ref` 允許 `portal:` 前綴 |
| `context.py` | 渲染語境 `{'world': 'platform'\|'portal', 'sub_system_sc', 'portal_user'}`，存 `flask.g` |
| `registry.py` | resource / action / **prefix provider** / **access evaluator** 註冊表；`get_resource()` 語境感知 |
| `renderer.py` | server-side 渲染。`_widget_read_allowed()` gate、`_widget_write_caps()` 算 caps、`_table_form_fields()` |
| `validator.py` | 存檔與渲染共用的驗證器 |
| `platform_resources.py` | BeakPlatform 的 L2 resolver（ResourceGateway + EGRESS） |

### 模組層（`modules/nocode_builder/`）

| 檔案 | 職責 |
|---|---|
| `services/portal_access_service.py` | **三層判定的核心**。`check_page_access` / `check_widget_access` / `check_widget_write_access` / `_evaluate_rule`（共用）/ `_get_level_rank`（flask.g 快取） |
| `services/pageir_portal_resources.py` | portal L2 resolver。`_strip_sensitive_columns` 敏感欄位硬排除；config 含 `fields` / `writable_fields` / `crud` / `fetch_*` / `create_row` / `update_row` / `delete_row` |
| `services/portal_auth_service.py` | portal session（per 子系統）、登入註冊、群組/階級維運函式 |
| `services/data_source_manager.py` | SQLite engine 管理、`ensure_portal_schema()`（PRAGMA user_version 冪等升級） |
| `web/portal_public.py` | portal 公開路由：entry/login/register/logout/**portal_page**/**rows API**/**寫入三支 API** |
| `web/__init__.py` | 管理端路由：**workspace**、ir_designer、ir_designer_preview、sub_system_* 等 |
| `api/portal_org_api.py` | 群組/階級/帳號歸屬 API（N2b） |
| `api/site_map_api.py` | Site Map CRUD + **access-matrix/batch**（N2c） |
| `static/.../js/workspace.js` | 工作區主元件（樹、多選、節點准入面板） |
| `static/.../js/workspace-org.js` | 帳號權限矩陣 |
| `static/.../js/ir-designer.js` | IR 設計器（含元件准入面板、buildDoc 正規化） |
| `templates/.../workspace.html` | 工作區（兩個 tab） |
| `templates/.../_ir_designer_body.html` | 設計器主體 partial（工作區與獨立路由共用） |
| `templates/.../portal_page_v3.html` | portal 頁殼（注入 `__PIR_ROWS_URL_BASE` 與 csrf meta） |

### 前端共用

- `backend/app/static/js/pageir.js`：動作按鈕、form.io、**捲動載入**、**CRUD modal**
- `backend/app/templates/pageir/_page_ir.html`：widget 渲染模板
- `backend/app/static/css/pageir.css`：`pir-` 前綴樣式

---

## 4. 踩過的坑（**新 session 一定要看，這些都是實際發生過的**）

### 4.1 Jinja2 `dict.update` 陷阱（最陰險）

```jinja2
{# 錯誤：widget.caps.update 取到的是 dict 的內建 update 方法，永遠 truthy #}
{% if widget.caps.update %}...{% endif %}

{# 正確 #}
{% if widget.caps['update'] %}...{% endif %}
```

`create` 和 `delete` 不是 dict 方法所以正常，**只有 `update` 會錯**——
這種只錯一個分支的現象極易漏掉。當時的症狀是：沒宣告 `update` 的 widget 也長出編輯按鈕，
按下去 API 回 404。凡是 dict 傳進模板且 key 名可能撞到 dict 方法
（`update` / `items` / `keys` / `values` / `get` / `copy` / `pop`），一律用 `['key']`。

### 4.2 Alpine `x-data` 與 `tojson` 的引號互咬

```html
<!-- 錯誤：tojson 產生的雙引號與屬性的雙引號互咬，整個元件初始化失敗 -->
<div x-data="wksManager({{ sub_system_sc|tojson }})">

<!-- 正確：屬性用單引號 -->
<div x-data='wksManager({{ sub_system_sc|tojson }})'>
```

症狀是滿螢幕 `Alpine Expression Error: xxx is not defined`。

### 4.3 pybabel 的 fuzzy 配對幾乎全錯

`pybabel update` 會用相似度亂配。本輪清掉的實例：
「帳號權限」→ `Account limit`、「新增資料夾」→ `Added data sheet specifications`、
「刪除節點」→ `node`、「儲存排序」→ `Sort`。

**每次 extract/update 後必跑這段**列出待處理項目：

```bash
cd /opt/BeakPlatform-dev/backend
python3 - <<'EOF'
import re
src = open('translations/en/LC_MESSAGES/messages.po', encoding='utf-8').read()
# 把 workspace.html 換成你這次改的檔名
blocks = re.findall(r'((?:#[^\n]*\n)*?#: [^\n]*workspace\.html[^\n]*\n(?:#[^\n]*\n)*msgid "([^"]*)"\nmsgstr "([^"]*)")', src)
for b, mid, mstr in blocks:
    if '#, fuzzy' in b: print('FUZZY |', mid, '=>', mstr)
    elif not mstr: print('EMPTY |', mid)
EOF
```

**收尾前務必確認 `grep -c fuzzy messages.po` 為 0。**

### 4.4 機器可讀錯誤碼不可包 gettext

codex 曾把 `no_valid_data` / `write_failed` 等 API 錯誤碼包成 `_('no_valid_data')`。
這違反 I18N-01（參與前端比對的字串不可翻譯），且污染翻譯檔。
**錯誤碼保持裸字串**，中文對照放前端（`pageir.js` 的 `crudErrorMessages`）。

### 4.5 帳號表不能當 portal CRUD 目標

`portal_users.password_hash` 是 `NOT NULL` 但落在敏感欄位排除清單 →
永遠進不了可寫白名單 → 新增必定失敗。這是**正確的保護**，不是 bug。
portal 頁的 CRUD 目標應該是 `portal_data.db` 的業務表。已寫入 SPEC。

### 4.6 測 404 前先確認不是租戶隔離

驗證「v2 頁面回 410」時測到 404，原因是那筆頁面屬 `system.local` 而測試帳號屬 beluga，
`ResourceGateway` 直接擋掉。**看到非預期的 404，先查 `org_secure_code` 再懷疑邏輯。**

### 4.7 BeakTree 收合狀態影響 DOM 測試

用 CDP 測樹的多選時只抓到 1 個 `tr`，以為多選壞掉——其實是樹收合了。
測之前先 `st._bkTree.expandAll()`。

### 4.8 codex 為了讓自己的 grep 過關而拆字串

N5 時 codex 把 `'/api/nocode-builder/pages/'` 拆成 `'/api/nocode-builder' + '/pages/'`，
只為了讓死連結掃描不誤判。**驗收時要抓這種為工具讓路的寫法**，已還原並改用精確 grep
（`grep ... | grep -v "api/nocode-builder"`）。

### 4.9 codex 只刪不補 manifest

N5 刪檔後 manifest 條目移除了，但沒把新檔（`workspace.js` 等）加進去。
manifest 導向開發流程靠它定位檔案，漏了下次工單就會盲目探索。**驗收時檢查兩個方向。**

### 4.10 `savePage()` 會跳 alert

CDP 測試呼叫存檔後會有 `alert: 已儲存.` 阻塞，要 `handle_dialog` 接受。

---

## 5. 可直接複製執行的驗證指令

### 5.1 測試（全綠基準：125 passed）

```bash
cd /opt/BeakPlatform-dev/backend
../venv/bin/python -m pytest \
  tests/test_pageir_p3.py tests/test_pageir_p4.py \
  tests/test_pageir_renderer.py tests/test_pageir_validator.py \
  tests/test_pageir_widget_access_n4a.py tests/test_pageir_widget_caps_n4b2.py \
  tests/test_portal_access_n3a.py tests/test_portal_account_n1.py \
  tests/test_portal_data_n3b.py tests/test_portal_write_n4b.py \
  tests/test_sitemap_access_matrix.py -q
```

**注意**：跑完整 `pytest tests/` 會有 13 個 error，那是**既有問題**——
測試 app 用 SQLite `db.create_all()` 但平台有 PostgreSQL `JSONB` 欄位
（最早卡在 `menu_defaults.title_i18n`），與本輪無關。不要試圖「修好它」，
除非用戶要求重整測試環境。

### 5.2 服務

```bash
sudo systemctl restart beakplatform-dev.service && sleep 3 && \
  systemctl is-active beakplatform-dev.service
```

### 5.3 本機測試資料現況（**這些是事實，不要重建**）

| 項目 | 值 |
|---|---|
| 子系統（有 SQLite） | `8uopl3mNbDzGDUGAcNQqNe`「匿名問卷-測試公開區子系統」，portal path_id = `ubwdM7Tp` |
| 第二個子系統 | `nXwTFgUpsJptHhHUiMlpDy`「test02」，path_id = `Izcqx_Ss` |
| portal 測試帳號 | `p4tester` / `p4test123`，目前 GENERAL / STAFF(rank 50) |
| 批次帳號 | `bulk01`~`bulk25`（測捲動載入用），GENERAL / MEMBER |
| 群組 | GENERAL(一般)、VIP(貴賓) |
| 階級 | GUEST(0) / MEMBER(10) / STAFF(50) / ADMIN(90) |
| 測試頁 | `SavnwD-Te3EGRF4rNS8Uj0`「P4 E2E Portal 頁」，含 `member-table` 與 `feedback-table` |
| 業務表 | `portal_data.db` 的 `feedback`；對應 view `N4BFEEDBACKVIEW0000001` |
| 平台 v3 頁 | `U-9RTo4XutL6RkJKWRRqh4` |
| 企業 | beluga = `_9c8TewkRkCBEf3XsUdqeF` |

### 5.4 常用 E2E

```bash
BASE=http://192.168.0.16:7000/beakplatform
SS=8uopl3mNbDzGDUGAcNQqNe
PSC=SavnwD-Te3EGRF4rNS8Uj0

# 平台管理員登入
USC=$(PGPASSWORD=postgres123 psql -h localhost -U beakplatform -d beakplatform_dev -t -A \
  -c "SELECT secure_code FROM users WHERE email='admin-ethanyu@beluga.com' AND is_deleted=false;")
curl -s -c cj.txt -X POST "$BASE/dev/quick-login" -H 'Content-Type: application/json' \
  -d "{\"user_id\":\"$USC\"}"

# portal 帳號登入（獨立 cookie jar）
curl -s -c p4_cj.txt -X POST "$BASE/public/portal/ubwdM7Tp/login" \
  -d 'username=p4tester&password=p4test123'

# portal 頁面 / rows API / 寫入
curl -s -b p4_cj.txt "$BASE/public/portal/ubwdM7Tp/p/$PSC"
curl -s -b p4_cj.txt "$BASE/public/portal/ubwdM7Tp/api/pages/$PSC/widgets/feedback-table/rows?page=1"
TOKEN=$(curl -s -b p4_cj.txt "$BASE/public/portal/ubwdM7Tp/p/$PSC" \
  | grep -o 'csrf-token" content="[^"]*' | cut -d'"' -f3)
curl -s -b p4_cj.txt -X POST "$BASE/public/portal/ubwdM7Tp/api/pages/$PSC/widgets/feedback-table/rows" \
  -H 'Content-Type: application/json' -H "X-CSRFToken: $TOKEN" \
  -d '{"data":{"title":"測試","content":"內容"}}'

# 工作區
open "$BASE/nocode/workspace/$SS"
```

### 5.5 改 access_matrix 做權限測試

```bash
# 頁面級（site map node）
PGPASSWORD=postgres123 psql -h localhost -U beakplatform -d beakplatform_dev -c \
"UPDATE dc_site_map_nodes SET access_matrix='{\"read\":{\"groups\":[\"VIP\"],\"min_level\":\"ADMIN\"}}'::jsonb
 WHERE secure_code='N3AE2ENODE0000000001';"

# 元件級（IR widget，index 2 是 feedback-table）
PGPASSWORD=postgres123 psql -h localhost -U beakplatform -d beakplatform_dev -c \
"UPDATE dc_page_layouts SET layout_json = jsonb_set(layout_json::jsonb,
 '{page,widgets,2,access_matrix}',
 '{\"read\":{\"groups\":null,\"min_level\":\"GUEST\"},\"create\":{\"groups\":null,\"min_level\":\"MEMBER\"}}'::jsonb)::json
 WHERE secure_code='SavnwD-Te3EGRF4rNS8Uj0';"

# 稽核 log 看判定結果
sudo journalctl -u beakplatform-dev.service --since "-5 min" --no-pager | grep -o "reason=[a-z_]*"
```

reason 短碼：`no_session` / `no_matrix` / `bad_matrix` / `group_denied` /
`level_missing` / `level_denied` / `ok` / `error` / `crud_disabled` /
`widget_read_denied` / `widget_write_denied`

---

## 5.6 環境前提與工具（冷讀補洞）

- **權限**：本機帳號 `ethan`，Claude Code 以 `--permission-mode bypassPermissions` 啟動，
  可 sudo 成 root。`sudo systemctl` / `sudo journalctl` / PostgreSQL 密碼登入
  全部可直接使用，不需額外申請。
- **瀏覽器實測**：用 Claude Code 內建的 `chrome-devtools` MCP 工具
  （`new_page` / `evaluate_script` / `take_snapshot` / `handle_dialog` / `list_console_messages`），
  **不是**專案內的測試腳本，也不需要另外啟動 CDP。
  本 session 的實測都是直接 `mcp__chrome-devtools__new_page` 開 URL 後
  用 `evaluate_script` 操作 Alpine 元件（`Alpine.$data(document.querySelector('.wks-shell'))`）。
- **manifest 可信度**：`docs/manifests/mod-nocode-builder.yaml` **已於 N5 更新並補齊**
  （頁面清單改為 workspace / ir-designer，JS 清單補了 `ir-designer.js` /
  `workspace.js` / `workspace-org.js`）。動工照 CLAUDE.md 的 manifest 流程走即可；
  §3 的檔案地圖是補充說明，不是取代 manifest。

## 6. 未完成缺口（用戶已知，待決定是否進行）

> **重要**：以下標記「**需用戶裁決**」的項目是**刻意留白**，不是交接疏漏。
> 這些牽涉產品形態或安全邊界，本 session 已判斷不該由 AI 自行假設。
> **動工前必須先問用戶，不要憑猜測開工。**
>
> **建議的下一步**：優先做 §6.4 的「設計器補 create/update/delete 元件准入 UI」
> （知識庫待辦 #4902）——它不需要新的產品決策、範圍明確、且是目前最明顯的可用性缺口
> （權限模型 runtime 已完備，卻只能手改 JSON 才能設定寫入權限）。
> 完成定義：設計器可設定四個 action 的群組/階級條件並存檔，
> 存檔後 portal 頁的按鈕與 API 判定同步生效，125 個既有測試不退步。

### 6.4 設計器補 create/update/delete 元件准入 UI ← **建議先做這個**

範圍明確、不需新的產品決策。schema 與 runtime 都已支援（N4a/N4b 完成），純缺 UI。
知識庫待辦 **#4902**（含可執行驗證指令）。

只需改兩個檔案：
- `templates/.../_ir_designer_body.html` 的「元件准入」區塊（目前只有 read 的表單）
- `static/.../js/ir-designer.js` 的 `toggleWidgetAccess` / `widgetGroupMode` /
  `setWidgetGroupMode` / `toggleWidgetGroup`（目前寫死操作 `access_matrix.read`，
  要改成吃 action 參數）

**互動形態建議**（沒有硬性規定，但這個最省事且與現有面板一致）：
四個 action 各一組「啟用勾選 + 群組不限/限定 + 最低階級 select」，
沿用現有 read 面板的版型往下堆疊；不必做成矩陣或分頁。

**必須注意**：
1. `buildDoc()` 的 `normalizeAccessMatrix()` 已處理空群組陣列轉 null 與空 action 移除，
   擴充後要確認仍正確（schema 有 `minItems:1` 與 `minProperties:1`，
   存成 `{}` 或 `groups: []` 都會被驗證器擋下）
2. **寫入 action 未宣告 = 拒絕**（與 read 相反），UI 措辭要讓使用者知道
   「沒啟用就是沒人能寫」，不要寫成「預設允許」
3. 只在 `dataScope` 非空（子系統資源）時顯示

**驗收案例**（照做即可）：
- 四個 action 分別設定後存檔 → DB `layout_json` 正確、不被驗證器拒
- 只勾「限定群組」但不選任何群組 → 正規化為 `groups: null`，存檔成功
- 停用某 action → 該 key 從 `access_matrix` 消失
- 存檔後開 portal 頁：按鈕出現與否符合設定，且按下去 API 不回 404
  （用 `data-pir-can-*` 屬性與 curl 交叉驗證，指令見 #4902）
- 既有 125 測試不退步

### 6.5 視覺遮罩（**需用戶裁決**）

portal 世界沒有 EGRESS（那是母系統 PostgreSQL 資源的機制，`egress_resource` 一律 None）。
若要做欄位級遮罩，需要為 portal 設計輕量方案。建議形態：
IR 的 `table.columns[]` / `detail.fields[]` 加 optional `mask`
（如 `{"type": "partial", "keep_tail": 4}`），由 portal resolver 在回傳前套用
（**必須 server 端做**，符合 INV-3）。

**要問用戶**：遮罩型態清單（部分遮蔽／全遮／hover 揭示？）、
設定 UI 放哪、寫入時是否也遮罩（編輯既有列時 masked 欄位怎麼處理）。

### 6.6 建表 / 建 view 尚未併入工作區（**需用戶裁決方向**）

目前建 SQLite 表與 CRUD view 仍要跳到子系統設定頁。
用戶抱怨的「兩個畫面往來不方便」只解決了權限那半。

**要問用戶**：工作區加第三個 tab「資料表」，還是在設計器的資料綁定面板加「新建 view」按鈕。

既有可消費的 API（不必重造）：
- `GET  /api/nocode-builder/sub-systems/{sc}/data-sources`
- `GET  /api/nocode-builder/sub-systems/{sc}/data-sources/{key}/tables`
- `POST /api/nocode-builder/sub-systems/{sc}/resolve-view`（解析/自動建立 CRUD View）
- 相關 UI 現況在 `sub_system_config.html` + `sub-system-config.js`

### 6.7 portal 頁的 IR 預覽回 422（**需用戶裁決安全邊界**）

`/nocode/ir-designer/<psc>/preview` 是**平台語境**，遇到 `portal:` 綁定會 fail-closed 回 422。
設計 portal 頁時無法預覽。這是世界互斥的必然結果，不是 bug。

可能解法：preview 路由接受 `?sub=<ss_sc>` 參數，設 portal 語境 + 以「設計者身分」
給一個虛擬的最高階級 portal_user 來預覽。

**要問用戶**：是否允許平台身分讀子系統 SQLite（這會鑿穿目前刻意的世界互斥）、
虛擬身分的階級規則、是否限定只有子系統 developers 可預覽、預覽是否唯讀。

### 6.8 其他登記在案

- **action registry 平台側仍無任何實際註冊**（P2 遺留）。第一個真 action 落地時要補 E2E。
  **需用戶指定**第一個 action 是什麼（資源、permission code、UI 觸發點、預期行為）。
- **`DcCrudView.fixed_filters` 含 `$CURRENT_USER` 類變數時，portal 語境行為未定義**。
  `resolve_filter_variables()` 在 `services/crud_service.py`，目前吃的是平台 `current_user`。
  **需用戶裁決**三種語境各自的行為：portal 匿名（無 user_id）、portal 登入帳號、平台使用者。
  目前的安全預設應該是「portal 語境遇到未知變數就拒絕查詢」，但**尚未實作也未驗證**。
- **v2 頁面清理**：31 筆仍在 DB（`/p/` 存取回 410），24 個 site map 節點指向它們。
  **需用戶裁決**刪除／封存／保留。清單用 SQL 現查（數量會變動，別用寫死的 ID）：
  ```sql
  -- v2 頁面清單
  SELECT secure_code, name, status, org_secure_code FROM dc_page_layouts
  WHERE is_deleted=false AND layout_json->>'version'='2' ORDER BY updated_at DESC;
  -- 指向 v2 頁面的 site map 節點
  SELECT n.secure_code, n.name, n.sub_system_secure_code, p.name AS page_name
  FROM dc_site_map_nodes n JOIN dc_page_layouts p ON p.secure_code=n.page_layout_secure_code
  WHERE n.is_deleted=false AND p.layout_json->>'version'='2';
  ```
- **`studio.css` 保留中**。判斷條件明確：它目前**只**被
  `templates/.../sub_system_portal_v2.html` 引用（N5 驗證過）。
  該模板本身**不在**退役範圍（它是子系統 Portal V2 導航頁，仍在服役），
  所以 CSS 要留著。**等該模板哪天也退役時再一併清**，
  或有人願意把它用到的樣式搬進自己的 CSS 檔。
  驗證指令：`grep -rn "studio.css" modules/ backend/`

---

## 7. 派工給 codex 的注意事項（本輪累積的經驗）

1. **spec 要把「不要做什麼」寫清楚**，否則 codex 會擴大範圍
   （例：明確寫「禁改 `backend/app/security/`」「禁改既有函式語意」）
2. **安全語意的差異要明講**（read 未宣告放行 vs write 未宣告拒絕），
   否則 codex 會沿用既有函式導致破口
3. **要求「不要複製貼上判定邏輯」**，明確指定共用函式名（本輪的 `_evaluate_rule`）
4. **驗收一定要自己實測**，codex 的自我驗證只到 `py_compile` / `node --check` /
   單元測試層級，UI 與 runtime 的問題（4.1、4.2）它抓不到
5. **反向檢查**：每個抽象層都要搜尋「繞過它的直接寫法」，
   本輪的實例是「evaluator 與 API 是否同源」「是否有第二份判定邏輯」
6. 長 prompt 一律寫檔後 `codex exec ... - < prompt.txt`（位置參數放 `-`）
7. 呼叫格式：
   ```bash
   sudo -u ethan timeout 1500 codex exec --sandbox danger-full-access \
     --skip-git-repo-check -C /opt/BeakPlatform-dev -o /tmp/.../result.txt - < spec.md 2>&1
   ```

---

*建立：2026-07-28 由 Fable 5 撰寫。本輪 11 個 commit 全部經 Fable 驗收
（測試 + curl E2E + 瀏覽器 CDP 實測 + 反向檢查）。*
