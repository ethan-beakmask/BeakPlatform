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
                              ├── form_{id}_v{n}                  (主表)
                              └── form_{id}_v{n}_items_{key}      (子表)
```

## 表命名

| 類型 | 格式 | 範例 |
|------|------|------|
| 企業資料庫 | `org_{org_id}` | `org_14` |
| 主表 | `form_{mapping_id}_v{publish_version}` | `form_38_v3` |
| 明細子表 | `form_{id}_v{n}_items_{grid_key}` | `form_38_v3_items_leavedetails` |
| 簽核記錄 (Phase 3) | `form_{id}_v{n}_approvals` | `form_38_v3_approvals` |

## 帳號權限

| 角色 | 命名 | 權限 |
|------|------|------|
| Admin | `bfadmin_{org_id}` | CREATE/DROP TABLE, GRANT |
| Sync | `bfsync_{org_id}` | SELECT, INSERT, UPDATE, DELETE |

密碼由系統自動產生（24 字元英數），以 Fernet 加密儲存在 `fw_org_databases`。

**注意**: Sync 角色的 DELETE 權限僅用於子表同步（DELETE + INSERT 策略），主表仍使用 UPSERT。

## 使用流程

1. **發行配對** — 在 `/forms/mappings` 建立表單-流程配對並發行
2. **啟用 SQL Sync** — 勾選 SQL 開關（必須已發行，啟用後不可關閉）
   - 自動建立企業 DB（如不存在）
   - 自動建立同步表（主表 + datagrid 子表）
   - 自動安裝 pgcrypto extension
3. **新發行版本** — 每次新發行自動建立新表 (`form_{id}_v{n+1}`)
4. **表單流程結束** — Worker 自動將終態資料寫入對應表

## Datagrid/Editgrid 明細子表

表單中的 datagrid/editgrid 元件（一對多明細）會同時存兩份：

1. **主表**: 整個 JSONB 陣列存為一個欄位（向後相容）
2. **子表**: 每一列展開為獨立 row（`_items_{grid_key}`）

### 子表結構

```sql
CREATE TABLE form_38_v3_items_leavedetails (
    id SERIAL PRIMARY KEY,
    form_instance_secure_code VARCHAR(32) NOT NULL,
    row_index INT NOT NULL,
    date DATE,
    period VARCHAR(500),
    hours NUMERIC,
    remark VARCHAR(500)
);
CREATE INDEX ON form_38_v3_items_leavedetails (form_instance_secure_code);
```

### 同步策略

子表使用 **DELETE + INSERT**（在同一 transaction 中）：
- 先刪除該 form_instance 的所有 rows
- 再全部重新插入

原因：datagrid 的 rows 可以增刪改排序，用 row_index 做 UPSERT 不可靠。

### Metadata

子表資訊嵌入 `FwSqlFormRegistry.column_mapping` 的 grid 欄位中：

```json
{
  "leaveDetails": {
    "pg_type": "JSONB",
    "nullable": true,
    "is_pii": false,
    "sub_table": {
      "table_name": "form_38_v3_items_leavedetails",
      "columns": {
        "date": {"pg_type": "DATE", "nullable": true, "is_pii": false},
        "period": {"pg_type": "VARCHAR(500)", "nullable": true, "is_pii": false}
      }
    }
  }
}
```

## PII 欄位加密

標記為 PII 的欄位（表單設計者在元件屬性中設 `properties.pii = true`）在 org DB 中以 pgcrypto 對稱加密儲存。

### 加密方式

- **加密**: `pgp_sym_encrypt(value::text, passphrase)` → BYTEA
- **解密**: `pgp_sym_decrypt(column, passphrase)::text`
- **欄位型別**: PII 欄位在 org DB 中存為 `BYTEA`

### 查詢解密範例

```sql
-- 查詢加密欄位
SELECT
    form_instance_secure_code,
    pgp_sym_decrypt(applicant_name, 'your-passphrase')::text AS applicant_name,
    pgp_sym_decrypt(id_number, 'your-passphrase')::text AS id_number,
    leave_type
FROM form_38_v3
WHERE form_instance_secure_code = 'xxx';
```

### 密鑰管理

- 密鑰存放在 `SYNC_PII_PASSPHRASE` 環境變數
- 與 `SYNC_CREDENTIAL_KEY`（Fernet，加密 DB 帳號密碼）分離
- 密鑰僅在 Worker 執行時使用，不暴露於前端或 API

## 舊資料回補工具

啟用 SQL Sync 前已結案的表單可用回補腳本批次寫入：

```bash
cd /opt/BeakPlatform
source venv/bin/activate
set -a && source .env && set +a

# 預覽（不實際入列）
python scripts/backfill_sync.py --dry-run

# 全部回補
python scripts/backfill_sync.py

# 指定企業
python scripts/backfill_sync.py --org ORG_SECURE_CODE

# 指定配對
python scripts/backfill_sync.py --mapping MAPPING_SECURE_CODE

# 自訂批次大小
python scripts/backfill_sync.py --batch-size 200
```

**冪等**: 已在 queue 中（completed 或 pending/processing）的 instances 會自動跳過。

## 環境變數

| 變數 | 說明 |
|------|------|
| `SYNC_PG_ADMIN_URL` | PostgreSQL 管理員連線 URL（需有 CREATEDB + CREATEROLE） |
| `SYNC_CREDENTIAL_KEY` | Fernet 加密金鑰（用於加密 DB 帳號密碼） |
| `SYNC_PII_PASSPHRASE` | PII 欄位加密密鑰（pgcrypto 對稱加密用） |

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
| `services/sql_sync/org_db_manager.py` | 建立企業 DB / 角色 / 權限 / pgcrypto |
| `services/sql_sync/pool.py` | Per-org 連線快取 (TTL 5 分鐘) |
| `services/sql_sync/converter.py` | form.io schema → DDL / 值轉換 / 子表 schema |
| `services/sql_sync/table_manager.py` | 建表 / 刪表 / 子表建立 / Registry |
| `services/sql_sync/sync_service.py` | enqueue + execute_sync + PII 加密 + 子表同步 |
| `services/sql_sync/worker.py` | Background Worker 主迴圈 |
| `scripts/sync_worker.py` | Worker 啟動腳本 |
| `scripts/backfill_sync.py` | 舊資料回補腳本 |
| `scripts/upgrade_approval_tables.py` | 既有 registry 補建 approval 子表 |
| `scripts/rotate_credentials.py` | 企業 DB 密碼輪換腳本 |

## 簽核記錄子表 (`_approvals`)

流程結束時，除了同步表單欄位，也將簽核記錄寫入固定 schema 的 approval 子表，讓 BI 可直接查詢簽核歷程。

### 表結構

```sql
CREATE TABLE form_38_v3_approvals (
    id SERIAL PRIMARY KEY,
    form_instance_secure_code VARCHAR(32) NOT NULL,
    node_id VARCHAR(100),
    node_name VARCHAR(200),
    approver_secure_code VARCHAR(32),
    approver_name VARCHAR(200),
    approver_dept VARCHAR(200),
    delegate_from_secure_code VARCHAR(32),
    delegate_from_name VARCHAR(200),
    action VARCHAR(50) NOT NULL,
    comment TEXT,
    assigned_at TIMESTAMP,
    acted_at TIMESTAMP
);
CREATE INDEX ON form_38_v3_approvals (form_instance_secure_code);
```

### 同步策略

與 datagrid 子表一致：**DELETE + INSERT**（同一 transaction）。
- 流程結束時查詢該 form_instance 的所有 `FwApprovalRecord`
- 一次性寫入 approval 子表
- comment 為純文字操作記錄，非 PII，不加密

### Metadata

在 `FwSqlFormRegistry.column_mapping` 中以 `_` 前綴的保留鍵儲存：

```json
{
  "_approval_table": "form_38_v3_approvals",
  "reason": {"pg_type": "VARCHAR(500)", ...}
}
```

`_` 前綴為系統保留 metadata（form.io 欄位 key 不會以 `_` 開頭）。

### 既有 Registry 升級

```bash
cd /opt/BeakPlatform
source venv/bin/activate
set -a && source .env && set +a

# 預覽
python scripts/upgrade_approval_tables.py --dry-run

# 執行
python scripts/upgrade_approval_tables.py

# 指定企業
python scripts/upgrade_approval_tables.py --org ORG_SECURE_CODE
```

## 密碼自動輪換

企業 DB 帳號（`bfadmin_{id}` / `bfsync_{id}`）的密碼應定期輪換。

### 輪換原理

- `ALTER ROLE ... PASSWORD` 不中斷已建立的 PostgreSQL 連線
- 連線池 TTL (5 分鐘) + health check 確保自然過渡
- Worker 和腳本是不同 process，Worker 的連線會在 TTL 到期後自動使用新密碼重連

### 手動執行

```bash
cd /opt/BeakPlatform
source venv/bin/activate
set -a && source .env && set +a

# 預覽（不實際輪換）
python scripts/rotate_credentials.py --dry-run

# 執行（僅輪換超過 90 天的）
python scripts/rotate_credentials.py

# 強制輪換全部
python scripts/rotate_credentials.py --force

# 自訂天數閾值
python scripts/rotate_credentials.py --max-age 60

# 指定企業
python scripts/rotate_credentials.py --org ORG_SECURE_CODE
```

### Systemd Timer（自動排程）

```bash
# 安裝
sudo cp scripts/systemd/beakplatform-rotate-credentials.service /etc/systemd/system/
sudo cp scripts/systemd/beakplatform-rotate-credentials.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now beakplatform-rotate-credentials.timer

# 確認排程
systemctl list-timers beakplatform-rotate-credentials.timer

# 手動觸發（測試）
sudo systemctl start beakplatform-rotate-credentials.service
journalctl -u beakplatform-rotate-credentials.service -e
```

Timer 每週日凌晨 3:00 觸發，腳本內部檢查 90 天閾值，只輪換超齡的企業。

## Phase 2 完成項目

- [x] Datagrid/Editgrid 明細子表 (`_items_{key}`)
- [x] PII 欄位加密（依 `properties.pii` 標記）
- [x] 舊資料回補工具（啟用 SQL Sync 前的表單補寫入）

## Phase 3 完成項目

- [x] 簽核記錄子表 (`_approvals`)
- [x] 密碼定期輪換排程
