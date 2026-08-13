## 交付要求（每次派工都適用）

### 自我驗證（你必須實際執行，不是宣稱）

```bash
cd /opt/BeakPlatform-dev
# 改過 JS
node --check <改過的每一支 .js>
# 改過 Python
cd backend && ../venv/bin/python -c "import app; print('import ok')"
# 改過 JSON（schema 等）
python3 -c "import json; json.load(open('<path>'))"
# 相關測試：一律經由 run_tests.sh（會把 DATABASE_URL 指向拋棄式 beakplatform_test）
bash scripts/run_tests.sh tests/test_pageir_*.py tests/test_portal_*.py -q   # 依任務挑相關檔
# 全量基準（2026-08-05）：382 passed / 1 failed / 1 skipped
#   1 failed = test_admin_required_for_admin（測試庫缺 RBAC seed，已知，非你造成）
#   1 skipped = test_e2e_portal_cancel.py（需實跑服務，掛 pytest.mark.e2e，不在基準內）
```

**禁止自己 `source .env` 之後直接叫 pytest**——`.env` 的 DATABASE_URL 指向開發庫，
測試收尾的 `db.drop_all()` 會打在開發資料庫上。必須走 `scripts/run_tests.sh`。
跑出基準以外的失敗時先重跑一次排除測試殘留，不要直接當成自己改壞。

### 使用者要點擊的東西，驗收必須用瀏覽器

**只要變更涉及連結、按鈕、select 的初次渲染值，curl 驗完還不算完成，
必須用 chrome-devtools 實際載入頁面並點一次。**

curl 對這三類有結構性盲區：

- **連結**：用 curl 測時是自己帶完整路徑，永遠測不出程式組出的網址少了
  nginx 的 `/beakplatform` 前綴（Page IR 的排序連結從第一版就是壞的，
  歷來都用 curl 驗收，直到有人真的點過表頭才發現）
- **select 初次渲染**：漏 `:selected` 時 HTML 原始碼看起來正常，
  要渲染後才知道顯示的是第一個選項
- **按鈕**：`BkCaps.can()` 漏注入 `__PAGE_CAPS` 時按鈕照樣渲染出來，
  點下去沒反應且 console 不報錯

若你的環境無法操作瀏覽器，**在回報中明確列出「哪些互動元素只做了 curl 驗證、
需要人工在瀏覽器點過」**，不要當成已驗收。

### 不要做的事

- **不要為了讓自己的 grep 或檢查通過而拆字串**
  （例：把 `'/api/x/pages/'` 拆成 `'/api/x' + '/pages/'` 只為避開掃描）
- **不要留下無人引用的死碼**（改了函式簽名就把舊版刪掉）
- **不要只刪不補 manifest**：`dev-notes/manifests/` 有檔案清單，
  刪檔要移除條目，加檔也要加條目，**兩個方向都要做**
- 不要修改 `dev-notes/manifests/security-core.yaml` 列出的安全核心檔案
- 不要改動與任務無關的既有行為（尤其是「順手優化」）
- 不要新增任務範圍外的檔案

### 完成後回報

簡述：改了哪些檔案、新增/更名的函式清單、既有行為如何確保不受影響、
自我驗證的實際輸出。

---

**注意**：Python / 模板變更**不會自動重載**，驗證前若需啟動服務，
正式管道是 `sudo systemctl restart beakplatform-dev.service`。
（若你只做靜態檢查則不需要。）
