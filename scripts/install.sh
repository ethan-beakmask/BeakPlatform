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
FLASK_PORT=7000
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
    # 生成隨機系統企業識別碼 (每套部署不同)
    SYS_ORG_CODE=$(python3 -c "import secrets; print('sys-' + secrets.token_hex(6))")
    cat > "$INSTALL_DIR/.env" << EOF
# BeakPlatform 環境變數
FLASK_APP=app
FLASK_ENV=development
SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")

# 系統企業識別碼 (每套部署唯一，勿變更)
SYSTEM_ORG_CODE=$SYS_ORG_CODE

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

# 設定管理員密碼
echo -e "${BLUE}[7/9] 設定管理員密碼...${NC}"
if [ -n "$ADMIN_INITIAL_PASSWORD" ]; then
    ADMIN_PASS="$ADMIN_INITIAL_PASSWORD"
    echo -e "${GREEN}  使用環境變數 ADMIN_INITIAL_PASSWORD${NC}"
else
    while true; do
        read -s -p "請輸入系統管理員初始密碼 (至少 8 字元): " ADMIN_PASS
        echo ""
        if [ ${#ADMIN_PASS} -lt 8 ]; then
            echo -e "${RED}  密碼長度不足 8 字元，請重新輸入${NC}"
            continue
        fi
        read -s -p "請再輸入一次確認: " ADMIN_PASS_CONFIRM
        echo ""
        if [ "$ADMIN_PASS" != "$ADMIN_PASS_CONFIRM" ]; then
            echo -e "${RED}  兩次密碼不一致，請重新輸入${NC}"
            continue
        fi
        break
    done
fi

# 初始化資料庫
echo -e "${BLUE}[8/9] 初始化資料庫...${NC}"
cd "$INSTALL_DIR/backend"
source ../venv/bin/activate
set -a && source ../.env && set +a

# 清除舊的 session 目錄（避免權限問題）
echo "清除 session 目錄..."
rm -rf /tmp/beakplatform_sessions 2>/dev/null || true

# 使用 Python 建立資料表（跳過模組同步，因為系統企業還沒建立）
echo "建立平台資料表..."
SKIP_MODULE_SYNC=1 python3 << 'PYEOF'
from app import create_app, db
app = create_app()
with app.app_context():
    db.create_all()
    print("   資料表建立完成")
PYEOF

# 建立初始資料（跳過模組同步）
echo "建立初始資料..."
SKIP_MODULE_SYNC=1 ADMIN_INITIAL_PASSWORD="$ADMIN_PASS" python3 << 'PYEOF'
import os, sys, bcrypt
from app import create_app, db
from app.models import Organization, User, UserType
from app.constants import SYSTEM_ORG_CODE

admin_password = os.environ.get('ADMIN_INITIAL_PASSWORD', '').strip()

app = create_app()
with app.app_context():
    existing = Organization.query.filter_by(domain_name=SYSTEM_ORG_CODE).first()
    if existing:
        print("   初始資料已存在，跳過")
    else:
        if not admin_password or len(admin_password) < 8:
            print("   錯誤: 管理員密碼無效")
            sys.exit(1)

        system_org = Organization(
            secure_code=SYSTEM_ORG_CODE,
            code='SYSTEM',
            name=SYSTEM_ORG_CODE,
            domain_name=SYSTEM_ORG_CODE,
            is_active=True
        )
        db.session.add(system_org)
        db.session.flush()

        password = admin_password.encode('utf-8')
        salt = bcrypt.gensalt()
        password_hash = bcrypt.hashpw(password, salt).decode('utf-8')

        admin = User(
            org_secure_code=SYSTEM_ORG_CODE,
            username='admin',
            email=f'admin@{SYSTEM_ORG_CODE}',
            display_name='系統管理員',
            password_hash=password_hash,
            user_type=UserType.SYSTEM_ADMIN,
            is_active=True,
            must_change_password=True
        )
        db.session.add(admin)
        db.session.commit()
        print("   初始資料建立完成")
PYEOF

# 執行模組資料庫遷移
echo "執行 FormWorkflow 模組遷移..."
PGPASSWORD=$DB_PASS psql -h localhost -U $DB_USER -d $DB_NAME -f ../modules/form_workflow/migrations/001_create_tables.sql 2>/dev/null || echo "   表格已存在"
PGPASSWORD=$DB_PASS psql -h localhost -U $DB_USER -d $DB_NAME -f ../modules/form_workflow/migrations/002_add_subflow_columns.sql 2>/dev/null || echo "   欄位已存在"

# 同步模組權限和選單
flask module sync 2>/dev/null || echo "   模組同步跳過"

# 初始化平台選單
echo "初始化平台選單..."
python3 ../scripts/init_menus.py --force 2>/dev/null || echo "   選單初始化跳過"

echo -e "${GREEN}✓ 資料庫初始化完成${NC}"

# 設定 Nginx
if [ "$SKIP_NGINX" = false ]; then
    echo -e "${BLUE}[9/9] 設定 Nginx...${NC}"

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
    echo -e "${YELLOW}[9/9] 跳過 Nginx 設定${NC}"
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
echo "管理員帳號:"
echo "  系統管理員: admin@\$SYSTEM_ORG_CODE (安裝時設定的密碼，首次登入須變更)"
echo ""
