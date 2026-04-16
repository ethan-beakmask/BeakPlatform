#!/bin/bash
#
# BeakPlatform 安裝驗證腳本
# 檢查平台和模組是否正確安裝
#

set -e

# 顏色定義
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

INSTALL_DIR="${INSTALL_DIR:-/opt/BeakPlatform}"
FLASK_PORT="${FLASK_PORT:-8000}"
FLASK_HOST="${FLASK_HOST:-127.0.0.1}"

PASS_COUNT=0
FAIL_COUNT=0

check() {
    local name="$1"
    local cmd="$2"

    if eval "$cmd" > /dev/null 2>&1; then
        echo -e "${GREEN}✓${NC} $name"
        ((PASS_COUNT++))
    else
        echo -e "${RED}✗${NC} $name"
        ((FAIL_COUNT++))
    fi
}

check_output() {
    local name="$1"
    local cmd="$2"
    local expected="$3"

    local output
    output=$(eval "$cmd" 2>/dev/null)
    if echo "$output" | grep -q "$expected"; then
        echo -e "${GREEN}✓${NC} $name"
        ((PASS_COUNT++))
    else
        echo -e "${RED}✗${NC} $name"
        echo -e "  ${YELLOW}預期包含: $expected${NC}"
        ((FAIL_COUNT++))
    fi
}

echo -e "${BLUE}"
echo "╔═══════════════════════════════════════════════════════════╗"
echo "║           BeakPlatform 安裝驗證                           ║"
echo "╚═══════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# 系統檢查
echo -e "\n${BLUE}[系統環境]${NC}"
check "Python 3 已安裝" "python3 --version"
check "PostgreSQL 已安裝" "psql --version"
check "Nginx 已安裝" "nginx -v"
check "Git 已安裝" "git --version"

# 目錄結構
echo -e "\n${BLUE}[目錄結構]${NC}"
check "安裝目錄存在" "test -d $INSTALL_DIR"
check "backend 目錄存在" "test -d $INSTALL_DIR/backend"
check "modules 目錄存在" "test -d $INSTALL_DIR/modules"
check "venv 存在" "test -d $INSTALL_DIR/venv"
check ".env 檔案存在" "test -f $INSTALL_DIR/.env"

# 模組檢查
echo -e "\n${BLUE}[模組結構]${NC}"
check "form_workflow 模組存在" "test -d $INSTALL_DIR/modules/form_workflow"
check "模組 __init__.py 存在" "test -f $INSTALL_DIR/modules/form_workflow/__init__.py"
check "模組 models 存在" "test -d $INSTALL_DIR/modules/form_workflow/models"
check "模組 api 存在" "test -d $INSTALL_DIR/modules/form_workflow/api"
check "模組 web 存在" "test -d $INSTALL_DIR/modules/form_workflow/web"
check "模組 templates 存在" "test -d $INSTALL_DIR/modules/form_workflow/templates"
check "模組 migrations 存在" "test -d $INSTALL_DIR/modules/form_workflow/migrations"

# 資料庫檢查
echo -e "\n${BLUE}[資料庫]${NC}"
check "PostgreSQL 服務運行中" "systemctl is-active postgresql"

# 讀取 .env 取得資料庫資訊
if [ -f "$INSTALL_DIR/.env" ]; then
    source "$INSTALL_DIR/.env"
    DB_URL="${DATABASE_URL:-postgresql://beakplatform:postgres123@localhost/beakplatform_dev}"
    # 解析 DATABASE_URL
    DB_USER=$(echo "$DB_URL" | sed -n 's/.*:\/\/\([^:]*\):.*/\1/p')
    DB_PASS=$(echo "$DB_URL" | sed -n 's/.*:\/\/[^:]*:\([^@]*\)@.*/\1/p')
    DB_HOST=$(echo "$DB_URL" | sed -n 's/.*@\([^\/]*\)\/.*/\1/p')
    DB_NAME=$(echo "$DB_URL" | sed -n 's/.*\/\([^?]*\).*/\1/p')
fi

DB_USER="${DB_USER:-beakplatform}"
DB_PASS="${DB_PASS:-postgres123}"
DB_HOST="${DB_HOST:-localhost}"
DB_NAME="${DB_NAME:-beakplatform_dev}"

check "資料庫連線" "PGPASSWORD=$DB_PASS psql -h $DB_HOST -U $DB_USER -d $DB_NAME -c 'SELECT 1'"

# 檢查平台資料表
check_output "users 資料表存在" "PGPASSWORD=$DB_PASS psql -h $DB_HOST -U $DB_USER -d $DB_NAME -c '\\dt users'" "users"
check_output "organizations 資料表存在" "PGPASSWORD=$DB_PASS psql -h $DB_HOST -U $DB_USER -d $DB_NAME -c '\\dt organizations'" "organizations"

# 檢查模組資料表
echo -e "\n${BLUE}[FormWorkflow 資料表]${NC}"
for table in fw_form_templates fw_workflow_templates fw_form_instances fw_workflow_instances fw_approval_records fw_workflow_variables fw_node_execution_queue; do
    check_output "$table 存在" "PGPASSWORD=$DB_PASS psql -h $DB_HOST -U $DB_USER -d $DB_NAME -c '\\dt $table'" "$table"
done

# API 測試（需要 Flask 運行中）
echo -e "\n${BLUE}[API 測試]${NC}"
echo -e "${YELLOW}注意: 以下測試需要 Flask 服務運行中${NC}"

if curl -s --connect-timeout 2 "http://$FLASK_HOST:$FLASK_PORT/" > /dev/null 2>&1; then
    check_output "平台 API 響應" "curl -s http://$FLASK_HOST:$FLASK_PORT/api/form-workflow/info" "form_workflow"
    check_output "模組權限 API" "curl -s http://$FLASK_HOST:$FLASK_PORT/api/form-workflow/permissions" "permissions"

    # 檢查認證攔截
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "http://$FLASK_HOST:$FLASK_PORT/api/form-workflow/templates")
    if [ "$HTTP_CODE" = "401" ]; then
        echo -e "${GREEN}✓${NC} 認證攔截正常 (401)"
        ((PASS_COUNT++))
    else
        echo -e "${RED}✗${NC} 認證攔截異常 (預期 401，實際 $HTTP_CODE)"
        ((FAIL_COUNT++))
    fi

    # 檢查 Web 路由
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "http://$FLASK_HOST:$FLASK_PORT/forms/")
    if [ "$HTTP_CODE" = "401" ] || [ "$HTTP_CODE" = "302" ]; then
        echo -e "${GREEN}✓${NC} Web 路由正常 ($HTTP_CODE)"
        ((PASS_COUNT++))
    else
        echo -e "${RED}✗${NC} Web 路由異常 (預期 401/302，實際 $HTTP_CODE)"
        ((FAIL_COUNT++))
    fi
else
    echo -e "${YELLOW}⚠ Flask 服務未運行，跳過 API 測試${NC}"
    echo "  啟動服務: cd $INSTALL_DIR/backend && flask run --port=$FLASK_PORT"
fi

# 總結
echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
TOTAL=$((PASS_COUNT + FAIL_COUNT))
echo -e "測試結果: ${GREEN}$PASS_COUNT 通過${NC} / ${RED}$FAIL_COUNT 失敗${NC} (共 $TOTAL 項)"

if [ $FAIL_COUNT -eq 0 ]; then
    echo -e "\n${GREEN}✓ 所有檢查通過！安裝成功。${NC}"
    exit 0
else
    echo -e "\n${RED}✗ 有 $FAIL_COUNT 項檢查失敗，請檢查上述錯誤。${NC}"
    exit 1
fi
