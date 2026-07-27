# Page IR 規格書 (v3)

**跨專案安全頁面組裝標準 -- 設計態與執行態單一格式**

> **規格所有權聲明**：本規格暫定於 BeakPlatform `docs/`，所有權將移出至獨立套件
> （跨專案共用：BeakPlatform / NoCode 子系統 / BeakForge）。移出前以本文件為唯一權威版本。
>
> **版本沿革**：`dc_page_layouts.layout_json` 的 v2 格式（`{version: 2, widgets: []}`）
> 自本規格定案起**直接廢棄**，不提供 migration（本機皆測試資料，2026-07-27 用戶裁決）。
> 新格式直接定為 **v3 = Page IR**。

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

## 3. L1：首發 Widget 目錄（v3.0，六項）

全部對應平台既有能力，不發明新機制。圖表、tab、卡片等列入 v3.1 之後。
目錄採**註冊制**：runtime 維護 widget registry，未註冊 type 渲染期直接拒絕。

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
  "row_actions_ref": "enroll-row-actions"
}
```

- `columns[].field` 必須 ∈ `binding.fields`（驗證器強制）。
- 資料一律由 L2 resolver 供給；欄位能見度（clear/masked/hidden）由 EGRESS-01 執行期決定，
  **IR 內無任何能見度欄位可寫**。
- `row_actions_ref`：引用同頁 `actions` widget 的 id（每列動作鈕），可省略。
- 可排序欄位表頭預設顯示排序符號（全域前端規範）。

### 3.3 `detail` -- 單筆欄位檢視

```json
{
  "id": "enroll-detail", "type": "detail",
  "binding": {"resource": "enrollment", "view": "detail", "fields": ["name", "email", "id_number"]},
  "layout_columns": 2,
  "fields": [
    {"field": "id_number", "label_i18n": {"zh-TW": "身分證字號"}}
  ]
}
```

- masked 欄位 hover 逐格揭示沿用 `BkEgress.bind()` 既有機制。
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
| NoCode 子系統 | **僅**子系統專屬 SQLite（單向橋接寫入）；母系統權限**不進入** | SQLite 內帳號體系（細節於 NoCode_Builder 重寫時另議） |
| BeakForge (SRS) | fixture 假資料，不接後端 | 全通過（純預覽）；RD 階段由目標專案 resolver 接手 |

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
