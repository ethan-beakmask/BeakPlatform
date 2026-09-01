# 測試備忘（pytest / test_client / Playwright）

> 2026-08-30 從 `CLAUDE.md` 移出（三個小節共 147 行）。
> **跑測試前只要記得一件事：一律用 `bash scripts/run_tests.sh`**，
> 那條連同已知非綠基準仍留在 `CLAUDE.md`。其餘細節在這裡。

---

## 跑測試一律用 `scripts/run_tests.sh`（2026-08-05 起，強制）

```bash
cd /opt/BeakPlatform-dev
bash scripts/run_tests.sh                                  # 全部
bash scripts/run_tests.sh tests/test_pageir_shared_menu.py -q
bash scripts/run_tests.sh -k menu -q
```

**不要自己 `source .env` 之後直接叫 pytest。**
`TestingConfig` 的資料庫是 `os.getenv('DATABASE_URL', 'sqlite:///:memory:')`，
而 `.env` 的 `DATABASE_URL` 指向**開發庫 `beakplatform_dev`**；
`conftest.py` 與另外三個測試檔的 `app` fixture 收尾都會呼叫 **`db.drop_all()`**。
也就是說照舊寫法跑測試 ＝ 對開發資料庫 create_all + drop_all。
在 2026-08-05 之前一直沒毀掉資料，**只是因為 `drop_all()` 被 FK 相依擋下來而拋例外**
（那批 `ERROR at teardown` 就是它），不是有防護。

`scripts/run_tests.sh` 會在 source .env **之後**把 `DATABASE_URL` 覆寫成
拋棄式的 `beakplatform_test`。另有一道防呆在
`backend/tests/conftest.py::pytest_configure`：庫名不是 `_test` 結尾且非 sqlite
就直接 `pytest.exit`（放在 `pytest_configure` 而不是 app fixture，因為
`test_smoke.py` / `test_page_template_instantiate.py` / `test_page_template_scope.py`
各自定義的 app fixture 會覆蓋 conftest 的版本）。

測試庫不存在時（`beakplatform` 帳號沒有 CREATEDB 權限）：
```bash
sudo -u postgres createdb -O beakplatform beakplatform_test
```
本機 `ethan` 可直接 sudo、不需密碼。連線參數就是上面「資料庫資訊」那組
（`localhost:5432 / beakplatform / postgres123`）；`run_tests.sh` 可用
`TEST_DB_NAME` / `DB_USER` / `DB_PASS` / `DB_HOST` 環境變數覆寫。

**測試庫可以一直重複使用、不必每次重建**——每個 app fixture 都是
`create_all()` 開場、`drop_all()` 收尾。反過來說**不要拿它存任何想留的東西**。

**但測試庫一次只能有一個使用者**（2026-08-28 踩到）。`run_tests.sh` 跑到一半時，
另外對 `beakplatform_test` 跑任何 `create_all()` / `drop_all()` 的腳本，兩邊會互相
等鎖；把那支腳本 timeout kill 掉之後，測試庫留下**半成品 schema**，
接下來的測試在 `db.create_all()` 撞

```
psycopg2.errors.UniqueViolation: duplicate key value violates unique constraint
"pg_type_typname_nsp_index"  DETAIL: Key (typname, typnamespace)=(conglomerates, 2200)
```

症狀是**多出一條基準以外的 error，看起來像自己改壞了**。處置：

```bash
sudo -u postgres dropdb --if-exists --force beakplatform_test
sudo -u postgres createdb -O beakplatform beakplatform_test
```

要在測試庫上跑自己的驗證腳本，等 `run_tests.sh` 結束再跑；跑完記得重建測試庫，
不要留 schema 給下一輪測試。（`drop_all()` 在有資料的庫上會卡很久，
用 dropdb 比等它快。）

**跑出基準以外的失敗時，歸因順序**（照這個順序查，不要跳）：
1. 先看是不是**測試資料殘留**——`bash scripts/run_tests.sh -q` 重跑一次，
   結果不同就是殘留或測試間互相污染，不是功能回歸
2. 再看 log 有沒有 `Unknown permission code` / `Modules already loaded`
   這類**環境訊息**（前者是測試庫缺 seed，見 PF-34）
3. 都不是才當作功能回歸，用 `git stash` 比對改動前後

**基準不寫死數字**（測試會持續新增，寫死的通過數必然腐爛而誤導）。
判斷有無退步的做法：**動工前先跑一次完整 `tests/` 記下當時的數字**，改完再跑一次比對。
完整跑約 9 分鐘（2026-08-28 實測 530 秒；舊文寫 4 分鐘已過時）。以下兩個非綠是**長期已知、成因明確**，不列入退步：

| 項目 | 狀態 | 成因 |
|---|---|---|
| `test_auth_interceptor.py::TestAuthDecorators::test_admin_required_for_admin` | failed | 測試庫是 `db.create_all()` 建的空表、**沒有 RBAC seed**（log 印 `Unknown permission code: user:read`），拿到 403 而非 200。要修就補 permission → role → `user_role_assignments` 整條鏈，權威清單在 `scripts/migrations/legacy/075_seed_resource_crud_permissions.py`（待辦 **PF-34**） |
| `test_od_protected_targets.py`（2 個 error） | error | **只在完整跑時出現，單獨跑該檔 56 passed** —— 是測試間污染，不是功能回歸。2026-08-20 實測確認（`/opt/tmp/verify/20260820-full-tests.log`）。看到它不要追功能，照上面歸因順序第 1 條處理即可 |
| `test_e2e_portal_cancel.py` | skipped | **永久 skip，重啟服務也救不回來**。它寫死 `PAGE_SC = "FORMTEST00000000000001"`，該驗收頁 2026-08-03 隨全面清除消失，測試在 line 87 就 skip。它另外掛 `pytest.mark.e2e`、服務沒起來也會 skip（line 238），但目前**先卡在找不到頁面**。要恢復必須重建驗收頁並改寫死的常數 |

寫「已知問題不要修」時務必連**成因與判別方式**一起寫，否則它會保護錯的東西——
先前那句「13 個 error 是 SQLite JSONB 問題，不要修」只在無 `DATABASE_URL` 時成立，
卻長期覆蓋掉「撞開發庫殘留」這組完全不同的錯誤，改用測試庫後其中
`tests/test_page_template_instantiate.py` 直接變成 14 passed。

## 用 Flask `test_client` 寫測試時的三個坑（2026-08-23 逐一試誤才弄對）

**一、URL 必須自己帶 `/beakplatform` 前綴。**
`create_app()` 用 `DispatcherMiddleware` 把 app 掛在 `APP_PREFIX`（預設
`/beakplatform`）底下，但 `app.url_map` 內的 rule **不含**這個前綴。
所以 `client.get('/api/users/')` 一律 404，要寫 `client.get('/beakplatform/api/users/')`。
症狀是「整批測試全 404、耗時 0 秒」，看起來像路由沒註冊。

```python
resp = client.get('/beakplatform' + rule)      # 對
resp = client.get(rule)                        # 錯，恆 404
```

**二、`app.module_loader.module_loader` 是進程層級單例，
第二個以後建立的 app 不會再註冊模組 blueprint。**
`load_modules()` 看 `self._loaded` 旗標，第二次直接
`logger.warning("Modules already loaded, skipping")` 就回傳。實測：

| 情況 | url_map 路由數 |
|---|---|
| 進程內第一個 app | 859 |
| 第二個以後 | **449**（少了 410 條模組路由） |
| 手動把 `_loaded` 重設為 False 再建 | 732（**救不回來**，部分模組載入會失敗） |

後果是**同一個測試單獨跑會綠、跟其他測試一起跑就紅**，而症狀看起來像
「資料沒同步」而不是「app 不完整」。要在測試裡拿到完整 url_map，
唯一可靠的做法是**開獨立進程**（`subprocess`），
範例見 `backend/tests/test_route_guard_table.py`。

**三、`test_client` 打 `/dev/quick-login` 會 404**（原因未查明，2026-08-23 實測）。
需要真實登入的測試改用 `requests` 打執行中的服務
（`http://192.168.0.16:7000/beakplatform`），單次請求約 28ms，
816 次請求 23 秒——全矩陣測試的成本完全可接受。

## 瀏覽器互動的 E2E：Playwright（2026-08-12 起）

pytest 之外另有一組 **Playwright E2E**，測的是 curl 與 pytest 都測不到的東西
（連結前綴、按鈕可見性、點擊後有沒有發某支 API、console 有沒有紅字）。

```bash
cd /opt/BeakPlatform-dev
bash scripts/run_e2e.sh                    # 跑全部，輸出自動 tee 到 /opt/tmp/verify/
bash scripts/run_e2e.sh --headed           # 讓人看得到瀏覽器
bash scripts/run_e2e.sh -g "A. 點不可簽核"  # 其餘參數原樣傳給 npx playwright test
```

- 測試在 `tests/e2e/`（**不是** `backend/tests/`，那是 pytest 的領地）
- **需要服務在跑**（走 nginx `http://192.168.0.16:7000/beakplatform`），
  但不需要測試資料庫——它打的是開發庫，且**只讀不寫**
- Playwright 1.62.1 裝在 repo 根（`package.json` + `node_modules/`，均已 gitignore）
- 登入走 `/dev/quick-login`（`tests/e2e/helpers/login.js`），免密碼免 CSRF
- 現有覆蓋：`od-pf79.spec.js`（資安案件處置中心的可簽核／不可簽核兩條路徑、
  OD 四頁副標、intake-keys 的 nginx 前綴）

**寫新 E2E 時的三條硬規則**（AI 派工時要逐條貼進 spec，否則必漏）：

1. **禁止 `page.evaluate(() => el.click())`**，一律 `locator.click()`。
   後者會先跑 actionability checks（visible / stable 連兩幀 box 相同 / enabled /
   receives events 的 hit-test），DOM click 把這層整個拿掉，
   被 overlay 蓋住的按鈕照樣觸發＝測不出使用者點不點得到
2. **禁止 `waitForTimeout` 或任何固定 sleep**，用 web-first assertion 與 `waitForResponse`
3. **禁止寫死 secure_code / 案件編號 / 密碼**，識別碼一律從 API 動態挑；
   資料前提不成立時 `test.skip()` 並印中文說明，不要讓它變紅、也不要靜默 pass

**新測試第一次就全綠時，必須做一次 mutation 驗證**：把被測的修復暫時改回壞掉的樣子，
確認測試會紅。恆真斷言（locator 打錯 → count 恆 0、監聽器沒掛上 → 陣列恆空）
會穩定通過而什麼都沒驗，**讀起來像有保障，比沒測更危險**。
PF-79 這組就是這樣驗的（記錄在 `/opt/tmp/verify/20260812-e2e-od-pf79.log`）。
