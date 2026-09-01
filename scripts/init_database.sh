#!/bin/bash
# BeakPlatform 資料庫初始化腳本
# 用途：建立乾淨的資料庫（庫名取自本 repo 的 .env，可用環境變數 DB_NAME 覆寫）
#
# 使用方式：
#   sudo ./init_database.sh
#
# 路徑一律由腳本自身位置推導，同一份腳本可用於開發與正式環境，
# 不得再出現硬編碼的 /opt/BeakPlatform 或 /opt/BeakPlatform-dev。
#
# Schema 權威是 ORM model（db.create_all），不跑任何 migration（PF-168 起
# migration 制度廢止，歷史封存在 scripts/migrations/legacy/）。
# create_all 之外的 DB 物件與出廠資料由 scripts/sql/ 的檔案補齊：
#   fw_sp_setup.sql                     SqlExecutor 白名單 schema 與擁有權分離
#   seed_workflow_node_definitions.sql  節點型別定義（export_node_definitions_seed.py 產生）
#   seed_node_org_grants.sql            受限節點出廠授權（只給系統企業）
#   seed_menu_defaults.sql              選單出廠預設值（選配，原廠匯出才有）
#   seed_rbac_defaults.sql              RBAC 出廠預設值（選配，原廠匯出才有）
#
# 注意：此腳本會刪除現有資料庫！執行前務必確認第一行印出的庫名。

set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# 庫名優先序：環境變數 DB_NAME > 本 repo .env 的 DATABASE_URL > 保守預設
if [ -z "$DB_NAME" ]; then
    DB_NAME="$(grep -m1 '^DATABASE_URL=' "$REPO_ROOT/.env" 2>/dev/null \
        | sed -E 's#^DATABASE_URL=.*/([^/?[:space:]]+).*$#\1#')"
fi
DB_NAME="${DB_NAME:-beakplatform_dev}"
DB_USER="${DB_USER:-beakplatform}"
DB_PASS="${DB_PASS:-postgres123}"

echo "=== BeakPlatform 資料庫初始化 ==="
echo "    Repo: $REPO_ROOT"
echo "    資料庫: $DB_NAME"
echo ""

# 確認執行（環境變數 INIT_DB_YES=1 可跳過，供自動化驗證使用）
if [ "${INIT_DB_YES:-0}" != "1" ]; then
    read -p "警告：這將刪除現有的 $DB_NAME 資料庫！確定要繼續？(y/N) " confirm
    if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
        echo "已取消"
        exit 0
    fi
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

echo "5. 清除 session 目錄..."
rm -rf /tmp/beakplatform_sessions 2>/dev/null || true

echo "6. 設定管理員密碼..."
# 從環境變數或互動輸入取得密碼
if [ -n "$ADMIN_INITIAL_PASSWORD" ]; then
    ADMIN_PASS="$ADMIN_INITIAL_PASSWORD"
else
    while true; do
        read -s -p "請輸入系統管理員初始密碼 (至少 8 字元): " ADMIN_PASS
        echo ""
        if [ ${#ADMIN_PASS} -lt 8 ]; then
            echo "   密碼長度不足 8 字元，請重新輸入"
            continue
        fi
        read -s -p "請再輸入一次確認: " ADMIN_PASS_CONFIRM
        echo ""
        if [ "$ADMIN_PASS" != "$ADMIN_PASS_CONFIRM" ]; then
            echo "   兩次密碼不一致，請重新輸入"
            continue
        fi
        break
    done
fi

echo "7. 建立資料表 (db.create_all)..."
cd "$REPO_ROOT/backend"
source "$REPO_ROOT/venv/bin/activate"
set -a && source "$REPO_ROOT/.env" && set +a

# DATABASE_URL 一律跟隨 DB_NAME——沒有這行，DB_NAME 被覆寫時
# create_all 會打進 .env 指向的那個庫（通常是 dev 庫），靜默毀掉它
export DATABASE_URL="postgresql://$DB_USER:$DB_PASS@localhost:5432/$DB_NAME"

# SKIP_MODULE_SYNC 只跳過選單/權限同步；模組 models 仍會載入，
# 模組表由 create_all 一併建立（module_loader 的 models 載入步驟，PF-168）
SKIP_MODULE_SYNC=1 python3 << 'EOF'
from app import create_app, db
app = create_app()
with app.app_context():
    db.create_all()
    print("   資料表建立完成")
EOF

echo "8. 建立初始資料..."
SKIP_MODULE_SYNC=1 ADMIN_INITIAL_PASSWORD="$ADMIN_PASS" python3 << 'EOF'
import os, sys, bcrypt
from app import create_app, db
from app.models import Organization, User, UserType
from app.constants import SYSTEM_ORG_CODE

admin_password = os.environ.get('ADMIN_INITIAL_PASSWORD', '').strip()
if not admin_password or len(admin_password) < 8:
    print("   錯誤: 管理員密碼無效")
    sys.exit(1)

app = create_app()
with app.app_context():
    system_org = Organization(
        secure_code=SYSTEM_ORG_CODE,
        code='SYSTEM',
        name=SYSTEM_ORG_CODE,
        domain_name=SYSTEM_ORG_CODE,
        is_active=True,
        is_system_org=True
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
    print(f"   - 企業: {SYSTEM_ORG_CODE}")
    print(f"   - 管理員: admin@{SYSTEM_ORG_CODE} (首次登入須改密碼)")
EOF

echo "9. 建立 fw_sp schema 與擁有權分離..."
sudo -u postgres psql -d "$DB_NAME" -v ON_ERROR_STOP=1 -v app_user="$DB_USER" \
    -q -f "$REPO_ROOT/scripts/sql/fw_sp_setup.sql"

echo "10. 種入節點型別定義與受限節點出廠授權..."
sudo -u postgres psql -d "$DB_NAME" -v ON_ERROR_STOP=1 -v system_org="$SYSTEM_ORG_CODE" \
    -q -f "$REPO_ROOT/scripts/sql/seed_workflow_node_definitions.sql"
sudo -u postgres psql -d "$DB_NAME" -v ON_ERROR_STOP=1 \
    -q -f "$REPO_ROOT/scripts/sql/seed_node_org_grants.sql"

echo "11. 出廠預設值（存在才執行）..."
for seed in seed_menu_defaults.sql seed_rbac_defaults.sql; do
    if [ -f "$REPO_ROOT/scripts/sql/$seed" ]; then
        sudo -u postgres psql -d "$DB_NAME" -v ON_ERROR_STOP=1 -q \
            -f "$REPO_ROOT/scripts/sql/$seed"
        echo "   已執行 $seed"
    fi
done

echo "12. 初始化平台選單..."
python3 "$REPO_ROOT/scripts/init_menus.py" --force

echo "13. 同步模組選單與權限..."
(cd "$REPO_ROOT/backend" && flask module sync --force) || echo "   警告: 模組同步失敗，首次啟動服務時會自動再同步"

echo ""
echo "=== 初始化完成 ==="
echo ""
echo "系統企業代碼 (SYSTEM_ORG_CODE)： $SYSTEM_ORG_CODE"
echo "  日後忘記可查： grep SYSTEM_ORG_CODE $REPO_ROOT/.env"
echo ""
echo "管理員帳號："
echo "  帳號: admin@$SYSTEM_ORG_CODE"
echo "  密碼: (安裝時設定的密碼，首次登入須變更)"
echo ""
echo "啟動服務："
echo "  cd $REPO_ROOT/backend"
echo "  source $REPO_ROOT/venv/bin/activate"
echo "  set -a && source $REPO_ROOT/.env && set +a"
echo "  flask run --host=127.0.0.1 --port=7000"
