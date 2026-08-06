# 共用元件庫規格（Shared Components）

> 2026-08-06 定版。取代 PF-29 的「共用選單」設計與其合併優先序。
> 對應待辦：PF-47。

## 1. 目的與語意裁決

**共用元件 = 子系統層級的元件實體，各頁引用它，改一次全部生效。**

使用者心智模型：「我設計了一個 menu-1，只限此專案用，拖到任何網頁功能都一模一樣。」

### 1.1 完全共用（推翻 PF-29 的合併優先序）

| | PF-29 舊規則 | 本規格 |
|---|---|---|
| `items` | 取共用元件的 | 取共用元件的 |
| 外觀（orientation / item_gap / hover_expand / nav_source / nav_key / style） | **頁面 widget 有寫用頁面的** | **一律取共用元件的** |
| 頁面端能不能覆寫 | 能 | **不能** |

同一份選單要在 A 頁橫式、B 頁縱式 → **建兩個共用元件**（menu-1 橫、menu-2 直），
不靠頁面覆寫。這是使用者裁決（2026-08-06）：「另外儲存成 menu-2(直) 就解決了」。

### 1.2 名稱唯一

`unique(sub_system_secure_code, name)`。使用者在 UI 上看到的是**共用元件的 name**，
widget `id` 降為頁面內部識別。這解掉「UI 上同名稱看起來就該是同一個東西」的困擾。

### 1.3 access_matrix 是唯一的例外：不套用「完全共用」，改為交集

`access_matrix` 是授權邊界，不是外觀。
**共用元件的 access_matrix 與頁面 widget 的 access_matrix 兩者都要通過**
（AND，任一不過就不渲染）。

理由：同一個元件在不同頁面可能需要不同准入；且系統一貫 fail-closed，
「取其一」的任何方向都會讓某一邊的設定靜默失效。

## 2. 資料模型

新表 `dc_shared_components`（`modules/nocode_builder/models/shared_component.py`）：

| 欄位 | 型別 | 說明 |
|---|---|---|
| `sub_system_secure_code` | String(32) NOT NULL index | 歸屬子系統 |
| `name` | String(200) NOT NULL | 顯示名稱，同子系統內唯一 |
| `widget_type` | String(32) NOT NULL | 八種：`menu` / `table` / `detail` / `master_detail` / `form` / `actions` / `text` / `layout` |
| `widget_json` | JSONB NOT NULL | **完整 widget 組態，不含 `id`**（含 `type`） |
| `is_active` | Boolean NOT NULL default true | |

繼承 `ModuleBaseModel`（secure_code / org_secure_code / is_deleted / timestamps）。

### 2.1 舊表處理

`dc_shared_menus` 的資料一次性遷移到新表（`widget_type='menu'`，
`widget_json = {"type":"menu","items":<items>, **<config>}`），
遷移後程式**不再讀寫舊表**，舊表保留為備份、不刪。

遷移腳本：`scripts/migrations/<序號>_shared_menus_to_components.py`，冪等
（以 `secure_code` 判斷是否已遷移）。

## 3. IR schema（`backend/app/pageir/schema_v3.json`）

每個 widget 型別加：

```jsonc
"shared_ref": { "type": "string", "pattern": "^[A-Za-z0-9_-]{1,32}$" }
```

`required` 改寫為 `["id", "type"]` + `anyOf`：

```jsonc
"anyOf": [
  { "required": ["<該型別原本的必填欄位>"] },
  { "required": ["shared_ref"] }
]
```

有 `shared_ref` 時頁面端其他欄位**允許存在但渲染時忽略**
（設計器「解除引用」要能還原成本地副本，故不強制刪除）。

## 4. Renderer：展開點統一提前

現況：展開只在 `_prepare_menu`（`backend/app/pageir/renderer.py:302`）。
改為在 `prepare_widget` 的 dispatch **之前**統一處理：

```python
shared_ref = widget.get("shared_ref")
if shared_ref:
    resolved = resolve_shared_component(shared_ref, ctx)   # registry
    if resolved is None:
        logger.warning(...)
        return None            # fail-closed：整個 widget 不渲染
    widget = {**resolved, "id": widget["id"]}
    # access_matrix 交集：兩份都保留，_widget_read_allowed 兩份都要過
```

- `_prepare_menu` 內原有的 shared_ref 合併邏輯**整段移除**
- 回 `None` 的 widget 由上層略過（layout children、canvas widget_ids 都要能容忍）
- fail-closed 觸發條件：元件不存在／已軟刪／`is_active=false`／不屬於本子系統

### 4.1 registry 泛化

`backend/app/pageir/registry.py`：

```python
register_shared_component_resolver(world, fn)   # 取代 register_shared_menu_resolver
get_shared_component_resolver(world)
```

resolver 簽名 `fn(shared_ref: str, ctx: dict) -> dict | None`，
回傳完整 widget 組態（不含 id）。**platform world 不註冊是預期狀態。**

portal 實作移到
`modules/nocode_builder/services/pageir_shared_component.py`
（沿用現行 `_resolve_shared_menu` 的租戶／子系統歸屬檢查）。

## 5. menu 自動模式

共用元件（`widget_type='menu'`）的 `widget_json` 加欄位：

```jsonc
{ "source_mode": "manual" | "auto",     // 預設 manual
  "include_system_links": false }        // auto 模式專用，預設 false
```

`auto` 時**忽略 `items`**，依 site map 即時生成：

- 從該子系統的根節點起遞迴，取 `is_deleted=false AND is_active=true`，依 `display_order`
- `folder` 節點 → 無連結的群組項（label + children）
- `page` 節點 → **`_build_auto_items` 自己不做任何權限判斷**，
  照樣產出項目；`check_page_access` 由下游的 `_build_item_entry` 執行
  （不通過且無可見 children 時整枝消失）。
  **兩處都判會讓規則有機會分岔，所以只在一處判**
- 深度上限 5（與手動模式一致）
- `include_system_links=true` 時，在最後附上 login / register / logout
  （沿用現行白名單與顯示規則：login/register 僅未登入時、register 另需
  `allow_registration`、logout 僅已登入時）

實作：`pageir_portal_menu.py` 新增 `_build_auto_items(sub_system_sc)` 產出
與手動模式**同形狀**的 items 樹，之後完全複用既有 `_build_item_entry`
（權限過濾、預覽語境連結、nav 聯動全部沿用，不另寫一套）。

## 6. API

前綴 `/api/nocode-builder/sub-systems/<ss>/shared-components`，
全部 `@permission_required('nocode_builder.manage')`（D2）。

| 方法 | 路徑 | 說明 |
|---|---|---|
| GET | `/shared-components?widget_type=menu` | 列出（`widget_type` 選填） |
| POST | `/shared-components` | 建立；`name` 重複回 409 |
| PUT | `/shared-components/<sc>` | 更新 `name` / `widget_json` / `is_active` |
| DELETE | `/shared-components/<sc>` | 被引用時 409 並回 `usages`（掃**所有** widget 型別） |

`widget_json` 驗證：包成單 widget 的假頁面過 `validate_page_ir`
（實作在 `shared_component_api._validate_widget_json`，補一個假 `id` 再驗）。

**POST 的 `widget_type` 由後端從 `widget_json.type` 推導，呼叫端不必也不應傳。**
`widget_json` 內**不可含 `id`**（含了回 400）。

寫入前會過 `_normalize_widget_json()`：menu 的 `style.background_file` 若是空字串
（UI 上的「不使用底圖」）就移除該鍵，否則 schema pattern 會擋成 400。
頁面存檔路徑另有一份同語意的 `ir-designer.js::normalizeMenuOnSave`，
**兩條路都要有**。

**舊 `/shared-menus` 端點與前端呼叫一併移除**，不留 alias
（舊的前端全域 `window.BkSharedMenu` 已改名 `window.BkSharedComponent`，
檔案 `shared-menu.js` 也在批次 3 更名為 `shared-component.js`）。

## 7. 樣板淨化（`page_template_service.sanitize_template_ir`）

跨子系統套用樣板時清掉所有 widget 的 `shared_ref`（現行只處理 menu）：

- `menu` → 清 `shared_ref` 並補 `items: []`（缺 items 會過不了 schema）
- 其他型別 → 清掉後缺必填欄位 → **整個 widget 移除**，
  並同步清 canvas `widget_ids` / layout `children` / `row_link_ref`（沿用既有處理）

report 碼改為 `shared_component_refs`（取代 `shared_menu_refs`），
中文對照在前端 `page-template.js` 的 `describeReport()`，**後端不翻譯**。

同子系統套用**維持完全不淨化**（`shared_ref` 原樣保留）。

## 8. 設計器

### 8.1 共用元件區塊（macro，各型別複用）

新增 `_ir_designer_shared_component.html`，提供 `render()` 與 `editor_bar()` macro：

- 未引用：`引用共用元件` 下拉（依 `widget.type` 過濾）＋ `[另存為共用元件]`
- 引用中：顯示共用元件名稱 ＋ `[編輯共用元件]` / `[解除引用]`
- 全部按鈕包 `{% if can('nocode_builder.manage') %}`（D2）

在 `master_detail` 以外的 widget 型別屬性面板頂部呼叫此 macro。

### 8.2 引用中的欄位處理

引用中時該 widget 的**所有設定欄位隱藏**（不是唯讀灰化），
只留共用元件名稱、四個動作與唯讀摘要。
理由：完全共用之後頁面端改了也不生效，留著可編輯的欄位比隱藏更誤導。

引用中的 widget 在頁面 IR 只保留 `id` / `type` / `shared_ref` / `access_matrix`
（有設定時），其餘型別設定鍵一律剝除，避免留下不會生效的死資料。

`access_matrix` 區塊**例外，維持可編輯**（§1.3 的交集語意）。

### 8.3 編輯共用元件：就地切換屬性面板

編輯共用元件時不再開獨立 modal，而是讓右側屬性面板改為編輯
`sharedComponentEditor.draft`，並在面板頂部顯示 `editor_bar()`：

- `[儲存共用元件]` 直接 PUT 共用元件，與頁面 `[儲存]` 無關
- `[取消]` 若有未儲存變更需二次確認
- 編輯期間不允許切換選取的頁面 widget

理由：table / detail / form / actions / text / layout 都已有完整屬性面板。
就地切換可避免複製約 400 行屬性面板，也不用改寫二十餘個既有欄位處理函式。

### 8.4 兩個宿主都要改

`_ir_designer_body.html` 有兩個宿主頁（`ir_designer.html` 與 `workspace.html`），
`{% block scripts %}` **各寫各的**。新增 JS 檔時兩邊都要加，
日常用的是工作區那邊。

### 8.5 現行 menu 實作已定的語意（泛化時照抄，不要重新發明）

批次 1、2 只做了 menu 的 UI，以下行為是既成事實，泛化時沿用：

| 動作 | 現行行為（`ir-designer.js`） |
|---|---|
| 另存為共用元件 | `window.prompt` 取名 → POST 建立 → 自動把當前 widget 設成 `shared_ref` 並剝除本地設定 → `markDirty()`（要按頁面 [儲存] 才寫進頁面） |
| 解除引用 | 把共用元件當下的 `widget_json` 複製回本地 widget，刪掉 `shared_ref`，`markDirty()` |
| 編輯共用元件 | 就地切換屬性面板，按 `[儲存共用元件]` 直接 PUT，**與頁面 [儲存] 完全無關**；存檔成功自動關閉 |
| 引用中隱藏 | `master_detail` 以外的型別設定欄位全部隱藏；`access_matrix` 例外，仍由頁面端編輯 |

UI 文案統一使用「共用元件」，並同步 i18n。

### 8.6 泛化裁決

- `layout` 開放共用；引用時頁面 widget 的 `children` 會被剝除，flow 樹的
  `加入到此 layout` 按鈕停用。
- 跨 widget 引用（`table.row_actions_ref` / `table.row_link_ref`）在建立或更新
  共用元件時一律剝除，後端 `dangling_ref` 驗證是最後防線。
- 解除引用時 `access_matrix` 以頁面端那份為準；頁面端沒有才取共用元件的。
- `master_detail` 本批不做設計器 UI，後端能力保留給後續批次。

## 9. 驗收

- 反向檢查先於功能測試：搜尋是否有繞過 `resolve_shared_component` 的直接寫法、
  是否有殘留讀 `dc_shared_menus` 的路徑
- 瀏覽器實測（VERIFY-01/03，主 Claude 執行，不可外包）：
  引用／解除引用／編輯共用元件／自動模式開關／跨頁生效
- 留證 `/opt/tmp/verify/<日期>-shared-components.log`（VERIFY-02）
- 迴歸基準：`bash scripts/run_tests.sh` → **`395 passed, 1 failed, 2 skipped`**
  （2026-08-06 批次 2 完成後實測）。
  那 1 failed 是 `tests/security/test_auth_interceptor.py::TestAuthDecorators::test_admin_required_for_admin`
  ——測試庫是空表、缺 RBAC seed（log 會印 `Unknown permission code: user:read`），
  2 skipped 是 `test_e2e_portal_cancel.py`（需實跑服務且依賴的驗收頁已刪）
  與 `test_portal_file_stage_a.py`（test app 未註冊 nocode_builder blueprint）。
  **這三個都不要去修。**

### 9.1 動手前的定位資訊

- manifest：`docs/manifests/mod-nocode-builder.yaml`（本次已加入新檔）
- 測試帳號與 curl 指令、可用子系統／頁面 secure_code、預覽網址：
  見 BBN 待辦 **PF-53**（`note_get(5068)`），內含本 session 實際跑通的指令
- 設計器屬性面板全在 `_ir_designer_props.html`（42KB），
  menu 的共用元件 UI 在 `_ir_designer_menu.html`

## 10. 本規格**不**包含（留在 PF-47）

- 「頁面 × 共用元件」批次矩陣 UI
- 子系統預設選單（新頁自動引用）

有了共用元件庫＋自動模式後，這兩項的必要性下降：新頁靠樣板帶 `shared_ref`，
選單內容由自動模式免設定。
