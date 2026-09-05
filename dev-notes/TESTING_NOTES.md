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
   這類**環境訊息**（前者＝該測試沒經 `rbac_seed` 種出廠權限定義，見下方 PF-34 段）
3. 都不是才當作功能回歸，用 `git stash` 比對改動前後

**基準不寫死數字**（測試會持續新增，寫死的通過數必然腐爛而誤導）。
判斷有無退步的做法：**動工前先跑一次完整 `tests/` 記下當時的數字**，改完再跑一次比對。
完整跑約 25 分鐘（2026-09-06 實測 1481 秒，1111 個測試、乾淨測試庫；2026-08-28 的 530 秒
是六百多個測試時的數字，已過時）。**全量前先重建測試庫**：`drop_all()` 不 VACUUM，
跑完一次全量就從 7.5 MB 膨脹到 71 MB，膨脹的庫上再跑一次全量要 42 分鐘
（2026-09-06 同一份程式對照，`/opt/tmp/verify/20260906-pf34.log`）。重建指令見上方。

**全量在 Claude Code session 裡怎麼跑**（2026-09-06 定型）：harness 會以「記憶體不足」
收掉背景等待迴圈（知識庫 #5397；實際可用記憶體 7 GB 也照收）。做法：
`nohup bash scripts/run_tests.sh -q > /opt/tmp/verify/<日期>-<主題>.log 2>&1 &` 起 pytest
（nohup 起的進程不受影響），再用 Monitor 工具跑
`while kill -0 <PID> 2>/dev/null; do sleep 60; done; tail -3 <log>` 等結尾。
判斷「有沒有 pytest 在跑」用 `ps -eo pid,etimes,args | grep "[v]env/bin/python -m pytest"`，
不要 `pgrep -f pytest`——自己 echo 的訊息裡含 pytest 字樣就會自我匹配（2026-09-06 踩到）。

以下兩個非綠是**長期已知、成因明確**，不列入退步：

| 項目 | 狀態 | 成因 |
|---|---|---|
| `test_od_protected_targets.py`（2 個 error） | error | **只在完整跑時出現，單獨跑該檔 56 passed** —— 是測試間污染，不是功能回歸。2026-08-20 實測確認（`/opt/tmp/verify/20260820-full-tests.log`）。看到它不要追功能，照上面歸因順序第 1 條處理即可 |
| `test_e2e_portal_cancel.py` | skipped | **永久 skip，重啟服務也救不回來**。它寫死 `PAGE_SC = "FORMTEST00000000000001"`，該驗收頁 2026-08-03 隨全面清除消失，測試在 line 87 就 skip。它另外掛 `pytest.mark.e2e`、服務沒起來也會 skip（line 238），但目前**先卡在找不到頁面**。要恢復必須重建驗收頁並改寫死的常數 |

**`admin_client` 自帶出廠權限定義（PF-34，2026-09-06 解決）**：conftest 的 `rbac_seed` fixture
呼叫 `seed_system_permissions()` 種入 `DEFAULT_PERMISSIONS`，`admin_client` 依賴它。
只種**定義**、不種角色與指派——ORG_ADMIN 的 bypass 只要定義存在就過（`PermissionService.check()`
先查定義、查不到就 False，bypass 在下一步），EMPLOYEE 型測試要自己建 Role／RolePermission／
UserRoleAssignment。2026-09-06 之前 `test_admin_required_for_admin` 因此長期 403，
而另外四個檔各自手種一份 `Permission(...)` 繞過它，同一個問題被解了五次。四件事：

- 測試裡**不要再 `Permission(...)` 手種出廠碼**（`user:read`、`work_schedule:read` 這類），
  會撞 `permissions.code` 唯一鍵（`UniqueViolation`）。已清掉 `test_calendar_projection` /
  `test_delegations_prefill` / `test_job_families_guards` / `test_users_position_display` 的複本。
  模組專屬碼（如 `test_portal_file_stage_a` 的 `nocode_builder.manage`）不在
  `DEFAULT_PERMISSIONS`，照舊手種
- 沒用 `admin_client` 但需要定義存在的測試，自己把 `rbac_seed` 加進參數
- 刻意不掛在 `app` fixture 自動種：`test_permission_defaults.py` 斷言「第一次 seed 建出全部筆數」，
  自動種了它會變 0
- `PermissionService._permission_cache` 是類別層級、跨測試存活，fixture 前後都 `clear_cache()`；
  自己手種任何 Permission 的測試也要清，否則上一個測試的物件會漂進來

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

## chrome-devtools MCP 掛掉時的瀏覽器驗收備援（2026-09-02 實證）

chrome-devtools MCP 連不上（VM 重開後常見）時，**不必放棄 VERIFY-01 的瀏覽器驗收**：
直接用專案的 Playwright 寫拋棄式 `.mjs` 腳本驅動。要點：

- 腳本要放在 repo 根目錄下執行（ESM 解析靠 node_modules 向上尋找，
  `NODE_PATH` 對 ESM 無效），驗完移出，**不要留著被 `git add -A` 收進去**
- 登入用 `ctx.request.post('<BASE>/auth/login', {data:{account, password}})`，
  session cookie 自動進 context（dev 機另有 quick-login 可用）
- 抓 JS 錯誤掛 `page.on('pageerror')` ＋ `page.on('console')` 兩個都要
- **Alpine 壓縮版的錯誤堆疊看不出出錯元素**：用
  `page.route('**/vendor/alpine.min.js*', ...)` 攔截改餵同版 `alpinejs@<版本>/dist/cdn.js`
  非壓縮版，console 會多印出錯的 expression 與 Duplicate key 警告
  （2026-09-02 就是這樣定位到簽核 modal 的 x-for key bug，commit 767b1955）
- 可見性判定沿用 VERIFY-01 規則：fixed 定位元素（`.fc-modal` 等）
  `offsetParent` 恆為 null，要用 `getComputedStyle().display` + `getBoundingClientRect()`
- flatpickr 接管後原生 input 會變 `type="hidden"`，點欄位要選
  `.formio-component-datetime input:not([type=hidden])`

範本腳本留存：session scratchpad 的 `repro_approval.mjs` / `.tmp-fill.mjs`
（拋棄式，邏輯照上面要點重寫即可）。
