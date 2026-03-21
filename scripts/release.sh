#!/bin/bash
# =============================================================================
# release.sh - BeakPlatform 發行腳本
# =============================================================================
# 將開發環境的程式碼發行到公開環境 (/opt/BeakPlatform-release)。
# 流程: 版本標記 → GitHub 過濾推送 → clone/pull → Docker build + up
#
# 用法:
#   bash scripts/release.sh                # 不打 tag，僅部署最新 main
#   bash scripts/release.sh v1.0.1         # 打 tag + 部署
#   bash scripts/release.sh --status       # 查看公開環境狀態
#   bash scripts/release.sh --stop         # 停止公開環境
#   bash scripts/release.sh --rebuild      # 強制重建 Docker image
# =============================================================================
set -e

# === 設定 ===
DEV_DIR="/opt/BeakPlatform"
RELEASE_DIR="/opt/BeakPlatform-release"
GITHUB_REMOTE="github"
GITHUB_CLONE_URL="git@github.com-beakplatform:beakplatform/BeakPlatform.git"
DOCKER_COMPOSE_DIR="deploy"
HEALTH_URL="http://localhost:8000/health"
HEALTH_TIMEOUT=60

# === 顏色 ===
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# === 參數處理 ===
VERSION=""
ACTION="deploy"
FORCE_REBUILD=false

case "${1:-}" in
    --status)
        ACTION="status"
        ;;
    --stop)
        ACTION="stop"
        ;;
    --rebuild)
        FORCE_REBUILD=true
        ;;
    v*.*.*)
        VERSION="$1"
        ;;
    "")
        ;;
    *)
        echo "用法:"
        echo "  bash scripts/release.sh                # 部署最新 main (不打 tag)"
        echo "  bash scripts/release.sh v1.0.1         # 打 tag + 部署"
        echo "  bash scripts/release.sh --status       # 查看公開環境狀態"
        echo "  bash scripts/release.sh --stop         # 停止公開環境"
        echo "  bash scripts/release.sh --rebuild      # 強制重建 Docker image"
        exit 1
        ;;
esac

# === 狀態查詢 ===
if [ "$ACTION" = "status" ]; then
    echo "=== BeakPlatform 公開環境狀態 ==="
    if [ -d "$RELEASE_DIR/$DOCKER_COMPOSE_DIR" ]; then
        cd "$RELEASE_DIR/$DOCKER_COMPOSE_DIR"
        docker compose --env-file .env.production ps 2>/dev/null || echo "Docker Compose 未啟動"
        echo ""
        if curl -s "$HEALTH_URL" 2>/dev/null | grep -q '"healthy"'; then
            log_info "健康檢查: 正常"
        else
            log_warn "健康檢查: 無回應"
        fi
    else
        log_warn "發行目錄不存在: $RELEASE_DIR"
    fi
    exit 0
fi

# === 停止 ===
if [ "$ACTION" = "stop" ]; then
    echo "=== 停止 BeakPlatform 公開環境 ==="
    if [ -d "$RELEASE_DIR/$DOCKER_COMPOSE_DIR" ]; then
        cd "$RELEASE_DIR/$DOCKER_COMPOSE_DIR"
        docker compose --env-file .env.production down
        log_info "已停止"
    else
        log_warn "發行目錄不存在: $RELEASE_DIR"
    fi
    exit 0
fi

# === 部署流程 ===
echo "============================================"
echo "  BeakPlatform 發行部署"
echo "============================================"

# Step 1: 確認開發環境狀態
log_info "Step 1: 檢查開發環境..."
cd "$DEV_DIR"

current_branch=$(git branch --show-current)
if [ "$current_branch" != "main" ]; then
    log_error "必須在 main 分支執行 (目前: $current_branch)"
    exit 1
fi

if ! git diff --quiet || ! git diff --cached --quiet; then
    log_error "工作區有未提交的變更，請先 commit"
    exit 1
fi

# Step 2: 版本標記 (選用)
if [ -n "$VERSION" ]; then
    log_info "Step 2: 標記版本 $VERSION..."

    if git tag -l "$VERSION" | grep -q .; then
        log_error "Tag $VERSION 已存在"
        exit 1
    fi

    # 更新 pyproject.toml 版本號
    PYVER="${VERSION#v}"
    current_ver=$(grep '^version = ' pyproject.toml | sed 's/version = "\(.*\)"/\1/')
    if [ "$current_ver" != "$PYVER" ]; then
        sed -i "s/^version = \"$current_ver\"/version = \"$PYVER\"/" pyproject.toml
        git add pyproject.toml
        git commit -m "release: $VERSION"
    fi

    git tag -a "$VERSION" -m "Release $VERSION"
    log_info "已建立 tag: $VERSION"
else
    log_info "Step 2: 跳過版本標記 (無版本參數)"
fi

# Step 3: 推送到 Forgejo
log_info "Step 3: 推送到 Forgejo..."
git push origin main --tags 2>&1 | tail -3

# Step 4: 過濾推送到 GitHub
log_info "Step 4: 過濾推送到 GitHub..."
bash scripts/push_github.sh

# 推送 tag 到 GitHub
if [ -n "$VERSION" ]; then
    git push "$GITHUB_REMOTE" "$VERSION" 2>&1 | tail -3
    log_info "已推送 tag $VERSION 到 GitHub"
fi

# Step 5: 準備發行目錄
log_info "Step 5: 準備發行目錄..."

if [ -d "$RELEASE_DIR/.git" ]; then
    # 已存在，拉取最新
    log_info "更新現有發行目錄..."
    cd "$RELEASE_DIR"
    git fetch origin
    git reset --hard origin/main
    if [ -n "$VERSION" ]; then
        git fetch origin --tags
    fi
else
    # 首次 clone
    log_info "首次 clone 從 GitHub..."
    git clone "$GITHUB_CLONE_URL" "$RELEASE_DIR"
    cd "$RELEASE_DIR"
fi

log_info "發行目錄 HEAD: $(git log --oneline -1)"

# Step 6: 確認 .env.production
log_info "Step 6: 檢查 .env.production..."
ENV_FILE="$RELEASE_DIR/$DOCKER_COMPOSE_DIR/.env.production"

if [ ! -f "$ENV_FILE" ]; then
    log_warn ".env.production 不存在，從範本建立..."

    # 產生隨機 SECRET_KEY
    SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    # 產生隨機 DB 密碼
    DB_PASS=$(python3 -c "import secrets; print(secrets.token_urlsafe(16))")

    cat > "$ENV_FILE" << ENVEOF
# BeakPlatform Release Environment
# 自動產生於 $(date '+%Y-%m-%d %H:%M')

# Database
DB_PASSWORD=$DB_PASS
DATABASE_URL=postgresql://beakplatform:${DB_PASS}@db:5432/beakplatform_dev

# Redis
REDIS_URL=redis://redis:6379/0

# Admin (首次啟動後請移除此行)
ADMIN_INITIAL_PASSWORD=

# Application
SECRET_KEY=$SECRET_KEY
FLASK_ENV=production
FLASK_DEBUG=0

# Dev tools (公開環境必須關閉)
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
FORMDATA_DATABASE_URL=postgresql://beakplatform:${DB_PASS}@db:5432/beakform_data
ENVEOF

    echo ""
    log_warn "=========================================="
    log_warn "  .env.production 已建立但需要設定:"
    log_warn "  1. 設定 ADMIN_INITIAL_PASSWORD (必填)"
    log_warn "  $ENV_FILE"
    log_warn "=========================================="
    echo ""
    read -p "請輸入管理員初始密碼 (至少 8 字元): " admin_pass
    if [ ${#admin_pass} -lt 8 ]; then
        log_error "密碼太短 (最少 8 字元)"
        exit 1
    fi
    sed -i "s/^ADMIN_INITIAL_PASSWORD=$/ADMIN_INITIAL_PASSWORD=$admin_pass/" "$ENV_FILE"
    log_info "管理員密碼已設定"
else
    log_info ".env.production 已存在，跳過建立"
fi

# Step 7: Docker build + up
log_info "Step 7: Docker 部署..."
cd "$RELEASE_DIR/$DOCKER_COMPOSE_DIR"

if [ "$FORCE_REBUILD" = true ]; then
    log_info "強制重建 Docker image..."
    docker compose --env-file .env.production build --no-cache
    docker compose up -d
else
    docker compose --env-file .env.production up -d --build
fi

# Step 8: 健康檢查
log_info "Step 8: 健康檢查 (等待最多 ${HEALTH_TIMEOUT}s)..."
elapsed=0
while [ $elapsed -lt $HEALTH_TIMEOUT ]; do
    if curl -s "$HEALTH_URL" 2>/dev/null | grep -q '"healthy"'; then
        log_info "健康檢查通過"
        break
    fi
    sleep 3
    elapsed=$((elapsed + 3))
    printf "."
done
echo ""

if [ $elapsed -ge $HEALTH_TIMEOUT ]; then
    log_error "健康檢查逾時 (${HEALTH_TIMEOUT}s)"
    log_warn "檢查 Docker logs:"
    echo "  cd $RELEASE_DIR/$DOCKER_COMPOSE_DIR && docker compose logs app"
    exit 1
fi

# 完成
echo ""
echo "============================================"
log_info "發行部署完成"
echo "  公開 URL: http://localhost:8000"
echo "  外部 URL: https://app.beakmask.org"
if [ -n "$VERSION" ]; then
    echo "  版本: $VERSION"
fi
echo "  發行目錄: $RELEASE_DIR"
echo "============================================"
