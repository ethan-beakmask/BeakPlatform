#!/bin/bash
# =============================================================================
# ITHome2026-WAF 防禦節點熱備切換（管理機執行）
# =============================================================================
# 用法（參數放組態檔，命令列只說「做什麼」）：
#   bash failover.sh status                 兩台目前誰持有服務 IP、cloudflared / od-bridge / blocklist
#   bash failover.sh switch                 切到「現在沒持有服務 IP」的那台（兩台之間來回）
#   bash failover.sh to <節點>              切到指定節點（組態檔的 NODE_A / NODE_B 名稱、或它的 IP）
#   bash failover.sh dry-run [<節點>]       只做前置檢查，不切換
#
# 選項：
#   --config FILE   組態檔（預設：本腳本旁的 failover.conf；沒有就找 /etc/ithome2026-waf/failover.conf）
#   --yes           不詢問直接切換（給排程或流程節點用）
#   --force         兩台 .env 不一致時仍切換
#   --log FILE      輸出同時寫入此檔（預設寫到組態檔 LOG_DIR 下的 failover-<日期>.log）
#   -h, --help      顯示本說明
#
# 組態檔格式見 failover.conf.example（KEY=VALUE，bash 語法）。
# 遠端一律用 sudo -n bash <安裝目錄>/standby.sh 執行，不會提示密碼。
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE=""
ACTION=""
TO_NODE=""
YES=0
DRY_RUN=0
FORCE=0
STATUS_ONLY=0
LOG_FILE=""

# 組態檔可設定的變數（命令列沒有對應選項，只從組態檔來）
SERVICE_IP=""
NODE_A=""; NODE_B=""
NODE_A_NAME="A"; NODE_B_NAME="B"
SSH_USER=""
SSH_OPTS_STR=""
INSTALL_DIR="/opt/ithome2026-waf"
LOG_DIR=""

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
log_info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1" >&2; }
die()       { log_error "$1"; exit 1; }
usage() { awk 'NR > 1 { if ($0 !~ /^#/) exit; sub(/^# ?/, ""); print }' "${BASH_SOURCE[0]}"; }

[[ $# -gt 0 ]] || { usage; exit 0; }
while [[ $# -gt 0 ]]; do
    case "$1" in
        status|switch|dry-run)
            [[ -z "$ACTION" ]] || die "只能指定一個動作（已有 $ACTION）"
            ACTION="$1"; shift
            if [[ "$ACTION" == "dry-run" && $# -gt 0 && "$1" != -* ]]; then TO_NODE="$1"; shift; fi
            ;;
        to)
            [[ -z "$ACTION" ]] || die "只能指定一個動作（已有 $ACTION）"
            ACTION="to"; [[ $# -ge 2 && -n "$2" && "$2" != -* ]] || die "to 後面要接節點名稱或 IP（收到空字串時常見原因：表單欄位沒填）"
            TO_NODE="$2"; shift 2 ;;
        --config) CONFIG_FILE="$2"; shift 2 ;;
        --yes|-y) YES=1; shift ;;
        --dry-run) DRY_RUN=1; shift ;;
        --force) FORCE=1; shift ;;
        --log) LOG_FILE="$2"; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) die "未知參數：$1（--help 看用法）" ;;
    esac
done
[[ -n "$ACTION" ]] || die "請指定動作：status / switch / to <節點> / dry-run（--help 看用法）"
[[ "$ACTION" == "dry-run" ]] && DRY_RUN=1
[[ "$ACTION" == "status" ]] && STATUS_ONLY=1

# ---- 組態檔 ----
if [[ -z "$CONFIG_FILE" ]]; then
    for c in "$SCRIPT_DIR/failover.conf" /etc/ithome2026-waf/failover.conf; do
        [[ -f "$c" ]] && { CONFIG_FILE="$c"; break; }
    done
fi
[[ -n "$CONFIG_FILE" && -f "$CONFIG_FILE" ]] || die "找不到組態檔（--config 指定，或把 failover.conf.example 複製成 failover.conf 填好）"
# shellcheck disable=SC1090
source "$CONFIG_FILE"
[[ -n "$SERVICE_IP" ]] || die "組態檔缺 SERVICE_IP"
[[ -n "$NODE_A" && -n "$NODE_B" ]] || die "組態檔要有 NODE_A 與 NODE_B（兩台的管理 IP）"
NODES=("$NODE_A" "$NODE_B")
SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=8)
if [[ -n "$SSH_OPTS_STR" ]]; then
    read -r -a opt_parts <<< "$SSH_OPTS_STR"
    for i in "${!opt_parts[@]}"; do
        # 自己展開 ~/：ssh 對 -i 的路徑不做 tilde 展開
        [[ "${opt_parts[$i]}" == "~/"* ]] && opt_parts[$i]="${HOME}/${opt_parts[$i]:2}"
    done
    SSH_OPTS+=("${opt_parts[@]}")
fi

# 節點名稱 → IP（to / dry-run 可以用 NODE_A_NAME、A/B、或 IP）
resolve_node() {
    case "$1" in
        "$NODE_A"|"$NODE_A_NAME"|A|a) printf '%s' "$NODE_A" ;;
        "$NODE_B"|"$NODE_B_NAME"|B|b) printf '%s' "$NODE_B" ;;
        *) die "不認識的節點：$1（可用 $NODE_A_NAME / $NODE_B_NAME / A / B / IP）" ;;
    esac
}
node_label() {
    case "$1" in
        "$NODE_A") printf '%s（%s）' "$NODE_A_NAME" "$NODE_A" ;;
        "$NODE_B") printf '%s（%s）' "$NODE_B_NAME" "$NODE_B" ;;
        *) printf '%s' "$1" ;;
    esac
}
[[ -n "$TO_NODE" ]] && TO_NODE="$(resolve_node "$TO_NODE")"

if [[ -z "$LOG_FILE" && -n "$LOG_DIR" && $STATUS_ONLY -eq 0 ]]; then
    mkdir -p "$LOG_DIR" && LOG_FILE="$LOG_DIR/failover-$(date +%Y%m%d).log"
fi
if [[ -n "$LOG_FILE" && -z "${FAILOVER_LOGGING:-}" ]]; then
    export FAILOVER_LOGGING=1
    exec > >(tee -a "$LOG_FILE") 2>&1
    echo "===== $(date '+%F %T') failover.sh $ACTION ${TO_NODE:+→ $TO_NODE} ====="
fi

command -v python3 >/dev/null || die "管理機需要 python3"
command -v ssh >/dev/null || die "找不到 ssh"

target_of() {
    local node="$1"
    if [[ -n "$SSH_USER" ]]; then
        printf '%s@%s' "$SSH_USER" "$node"
    else
        printf '%s' "$node"
    fi
}

remote() {
    local node="$1"; shift
    ssh "${SSH_OPTS[@]}" "$(target_of "$node")" "$@"
}

standby_cmd() {
    local sub="$1"
    printf 'sudo -n bash %q/standby.sh %q --dir %q' "$INSTALL_DIR" "$sub" "$INSTALL_DIR"
}

remote_standby() {
    local node="$1" sub="$2"; shift 2
    remote "$node" "$(standby_cmd "$sub") $*"
}

status_file_for() {
    local node="$1"
    printf '%s/status-%s.json' "$WORKDIR" "$(printf '%s' "$node" | tr -c 'A-Za-z0-9_.-' '_')"
}

DEAD_NODES=()
fetch_statuses() {
    local node file
    DEAD_NODES=()
    for node in "${NODES[@]}"; do
        file="$(status_file_for "$node")"
        if remote_standby "$node" status "--service-ip $(printf '%q' "$SERVICE_IP")" > "$file" 2>/dev/null \
           && python3 -m json.tool "$file" >/dev/null 2>&1; then
            continue
        fi
        # 失聯的節點就是熱備要處理的情境：記成 unreachable，不中止。
        # 服務 IP 視為「沒人持有」（它若還活著卻不理 SSH，切換後會撞 IP，事後驗證會抓到）
        DEAD_NODES+=("$node")
        log_warn "$node 連不上（SSH／sudo -n／standby.sh 任一失敗），視為失聯節點"
        printf '{"hostname":"","iface":"","mgmt_ip":"%s","service_ip":"%s","holds_service_ip":false,"route_src":"","cloudflared":"unreachable","od_bridge":"unreachable","blocklist_count":0,"blocklist6_count":0,"unit_installed":false,"snat_rule":false,"env":null,"unreachable":true}\n' "$node" "$SERVICE_IP" > "$file"
    done
    [[ ${#DEAD_NODES[@]} -lt 2 ]] || die "兩台都連不上，無法切換"
}
node_dead() { local n; for n in "${DEAD_NODES[@]:-}"; do [[ "$n" == "$1" ]] && return 0; done; return 1; }

print_status_table() {
    python3 - "$SERVICE_IP" "${NODES[0]}" "$(status_file_for "${NODES[0]}")" "${NODES[1]}" "$(status_file_for "${NODES[1]}")" <<'PY'
import json, sys
rows = []
for node, path in [(sys.argv[2], sys.argv[3]), (sys.argv[4], sys.argv[5])]:
    d = json.load(open(path, encoding="utf-8"))
    if d.get("unreachable"):
        rows.append([node, "-", "失聯", "-", "unreachable", "unreachable", "-", "-"])
        continue
    rows.append([node, d.get("mgmt_ip", ""), "是" if d["holds_service_ip"] else "否", "是" if d.get("snat_rule") else "否",
                 d["cloudflared"], d["od_bridge"],
                 str(d["blocklist_count"] + d["blocklist6_count"]), d["env"].get("CF_HOSTNAME", "")])
headers = ["節點", "管理 IP", "持有服務 IP", "SNAT", "cloudflared", "od-bridge", "blocklist", "CF_HOSTNAME"]
widths = [max(len(str(x)) for x in col) for col in zip(headers, *rows)]
fmt = "  ".join("{:<%d}" % w for w in widths)
print(fmt.format(*headers))
print(fmt.format(*["-" * w for w in widths]))
for r in rows:
    print(fmt.format(*r))
PY
}

precheck_and_plan() {
    python3 - "$SERVICE_IP" "$TO_NODE" "$FORCE" "$YES" "${NODES[0]}" "$(status_file_for "${NODES[0]}")" "${NODES[1]}" "$(status_file_for "${NODES[1]}")" > "$WORKDIR/plan.env" <<'PY'
import json, sys
service_ip, to_node, force, yes = sys.argv[1:5]
items = [(sys.argv[5], sys.argv[6]), (sys.argv[7], sys.argv[8])]
data = [(node, json.load(open(path, encoding="utf-8"))) for node, path in items]
holders = [node for node, d in data if d.get("holds_service_ip")]
errors = []
if len(holders) == 2:
    errors.append("兩台都持有服務 IP，為避免雙現役已中止")
if len(holders) == 0 and yes != "1":
    errors.append("目前沒有節點持有服務 IP；冷啟動需要 --yes 並指定 --to")
if len(holders) == 0 and not to_node and len([n for n, d in data if not d.get("unreachable")]) != 1:
    errors.append("冷啟動必須指定 --to")
nodes = [node for node, _ in data]
if to_node and to_node not in nodes:
    errors.append("--to 必須是 --nodes 其中一台")
old = holders[0] if len(holders) == 1 else ""
dead = [node for node, d in data if d.get("unreachable")]
if to_node:
    new = to_node
elif old:
    new = next((node for node in nodes if node != old), "")
else:
    # 沒人持有（例如現役節點整台失聯）：目標就是活著的那台
    alive = [node for node in nodes if node not in dead]
    new = alive[0] if len(alive) == 1 else ""
if old and new == old:
    errors.append("--to 不能指定目前持有服務 IP 的節點")
target = dict(data).get(new)
if target and target.get("unreachable"):
    errors.append("目標節點連不上，無法接手")
elif target and target.get("cloudflared") not in ("stopped", "absent"):
    errors.append("目標節點 cloudflared 不是 stopped/absent，可能形成兩個 connector")
keys = ["CF_HOSTNAME", "WELCOME_HOSTNAME", "WAF_BACKEND_PATH", "WAF_BACKEND_URL", "BEAK_BASE_URL"]
any_dead = any(d.get("unreachable") for _, d in data)
if force != "1" and not any_dead:
    env0, env1 = data[0][1].get("env", {}), data[1][1].get("env", {})
    diffs = [k for k in keys if env0.get(k, "") != env1.get(k, "")]
    if diffs:
        errors.append("兩台 .env 不一致：" + ", ".join("%s(%r != %r)" % (k, env0.get(k, ""), env1.get(k, "")) for k in diffs))
if errors:
    for e in errors:
        print("ERROR=%s" % e)
    raise SystemExit(1)
old_count = dict(data).get(old, {}).get("blocklist_count", 0) + dict(data).get(old, {}).get("blocklist6_count", 0) if old else 0
print("OLD_NODE=%s" % old)
print("NEW_NODE=%s" % new)
print("OLD_BLOCKS=%s" % old_count)
PY
}

load_plan() {
    # shellcheck disable=SC1091
    source "$WORKDIR/plan.env"
}

confirm_plan() {
    echo
    echo "切換計畫："
    echo "  服務 IP：$SERVICE_IP"
    echo "  來源節點：$( [[ -n "${OLD_NODE:-}" ]] && node_label "$OLD_NODE" || echo "（無，冷啟動）" )"
    echo "  目標節點：$(node_label "$NEW_NODE")"
    echo "  將複製封鎖清單：約 $OLD_BLOCKS 筆"
    if [[ $DRY_RUN -eq 1 ]]; then
        log_info "--dry-run：前置檢查完成，不執行切換"
        exit 0
    fi
    if [[ $YES -eq 0 ]]; then
        local ans
        read -rp "輸入 yes 開始切換: " ans
        [[ "$ans" == "yes" ]] || exit 0
    fi
}

manual_rollback() {
    echo
    echo "手動回退指令："
    [[ -n "${NEW_NODE:-}" ]] && echo "  ssh ${SSH_OPTS[*]} $(target_of "$NEW_NODE") 'sudo -n bash $INSTALL_DIR/standby.sh release --dir $INSTALL_DIR --service-ip $SERVICE_IP'"
    [[ -n "${OLD_NODE:-}" ]] && echo "  ssh ${SSH_OPTS[*]} $(target_of "$OLD_NODE") 'sudo -n bash $INSTALL_DIR/standby.sh takeover --dir $INSTALL_DIR --service-ip $SERVICE_IP'"
}

http_code() { local c; c="$(curl -s -o /dev/null -m 8 -w '%{http_code}' "$1" 2>/dev/null)"; printf '%s' "${c:-000}"; }

verify_after() {
    # 管理機的 ARP 快取要等新節點的 gratuitous ARP 或鄰居探測才會換成新 MAC，
    # 通常在數秒內，所以最多重試 20 秒再判定失敗
    local code="000" sqli i
    for i in $(seq 1 10); do
        code="$(http_code "http://$SERVICE_IP:8080/")"
        [[ "$code" != "000" ]] && break
        sleep 2
    done
    echo "WAF / HTTP：$code（重試 $i 次）"
    [[ "$code" != "000" ]] || return 1
    sqli="$(http_code "http://$SERVICE_IP:8080/?id=1%27%20OR%201=1--")"
    echo "WAF SQLi 探測：$sqli"
    [[ "$sqli" == "403" ]] || return 1
    echo "ARP 鄰居："
    ip neigh show "$SERVICE_IP" || true
}

WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT

fetch_statuses
if [[ $STATUS_ONLY -eq 1 ]]; then
    print_status_table
    exit 0
fi

precheck_and_plan || { cat "$WORKDIR/plan.env" >&2; exit 1; }
load_plan
confirm_plan

STATE_FILE="$WORKDIR/state.json"
if [[ -n "$OLD_NODE" ]] && ! node_dead "$OLD_NODE"; then
    log_info "從 $OLD_NODE 匯出狀態"
    remote_standby "$OLD_NODE" export-state > "$STATE_FILE"
else
    [[ ${#DEAD_NODES[@]} -gt 0 ]] && log_warn "失聯節點 ${DEAD_NODES[*]} 上的封鎖清單無法複製，新節點從空清單開始"
    printf '{"version":1,"exported_at":"","host":"","blocklist":null,"blocklist6":null,"edl_state":null}\n' > "$STATE_FILE"
fi

T_RELEASE="$(date +%s)"
if [[ -n "$OLD_NODE" ]] && ! node_dead "$OLD_NODE"; then
    log_info "釋放舊節點 $OLD_NODE"
    remote_standby "$OLD_NODE" release "--service-ip $(printf '%q' "$SERVICE_IP")"
fi

log_info "接手新節點 $NEW_NODE"
TAKEOVER_OUT="$WORKDIR/takeover.out"
if ! remote "$NEW_NODE" "$(standby_cmd takeover) --service-ip $(printf '%q' "$SERVICE_IP") --state-file -" < "$STATE_FILE" | tee "$TAKEOVER_OUT"; then
    manual_rollback
    exit 1
fi
REGISTERED_AT="$(awk -F= '/^CLOUDFLARED_REGISTERED_AT=/{print $2}' "$TAKEOVER_OUT" | tail -1)"

log_info "事後驗證"
if ! verify_after; then
    log_error "事後驗證失敗"
    manual_rollback
    exit 1
fi

fetch_statuses
print_status_table
if [[ -n "$REGISTERED_AT" ]]; then
    echo "服務中斷約 $((REGISTERED_AT - T_RELEASE)) 秒"
else
    echo "服務中斷約 $(( $(date +%s) - T_RELEASE )) 秒（未取得 cloudflared 註冊時間）"
fi
