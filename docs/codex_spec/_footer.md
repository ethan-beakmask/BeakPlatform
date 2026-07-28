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
# 相關測試（基準 155 passed，不得退步）
cd /opt/BeakPlatform-dev/backend && ../venv/bin/python -m pytest \
  tests/test_pageir_*.py tests/test_portal_*.py tests/test_sitemap_access_matrix.py -q
```

**跑完整 `pytest tests/` 會有 13 個既有 error**（測試用 SQLite 但平台有 PostgreSQL
JSONB 欄位），與任何變更無關，不要試圖修。只跑相關測試檔。

### 不要做的事

- **不要為了讓自己的 grep 或檢查通過而拆字串**
  （例：把 `'/api/x/pages/'` 拆成 `'/api/x' + '/pages/'` 只為避開掃描）
- **不要留下無人引用的死碼**（改了函式簽名就把舊版刪掉）
- **不要只刪不補 manifest**：`docs/manifests/` 有檔案清單，
  刪檔要移除條目，加檔也要加條目，**兩個方向都要做**
- 不要修改 `docs/manifests/security-core.yaml` 列出的安全核心檔案
- 不要改動與任務無關的既有行為（尤其是「順手優化」）
- 不要新增任務範圍外的檔案

### 完成後回報

簡述：改了哪些檔案、新增/更名的函式清單、既有行為如何確保不受影響、
自我驗證的實際輸出。

---

**注意**：Python / 模板變更**不會自動重載**，驗證前若需啟動服務，
正式管道是 `sudo systemctl restart beakplatform-dev.service`。
（若你只做靜態檢查則不需要。）
