# i18n Phase 4/5 Report

日期: 2026-07-12

## 結論

本輪完成 `open_defense` 模組的 user-facing i18n 包裹、英文翻譯與驗證。其餘模組已完成盤點，但未做全量包裹；原因是 `form_workflow`、`nocode_builder` 等含大量流程節點定義、DB seed/資料值與模板/JS 顯示文字混雜，依任務規則不能以全域機械轉換直接包裹，需分批人工判斷。

## 步驟 0 盤點

模組:

| 模組 | Python 中文 literal | HTML 中文行 | JS 中文行 | 本輪狀態 |
|---|---:|---:|---:|---|
| open_defense | 152 | 89 | 17 | 完成 |
| vuln_lifecycle | 68 | 120 | 23 | 完成 (2d9b8534) |
| spec_formulate | 349 | 166 | 88 | 完成 (915e0973) |
| nocode_builder | 554 | 486 | 462 | 完成 (cf0e7da6) |
| form_workflow | 1667 | 1289 | 2228 | 完成 (bcd10510) |

機制確認:

- `backend/app/module_loader.py` 已支援模組自帶 `translations/<locale>/LC_MESSAGES/messages.po`，但本輪為了沿用既有平台 catalog 驗證流程，將 `open_defense` 暫併入 `backend/translations/`。
- `BkI18n.loadModule()` 已存在，但沒有模組頁面載入模組字典的通用慣例。本輪 `open_defense` JS 字串併入 `backend/app/static/i18n/en.json`。
- `backend/babel.cfg` 已擴充為可搭配額外 input dir 掃描模組。實際使用指令: `cd backend && ../venv/bin/pybabel extract -F babel.cfg -k _l -o translations/messages.pot . ../modules/open_defense`。

## 包裹與翻譯數

`open_defense`:

| 類型 | 包裹數 |
|---|---:|
| Python `_()` occurrences | 57 |
| Template `_()` / `__()` occurrences | 99 |
| Static JS `__()` occurrences | 14 |
| `.po` OpenDefense msgids | 118 |
| `en.json` 新增/確認 JS keys | 18 |

## 跳過案例

- `modules/open_defense/__init__.py`: `MODULE_INFO.display_name`、menu item `name`、permission `name/description` 會同步寫入 DB，屬資料值，未包裹。
- `modules/open_defense/models/*.py`: 模型 docstring、`__repr__`、狀態/欄位技術值非 user-facing，未包裹。
- `modules/open_defense/services/hmac_verifier.py`: 簽章格式與驗證技術錯誤不直接作 UI 文案，未包裹。
- `modules/open_defense/services/expiry_service.py`: `TTL expired auto-unblock (原決策 ...)` 是寫入決策 reason 的資料值，未包裹。
- `modules/open_defense/services/intake_service.py`: `OpenDefense Webhook`、`OpenDefense Event`、`WEBHOOK_OD`、`Published`、狀態值等為資料/技術值，未包裹。
- 其餘四個模組: 本輪僅盤點，未包裹；需另開分批任務處理，避免誤包 node definition、表單 schema、DB seed/同步資料、比較用字串。

## 技術債

- 模組 Python/Jinja 翻譯目前併入平台主 `.po`；長期應改成各模組自帶 translations 並確認 Flask-Babel 在 module_loader 追加路徑後實際載入順序穩定。
- 模組 JS 字典目前併入 `backend/app/static/i18n/en.json`；長期應建立模組頁面統一載入 `/static/modules/<name>/i18n/<locale>.json` 並呼叫 `BkI18n.loadModule()`。
- `babel.cfg` 若要掃所有模組，需要調整 extract 指令加入對應 input dirs，或改成 repo root 執行的設定。

## 驗證結果

- `../venv/bin/pybabel compile -d translations`: pass
- `python3 -m py_compile` for all `modules/open_defense/**/*.py`: pass
- `node --check` for all `modules/open_defense/static/modules/open_defense/js/*.js`: pass
- Jinja parse with `jinja2.ext.i18n` for all OpenDefense templates: pass
- `sudo systemctl restart beakplatform-dev.service`: active
- curl login using CLAUDE.md JSON flow: success
- Smoke pages:
  - `/beakplatform/open-defense/dashboard`: 200
  - `/beakplatform/open-defense/decisions`: 200
  - `/beakplatform/open-defense/intake-keys`: 200
  - `/beakplatform/open-defense/service-accounts`: 200

## 分批完成記錄 (2026-07-12)

四模組已於同日分批完成，一批一 commit。各批跳過案例與驗證細節見 commit message 與 /opt/tmp/ 下 codex 報告（nb_i18n_codex_report.md、fw_i18n_codex_a_report.md、fw_i18n_codex_b_report.md、fw_i18n_js_skips.tsv）。

新增技術債：
- 公開 Portal（nocode_builder 的 portal_login / portal_register / portal_public 與 portal_auth_service）未包裹——外部訪客語系機制未定義，需另案設計。
- studio.html / workflow_designer.html / form_designer.html 為獨立模板，已各自補 i18n.js 載入區塊；日後新增獨立模板需記得比照。
