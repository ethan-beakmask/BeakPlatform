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
#   BEAK_PORT              BeakPlatform 存取 port (預設: 8000，被佔用時自動找空 port)
#   ADMIN_INITIAL_PASSWORD 管理員初始密碼 (不設定則互動式輸入)
#   GITHUB_TOKEN           GitHub Personal Access Token (不設定則互動式輸入)
#   GITHUB_REPO            GitHub clone URL (預設: https://github.com/ethan-beakmask/BeakPlatform.git)
# =============================================================================
set -e

# === 設定 ===
INSTALL_DIR="${INSTALL_DIR:-/opt/BeakPlatform}"
DB_NAME="${DB_NAME:-beakplatform}"
DB_USER="${DB_USER:-beakplatform}"
DB_PASS="${DB_PASS:-postgres123}"
BEAK_PORT="${BEAK_PORT:-8000}"
GITHUB_REPO="${GITHUB_REPO:-https://github.com/ethan-beakmask/BeakPlatform.git}"
SERVICE_NAME="beakplatform"
SERVICE_USER="beakplatform"
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

# 檢查 port 是否被佔用（0=空閒, 1=佔用）
is_port_in_use() {
    ss -tlnH "sport = :$1" 2>/dev/null | grep -q . && return 0
    return 1
}

# 從指定 port 開始找一個空閒 port
find_free_port() {
    local port=$1
    local max_try=100
    local i=0
    while [ $i -lt $max_try ]; do
        if ! is_port_in_use "$port"; then
            echo "$port"
            return 0
        fi
        port=$((port + 1))
        i=$((i + 1))
    done
    return 1
}

# 解析 port：檢查用戶指定的 BEAK_PORT，佔用則自動找空 port
# 同時設定 NGINX_PORT（外部）和 APP_PORT（內部 Gunicorn）
resolve_ports() {
    NGINX_PORT="$BEAK_PORT"

    if is_port_in_use "$NGINX_PORT"; then
        local new_port
        new_port=$(find_free_port "$NGINX_PORT")
        if [ -z "$new_port" ]; then
            log_error "無法找到可用的 port（從 $NGINX_PORT 開始搜尋）"
            exit 1
        fi
        log_warn "Port $NGINX_PORT 已被佔用，自動改用 port $new_port"
        NGINX_PORT="$new_port"
    fi

    # Gunicorn 內部 port = NGINX_PORT + 1，綁 127.0.0.1
    APP_PORT=$((NGINX_PORT + 1))
    if is_port_in_use "$APP_PORT"; then
        APP_PORT=$(find_free_port "$((NGINX_PORT + 2))")
        if [ -z "$APP_PORT" ]; then
            log_error "無法找到 Gunicorn 內部可用 port"
            exit 1
        fi
    fi

    # APP_PREFIX 預設 /beakplatform（與 Python 端 __init__.py 一致）
    local health_prefix="${APP_PREFIX:-/beakplatform}"
    HEALTH_URL="http://localhost:${APP_PORT}${health_prefix}/health"
}

health_check() {
    log_info "健康檢查 (等待最多 ${HEALTH_TIMEOUT}s)..."
    local elapsed=0
    while [ $elapsed -lt $HEALTH_TIMEOUT ]; do
        if curl -sf "$HEALTH_URL" 2>/dev/null | grep -q '"healthy"'; then
            log_info "健康檢查通過"
            # 穩定性驗證：等 5 秒後確認服務仍在運行
            sleep 5
            if systemctl is-active --quiet "$SERVICE_NAME"; then
                log_info "服務穩定性驗證通過"
                return 0
            else
                log_error "服務在健康檢查後崩潰"
                log_warn "最近日誌:"
                journalctl -u "$SERVICE_NAME" -n 20 --no-pager 2>/dev/null || true
                return 1
            fi
        fi
        sleep 3
        elapsed=$((elapsed + 3))
        printf "."
    done
    echo ""
    log_error "健康檢查逾時 (${HEALTH_TIMEOUT}s)"
    log_warn "最近日誌:"
    journalctl -u "$SERVICE_NAME" -n 20 --no-pager 2>/dev/null || true
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

ensure_service_user() {
    if ! id -u "$SERVICE_USER" >/dev/null 2>&1; then
        useradd --system --home-dir "$INSTALL_DIR" --no-create-home --shell /usr/sbin/nologin "$SERVICE_USER"
        log_info "系統帳號 $SERVICE_USER 已建立"
    fi
}

fix_ownership() {
    chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"
    # 確保 log 目錄可寫（1777 sticky bit，允許多帳號寫入但不能互刪）
    mkdir -p /opt/tmp
    chown "$SERVICE_USER:$SERVICE_USER" /opt/tmp
    chmod 1777 /opt/tmp
}

# 以應用帳號身分執行指令（載入 venv + .env）
run_as_app() {
    sudo -u "$SERVICE_USER" bash -c "
        set -a; source '$INSTALL_DIR/.env'; set +a
        export PATH='$INSTALL_DIR/venv/bin':\$PATH
        export HOME='$INSTALL_DIR'
        cd '$INSTALL_DIR'
        $1
    "
}

# Schema 權威是 ORM model（db.create_all），migration 制度已廢止（PF-168，
# 歷史封存在 scripts/migrations/legacy/）。create_all 之外的 DB 物件與
# 出廠資料由 scripts/sql/ 的檔案補齊，全部冪等，安裝與更新共用。
# 前置：資料庫與系統企業已存在。
apply_db_extras() {
    local sys_org
    sys_org=$(grep -m1 '^SYSTEM_ORG_CODE=' "$INSTALL_DIR/.env" | cut -d'=' -f2-)
    if [ -z "$sys_org" ]; then
        log_error ".env 缺少 SYSTEM_ORG_CODE，無法種入出廠資料"
        return 1
    fi
    sudo -u postgres psql -d "$DB_NAME" -v ON_ERROR_STOP=1 -v app_user="$DB_USER" \
        -q -f "$INSTALL_DIR/scripts/sql/fw_sp_setup.sql"
    sudo -u postgres psql -d "$DB_NAME" -v ON_ERROR_STOP=1 -v system_org="$sys_org" \
        -q -f "$INSTALL_DIR/scripts/sql/seed_workflow_node_definitions.sql"
    sudo -u postgres psql -d "$DB_NAME" -v ON_ERROR_STOP=1 \
        -q -f "$INSTALL_DIR/scripts/sql/seed_node_org_grants.sql"
    local seed
    for seed in seed_menu_defaults.sql seed_rbac_defaults.sql; do
        if [ -f "$INSTALL_DIR/scripts/sql/$seed" ]; then
            sudo -u postgres psql -d "$DB_NAME" -v ON_ERROR_STOP=1 -q \
                -f "$INSTALL_DIR/scripts/sql/$seed"
        fi
    done
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
        echo "  BEAK_PORT=$BEAK_PORT (存取 port，預設 8000，被佔用時自動找空 port)"
        echo "  GITHUB_TOKEN=<GitHub PAT> (不設定則互動式輸入)"
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

    exit 0
fi


# =========================================================================
#  --start
# =========================================================================
if [ "$ACTION" = "start" ]; then
    check_root
    # 從已安裝的 .env 讀取 Gunicorn port 與 APP_PREFIX，設定 health check URL
    local_app_port=$(grep '^GUNICORN_BIND=' "$INSTALL_DIR/.env" 2>/dev/null | sed 's/.*://' || echo "")
    local_app_prefix=$(grep '^APP_PREFIX=' "$INSTALL_DIR/.env" 2>/dev/null | cut -d'=' -f2- || echo "")
    HEALTH_URL="http://localhost:${local_app_port:-8001}${local_app_prefix:-/beakplatform}/health"
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


    # 移除安裝目錄
    rm -rf "$INSTALL_DIR"

    # 移除系統帳號
    if id -u "$SERVICE_USER" >/dev/null 2>&1; then
        userdel "$SERVICE_USER" 2>/dev/null || true
        log_info "系統帳號 $SERVICE_USER 已移除"
    fi

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

    # 允許 root 操作非 root 擁有的 repo
    git config --global --add safe.directory "$INSTALL_DIR" 2>/dev/null || true

    # 檢查 remote URL 是否帶有 token（能自動認證）
    current_url=$(git remote get-url origin 2>/dev/null)
    if ! echo "$current_url" | grep -q '@github.com'; then
        # remote URL 不含 token，需要取得
        if [ -z "${GITHUB_TOKEN:-}" ]; then
            read -s -p "請輸入 GitHub Personal Access Token: " GITHUB_TOKEN
            echo ""
            if [ -z "$GITHUB_TOKEN" ]; then
                log_error "未輸入 Token，無法繼續"
                exit 1
            fi
        fi
        git remote set-url origin "https://${GITHUB_TOKEN}@${GITHUB_REPO#https://}"
    fi

    git fetch origin main
    local_hash=$(git rev-parse HEAD)
    remote_hash=$(git rev-parse origin/main)

    if [ "$local_hash" = "$remote_hash" ]; then
        log_info "程式碼已是最新版本 ($(git log --oneline -1))"
        log_info "仍會執行 schema 同步與出廠資料補種（冪等），修復上次可能中斷的更新"
    else
        git reset --hard origin/main
        log_info "更新至: $(git log --oneline -1)"
    fi

    # 確保服務帳號存在 + 修正檔案所有權
    ensure_service_user
    fix_ownership

    # [2] 更新 Python 依賴（以應用帳號執行）
    log_step "2/6" "更新 Python 依賴..."
    sudo -u "$SERVICE_USER" "$INSTALL_DIR/venv/bin/pip" install --upgrade pip -q
    sudo -u "$SERVICE_USER" "$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/backend/requirements.txt" -q

    # [2.5] 補齊舊版 .env 缺少的檔案加密設定（冪等）
    if ! grep -q '^ENCRYPTION_MASTER_KEY=' "$INSTALL_DIR/.env" 2>/dev/null; then
        log_warn ".env 缺少 ENCRYPTION_MASTER_KEY，自動產生..."
        NEW_EMK=$(python3 -c "import os, base64; print(base64.urlsafe_b64encode(os.urandom(32)).decode())")
        {
            echo ""
            echo "# 檔案加密 (FILE-01) - AES-256-GCM Master Key，遺失將無法解密既有加密附件"
            echo "ENCRYPTION_MASTER_KEY=$NEW_EMK"
        } >> "$INSTALL_DIR/.env"
    fi
    if ! grep -q '^ENCRYPTED_STORAGE_DIR=' "$INSTALL_DIR/.env" 2>/dev/null; then
        echo "ENCRYPTED_STORAGE_DIR=$INSTALL_DIR/backend/encrypted_storage" >> "$INSTALL_DIR/.env"
    fi
    mkdir -p "$INSTALL_DIR/backend/encrypted_storage"
    chown "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR/backend/encrypted_storage"
    chmod 700 "$INSTALL_DIR/backend/encrypted_storage"

    # [3] 同步資料庫 schema 與出廠資料
    #     model 即權威：create_all 只補「新表」，不改既有表的欄位。
    #     欄位級的升級機制目前刻意不存在（尚無任何已公開的既有環境需要升級），
    #     公開後首次需要時另行設計，不要回頭復活 run_migrations。
    log_step "3/6" "同步資料庫 schema 與出廠資料..."
    sudo -u postgres psql -d "$DB_NAME" -c "CREATE EXTENSION IF NOT EXISTS pgcrypto;" 2>/dev/null || true
    run_as_app "cd backend && EXECUTOR_STANDALONE=1 SKIP_MODULE_SYNC=1 python3 ../scripts/db_create_all.py"
    apply_db_extras

    # [4] 初始化選單與權限 (冪等)
    log_step "4/6" "同步選單與權限..."
    run_as_app "EXECUTOR_STANDALONE=1 python3 scripts/init_menus.py" || log_warn "選單初始化跳過"
    run_as_app "EXECUTOR_STANDALONE=1 python3 scripts/init_permissions.py" || log_warn "權限初始化跳過"

    # [5] 同步模組
    log_step "5/6" "同步模組..."
    run_as_app "cd backend && EXECUTOR_STANDALONE=1 FLASK_ENV=${FLASK_ENV:-production} flask module sync" 2>/dev/null || log_warn "模組同步跳過"

    # [6] 重啟服務
    log_step "6/6" "重啟服務..."
    # 從已安裝的 .env 讀取 Gunicorn port 與 APP_PREFIX，設定 health check URL
    local_app_port=$(grep '^GUNICORN_BIND=' "$INSTALL_DIR/.env" 2>/dev/null | sed 's/.*://' || echo "")
    local_app_prefix=$(grep '^APP_PREFIX=' "$INSTALL_DIR/.env" 2>/dev/null | cut -d'=' -f2- || echo "")
    HEALTH_URL="http://localhost:${local_app_port:-8001}${local_app_prefix:-/beakplatform}/health"
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

# 解析 port（檢查佔用，自動分配）
resolve_ports

echo "  安裝目錄: $INSTALL_DIR"
echo "  資料庫:   $DB_NAME"
echo "  Port:     $NGINX_PORT (Nginx) / $APP_PORT (Gunicorn internal)"
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
log_step "1/9" "檢查系統依賴..."

REQUIRED_PKGS=(python3 python3-venv python3-pip postgresql postgresql-contrib redis-server nginx git curl sudo)
MISSING_PKGS=()

for pkg in "${REQUIRED_PKGS[@]}"; do
    if dpkg -l "$pkg" 2>/dev/null | grep -q "^ii"; then
        printf "  %-25s %s\n" "$pkg" "OK"
    else
        printf "  %-25s %s\n" "$pkg" "缺少"
        MISSING_PKGS+=("$pkg")
    fi
done

if [ ${#MISSING_PKGS[@]} -eq 0 ]; then
    log_info "所有系統依賴已安裝，跳過"
else
    log_info "需要安裝: ${MISSING_PKGS[*]}"
    # apt-get update 加 120 秒 timeout，避免在封閉網路無限等待
    timeout 120 apt-get update -q || log_warn "apt update 逾時或失敗，嘗試直接安裝..."
    apt-get install -y -q "${MISSING_PKGS[@]}"
fi

# 確保服務啟動
systemctl enable --now postgresql 2>/dev/null || true
systemctl enable --now redis-server 2>/dev/null || true
systemctl enable --now nginx 2>/dev/null || true

log_info "系統依賴安裝完成"

# 建立應用服務帳號
ensure_service_user


# === [2/9] PostgreSQL ===
log_step "2/9" "設定 PostgreSQL..."

sudo -u postgres psql -c "CREATE USER $DB_USER WITH PASSWORD '$DB_PASS';" 2>/dev/null || true
sudo -u postgres psql -c "ALTER USER $DB_USER WITH PASSWORD '$DB_PASS';" 2>/dev/null || true

# 全新安裝：先清除舊 DB 再建立（避免殘留資料衝突）
# 斷開所有連線後再 DROP，並驗證結果
sudo -u postgres psql -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='$DB_NAME' AND pid <> pg_backend_pid();" > /dev/null 2>&1 || true
sleep 1
if ! sudo -u postgres psql -c "DROP DATABASE IF EXISTS $DB_NAME;" 2>/dev/null; then
    log_error "無法刪除資料庫 $DB_NAME（可能有程式佔用連線）"
    log_error "請先停止所有連線此資料庫的程式，再重新執行安裝"
    exit 1
fi
sudo -u postgres psql -c "CREATE DATABASE $DB_NAME OWNER $DB_USER;" 2>/dev/null
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;" 2>/dev/null

# 啟用必要的 PostgreSQL extensions
sudo -u postgres psql -d "$DB_NAME" -c "CREATE EXTENSION IF NOT EXISTS pgcrypto;" 2>/dev/null
log_info "PostgreSQL 設定完成 (DB: $DB_NAME)"


# === [3/9] 取得程式碼 ===
log_step "3/9" "取得程式碼..."

# 取得 GitHub Token（私有 repo 必須）
if [ -z "${GITHUB_TOKEN:-}" ]; then
    echo ""
    echo "  BeakPlatform 使用私有 GitHub 儲存庫，需要 Personal Access Token (PAT) 才能下載。"
    echo "  產生方式: GitHub → Settings → Developer settings → Personal access tokens"
    echo "  權限需求: Fine-grained token，僅授本 repo 的 Contents: Read-only"
    echo ""
    read -s -p "請輸入 GitHub Personal Access Token: " GITHUB_TOKEN
    echo ""
    if [ -z "$GITHUB_TOKEN" ]; then
        log_error "未輸入 Token，無法繼續"
        exit 1
    fi
fi

# 組成帶 token 的 clone URL
GITHUB_CLONE_URL="https://${GITHUB_TOKEN}@${GITHUB_REPO#https://}"

# 允許 root 操作非 root 擁有的 repo（覆蓋安裝時目錄已 chown 給 service user）
git config --global --add safe.directory "$INSTALL_DIR" 2>/dev/null || true

if [ -d "$INSTALL_DIR/.git" ]; then
    cd "$INSTALL_DIR"

    # 更新 remote URL（token 可能已變更）
    git remote set-url origin "$GITHUB_CLONE_URL"

    # 拉取最新版本並同步（force push 環境下本地 commit 必然脫離 remote 歷史，直接 reset）
    git fetch origin main 2>/dev/null
    git reset --hard origin/main
    log_info "程式碼已同步至最新版本"
else
    if [ -d "$INSTALL_DIR" ]; then
        # 目錄存在但不是 git repo，備份後重新 clone
        mv "$INSTALL_DIR" "${INSTALL_DIR}.bak.$(date +%s)"
        log_warn "既有目錄已備份"
    fi
    git clone "$GITHUB_CLONE_URL" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
    log_info "程式碼 clone 完成: $(git log --oneline -1)"
fi

# 修正檔案所有權（git 以 root clone/reset，需轉移給應用帳號）
fix_ownership


# === [4/9] Python 虛擬環境 ===
log_step "4/9" "建立 Python 虛擬環境..."
cd "$INSTALL_DIR"
sudo -u "$SERVICE_USER" python3 -m venv "$INSTALL_DIR/venv"
sudo -u "$SERVICE_USER" "$INSTALL_DIR/venv/bin/pip" install --upgrade pip -q
sudo -u "$SERVICE_USER" "$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/backend/requirements.txt" -q
log_info "Python 環境建立完成"


# === [5/9] 環境變數 ===
log_step "5/9" "設定環境變數..."

SYS_ORG_CODE=$(python3 -c "import secrets; print('sys-' + secrets.token_hex(6))")
SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
ENCRYPTION_MASTER_KEY=$(python3 -c "import os, base64; print(base64.urlsafe_b64encode(os.urandom(32)).decode())")

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

# URL 前綴 (Nginx location / DispatcherMiddleware 路徑)
APP_PREFIX=/beakplatform

# 資料庫
DATABASE_URL=postgresql://$DB_USER:$DB_PASS@localhost/$DB_NAME

# Redis
REDIS_URL=redis://localhost:6379/0

# Rate Limiting (速率限制)
# RATELIMIT_DEFAULT: 全站 API 總量上限 (每日/每分鐘，已登入用戶 per-user、未登入 per-IP)
# RATELIMIT_LOGIN: 登入端點限制 (per-IP，防暴力破解)
# RATELIMIT_FORGOT_PASSWORD: 忘記密碼端點限制 (per-IP)
# RATELIMIT_RESET_PASSWORD: 重設密碼端點限制 (per-IP)
RATELIMIT_ENABLED=true
RATELIMIT_DEFAULT="200000 per day;6000 per minute"
RATELIMIT_LOGIN="50 per minute"
RATELIMIT_FORGOT_PASSWORD="30 per hour"
RATELIMIT_RESET_PASSWORD="50 per hour"

# Gunicorn
GUNICORN_BIND=127.0.0.1:${APP_PORT}
GUNICORN_WORKERS=3
GUNICORN_THREADS=2

# Session
SESSION_COOKIE_SECURE=false

# 檔案加密 (FILE-01) - AES-256-GCM Master Key，遺失將無法解密既有加密附件
ENCRYPTION_MASTER_KEY=$ENCRYPTION_MASTER_KEY
ENCRYPTED_STORAGE_DIR=$INSTALL_DIR/backend/encrypted_storage
ENVEOF

mkdir -p "$INSTALL_DIR/backend/encrypted_storage"
chown "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR/backend/encrypted_storage"
chmod 700 "$INSTALL_DIR/backend/encrypted_storage"

chown "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR/.env"
chmod 600 "$INSTALL_DIR/.env"
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

# 清除舊 session（Redis + filesystem）
# 必須清 Redis，否則舊 session 可跨安裝穿越，繼承前一套系統的登入狀態
redis-cli FLUSHDB > /dev/null 2>&1 || log_warn "Redis FLUSHDB 失敗，請手動清除"
rm -rf /tmp/beakplatform_sessions* /tmp/beakplatform_test_sessions* 2>/dev/null || true

# 建立資料表 + 初始資料（以應用帳號執行，避免產生 root 擁有的暫存檔）
# EXECUTOR_STANDALONE=1 防止 workflow executor 背景線程啟動查詢尚未建立的表
# SKIP_MODULE_SYNC=1 避免 create_app 在表建立前嘗試同步模組產生大量錯誤訊息
INIT_SCRIPT=$(mktemp)
cat > "$INIT_SCRIPT" << 'PYEOF'
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
            is_active=True,
            is_system_org=True
        )
        db.session.add(system_org)
        db.session.flush()

        # 建立系統企業的預設角色（鑰匙2 需要這些角色才能建立 MRR）
        from app.services.organization_service import OrganizationService
        OrganizationService._create_default_roles(system_org)
        db.session.flush()
        print("  預設角色建立完成")

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
chmod 644 "$INIT_SCRIPT"
sudo -u "$SERVICE_USER" env \
    ADMIN_INITIAL_PASSWORD="$ADMIN_PASS" \
    SKIP_MODULE_SYNC=1 \
    EXECUTOR_STANDALONE=1 \
    PYTHONPATH="$INSTALL_DIR/backend" \
    HOME="$INSTALL_DIR" \
    bash -c "
        set -a; source '$INSTALL_DIR/.env'; set +a
        cd '$INSTALL_DIR/backend'
        '$INSTALL_DIR/venv/bin/python3' '$INIT_SCRIPT'
    "
rm -f "$INIT_SCRIPT"

# create_all 之外的 DB 物件（fw_sp schema／擁有權分離）與出廠資料
#（節點型別定義、受限節點授權、出廠預設值）
apply_db_extras

# 初始化選單
run_as_app "EXECUTOR_STANDALONE=1 python3 scripts/init_menus.py --force" || log_warn "選單初始化跳過"

# 初始化權限
run_as_app "EXECUTOR_STANDALONE=1 python3 scripts/init_permissions.py" || log_warn "權限初始化跳過"

# 同步模組
run_as_app "cd backend && EXECUTOR_STANDALONE=1 FLASK_ENV=production flask module sync" 2>/dev/null || log_warn "模組同步跳過"

# 種入系統企業出廠資料（角色權限、ORG_ADMIN 帳號、編號規則、Key2 等，冪等）
run_as_app "cd backend && EXECUTOR_STANDALONE=1 SKIP_MODULE_SYNC=1 ADMIN_INITIAL_PASSWORD='$ADMIN_PASS' python3 ../scripts/seed_system_org_defaults.py" || log_warn "系統企業出廠資料種入失敗，可事後手動執行 scripts/seed_system_org_defaults.py"

log_info "資料庫初始化完成"


# === [8/9] systemd 服務 ===
log_step "8/9" "設定 systemd 服務..."

cat > "/etc/systemd/system/${SERVICE_NAME}.service" << SVCEOF
[Unit]
Description=BeakPlatform Gunicorn Service
After=network.target postgresql.service redis-server.service
Requires=postgresql.service redis-server.service

[Service]
Type=exec
User=$SERVICE_USER
Group=$SERVICE_USER
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

# 自動偵測 server IP（供 nginx server_name 和完成訊息使用）
SERVER_IP=$(ip -4 route get 8.8.8.8 2>/dev/null | awk '/src/ {print $7; exit}')
SERVER_IP="${SERVER_IP:-$(hostname -I 2>/dev/null | awk '{print $1}')}"
SERVER_IP="${SERVER_IP:-$(hostname -f 2>/dev/null)}"

cat > "/etc/nginx/sites-available/$SERVICE_NAME" << 'NGXEOF'
upstream beakplatform {
    server 127.0.0.1:APP_PORT_PLACEHOLDER;
}

server {
    listen NGINX_PORT_PLACEHOLDER;
    server_name SERVER_NAME_PLACEHOLDER;

    client_max_body_size 20M;

    # Security headers
    add_header X-Frame-Options SAMEORIGIN always;
    add_header X-Content-Type-Options nosniff always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy strict-origin-when-cross-origin always;

    location / {
        proxy_pass http://beakplatform;
        proxy_http_version 1.1;
        proxy_set_header Host $http_host;
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

# 替換 placeholders
sed -i "s/APP_PORT_PLACEHOLDER/${APP_PORT}/" "/etc/nginx/sites-available/$SERVICE_NAME"
sed -i "s/NGINX_PORT_PLACEHOLDER/${NGINX_PORT}/" "/etc/nginx/sites-available/$SERVICE_NAME"
sed -i "s/SERVER_NAME_PLACEHOLDER/${SERVER_IP}/" "/etc/nginx/sites-available/$SERVICE_NAME"

ln -sf "/etc/nginx/sites-available/$SERVICE_NAME" "/etc/nginx/sites-enabled/"

# 移除可能衝突的舊站台設定（僅限 BeakPlatform 前身，不動用戶的其他設定）
for old_conf in beakmask; do
    if [ -f "/etc/nginx/sites-enabled/$old_conf" ]; then
        rm -f "/etc/nginx/sites-enabled/$old_conf"
        log_warn "移除舊 Nginx 設定: $old_conf"
    fi
done

nginx -t && systemctl reload nginx
log_info "Nginx 設定完成 (port $NGINX_PORT -> Gunicorn $APP_PORT)"


# === 啟動服務 ===
log_info "啟動 BeakPlatform..."
systemctl restart "$SERVICE_NAME"

health_check

# 讀取部署資訊
deployed_org_code=$(grep '^SYSTEM_ORG_CODE=' "$INSTALL_DIR/.env" | cut -d'=' -f2-)

# 組裝 URL（port 80 不顯示 port，其他 port 要帶上）
if [ "$NGINX_PORT" = "80" ]; then
    DISPLAY_URL="http://$SERVER_IP"
else
    DISPLAY_URL="http://$SERVER_IP:$NGINX_PORT"
fi

# 種入系統對外網址（URL-02：未設定時領取頁等處只會顯示「尚未設定」，
# 安裝當下就知道正確值，直接種入；已設定的不覆蓋，管理員可在
# /hostconfig/server-settings 調整）
sudo -u postgres psql -d "$DB_NAME" -q -c "
INSERT INTO system_settings (secure_code, key, value, value_type, category, created_at, updated_at, is_deleted)
SELECT substr(md5(random()::text),1,22), 'system_base_url', '$DISPLAY_URL', 'string', 'general',
       now() AT TIME ZONE 'UTC', now() AT TIME ZONE 'UTC', false
WHERE NOT EXISTS (SELECT 1 FROM system_settings WHERE key='system_base_url' AND is_deleted=false);
" 2>/dev/null || log_warn "system_base_url 種入失敗，可事後在 /hostconfig/server-settings 設定"

echo ""
echo "============================================"
log_info "全新安裝完成"
echo ""
echo "  URL:  $DISPLAY_URL"
echo ""
echo "  系統企業: $deployed_org_code"
echo "  管理員:   admin@$deployed_org_code"
echo "  密碼:     (安裝時設定，首次登入須變更)"
echo ""
echo "  首次登入會被強制導向初始設定頁（無法略過），說明文件："
echo "    $INSTALL_DIR/docs/install/first_login.html"
echo "    （用瀏覽器直接開，不需要平台在執行中）"
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
