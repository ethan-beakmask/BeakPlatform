# 交接：NoCode 子系統刪除不級聯 → 孤兒頁面仍可從平台開啟

建立：2026-07-31。完整脈絡與決策過程在 BeakBroodNest **#4939**（`note_get(4939)`），
本檔是可直接動工的版本。前置背景：#4913（NoCode 收尾）、#4904（六元件完成）。

## 一句話

刪掉子系統後，它底下的頁面在**平台側**還開得起來；根因是刪除不級聯。
**2026-07-31 傍晚三段修法已全部完成並實測通過**（詳見文末「完成紀錄」）。
以下「待做的三段」保留為設計說明，描述的是現在程式碼實際採用的判定與作法。

## 風險等級（先講清楚，避免誤判優先級）

- **portal 公開路徑不受影響**：`modules/nocode_builder/web/portal_public.py`
  的 `_resolve_sub_system()` 查子系統時已帶 `is_deleted=False`，
  並要求 `status='published'`，子系統一刪整條 `/public/portal/...` 立刻 404
- 沒擋的是**平台側**兩個入口，兩者都需要登入 + 模組權限：
  - `backend/app/web/main.py:247` `published_page()` —— `/p/<page_layout_sc>`
    只檢查頁面自身 `is_deleted` 與 `status='published'`
  - `modules/nocode_builder/web/__init__.py:42` `ir_designer()` ——
    只掛 `@module_access_required('nocode_builder')`，拿到頁面 sc 就能開

→ 是「內部殘留的可見性問題」，不是對外破口。

## 待做的三段（建議一次做完）

### 1. 存取層 fail-closed

上述兩個入口都要回頭確認「這個頁面所屬的子系統存活且未刪」，不成立一律 **404**
（不洩漏存在與否，與 portal 既有判定一致）。

**判定必須是雙路徑 OR，只看 site map 會誤擋 portal 頁：**

```
存活 = (有存活 dc_site_map_nodes 指向 且 該節點的子系統存活)
    OR (有存活 dc_sub_system_pages 掛載 且 該子系統存活)
```

另有一類頁面**兩條都沒有**（純平台 IR 頁，不屬於任何子系統）——
那種不該被誤擋，判定要寫成「**有掛在某個子系統下 → 該子系統必須存活**」，
而不是「一定要查得到子系統」。

**判定只看「存活」的關聯，不要去追已軟刪的關聯來推論身世。**
會有「這頁原本掛在已刪子系統下，關聯也被一起軟刪了」與「本來就是純平台頁」
長得一樣的情形——刻意不分辨：存取層對兩者都放行（它們都不屬於任何活著的子系統，
沒有洩漏子系統資料的問題），真正該把前者收掉的是清理腳本，不是存取層。
這是取捨，不是疏漏；要改成更嚴格之前先想清楚純平台 IR 頁會不會被誤殺。

### 2. 刪除級聯

刪子系統時一併軟刪其 `dc_site_map_nodes`、`dc_sub_system_pages`，以及**僅由這些
節點/掛載關聯、沒有其他存活關聯**的 `dc_page_layouts`。同樣用上面的雙路徑判定。

**要改的是 service 不是 API**：
`modules/nocode_builder/api/sub_system_api.py:189` 的
`DELETE /api/nocode-builder/sub-systems/<secure_code>`（`@csrf.exempt`
+ `@admin_required`）只是委派，實際邏輯在
`modules/nocode_builder/services/project_service.py:145` `delete_project()`。

該函式目前做的事：停用關聯選單 → `delete_portal_path()` 刪 portal 路徑 →
撤銷開發者 `nocode_builder` 權限 → `ResourceGateway.delete(ss, soft=True)` →
`cleanup_portal_sqlite()` 清 SQLite 檔。
**它的 docstring 寫「完整清理」但從來沒碰 `dc_site_map_nodes` /
`dc_sub_system_pages` / `dc_page_layouts`** —— 這就是孤兒的來源，級聯加在這裡。

軟刪一律走 `ResourceGateway.delete(obj, check_permission=False, soft=True)`
（沿用既有慣例，不要自己寫 `UPDATE ... SET is_deleted=true`；
`deleted_at` 等欄位由 gateway 統一處理）。

### 3. 清理腳本

**檔名就用 `scripts/cleanup_orphan_nocode_pages.py`**，比照
`scripts/add_portal_user_ref.py` 的既有寫法：無參數顯示中文說明、
`--dry-run` / `--apply` 二選一、冪等、可重複執行。
（2026-07-31 已用手動 SQL 清過一輪，腳本是為了日後重複發生時可用。）

清理範圍就是下面「已經做掉的事」表格裡的 A / B / C 三類，**外加**
`dc_sub_system_pages` 指向已刪或不存在子系統的掛載列（本輪沒查、也沒清，
新腳本要一併涵蓋）。B 類務必用雙路徑判定，別重蹈下面「踩過的坑」。

## 2026-07-31 已經做掉的事（不要重做）

清掉三類孤兒（全部軟刪，可還原）：

| 類型 | 內容 |
|---|---|
| A：節點掛在**已軟刪**子系統下 | 35 節點 + 34 頁面 |
| B：頁面**無 site map 節點**指向 | 12 頁面 |
| C：節點的 `sub_system_secure_code` 在 `dc_sub_systems` **根本不存在** | 19 節點 + 17 頁面 |

C 類是驗證時才發現的——原本的清單查詢用 `JOIN dc_sub_systems`，整批漏掉。

清完狀態：**存活節點 9、存活頁面 11**，三類孤兒皆 0。
備份（清理前的兩張表 `pg_dump --data-only`，要還原就用它）：
**`/opt/tmp/beakplatform_backup/backup_sitemap_pages_20260731.sql`**
清單 CSV 給了用戶兩份，在 `/mnt/smb/BeakPlatform_孤兒頁面清單_20260731.csv`
與 `/mnt/smb/BeakPlatform_孤兒清單C_子系統不存在_20260731.csv`。

### 踩過的坑（同樣的錯不要再犯一次）

B 類判定「沒有 site map 節點指向 = 游離頁面」**是錯的**，
誤刪了兩個 published 驗收頁 `FORMTEST00000000000001`（Form 送件 E2E）與
`qiHMpMCul-1KGxhU4Q7Trd`（主細表驗收）——它們只有 `dc_sub_system_pages` 掛載。
前者是 `backend/tests/test_e2e_portal_cancel.py` 的依賴，
**刪掉會讓 E2E 靜默 skip 而不是報錯**。已還原並實跑 E2E 確認無損。

## 可執行指令（本 session 實跑成功過，照抄；不要憑印象改寫）

DB 連線（本機開發環境，密碼見專案 CLAUDE.md「資料庫資訊」）：

```bash
PGPASSWORD=postgres123 psql -h localhost -U beakplatform -d beakplatform_dev
```

### 動工前先確認孤兒現況

```sql
SELECT '存活節點總數', count(*) FROM dc_site_map_nodes WHERE is_deleted=false
UNION ALL SELECT '  其中子系統已刪', count(*) FROM dc_site_map_nodes n
  JOIN dc_sub_systems ss ON ss.secure_code=n.sub_system_secure_code
  WHERE n.is_deleted=false AND ss.is_deleted=true
UNION ALL SELECT '  其中子系統不存在', count(*) FROM dc_site_map_nodes n
  WHERE n.is_deleted=false
    AND NOT EXISTS (SELECT 1 FROM dc_sub_systems ss WHERE ss.secure_code=n.sub_system_secure_code)
UNION ALL SELECT '存活頁面總數', count(*) FROM dc_page_layouts WHERE is_deleted=false;
-- 2026-07-31 清理後應為 9 / 0 / 0 / 11
```

### 頁面的雙路徑關聯檢視（判斷該不該擋或刪，一定要看這兩欄）

```sql
SELECT p.secure_code, p.name, p.status,
  (SELECT count(*) FROM dc_site_map_nodes n
     WHERE n.page_layout_secure_code=p.secure_code AND n.is_deleted=false) AS 節點,
  (SELECT count(*) FROM dc_sub_system_pages sp
     WHERE sp.page_layout_secure_code=p.secure_code AND sp.is_deleted=false) AS 掛載
FROM dc_page_layouts p WHERE p.is_deleted=false ORDER BY p.name;
```

### 改資料前必做備份

```bash
PGPASSWORD=postgres123 pg_dump -h localhost -U beakplatform -d beakplatform_dev \
  -t dc_site_map_nodes -t dc_page_layouts --data-only -f backup_sitemap_pages.sql
```

### 誤刪還原（實測還原成功過）

```sql
UPDATE dc_page_layouts p SET is_deleted=false, updated_at=now()
WHERE p.is_deleted=true
  AND EXISTS (SELECT 1 FROM dc_sub_system_pages sp
              JOIN dc_sub_systems ss ON ss.secure_code=sp.sub_system_secure_code
              WHERE sp.page_layout_secure_code=p.secure_code
                AND sp.is_deleted=false AND ss.is_deleted=false);
```

### 產清單 CSV 給用戶

**本 session 用的完整查詢已存檔，直接拿去改就好**：
`/opt/tmp/beakplatform_backup/orphans_report_20260731.sql`
（A 類 + B 類的 UNION ALL，含子系統/節點/頁面欄位與設計器網址）。

`\copy` 不吃多行 SQL，要用 `COPY ( ... ) TO STDOUT WITH CSV HEADER;` 寫進 .sql 檔再：

```bash
PGPASSWORD=postgres123 psql -h localhost -U beakplatform -d beakplatform_dev \
  -f orphans.sql > orphans.csv
df /mnt/smb                      # 寫 /mnt/smb 前必須確認已掛載
python3 -c "
src=open('orphans.csv',encoding='utf-8').read()
open('/mnt/smb/檔名.csv','w',encoding='utf-8-sig',newline='').write(src)"
# 中文 CSV 一定要 utf-8-sig，否則用戶用 Excel 開會亂碼
```

### 改完必驗

```bash
cd /opt/BeakPlatform-dev/backend
# E2E（需服務在跑，應 1 passed；若變成 skip 表示 FORMTEST 頁被擋掉或刪掉了）
../venv/bin/python -m pytest tests/test_e2e_portal_cancel.py -q
# 基準 248 passed，不得退步
../venv/bin/python -m pytest tests/test_pageir_*.py tests/test_portal_*.py \
  tests/test_sitemap_access_matrix.py tests/test_platform_fixed_filters.py -q
```

存取層是「使用者要點的東西」，依 CLAUDE.md VERIFY-01，curl 驗完**還要**用
chrome-devtools 實際開一次頁面確認。

### 驗收要用哪個帳號（本 session 實際用過的）

平台側兩個入口都需要 `nocode_builder` 模組權限。**用
`admin-ethanyu@beluga.com`**（ORG_ADMIN，secure_code `jIYEQ-_lZMZNBkVy-hijal`），
本 session 用它成功開過工作區與設計器：

```bash
BASE=http://192.168.0.16:7000/beakplatform
curl -s -c cj.txt -X POST "$BASE/dev/quick-login" \
  -H 'Content-Type: application/json' -d '{"user_id":"jIYEQ-_lZMZNBkVy-hijal"}'
curl -s -b cj.txt -o /dev/null -w '%{http_code}\n' "$BASE/p/<page_layout_sc>"
```

瀏覽器驗收走 chrome-devtools MCP：`new_page` 開 `$BASE/dev/quick-login`
→ 點企業 `beluga` → 點 `admin-ethanyu@beluga.com` → 再 `navigate_page` 到目標頁。
（沒有 chrome-devtools 可用時，在回報中明列「哪些互動元素只做了 curl 驗證、
需人工在瀏覽器點過」，不要當成已驗收。）

### 驗證級聯有沒有生效（刪一個子系統來看）

```bash
# 端點 @csrf.exempt + @admin_required，所以不必帶 CSRF token
curl -s -b cj.txt -X DELETE "$BASE/api/nocode-builder/sub-systems/<sub_system_sc>"
# 然後用上面「動工前先確認孤兒現況」那段 SQL 檢查有沒有產生新孤兒（三項應維持 0）
```

**不要拿 `8uopl3mNbDzGDUGAcNQqNe`（匿名問卷-測試公開區子系統）當實驗對象** ——
portal 測試資料、驗收頁與 `test_e2e_portal_cancel.py` 全部依賴它。
拿清單裡其他測試子系統（例如 `999`、`0000`、`FORMGRID`）試。

## 一個尚未釐清的對不上帳

用戶說他已在 UI 把子系統刪到「剩 `nXwTFgUpsJptHhHUiMlpDy` 與
`8uopl3mNbDzGDUGAcNQqNe` 兩個」，但 DB 查 `is_deleted=false` 仍有 **7 個**
（子子子 / 匿名問卷-測試公開區子系統 / test02 / 0000 / 子系統1號 / FORMGRID / 999）。
可能是列表畫面另有過濾條件（status / portal_mode / 權限），也可能是記憶出入。
**動工前先釐清**，免得又對不上帳。

## 環境備忘

本機（`/opt/BeakPlatform-dev` 研發、`/opt/BeakPlatform` 測試）**全部都是測試資料**，
用戶明確說可自由刪除；本系統定位 SaaS，日後要乾淨測試就建一個測試用公司客戶。

---

## 完成紀錄（2026-07-31 傍晚）

### 對不上帳的答案：是租戶隔離，不是 bug

DB 有 7 個存活子系統，但用戶只看到 2 個 —— 那 2 個
（`nXwTFgUpsJptHhHUiMlpDy` test02、`8uopl3mNbDzGDUGAcNQqNe` 匿名問卷）
的 `org_secure_code` 都是 `_9c8TewkRkCBEf3XsUdqeF`（beluga），
另外 5 個屬於別的企業，列表本來就看不到。無需處理。

### 實際落地的程式

| 檔案 | 內容 |
|---|---|
| `modules/nocode_builder/services/page_ownership_service.py`（新） | `get_owner_sub_system_codes()` / `is_page_reachable()`，雙路徑 OR 判定 |
| `backend/app/web/main.py` `published_page()` | `/p/<sc>` 不可達 → 404 |
| `modules/nocode_builder/web/__init__.py` | `ir_designer()`（原本連頁面存不存在都不查）、`ir_designer_preview()` 加判定；`workspace()` 加「子系統存活」判定 |
| `modules/nocode_builder/api/__init__.py` | `GET/PUT /pages/<sc>`、`publish`/`unpublish` 四個端點加判定（否則 UI 擋了、API 照樣讀寫孤兒頁的 IR） |
| `modules/nocode_builder/services/project_service.py` `delete_project()` | 級聯軟刪節點 → 掛載 → `flush()` → 用雙路徑判定決定要不要軟刪頁面 |
| `scripts/cleanup_orphan_nocode_pages.py`（新） | A/B/C 三類 + 孤兒掛載，`--dry-run`/`--apply`，冪等 |

**級聯判定的一個細節**：`is_page_reachable()` 對「零關聯」回 `True`（純平台頁放行），
所以級聯與清理腳本判斷頁面該不該刪時，條件是
`not is_page_reachable(sc) or not get_owner_sub_system_codes(sc)`
—— 後半段才收得掉「關聯剛被級聯刪光、變成零關聯」的頁。

**刻意沒動**：`GET /api/nocode-builder/pages`（列表）仍會列出孤兒頁。
理由是它是選頁器的資料來源，過濾掉的副作用大於效益；孤兒頁的正解是清理腳本。

### 實測（都在本機實跑過）

- 建實驗子系統 `53iLtkX9AIp_c2Ee9Q-pEc` + 兩頁（一頁走 site map 節點、一頁走
  `dc_sub_system_pages` 掛載，兩條路徑都覆蓋）→ 刪除前 `/p/`、設計器、
  `GET /api/.../pages/<sc>`、工作區全部 200
- `DELETE /api/nocode-builder/sub-systems/<sc>` → DB 驗證節點、掛載、**兩頁**皆軟刪；
  上述入口全部變 404（含 `/preview`、`PUT`）
- 再用 SQL 把該子系統的關聯與頁面還原成「頁與關聯存活、子系統已刪」的**孤兒樣態** →
  六個入口仍全部 404，證明存取層 fail-closed 不是只靠「頁面被刪掉」
- 清理腳本 `--dry-run` 抓到 1 節點 + 3 掛載 + 2 頁面（其中兩筆掛載是前一輪沒清的殘留，
  指向的頁面早已軟刪）→ `--apply` 後再跑 `--dry-run` 為 0/0/0（冪等）
- 清理後存活頁面仍是 11 筆、與清理前完全一致（`FORMTEST00000000000001`、
  `qiHMpMCul-1KGxhU4Q7Trd` 沒被誤殺）
- `pytest tests/test_pageir_*.py tests/test_portal_*.py tests/test_sitemap_access_matrix.py
  tests/test_platform_fixed_filters.py -q` → **248 passed**（基準持平）；
  `tests/test_e2e_portal_cancel.py` → **1 passed**
- 瀏覽器（chrome-devtools，`admin-ethanyu@beluga.com`）：test02 工作區 → 點 Site Map
  節點 → 設計器正常載入頁面；改開已刪頁的設計器網址 → 404 頁面

備份（本輪動資料前）：`/opt/tmp/beakplatform_backup/backup_orphan_fix_20260731_1702.sql`
（`dc_site_map_nodes` / `dc_page_layouts` / `dc_sub_system_pages` 三表 data-only）。
