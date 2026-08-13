# 頁面版面樣板庫規格（Page Templates）

> 定版：2026-08-04（PF-24~28、PF-32），2026-08-06 自 `CLAUDE.md` 移出成獨立規格
> 相關：`dev-notes/SHARED_COMPONENTS_SPEC.md`（共用元件＝引用語意，與本檔的複製語意互補）、
> `dev-notes/PAGE_IR_SPEC.md`（IR schema）、`dev-notes/PAGE_IR_LAYOUT_ENGINES.md`（三個版面引擎）

## 0. 一句話定位

**樣板是複製語意**：以樣板建頁 ＝ 把樣板當下的 IR 複製一份成為新頁，此後兩者無關。
需要「改一次、所有頁面同步生效」的請用共用元件（引用語意），見
`dev-notes/SHARED_COMPONENTS_SPEC.md`。

## 1. 資料模型：`dc_page_templates`

三種 `scope`：

| scope | `org_secure_code` | `sub_system_secure_code` | 誰看得到 | 誰能建立 |
|---|---|---|---|---|
| `system` | **必須 NULL** | **必須 NULL** | 所有企業所有子系統 | **只有種子腳本，API 一律 403** |
| `org` | 企業 sc | NULL | 該企業全部子系統 | API |
| `sub_system` | 企業 sc | 子系統 sc | **只有來源子系統** | API |

DB 有 CHECK 約束保證 `system` 的兩個欄位為 NULL。

**`scope='sub_system'` 只有來源子系統看得到**（`list_templates` 第三段以
`sub_system_secure_code` 過濾）。因此**跨子系統套用在 UI 上唯一走得到的路徑是
`scope='org'` 樣板**——要重現淨化行為時別選 sub_system 的（看不到），
也別選內建的（零綁定、淨化是 no-op）。

## 2. API

| 端點 | 用途 |
|---|---|
| `GET /api/nocode-builder/templates?sub_system=<sc>[&include_hidden=1]` | 三段 union：內建 + 本企業 + 該子系統私有 |
| `POST /api/nocode-builder/templates` | 另存為樣板（`scope='system'` → 403） |
| `POST /api/nocode-builder/templates/<sc>/instantiate` | 以樣板建頁，回 `{page, report}` |
| `POST /api/nocode-builder/sub-systems/<ss>/template-hides` | 隱藏內建樣板（冪等，非 system → 400） |
| `DELETE /api/nocode-builder/sub-systems/<ss>/template-hides/<tpl>` | 取消隱藏（冪等） |

`instantiate` **只建 `DcPageLayout`**，不建 site map 節點、不做子系統掛載——
那是前端 `workspace.js` 的 `finishPageCreation()` 接手做的。
它也會把 IR 的 `page.title_i18n` 覆寫成新頁名稱（不覆寫的話 portal 上會顯示樣板名）。

## 3. 隱藏是「可見性」不是「授權邊界」（PF-32）

`dc_sub_system_template_hides` 記錄 per 子系統的隱藏名單，**只作用於 `scope='system'`**。

- `list_templates` 預設扣掉；`include_hidden=1` 保留並標 `is_hidden`
- `instantiate` **刻意不檢查隱藏**（UI 觸發不到，且隱藏不是安全邊界）
- **取消隱藏一律硬刪列**（`db.session.delete`），不可軟刪——
  unique `(sub_system_secure_code, template_secure_code)` 會擋住之後重新隱藏
- 隱藏**不得**用「軟刪 system 樣板」實作：種子腳本會把 `is_deleted` 設回 False 復活它

## 4. 淨化：只有跨子系統才做

判定：`sanitized = (not source) or (source != target)`
（`page_template_service.py` 一開頭就 `return`，依據是樣板的 `source_sub_system_sc`，
為 NULL 一律走淨化路徑）。

### 4.1 同子系統套用完全不淨化

menu 的 `items[].node`、`shared_ref`、access_matrix **原封不動保留**，
`create_template` 也是原樣存 `layout_json` 不做任何處理。

**「另存為樣板」存的是當下那頁的完整 IR**，不是內建樣板的副本；
內建樣板的「零綁定」是那六筆種子資料的內容，**不是會傳染的屬性**
（2026-08-06 API 實測確認）。

要讓新頁一建出來就有選單，正解是先設好一頁（menu 引用共用元件）再另存為
子系統私有樣板；既有頁面沒有批次套用的方法，見待辦 **PF-47**。

### 4.2 跨子系統的淨化規則

唯一實作是 `modules/nocode_builder/services/page_template_service.py::sanitize_template_ir()`，
純函式、不碰 DB，**禁止各處自行清理引用**。

分水嶺是 **schema 能不能省略**：

| 對象 | 處置 | report 碼 |
|---|---|---|
| menu 的 `items[].node` | 整枝移除 | — |
| `binding.resource`（必填） | **整個 widget 移除**，並同步清 canvas `widget_ids`／layout `children`／`row_link_ref` | `binding_unavailable` |
| 所有型別的 `shared_ref` | 清掉。menu 清掉後**必須補 `items: []`**（少補的話淨化產物過不了 `validate_page_ir`，整個 instantiate 會 500）；其他型別因缺必填欄位整個 widget 移除 | `shared_component_refs` / `shared_component_unavailable` |
| 權限碼類（`action_ref`／`access_matrix`） | **保留**並列進 `report.warnings` | — |

權限碼保留而不清除的理由：系統本來就 fail-closed，擅自清掉反而讓使用者以為設定過了。

`report` 內是**機器可讀碼**，中文對照在前端 `page-template.js` 的 `describeReport()`，
**後端不要翻譯**。

## 5. 內建樣板

`scripts/seed_system_page_templates.py --apply` 種入（冪等），固定六個 secure_code：

```
sys_tpl_top_left_main  sys_tpl_top_main  sys_tpl_left_main
sys_tpl_single         sys_tpl_dashboard sys_tpl_free_blank
```

它們**一律零綁定**（空 menu + 佔位 text）——會被所有企業的所有子系統套用，
任何綁定必然是錯的。

`--purge-legacy` 可軟刪沒有 `ir_version` 的 v2 舊樣板（預設不做）。

## 6. 縮圖

`thumbnail_svg` **留空即可**，前端 `templateThumbnailSrc()` 會從 IR 即時生成，
不要在 Python 裡重寫 SVG 產生器。

該欄位是可經 API 寫入的自由文字，所以：

- **一律用 `<img src="data:image/svg+xml,...">` 呈現、禁止 `x-html`**（img 內的 SVG 不執行腳本）
- 後端另有 `_validate_thumbnail_svg()` 擋 `<script>`／`on*=`／`xlink:href`／超長

**IR 的 `zone.row` / `zone.col` 是 1-based**（schema `minimum: 1`），換算成陣列索引要減 1。
`gridSvg` 犯過這個錯，所有 zone 疊在同一格、縮圖只剩右下一塊
（2026-08-04 commit `324842d8` 修）。
