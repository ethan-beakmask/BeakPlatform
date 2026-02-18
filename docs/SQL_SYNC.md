# SQL Sync — 企業專屬資料庫同步

## 概述

SQL Sync 將表單的 JSONB 欄位資料攤平寫入企業專屬的 PostgreSQL 資料庫，供報表、BI 等外部應用直接查詢。

**核心原則：**
- 每個企業一個獨立資料庫 (`org_{id}`)
- 雙權限帳號分離：DDL (`bfadmin_{id}`) / DML (`bfsync_{id}`)
- 只在流程結束時同步（終態資料：APPROVED / REJECTED / CANCELLED / ERROR）
- 表結構只有 `form_instance_secure_code`（關聯鍵）+ 表單欄位，系統欄位由主庫提供

## 架構

```
Flask App                    Background Worker
    │                              │
    │  表單流程結束                  │  每 2 秒輪詢
    │  (_finalize_workflow)        │
    ▼                              ▼
fw_sync_queue (主庫)  ──────►  SyncWorker
                                   │
                                   │  UPSERT (bfsync 低權限)
                                   ▼
                              org_{id} DB
                              └── form_{mapping_id}_v{version}
```

## 表命名

| 類型 | 格式 | 範例 |
|------|------|------|
| 企業資料庫 | `org_{org_id}` | `org_14` |
| 主表 | `form_{mapping_id}_v{publish_version}` | `form_38_v3` |
| 簽核記錄 (Phase 2) | `form_{id}_v{n}_approvals` | `form_38_v3_approvals` |
| 明細子表 (Phase 2) | `form_{id}_v{n}_items_{grid_key}` | `form_38_v3_items_leaveDetails` |

## 帳號權限

| 角色 | 命名 | 權限 |
|------|------|------|
| Admin | `bfadmin_{org_id}` | CREATE/DROP TABLE, GRANT |
| Sync | `bfsync_{org_id}` | SELECT, INSERT, UPDATE（無 DELETE） |

密碼由系統自動產生（24 字元英數），以 Fernet 加密儲存在 `fw_org_databases`。

## 使用流程

1. **發行配對** — 在 `/forms/mappings` 建立表單-流程配對並發行
2. **啟用 SQL Sync** — 勾選 SQL 開關（必須已發行，啟用後不可關閉）
   - 自動建立企業 DB（如不存在）
   - 自動建立同步表
3. **新發行版本** — 每次新發行自動建立新表 (`form_{id}_v{n+1}`)
4. **表單流程結束** — Worker 自動將終態資料寫入對應表

## 環境變數

| 變數 | 說明 |
|------|------|
| `SYNC_PG_ADMIN_URL` | PostgreSQL 管理員連線 URL（需有 CREATEDB + CREATEROLE） |
| `SYNC_CREDENTIAL_KEY` | Fernet 加密金鑰（用於加密 DB 帳號密碼） |

## Worker 管理

```bash
# 啟動 / 停止 / 狀態
sudo systemctl start beakplatform-sync-worker
sudo systemctl stop beakplatform-sync-worker
sudo systemctl status beakplatform-sync-worker

# 查看日誌
journalctl -u beakplatform-sync-worker -f

# 手動執行（除錯用）
cd /opt/BeakPlatform
source venv/bin/activate
set -a && source .env && set +a
python scripts/sync_worker.py
```

## 主要檔案

| 檔案 | 職責 |
|------|------|
| `models/org_database.py` | 企業 DB 記錄 + 加密憑證 |
| `models/sync_queue.py` | 同步佇列 Model |
| `services/sql_sync/org_db_manager.py` | 建立企業 DB / 角色 / 權限 |
| `services/sql_sync/pool.py` | Per-org 連線快取 (TTL 5 分鐘) |
| `services/sql_sync/converter.py` | form.io schema → DDL / 值轉換 |
| `services/sql_sync/table_manager.py` | 建表 / 刪表 / Registry |
| `services/sql_sync/sync_service.py` | enqueue + execute_sync |
| `services/sql_sync/worker.py` | Background Worker 主迴圈 |
| `scripts/sync_worker.py` | Worker 啟動腳本 |

## Phase 2 待辦

- [ ] 簽核記錄子表 (`_approvals`)
- [ ] Datagrid/Editgrid 明細子表 (`_items_{key}`)
- [ ] PII 欄位加密（依 `properties.pii` 標記）
- [ ] 舊資料回補工具（啟用 SQL Sync 前的表單補寫入）
- [ ] 密碼定期輪換排程
