#!/bin/bash
# =============================================================================
# Integrated-WAF WAF 熱備健康監看探測（管理機執行）
# =============================================================================
# 用法（參數放組態檔，命令列只說「做什麼」）：
#   bash monitor_probe.sh                 執行一次健康探測
#
# 選項：
#   --config FILE   組態檔（預設：本腳本旁的 failover.conf；沒有就找 /etc/integrated-waf/failover.conf）
#   -h, --help      顯示本說明
#
# 這支腳本一律 exit 0，判定結果寫在 stdout 單行，供平台流程 OsExecutor 讀取。
# 組態檔格式見 failover.conf.example（KEY=VALUE，bash 語法）。
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE=""

# 內建預設值只是佔位，實際值一律由組態檔覆蓋（見 failover.conf.example）
PUBLIC_URL="https://example.com/"
PUBLIC_HOST="example.com"
INTERNAL_URL="http://192.168.1.20:8080/"
GATEWAY_IP="192.168.1.1"
NODE_A="192.168.1.11"
NODE_B="192.168.1.12"
MONITOR_STOP_FLAG="/opt/tmp/waf-monitor.stop"
MONITOR_HEARTBEAT="/opt/tmp/heartbeat/waf_monitor.ok"

usage() { awk 'NR > 1 { if ($0 !~ /^#/) exit; sub(/^# ?/, ""); print }' "${BASH_SOURCE[0]}"; }

while [[ $# -gt 0 ]]; do
    case "$1" in
        --config)
            [[ $# -ge 2 && -n "${2:-}" ]] || { echo "--config 後面要接檔案路徑" >&2; exit 2; }
            CONFIG_FILE="$2"; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        # 參數錯誤要用非零離開碼：這支正常路徑一律 exit 0，靜默的 exit 0 會讓
        # 呼叫端（OsExecutor）以為探測成功卻拿到空 stdout，被判成服務失敗而誤告警。
        *) echo "未知參數：$1（--help 看用法）" >&2; exit 2 ;;
    esac
done

if [[ -z "$CONFIG_FILE" ]]; then
    for c in "$SCRIPT_DIR/failover.conf" /etc/integrated-waf/failover.conf; do
        [[ -f "$c" ]] && { CONFIG_FILE="$c"; break; }
    done
fi
if [[ -n "$CONFIG_FILE" && -f "$CONFIG_FILE" ]]; then
    # shellcheck disable=SC1090
    source "$CONFIG_FILE"
elif [[ -n "$CONFIG_FILE" ]]; then
    echo "找不到組態檔：$CONFIG_FILE，改用內建預設值" >&2
fi

write_heartbeat() {
    mkdir -p "$(dirname "$MONITOR_HEARTBEAT")"
    date '+%Y-%m-%d %H:%M:%S' > "$MONITOR_HEARTBEAT"
}

print_state() {
    local state="$1" ext="$2" int="$3" gw="$4"
    printf 'TS=%s STATE=%s EXT=%s INT=%s GW=%s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$state" "$ext" "$int" "$gw"
}

ping_ok() {
    local target="$1"
    [[ -n "$target" ]] && ping -c1 -W1 "$target" >/dev/null 2>&1
}

http_code() {
    local code
    code="$(curl -s -o /dev/null -m 8 -w '%{http_code}' "$@" 2>/dev/null || true)"
    [[ -n "$code" ]] || code="000"
    printf '%s' "$code"
}

is_up_code() {
    local code="$1"
    [[ "$code" =~ ^[23][0-9][0-9]$ ]]
}

if [[ -f "$MONITOR_STOP_FLAG" ]]; then
    write_heartbeat
    print_state "STOP" "-" "-" "-"
    exit 0
fi

GW="fail"
if ping_ok "$GATEWAY_IP" || ping_ok "$NODE_A" || ping_ok "$NODE_B"; then
    GW="ok"
fi

if [[ "$GW" == "fail" ]]; then
    write_heartbeat
    print_state "ISOLATED" "-" "-" "$GW"
    exit 0
fi

CFIP="$(dig @1.1.1.1 +short "$PUBLIC_HOST" 2>/dev/null | grep -E '^[0-9.]+$' | head -1 || true)"
if [[ -z "$CFIP" ]]; then
    EXT="dnsfail"
else
    EXT="$(http_code --resolve "$PUBLIC_HOST:443:$CFIP" "$PUBLIC_URL")"
fi

INT="$(http_code "$INTERNAL_URL")"

STATE="FAIL"
if is_up_code "$EXT" || [[ "$INT" != "000" ]]; then
    STATE="OK"
fi

write_heartbeat
print_state "$STATE" "$EXT" "$INT" "$GW"
exit 0
