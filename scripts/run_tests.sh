#!/usr/bin/env bash
#
# 跑 pytest 的唯一正確入口。
#
# 為什麼需要這支：TestingConfig 的資料庫是 os.getenv('DATABASE_URL', 'sqlite:///:memory:')，
# 而專案標準操作是先 `set -a && source .env && set +a`——.env 的 DATABASE_URL 指向開發庫
# beakplatform_dev，於是測試會跑在開發資料庫上，而 app fixture 收尾會呼叫 db.drop_all()。
# 這支腳本負責在載入 .env 之後把 DATABASE_URL 強制改指到拋棄式測試庫。
# （conftest.py 的 pytest_configure 另有一道防呆，會擋下庫名不是 _test 結尾的情況。）
#
# 用法：
#   bash scripts/run_tests.sh                      # 跑全部
#   bash scripts/run_tests.sh tests/test_pageir_shared_menu.py -q
#   bash scripts/run_tests.sh -k menu -q
#
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEST_DB_NAME="${TEST_DB_NAME:-beakplatform_test}"
DB_USER="${DB_USER:-beakplatform}"
DB_PASS="${DB_PASS:-postgres123}"
DB_HOST="${DB_HOST:-localhost}"

cd "$PROJECT_ROOT"

if [ -f .env ]; then
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
fi

# 一定要在 source .env 之後覆寫，否則會被 .env 的開發庫蓋掉。
export DATABASE_URL="postgresql://${DB_USER}:${DB_PASS}@${DB_HOST}/${TEST_DB_NAME}"

if ! PGPASSWORD="$DB_PASS" psql -h "$DB_HOST" -U "$DB_USER" -d "$TEST_DB_NAME" -c 'SELECT 1' >/dev/null 2>&1; then
    echo "測試資料庫 ${TEST_DB_NAME} 不存在或連不上。"
    echo "建立方式（beakplatform 帳號沒有 CREATEDB 權限，要用 postgres）："
    echo "  sudo -u postgres createdb -O ${DB_USER} ${TEST_DB_NAME}"
    exit 1
fi

cd backend
exec ../venv/bin/python -m pytest "$@"
