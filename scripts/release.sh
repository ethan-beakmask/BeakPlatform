#!/bin/bash
# =============================================================================
# release.sh - BeakPlatform 發行部署（三模式）
# =============================================================================
# 模式:
#   bash scripts/release.sh              全新安裝（刪除舊資料，模擬首次安裝）
#   bash scripts/release.sh --update     升級更新（保留資料，跑 migrations）
#   bash scripts/release.sh --clone-db   複製開發 DB 到 Docker（含 SECRET_KEY 同步）
#   bash scripts/release.sh --status     查看公開環境狀態
#   bash scripts/release.sh --stop       停止公開環境
#   bash scripts/release.sh --rebuild    強制重建 Docker image（全新安裝 + no-cache）
# =============================================================================
set -e

# === 設定 ===
DEV_DIR="/opt/BeakPlatform"
RELEASE_DIR="/opt/BeakPlatform-release"
GITHUB_REMOTE="github"
GITHUB_CLONE_URL="git@github.com-beakplatform:beakplatform/BeakPlatform.git"
DOCKER_COMPOSE_DIR="deploy"
HEALTH_URL="http://localhost:8000/health"
HEALTH_TIMEOUT=120
DEV_ENV_FILE="$DEV_DIR/.env"
DOCKER_ENV_FILE="$RELEASE_DIR/$DOCKER_COMPOSE_DIR/.env.production"
COMPOSE_CMD="docker compose --env-file .env.production"

# === 顏色 ===
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# === 共用函式 ===
health_check() {
    log_info "健康檢查 (等待最多 ${HEALTH_TIMEOUT}s)..."
    local elapsed=0
    while [ $elapsed -lt $HEALTH_TIMEOUT ]; do
        if curl -s "$HEALTH_URL" 2>/dev/null | grep -q '"healthy"'; then
            log_info "健康檢查通過"
            return 0
        fi
        sleep 3
        elapsed=$((elapsed + 3))
        printf "."
    done
    echo ""
    log_error "健康檢查逾時 (${HEALTH_TIMEOUT}s)"
    log_warn "檢查 Docker logs: cd $RELEASE_DIR/$DOCKER_COMPOSE_DIR && $COMPOSE_CMD logs app"
    return 1
}

push_and_pull() {
    # 確認開發環境狀態
    log_info "檢查開發環境..."
    cd "$DEV_DIR"

    local current_branch
    current_branch=$(git branch --show-current)
    if [ "$current_branch" != "main" ]; then
        log_error "必須在 main 分支執行 (目前: $current_branch)"
        exit 1
    fi

    if ! git diff --quiet || ! git diff --cached --quiet; then
        log_error "工作區有未提交的變更，請先 commit"
        exit 1
    fi

    # 推送到 Forgejo
    log_info "推送到 Forgejo..."
    git push origin main 2>&1 | tail -3

    # 過濾推送到 GitHub
    log_info "過濾推送到 GitHub..."
    bash scripts/push_github.sh

    # 準備發行目錄
    log_info "準備發行目錄..."
    if [ -d "$RELEASE_DIR/.git" ]; then
        cd "$RELEASE_DIR"
        git fetch origin
        git reset --hard origin/main
    else
        log_info "首次 clone 從 GitHub..."
        git clone "$GITHUB_CLONE_URL" "$RELEASE_DIR"
        cd "$RELEASE_DIR"
    fi
    log_info "發行目錄 HEAD: $(git log --oneline -1)"
}

ensure_env_file() {
    # 確認 .env.production 存在
    if [ ! -f "$DOCKER_ENV_FILE" ]; then
        log_info "建立 .env.production..."
        local secret_key db_pass
        secret_key=$(python3 -c "import secrets; print(secrets.token_hex(32))")
        db_pass="postgres123"

        cat > "$DOCKER_ENV_FILE" << ENVEOF
# BeakPlatform Release Environment
# 自動產生於 $(date '+%Y-%m-%d %H:%M')

# Database
DB_PASSWORD=$db_pass
DATABASE_URL=postgresql://beakplatform:${db_pass}@db:5432/beakplatform_dev

# Redis
REDIS_URL=redis://redis:6379/0

# Admin (首次啟動自動建立)
ADMIN_INITIAL_PASSWORD=Admin1234

# Application
SECRET_KEY=$secret_key
FLASK_ENV=production
FLASK_DEBUG=0

# Dev tools (公開環境關閉)
ENABLE_DEV_TOOLS=false

# Gunicorn
GUNICORN_BIND=0.0.0.0:5000
GUNICORN_WORKERS=3
GUNICORN_THREADS=2

# Session
SESSION_COOKIE_SECURE=false

# Rate Limiting
RATELIMIT_ENABLED=true
RATELIMIT_DEFAULT=200 per day;50 per hour
RATELIMIT_LOGIN=30 per minute

# Form Data Sync
FORMDATA_DATABASE_URL=postgresql://beakplatform:${db_pass}@db:5432/beakform_data
ENVEOF
        log_info ".env.production 已建立 (admin 密碼: Admin1234)"
    fi
}

# === 參數處理 ===
ACTION="fresh"
FORCE_REBUILD=false

case "${1:-}" in
    --update)    ACTION="update" ;;
    --clone-db)  ACTION="clone-db" ;;
    --status)    ACTION="status" ;;
    --stop)      ACTION="stop" ;;
    --rebuild)   ACTION="fresh"; FORCE_REBUILD=true ;;
    "")          ACTION="fresh" ;;
    *)
        echo "BeakPlatform 發行部署"
        echo ""
        echo "用法:"
        echo "  bash scripts/release.sh              全新安裝（模擬首次安裝）"
        echo "  bash scripts/release.sh --update     升級更新（保留資料 + migrations）"
        echo "  bash scripts/release.sh --clone-db   複製開發 DB 到 Docker"
        echo "  bash scripts/release.sh --status     查看狀態"
        echo "  bash scripts/release.sh --stop       停止服務"
        echo "  bash scripts/release.sh --rebuild    全新安裝 + 強制重建 image"
        exit 1
        ;;
esac


# =========================================================================
#  --status
# =========================================================================
if [ "$ACTION" = "status" ]; then
    echo "=== BeakPlatform 公開環境狀態 ==="
    if [ -d "$RELEASE_DIR/$DOCKER_COMPOSE_DIR" ]; then
        cd "$RELEASE_DIR/$DOCKER_COMPOSE_DIR"
        $COMPOSE_CMD ps 2>/dev/null || echo "Docker Compose 未啟動"
        echo ""
        if curl -s "$HEALTH_URL" 2>/dev/null | grep -q '"healthy"'; then
            log_info "健康檢查: 正常"
        else
            log_warn "健康檢查: 無回應"
        fi
        # Migration 狀態
        echo ""
        docker exec beakmask-app python3 /opt/BeakPlatform/scripts/run_migrations.py --status 2>/dev/null \
            || log_warn "無法查詢 migration 狀態"
    else
        log_warn "發行目錄不存在: $RELEASE_DIR"
    fi
    exit 0
fi


# =========================================================================
#  --stop
# =========================================================================
if [ "$ACTION" = "stop" ]; then
    echo "=== 停止 BeakPlatform 公開環境 ==="
    if [ -d "$RELEASE_DIR/$DOCKER_COMPOSE_DIR" ]; then
        cd "$RELEASE_DIR/$DOCKER_COMPOSE_DIR"
        $COMPOSE_CMD down
        log_info "已停止"
    else
        log_warn "發行目錄不存在: $RELEASE_DIR"
    fi
    exit 0
fi


# =========================================================================
#  全新安裝（預設）
# =========================================================================
if [ "$ACTION" = "fresh" ]; then
    echo "============================================"
    echo "  BeakPlatform 全新安裝"
    echo "============================================"

    push_and_pull

    # 停止並刪除舊環境
    cd "$RELEASE_DIR/$DOCKER_COMPOSE_DIR"
    if $COMPOSE_CMD ps -q 2>/dev/null | grep -q .; then
        log_info "停止現有容器..."
        $COMPOSE_CMD down -v
    else
        # 容器沒跑，但 volume 可能還在
        log_info "清除舊 volume..."
        $COMPOSE_CMD down -v 2>/dev/null || true
    fi

    # 重建 .env.production
    rm -f "$DOCKER_ENV_FILE"
    ensure_env_file

    # Docker build + up
    log_info "Docker 建置..."
    if [ "$FORCE_REBUILD" = true ]; then
        $COMPOSE_CMD build --no-cache
    fi
    $COMPOSE_CMD up -d --build

    health_check

    echo ""
    echo "============================================"
    log_info "全新安裝完成"
    echo "  URL: https://app.beakmask.org"
    echo "  管理帳號: admin / Admin1234 (由 .env.production 設定)"
    echo "============================================"
    exit 0
fi


# =========================================================================
#  --update 升級更新
# =========================================================================
if [ "$ACTION" = "update" ]; then
    echo "============================================"
    echo "  BeakPlatform 升級更新"
    echo "============================================"

    push_and_pull
    ensure_env_file

    cd "$RELEASE_DIR/$DOCKER_COMPOSE_DIR"

    # 重建 app image，保留 DB volume
    log_info "重建 app 容器..."
    $COMPOSE_CMD up -d --build

    # 等 DB 就緒後跑 migrations
    log_info "等待容器啟動..."
    sleep 5

    log_info "執行 migrations..."
    docker exec beakmask-app python3 /opt/BeakPlatform/scripts/run_migrations.py --run

    # 重啟 app 讓變更生效
    log_info "重啟 app..."
    docker compose restart app

    health_check

    echo ""
    echo "============================================"
    log_info "升級更新完成"
    echo "  URL: https://app.beakmask.org"
    echo "============================================"
    exit 0
fi


# =========================================================================
#  --clone-db 複製開發 DB
# =========================================================================
if [ "$ACTION" = "clone-db" ]; then
    echo "============================================"
    echo "  BeakPlatform 複製開發 DB 到 Docker"
    echo "============================================"

    # 確認發行目錄存在
    if [ ! -d "$RELEASE_DIR/$DOCKER_COMPOSE_DIR" ]; then
        log_error "發行目錄不存在，請先執行一次全新安裝或 --update"
        exit 1
    fi

    cd "$RELEASE_DIR/$DOCKER_COMPOSE_DIR"

    # 確保 DB 容器運行中
    if ! docker ps --format '{{.Names}}' | grep -q beakmask-db; then
        log_info "啟動 DB 容器..."
        $COMPOSE_CMD up -d db redis
        sleep 5
    fi

    # 停止 app 容器（避免 DB 連線衝突）
    log_info "停止 app 容器..."
    $COMPOSE_CMD stop app 2>/dev/null || true

    # ---- 複製主資料庫 beakplatform_dev ----
    log_info "匯出本機 beakplatform_dev..."
    dump_main="/tmp/bk_clone_main.sql"
    sudo -u postgres pg_dump --no-owner --no-privileges beakplatform_dev > "$dump_main"
    dump_size=$(du -h "$dump_main" | cut -f1)
    log_info "匯出完成 ($dump_size)"

    log_info "清除 Docker beakplatform_dev..."
    docker exec beakmask-db psql -U beakplatform -d postgres -q -c \
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='beakplatform_dev' AND pid <> pg_backend_pid();" \
        > /dev/null 2>&1 || true
    docker exec beakmask-db psql -U beakplatform -d postgres -q -c "DROP DATABASE IF EXISTS beakplatform_dev;" 2>/dev/null
    docker exec beakmask-db psql -U beakplatform -d postgres -q -c "CREATE DATABASE beakplatform_dev OWNER beakplatform;" 2>/dev/null

    log_info "匯入 beakplatform_dev 到 Docker..."
    docker exec -i beakmask-db psql -U beakplatform -d beakplatform_dev -q < "$dump_main" 2>/dev/null
    rm -f "$dump_main"
    log_info "beakplatform_dev 匯入完成"

    # ---- 複製 beakform_data（若存在）----
    if sudo -u postgres psql -lqt | cut -d \| -f 1 | grep -qw beakform_data; then
        log_info "匯出本機 beakform_data..."
        dump_form="/tmp/bk_clone_form.sql"
        sudo -u postgres pg_dump --no-owner --no-privileges beakform_data > "$dump_form"
        log_info "匯出完成 ($(du -h "$dump_form" | cut -f1))"

        docker exec beakmask-db psql -U beakplatform -d postgres -q -c \
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='beakform_data' AND pid <> pg_backend_pid();" \
            > /dev/null 2>&1 || true
        docker exec beakmask-db psql -U beakplatform -d postgres -q -c "DROP DATABASE IF EXISTS beakform_data;" 2>/dev/null
        docker exec beakmask-db psql -U beakplatform -d postgres -q -c "CREATE DATABASE beakform_data OWNER beakplatform;" 2>/dev/null

        log_info "匯入 beakform_data 到 Docker..."
        docker exec -i beakmask-db psql -U beakplatform -d beakform_data -q < "$dump_form" 2>/dev/null
        rm -f "$dump_form"
        log_info "beakform_data 匯入完成"
    else
        log_warn "本機 beakform_data 不存在，跳過"
    fi

    # ---- 複製集團 DB (bk_org_*)（若存在）----
    org_dbs=$(sudo -u postgres psql -lqt | cut -d \| -f 1 | grep -w 'bk_org_.*' || true)
    if [ -n "$org_dbs" ]; then
        for org_db in $org_dbs; do
            org_db=$(echo "$org_db" | xargs)  # trim
            log_info "匯出本機 $org_db..."
            dump_org="/tmp/bk_clone_${org_db}.sql"
            sudo -u postgres pg_dump --no-owner --no-privileges "$org_db" > "$dump_org"

            docker exec beakmask-db psql -U beakplatform -d postgres -q -c \
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='$org_db' AND pid <> pg_backend_pid();" \
                > /dev/null 2>&1 || true
            docker exec beakmask-db psql -U beakplatform -d postgres -q -c "DROP DATABASE IF EXISTS \"$org_db\";" 2>/dev/null
            docker exec beakmask-db psql -U beakplatform -d postgres -q -c "CREATE DATABASE \"$org_db\" OWNER beakplatform;" 2>/dev/null

            log_info "匯入 $org_db 到 Docker..."
            docker exec -i beakmask-db psql -U beakplatform -d "$org_db" -q < "$dump_org" 2>/dev/null
            rm -f "$dump_org"
            log_info "$org_db 匯入完成"
        done
    fi

    # ---- 同步 SECRET_KEY ----
    log_info "同步 SECRET_KEY..."
    if [ ! -f "$DEV_ENV_FILE" ]; then
        log_error "開發環境 .env 不存在: $DEV_ENV_FILE"
        exit 1
    fi
    if [ ! -f "$DOCKER_ENV_FILE" ]; then
        log_error "Docker .env.production 不存在: $DOCKER_ENV_FILE"
        exit 1
    fi

    dev_secret=$(grep '^SECRET_KEY=' "$DEV_ENV_FILE" | head -1 | cut -d'=' -f2-)
    if [ -z "$dev_secret" ]; then
        log_error "開發環境 .env 中找不到 SECRET_KEY"
        exit 1
    fi

    # 備份後替換
    cp "$DOCKER_ENV_FILE" "${DOCKER_ENV_FILE}.bak"
    sed -i "s|^SECRET_KEY=.*|SECRET_KEY=$dev_secret|" "$DOCKER_ENV_FILE"
    log_info "SECRET_KEY 已同步"

    # pg_dump 已包含 schema_migrations 表和記錄，無需額外同步
    log_info "Migration 記錄已隨 DB 匯入（schema_migrations 表）"

    # ---- 重啟 app ----
    log_info "啟動 app 容器..."
    $COMPOSE_CMD up -d app

    health_check

    echo ""
    echo "============================================"
    log_info "DB 複製完成"
    echo "  URL: https://app.beakmask.org"
    echo "  帳號密碼與開發環境相同"
    echo "============================================"
    exit 0
fi
