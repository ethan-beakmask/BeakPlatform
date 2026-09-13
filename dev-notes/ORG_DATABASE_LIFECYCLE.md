# 企業專屬資料庫的生命週期（PF-256，2026-09-12 定版）

> 這份文件取代先前散落在 CLAUDE.md、`org_physical_cleanup_service.py` 註解與
> BBN 原子裡互相矛盾的敘述。**日後只改這裡，CLAUDE.md 只留指針。**

## 一、它是什麼

每家企業有一個獨立的 PostgreSQL 資料庫 `org_<Organization.id>`，
搭配兩個專用角色：

| 角色 | 權限 | 用途 |
|---|---|---|
| `bfadmin_<id>` | 該庫 owner（DDL） | 建表、GRANT、安裝 extension |
| `bfsync_<id>` | 僅 DML | 平台日常讀寫 |

帳密以 Fernet（`SYNC_CREDENTIAL_KEY`）加密後存在主庫的 `fw_org_databases`。
目前住在裡面的資料：企業級對照表（`lookup_categories` / `lookup_items`，
含簽核片語）、表單 SQL Sync 的同步表、規格制定模組的實體表。

集團共用庫 `cg_<id>`（`cgadmin_*` / `cgmember_*`）已於 2026-09-13 依 PF-269 移除；
看到這類庫或角色一律是歷史殘留，直接刪。

## 二、佈建憑證：不需要 superuser（2026-09-12 起）

`.env` 的 `SYNC_PG_ADMIN_URL` 只需要一個
**`LOGIN + CREATEDB + CREATEROLE` 的非 superuser 角色**，
`install.sh` 會自動建立 `<db_user>_prov` 並填好。

2026-09-12 之前這裡寫的是 postgres superuser，理由是「安裝 pgcrypto 需要 superuser」——
**這個理由是錯的**：`pgcrypto` 在 PG16／PG18 都是 `trusted = true`，
資料庫 owner 就能安裝（實測 `pg_extension.extowner` 是 `bfadmin_<id>`）。
`org_db_manager._get_su_dsn()` 已刪除。

為什麼不留 superuser：superuser 可以 `COPY ... TO PROGRAM`，
等同 postgres 使用者身分的 OS 命令執行，而這份 `.env` 是要交付給客戶的產物。
非 superuser 的 provisioner 實測被擋下（`permission denied to COPY to or from
an external program`），也無法 `ALTER ROLE <應用帳號> WITH PASSWORD`、
無法讀主庫的 `users` 表。

**PG15 以下不成立**：那些版本的 `CREATEROLE` 可以奪取任何非 superuser 角色。
`install.sh` 的 `check_pg_version()` 會在低於 16 時警告（不中止）。

### 兩個猜不到的實作細節

- **`createrole_self_grant` 在 PG16 起預設是空字串**：`CREATEROLE` 建立角色時只拿到
  ADMIN OPTION、不含 SET，而 `CREATE DATABASE ... OWNER x` 要求建立者能 `SET ROLE` 到 x。
  未處理會得到 `ERROR: must be able to SET ROLE "bfadmin_N"`，而這句話完全不指向根因。
  `org_db_manager` 用 `SET createrole_self_grant = 'set, inherit'`
  ＋ `_ensure_can_set_role()`（`pg_has_role` 查不到就 `GRANT ... WITH SET TRUE`）處理。
- **刪庫不需要 provisioner**：`org_<id>` 的 owner 就是 `bfadmin_<id>`，
  憑證在登記表裡，連 `postgres` 維護庫就能 `DROP DATABASE ... WITH (FORCE)`。
  `drop_org_database()` 優先用 owner 憑證，失敗才退回 provisioner，
  都不行才回 `manual_command`（`sudo -u postgres dropdb <name>`）。

## 三、什麼時候建立

| 時機 | 實作 |
|---|---|
| **建立企業時**（2026-09-12 起的主要路徑） | `api/organizations.py` 與 `web/organizations.py` 在 `db.session.commit()` 之後呼叫 `org_database_service.ensure_org_database(org)` |
| 安裝／更新 | `bootstrap.py::ensure_org_databases()`（fresh 與 `--update` 都跑；`SYNC_PG_ADMIN_URL` 未設定時整步跳過並警告） |
| 補建 | 健康頁的【補建】按鈕，或 `scripts/provision_missing_org_databases.py --apply` |
| 按需（既有路徑，保留） | 表單配對啟用 SQL Sync、規格制定模組建實體表 |

**建庫失敗不會擋住企業建立**（企業已 commit，庫可事後補建），
但**一定會回報**：API 回應多一個 `warning` 欄位、Web 多一則 warning flash、
健康頁把該企業標成異常。這是刻意的——靜默才是這條待辦要解決的東西。

`ensure_org_database()` 的契約：**呼叫端必須先把 Organization commit 之後才呼叫**，
成功時它自己 commit 登記列，失敗時 rollback 並回 message。

## 四、什麼時候刪除

| 動作 | 位置 | 對專屬資料庫 |
|---|---|---|
| 刪除企業（軟刪除） | 企業編輯頁 | **不動**。這是保留期，客戶反悔續約時還原得回來 |
| 永久刪除已軟刪除的企業 | `/organizations/` 列表頁最下方 | **連同 `org_<id>` 與 `bfadmin_*` / `bfsync_*` 一起刪** |
| `install.sh --uninstall` | CLI | 連同所有 `org_*` / `cg_*` 與其專用角色、provisioner 一起刪 |
| `install.sh`（全新安裝） | CLI | 先清掉前一次安裝殘留的 `org_*` / `cg_*` 與角色 |

走到永久刪除已經是**第二道人工動作**（先軟刪、再到另一個區塊永久刪），
足以確認意圖，**不需要緩衝期**（Ethan 2026-09-07 二次定案，
推翻同日稍早「預設保留一段緩衝期」的說法，也推翻 2026-08-28「一律不由 web 端刪」）。

### 硬刪除的順序陷阱（改這段程式前必讀）

```
收集 db_name ＋ owner 憑證   <- 必須在刪表之前（fw_org_databases 的登記列會被一起刪掉）
刪各表 / DELETE organizations
db.session.commit()
DROP DATABASE / DROP ROLE    <- 必須在 commit 之後（交易若回滾，企業還在而庫已刪就回不來）
移除 encrypted_storage / EDL 目錄
```

唯一實作是 `org_database_service.collect_org_databases()` ＋
`drop_collected_databases()`。**角色是資料庫 owner，所以先刪庫再刪角色**，
庫沒刪成功就絕對不刪角色。

## 五、健康檢查與孤兒（PF-264）

**入口：`/organizations/databases`「企業獨立資料庫管理」（`@system_admin_required`）
頂端的「資料庫健康狀態」區塊。**
`/hostconfig/server-settings` 的「企業專屬資料庫」分類是同一份資料的唯讀版，
任一異常就亮紅字並連過去；那一頁刻意不提供任何修復或刪除動作。

唯一實作 `org_database_service.scan_org_database_health()`，端點
`GET /organizations/databases/health`。回的東西：

| 區塊 | 內容 |
|---|---|
| `provisioning` | 變數在不在 → 連得上嗎 → 有沒有 CREATEDB / CREATEROLE（`provisioning_health()`） |
| `orgs[].status` | `ok` / `unreachable` / `missing_database` / `not_ready` / `missing_registration` |
| `orgs[].degrade` | 該企業最近一次「讀取降級」的時間、原因、次數 |
| `orphan_databases` | 實體庫在、但不對應任何仍存在於 `organizations` 的企業 |
| `orphan_roles` | `bfadmin_<n>` / `bfsync_<n>`，但企業與 `org_<n>` 庫都不存在 |

三個動作端點（都 `@system_admin_required`，資料庫名走 request body 不走 URL）：
`POST .../<org_secure_code>/provision`、`POST .../orphans/delete-database`、
`POST .../orphans/delete-roles`。
**刪除類一律 fail-closed**：不是孤兒就拒絕，判不出來也拒絕
（守門條件有單元測試 `backend/tests/test_org_database_service.py`）。

### 為什麼「兩個方向」都要查

- 登記在、實體庫不在：本機系統企業的 `org_14` 就這樣存在了大半年
- 實體庫在、登記不在：企業硬刪除會把 `fw_org_databases` 一起刪掉，
  刪庫若失敗就再也查不到該刪哪個庫（`org_107` 即此；2026-09-12 已清）

`provision_org_database()` 的冪等檢查從此**同時看登記與實體庫**——
在此之前「登記 `is_ready=true` 但實體庫不存在」是不可逆狀態，重跑佈建也修不好。

## 六、連不上時的容錯

唯一實作在 `backend/app/services/lookup_org_service.py`：

| 路徑 | 行為 |
|---|---|
| 讀取（`get_categories` / `get_items*` / `check_item_code_exists` 等 8 支） | `logger.warning` ＋ `record_degrade()` ＋ 回空值 |
| 寫入（`create_*` / `update_*` / `delete_*` / `reorder_items`） | 拋 `OrgDatabaseUnavailable`，API 層回 **503** 與明確訊息 |

`OrgDatabaseUnavailable` 繼承 `RuntimeError`，所以
**`except OrgDatabaseUnavailable` 一定要排在 `except RuntimeError` 之前**，
否則會被吃掉變成 400。

呼叫端：`backend/app/api/lookup.py`、`modules/form_workflow/api/fc_phrases.py`
（簽核片語，表單中心每次載入都會打到）、`backend/app/api/code_service.py`。
`backend/app/services/lookup_service.py` 既有的五處 try/except 保留為第二層保險。

`record_degrade()` 是**進程內**的紀錄，多 worker 下各自獨立，
數字會低估但不會誤報；健康頁有一行說明。

**容錯只涵蓋 lookup 這條線**（PF-256 的範圍就是這樣定的）。
其他也在用 `pool.get_org_conn()` 的地方——SQL Sync 的
`sync_service` / `table_manager` / `alter_manager` / `schema_reader`、
`spec_formulate` 的 `pg_table_manager`、`nocode_builder` 的 `db_connector`——
**企業庫掛掉時仍會把例外往上拋**。那些是背景 worker 或明確的 SQL 功能，
失敗要讓人看見是對的；但如果哪天有人回報「啟用 SQL Sync 的企業庫掛了會 500」，
成因在這裡，不是漏做而是沒納入範圍。

## 七、掃 `pg_database` 不需要特權連線

`pg_database` 對任何角色都可讀，用平台自己的主庫連線即可。
但 **`pg_database_size()` 需要該庫的 CONNECT 權限**，而建庫時已
`REVOKE CONNECT ... FROM PUBLIC`，直接呼叫會整句 `InsufficientPrivilege`
（實測 `permission denied for database org_106`）。
一律包 `CASE WHEN has_database_privilege(datname, 'CONNECT') THEN ... ELSE NULL END`。
已退役的集團資料庫總覽曾經為了這件事開一條 superuser 連線，後續已移除。

## 八、驗收憑證

`/opt/tmp/verify/20260912-pf256.log`
（非 superuser provisioner 全程實測、健康掃描、瀏覽器點過補建／刪孤兒庫／刪孤兒角色）。
