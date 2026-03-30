# BeakPlatform 安裝手冊

版本: 1.1
日期: 2026-03-28
適用系統: Ubuntu 24.04 LTS

---

## 目錄

1. 系統需求
2. 安裝步驟
3. 初始化資料庫
4. 啟動服務
5. 首次登入
6. 服務管理
7. 升級更新
8. 已知問題與注意事項
9. 疑難排解

---

## 1. 系統需求

| 項目 | 最低需求 |
|------|----------|
| 作業系統 | Ubuntu 24.04 LTS |
| CPU | 2 核心 |
| 記憶體 | 4 GB |
| 磁碟空間 | 20 GB |
| Python | 3.12 |
| PostgreSQL | 16 |
| Redis | 7.0+ |

---

## 2. 安裝步驟

### 2.1 安裝系統套件

```bash
sudo apt-get update
sudo apt-get install -y \
    postgresql postgresql-client \
    redis-server \
    python3-venv python3-pip python3-dev \
    libpq-dev build-essential
```

### 2.2 設定 Redis

BeakPlatform 使用 port 6380 (非預設的 6379)。

```bash
sudo sed -i 's/^port 6379/port 6380/' /etc/redis/redis.conf
sudo systemctl restart redis-server
sudo systemctl enable redis-server
```

### 2.3 設定 PostgreSQL

```bash
# 建立資料庫使用者
sudo -u postgres psql -c "CREATE USER beakplatform WITH PASSWORD 'postgres123';"
sudo -u postgres psql -c "ALTER USER beakplatform CREATEDB;"
sudo -u postgres psql -c "ALTER USER beakplatform WITH SUPERUSER;"

# 建立資料庫
sudo -u postgres psql -c "CREATE DATABASE beakplatform_dev OWNER beakplatform;"

# 安裝 pgcrypto 擴充
sudo -u postgres psql -d beakplatform_dev -c "CREATE EXTENSION IF NOT EXISTS pgcrypto;"
```

> 註: SUPERUSER 權限用於 pgcrypto 擴充建立，正式環境可在擴充建立後移除。

### 2.4 部署程式碼

將 BeakPlatform 程式碼放置到 `/opt/BeakPlatform/`。

**從開發機 rsync (適用於內部部署):**

```bash
sudo mkdir -p /opt/BeakPlatform
sudo chown $USER:$USER /opt/BeakPlatform

rsync -avz \
    --exclude='venv/' \
    --exclude='.git/' \
    --exclude='__pycache__/' \
    --exclude='*.pyc' \
    --exclude='app.db' \
    --exclude='deploy/' \
    --exclude='devtools/' \
    源機IP:/opt/BeakPlatform/ /opt/BeakPlatform/
```

### 2.5 建立 Python 虛擬環境

```bash
cd /opt/BeakPlatform
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r backend/requirements.txt
pip install Unidecode PyYAML pillow ruamel.yaml html2image rich
```

### 2.6 設定環境變數

確認 `/opt/BeakPlatform/.env` 存在且內容正確:

```bash
# 必要欄位
DATABASE_URL=postgresql://beakplatform:postgres123@localhost:5432/beakplatform_dev
REDIS_URL=redis://localhost:6380/0
SECRET_KEY=<請更換為隨機字串>
FLASK_ENV=development
FLASK_DEBUG=1
APP_PORT=7000
```

若需產生新的 SECRET_KEY:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

---

## 3. 初始化資料庫

### 3.1 建立資料表

**重要: 必須 import 模組 model，否則模組的表不會被建立。**

```bash
cd /opt/BeakPlatform/backend
source /opt/BeakPlatform/venv/bin/activate
set -a && source /opt/BeakPlatform/.env && set +a

python3 << 'EOF'
import sys
sys.path.insert(0, '..')
from modules.form_workflow.models import *
from modules.nocode_builder.models import *
from app import create_app, db
app = create_app()
with app.app_context():
    db.create_all()
    print("資料表建立完成")
EOF
```

### 3.2 建立初始資料

```bash
SKIP_MODULE_SYNC=1 python3 << 'EOF'
import bcrypt
from app import create_app, db
from app.models import Organization, User, UserType

app = create_app()
with app.app_context():
    existing = Organization.query.filter_by(domain_name='system.local').first()
    if existing:
        print("初始資料已存在，跳過")
    else:
        system_org = Organization(
            secure_code='system.local',
            code='SYSTEM',
            name='system.local',
            domain_name='system.local',
            is_active=True
        )
        db.session.add(system_org)
        db.session.flush()

        import os, sys
        admin_password = os.environ.get('ADMIN_INITIAL_PASSWORD', '').strip()
        if not admin_password or len(admin_password) < 8:
            print("ERROR: 請設定 ADMIN_INITIAL_PASSWORD 環境變數 (至少 8 字元)")
            sys.exit(1)

        password = admin_password.encode('utf-8')
        salt = bcrypt.gensalt()
        password_hash = bcrypt.hashpw(password, salt).decode('utf-8')

        admin = User(
            org_secure_code='system.local',
            username='admin',
            email='admin@system.local',
            display_name='System Admin',
            password_hash=password_hash,
            user_type=UserType.SYSTEM_ADMIN,
            is_active=True,
            must_change_password=True
        )
        db.session.add(admin)
        db.session.commit()
        print("初始資料建立完成")
        print("  帳號: admin@system.local")
        print("  密碼: (由 ADMIN_INITIAL_PASSWORD 設定，首次登入須變更)")
EOF
```

### 3.3 執行平台 Migration

```bash
export PGPASSWORD=postgres123

# 逐一執行平台 migration (排除 deprecated 和 drop 腳本)
for f in /opt/BeakPlatform/scripts/migrations/0*.sql; do
    # 跳過 deprecated 檔案
    [[ "$f" == *.deprecated ]] && continue
    echo "--- Running $f ---"
    psql -h localhost -U beakplatform -d beakplatform_dev -f "$f" 2>&1 | grep -E 'ERROR' || true
done

# 執行 backend migration
for f in /opt/BeakPlatform/backend/migrations/0*.sql; do
    echo "--- Running $f ---"
    psql -h localhost -U beakplatform -d beakplatform_dev -f "$f" 2>&1 | grep -E 'ERROR' || true
done
```

> 註: 部分 migration 的 ERROR 是正常的 (如欄位或表已存在)。
> db.create_all() 已建立所有 ORM 定義的結構，migration SQL 主要補充索引和資料。

### 3.4 初始化選單

```bash
cd /opt/BeakPlatform/backend
source /opt/BeakPlatform/venv/bin/activate
set -a && source /opt/BeakPlatform/.env && set +a

python3 /opt/BeakPlatform/scripts/init_menus.py --force
```

### 3.5 同步模組

```bash
flask module sync
```

---

## 4. 啟動服務

### 4.1 安裝 systemd service

```bash
sudo cp /opt/BeakPlatform/beakplatform.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable beakplatform
sudo systemctl start beakplatform
```

### 4.2 驗證服務

```bash
# 檢查服務狀態
sudo systemctl status beakplatform

# 健康檢查
curl -s http://localhost:7000/health
# 預期回應: {"service":"beakplatform","status":"healthy"}
```

---

## 5. 首次登入

### 5.1 系統管理員登入

- URL: `http://<主機IP>:7000/auth/login`
- 帳號: `admin@system.local`
- 密碼: 安裝時透過 `ADMIN_INITIAL_PASSWORD` 設定的密碼（首次登入強制變更）

**重要: 系統管理員必須使用 `/auth/login` (共用登入頁)，不要使用 `/auth/org/system.local/login`。**

首次登入會要求變更密碼，新密碼最少 12 碼。

### 5.2 建立企業

登入後透過系統管理介面建立企業，需填寫:
- 企業名稱
- Domain Name (用於企業專屬登入)

### 5.3 建立企業合約

**企業成員帳號需要有效合約才能登入。** 建立企業後，需到合約管理建立一筆合約，設定有效起迄日期。

企業管理員 (ORG_ADMIN) 和原始管理員 (is_original_admin=True) 不受合約限制。

### 5.4 企業成員登入

- URL: `http://<主機IP>:7000/auth/org/<domain_name>/login`
- 帳號: 僅輸入 username (不含 @domain)
- 或使用共用登入頁: `http://<主機IP>:7000/auth/login`，帳號格式 `username@domain`

---

## 6. 服務管理

### 啟動/停止/重啟

```bash
sudo systemctl start beakplatform
sudo systemctl stop beakplatform
sudo systemctl restart beakplatform
```

### 查看日誌

```bash
sudo journalctl -u beakplatform -f
```

### 手動啟動 (除錯用)

```bash
cd /opt/BeakPlatform/backend
source /opt/BeakPlatform/venv/bin/activate
set -a && source /opt/BeakPlatform/.env && set +a
flask run --host=0.0.0.0 --port=7000
```

---

## 8. 已知問題與注意事項

### 7.1 選單 icon 顯示問題
- 部分模組選單 (如「表單流程」) 會顯示為「F 表單流程」
- 原因: 模組定義中 icon 欄位設定了字元值
- 影響: 僅外觀，不影響功能
- 狀態: 主專案待修

### 7.2 登出後導向
- 登出後系統會根據 session 記錄的企業 domain 導向企業專屬登入頁
- 系統管理員登出後可能被導向 `/auth/org/system.local/login`
- 此時請手動前往 `/auth/login` 重新登入

### 7.3 合約檢查
- 企業成員 (EMPLOYEE) 登入時會檢查企業合約有效性
- 合約無效時登入會被靜默拒絕，錯誤訊息可能顯示不正確
- 確保每個企業都有設定有效合約

### 7.4 密碼重設 (緊急用)

如果管理員帳號無法登入，可直接在伺服器執行:

```bash
cd /opt/BeakPlatform/backend
source /opt/BeakPlatform/venv/bin/activate
set -a && source /opt/BeakPlatform/.env && set +a

python3 -c "
import bcrypt, getpass
from app import create_app, db
from app.models import User

new_pw = getpass.getpass('輸入新密碼: ')
app = create_app()
with app.app_context():
    user = User.query.filter_by(username='admin', org_secure_code='system.local').first()
    pw = bcrypt.hashpw(new_pw.encode(), bcrypt.gensalt()).decode()
    user.password_hash = pw
    user.must_change_password = True
    db.session.commit()
    print('密碼已重設，下次登入須變更')
"
```

---

## 7. 升級更新

### 7.1 Migration 管理機制

BeakPlatform 使用 `scripts/run_migrations.py` 統一管理資料庫 schema 變更。

Migration 檔案來源：
- **平台級**: `scripts/migrations/*.sql|*.py`
- **模組級**: `modules/*/migrations/*.sql|*.py`

追蹤表 `schema_migrations` 記錄已執行的 migration，避免重複執行。

### 7.2 首次啟用 migration 管理（既有安裝）

如果是從未使用 migration 管理的舊版本升級，需要先建立 baseline：

```bash
cd /opt/BeakPlatform
source venv/bin/activate
set -a && source .env && set +a

# 標記所有既有 migration 為已執行（不會實際執行 SQL）
python3 scripts/run_migrations.py --mark-all
```

### 7.3 日常更新流程

```bash
cd /opt/BeakPlatform
git pull

source venv/bin/activate
set -a && source .env && set +a

# 安裝新增的 Python 套件（如有）
pip install -r requirements.txt

# 查看待執行的 migration
python3 scripts/run_migrations.py --status

# 執行 migration
python3 scripts/run_migrations.py --run

# 同步模組選單與權限
cd backend
flask module sync

# 重啟服務
sudo systemctl restart beakplatform
```

### 7.4 run_migrations.py 指令參考

| 指令 | 說明 |
|------|------|
| `--status` | 顯示 migration 狀態（已執行/待執行） |
| `--scan` | 掃描所有 migration 檔案（不需 DB 連線） |
| `--run` | 依序執行待處理的 migration |
| `--mark-all` | 標記所有為已執行（baseline 用，不實際跑 SQL） |

### 7.5 注意事項

- Migration SQL 必須冪等（使用 `IF NOT EXISTS`、`ADD COLUMN IF NOT EXISTS`）
- 檔名含 `_drop_` 的視為 rollback 腳本，不會自動執行
- 執行失敗時會中斷並顯示錯誤，修正後重新 `--run` 即可（已成功的不會重跑）
- 資料庫表的 owner 必須與 `DATABASE_URL` 中的使用者一致，否則 DDL 操作會失敗

---

## 9. 疑難排解

### 問題: 登入後出現 InternalError / InFailedSqlTransaction

**原因:** 資料表結構不完整，通常是模組的表沒建出來。

**解法:**
```bash
cd /opt/BeakPlatform/backend
source /opt/BeakPlatform/venv/bin/activate
set -a && source /opt/BeakPlatform/.env && set +a

python3 -c "
import sys; sys.path.insert(0, '..')
from modules.form_workflow.models import *
from modules.nocode_builder.models import *
from app import create_app, db
app = create_app()
with app.app_context():
    db.create_all()
    print('Tables rebuilt')
"

sudo systemctl restart beakplatform
```

### 問題: Redis 連線失敗

**檢查:** Redis 是否運行在 port 6380。

```bash
redis-cli -p 6380 ping
# 預期回應: PONG
```

### 問題: PostgreSQL 連線失敗

**檢查:**
```bash
PGPASSWORD=postgres123 psql -h localhost -U beakplatform -d beakplatform_dev -c "SELECT 1;"
```

若失敗，檢查 `/etc/postgresql/16/main/pg_hba.conf` 是否允許本機密碼登入:
```
local   all   beakplatform   md5
host    all   beakplatform   127.0.0.1/32   scram-sha-256
```

修改後重啟: `sudo systemctl restart postgresql`

---

*本文件由 2026-03-09 首次部署測試產出，待乾淨環境驗證後更新。*
