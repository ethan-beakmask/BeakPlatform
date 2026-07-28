# Portal 帳號規格 (N1)

**NoCode 公開 Portal 帳號識別、群組階級與 session 標準**

> **邊界聲明**：本規格只定義 NoCode 子系統公開 portal 的帳號庫與瀏覽器 session。
> 母系統帳號、平台 RBAC、PostgreSQL schema 與 `backend/app/security/` 不屬於本規格。

---

## 1. 帳號庫邊界

每個 NoCode 子系統各自持有一組 SQLite：

| 檔案 | 用途 |
|---|---|
| `data/nocode_portals/<sub_system_sc>/portal.db` | portal 帳號、角色、群組、階級、設定 |
| `data/nocode_portals/<sub_system_sc>/portal_data.db` | 公開 portal 業務資料 |

`portal.db` 與母系統登入資料完全隔離。公開 portal 登入不建立 Flask-Login identity，
也不繼承母系統權限。

---

## 2. Session 識別

Portal 使用 Flask signed session cookie。session 只保存必要識別資訊與判定快取，
不保存密碼、hash、token 或母系統權限。

現行 key：

```python
session["portal_sessions"] = {
    "<sub_system_sc>": {
        "sub_system_sc": str,
        "user_id": int | None,
        "user_type": "GUEST" | "PUBLIC_USER",
        "group_code": str | None,
        "level_code": str,
        "level_rank": int,
        "roles": [str],
        "display_name": str,
    }
}
```

同一瀏覽器可同時持有多個子系統的 portal session。登入或登出某個子系統時，
只修改該 `sub_system_sc` 對應的 entry。

舊版 `session["portal_guest"]` 不再讀取；既有開發 session 會自然失效。

---

## 3. GUEST 語意

GUEST 是匿名訪問者，不對應 `portal_users` 資料列：

| 欄位 | 值 |
|---|---|
| `user_id` | `None` |
| `user_type` | `GUEST` |
| `group_code` | `None` |
| `level_code` | `GUEST` |
| `level_rank` | `0` |
| `roles` | `["GUEST"]` |
| `display_name` | `訪客` |

是否允許自動建立 GUEST session 仍由 `portal_settings.allow_anonymous` 決定。

---

## 4. 群組×階級模型

Portal 權限結構借鑒平台職級矩陣：

| 平台概念 | Portal 概念 | 欄位 |
|---|---|---|
| 職系 | 群組 | `group_code` |
| 職等 | 階級 | `level_code` / `level_rank` |

群組定義於 `portal_groups`：

| 欄位 | 語意 |
|---|---|
| `code` | 穩定代碼，格式 `^[A-Z][A-Z0-9_]{0,31}$` |
| `name` | 顯示名稱 |
| `display_order` | UI 排序 |
| `is_active` | 是否可指派 |

階級定義於 `portal_levels`：

| 欄位 | 語意 |
|---|---|
| `code` | 穩定代碼，格式同群組 |
| `name` | 顯示名稱 |
| `rank` | 階級高低，數字大代表權限高 |
| `display_order` | UI 排序 |
| `is_active` | 是否可指派 |

預設群組：`GENERAL` 一般。

預設階級：`GUEST` rank 0、`MEMBER` rank 10、`STAFF` rank 50、`ADMIN` rank 90。
管理者可調整 rank，因此執行期必須查表，不可硬編碼 rank。

---

## 5. 帳號預設值

公開註冊建立 `portal_users`：

| 欄位 | 預設 |
|---|---|
| `role_code` | `PUBLIC_USER` |
| `group_code` | `GENERAL` |
| `level_code` | `MEMBER` |

登入時若帳號的 `level_code` 為 `NULL`、不存在或停用，session 以
`level_code = "GUEST"`、`level_rank = 0` 處理，採 fail-closed。

`roles` 欄位保留向下相容；N1 不改頁面准入判定。

---

## 6. 判定規則

後續 portal 頁面准入應採同一語意：

```text
(群組符合或不限) AND (level_rank >= 門檻)
```

N1 只建立帳號結構與 session 規範化，不變更既有 `visible_roles` 判定。

## 6.1 頁面准入判定（N3a）

Portal 頁面 runtime 會在既有 `DcSubSystemPage.visible_roles` 通過後，再消費
`DcSiteMapNode.access_matrix`。兩者是 AND 關係：`visible_roles` 與
`access_matrix` 都必須通過，頁面才會渲染；任一拒絕皆回 404，避免洩漏頁面存在。

判定順序：

| 順序 | 條件 | 結果 |
|---|---|---|
| 1 | `portal_user` 為 `None` | 拒絕，`no_session` |
| 2 | 找不到 active、未刪除且對應子系統/頁面的 site map node | 放行，`no_matrix` |
| 3 | node 存在但 `access_matrix` 為 `NULL` | 放行，`no_matrix` |
| 4 | `access_matrix` 不是物件、缺 `read`、`read` 不是物件 | 拒絕，`bad_matrix` |
| 5 | `read.groups` 為 `null` | 群組條件通過 |
| 6 | `read.groups` 為清單 | `portal_user.group_code` 必須在清單內，否則拒絕 `group_denied` |
| 7 | `read.min_level` 缺少或不是字串 | 拒絕，`bad_matrix` |
| 8 | `read.min_level` 在該子系統 active `portal_levels` 查無 | 拒絕，`level_missing` |
| 9 | `portal_user.level_rank` 小於 min level rank | 拒絕，`level_denied` |
| 10 | 群組與階級皆通過 | 放行，`ok` |

Reason 短碼只供稽核與 log 使用，不是 user-facing 訊息：

| reason | 意義 |
|---|---|
| `no_session` | 沒有 portal session |
| `no_matrix` | 沒有對應 node，或 node 尚未設定 `access_matrix` |
| `bad_matrix` | `access_matrix` runtime 格式不合法 |
| `group_denied` | 使用者群組不符合 `read.groups` |
| `level_missing` | `read.min_level` 指向不存在或停用的 portal level |
| `level_denied` | 使用者 `level_rank` 未達門檻 |
| `ok` | 判定通過 |
| `error` | 未預期例外，例如 `portal.db` 不存在 |

Fail-closed 原則：只要 `access_matrix` 已設定，格式錯誤、`min_level` 查無、
portal DB 讀取錯誤或其他未預期例外都一律拒絕。`access_matrix = NULL` 是向下相容語意，
代表此節點尚未啟用 N3a 矩陣判定，runtime 交回既有 `visible_roles` 機制把關。

## 6.2 元件級判定（N4a）

Page IR v3 的 `table` / `detail` widget 可宣告元件級 `access_matrix`。它與頁面級
判定是 AND 關係：頁面級 `visible_roles` 與 `DcSiteMapNode.access_matrix.read`
先通過後，元件仍可能因自己的 `access_matrix.read` 被擋。

N4a runtime 只判定 `read`。`read` 不通過時，該 widget 不進 server-side render tree，
也不會呼叫資料 resolver；rows API 對同一 widget 回 404，符合 INV-3 hidden 不出資料。
未宣告 `access_matrix` 代表不額外限制；對 `check_widget_access()` 而言，某個 action
key 未宣告即放行，讓 N4b 的 create/update/delete 呼叫端可自行決定預設策略。

`create` / `update` / `delete` 三個 key 已保留在 schema 與型別語意中，但本階段不由
渲染流程消費。格式錯誤、`min_level` 查無、portal session/context 缺失或未預期例外
皆 fail-closed。

## 6.3 寫入判定（N4b）

Portal 寫入 API（create / update / delete）採明確宣告才允許的 fail-closed 語意：
`access_matrix` 不存在、不是 dict，或未宣告對應 action 時，一律拒絕並以 404 回應。
這與 `read` 的相容語意不同；`check_widget_access()` 仍維持 action 未宣告即放行，
寫入端必須使用 `check_widget_write_access()`。

每次寫入都會重新跑完整准入鏈：子系統 path、portal session（或允許匿名時的 GUEST）、
Page IR v3 已發布頁、子系統 mount/visible role、頁面級 `access_matrix.read`、
table widget、widget `read`、widget 寫入 action。任一環節失敗都回 404，避免洩漏
頁面、widget 或資料列是否存在。

寫入還必須通過 view 層級 CRUD 開關：`DcCrudView.allow_create / allow_edit /
allow_delete` 為 False 時，對應 action 直接拒絕，即使 widget `access_matrix` 通過。
實際可寫欄位是三重交集：

`binding.fields` ∩ `resource.fields` ∩ `sqlite_crud_service._get_writable_columns(view)`

交集會再經 `_strip_sensitive_columns()` 排除 password / token / secret 等敏感欄位。
client payload 中不在交集內的 key 會被靜默丟棄；交集為空時回 400
`no_writable_fields`。client 不得指定 table、view、resource 或任何 SQL 片段，
所有寫入皆透過 `SqliteCrudService` 執行。

三支寫入 API 不豁免 CSRF。Portal Page IR v3 HTML 會輸出
`<meta name="csrf-token" ...>`，前端必須帶 `X-CSRFToken`。

**目標表選擇原則（2026-07-28 驗收發現）**：若目標表存在 `NOT NULL` 且無預設值的
欄位，而該欄位落在敏感欄位排除清單內（如 `portal_users.password_hash`），
portal 新增必然失敗——因為它永遠進不了可寫白名單。這是預期的保護行為：
**帳號表（`portal.db` 的 `portal_users` 等）不應作為 portal 頁面的 CRUD 目標**，
帳號維運請走工作區「帳號權限」矩陣。portal 頁面的 CRUD 目標應是
`portal_data.db` 中的業務表，且欄位需有預設值或允許 NULL。

---

## 7. Schema 升級

`portal.db` 使用 `PRAGMA user_version` 管理 schema：

| version | 語意 |
|---|---|
| `0` 或 `1` | 基本帳號、角色、設定表 |
| `2` | 新增 `portal_groups`、`portal_levels`、`portal_users.group_code`、`portal_users.level_code` |

`ensure_portal_schema(sub_system_sc)` 對既有 DB 做冪等升級：

1. 檢查 `portal.db` 是否存在；不存在即拋出 `FileNotFoundError`，不自動建庫。
2. 讀取 `PRAGMA user_version`。
3. 小於 2 時建立群組與階級表、補 `portal_users` 欄位、寫入預設資料。
4. 完成後設定 `PRAGMA user_version = 2`。

`init_portal_sqlite()` 建立新子系統時會先套用基本 schema，再立即升級到 version 2。
登入、註冊與建立 GUEST session 會 lazy 呼叫升級流程，確保舊子系統可平滑升級。
