# 開發工具與 POC 文件

> 本文件記錄 BeakPlatform 的非主應用工具，供開發者參考。

---

## 1. DevTools -- 開發工具服務

**路徑**: `/opt/BeakPlatform/devtools/`
**Port**: 7001
**狀態**: 開發環境專用，生產環境禁止啟用

### 用途

提供開發期間的資料庫檢視與資料清理工具，不涉及主應用邏輯。

### 功能

| 功能 | 說明 |
|------|------|
| DB Viewer | 資料庫表結構瀏覽器（三欄式：表列表 / 欄位資訊 / 資料預覽） |
| Quick Login | 連結到主應用的多帳號快速切換 |
| 表單流程清理 | 清除指定企業的 form_workflow 表單/流程/簽核資料 |

### 安全控制

- **IP 白名單**: 僅允許內網 IP (`192.168.*`, `10.*`, `172.16-31.*`, `127.0.0.1`)
- **敏感欄位模糊**: 含 `password`/`secret`/`token` 的欄位需 hover 才可見

### 啟動方式

```bash
# 手動啟動
cd /opt/BeakPlatform/devtools && source ../venv/bin/activate
set -a && source ../.env && set +a && python app.py

# systemd 服務
sudo systemctl start beakplatform-devtools
```

### 清除流程涵蓋表（按外鍵順序）

```
fw_node_execution_logs → fw_node_execution_queue → fw_approval_records
→ fw_workflow_variables → fw_workflow_instances → fw_form_instances
→ fw_published_form_workflows → fw_form_workflow_mappings
→ fw_workflow_templates → fw_form_templates
→ audit_logs (全企業清除時)
```

### 部署排除

- `.dev-only` 標記檔案
- `.gitattributes` 設定 `export-ignore`
- rsync 部署時 `--exclude='devtools/'`

---

## 2. SQL Form POC -- 動態表單概念驗證

**路徑**: `/opt/BeakPlatform/tools/sql_form_poc/`
**Port**: 5555
**狀態**: POC 階段，未整合到主應用

### 用途

驗證「PostgreSQL 表結構 → form.io 表單 → CRUD 資料」的完整流程。

### 核心流程

```
PostgreSQL 表 (fw_data_*)
    ↓ converter.py (欄位分析)
form.io Schema (自動產生)
    ↓ Designer (使用者自訂版面)
JSONB 存檔 (fw_sql_form_layouts)
    ↓ Data Manager
表單提交 → SQL INSERT/UPDATE/DELETE
```

### 型別對應

| PostgreSQL 型別 | form.io 元件 |
|-----------------|-------------|
| varchar / character varying | textfield |
| text | textarea |
| integer / bigint / numeric | number |
| boolean | checkbox |
| date | day |
| timestamp | datetime |
| jsonb / json | textarea |

### API 端點

```
GET  /api/tables                          列出所有 fw_data_* 表
GET  /api/tables/<table>/schema           自動產生 form.io schema
GET  /api/tables/<table>/layout           取得已存版面（含合併邏輯）
POST /api/tables/<table>/layout           儲存自訂版面
DEL  /api/tables/<table>/layout           刪除版面恢復自動
GET  /api/tables/<table>/data             列最新 10 筆資料
POST /api/tables/<table>/data             新增行
GET  /api/tables/<table>/data/<id>        取單筆
PUT  /api/tables/<table>/data/<id>        更新
DEL  /api/tables/<table>/data/<id>        刪除
```

### 安全設計

- **表名白名單**: 正規表示式 `^fw_data_[a-z0-9_]+$`，不符合 → 400
- **Parameterized queries**: 防止 SQL 注入
- **存在檢查**: 查 `information_schema.tables`，不存在 → 404

### 版面合併邏輯

```
無存檔版面 → 回傳自動產生版面
有存檔版面 → 比較 SQL 欄位與已存欄位:
  - 新增欄位 (SQL 有、版面無) → 追加到末尾 + 警告
  - 孤立欄位 (版面有、SQL 無) → 警告但保留
```

### 啟動方式

```bash
cd /opt/BeakPlatform/tools/sql_form_poc
source ../../venv/bin/activate
python app.py  # Port 5555
```

### DB 表

```sql
fw_sql_form_layouts (table_name VARCHAR UNIQUE, layout JSONB)
fw_data_employee   (測試用範例表)
```

---

*最後更新: 2026-03-14*
