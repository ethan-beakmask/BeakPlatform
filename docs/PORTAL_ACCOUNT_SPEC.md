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
