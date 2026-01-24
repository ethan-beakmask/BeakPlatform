#!/bin/bash
#
# BeakPlatform 自動安裝腳本
# 適用於 Ubuntu 22.04/24.04 LTS
#
# 用法: sudo ./install.sh [選項]
#   --skip-db       跳過資料庫設定（使用已存在的資料庫）
#   --skip-nginx    跳過 Nginx 設定
#   --dev           開發模式（包含 DevTools）
#

set -e

# 顏色定義
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 預設值
INSTALL_DIR="/opt/BeakPlatform"
DB_NAME="beakplatform_dev"
DB_USER="beakplatform"
DB_PASS="postgres123"
FLASK_PORT=5009
SKIP_DB=false
SKIP_NGINX=false
DEV_MODE=true

# 解析參數
while [[ $# -gt 0 ]]; do
    case $1 in
        --skip-db)
            SKIP_DB=true
            shift
            ;;
        --skip-nginx)
            SKIP_NGINX=true
            shift
            ;;
        --dev)
            DEV_MODE=true
            shift
            ;;
        *)
            echo -e "${RED}未知參數: $1${NC}"
            exit 1
            ;;
    esac
done

echo -e "${BLUE}"
echo "╔═══════════════════════════════════════════════════════════╗"
echo "║           BeakPlatform 自動安裝腳本                       ║"
echo "╚═══════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# 檢查是否為 root
if [[ $EUID -ne 0 ]]; then
   echo -e "${YELLOW}建議以 root 執行此腳本${NC}"
   echo "繼續執行中..."
fi

# 檢查系統
echo -e "${BLUE}[1/8] 檢查系統...${NC}"
if ! grep -q "Ubuntu" /etc/os-release 2>/dev/null; then
    echo -e "${YELLOW}警告: 此腳本針對 Ubuntu 設計，其他系統可能需要調整${NC}"
fi

# 安裝系統依賴
echo -e "${BLUE}[2/8] 安裝系統依賴...${NC}"
apt-get update -qq
apt-get install -y -qq \
    python3 \
    python3-venv \
    python3-pip \
    postgresql \
    postgresql-contrib \
    nginx \
    git \
    curl \
    sudo

echo -e "${GREEN}✓ 系統依賴安裝完成${NC}"

# 設定 PostgreSQL
if [ "$SKIP_DB" = false ]; then
    echo -e "${BLUE}[3/8] 設定 PostgreSQL...${NC}"

    # 確保 PostgreSQL 運行
    systemctl start postgresql || true
    systemctl enable postgresql || true

    # 建立用戶和資料庫
    sudo -u postgres psql -c "CREATE USER $DB_USER WITH PASSWORD '$DB_PASS';" 2>/dev/null || echo "用戶已存在"
    sudo -u postgres psql -c "CREATE DATABASE $DB_NAME OWNER $DB_USER;" 2>/dev/null || echo "資料庫已存在"
    sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;"

    echo -e "${GREEN}✓ PostgreSQL 設定完成${NC}"
else
    echo -e "${YELLOW}[3/8] 跳過 PostgreSQL 設定${NC}"
fi

# 取得程式碼
echo -e "${BLUE}[4/8] 取得程式碼...${NC}"
if [ -d "$INSTALL_DIR/.git" ]; then
    echo "目錄已存在，執行 git pull..."
    cd "$INSTALL_DIR"
    git pull origin main || true
else
    mkdir -p "$INSTALL_DIR"
    git clone http://192.168.0.16:3000/forgejoadmin/BeakPlatform.git "$INSTALL_DIR" || {
        echo -e "${RED}無法從 Forgejo clone，嘗試本地複製...${NC}"
        if [ -d "/opt/BeakPlatform" ] && [ "$INSTALL_DIR" != "/opt/BeakPlatform" ]; then
            cp -r /opt/BeakPlatform/* "$INSTALL_DIR/"
        fi
    }
fi
echo -e "${GREEN}✓ 程式碼取得完成${NC}"

# 建立虛擬環境
echo -e "${BLUE}[5/8] 建立 Python 虛擬環境...${NC}"
cd "$INSTALL_DIR"
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip -q
pip install -r backend/requirements.txt -q
echo -e "${GREEN}✓ Python 環境建立完成${NC}"

# 設定環境變數
echo -e "${BLUE}[6/8] 設定環境變數...${NC}"
if [ ! -f "$INSTALL_DIR/.env" ]; then
    cat > "$INSTALL_DIR/.env" << EOF
# BeakPlatform 環境變數
FLASK_APP=app
FLASK_ENV=development
SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")

# 資料庫
DATABASE_URL=postgresql://$DB_USER:$DB_PASS@localhost/$DB_NAME

# 開發工具
ENABLE_DEV_TOOLS=true
DEV_ALLOWED_IPS=127.0.0.1,192.168.0.0/16,10.0.0.0/8
EOF
    echo -e "${GREEN}✓ 環境變數設定完成${NC}"
else
    echo -e "${YELLOW}✓ .env 已存在，跳過${NC}"
fi

# 初始化資料庫
echo -e "${BLUE}[7/8] 初始化資料庫...${NC}"
cd "$INSTALL_DIR/backend"
source ../venv/bin/activate
set -a && source ../.env && set +a

# 執行平台資料庫遷移
flask db upgrade 2>/dev/null || echo "DB upgrade 跳過或已完成"

# 執行種子資料
flask seed init 2>/dev/null || echo "Seed 跳過或已完成"

# 執行模組資料庫遷移
echo "執行 FormWorkflow 模組遷移..."
PGPASSWORD=$DB_PASS psql -h localhost -U $DB_USER -d $DB_NAME -f ../modules/form_workflow/migrations/001_create_tables.sql 2>/dev/null || echo "表格已存在"
PGPASSWORD=$DB_PASS psql -h localhost -U $DB_USER -d $DB_NAME -f ../modules/form_workflow/migrations/002_add_subflow_columns.sql 2>/dev/null || echo "欄位已存在"

# 同步模組
flask module sync 2>/dev/null || echo "模組同步跳過"

echo -e "${GREEN}✓ 資料庫初始化完成${NC}"

# 設定 Nginx
if [ "$SKIP_NGINX" = false ]; then
    echo -e "${BLUE}[8/8] 設定 Nginx...${NC}"

    cat > /etc/nginx/sites-available/beakplatform << EOF
server {
    listen 80;
    server_name _;

    location / {
        proxy_pass http://127.0.0.1:$FLASK_PORT;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    location /static {
        alias $INSTALL_DIR/backend/app/static;
        expires 1d;
    }
}
EOF

    ln -sf /etc/nginx/sites-available/beakplatform /etc/nginx/sites-enabled/
    rm -f /etc/nginx/sites-enabled/default 2>/dev/null || true
    nginx -t && systemctl reload nginx

    echo -e "${GREEN}✓ Nginx 設定完成${NC}"
else
    echo -e "${YELLOW}[8/8] 跳過 Nginx 設定${NC}"
fi

# 完成
echo ""
echo -e "${GREEN}"
echo "╔═══════════════════════════════════════════════════════════╗"
echo "║               安裝完成！                                  ║"
echo "╚═══════════════════════════════════════════════════════════╝"
echo -e "${NC}"
echo ""
echo "啟動服務:"
echo "  cd $INSTALL_DIR/backend"
echo "  source ../venv/bin/activate"
echo "  set -a && source ../.env && set +a"
echo "  flask run --host=0.0.0.0 --port=$FLASK_PORT"
echo ""
echo "訪問:"
echo "  開發工具: http://YOUR_IP:$FLASK_PORT/dev/quick-login"
echo "  表單模組: http://YOUR_IP:$FLASK_PORT/forms/"
echo ""
echo "預設帳號:"
echo "  系統管理員: admin@system.local / admin123"
echo ""
