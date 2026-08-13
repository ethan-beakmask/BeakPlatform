# BeakPlatform i18n 計畫

**目標語言**: zh-TW (primary) + en
**策略**: 完善現有 Flask-Babel 體系 + 新建 JS i18n 機制
**建立日期**: 2026-03-26

---

## 現況盤點 (2026-03-26)

| 層面 | 檔案數 | 待處理字串數 | 現況 |
|------|--------|-------------|------|
| Backend HTML 模板 | 115/123 | ~800+ | 僅 8 檔有 `_()` |
| Python flash() | 17 檔 | 142 | 0% 包裹 |
| Python API error | 20 檔 | 373 | 0% 包裹 |
| Platform JS | 44 檔 | ~250 user-facing | 無 i18n 機制 |
| 模組 HTML 模板 | 33 檔 | ~500+ | 0% |
| 模組 JS | 36 檔 | 4,882 | 0% (workflow-main.js 獨占 4,734) |
| 模組 Python | 113 檔 | 7,894 | 0% |
| **合計** | | **~15,000+** | **已完成 ~5%** |

已有 .po 翻譯: 114 條 (上次 extract: 2026-02-07)，僅涵蓋 8 個模板。

---

## 架構決策

| 決策 | 方案 |
|------|------|
| 支援語言 | zh-TW (primary) + en，砍掉 zh-CN / ja |
| msgid 格式 | 繁體中文原文當 key (現行做法) |
| Server-side | Flask-Babel，`_('中文')` |
| Client-side | 新建 `BkI18n` 全域函式 + JSON 翻譯檔 |
| JSON 字典位置 | `backend/app/static/i18n/en.json` (社群可擴展) |
| 模組 i18n | 各模組 `static/modules/<name>/i18n/en.json` |
| DB 動態內容 | 現有 I18nMixin + title_i18n JSONB，不動 |

### JS i18n 機制

```javascript
// backend/app/static/js/i18n.js (全域載入於 base.html)
const BkI18n = {
    _locale: 'zh-TW',
    _dict: {},

    init(locale, coreDict) {
        this._locale = locale;
        this._dict = coreDict || {};
    },

    loadModule(moduleDict) {
        Object.assign(this._dict, moduleDict);
    },

    t(text) {
        if (this._locale === 'zh-TW') return text;
        return this._dict[text] || text;  // fallback 回原文
    }
};

const __ = (text) => BkI18n.t(text);
```

JS 寫法範例:
```javascript
// 改前
alert('確定要刪除嗎？');
// 改後
alert(__('確定要刪除嗎？'));
```

JSON 字典範例 (`en.json`):
```json
{
    "確定要刪除嗎？": "Are you sure you want to delete?",
    "儲存成功": "Saved successfully"
}
```

---

## 執行階段

### Phase 0 - 基礎建設 ✅ (2026-07-12 完成)

- [x] 清理 `i18n.py`: 移除 zh-CN / ja，僅保留 zh-TW + en
- [x] 刪除 `translations/zh_CN/`、`translations/zh_Hans_CN/` 和 `translations/ja/`
- [x] 建立 `backend/app/static/js/i18n.js` (BkI18n + `__()`，含 `{n}` 佔位符插值)
- [x] `base.html` 注入 locale 變數 + 載入 i18n.js + 非 zh-TW 時 fetch 對應 JSON 字典
- [x] 建立空的 `backend/app/static/i18n/en.json`
- [x] 額外：4 處介面語言下拉改由 `supported_languages` 動態產生（users create/edit、admin settings、employee create form）

### Phase 1 - Platform Python 後端 ✅ (2026-07-12 完成)

- [x] `backend/app/web/*.py` 全 33 檔（跳過 dev.py）: flash/jsonify/abort user-facing 字串加 `_()`
- [x] `backend/app/api/*.py` 全 33 檔: error/message 字串加 `_()`，f-string 改 `%(x)s` kwargs 插值
- [x] `pybabel extract` + `update` + 翻譯 en/messages.po（832 條全數翻譯，含修正 75 條錯誤 fuzzy 配對）+ `compile`
- 刻意跳過（包裹會壞邏輯或屬資料值）：`_ss_packages.py` 版本狀態字串（有字面比較）、`security_center.py`「未知用戶」（與 DB audit details 成對比較）、audit log、email 主旨/內文、DB seed 資料、模組層級 label dicts（留待後續 Phase 以 `_l()` 統一處理）

### Phase 2 - Platform HTML 模板 ✅ (2026-07-12 完成)

- [x] 137 個模板逐一包裹 `_()`（跳過 dev/ 與 test 頁；`_methods.html` 純 JS partial 屬 Phase 3）
- [x] extract 後 msgid 832 → 2,529，新增 1,698 條翻譯（含修正 475 條錯誤 fuzzy 配對）+ compile
- [x] 冒煙測試：en 用戶模板渲染英文、zh-TW 不受影響
- 註：頁面上殘留中文有兩類且皆屬預期 — (1) Alpine x-text JS 表達式（Phase 3）、(2) 選單標題來自 DB title_i18n 動態資料（不在程式 i18n 範圍）

### Phase 3 - Platform JS ✅ (2026-07-12 完成)

- [x] 靜態 JS 52 檔 + 模板 `<script>`/`_methods.html` partial/Alpine 表達式，user-facing 字串改用 `__()`
- [x] `en.json` 497 條字典翻譯完成
- [x] 字典載入改為阻塞式路由 `/i18n/<locale>.js`（main.py `i18n_dict_js`），避免 Alpine 渲染搶先於 async fetch
- [x] 實測：en 模式選單管理頁按鈕與 JS 動態訊息（Position reset）皆英文
- 修復附帶問題：msgid 裸 `%` 造成 500（flask_babel 一律做 % 插值，settings.html 改 `%%`）、`selectattr('contains')` 缺自訂 test（既有 bug，app 註冊 `contains`）、「未知網域」跨層字串比對改 `org_unknown` 布林旗標、選單標題 title_i18n 回填 72 筆英文
- 待辦：menu_defaults.py（新裝 seed）尚未帶英文選單標題

### Phase 4 - 模組 Python + 模板 ✅ (2026-07-12 完成)

五模組（open_defense、vuln_lifecycle、spec_formulate、nocode_builder、form_workflow）分批完成，
一批一 commit，詳見 `I18N_PHASE45_REPORT.md`。翻譯併入平台主 `.po`。

### Phase 5 - 模組 JS ✅ (2026-07-12 完成)

同上五模組 JS 全量 `__()` 包裹，字典併入 `backend/app/static/i18n/en.json`。

### 收尾驗證 ✅ (2026-07-15 完成)

- [x] extract 全模組後 .po 4,011 條 0 未翻譯 0 fuzzy；en.json 1,328 條無空值
- [x] 全庫掃描 `__()` key 與 en.json 比對：無缺漏
- [x] 修復批次包裹事故殘留：6 處 Jinja `_()` 誤把 Alpine 表達式/HTML 包進 msgid
  （form_center、_form_center_list_view、data_spec_list、workflow_list、field_spec_editor、mappings_list）
- [x] 補漏包字串：form_center/_form_center_list_view 批次簽核 title、mappings_list 3 處 title、
  sync_control placeholder、initial_setup (未設定)
- [x] 修 nocode_builder 三處硬編碼過期前綴 `/bp/` redirect（改 url_for）
- [x] en 語系冒煙測試六模組頁面：殘留 user-facing 中文 0 行

---

## 每 Phase 驗證方式

1. `pybabel extract` + `pybabel update` 確認無遺漏
2. 切換 locale 為 en，目視檢查頁面
3. 確認 fallback: 未翻譯字串顯示中文原文 (不會 broken)

## 工作量

| Phase | 字串數 | 性質 |
|-------|--------|------|
| 0 | 0 | 架構調整 |
| 1 | ~515 | 機械性包裹 + extract |
| 2 | ~800 | 機械性包裹 + extract |
| 3 | ~250 | JS 改寫法 + 填 JSON |
| 4 | ~8,400 | 模組，量最大 |
| 5 | ~5,000 | 模組 JS |

## 未來開發守則

Phase 0 完成後即生效:
- **所有新的 user-facing 字串必須用 `_()`(Python/Jinja2) 或 `__()`(JS)**
- 英文翻譯品質: 正確可讀即可，直譯為主
- 新增頁面時同步更新 .po 和 en.json

---

*最後更新: 2026-07-15（全 Phase 完成並收尾驗證，Issue #3 關閉；技術債移至獨立 Issue 追蹤）*
