# FormWorkflow 模組 - 資料庫遷移

## 遷移腳本

| 版本 | 檔案 | 說明 |
|------|------|------|
| 001 | `001_create_tables.sql` | 建立所有模組資料表 |
| 001 | `001_drop_tables.sql` | 刪除所有模組資料表（回滾用） |

## 安裝步驟

### 1. 確認資料庫連線

```bash
# 測試連線
psql -U beakplatform -d beakplatform_dev -c "SELECT 1"
```

### 2. 執行遷移腳本

```bash
cd /opt/BeakPlatform/modules/form_workflow/migrations

# 建立資料表
psql -U beakplatform -d beakplatform_dev -f 001_create_tables.sql
```

### 3. 驗證

```bash
# 檢查資料表
psql -U beakplatform -d beakplatform_dev -c "
SELECT table_name
FROM information_schema.tables
WHERE table_name LIKE 'fw_%'
ORDER BY table_name;
"
```

## 回滾

如需回滾（刪除所有資料表）：

```bash
psql -U beakplatform -d beakplatform_dev -f 001_drop_tables.sql
```

**警告：回滾會刪除所有資料！**

## 資料表說明

| 資料表 | 說明 |
|--------|------|
| `fw_form_templates` | 表單模板 |
| `fw_workflow_templates` | 工作流模板 |
| `fw_form_instances` | 表單實例（用戶填寫的表單） |
| `fw_workflow_instances` | 工作流實例（執行中的流程） |
| `fw_approval_records` | 簽核記錄 |
| `fw_node_execution_queue` | 節點執行隊列 |
| `fw_workflow_variables` | 工作流變數 |

## 版本記錄

- **001** (2026-01-24): 初始版本，建立基礎資料表
