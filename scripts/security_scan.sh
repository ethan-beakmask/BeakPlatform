#!/bin/bash
# BeakMask 安全掃描腳本
# 用法: ./scripts/security_scan.sh [--full] [--json] [--sarif]
#
# 模式:
#   預設     - Flask 專用規則 + 自定義規則 (27+9 條，無誤報)
#   --full   - 全部社群規則 + 自定義規則 (454+9 條，已排除 Django 誤報)

cd "$(dirname "$0")/.." || exit 1

# 解析參數
FULL_MODE=false
OUTPUT_FORMAT=""

for arg in "$@"; do
    case $arg in
        --full)  FULL_MODE=true ;;
        --json)  OUTPUT_FORMAT="--json" ;;
        --sarif) OUTPUT_FORMAT="--sarif" ;;
    esac
done

if $FULL_MODE; then
    # 完整掃描：全部規則 + 排除 Django 誤報
    EXCLUDE_RULES=(
        "python.django.security.audit.unvalidated-password.unvalidated-password"
        "python.django.security.django-no-csrf-token.django-no-csrf-token"
    )
    EXCLUDE_ARGS=""
    for rule in "${EXCLUDE_RULES[@]}"; do
        EXCLUDE_ARGS="$EXCLUDE_ARGS --exclude-rule=$rule"
    done
    echo "=== 完整掃描模式 (454+ 規則) ==="
    semgrep --config=.semgrep/ --config=auto $EXCLUDE_ARGS $OUTPUT_FORMAT backend/
else
    # 預設：Flask 專用規則
    echo "=== Flask 專用掃描模式 (27+9 規則) ==="
    semgrep --config=.semgrep/ --config=p/flask $OUTPUT_FORMAT backend/
fi
