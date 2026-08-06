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
| `widget_type` | String(32) NOT NULL | `menu` / `table` / `detail` / `form` / `actions` / `text` / `layout` |
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
- `page` 節點 → 過 `check_page_access`；不通過且無可見 children 時整枝消失（沿用現行行為）
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
（沿用現行 `shared_menu_api._validate_items` 的手法，改成整個 widget）。

**舊 `/shared-menus` 端點與前端呼叫一併移除**，不留 alias。

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

新增 `_ir_designer_shared_component.html`，提供 `render(widget_expr)` macro：

- 未引用：`引用共用元件` 下拉（依 `widget.type` 過濾）＋ `[另存為共用元件]`
- 引用中：顯示共用元件名稱 ＋ `[編輯共用元件]` / `[解除引用]`
- 全部按鈕包 `{% if can('nocode_builder.manage') %}`（D2）

在**每個** widget 型別的屬性面板頂部呼叫此 macro。

### 8.2 引用中的欄位處理

引用中時該 widget 的**所有設定欄位隱藏**（不是唯讀灰化），
只留共用元件名稱、四個動作與唯讀摘要。
理由：完全共用之後頁面端改了也不生效，留著可編輯的欄位比隱藏更誤導。

`access_matrix` 區塊**例外，維持可編輯**（§1.3 的交集語意）。

### 8.3 編輯共用元件 modal

沿用現行共用選單 modal 的形狀（存檔與頁面儲存分開，按鈕 `[儲存共用元件]`）：

- menu 型別：items 樹編輯 ＋ **自動模式開關** ＋ `include_system_links`
  （自動模式開啟時，items 編輯區隱藏）
- 其他型別：該型別的完整屬性欄位

### 8.4 兩個宿主都要改

`_ir_designer_body.html` 有兩個宿主頁（`ir_designer.html` 與 `workspace.html`），
`{% block scripts %}` **各寫各的**。新增 JS 檔時兩邊都要加，
日常用的是工作區那邊。

## 9. 驗收

- 反向檢查先於功能測試：搜尋是否有繞過 `resolve_shared_component` 的直接寫法、
  是否有殘留讀 `dc_shared_menus` 的路徑
- 瀏覽器實測（VERIFY-01/03，主 Claude 執行，不可外包）：
  引用／解除引用／編輯共用元件／自動模式開關／跨頁生效
- 留證 `/opt/tmp/verify/<日期>-shared-components.log`（VERIFY-02）
- 迴歸基準：`bash scripts/run_tests.sh` 對照 `382 passed, 1 failed, 1 skipped`

## 10. 本規格**不**包含（留在 PF-47）

- 「頁面 × 共用元件」批次矩陣 UI
- 子系統預設選單（新頁自動引用）

有了共用元件庫＋自動模式後，這兩項的必要性下降：新頁靠樣板帶 `shared_ref`，
選單內容由自動模式免設定。
