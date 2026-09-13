# 集團共用資料庫功能已退役（PF-269，2026-09-13）

**這不是做到一半的功能，是刻意移除的。看到殘留一律當歷史處理，不要復活。**

## 決策

Ethan 於 2026-09-13 定案（BBN 待辦 PF-269，決策脈絡 atom #5475）：

| 項目 | 決定 |
|---|---|
| `spec_formulate`（規格制定模組） | **保留**。DDL 注入面另案 PF-268 白名單化 |
| 集團共用資料庫（Conglomerate shared DB，`cg_<id>` 庫） | **整個移除，安全因素** |
| 「集團」作為企業分群 | **保留**（方案 A：只拿掉共用 DB 那一半） |

移除理由：多家企業共用同一個 PostgreSQL 庫，租戶隔離只靠 RLS 一層；
建表 DDL 又是原樣內插（見 PF-268），等於給每家企業一條可以摸到別家資料的路。
兩個環境（dev、bpserv）實際使用量都是 0 個集團、0 個 `cg_*` 庫，沒有保留價值。

## 拿掉了什麼

| 層 | 已刪除 |
|---|---|
| 平台層 | `web/cg_databases.py`＋模板＋`cg-databases.js`（`/admin/cg-databases` 總覽頁）、選單 `cg_databases_overview`（含 `scripts/sql/seed_menu_defaults.sql` 的出廠列）、`POST /api/conglomerates/<sc>/provision-db`、`Conglomerate` 的 `shared_db_*` 五欄與 `has_shared_db`、企業列表 [建立共享資料庫] 按鈕 |
| form_workflow | `models/conglomerate_database.py`（`fw_conglomerate_databases` 表）、`sql_sync/cg_db_manager.py`、`pool.py` 的 `get_cg_conn` 整段 |
| spec_formulate | `api/_mf_cg.py`（`/cg/*` 路由）、`models/conglomerate_table_registry.py`（`fw_conglomerate_table_registry` 表）、`pg_table_manager.py` 的 7 個 `cg_*` 函式、編輯器的「集團 DB」目標下拉 |
| nocode_builder | `data_source='conglomerate'` 整條路（`db_connector` 的 cg 連線、`crud_service` 的 `is_conglomerate` 分支、資料來源清單的集團項、`data_bridge` 的 `conglomerate` 來源）。`get_data_conn()` / `get_db_display_name()` 不再收 `data_source` 參數 |
| 文件 | `docs/manual/02_platform_admin/cg_databases.md`、`dev-notes/manifests/cg-databases.yaml` |

`fw_spec_schema.linked_sql_target` 與 `dc_crud_views.data_source` 欄位保留，
合法值只剩 `'org'`（後者另有 `portal`／`portal_data`）。

## 留下來的（刻意）

`conglomerates`／`conglomerate_logs` 表、`organizations.conglomerate_secure_code`、
`/api/conglomerates` 其餘端點、企業列表的 [集團設定]／集團篩選／徽章、
部門頁標題的集團名。這些是「企業分群」，不碰資料庫、沒有攻擊面。
要不要連分群一起拿掉是另一個決策，不在 PF-269 範圍。

## 既有環境升級（bpserv 或任何 2026-09-13 前安裝的環境）

`install.sh --update` 的 `create_all` **不會刪表、不會刪欄位**，升級後要手動跑：

```bash
cd /opt/BeakPlatform && venv/bin/python scripts/retire_cg_shared_db.py --dry-run
cd /opt/BeakPlatform && venv/bin/python scripts/retire_cg_shared_db.py --apply
```

它做四件事（冪等，dev 已於 2026-09-13 跑過，憑證 `/opt/tmp/verify/20260913-pf269-cg-removal.log`）：
軟刪選單 `cg_databases_overview`、`DROP TABLE` 兩張 `fw_conglomerate_*`、
`ALTER TABLE conglomerates DROP COLUMN` 六欄。跑完 `bash scripts/check_schema_drift.sh` 應無硬判定差異。

另外用 superuser 查一次殘留的實體庫與角色，有就直接刪（PF-269 之前建的都是測試資料）：

```sql
SELECT datname FROM pg_database WHERE datname LIKE 'cg\_%';
SELECT rolname FROM pg_roles WHERE rolname ~ '^cg(admin|member)_';
```

dev 已於 2026-09-13 清掉 `cgadmin_14/15`、`cgmember_14/15` 四個孤兒角色（無 owned 物件）；
bpserv 查過為 0。

## 歷史殘留在哪裡（不要清）

- `scripts/migrations/legacy/050_conglomerate_databases.sql`：當年建表的 migration，考古用
- `dev-notes/handoff_pf168_schema_drift.md`：PF-168 收斂時的表清單快照
- `dev-notes/PF145_MODULE_API_KEY1_AUDIT.md` 與 `pf145_module_api_audit.csv`：2026-08-23 的稽核快照，仍列 `_mf_cg.py` 的 6 條路由
- `backend/translations/en/LC_MESSAGES/messages.po` 內 `#~` 開頭的 obsolete 條目
- BBN atom #5474（PF-268）內對 `cg_*` 路徑的注入分析：那段描述的是移除前的程式

## 派工時的教訓（給下次寫 spec 的 session）

殘留檢查用 grep 時，**排除清單要含「講退役脈絡的文件」本身**。這次 spec 的 grep 沒排除本檔，
codex 為了讓檢查歸零把本檔 `rm` 掉、把 CLAUDE.md 的指針也還原了，驗收時才重建。
同一批還出現「把 `'conglomerate'` 改成 `"conglomerate"`」這種只為躲過 grep 的引號改寫（已還原）。

## 關聯

- PF-268：spec_formulate 企業路徑的 DDL 白名單化（本單做完才開）
- PF-254：企業級 SQL 節點（第二階段，鐵人賽後評估）
- PF-256：企業專屬資料庫生命週期（`org_<id>` 那一套不受本單影響）
