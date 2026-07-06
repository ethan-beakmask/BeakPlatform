# 交接提示詞：檔案 API 物件級授權（下載越權 + list/meta 上收）

> 把這份文件**整段貼給下一次對話的 Claude**（在 `/opt/BeakPlatform-dev/` 開的對話）。
> 這是 API 授權稽核（`docs/handoff_authz_api_guard.md`）過程中發現的獨立弱點，已壓縮成接手包。

---

## 你接手的脈絡

前一輪對話針對「PageRoleGuard 跳過 /api/」做了 528 個 API 端點的守衛盤點，定案採
`@permission_required`（方案 b）作為 API 細粒度授權統一機制。盤點過程深讀 33 條
login-only 端點時，發現檔案 API 的問題**超出 decorator 能解決的範圍**（需要物件級
/context 級判定），整組獨立成這份交接包。**檔案 API 的授權收斂全部歸這包**，
包括原主線第 1 批曾列的 `files/list`、`meta` 上收。

已確認的相關事實（不用重查）：

- cross-members / units/groups / pages / store 等 login-only 端點**都有函式內授權**，不是破口。
- `permission_required` decorator 已於 commit `57541d8b` 修復並強化：
  改呼叫 `PermissionService.can()`，新增 `model`/`sc_kwarg` 參數可撈資源物件供
  ABAC 條件評估，fail-closed。已有實際掛載範例：`api/users.py` 的
  `GET /api/users/<sc>` 掛 `@permission_required('user', 'read', model=User)`，
  低權限帳號驗收通過。**若檔案 API 有適合純 RBAC 解的端點，直接沿用此 decorator。**

---

## 這個弱點是什麼

**檔案下載/metadata API 只做租戶（org）隔離，沒有做「這個用戶跟這個檔案有沒有關係」的檢查。**

位置：`backend/app/api/files.py`

| 端點 | 行號（2026-07-06 時點） | 現有檢查 | 問題 |
|------|------|------|------|
| `POST /api/files/<sc>/download-token` | ~211 | 僅 `org_sc` 比對 | 同企業**任何登入用戶**可對任何檔案申請下載 token，含他人的加密簽核附件（form_attachment）；token 兌換端 `/api/files/dl/<token>` 是 public，信任 token 內容 |
| `GET /api/files/<sc>/meta` | ~372 | 僅 `org_sc` 比對 | 任何用戶可讀任何檔案 metadata（檔名、上傳者、context） |
| `GET /api/files/list` | ~489 | 僅 `org_sc` 比對 | 任何用戶可列全企業檔案清單，`context_type`/`context_id` 參數是選填過濾而非強制 |

**沒問題的部分（不要動）**：`DELETE /<sc>`、`revert-delete`、`revert-deletes` 已限上傳者本人；
`upload` 開放給登入用戶是合理的（一般用戶要傳簽核附件）。

**後果**：低權限用戶可枚舉 `/api/files/list` 拿到全企業檔案 secure_code，再逐一
`download-token` 下載，等於繞過整套表單簽核的可視範圍控制。AES-256-GCM 加密在此無效，
因為 `file_service.serve_file()` 對「有權限的請求」自動解密——而權限判定就是缺的那塊。

---

## 必讀（按順序）

1. `CLAUDE.md` — FILE-01 檔案統一規範（context_type / storage_type 對應表）
2. `backend/app/api/files.py` — 全部端點，特別是 download-token 的 Redis token 流程
3. `backend/app/services/file_service.py` — `get_file_by_sc()`、`list_files()`、`serve_file()`
4. 檔案 model（`file_service` 引用的那個，看有哪些欄位可用：`uploader_sc`、`context_type`、`context_id`）
5. `modules/form_workflow/` 中簽核流程如何引用附件（找 `form_attachment` 與 `context_id` 的關係），
   確認「流程參與者」在資料層怎麼判定（發起人、簽核人、被會簽人）

---

## 設計難點（先跟用戶討論清楚，不要直接寫）

1. **授權語意依 context_type 而異**，不是一個 decorator 能統一的：
   - `form_attachment`：應限「該簽核流程的參與者」（發起人 + 流程節點簽核人 + admin）。
     參與者判定需要查 form_workflow 模組的流程實例資料——平台層 `files.py` 查模組層資料
     有無分層違反問題，要跟用戶確認介面怎麼開（建議：file_service 定義
     per-context authorizer 註冊機制，模組註冊自己的判定函式）。
   - `subsystem_file`：限該子系統有 ACL 的用戶？要查 module_access。
   - `org_logo` / `wf_background`：本來就公開級，不用收。
2. **fail-closed 與回溯相容**：加了參與者檢查後，既有功能（簽核 modal 的附件列表、
   下載按鈕）是以什麼身份呼叫的要先驗證，避免把正常簽核人擋掉。
3. **`/api/files/list` 的收法**：強制要求 `context_id` 並驗證呼叫者對該 context 的權限？
   還是無 context 時只回自己上傳的檔案？要用戶定案。
4. **`dl/<token>` 兌換端不用動**：token 是 60 秒一次性、由申請端寫入完整身份，
   把關做在申請端（download-token）即可。

---

## 建議做法（草案，待用戶定案）

1. 在 `file_service` 加一個 `can_access_file(user, record) -> bool` 統一判定函式：
   - admin（org_admin/system_admin）→ 放行
   - `record.uploader_sc == user.secure_code` → 放行
   - 依 `context_type` 分派給註冊的 authorizer（form_attachment → 流程參與者判定）
   - 無 authorizer 的 context_type → **fail-closed 擋下**（寫 log）
2. `download-token`、`meta` 進入時呼叫 `can_access_file`，不通過回 403 + 稽核日誌
   （沿用 `_log_file_access`，加 denied 記錄）。
3. `list` 收斂：無 `context_id` 時只回自己上傳的；有 `context_id` 時先過
   `can_access_file` 等級的 context 權限檢查。
4. 低權限測試帳號 before/after 驗收：
   - 該擋：用戶 A 下載用戶 B 的 form_attachment（A 非該流程參與者）→ 403
   - 該通：流程簽核人下載待簽表單的附件 → 200
   - 該通：admin 全部 → 200
   - 該通：自己上傳的 → 200

---

## 驗證環境備忘（這輪已確認可用）

- 服務 URL 前綴：全站掛在 `/beakplatform` 下（DispatcherMiddleware），
  API 實際路徑是 `http://192.168.0.16:7000/beakplatform/api/...`
- 登入：`POST /beakplatform/auth/login`，JSON body
  `{"account": "username@domain", "password": "..."}`（JSON 走 API 模式免 CSRF）
- 低權限測試帳號（beluga 企業，org_sc=`_9c8TewkRkCBEf3XsUdqeF`）：
  - `user@beluga.com` / `Test1234!`（EMPLOYEE，無任何角色）
  - `admin-ethanyu@beluga.com` / `Test1234!`（ORG_ADMIN）
- 驗收腳本範例可參考前一輪做法：requests.Session 登入 → 打 API 比對狀態碼
  （該擋 403 / 該通 200 / admin 200 / 移除授權後回歸 403）
- 改了 security 層或 API 程式後要重啟 Flask（服務非 debug 模式，不會 auto-reload）

---

## 邊界

- 這輪**只處理檔案 API 的物件級授權**（含 `list`/`meta` 上收），不要動：
  - `@permission_required` 的全面鋪設（那是 `handoff_authz_api_guard.md` 主線的分批工作）
  - `ResourceGateway.list()` RBAC（已完成，見 git log）
  - 模組 API 的 223 條角色細分（用戶已定案這輪不碰）
- `files.py` 不在 security-core 禁區清單，但 FILE-01 是強制規範：所有改動走
  `file_service`，禁止在 API 層直接摸儲存目錄或 crypto。
- 測試環境資料皆可拋棄，可自建測試企業/用戶/檔案驗證。
