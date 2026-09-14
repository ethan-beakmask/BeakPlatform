#!/bin/bash
# check_schema_drift.sh — 全新安裝 schema 與 dev 庫的守恆檢查（PF-168）
#
# 做法：建拋棄式的 beakplatform_freshcheck 庫 → 走安裝路徑（db.create_all ＋
# fw_sp_setup.sql）→ 與 .env 指向的 dev 庫比對表／欄位／型別／NOT NULL／
# fw_sp schema 與 ACL。有差異 exit 1（紅）。
#
# 什麼時候跑：改 ORM model、加表、動 DB 物件之後；以及例行驗收。
# 全程約 1~2 分鐘。需要 sudo（建刪 freshcheck 庫）。
#
# 用法：
#   bash scripts/check_schema_drift.sh                 執行檢查
#   bash scripts/check_schema_drift.sh --keep          檢查後保留 freshcheck 庫
#   bash scripts/check_schema_drift.sh --show-indexes  連索引差異明細一起列（警告區）
#   bash scripts/check_schema_drift.sh --show-defaults 連 server default 差異明細一起列
#   bash scripts/check_schema_drift.sh --help          顯示本說明

set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRESH_DB="beakplatform_freshcheck"
DB_USER="${DB_USER:-beakplatform}"
DB_PASS="${DB_PASS:-}"
KEEP=0
DIFF_ARGS=()

for arg in "$@"; do
    case "$arg" in
        --keep) KEEP=1 ;;
        --show-indexes|--show-defaults) DIFF_ARGS+=("$arg") ;;
        --help|-h) grep '^#' "$0" | sed 's/^# \{0,1\}//' | head -16; exit 0 ;;
        *) echo "未知參數: $arg（--help 看用法）"; exit 2 ;;
    esac
done

DEV_URL="$(grep -m1 '^DATABASE_URL=' "$REPO_ROOT/.env" | cut -d'=' -f2-)"
if [ -z "$DEV_URL" ]; then
    echo "錯誤: $REPO_ROOT/.env 沒有 DATABASE_URL"
    exit 2
fi

# 未指定 DB_PASS 時沿用 dev 庫的密碼（安裝時隨機產生，沒有固定預設值）。
if [ -z "$DB_PASS" ]; then
    DB_PASS=$(printf '%s' "$DEV_URL" | sed -n 's#^[a-z]*://[^:]*:\([^@]*\)@.*#\1#p')
fi
if [ -z "$DB_PASS" ]; then
    echo "錯誤: 找不到資料庫密碼，請設定 DB_PASS 或確認 DATABASE_URL 含密碼"
    exit 2
fi

echo "=== schema drift 檢查（乾淨安裝 vs dev）==="
echo "1. 重建 $FRESH_DB..."
sudo -u postgres psql -q -c "DROP DATABASE IF EXISTS $FRESH_DB;" \
    -c "CREATE DATABASE $FRESH_DB OWNER $DB_USER;"

echo "2. db.create_all（載入全部模組 models）..."
(
    cd "$REPO_ROOT/backend"
    set -a && source "$REPO_ROOT/.env" && set +a
    export DATABASE_URL="postgresql://$DB_USER:$DB_PASS@localhost:5432/$FRESH_DB"
    SKIP_MODULE_SYNC=1 "$REPO_ROOT/venv/bin/python" ../scripts/db_create_all.py 2>&1 | tail -1
)

echo "3. fw_sp schema 與擁有權分離..."
sudo -u postgres psql -d "$FRESH_DB" -v ON_ERROR_STOP=1 -v app_user="$DB_USER" \
    -q -f "$REPO_ROOT/scripts/sql/fw_sp_setup.sql"

echo "4. 比對..."
set +e
"$REPO_ROOT/venv/bin/python" "$REPO_ROOT/scripts/schema_drift_diff.py" \
    --fresh-dsn "postgresql://$DB_USER:$DB_PASS@localhost:5432/$FRESH_DB" \
    --dev-dsn "$DEV_URL" \
    "${DIFF_ARGS[@]}"
RC=$?
set -e

if [ "$KEEP" = "1" ]; then
    echo "(--keep：保留 $FRESH_DB 供檢視)"
else
    sudo -u postgres psql -q -c "DROP DATABASE IF EXISTS $FRESH_DB;"
fi

exit $RC
