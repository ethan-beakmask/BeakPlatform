# i18n Phase 4/5 任務書 — 模組層（codex 執行）

工作目錄：/opt/BeakPlatform-dev/。目標：modules/ 下所有模組的 user-facing 中文字串 i18n 化（zh-TW 原文當 key，en 翻譯）。

## 前情提要（Platform 層已完成，照既有慣例做）

- Python/Jinja2：`from flask_babel import gettext as _`，`_('中文')`，f-string 改 `_('... %(x)s ...', x=v)`
- 前端 JS：全域 `__(text, params)`（i18n.js，base.html 已載入），`__('... {x} ...', {x: v})`
- **flask_babel 地雷**：gettext 一律做 `%` 插值，msgid 含裸 `%` 會 500，必須寫成 `%%`
- **禁止包裹**：logger/console 訊息、註解、寫入 DB 的資料值、email 主旨內文、技術值、參與 `==`/`===` 比較的字串（跳過並記錄）
- 平台詞彙對照與規則詳見 dev-notes/I18N_PLAN.md 與 git log 中 Phase 1~3 的 commit

## 執行步驟（依序，每模組完成後再下一個）

### 步驟 0：機制確認（先做，寫進報告）
1. 盤點 modules/ 下有哪些模組、各模組 Python/模板/JS 的 user-facing 中文字串實際數量（排除註解、log、資料值）
2. 確認 `backend/app/module_loader.py` 是否已支援載入模組自帶 translations（搜 translations 相關程式）。
   - 若支援：模組 .po 放 `modules/<name>/translations/en/LC_MESSAGES/messages.po`
   - 若不支援：模組字串暫時併入平台主 .po（`backend/translations/`），在報告中註明此技術債
3. 模組 JS 字典：確認前端如何為模組頁面載入額外字典（BkI18n.loadModule）。若無現成機制，模組 JS 字串併入平台 `backend/app/static/i18n/en.json`，報告註明

### 步驟 1：逐模組包裹（優先序：open_defense → vuln_lifecycle → spec_formulate → nocode_builder → form_workflow）
- Python：flash/jsonify error/message/abort 訊息包 `_()`
- 模板：HTML 可見文字與 placeholder/title 屬性包 `{{ _('...') }}`；script/Alpine JS 字串包 `__()`
- JS：user-facing 字串包 `__()`
- form_workflow 的 workflow-main.js 極大（先前粗估 4,734 條中文，多數可能是 node 定義等資料值）——先盤點實際 user-facing 數量再動手，資料值一律不包

### 步驟 2：翻譯與編譯
- pybabel extract/update（cd backend && ../venv/bin/pybabel extract -F babel.cfg -k _l -o translations/messages.pot . && ../venv/bin/pybabel update -i translations/messages.pot -d translations -l en）
- 注意 babel.cfg 目前只掃 backend/app，若模組字串要進主 .po 需擴充 babel.cfg 的掃描路徑（[python: ../modules/**.py] 等），改前先驗證 pybabel 接受
- **pybabel update 產生的 fuzzy 配對幾乎全是垃圾，必須逐條重翻並清除 fuzzy flag**
- 翻譯直譯可讀即可；`%(x)s`/`{x}` 佔位符原樣保留
- ../venv/bin/pybabel compile -d translations

### 步驟 3：逐模組驗證
- python3 -m py_compile 所有改過的 .py
- venv/bin/python3 + jinja2.ext.i18n parse 所有改過的模板
- node --check 所有改過的 .js
- sudo systemctl restart beakplatform-dev.service 後，用 curl 冒煙測試該模組主頁面 200（登入方式見 CLAUDE.md「開發測試登入」）

### 步驟 4：報告
寫 `dev-notes/I18N_PHASE45_REPORT.md`：各模組包裹數、翻譯數、跳過案例（檔:行:原因）、技術債清單、驗證結果。

## 紀律
- **不要 git commit / push**——留給人工驗收
- 不要動 backend/app/security/ 下任何檔案
- 不要動 platform 層已完成的檔案（除 babel.cfg、en.json 依步驟 0 判斷需要擴充外）
- DB 是測試資料，可自由測試
