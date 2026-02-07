# BeakPlatform 安裝指南

本文件說明如何在全新的 Ubuntu 環境安裝 BeakPlatform。

---

## 系統需求

- **作業系統**: Ubuntu 22.04 LTS 或 24.04 LTS
- **記憶體**: 最低 2GB，建議 4GB+
- **硬碟**: 最低 10GB
- **網路**: 需要連接網際網路（安裝套件用）

---

## 快速安裝

```bash
# 1. 下載安裝腳本
curl -O http://192.168.0.16:3000/forgejoadmin/BeakPlatform/raw/branch/main/scripts/install.sh

# 2. 執行安裝
chmod +x install.sh
sudo ./install.sh
```

---

## 手動安裝步驟

### 1. 安裝系統依賴

```bash
sudo apt update
sudo apt install -y \
    python3.12 \
    python3.12-venv \
    python3-pip \
    postgresql \
    postgresql-contrib \
    nginx \
    git \
    curl
```

### 2. 設定 PostgreSQL

```bash
# 切換到 postgres 用戶
sudo -u postgres psql

# 在 psql 中執行：
CREATE USER beakplatform WITH PASSWORD 'postgres123';
CREATE DATABASE beakplatform_dev OWNER beakplatform;
GRANT ALL PRIVILEGES ON DATABASE beakplatform_dev TO beakplatform;
\q
```

### 3. 取得程式碼

```bash
# 建立目錄
sudo mkdir -p /opt/BeakPlatform
sudo chown $USER:$USER /opt/BeakPlatform

# Clone 程式碼
git clone http://192.168.0.16:3000/forgejoadmin/BeakPlatform.git /opt/BeakPlatform
cd /opt/BeakPlatform
```

### 4. 建立 Python 虛擬環境

```bash
python3.12 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r backend/requirements.txt
```

### 5. 設定環境變數

```bash
cp .env.example .env

# 編輯 .env，設定以下參數：
# DATABASE_URL=postgresql://beakplatform:postgres123@localhost/beakplatform_dev
# SECRET_KEY=your-secret-key-here
# FLASK_ENV=development
```

### 6. 初始化資料庫

```bash
cd backend
source ../venv/bin/activate
set -a && source ../.env && set +a

# 執行資料庫初始化
flask db upgrade
flask seed init
```

### 7. 啟動服務

```bash
# 開發模式
flask run --host=0.0.0.0 --port=7000

# 或使用 Gunicorn（生產模式）
gunicorn -w 4 -b 0.0.0.0:7000 "app:create_app()"
```

---

## 安裝模組

### 安裝 form_workflow 模組

```bash
cd /opt/BeakPlatform

# 1. 模組已包含在 modules/ 目錄中

# 2. 執行模組資料庫遷移
cd backend
source ../venv/bin/activate
set -a && source ../.env && set +a

psql -h localhost -U beakplatform -d beakplatform_dev -f ../modules/form_workflow/migrations/001_create_tables.sql
psql -h localhost -U beakplatform -d beakplatform_dev -f ../modules/form_workflow/migrations/002_add_subflow_columns.sql

# 3. 同步模組權限和選單
flask module sync

# 4. 重啟服務
```

---

## 驗證安裝

### 檢查服務狀態

```bash
# 檢查 Flask 是否正常
curl http://localhost:7000/api/form-workflow/info

# 預期回應：
# {"success": true, "data": {"name": "form_workflow", ...}}
```

### 檢查資料庫

```bash
psql -h localhost -U beakplatform -d beakplatform_dev -c "\dt fw_*"

# 預期顯示 7 個資料表：
# fw_form_templates
# fw_workflow_templates
# fw_form_instances
# fw_workflow_instances
# fw_approval_records
# fw_workflow_variables
# fw_node_execution_queue
```

### 登入測試

1. 開啟瀏覽器訪問 `http://YOUR_IP:7000/dev/quick-login`
2. 選擇企業和用戶
3. 點擊登入
4. 訪問 `http://YOUR_IP:7000/forms/` 確認模組頁面正常

---

## 常見問題

### Q: PostgreSQL 連線失敗

```bash
# 檢查 PostgreSQL 服務
sudo systemctl status postgresql

# 檢查連線設定
sudo nano /etc/postgresql/*/main/pg_hba.conf
# 確保有這行：
# local   all   beakplatform   md5
```

### Q: 模組未載入

```bash
# 檢查模組目錄
ls -la /opt/BeakPlatform/modules/

# 檢查模組 __init__.py
cat /opt/BeakPlatform/modules/form_workflow/__init__.py

# 重新同步模組
cd /opt/BeakPlatform/backend
flask module list
flask module sync
```

### Q: 權限不足

```bash
# 確保目錄權限正確
sudo chown -R $USER:$USER /opt/BeakPlatform
```

---

## Nginx 配置（可選）

```nginx
# /etc/nginx/sites-available/beakplatform
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:7000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    location /static {
        alias /opt/BeakPlatform/backend/app/static;
    }
}
```

啟用配置：
```bash
sudo ln -s /etc/nginx/sites-available/beakplatform /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

---

## Systemd 服務（可選）

```ini
# /etc/systemd/system/beakplatform.service
[Unit]
Description=BeakPlatform
After=network.target postgresql.service

[Service]
User=www-data
Group=www-data
WorkingDirectory=/opt/BeakPlatform/backend
Environment="PATH=/opt/BeakPlatform/venv/bin"
EnvironmentFile=/opt/BeakPlatform/.env
ExecStart=/opt/BeakPlatform/venv/bin/gunicorn -w 4 -b 127.0.0.1:7000 "app:create_app()"
Restart=always

[Install]
WantedBy=multi-user.target
```

啟用服務：
```bash
sudo systemctl daemon-reload
sudo systemctl enable beakplatform
sudo systemctl start beakplatform
```

---

*最後更新: 2026-01-24*
