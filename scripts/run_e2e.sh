#!/usr/bin/env bash
set -o pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
VERIFY_DIR="/opt/tmp/verify"
LOG_FILE="${VERIFY_DIR}/$(date +%Y%m%d)-e2e-od-pf79.log"

show_help() {
  cat <<'EOF'
用法：
  bash scripts/run_e2e.sh [選項] [Playwright 參數...]

選項：
  --help      顯示此說明並結束
  --headed    以有頭模式執行瀏覽器

說明：
  無參數時會執行全部 E2E 測試。
  除 --help 外，其餘參數會原樣傳給 npx playwright test。
  執行輸出會同步追加到 /opt/tmp/verify/YYYYMMDD-e2e-od-pf79.log。
EOF
}

for arg in "$@"; do
  if [[ "${arg}" == "--help" ]]; then
    show_help
    exit 0
  fi
done

mkdir -p "${VERIFY_DIR}"
cd "${REPO_ROOT}" || exit 1

npx playwright test --config tests/e2e/playwright.config.js "$@" 2>&1 | tee -a "${LOG_FILE}"
exit "${PIPESTATUS[0]}"
