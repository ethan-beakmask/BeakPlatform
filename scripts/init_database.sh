#!/bin/bash
# BeakPlatform 資料庫初始化腳本
# 用途：建立乾淨的 beakplatform_dev 資料庫
#
# 使用方式：
#   sudo ./init_database.sh
#
# 注意：此腳本會刪除現有的 beakplatform_dev 資料庫！

set -e

DB_NAME="beakplatform_dev"
DB_USER="beakplatform"
DB_PASS="postgres123"

echo "=== BeakPlatform 資料庫初始化 ==="
echo ""

# 確認執行
read -p "警告：這將刪除現有的 $DB_NAME 資料庫！確定要繼續？(y/N) " confirm
if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
    echo "已取消"
    exit 0
fi

echo ""
echo "1. 建立用戶 $DB_USER..."
sudo -u postgres psql -c "CREATE USER $DB_USER WITH PASSWORD '$DB_PASS';" 2>/dev/null || echo "   用戶已存在"

echo "2. 刪除舊資料庫..."
sudo -u postgres psql -c "DROP DATABASE IF EXISTS $DB_NAME;"

echo "3. 建立新資料庫..."
sudo -u postgres psql -c "CREATE DATABASE $DB_NAME OWNER $DB_USER;"

echo "4. 授權..."
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;"

echo "5. 執行 Flask 資料庫遷移..."
cd /opt/BeakPlatform/backend
source /opt/BeakPlatform/venv/bin/activate
set -a && source ../.env && set +a

# 使用 Flask-Migrate 或直接建立表
python3 << 'EOF'
from app import create_app, db
app = create_app()
with app.app_context():
    db.create_all()
    print("   資料表建立完成")
EOF

echo "6. 建立初始資料..."
python3 << 'EOF'
import bcrypt
from app import create_app, db
from app.models import Organization, User, UserType

app = create_app()
with app.app_context():
    # 建立 system.local 企業
    system_org = Organization(
        secure_code='system.local',
        code='SYSTEM',
        name='system.local',
        domain_name='system.local',
        is_active=True
    )
    db.session.add(system_org)
    db.session.flush()

    # 使用 bcrypt 產生密碼 hash
    password = 'admin123'.encode('utf-8')
    salt = bcrypt.gensalt()
    password_hash = bcrypt.hashpw(password, salt).decode('utf-8')

    # 建立系統管理員
    admin = User(
        org_secure_code='system.local',
        username='admin',
        email='admin@system.local',
        display_name='系統管理員',
        password_hash=password_hash,
        user_type=UserType.SYSTEM_ADMIN,
        is_active=True,
        must_change_password=True
    )
    db.session.add(admin)
    db.session.commit()

    print("   初始資料建立完成")
    print("   - 企業: system.local")
    print("   - 管理員: admin@system.local / admin123")
EOF

echo ""
echo "=== 初始化完成 ==="
echo ""
echo "預設帳號："
echo "  帳號: admin@system.local"
echo "  密碼: admin123"
echo ""
echo "啟動服務："
echo "  cd /opt/BeakPlatform/backend"
echo "  source /opt/BeakPlatform/venv/bin/activate"
echo "  set -a && source ../.env && set +a"
echo "  flask run --host=0.0.0.0 --port=7000"
