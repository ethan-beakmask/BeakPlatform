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

### Phase 2 - Platform HTML 模板

- [ ] 115 個未覆蓋模板逐一包裹 `_()`
- [ ] 再次 extract + 翻譯 .po + compile

### Phase 3 - Platform JS

- [ ] 44 檔，~250 user-facing 字串改用 `__()`
- [ ] 對應填入 `backend/app/static/i18n/en.json`

### Phase 4 - 模組 Python + 模板

依模組分批:

- [ ] **4a**: form_workflow Python (flash/error) + 模板 `_()`
- [ ] **4b**: nocode_builder Python + 模板
- [ ] **4c**: spec_formulate Python + 模板
- [ ] 各模組 extract + 翻譯 + 建立模組 `i18n/en.json`

### Phase 5 - 模組 JS

- [ ] **5a**: form_workflow JS (workflow-main.js 4,734 + 其他)
- [ ] **5b**: nocode_builder JS (studio.js 等)
- [ ] **5c**: spec_formulate JS

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

*最後更新: 2026-07-12（Phase 0 + Phase 1 完成，「未來開發守則」已生效）*
