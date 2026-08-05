# Portal 檔案元件規格（Page IR `file_box` widget）

**狀態**：**階段 A 已完成並驗收（2026-08-05）**，階段 B~E 未實作
**日期**：2026-08-05
**關聯**：PF-42（發布快照，上線前應完成）、FILE-01、PF-7（portal 權限模型）

---

## 1. 目標

讓 NoCode 子系統的**末端用戶**（portal 帳號與匿名訪客）能在 portal 頁面上傳與下載檔案，
權限由設計者在 IR 設計器設定。

**不在範圍內**：平台側員工的檔案功能（既有 `BkFileAttachment` 已涵蓋）、
子系統系統級素材（底圖等，走既有 `nc_background`）。

---

## 2. 架構決策（已定案，不要重新討論）

| 決策 | 內容 | 理由 |
|---|---|---|
| 儲存層 | **完全重用 `file_service`**，一行不改 | 加密（AES-256-GCM + 企業金鑰包覆）、SHA-256 完整性、`file_access_logs` 稽核都已成熟，重做必然出新洞 |
| `platform_files` schema | **不動** | 見下 |
| 歸屬與 ACL | 記在**子系統 SQLite**（`portal.db`）新表 | 符合「實體與加密在平台、歸屬與權限在 SQLite」的分工；抽離子系統時搬 SQLite + 檔案目錄即可 |
| `uploader_sc` | portal 上傳者**不寫入**此欄位 | 該欄位語意是平台 `users.secure_code`；塞 `portal:xxx` 前綴會讓 `can_access_file()` 的「上傳者放行」邏輯誤判 |
| 認證 | portal 專用路徑，**不經 Flask-Login** | `/api/files/*` 全是 `@login_required`，portal session 走不進去（實測全 401） |
| 授權 | 接 `portal_permission_service`，**不自行組 SQL** | 該檔是有效權限計算的唯一實作 |
| 下載保護 | 判權後**直接串流**，不做一次性 token | 平台的 token 是純 bearer（實測跨身分可兌換），portal 側請求量小，直接判權更嚴格也更簡單 |
| 匿名上傳 | **禁止**，無例外 | 用戶定案 |

---

## 3. 權限模型

用戶列出的五種檔案流向，**不枚舉成五種類型**，而是由 widget 的四個屬性組合而成：

| 流向 | `upload_by` | `read_scope` | `per_file_acl` | `guest_readable` |
|---|---|---|---|---|
| 設計者 → 全部用戶 | `designer` | `["*"]` | false | false |
| 設計者 → 指定角色/群組 | `designer` | `["<perm_code>"]` | false | false |
| 設計者 → 指定帳號 | `designer` | `[]` | **true** | false |
| 設計者 → 匿名 | `designer` | `[]` | false | **true** |
| 用戶 → 子系統（管理角色可見） | `portal_user` | `["<perm_code>"]` | false | false |
| 用戶 → 匿名 | `portal_user` | `[]` | false | **true** |

### 屬性定義

- **`upload_by`**：`designer`（只有平台側設計者能放檔）／`portal_user`（登入的 portal 帳號能上傳）。
  匿名一律不能上傳。
- **`read_scope`**：權限碼陣列（格式 `resource.action`）。`["*"]` 表示所有**已登入**的 portal 帳號。
  空陣列表示不靠權限碼開放（只靠 ACL 或 guest）。
  判定走 `portal_permission_service` 的有效權限集合，`match_mode` 固定 `any`。
- **`per_file_acl`**：啟用後，設計者可為**個別檔案**指定可讀帳號清單（見 §4 `portal_file_acl`）。
  這是**第三種判定機制**，與權限碼並存：
  **讀取通過 = 權限碼命中 OR 在 ACL 名單內**；但**個人 deny 仍然最優先**（見下）。
- **`guest_readable`**：匿名訪客可讀。**設計者與管理者可隨時關閉，且判定在讀取當下做**
  ——關閉後既有連結立即失效，不可在發連結時就決定。

### 判定順序（fail-closed）

```
1. 子系統 status != 'published'                        → 404
2. 頁面未掛載於該子系統 / 未 published                 → 404
3. widget 不存在或 type != 'file_box'                  → 404
4. 檔案 is_deleted                                     → 404
5. 個人 deny（portal_user_permissions 的 deny）        → 404
6. 上傳者本人（uploader_ref 相符）                     → 放行
7. read_scope 命中有效權限集合                          → 放行
8. per_file_acl 命中（grantee_type = user / role）      → 放行
9. guest_readable 且該 widget 允許匿名                  → 放行
10. 其他                                               → 404
```

**一律回 404，不回 403**——不洩漏檔案是否存在（與 portal 既有慣例一致）。
拒絕原因寫 log（`reason=`），供 `journalctl` 排查。

### 明確不做

- 用戶 → 特定用戶（這不是社群系統）
- 只給自己私用、連管理員都看不到（日記／記帳型應用不存在）
- 因此**上傳者本人可見自己上傳的檔案**是預期行為（第 6 條），不算「私用場景」

### 設計者的可見性

「正式發行後排除設計者」在技術上**做不到**——設計者持有 `nocode_builder.manage`，
可改權限矩陣、改頁面、直接讀 SQLite。實作上只做到**預設不給設計者看**
（UI 不顯示、API 擋、存取寫稽核），這是**營運控制不是安全邊界**，
文件與 UI 都不得暗示它是硬邊界。

---

## 4. SQLite schema（portal.db v3 → v4）

**升級一律加在 `data_source_manager.py::ensure_portal_schema()` 的階梯中**
（`if version < 4: ... PRAGMA user_version = 4`），不要另寫 migration 腳本。

```sql
CREATE TABLE IF NOT EXISTS portal_files (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    secure_code       TEXT NOT NULL UNIQUE,   -- portal 側識別碼，URL 用（22 字元亂數）
    platform_file_sc  TEXT NOT NULL,          -- 對應 platform_files.secure_code（實體所在）
    page_sc           TEXT NOT NULL,          -- 所屬頁面 dc_page_layouts.secure_code
    widget_id         TEXT NOT NULL,          -- 所屬 widget 的 id
    uploader_ref      TEXT NOT NULL,          -- 'u:<portal_users.secure_code>' 或 'designer:<平台 users.secure_code>'
    original_name     TEXT NOT NULL,
    file_size         INTEGER NOT NULL DEFAULT 0,
    file_ext          TEXT DEFAULT '',
    is_deleted        INTEGER NOT NULL DEFAULT 0,
    deleted_at        TEXT,
    created_at        TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_portal_files_widget ON portal_files(page_sc, widget_id, is_deleted);
CREATE INDEX IF NOT EXISTS idx_portal_files_uploader ON portal_files(uploader_ref, is_deleted);

CREATE TABLE IF NOT EXISTS portal_file_acl (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    file_secure_code  TEXT NOT NULL,
    grantee_type      TEXT NOT NULL,          -- 'user' | 'role'
    grantee_code      TEXT NOT NULL,          -- portal_users.secure_code 或 portal_admin_roles.code
    created_at        TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(file_secure_code, grantee_type, grantee_code)
);
```

**注意**：`portal_files` 放 `portal.db`（權限相關）而非 `portal_data.db`（業務資料）。

**級聯**：刪除子系統時 `cleanup_portal_sqlite()` 已整個目錄刪除；
但 `platform_files` 的實體**不會**跟著刪 → 需要在子系統刪除流程補一步
（依 `portal_files.platform_file_sc` 批次軟刪 `platform_files`），否則會產生孤兒加密檔。

---

## 5. API 端點

### Portal 側（末端用戶用，走 portal session）

前綴 `/public/portal/<path_id>/files`，實作在 `modules/nocode_builder/web/portal_public.py`。

| 方法 | 路徑 | 說明 |
|---|---|---|
| POST | `/upload` | body: `page_sc`、`widget_id`、`file`。需 `upload_by == 'portal_user'` 且已登入 |
| GET | `/list?page=<sc>&widget=<id>` | 回該 widget 中**該身分可讀**的檔案清單（已過濾） |
| GET | `/<portal_file_sc>` | 下載。判權後直接串流 |
| DELETE | `/<portal_file_sc>` | 僅上傳者本人或具管理權限者 |

**匿名可存取的只有 GET `/list` 與 GET `/<sc>`，且僅在 `guest_readable` 為真時。**

### 平台側（設計者放檔用，走 Flask-Login）

| 方法 | 路徑 | 說明 |
|---|---|---|
| POST | `/api/nocode-builder/sub-systems/<ss>/portal-files` | 設計者上傳，內部呼叫 `file_service.upload_file(context_type='portal_file')` 後在 SQLite 建對照列 |
| GET | `/api/nocode-builder/sub-systems/<ss>/portal-files?page=&widget=` | 設計者檢視 |
| DELETE | `/api/nocode-builder/sub-systems/<ss>/portal-files/<sc>` | |
| PUT | `/api/nocode-builder/sub-systems/<ss>/portal-files/<sc>/acl` | 整組覆寫 ACL（與 PF-8 權限管理的「整組覆寫」慣例一致，非增量） |

平台側端點一律掛 `@permission_required('nocode_builder.manage')`。

### `context_type` 新增

`file_service.py` 的三張表要同步加 `portal_file`：

- `CONTEXT_STORAGE_MAP['portal_file'] = 'encrypted'`（末端用戶檔案一律加密儲存）
- `CONTEXT_ALLOWED_EXT['portal_file']`：比照 `form_attachment`
- `CONTEXT_MAX_SIZE['portal_file']`：50MB

**不要**加進 `PUBLIC_CONTEXT_TYPES`——那組是無租戶隔離、無語境的全域公開，
匿名可讀由 portal 端點自行判定。

---

## 6. IR widget 定義

新 widget type `file_box`，加入 `backend/app/pageir/schema_v3.json`。

```jsonc
{
  "type": "file_box",
  "id": "files-1",
  "title_i18n": {"zh-TW": "附件", "en": "Attachments"},
  "mode": "upload | list | both",        // 預設 both
  "upload_by": "designer | portal_user", // 預設 portal_user
  "read_scope": ["donation.manage"],     // 權限碼陣列，["*"] = 所有登入帳號
  "per_file_acl": false,
  "guest_readable": false,
  "max_files": 20,                       // 每個帳號在此 widget 的上傳上限
  "allowed_ext": ["pdf", "png", "jpg"],  // 選填，未填則用 context_type 的白名單
  "list_columns": ["name", "size", "uploaded_at", "uploader"]
}
```

- `read_scope` 的每個元素必須符合 `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$` 或字面 `*`
- `allowed_ext` 只能是 `CONTEXT_ALLOWED_EXT['portal_file']` 的子集（schema 擋一次、後端再擋一次）
- 渲染實作在 `backend/app/pageir/renderer.py`，**參照 menu widget 的 `_prepare_menu` 模式**
- 若 `page.engine` 為 `grid` / `free`，widget 落在 zone／frame 內部，
  與其他 flow widget 一視同仁，**不需要為引擎寫分支**

---

## 7. 設計器 UI

屬性面板加在 `modules/nocode_builder/templates/modules/nocode_builder/_ir_designer_props.html`
（42KB 的那個檔，所有 widget 屬性面板都在裡面）。

需要的欄位：模式、誰能上傳、可讀權限碼（多選，來源是該子系統的 `portal_permissions`）、
啟用個別檔案 ACL、匿名可讀開關、單人上傳上限、允許副檔名、清單欄位。

`per_file_acl` 啟用時，設計者上傳的每個檔案要能就地指定可讀帳號／角色
（帳號清單來源 `portal_users`，角色來源 `portal_admin_roles`）。

**匿名可讀開關必須在設計器與工作區權限矩陣兩處都能關**
（用戶要求「管理者與設計者隨時可關閉」）。

---

## 8. 分階段實作

| 階段 | 內容 | 可驗收的產出 |
|---|---|---|
| A ✅ | portal.db v4 schema + `context_type` 註冊 + 平台側四個 API | 設計者能放檔、SQLite 有對照列 |
| B | portal 側四個端點 + 判定鏈 | curl 四種身分矩陣測試全綠 |
| C | `schema_v3.json` + renderer | 頁面能渲染出上傳區與清單 |
| D | 設計器屬性面板 | 瀏覽器實際設定並驗證生效 |
| E | 子系統刪除的級聯補刀 | 刪子系統後無孤兒 `platform_files` |

---

## 9. 安全要求（派工時必須逐條複製進 prompt）

1. **FILE-01**：一律透過 `file_service`，禁止自行實作上傳下載、禁止直接讀寫
   `uploads/` 或 `encrypted_storage/`、禁止手動呼叫 `crypto/engine.py`
2. **下載回應的 `Content-Type` 一律用 `file_service.get_serve_mime(record)`**
   （副檔名白名單推導），**禁止**使用 `platform_files.mime_type`
   ——該欄位是上傳者宣告的值，2026-08-05 才因此修掉一個儲存型 XSS
3. 下載回應必須設 `g._bk_strict_file_csp = True`，讓 `security_headers` 送出
   `default-src 'none'; sandbox`；副檔名在 `file_service.FORCE_DOWNLOAD_EXT` 內時
   加 `Content-Disposition: attachment`
4. **權限判定失敗一律回 404**，不回 403，不洩漏存在與否
5. **禁止自行組 SQL 計算 portal 權限**，一律呼叫 `portal_permission_service`
6. **禁止在正式服務層新增任何可免密碼登入的函式**（那會被推上公開 repo）
7. 所有 SQL 走 bind param；表名／欄名若需動態組合必須過
   `sqlite_crud_service._validate_identifier` 同級的白名單
8. 匿名上傳一律拒絕，即使 widget 設定看似允許（fail-closed 雙重確認）
9. 新增的 portal 模板**禁止** `{% extends "layouts/base.html" %}`
   ——portal 是公開路由，會把平台 navbar／選單／capability.js 洩漏給外部訪客
10. 所有 user-facing 字串包 `_()` / `{{ _() }}` / `__()`；
    **禁止**包裹參與 `==` 比較的字串與機器可讀錯誤碼

派工時**併同貼上**：`docs/codex_spec/portal.md`、`security.md`、`frontend.md`、
`i18n.md`、`_footer.md`（`_footer.md` 每次必貼）。

---

## 10. 實作細節（2026-08-05 codex 冷讀後補，避免新接手者試誤）

### 檔案位置與既有 helper

| 要做的事 | 用哪個 | 位置 |
|---|---|---|
| 平台側四個 API | 新檔 `portal_file_api.py`，比照 `portal_permission_api.py` 的註冊方式 | `modules/nocode_builder/api/` |
| portal 側四個端點 | 加在既有檔 | `modules/nocode_builder/web/portal_public.py` |
| 取 portal.db session | `DataSourceManager().get_session(sub_system_sc, 'portal')` | `services/data_source_manager.py` |
| 產生 `secure_code` | `from app.utils.security import generate_secure_code`（預設 22 字元 `token_urlsafe`） | 寫入時遇 UNIQUE 衝突重試一次即可 |
| 判斷頁面屬於哪個子系統 | `get_owner_sub_system_codes()` / `is_page_reachable()` | `services/page_ownership_service.py`，**禁止自己查單一張表**（此坑已犯過三次） |
| 取設計者身分 | `current_user.secure_code`（平台 `User` model） | |

`<ss>` 一律指 **`dc_sub_systems.secure_code`**，不是 `path_id`、不是 slug。
`path_id` 只出現在 portal 側的公開 URL。

### 交易與補償（**這幾條寫錯會產生孤兒加密檔或幽靈記錄**）

- 上傳流程是「先 `file_service.upload_file()` → 再寫 SQLite 對照列」，
  **兩個資料庫無法同一 transaction**。SQLite 寫入失敗時**必須補償**：
  軟刪剛建立的 `platform_files`（`status='deleted'`）並 `db.session.commit()`，
  然後回 500。不補償就是孤兒加密檔
- 單檔 DELETE：**同時**軟刪 `portal_files.is_deleted=1` 與對應的 `platform_files`
  （走 `file_service` 既有的刪除路徑，不要自己 UPDATE）。
  順序是先 SQLite 再平台——SQLite 失敗就整個中止，平台檔還在總比反過來好
- ACL 整組覆寫：先確認檔案存在且屬於該子系統，再在**單一 SQLite transaction**
  內 `DELETE` 全部舊列 + `INSERT` 新列。`get_session()` 的 context manager
  已有 commit/rollback，不要自己開第二層

### 平台側 API 的驗證邊界

- `@permission_required('nocode_builder.manage')` **之外還要檢查**：
  子系統屬於 `current_user` 所在企業（租戶隔離）、子系統未刪除。
  停用（非 published）不擋——設計者本來就要能在發布前放檔
- `page_sc` + `widget_id` **必須驗證存在於該頁 IR 中且 `type == 'file_box'`**（fail-closed）。
  階段 C 之前 IR 還沒有這個 widget type，此檢查在階段 C 完成後才會真的通過
  ——階段 A 先寫好檢查、以 fixture IR 測試，**不要留 TODO 跳過**
- `upload_by == 'designer'` 的檢查同樣在平台側做：widget 設定為 `portal_user` 時，
  平台側上傳 API 一律拒絕（400）
- `per_file_acl` 未啟用時寫入 ACL → 400，不靜默忽略
- ACL 的 `grantee_code` 必須驗證存在：`user` 查 `portal_users`（且
  `is_active=1`），`role` 查 `portal_admin_roles`。查不到回 400

### 回應格式（沿用既有慣例，不要自創）

成功 `{"success": true, "data": {...}}`；失敗 `{"success": false, "message": "<已 gettext 的訊息>"}`。
狀態碼：驗證失敗 400、權限不足 403（**平台側**）、資源不存在 404、
伺服器錯誤 500。**portal 側一律 404**（見 §3 判定順序）。

### `CONTEXT_ALLOWED_EXT['portal_file']` 展開值

```python
{'pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx',
 'odt', 'ods', 'csv', 'txt', 'rtf',
 'png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp',
 'zip', '7z', 'rar'}
```

改 `file_service.py` 的三張常數表時，同步檢查 `docs/FILE_SERVICE.md`
的 context_type 對應表要不要更新。

### 階段 A 的驗收環境

可用的識別碼與登入指令見 BBN 待辦 **PF-44**（`note_search("PF-44")`），
內含本機已驗證過的 quick-login、portal-quick-login、sqlite3 直查指令，
以及六種身分的測試帳號 secure_code。照抄即可，不要自己找帳號。

### 階段 A 完成後的既成事實（2026-08-05，階段 B 起照這個走）

- 落地檔案：`modules/nocode_builder/services/portal_file_service.py`（SQLite 存取層，
  含 `find_file_box_widget` / `widget_setting`）、`modules/nocode_builder/api/portal_file_api.py`
  （平台側四個端點）。階段 B 的 portal 端點**重用同一個 service**，不要再寫一份 SQL
- **widget 設定直接掛在 widget 物件上，沒有 `settings` 子物件**（見 §6）。
  `widget_setting()` 對型別錯誤一律回退預設值、不 raise
- 平台側端點的 decorator 組合：`@csrf.exempt` + `@admin_required` +
  `@permission_required('nocode_builder.manage')`（與 PF-29 共用選單端點一致）
- **回應一律不含 `platform_file_sc`**（少一條餵給 `/api/files/<sc>/serve` 的旁路）
- 失敗回應用 `message` key（非同 blueprint 舊檔的 `error`）
- 軟刪檔案時**一併硬刪該檔的 ACL 列**
- **PF-43 的上傳端收斂已在階段 A 一併完成**：`/api/files/upload` 只收
  `file_service.GENERIC_UPLOAD_CONTEXT_TYPES`（`form_attachment` / `subsystem_file`），
  `portal_file` 只能走平台側專屬端點。讀取端語境化（PF-43 的另一半）仍未做

## 11. 已知待決

- `read_scope` 為 `["*"]` 時是否包含匿名？**不包含**——匿名只吃 `guest_readable`
- 上傳配額（`max_files`）達上限時的行為：拒絕並回明確訊息，不靜默覆蓋
- 匿名下載的頻率限制：接 open-defense 的 security-cases 監控與自動封 IP，
  屬後續工單，本規格只要求下載端點記錄足夠的稽核欄位（來源 IP 走 `get_client_ip()`）
