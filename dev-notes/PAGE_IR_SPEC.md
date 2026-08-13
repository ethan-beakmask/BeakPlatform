# Page IR 規格書 (v3)

**跨專案安全頁面組裝標準 -- 設計態與執行態單一格式**

> **規格所有權聲明**：本規格暫定於 BeakPlatform `dev-notes/`，所有權將移出至獨立套件
> （跨專案共用：BeakPlatform / NoCode 子系統 / BeakForge）。移出前以本文件為唯一權威版本。
>
> **版本沿革**：`dc_page_layouts.layout_json` 的 v2 格式（`{version: 2, widgets: []}`）
> 自本規格定案起**直接廢棄**，不提供 migration（本機皆測試資料，2026-07-27 用戶裁決）。
> 新格式直接定為 **v3 = Page IR**。v2 渲染路徑已於 2026-07-28 完全移除，舊頁面請求回 410。

---

## 0. 設計原則（定案脈絡）

1. **單一 IR 貫穿設計態與執行態**：設計器存的 JSON 就是 runtime 讀的 JSON，
   執行期不做二次轉譯，避免兩份真相。
2. **安全是格式的性質，不是提示詞的叮嚀**：不安全的東西在 IR 裡**無法被表達**
   （詳見第 5 節安全不變量）。AI 產出 IR 時能犯的錯只剩 UI 層錯誤，犯不了資安錯誤。
3. **判定引擎獨立、規範語彙統一**（沿用 `COMPONENT_VISIBILITY_GUIDE.md` 定案）：
   IR 不內建任何權限判定，一律委派平台既有四層防線
   （PageRoleGuard / can() / schema 裁剪 / EGRESS-01）。
4. **form.io 降級為可插拔的表單渲染器**：只活在 `form` widget 的 payload 子樹內，
   外層版面與其他 widget 與 form.io 無關。form.io 升級不影響 IR。

---

## 1. 三層架構

| 層 | 內容 | 定義者 | 跨專案 |
|---|---|---|---|
| **L0 Page IR core** | 頁面文件結構、widget 樹、綁定參照語法、id 規則、版本號 | 本規格第 2、4 節 | **共用，唯一標準** |
| **L1 Widget 目錄** | 可用 widget 清單與各自屬性 schema | 本規格第 3 節（首發 6 項）；各專案可**註冊**擴充 | 基本目錄共用，擴充各自註冊 |
| **L2 Binding Resolver** | 綁定參照 → 實際資料/動作的執行期解析 | 各平台自行實作（介面約定見第 6 節） | **刻意不共用**（安全邊界所在） |

L2 不共用是設計刀口：同一份 IR，在 BeakPlatform 走 ResourceGateway + EGRESS + 權限鏈；
在 NoCode 子系統只認子系統 SQLite 與 SQLite 內帳號（母系統權限不進入）；
在 BeakForge SRS 階段接 fixture 假資料純預覽。

---

## 2. L0：頁面文件結構

### 2.1 頂層結構

```json
{
  "ir_version": 3,
  "page": {
    "id": "guest-enrollment-list",
    "title_i18n": {"zh-TW": "報名清單", "en": "Enrollment List"},
    "widgets": [ /* widget 樹，見下 */ ]
  }
}
```

- `ir_version`：整數，本規格為 `3`。runtime 遇到不認識的版本一律拒絕渲染（fail-closed）。
- `page.id`：頁面級唯一 slug（規則同 2.2）。
- `title_i18n`：i18n dict，key 為 locale。所有 user-facing 字串一律 `*_i18n` dict，
  **禁止**裸字串欄位（呼應 I18N-01；IR 屬 DB 資料，不走 gettext）。

### 2.2 Widget 共同欄位

每個 widget 必有：

| 欄位 | 型別 | 規則 |
|---|---|---|
| `id` | string | **穩定的人類可讀 slug**（kebab-case，`^[a-z][a-z0-9-]{1,63}$`），頁面內唯一。設計器產生時以語意命名（如 `enroll-table`），**禁止隨機碼**——AI 修改時可精準定位、diff 可讀 |
| `type` | string | 必須是 L1 目錄已註冊的 type，未註冊即拒絕（存檔與渲染兩端都驗） |

其餘屬性依各 type 的 JSON Schema 定義，**一律 `additionalProperties: false`**：
AI 幻覺出的屬性在存檔時即被拒絕，不靜默帶病上線。

### 2.3 驗證

- 採 JSON Schema（Draft 2020-12）嚴格驗證，驗證器為存檔（設計器 save API）
  與渲染（runtime load）兩端共用的同一支程式。
- 驗證失敗 = 拒絕存檔 / 拒絕渲染，回報精確路徑（如 `widgets[2].columns[0]: unknown field 'sql'`），
  供 AI 或人類修正。

---

## 3. L1：Widget 目錄

全部對應平台既有能力，不發明新機制。圖表、tab、卡片等列入後續版本。
目錄採**註冊制**：runtime 維護 widget registry，未註冊 type 渲染期直接拒絕。

3.1~3.6 是 v3.0 首發六項；**3.7 之後為後續新增**
（`menu` 見 3.7；`master_detail`、`file_box` 另見
`dev-notes/PORTAL_FILE_WIDGET_SPEC.md` 與各自的實作）。
所有型別在 schema 中皆為 `required: ["id","type"]` 加
`anyOf: [{required:[<原必填>]}, {required:["shared_ref"]}]`——
`shared_ref` 是共用元件引用，見 `dev-notes/SHARED_COMPONENTS_SPEC.md`。

### 3.1 `layout` -- 區塊/欄格容器（唯一容器型 widget）

```json
{
  "id": "main-grid", "type": "layout",
  "columns": 2, "gap": 16,
  "children": [ /* widget 陣列 */ ]
}
```

- 渲染為 CSS Grid（呼應 FRONT-07，禁 Bootstrap grid）。
- `columns`: 1~4；`gap`: px 整數。可巢狀，深度上限 4（驗證器強制）。
- **唯一**可含 `children` 的 type，其餘皆為葉節點。

### 3.2 `table` -- 資料表格

```json
{
  "id": "enroll-table", "type": "table",
  "binding": {"resource": "enrollment", "view": "list", "fields": ["name", "email", "created_at"]},
  "columns": [
    {"field": "name", "label_i18n": {"zh-TW": "姓名"}, "sortable": true}
  ],
  "page_size": 20,
  "default_sort": {"field": "created_at", "dir": "desc"},
  "access_matrix": {
    "read": {"required_permissions": ["enrollment.read"], "match_mode": "any"}
  },
  "row_actions_ref": "enroll-row-actions"
}
```

- `columns[].field` 必須 ∈ `binding.fields`（驗證器強制）。
- 資料一律由 L2 resolver 供給；欄位能見度（clear/masked/hidden）由 EGRESS-01 執行期決定，
  **IR 內無任何能見度欄位可寫**。
- `row_actions_ref`：引用同頁 `actions` widget 的 id（每列動作鈕），可省略。
- `access_matrix`：資料元件級 portal 准入宣告，格式見 6.3.1；可省略。
- 可排序欄位表頭預設顯示排序符號（全域前端規範）。

### 3.3 `detail` -- 單筆欄位檢視

```json
{
  "id": "enroll-detail", "type": "detail",
  "binding": {"resource": "enrollment", "view": "detail", "fields": ["name", "email", "id_number"]},
  "layout_columns": 2,
  "access_matrix": {
    "read": {"required_permissions": ["enrollment.read"], "match_mode": "any"}
  },
  "fields": [
    {"field": "id_number", "label_i18n": {"zh-TW": "身分證字號"}}
  ]
}
```

- masked 欄位 hover 逐格揭示沿用 `BkEgress.bind()` 既有機制。
- `access_matrix`：資料元件級 portal 准入宣告，格式見 6.3.1；可省略。
- **禁止** list 頁內嵌預載 detail 資料（EGRESS-01 既有禁令）：
  `table` + `detail` 同頁時必須分開請求。

### 3.4 `form` -- 表單（form.io schema payload）

```json
{
  "id": "enroll-form", "type": "form",
  "formio_schema": { /* form.io schema JSON，原樣持有，IR 不解析其內部 */ },
  "submit_action_ref": "enroll-submit"
}
```

- `formio_schema` 是**不透明 payload**：IR 驗證器只驗它是 object，不驗內部
  （form.io 版本升級不影響 IR schema）。
- `submit_action_ref` 是 **L2 action registry 參照**（同 `actions.action_ref` 的 pattern），
  **不是**頁內 actions widget 的 id——渲染期經 `get_action()` fail-closed 解析
  （2026-07-27 修訂：P1 初版誤將其列入頁內 dangling_ref 檢查，P3 定案更正）。
- 執行期沿用 form_workflow 整套既有防線：三態欄位權限伺服器端裁剪
  （`_apply_field_permissions_to_schema()` 模式）、form_data hidden 同步剔除（Forgejo #27 修法）、
  EGRESS `form_node` 語境最終守門。裁剪一律在 server 端、於 IR runtime 吐出 schema 之前完成。

### 3.5 `actions` -- 按鈕列

```json
{
  "id": "enroll-row-actions", "type": "actions",
  "buttons": [
    {
      "id": "btn-approve",
      "label_i18n": {"zh-TW": "簽核"},
      "style": "primary",
      "permission": "enrollment.approve",
      "action_ref": "enrollment.approve"
    }
  ]
}
```

- `permission`：**只准引用既有 permission code**（API 層那套命名，不另創）。
  渲染期由 `can()` / `BkCaps` 判定：無權限 → server-side 不渲染該鈕（DOM 不存在）。
- `action_ref`：指向 L2 已註冊的 action（見 6.2），**IR 內不可出現 URL / endpoint 字串**。
- `style`: `primary | secondary | danger`（對應 common.css 既有 `.btn` 系）。

### 3.6 `text` -- 靜態文字/標題

```json
{"id": "page-intro", "type": "text", "level": "h2", "content_i18n": {"zh-TW": "報名須知"}}
```

- `level`: `h1|h2|h3|p`。無安全語意、無綁定。content 渲染時一律 HTML escape（禁 raw HTML）。

### 3.7 `menu` -- 導覽選單（PF-8c 起，2026-08-03/04 定版）

> 2026-08-06 自 `CLAUDE.md` 移入。自動模式（`source_mode`／`include_system_links`）
> 的完整規則在 `dev-notes/SHARED_COMPONENTS_SPEC.md` §5。

```jsonc
{"type":"menu","id":"menu-1","title_i18n":{...},
 "items":[{"kind":"node","node":"<site_map_node_sc>","children":[...]},
          {"kind":"system","link":"login|register|logout"}],
 "orientation":"vertical|horizontal","item_gap":6,"hover_expand":true,
 "nav_source":"self|parent_selection","nav_key":"nav",
 "style":{"bg_color":"#ffffff", ...六色..., "border_color":"#dddddd",
          "border_width":1,"border_radius":4,
          "background_file":"<platform_files.secure_code>",
          "background_size":"cover","background_repeat":"no-repeat",
          "background_position":"center"}}
```

**items 是完全自訂的樹**：陣列順序＝顯示順序、`children` 巢狀＝階層（深度上限 5），
**不跟著 site map 的結構與順序走**（2026-08-03 用戶定案改的，早期版本相反）。
名稱與圖示仍即時取自 site map，所以改名會反映；節點被刪或停用時該項連同
children 整枝消失（fail-closed）。

顯示條件 = 在 items 樹中 AND `check_page_access` 通過
（menu 是導覽、不是授權邊界，各頁自己仍會再判一次）。

**樣式顏色一律 `^#[0-9a-fA-F]{6}$`**：schema 擋一次、renderer `_menu_style()`
白名單化再擋一次——值最後會進 inline style，兩道防線缺一不可。

底圖只認 `context_type == 'nc_background'` 的 platform file，不接受任意 URL。
**存的是 `platform_files.secure_code`，不是 `DcBackground.secure_code`**
（`/api/nocode-builder/backgrounds` 回應的 `platform_file_sc` 欄位）——
存錯的症狀是「選了底圖完全沒反應、也不報錯」。
UI 上「不使用底圖」是空字串，但 schema pattern 不收空字串，**寫入端必須正規化**：
頁面存檔走 `ir-designer.js::normalizeMenuOnSave`，共用元件走
`shared_component_api._normalize_widget_json`，**兩條路都要有**。

**兩個 menu 聯動**：`nav_source=parent_selection` 依 `?<nav_key>=` 只渲染該節點的
children，純伺服器端。聯動連結**只沿用本頁各 menu 的 nav_key**
（`renderer._menu_nav_keys()`），不可整包複製 `request.args`
（表格的 `xxx__page`／`xxx__sort` 會被帶去別頁撞上同 id 的 widget）。

橫式子選單是純 CSS hover 浮出，**父子之間的 gap 必須有透明 `::before` 橋接**，
否則滑鼠移過去的瞬間就離開 `:hover`、子選單當場消失（commit `71e8ea54`）。

平台層走 registry：`register_menu_provider(world, fn)`，portal 實作在
`services/pageir_portal_menu.py`；**platform world 沒有 provider 是預期狀態**
（entries 回空陣列，不 raise）。provider 要求 render context 同時有
`sub_system_sc`、`portal_user`、`path_id`，**少任何一個一律回空陣列**，
畫面上就是「沒有可顯示的項目」。

`system_link` 值域是**後端白名單**（login/register/logout），不接受任意 URL；
login/register 只在未登入時出現，register 另需 `allow_registration`，logout 反之。

**設計器預覽的 menu 連結留在預覽語境**（2026-08-06 起，commit `a0272748`）：
`portal_user['user_type'] == 'PREVIEW'` 時，node 連結組成
`/nocode/ir-designer/<目標頁sc>/preview?sub=&level=&group=`（沿用當前預覽身分），
system_link 一律不輸出（預覽沒有 portal session，登入／登出走不通）。
在此之前連結一律指向公開 portal，**未發布的子系統／頁面點下去必定 404**——
症狀是「直接按預覽正常、從預覽的選單點過去 404」。正式 portal 行為不變。

site map 的 `folder` 節點型別已放行（不建 page layout、不可當根節點）。

尚未移植 v2 SITEMENU 的：橫式圖示位置、選單高度、懸停延遲（待辦 **PF-19**，
內含 v2 的值域／預設值與要改的檔案清單，動工前先讀）。

---

## 4. L0：綁定參照語法（Binding Reference）

IR 中「資料從哪來」只有一種合法寫法：

```json
{"resource": "<resource_code>", "view": "<view_name>", "fields": ["k1", "k2"]}
```

- `resource`：L2 resolver 註冊表中的資源代碼（字串 slug）。
- `view`：該資源下已註冊的視圖名（如 `list` / `detail`）。
- `fields`：欄位 key 白名單陣列。resolver 只回傳這些 key（再經 EGRESS 過濾）。

**除此之外的任何取數表達皆屬非法**：IR schema 中不存在可放 SQL、欄位運算式、
字串拼接、任意 URL 的欄位——寫了就是 `additionalProperties` 驗證失敗。
這使「繞過 ResourceGateway」在格式層面不可表達。

---

## 5. 安全不變量（INV，驗收時逐條檢查）

| # | 不變量 | 落點 |
|---|---|---|
| INV-1 | **IR 無查詢語言**：取數僅准第 4 節白名單結構，無任何欄位可承載 SQL/表達式/URL | JSON Schema |
| INV-2 | **能見度不是設計項**：設計者只能宣告「欄位出現在哪」，clear/masked/hidden 由 EGRESS-01 執行期決定，IR 不可覆寫（否則即提權路徑） | schema 無此欄位 + resolver |
| INV-3 | **hidden 一律後端不出資料**：hidden widget/欄位不進 render tree、不進 API 回應；前端條件顯示只准當體驗輔助 | server-side 渲染 |
| INV-4 | **三態語彙統一** `editable / readonly / hidden`（按鈕為 visible/hidden 退化版；EGRESS 資料值對應 clear/masked/hidden） | 全平台既定 |
| INV-5 | **fail-closed**：未註冊 widget type、未註冊 resource/view/action、不認識的 ir_version → 拒絕（存檔與渲染兩端） | validator + registry |
| INV-6 | **IR 不定義權限**：`permission` 欄位只引用既有 permission code；新權限走平台既有註冊管道，IR 無此能力 | schema + 驗收 |
| INV-7 | **動作 API 防線不因 IR 而免**：`actions` 按鈕背後的 API 照掛 `@permission_required`（D2 標準）；IR 渲染層只是 UI 鏡射，非防線 | L2 action registry |

---

## 6. L2：Binding Resolver 介面約定

各平台實作以下介面（語言/框架不限，語意必須一致）：

### 6.1 資料解析

```
resolve_binding(binding, ctx) -> {rows | record, field_visibility}
```

- `ctx`：執行語境（當前用戶、org、頁面、node_key 等，由平台注入，IR 不可指定）。
- 回傳資料**已完成**權限過濾與 EGRESS 能見度處理（masked 值以哨兵替換、hidden 剔除）。
- 未註冊的 `resource`/`view`、`fields` 含未授權欄位 → 拒絕（fail-closed）。

### 6.2 動作解析

```
resolve_action(action_ref, ctx) -> 已註冊動作的執行端點
can(permission, ctx) -> bool
```

- action registry 由各平台維護：`action_ref` → 實際 API endpoint 的對照在 resolver 內，不在 IR 內。

### 6.3 三種 resolver 的預定實作

| 平台 | 資料面 | 權限面 |
|---|---|---|
| BeakPlatform | ResourceGateway + EGRESS-01 | 四層防線全套（雙鑰匙 / can() / 裁剪 / egress） |
| NoCode 子系統 | **僅**子系統專屬 SQLite（單向橋接寫入）；母系統權限**不進入** | SQLite 內帳號體系（portal_users / portal_roles） |
| BeakForge (SRS) | fixture 假資料，不接後端 | 全通過（純預覽）；RD 階段由目標專案 resolver 接手 |

#### 6.3.1 NoCode 子系統 resolver（P4 定案，2026-07-28）

- **兩個世界互斥**：渲染語境（render context）分 `platform` / `portal` 兩種，
  由渲染入口路由在 server-side 設定，IR 不可指定。
  - `platform` 語境**只准**解析無前綴資源（`user` 等平台註冊資源），
    解析 `portal:` 資源一律 None → fail-closed（平台登入不得讀子系統 SQLite）。
  - `portal` 語境**只准**解析 `portal:` 前綴資源，
    解析平台資源一律 None → fail-closed（母系統資料不進入 portal）。
  - 一份 IR 頁面天然屬於單一世界，不存在混血頁。
- **`portal:` 前綴資源**：`{"resource": "portal:<DcCrudView.secure_code>"}`，
  registry 採 prefix 型 provider（先例：egress `register_accessor_prefix`）。
  binding_slug pattern 為此放寬允許 `portal:` + secure_code 字元集
  （唯一允許的前綴例外；secure_code 非人類可讀 slug 是已知取捨，
  設計器以下拉選單呈現 view 名稱）。
- **欄位白名單來源**：`DcCrudView.columns_config` 的 visible 欄位
  （沿用 sqlite_crud_service 既有安全配置層）；`binding.fields` ⊄ 白名單 → 拒絕。
  N4b 起 portal resolver 另提供寫入介面：`writable_fields`、`crud`、
  `create_row(payload)`、`update_row(record_sc, payload)`、`delete_row(record_sc)`；
  可寫欄位仍由 runtime 以 `binding.fields`、`resource.fields`、`writable_fields`
  三重交集決定。
- **EGRESS 取捨**：SQLite 資料無 EGRESS 政策（EGRESS-01 屬母系統 PostgreSQL 資源），
  portal resolver 的 `egress_resource` 一律 `None`，欄位控制**僅**靠
  columns_config 白名單。此為已知取捨，不新增 INV。
- **敏感欄位硬排除**（2026-07-28 用戶裁決）：欄名含
  `password / passwd / pw_hash / secret / token / salt / api_key / apikey /
  credential / private_key`（不分大小寫、子字串比對）者，resolver 層無條件
  剔出白名單——即使 columns_config 標 visible 也擋。設計器 meta 與渲染兩端
  共用同一 helper（`_strip_sensitive_columns`）。誤傷寧可偏嚴（fail-closed 傾向）。
- **語境注入**：portal 語境 ctx 含 `sub_system_sc`（由 portal path_id 於 server-side
  解析，**禁止**採用 client 提供的 sub_system_sc 參數/header）與 portal session
  （portal_auth_service，與 Flask-Login 完全分離）。
- **portal 渲染入口**：`/public/portal/<path_id>/p/<page_layout_sc>`，
  要求 portal session（或子系統允許匿名時自動 GUEST）；頁面必須
  `status='published'`、`ir_version=3`、且經 DcSubSystemPage 掛載於該子系統
  並通過 visible_roles 檢查。`/p/` 維持平台世界專用。
- **元件級 `access_matrix`（N4a）**：`table` / `detail` 可宣告
  `access_matrix`，目前 runtime 只消費 `read`，schema 與型別保留
  `create` / `update` / `delete` 給 N4b。

  ```json
  {
    "read": {"required_permissions": ["enrollment.read"], "match_mode": "any"},
    "create": {"required_permissions": ["enrollment.create"], "match_mode": "any"},
    "update": {"required_permissions": ["enrollment.update"], "match_mode": "any"},
    "delete": {"required_permissions": ["enrollment.delete"], "match_mode": "all"}
  }
  ```

  `required_permissions` 必須是既有 `portal_permissions.code`（格式
  `resource.action`，小寫 snake_case），至少一項；`match_mode` 選填，
  `any`（預設，任一即可）或 `all`（全部都要）。有效權限由
  `portal_permission_service` 計算（階級 rank 向下繼承、管理角色聯集、
  個人 deny 最優先）。此欄位只在 `portal` 語境生效；`platform` 語境仍走
  ResourceGateway / EGRESS / can()，不消費此宣告。Portal 語境下未宣告
  `access_matrix` 代表不額外限制；宣告後 `read` 不通過、評估器未註冊、
  或 rule 格式不合法（空陣列、未知 match_mode、多餘欄位），
  該元件不進 render tree，也不取資料。

  與 INV-2 的關係：這是「准入宣告」，只引用既有 permission code（呼應
  INV-6），不是欄位 clear/masked/hidden 覆寫。欄位能見度仍由 EGRESS 或
  portal resolver 白名單在 runtime 決定，IR 只宣告元件准入條件。

---

## 7. 渲染模式

- **Server-side 渲染為主**（Jinja + Alpine 架構）：runtime 讀 IR → 逐 widget 經
  registry 渲染 → 無權限元件不進 DOM。
- 前端只做互動增強（排序、分頁請求、hover 揭示），不做權限判定。
- 樣式僅用 common.css 既有元件 + `var(--color-*)` 白名單變數（FRONT-07），
  IR widget 渲染輸出使用 `pir-` 前綴 class。

---

## 8. 實作階段切分（codex 工單順序）

| 階段 | 內容 | 前置 |
|---|---|---|
| P1 | IR JSON Schema（L0 + 六 widget）+ 共用驗證器 + 存檔 API 接驗證器；v2 廢棄（讀到 `version: 2` 即拒絕並提示重建） | 本規格定稿 |
| P2 | Server-side renderer 六 widget + BeakPlatform resolver（ResourceGateway/EGRESS/can() 接線） | P1 |
| P3 | 設計器 MVP：拖拉擺放 + 屬性面板（依 widget schema 自動生成）+ `form` widget 子樹嵌既有 form.io builder + 即時預覽（fixture resolver） | P1（P2 可並行） |
| P4 | NoCode 子系統 SQLite resolver | NoCode_Builder 重寫立項時 |
| P5 | BeakForge fixture resolver + SRS 流程接入 | BeakForge 改版時 |

每階段：Fable 撰 spec → codex 實作 → Fable 驗收（含 INV-1~7 逐條反向檢查：
每個抽象層都搜尋「繞過它的直接寫法」）。

---

## 9. 與既有文件的關係

- `COMPONENT_VISIBILITY_GUIDE.md`：四層防線與三態語彙的定案來源；本規格是其
  「NoCode_Builder 重寫消費指引」（§4）的具體化。
- `EGRESS_POLICY_SPEC.md`：INV-2/INV-3 的執行機制。
- `PERMISSION_MODEL.md`：permission code 與雙鑰匙的權威定義。
- form.io 相關既有結論（2026-07-18 session）：form.io conditional visibility
  是前端條件、資料仍在 payload，只准當體驗輔助不准當防線——本規格 INV-3 的由來。

---

*定稿待用戶審核。裁決記錄：2026-07-27 -- 單一 IR 不二次轉譯 / 規格暫居 BeakPlatform docs / v2 直接廢棄 / 首發六 widget / AI 可讀寫三硬規則（穩定 slug id、additionalProperties: false、綁定白名單）。*
