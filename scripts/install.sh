#!/bin/bash
# =============================================================================
# BeakPlatform 安裝與升級腳本
# 適用於 Ubuntu 22.04/24.04 LTS
# =============================================================================
# 用法:
#   sudo bash install.sh                         全新安裝 (互動式設定密碼)
#   sudo bash install.sh --update                升級更新 (保留資料)
#   sudo bash install.sh --status                查看服務狀態
#   sudo bash install.sh --start                 啟動服務
#   sudo bash install.sh --stop                  停止服務
#   sudo bash install.sh --uninstall             移除安裝
#
# 環境變數 (可選):
#   INSTALL_DIR            安裝目錄 (預設: /opt/BeakPlatform)
#   DB_NAME                資料庫名稱 (預設: beakplatform)
#   DB_USER                資料庫使用者 (預設: beakplatform)
#   DB_PASS                資料庫密碼 (預設: postgres123)
#   APP_PORT               應用程式 port (預設: 8000)
#   ADMIN_INITIAL_PASSWORD 管理員初始密碼 (不設定則互動式輸入)
#   GITHUB_REPO            GitHub clone URL (預設: https://github.com/beakplatform/BeakPlatform.git)
# =============================================================================
set -e

# === 設定 ===
INSTALL_DIR="${INSTALL_DIR:-/opt/BeakPlatform}"
DB_NAME="${DB_NAME:-beakplatform}"
DB_USER="${DB_USER:-beakplatform}"
DB_PASS="${DB_PASS:-postgres123}"
APP_PORT="${APP_PORT:-8000}"
GITHUB_REPO="${GITHUB_REPO:-https://github.com/beakplatform/BeakPlatform.git}"
SERVICE_NAME="beakplatform"
HEALTH_URL="http://localhost:${APP_PORT}/health"
HEALTH_TIMEOUT=60

# === 顏色 ===
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_step()  { echo -e "${BLUE}[$1]${NC} $2"; }

# === 共用函式 ===

check_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "此腳本需要 root 權限執行"
        echo "  用法: sudo bash $0 $*"
        exit 1
    fi
}

check_ubuntu() {
    if ! grep -q "Ubuntu" /etc/os-release 2>/dev/null; then
        log_warn "此腳本針對 Ubuntu 22.04/24.04 設計，其他系統可能需要調整"
    fi
}

health_check() {
    log_info "健康檢查 (等待最多 ${HEALTH_TIMEOUT}s)..."
    local elapsed=0
    while [ $elapsed -lt $HEALTH_TIMEOUT ]; do
        if curl -sf "$HEALTH_URL" 2>/dev/null | grep -q '"healthy"'; then
            log_info "健康檢查通過"
            return 0
        fi
        sleep 3
        elapsed=$((elapsed + 3))
        printf "."
    done
    echo ""
    log_error "健康檢查逾時 (${HEALTH_TIMEOUT}s)"
    log_warn "檢查服務日誌: journalctl -u ${SERVICE_NAME} -n 50"
    return 1
}

load_env() {
    if [ -f "$INSTALL_DIR/.env" ]; then
        set -a
        source "$INSTALL_DIR/.env"
        set +a
    fi
}

activate_venv() {
    source "$INSTALL_DIR/venv/bin/activate"
}

# === 參數處理 ===
ACTION="fresh"

case "${1:-}" in
    --update)    ACTION="update" ;;
    --status)    ACTION="status" ;;
    --start)     ACTION="start" ;;
    --stop)      ACTION="stop" ;;
    --uninstall) ACTION="uninstall" ;;
    "")          ACTION="fresh" ;;
    *)
        echo "BeakPlatform 安裝與升級腳本"
        echo ""
        echo "用法:"
        echo "  sudo bash install.sh                  全新安裝"
        echo "  sudo bash install.sh --update         升級更新 (保留資料)"
        echo "  sudo bash install.sh --status         查看服務狀態"
        echo "  sudo bash install.sh --start          啟動服務"
        echo "  sudo bash install.sh --stop           停止服務"
        echo "  sudo bash install.sh --uninstall      移除安裝"
        echo ""
        echo "環境變數:"
        echo "  INSTALL_DIR=$INSTALL_DIR"
        echo "  DB_NAME=$DB_NAME"
        echo "  APP_PORT=$APP_PORT"
        echo "  GITHUB_REPO=$GITHUB_REPO"
        exit 1
        ;;
esac


# =========================================================================
#  --status
# =========================================================================
if [ "$ACTION" = "status" ]; then
    echo "=== BeakPlatform 服務狀態 ==="
    echo ""

    # systemd service
    if systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
        log_info "服務狀態: 運行中"
        systemctl status "$SERVICE_NAME" --no-pager -l 2>/dev/null | head -15
    else
        log_warn "服務狀態: 未運行"
    fi

    echo ""

    # 健康檢查
    if curl -sf "$HEALTH_URL" 2>/dev/null | grep -q '"healthy"'; then
        log_info "健康檢查: 正常"
    else
        log_warn "健康檢查: 無回應"
    fi

    # Nginx
    echo ""
    if systemctl is-active --quiet nginx 2>/dev/null; then
        log_info "Nginx: 運行中"
    else
        log_warn "Nginx: 未運行"
    fi

    # Redis
    if systemctl is-active --quiet redis-server 2>/dev/null; then
        log_info "Redis: 運行中"
    else
        log_warn "Redis: 未運行"
    fi

    # PostgreSQL
    if systemctl is-active --quiet postgresql 2>/dev/null; then
        log_info "PostgreSQL: 運行中"
    else
        log_warn "PostgreSQL: 未運行"
    fi

    # Migration 狀態
    if [ -d "$INSTALL_DIR" ] && [ -f "$INSTALL_DIR/.env" ]; then
        echo ""
        cd "$INSTALL_DIR"
        activate_venv
        load_env
        cd backend
        python3 ../scripts/run_migrations.py --status 2>/dev/null || true
    fi

    exit 0
fi


# =========================================================================
#  --start
# =========================================================================
if [ "$ACTION" = "start" ]; then
    check_root
    log_info "啟動 BeakPlatform..."
    systemctl start "$SERVICE_NAME"
    health_check
    exit 0
fi


# =========================================================================
#  --stop
# =========================================================================
if [ "$ACTION" = "stop" ]; then
    check_root
    log_info "停止 BeakPlatform..."
    systemctl stop "$SERVICE_NAME"
    log_info "服務已停止"
    exit 0
fi


# =========================================================================
#  --uninstall
# =========================================================================
if [ "$ACTION" = "uninstall" ]; then
    check_root
    echo "=== BeakPlatform 移除 ==="
    echo ""
    log_warn "此操作將移除:"
    echo "  - systemd 服務 ($SERVICE_NAME)"
    echo "  - Nginx 設定"
    echo "  - 安裝目錄 ($INSTALL_DIR)"
    echo "  - 資料庫 ($DB_NAME)"
    echo ""
    read -p "確定要移除嗎？(輸入 YES 確認): " CONFIRM
    if [ "$CONFIRM" != "YES" ]; then
        echo "取消移除"
        exit 0
    fi

    # 停止服務
    systemctl stop "$SERVICE_NAME" 2>/dev/null || true
    systemctl disable "$SERVICE_NAME" 2>/dev/null || true
    rm -f "/etc/systemd/system/${SERVICE_NAME}.service"
    systemctl daemon-reload

    # 移除 Nginx 設定
    rm -f "/etc/nginx/sites-enabled/$SERVICE_NAME"
    rm -f "/etc/nginx/sites-available/$SERVICE_NAME"
    systemctl reload nginx 2>/dev/null || true

    # 移除資料庫
    sudo -u postgres psql -c "DROP DATABASE IF EXISTS $DB_NAME;" 2>/dev/null || true
    # 附屬 DB
    sudo -u postgres psql -c "DROP DATABASE IF EXISTS beakform_data;" 2>/dev/null || true

    # 移除安裝目錄
    rm -rf "$INSTALL_DIR"

    log_info "移除完成"
    exit 0
fi


# =========================================================================
#  --update 升級更新
# =========================================================================
if [ "$ACTION" = "update" ]; then
    check_root

    echo "============================================"
    echo "  BeakPlatform 升級更新"
    echo "============================================"

    if [ ! -d "$INSTALL_DIR/.git" ]; then
        log_error "安裝目錄不存在或不是 git repo: $INSTALL_DIR"
        log_error "請先執行全新安裝: sudo bash install.sh"
        exit 1
    fi

    cd "$INSTALL_DIR"

    # [1] 拉取最新程式碼
    log_step "1/6" "拉取最新程式碼..."
    git fetch origin main
    local_hash=$(git rev-parse HEAD)
    remote_hash=$(git rev-parse origin/main)

    if [ "$local_hash" = "$remote_hash" ]; then
        log_info "程式碼已是最新版本 ($(git log --oneline -1))"
        echo "如需強制重新初始化，請使用全新安裝"
        exit 0
    fi

    git reset --hard origin/main
    log_info "更新至: $(git log --oneline -1)"

    # [2] 更新 Python 依賴
    log_step "2/6" "更新 Python 依賴..."
    activate_venv
    pip install --upgrade pip -q
    pip install -r backend/requirements.txt -q

    # [3] 載入環境變數 + 執行 migrations
    log_step "3/6" "執行資料庫遷移..."
    load_env
    # 確保必要的 PostgreSQL extensions 存在
    sudo -u postgres psql -d "$DB_NAME" -c "CREATE EXTENSION IF NOT EXISTS pgcrypto;" 2>/dev/null || true
    cd backend
    EXECUTOR_STANDALONE=1 python3 ../scripts/run_migrations.py --run

    # [4] 初始化選單與權限 (冪等)
    log_step "4/6" "同步選單與權限..."
    cd "$INSTALL_DIR"
    EXECUTOR_STANDALONE=1 python3 scripts/init_menus.py || log_warn "選單初始化跳過"
    EXECUTOR_STANDALONE=1 python3 scripts/init_permissions.py || log_warn "權限初始化跳過"

    # [5] 同步模組
    log_step "5/6" "同步模組..."
    cd "$INSTALL_DIR/backend"
    EXECUTOR_STANDALONE=1 FLASK_ENV=${FLASK_ENV:-production} flask module sync 2>/dev/null || log_warn "模組同步跳過"

    # [6] 重啟服務
    log_step "6/6" "重啟服務..."
    systemctl restart "$SERVICE_NAME"

    health_check

    echo ""
    echo "============================================"
    log_info "升級更新完成"
    echo "  版本: $(cd "$INSTALL_DIR" && git log --oneline -1)"
    echo "============================================"
    exit 0
fi


# =========================================================================
#  全新安裝
# =========================================================================
check_root
check_ubuntu

echo "============================================"
echo "  BeakPlatform 全新安裝"
echo "============================================"
echo ""
echo "  安裝目錄: $INSTALL_DIR"
echo "  資料庫:   $DB_NAME"
echo "  Port:     $APP_PORT"
echo "  來源:     $GITHUB_REPO"
echo ""

# 如果目錄已存在且有 .env，警告
if [ -f "$INSTALL_DIR/.env" ]; then
    log_warn "偵測到既有安裝: $INSTALL_DIR"
    read -p "要覆蓋安裝嗎？既有資料將被清除 (y/N): " OVERWRITE
    if [[ ! "$OVERWRITE" =~ ^[yY]$ ]]; then
        echo "取消安裝。如需升級請用: sudo bash install.sh --update"
        exit 0
    fi
    # 停掉舊服務
    systemctl stop "$SERVICE_NAME" 2>/dev/null || true
    # 備份舊 .env（含手動調整的設定）
    cp "$INSTALL_DIR/.env" "$INSTALL_DIR/.env.bak.$(date +%s)"
    log_info "已備份舊 .env"
fi


# === [1/9] 系統依賴 ===
log_step "1/9" "安裝系統依賴..."
apt-get update -qq || log_warn "部分 apt 來源無法更新，繼續安裝..."
apt-get install -y -qq \
    python3 \
    python3-venv \
    python3-pip \
    postgresql \
    postgresql-contrib \
    redis-server \
    nginx \
    git \
    curl \
    sudo

# 確保服務啟動
systemctl enable --now postgresql 2>/dev/null || true
systemctl enable --now redis-server 2>/dev/null || true
systemctl enable --now nginx 2>/dev/null || true

log_info "系統依賴安裝完成"


# === [2/9] PostgreSQL ===
log_step "2/9" "設定 PostgreSQL..."

sudo -u postgres psql -c "CREATE USER $DB_USER WITH PASSWORD '$DB_PASS';" 2>/dev/null || true

# 全新安裝：先清除舊 DB 再建立（避免殘留資料衝突）
# 斷開所有連線後再 DROP，並驗證結果
for target_db in "$DB_NAME" "beakform_data"; do
    sudo -u postgres psql -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='$target_db' AND pid <> pg_backend_pid();" > /dev/null 2>&1 || true
    sleep 1
    if ! sudo -u postgres psql -c "DROP DATABASE IF EXISTS $target_db;" 2>/dev/null; then
        log_error "無法刪除資料庫 $target_db（可能有程式佔用連線）"
        log_error "請先停止所有連線此資料庫的程式，再重新執行安裝"
        exit 1
    fi
    sudo -u postgres psql -c "CREATE DATABASE $target_db OWNER $DB_USER;" 2>/dev/null
    if [ "$target_db" = "$DB_NAME" ]; then
        sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE $target_db TO $DB_USER;" 2>/dev/null
    fi
done

# 啟用必要的 PostgreSQL extensions
sudo -u postgres psql -d "$DB_NAME" -c "CREATE EXTENSION IF NOT EXISTS pgcrypto;" 2>/dev/null
log_info "PostgreSQL 設定完成 (DB: $DB_NAME + beakform_data)"


# === [3/9] 取得程式碼 ===
log_step "3/9" "取得程式碼..."

if [ -d "$INSTALL_DIR/.git" ]; then
    cd "$INSTALL_DIR"

    # 安全檢查：如果有未 push 的 commit，警告用戶
    git fetch origin main 2>/dev/null
    local_ahead=$(git rev-list --count origin/main..HEAD 2>/dev/null || echo "0")
    if [ "$local_ahead" -gt 0 ]; then
        log_warn "偵測到 $local_ahead 個未 push 的 commit:"
        git log --oneline origin/main..HEAD
        read -p "繼續將會 reset 到 remote 版本，這些 commit 會遺失。繼續？(y/N): " CONFIRM_RESET
        if [[ ! "$CONFIRM_RESET" =~ ^[yY]$ ]]; then
            log_error "取消安裝"
            exit 1
        fi
    fi

    git reset --hard origin/main
    log_info "程式碼已更新: $(git log --oneline -1)"
else
    if [ -d "$INSTALL_DIR" ]; then
        # 目錄存在但不是 git repo，備份後重新 clone
        mv "$INSTALL_DIR" "${INSTALL_DIR}.bak.$(date +%s)"
        log_warn "既有目錄已備份"
    fi
    git clone "$GITHUB_REPO" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
    log_info "程式碼 clone 完成: $(git log --oneline -1)"
fi


# === [4/9] Python 虛擬環境 ===
log_step "4/9" "建立 Python 虛擬環境..."
cd "$INSTALL_DIR"
python3 -m venv venv
activate_venv
pip install --upgrade pip -q
pip install -r backend/requirements.txt -q
log_info "Python 環境建立完成"


# === [5/9] 環境變數 ===
log_step "5/9" "設定環境變數..."

SYS_ORG_CODE=$(python3 -c "import secrets; print('sys-' + secrets.token_hex(6))")
SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")

cat > "$INSTALL_DIR/.env" << ENVEOF
# BeakPlatform 環境設定
# 自動產生於 $(date '+%Y-%m-%d %H:%M')
FLASK_APP=app
FLASK_ENV=production

# 系統企業識別碼 (每套部署唯一，勿變更)
SYSTEM_ORG_CODE=$SYS_ORG_CODE

# 應用程式
SECRET_KEY=$SECRET_KEY
ENABLE_DEV_TOOLS=false

# 資料庫
DATABASE_URL=postgresql://$DB_USER:$DB_PASS@localhost/$DB_NAME

# Redis
REDIS_URL=redis://localhost:6379/0

# Rate Limiting
RATELIMIT_ENABLED=true
RATELIMIT_DEFAULT="200 per day;50 per hour"
RATELIMIT_LOGIN="30 per minute"

# Gunicorn
GUNICORN_BIND=127.0.0.1:${APP_PORT}
GUNICORN_WORKERS=3
GUNICORN_THREADS=2

# Session
SESSION_COOKIE_SECURE=false

# Form Data Sync
FORMDATA_DATABASE_URL=postgresql://$DB_USER:$DB_PASS@localhost/beakform_data
ENVEOF

log_info "環境變數設定完成 (SYSTEM_ORG_CODE=$SYS_ORG_CODE)"


# === [6/9] 管理員密碼 ===
log_step "6/9" "設定管理員密碼..."

if [ -n "${ADMIN_INITIAL_PASSWORD:-}" ]; then
    ADMIN_PASS="$ADMIN_INITIAL_PASSWORD"
    log_info "使用環境變數 ADMIN_INITIAL_PASSWORD"
else
    while true; do
        read -s -p "請輸入系統管理員初始密碼 (至少 8 字元): " ADMIN_PASS
        echo ""
        if [ ${#ADMIN_PASS} -lt 8 ]; then
            log_error "密碼長度不足 8 字元，請重新輸入"
            continue
        fi
        read -s -p "請再輸入一次確認: " ADMIN_PASS_CONFIRM
        echo ""
        if [ "$ADMIN_PASS" != "$ADMIN_PASS_CONFIRM" ]; then
            log_error "兩次密碼不一致，請重新輸入"
            continue
        fi
        break
    done
fi


# === [7/9] 初始化資料庫 ===
log_step "7/9" "初始化資料庫..."
cd "$INSTALL_DIR/backend"
load_env

# 清除舊 session
rm -rf /tmp/beakplatform_sessions 2>/dev/null || true

# 建立資料表 + 初始資料
# EXECUTOR_STANDALONE=1 防止 workflow executor 背景線程啟動查詢尚未建立的表
# SKIP_MODULE_SYNC=1 避免 create_app 在表建立前嘗試同步模組產生大量錯誤訊息
SKIP_MODULE_SYNC=1 EXECUTOR_STANDALONE=1 ADMIN_INITIAL_PASSWORD="$ADMIN_PASS" python3 << 'PYEOF'
import os, sys, bcrypt, importlib
from pathlib import Path
from app import create_app, db
from app.models import Organization, User, UserType
from app.constants import SYSTEM_ORG_CODE

admin_password = os.environ.get('ADMIN_INITIAL_PASSWORD', '').strip()

app = create_app()
with app.app_context():
    # 顯式載入所有模組 models，確保 db.create_all() 能建立模組表
    # app.root_path = <INSTALL_DIR>/backend/app，往上兩層到專案根目錄
    modules_dir = Path(app.root_path).parent.parent / 'modules'
    if modules_dir.exists():
        for mod_dir in sorted(modules_dir.iterdir()):
            models_init = mod_dir / 'models' / '__init__.py'
            if models_init.exists():
                mod_name = mod_dir.name
                try:
                    importlib.import_module(f'modules.{mod_name}.models')
                    print(f"  載入模組 models: {mod_name}")
                except Exception as e:
                    print(f"  警告: 載入 {mod_name} models 失敗: {e}")

    # 建立所有資料表（含平台 + 模組）
    db.create_all()
    print("  資料表建立完成")

    # 檢查是否已有初始資料（用 code='SYSTEM' 檢查，不受 SYSTEM_ORG_CODE 變動影響）
    existing = Organization.query.filter_by(code='SYSTEM').first()
    if existing:
        print(f"  初始資料已存在 (secure_code={existing.secure_code})，跳過")
    else:
        if not admin_password or len(admin_password) < 8:
            print("  錯誤: 管理員密碼無效")
            sys.exit(1)

        # 建立系統企業
        system_org = Organization(
            secure_code=SYSTEM_ORG_CODE,
            code='SYSTEM',
            name=SYSTEM_ORG_CODE,
            domain_name=SYSTEM_ORG_CODE,
            is_active=True
        )
        db.session.add(system_org)
        db.session.flush()

        # 建立管理員
        password = admin_password.encode('utf-8')
        salt = bcrypt.gensalt()
        password_hash = bcrypt.hashpw(password, salt).decode('utf-8')

        admin = User(
            org_secure_code=SYSTEM_ORG_CODE,
            username='admin',
            email=f'admin@{SYSTEM_ORG_CODE}',
            display_name='System Admin',
            password_hash=password_hash,
            user_type=UserType.SYSTEM_ADMIN,
            is_active=True,
            must_change_password=True
        )
        db.session.add(admin)
        db.session.commit()
        print("  初始資料建立完成")
PYEOF

# 執行所有 migrations（冪等，db.create_all 已建的表會被 IF NOT EXISTS 跳過）
# 確保非 ORM 管理的表（如 timeout_trackers、workflow_node_categories）也被建立
cd "$INSTALL_DIR"
EXECUTOR_STANDALONE=1 python3 scripts/run_migrations.py --run

# 初始化選單
EXECUTOR_STANDALONE=1 python3 scripts/init_menus.py --force || log_warn "選單初始化跳過"

# 初始化權限
EXECUTOR_STANDALONE=1 python3 scripts/init_permissions.py || log_warn "權限初始化跳過"

# 同步模組
cd "$INSTALL_DIR/backend"
EXECUTOR_STANDALONE=1 FLASK_ENV=production flask module sync 2>/dev/null || log_warn "模組同步跳過"

log_info "資料庫初始化完成"


# === [8/9] systemd 服務 ===
log_step "8/9" "設定 systemd 服務..."

cat > "/etc/systemd/system/${SERVICE_NAME}.service" << SVCEOF
[Unit]
Description=BeakPlatform Gunicorn Service
After=network.target postgresql.service redis-server.service
Requires=postgresql.service redis-server.service

[Service]
Type=notify
User=root
Group=root
WorkingDirectory=$INSTALL_DIR/backend
EnvironmentFile=$INSTALL_DIR/.env
ExecStart=$INSTALL_DIR/venv/bin/gunicorn -c gunicorn.conf.py wsgi:application
ExecReload=/bin/kill -s HUP \$MAINPID
Restart=on-failure
RestartSec=5
KillMode=mixed
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
SVCEOF

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
log_info "systemd 服務已建立: ${SERVICE_NAME}.service"


# === [9/9] Nginx ===
log_step "9/9" "設定 Nginx..."

cat > "/etc/nginx/sites-available/$SERVICE_NAME" << 'NGXEOF'
upstream beakplatform {
    server 127.0.0.1:APP_PORT_PLACEHOLDER;
}

server {
    listen 80;
    server_name _;

    client_max_body_size 20M;

    # Security headers
    add_header X-Frame-Options SAMEORIGIN always;
    add_header X-Content-Type-Options nosniff always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy strict-origin-when-cross-origin always;

    location / {
        proxy_pass http://beakplatform;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 30s;
        proxy_read_timeout 60s;
        proxy_send_timeout 60s;
    }

    location /static/ {
        proxy_pass http://beakplatform;
        expires 7d;
        add_header Cache-Control "public, immutable";
    }

    location /health {
        proxy_pass http://beakplatform;
        access_log off;
    }
}
NGXEOF

# 替換 port placeholder
sed -i "s/APP_PORT_PLACEHOLDER/${APP_PORT}/" "/etc/nginx/sites-available/$SERVICE_NAME"

ln -sf "/etc/nginx/sites-available/$SERVICE_NAME" "/etc/nginx/sites-enabled/"
rm -f /etc/nginx/sites-enabled/default 2>/dev/null || true

# 移除可能衝突的舊站台設定
for old_conf in beakmask; do
    if [ -f "/etc/nginx/sites-enabled/$old_conf" ]; then
        rm -f "/etc/nginx/sites-enabled/$old_conf"
        log_warn "移除舊 Nginx 設定: $old_conf"
    fi
done

nginx -t && systemctl reload nginx
log_info "Nginx 設定完成 (port 80 -> $APP_PORT)"


# === 啟動服務 ===
log_info "啟動 BeakPlatform..."
systemctl restart "$SERVICE_NAME"

health_check

# 讀取部署資訊
deployed_org_code=$(grep '^SYSTEM_ORG_CODE=' "$INSTALL_DIR/.env" | cut -d'=' -f2-)

echo ""
echo "============================================"
log_info "全新安裝完成"
echo ""
echo "  URL:  http://YOUR_SERVER_IP (Nginx port 80)"
echo "        http://YOUR_SERVER_IP:$APP_PORT (直連 Gunicorn)"
echo ""
echo "  系統企業: $deployed_org_code"
echo "  管理員:   admin@$deployed_org_code"
echo "  密碼:     (安裝時設定，首次登入須變更)"
echo ""
echo "  服務管理:"
echo "    sudo bash $INSTALL_DIR/scripts/install.sh --status"
echo "    sudo bash $INSTALL_DIR/scripts/install.sh --update"
echo "    sudo bash $INSTALL_DIR/scripts/install.sh --stop"
echo "    sudo bash $INSTALL_DIR/scripts/install.sh --start"
echo ""
echo "  日誌查看:"
echo "    journalctl -u $SERVICE_NAME -f"
echo "============================================"
