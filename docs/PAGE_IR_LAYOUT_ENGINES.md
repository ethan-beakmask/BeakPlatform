# Page IR v3 版面引擎（Layout Engines）規格

定版日期：2026-08-05
狀態：規格定版，分兩批實作（批次 1 後端渲染、批次 2 設計器 UI）

## 1. 背景與決策

Page IR v3 目前唯一的排版單位是 `layout` widget（`columns` 1~4 均分、可巢狀），
本質是**流式版面**：只能切等分，沒有跨列合併、沒有列高控制，
`pageir.css` 在 720px 以下強制塌成一欄。適合表單／清單，不適合儀表板與入口頁。

已退役的 v2 設計器（Studio，commit `27464e66` 刪除）有兩種**幾何式**版面：
矩陣（16 宮格切割合併）與自由（GridStack 12 欄拖放）。

### 決策：不做自動適配，改提供三個版面引擎讓設計者自選

理由：純 CSS 自適應對大型商務表單不適用，因為**閱讀順序無法自動推導**——
桌機並排的欄位在手機該上下排還是併成摺疊群組，只有設計者知道。
把「這頁給誰在什麼裝置上用」這個產品決策還給設計者，平台不猜。

| engine | 語意 | 適用 | 窄螢幕 |
|---|---|---|---|
| `flow`（預設，即現況） | 縱向流 + layout widget 等分 | 表單、清單、明細 | 自動塌成一欄 |
| `grid` | 矩陣切割／合併，欄寬 fr、列高 px | 儀表板、子系統入口頁 | 水平捲動（不塌） |
| `free` | 12 欄 × row_unit 網格自由放置 | 美工版面、看板 | 水平捲動（不塌） |

### 核心約束：三個引擎只差「外殼」，不差「內容」

```
engine 決定「框在哪、多大」
  └── 框（zone / frame）內部一律是現有的 flow widget list
```

- `page.widgets` 結構、widget 渲染、access_matrix、egress、i18n **一行不改**
- 新增 widget 型別時只需實作一次，不必做三遍
- **禁止跨引擎巢狀**（zone 裡不能再放一個 canvas）。v2 Studio 也不支援，
  允許的話設計器的選取／拖放語意會爆掉
- IR 遷移是純加法：沒有 `engine` 欄位＝`flow`，現有頁面零改動

### 已定案的三個邊界問題

1. **高度溢出**：zone／frame 預設 `overflow: auto`（內部捲動）。
   table／master_detail／form 的高度不可預測，撐開整列會破壞矩陣比例。
   設計器需對這幾種 widget 提示「高度不定，建議給足空間」。
2. **窄螢幕降級**：`grid` 與 `free` 一律「水平捲動 + `min_width`」，不塌、不縮放。
   大螢幕商務系統的常規做法，設計者所見即所得。
   （`free` 座標重疊時線性化順序無解，故不提供降級成 flow 的選項。）
3. **粒度**：**一頁一引擎**。同一子系統的入口頁用 `grid`、表單頁用 `flow` 是正常組合。

---

## 2. IR Schema 增量

```jsonc
{
  "ir_version": 3,
  "page": {
    "id": "page",
    "title_i18n": {"zh-TW": "..."},
    "engine": "flow" | "grid" | "free",   // 選填，預設 "flow"
    "canvas": { ... },                     // engine 為 grid/free 時必填；flow 時禁止出現
    "widgets": [ ... ]                     // 不變。engine != flow 時作為「widget 池」
  }
}
```

### 2.1 `canvas`（engine = "grid"）

```jsonc
{
  "min_width": 1280,                 // int 320..4096，預設 1280。畫布最小寬度(px)
  "col_widths": [1, 2, 1, 1],        // number 0.1..20，長度 = 欄數 (1..24)，單位 fr
  "row_heights": [120, 320, 200],    // int 48..2000，長度 = 列數 (1..24)，單位 px
  "gap": 8,                          // int 0..64，預設 8
  "zones": [
    {
      "id": "z1",                    // slug，全頁唯一（與 widget id 共用命名空間）
      "row": 1, "col": 1,            // 1-based 起點
      "row_span": 2, "col_span": 1,  // >= 1
      "overflow": "auto" | "visible",// 預設 "auto"
      "widget_ids": ["w-table-1"]    // 引用 page.widgets 的**頂層** widget id
    }
  ]
}
```

- **列高用 px 而非 fr**：頁面總高不確定，fr 需要容器有確定高度。
  欄寬用 fr（隨畫布寬度分配），列高用 px（總高 = sum(row_heights) + gap）。
  v2 的 fr 列高不做遷移（v2 `layout_json` 已退役，`/p/` 回 410）。

### 2.2 `canvas`（engine = "free"）

```jsonc
{
  "min_width": 1280,        // 同上
  "row_unit": 60,           // int 20..200，預設 60。每格列高(px)
  "columns": 12,            // const 12（保留欄位，目前固定 12，與 GridStack 對齊）
  "gap": 8,                 // int 0..64，預設 8
  "frames": [
    {
      "id": "f1",           // slug，全頁唯一
      "x": 0, "y": 0,       // 0-based，x 0..11，y 0..999
      "w": 6, "h": 5,       // w 1..12（x+w <= 12），h 1..200
      "overflow": "auto" | "visible",
      "widget_ids": ["w-menu-1"]
    }
  ]
}
```

`free` 的渲染**不用絕對定位**，改用 CSS Grid：
`grid-template-columns: repeat(12, 1fr)` + `grid-auto-rows: <row_unit>px`，
frame 用 `grid-column: x+1 / span w; grid-row: y+1 / span h`。
與 GridStack 的模型一致（GridStack 預設不允許重疊），且不需要 JS 計算高度。

### 2.3 Schema 表達方式

在 `schema_v3.json`：

- `$defs.page` 新增 `engine`（enum，預設值由 renderer 補）與 `canvas`
- 新增 `$defs.grid_canvas`、`$defs.free_canvas`、`$defs.grid_zone`、`$defs.free_frame`
- `$defs.page` 用 `allOf` + `if/then` 綁定：
  - `engine` 缺省或 `flow` → `canvas` 必須不存在（`{"not": {"required": ["canvas"]}}`）
  - `engine == "grid"` → 必須有 `canvas`，且 `canvas` 套 `grid_canvas`
  - `engine == "free"` → 必須有 `canvas`，且 `canvas` 套 `free_canvas`
- `additionalProperties: false` 維持不變（新欄位要明列）

---

## 3. 語意驗證（`validator.py::_semantic_errors`）

schema 表達不了的，一律在此檢查。錯誤 code 沿用既有風格：

| 檢查 | error code |
|---|---|
| zone/frame `id` 與 widget id 重複 | `unique_id`（沿用 `_check_unique_id`） |
| `col_widths` 長度 != 每個 zone 的 col 範圍上界所需；zone 超出矩陣範圍 | `zone_out_of_range` |
| 兩個 zone 幾何重疊 | `zone_overlap` |
| frame `x + w > 12` 或幾何重疊 | `frame_overlap` / `frame_out_of_range` |
| `widget_ids` 指向不存在的 widget | `dangling_widget_ref` |
| `widget_ids` 指向**非頂層** widget（layout 的 children） | `nested_widget_ref` |
| 同一個 widget id 被兩個 zone/frame 引用 | `duplicate_widget_ref` |

**未被任何 zone/frame 引用的頂層 widget：不算錯誤**（設計器需要能存草稿），
但 renderer 不渲染它，並 `logger.info` 記一筆。設計器在儲存時給黃色提示。

---

## 4. Renderer（`renderer.py`）

- `render_page_ir_full(doc)` 回傳 dict 新增 `"engine"` 鍵（`flow`/`grid`/`free`）
- `flow`：行為完全不變
- `grid`/`free`：
  1. 照現行流程 `_prepare_widget()` 準備**頂層** widget（access_matrix 過濾照舊，
     被過濾掉的 widget 其 zone 就是空框，這是預期行為）
  2. 依 `canvas` 組出 zone/frame 清單，每個含 `widgets`（已 prepare 的 widget 物件序列）
  3. 傳給 `pageir/_page_ir.html`
- **fail-closed**：canvas 解析出現任何非預期狀況（引用不到、幾何異常）一律
  `raise PageIrRenderError`，不做「盡量渲染」

### 4.1 flow 的響應式 class（重要）

`pageir.css:454` 現有規則會把 **canvas 內部的** layout/detail 也在 720px 以下壓成一欄，
破壞固定寬畫布。作法：

- renderer 在 **engine == flow** 時，為 layout widget 輸出 `pir-layout pir-layout--responsive`，
  detail widget 輸出 `pir-detail pir-detail--responsive`
- engine 為 grid/free 時**不加** `--responsive`
- `pageir.css` 的 `@media (max-width: 720px)` 規則選擇器改為只作用於 `--responsive` 變體

（不要用 `:has()` 或後代選擇器排除，巢狀 layout 會漏。）

---

## 5. 模板

### 5.1 `backend/app/templates/pageir/_page_ir.html`

新增外殼分支，`render_widget` macro 完全不動：

```jinja
{% if engine == 'grid' %}
<div class="pir-canvas pir-canvas--grid" style="min-width:{{ canvas.min_width }}px; grid-template-columns:{{ canvas.col_template }}; grid-template-rows:{{ canvas.row_template }}; gap:{{ canvas.gap }}px">
  {% for zone in canvas.zones %}
  <div id="{{ zone.id }}" class="pir-zone{% if zone.overflow == 'auto' %} pir-zone--scroll{% endif %}"
       style="grid-area:{{ zone.row }} / {{ zone.col }} / span {{ zone.row_span }} / span {{ zone.col_span }}">
    {% for widget in zone.widgets %}{{ render_widget(widget) }}{% endfor %}
  </div>
  {% endfor %}
</div>
{% elif engine == 'free' %}
  ...（同構，grid-column / grid-row + grid-auto-rows）
{% else %}
  {% for widget in widgets %}{{ render_widget(widget) }}{% endfor %}
{% endif %}
```

`col_template` / `row_template` 由 renderer 組好字串（`"1fr 2fr 1fr"` / `"120px 320px"`），
模板不做運算。**數值一律在 renderer 端經型別轉換與範圍夾制後才進 inline style**
（與 menu widget 的 `_menu_style()` 白名單同一原則：schema 擋一次、renderer 再擋一次）。

### 5.2 外層容器放寬

`grid`/`free` 需要突破現有的內容區限寬，否則畫布被裁切：

- `backend/app/templates/pageir/page_v3.html`：`.pir-page` 依 engine 加 `pir-page--wide`
- `modules/nocode_builder/templates/modules/nocode_builder/portal_page_v3.html`：
  `.portal-content`（`max-width:1180px`）依 engine 加 `portal-content--wide`
  （`max-width:none`），並在包住畫布的容器加 `overflow-x:auto`
- 兩個模板都需要 renderer 回傳的 `engine`，呼叫端（`render_page_ir_full` 的所有使用處）
  要把它傳進 `render_template`

**注意**：`portal_page_v3.html` 不繼承 `layouts/base.html`，樣式必須自己補（CLAUDE.md 既有規範）。

### 5.3 CSS（`backend/app/static/css/pageir.css`）

```css
.pir-canvas { display: grid; }
.pir-canvas--free { grid-template-columns: repeat(12, 1fr); }
.pir-zone { display: flex; flex-direction: column; gap: 16px; min-width: 0; min-height: 0; }
.pir-zone--scroll { overflow: auto; }
```

只能用既有 CSS 變數白名單：
`--color-primary --color-text --color-text-secondary --color-text-muted
--color-bg --color-bg-white --color-bg-light --color-border`。
禁止自創變數（fallback 會生效，曾造成白底白字）。

---

## 6. 設計器（批次 2）

- 頁面屬性面板新增「版面引擎」下拉（流式／矩陣／自由）。
  切換引擎**不刪 widget**，只重建 canvas；已放置的 zone/frame 對應關係清空並提示
- `grid` 畫布復用 `grid-layout-editor.js`（1065 行，目前無引用），
  需**剝離 v2 遺留**：`widgetMap` 內嵌 widget config 與 `DataListWidget` 實例管理
  改為 zone → `widget_ids` 的引用關係
- `free` 畫布用 `backend/app/static/vendor/gridstack/gridstack-all.js`（vendor 已在）
- 左側 widget 池顯示「未放置」的 widget，拖入 zone/frame
- 儲存前若有未放置 widget，顯示黃色提示（不阻擋儲存）

前端規範一律適用：FRONT-01（JS/CSS 分離）、FRONT-05/06/07/08、I18N-01。

---

## 7. 驗收

- **後端**：`pytest tests/test_pageir_*.py tests/test_portal_*.py
  tests/test_sitemap_access_matrix.py tests/test_platform_fixed_filters.py -q`
  基準 248 passed，不得退步；新增 engine 相關測試
- **前端**：VERIFY-01／VERIFY-03——凡使用者要點的東西，
  一律由主 Claude 用 chrome-devtools 實測，不採信 AI 自我檢查表
- **留證**：VERIFY-02——輸出落地 `/opt/tmp/verify/<日期>-pageir-engines.log`

## 8. 不在本次範圍

- v2 `layout_json` 資料遷移（已退役，不做）
- zone/frame 層級的樣式（底色、框線、底圖）——先保持最小可用，日後再議
- 跨引擎巢狀（明確禁止）
- 斷點覆寫式的 `columns: {lg, md, sm}`——三引擎架構下 flow 自己塌一欄已足夠，取消
