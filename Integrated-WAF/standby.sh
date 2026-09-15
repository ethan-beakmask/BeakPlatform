#!/bin/bash
# =============================================================================
# Integrated-WAF 防禦節點熱備切換工具
# =============================================================================
# 用法：
#   sudo bash standby.sh status        --service-ip IP
#   sudo bash standby.sh takeover      --service-ip IP [--state-file FILE|-] [--no-tunnel] [--no-services] [--force]
#   sudo bash standby.sh fence-check   --service-ip IP        （開機第二階段：被 fence 時停 cloudflared / od-bridge）
#   sudo bash standby.sh release       --service-ip IP [--keep-services]
#   sudo bash standby.sh export-state
#   sudo bash standby.sh import-state  [--state-file FILE|-]
#
# 共同選項：
#   --dir DIR       安裝目錄（預設 /opt/ithome2026-waf）
#   --iface IFACE   網卡（預設 .env 的 NODE_IFACE；沒有就由預設路由偵測）
#   -h, --help      顯示本說明
#
# 說明：
#   takeover 會把服務 IP 綁到本機、把子網與 default 路由 src 改成服務 IP、
#   建一條 SNAT 讓容器出站也用服務 IP（docker 的 MASQUERADE 只認網卡 primary 位址，
#   不認路由 src），啟用開機重做網路設定的 systemd unit，必要時匯入舊節點狀態，
#   最後啟動 od-bridge 與 cloudflared。release 反向做一遍：停只能單機跑的服務、
#   刪 SNAT、釋放服務 IP、路由 src 改回管理 IP。
#   腦裂防護：takeover 先做 ARP 重複位址偵測（DAD），服務 IP 已被別台持有就拒絕接手
#   （--force 可跳過）；開機時的 unit 走同一道檢查，被拒絕就標記 fence，docker 起來後
#   由 waf-service-fence.service 把 cloudflared / od-bridge 停掉，避免「掛掉的舊現役
#   修好重開後把服務搶回來」。
# =============================================================================
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/ithome2026-waf}"
ENV_FILE=""
OPT_IFACE=""
SERVICE_IP=""
STATE_FILE=""
NO_TUNNEL=0
NO_SERVICES=0
KEEP_SERVICES=0
BOOT_MODE=0
FORCE=0
FENCE_FLAG=/run/waf-service-ip.fenced

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
log_info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1" >&2; }
die()       { log_error "$1"; exit 1; }
usage() { awk 'NR > 1 { if ($0 !~ /^#/) exit; sub(/^# ?/, ""); print }' "${BASH_SOURCE[0]}"; }

[[ $# -gt 0 ]] || { usage; exit 0; }
case "${1:-}" in
    -h|--help) usage; exit 0 ;;
esac
MODE="$1"; shift

while [[ $# -gt 0 ]]; do
    case "$1" in
        --service-ip) SERVICE_IP="$2"; shift 2 ;;
        --state-file) STATE_FILE="$2"; shift 2 ;;
        --no-tunnel) NO_TUNNEL=1; shift ;;
        --no-services) NO_SERVICES=1; shift ;;
        --keep-services) KEEP_SERVICES=1; shift ;;
        --boot) BOOT_MODE=1; shift ;;
        --force) FORCE=1; shift ;;
        --dir) INSTALL_DIR="$2"; shift 2 ;;
        --iface) OPT_IFACE="$2"; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) die "未知參數：$1（--help 看用法）" ;;
    esac
done

[[ $EUID -eq 0 ]] || die "請用 sudo 執行；本工具不會自動 sudo"
ENV_FILE="$INSTALL_DIR/.env"

get_env() { grep -E "^$1=" "$ENV_FILE" 2>/dev/null | tail -1 | cut -d= -f2- ; }
compose() { (cd "$INSTALL_DIR" && docker compose "$@"); }
detect_iface() { ip -4 route show default 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="dev"){print $(i+1); exit}}'; }

need_dir() {
    [[ -d "$INSTALL_DIR" ]] || die "找不到安裝目錄：$INSTALL_DIR"
    [[ -f "$INSTALL_DIR/docker-compose.yml" ]] || die "找不到 $INSTALL_DIR/docker-compose.yml"
}

need_env() {
    need_dir
    [[ -f "$ENV_FILE" ]] || die "找不到 $ENV_FILE"
}

resolve_iface() {
    local iface="${OPT_IFACE:-}"
    [[ -n "$iface" ]] || iface="$(get_env NODE_IFACE)"
    [[ -n "$iface" ]] || iface="$(detect_iface)"
    [[ -n "$iface" ]] || die "偵測不到預設路由的網卡，請用 --iface 指定"
    printf '%s' "$iface"
}

first_global_cidr() {
    local iface="$1"
    ip -4 -o addr show dev "$iface" scope global | awk '{print $4; exit}'
}

# 管理 IP＝網卡上第一個「不是服務 IP」的 global 位址（服務 IP 可能排在前面）
mgmt_ip() {
    local iface="$1"
    ip -4 -o addr show dev "$iface" scope global | awk '{print $4}' | cut -d/ -f1 \
        | grep -vx "$SERVICE_IP" | head -1
}

SNAT_TABLE="ip wafsvc"
docker_subnet() { local s; s="$(get_env DOCKER_SUBNET)"; printf '%s' "${s:-172.18.0.0/16}"; }

# 容器出站走 docker 的 MASQUERADE，它選的是網卡的 primary 位址而不是路由的 src；
# 服務 IP 是後加的 secondary，所以要另外用一條 SNAT 明確指定，否則 WAF 轉發到
# 被保護網站、Vector 送事件到管制端的來源都會是管理 IP。獨立一張表，不受
# nftables.sh 重建 inet secstack 影響。
ensure_snat() {
    local iface="$1" subnet; subnet="$(docker_subnet)"
    nft add table $SNAT_TABLE
    nft add chain $SNAT_TABLE postrouting '{ type nat hook postrouting priority srcnat - 10; policy accept; }'
    nft flush chain $SNAT_TABLE postrouting
    nft add rule $SNAT_TABLE postrouting ip saddr "$subnet" oifname "$iface" snat to "$SERVICE_IP"
    log_info "已設定容器出站 SNAT：$subnet -> $SERVICE_IP"
}
remove_snat() {
    if nft list table $SNAT_TABLE >/dev/null 2>&1; then
        nft delete table $SNAT_TABLE
        log_info "已移除容器出站 SNAT"
    fi
}
snat_present() {
    nft list table $SNAT_TABLE 2>/dev/null | grep -q "snat to ${SERVICE_IP//./\\.}"
}

subnet_prefix() {
    local cidr="$1"
    python3 - "$cidr" <<'PY'
import ipaddress, sys
print(ipaddress.ip_interface(sys.argv[1]).network.with_prefixlen)
PY
}

route_json() {
    local target="$1" iface="$2"
    ip -j -4 route show "$target" dev "$iface" 2>/dev/null | python3 -c '
import json, sys
routes = json.load(sys.stdin)
print(json.dumps(routes[0] if routes else {}))
'
}

route_src() {
    local target="$1" iface="$2"
    route_json "$target" "$iface" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("prefsrc",""))'
}

replace_route_src() {
    local target="$1" iface="$2" src="$3" json
    json="$(route_json "$target" "$iface")"
    python3 - "$json" "$target" "$iface" "$src" <<'PY' | xargs -r ip route replace
import json, sys
r = json.loads(sys.argv[1])
target, fallback_dev, src = sys.argv[2:5]
if not r:
    raise SystemExit("找不到路由：%s dev %s" % (target, fallback_dev))
parts = [r.get("dst") or target]
if r.get("gateway"):
    parts += ["via", r["gateway"]]
parts += ["dev", r.get("dev") or fallback_dev]
if r.get("protocol"):
    parts += ["proto", r["protocol"]]
if r.get("scope"):
    parts += ["scope", r["scope"]]
if r.get("metric") is not None:
    parts += ["metric", str(r["metric"])]
parts += ["src", src]
print(" ".join(parts))
PY
}

# 保險：刪位址後若路由仍被 kernel 帶走，用刪除前記下的 default 路由重建
restore_routes_if_missing() {
    local iface="$1" prefix="$2" mgmt="$3" def_json="$4" gw
    if [[ -z "$(route_src "$prefix" "$iface")" ]]; then
        ip route replace "$prefix" dev "$iface" proto kernel scope link src "$mgmt"
        log_warn "子網路由曾消失，已重建（src $mgmt）"
    fi
    if [[ -z "$(route_src default "$iface")" ]]; then
        gw="$(printf '%s' "$def_json" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("gateway",""))')"
        [[ -n "$gw" ]] || die "default 路由消失且無法得知閘道，請手動 ip route add default via <閘道> dev $iface"
        ip route replace default via "$gw" dev "$iface" src "$mgmt"
        log_warn "default 路由曾消失，已重建（via $gw src $mgmt）"
    fi
}

url_host() { printf '%s' "$1" | sed -E 's#^[a-z]+://##; s#[:/].*$##'; }

# 主動讓「會回應我們的鄰居」學到新 MAC：閘道、被保護網站、管制端。
# 只靠 gratuitous ARP 不夠——不少路由器忽略它，快取要等 60～90 秒才老化，
# 這段時間 cloudflared 出站、WAF 轉發全部失敗（2026 實測第二次切換中斷 90 秒）。
# ARP「請求」的 sender 欄位幾乎所有裝置都會採信，所以對每個鄰居發一次以服務 IP 為 sender 的請求。
announce_arp() {
    local iface="$1" gw target targets=()
    gw="$(ip -4 route show default dev "$iface" | awk '{for(i=1;i<=NF;i++) if($i=="via"){print $(i+1); exit}}')"
    [[ -n "$gw" ]] && targets+=("$gw")
    for target in "$(url_host "$(get_env WAF_BACKEND_URL)")" "$(url_host "$(get_env BEAK_BASE_URL)")"; do
        [[ "$target" =~ ^[0-9.]+$ ]] && targets+=("$target")
    done
    if command -v arping >/dev/null; then
        arping -U -c 1 -w 1 -I "$iface" -s "$SERVICE_IP" "$SERVICE_IP" >/dev/null 2>&1 &
        for target in "${targets[@]}"; do
            arping -c 2 -w 2 -I "$iface" -s "$SERVICE_IP" "$target" >/dev/null 2>&1 &
        done
        wait
        log_info "已向 ${targets[*]:-（無）} 宣告服務 IP 的 MAC（arping）"
    else
        # 沒有 arping：清掉本機對鄰居的快取，再以服務 IP 為來源 ping 一下，逼 kernel 發 ARP 請求
        for target in "${targets[@]}"; do
            ip neigh flush to "$target" dev "$iface" >/dev/null 2>&1 || true
            ping -c 1 -W 1 -I "$SERVICE_IP" "$target" >/dev/null 2>&1 || true
        done
        log_info "已向 ${targets[*]:-（無）} 宣告服務 IP 的 MAC（ARP 請求；建議安裝 iputils-arping）"
    fi
}

# ARP 重複位址偵測：服務 IP 若已有別台在回應，回 0（衝突）並印出對方 MAC
service_ip_taken() {
    local iface="$1" out
    service_ip_bound "$iface" && return 1        # 自己已持有就不算衝突（冪等重跑）
    command -v arping >/dev/null || return 1     # 沒有 arping 只能略過
    if out="$(arping -D -c 2 -w 2 -I "$iface" "$SERVICE_IP" 2>&1)"; then
        return 1
    fi
    printf '%s\n' "$out" | grep -o '\[[0-9A-Fa-f:]*\]' | head -1 | tr -d '[]'
    return 0
}

fence_check() {
    need_env
    [[ -n "$SERVICE_IP" ]] || die "fence-check 需要 --service-ip"
    if [[ -f "$FENCE_FLAG" ]]; then
        log_warn "開機時偵測到服務 IP $SERVICE_IP 已被別台持有（$(cat "$FENCE_FLAG")），本機退為待命：停 cloudflared / od-bridge"
        compose --profile tunnel stop -t 3 cloudflared >/dev/null 2>&1 || true
        compose stop -t 3 od-bridge >/dev/null 2>&1 || true
        logger -t waf-standby "fenced: service ip $SERVICE_IP held by $(cat "$FENCE_FLAG"); cloudflared/od-bridge stopped"
        log_warn "要讓本機回到現役，先在對方執行 release，再於本機執行 takeover；或用 failover.sh"
    else
        log_info "未被 fence，維持現役"
    fi
}

service_ip_bound() {
    local iface="$1"
    ip -4 addr show dev "$iface" | grep -Eq "inet ${SERVICE_IP//./\\.}/"
}

count_set() {
    local setname="$1"
    nft -j list set inet secstack "$setname" 2>/dev/null | python3 -c 'import json,sys; d=json.load(sys.stdin); print(sum(len(x["set"].get("elem",[])) for x in d.get("nftables",[]) if "set" in x))' 2>/dev/null || printf '0'
}

service_state() {
    local svc="$1" state="absent"
    # docker 沒在跑就直接回 stopped：開機 unit 排在 docker.service 之前，這時呼叫 docker CLI
    # 會觸發 socket activation 去等 docker.service，而 docker.service 又在等本 unit → 開機死鎖
    systemctl is-active --quiet docker 2>/dev/null || { printf 'stopped'; return; }
    if compose ps --format json "$svc" >/tmp/standby-ps.$$ 2>/dev/null; then
        state="$(python3 - "$svc" /tmp/standby-ps.$$ <<'PY'
import json, sys
svc, path = sys.argv[1:3]
text = open(path, encoding="utf-8").read().strip()
if not text:
    print("stopped")
    raise SystemExit
rows = []
for line in text.splitlines():
    try:
        rows.append(json.loads(line))
    except json.JSONDecodeError:
        pass
if not rows:
    print("stopped")
    raise SystemExit
for row in rows:
    service = row.get("Service") or row.get("Name") or ""
    if service == svc or service.endswith("_" + svc):
        status = (row.get("State") or row.get("Status") or "").lower()
        print("running" if "running" in status else "stopped")
        break
else:
    print("stopped")
PY
)"
        rm -f /tmp/standby-ps.$$
    fi
    printf '%s' "$state"
}

status_json() {
    need_env
    [[ -n "$SERVICE_IP" ]] || die "status 需要 --service-ip"
    local iface cidr mgmt prefix rsrc holds unit snat
    iface="$(resolve_iface)"
    cidr="$(first_global_cidr "$iface")"; [[ -n "$cidr" ]] || die "$iface 沒有 global IPv4"
    prefix="$(subnet_prefix "$cidr")"
    rsrc="$(route_src "$prefix" "$iface")"
    mgmt="$(mgmt_ip "$iface")"
    holds=false; service_ip_bound "$iface" && holds=true
    unit=false; [[ -f /etc/systemd/system/waf-service-ip.service ]] && unit=true
    snat=false; snat_present && snat=true
    local fenced=false; [[ -f "$FENCE_FLAG" ]] && fenced=true
    local cf_ready=false; cloudflared_ready && cf_ready=true
    python3 - "$iface" "$mgmt" "$SERVICE_IP" "$holds" "$rsrc" "$(service_state cloudflared)" "$(service_state od-bridge)" "$(count_set blocklist)" "$(count_set blocklist6)" "$unit" "$ENV_FILE" "$snat" "$fenced" "$cf_ready" <<'PY'
import json, socket, sys
iface, mgmt, service_ip, holds, route_src, cf, od, bl, bl6, unit, env_file, snat, fenced, cf_ready = sys.argv[1:15]
keys = ["CF_HOSTNAME", "WELCOME_HOSTNAME", "WAF_BACKEND_PATH", "WAF_BACKEND_URL", "BEAK_BASE_URL"]
env = {k: "" for k in keys}
try:
    for line in open(env_file, encoding="utf-8"):
        line = line.rstrip("\n")
        if "=" in line:
            k, v = line.split("=", 1)
            if k in env:
                env[k] = v
except FileNotFoundError:
    pass
print(json.dumps({
    "hostname": socket.gethostname(),
    "iface": iface,
    "mgmt_ip": mgmt,
    "service_ip": service_ip,
    "holds_service_ip": holds == "true",
    "route_src": route_src,
    "cloudflared": cf,
    "od_bridge": od,
    "blocklist_count": int(bl),
    "blocklist6_count": int(bl6),
    "unit_installed": unit == "true",
    "snat_rule": snat == "true",
    "fenced": fenced == "true",
    "cloudflared_ready": cf_ready == "true",
    "env": env,
}, ensure_ascii=False, separators=(",", ":")))
PY
}

write_unit() {
    local ip="$1"
    cat > /etc/systemd/system/waf-service-ip.service <<EOT
[Unit]
Description=Integrated-WAF service IP warm standby takeover
After=network-online.target nftables.service
Wants=network-online.target
Before=docker.service

[Service]
Type=oneshot
ExecStart=/bin/bash $INSTALL_DIR/standby.sh takeover --service-ip $ip --no-services --boot
RemainAfterExit=yes
TimeoutStartSec=90

[Install]
WantedBy=multi-user.target
EOT
    # 第二階段：docker 起來之後，被 fence 的話把只能單機跑的容器停掉
    cat > /etc/systemd/system/waf-service-fence.service <<EOT
[Unit]
Description=Integrated-WAF warm standby fence (stop cloudflared/od-bridge if service IP is held elsewhere)
After=docker.service waf-service-ip.service
Requires=docker.service

[Service]
Type=oneshot
ExecStart=/bin/bash $INSTALL_DIR/standby.sh fence-check --service-ip $ip
RemainAfterExit=yes
TimeoutStartSec=120

[Install]
WantedBy=multi-user.target
EOT
    systemctl daemon-reload
    systemctl enable waf-service-ip.service waf-service-fence.service >/dev/null
}

disable_unit() {
    systemctl disable waf-service-ip.service waf-service-fence.service >/dev/null 2>&1 || true
    rm -f /etc/systemd/system/waf-service-ip.service /etc/systemd/system/waf-service-fence.service "$FENCE_FLAG"
    systemctl daemon-reload
}

read_state_payload() {
    local file="$1"
    if [[ "$file" == "-" ]]; then
        cat
    else
        [[ -f "$file" ]] || die "找不到狀態檔：$file"
        cat "$file"
    fi
}

export_state() {
    need_dir
    local bl_file bl6_file
    bl_file="$(mktemp)"; bl6_file="$(mktemp)"
    nft -j list set inet secstack blocklist > "$bl_file" 2>/dev/null || true
    nft -j list set inet secstack blocklist6 > "$bl6_file" 2>/dev/null || true
    python3 - "$INSTALL_DIR" "$bl_file" "$bl6_file" <<'PY'
import json, os, socket, sys
from datetime import datetime, timezone
install_dir, bl_path, bl6_path = sys.argv[1:4]
def parse(path):
    raw = open(path, encoding="utf-8").read()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None
edl_path = os.path.join(install_dir, "od-bridge", "state", "edl", "state.json")
edl = None
if os.path.exists(edl_path):
    with open(edl_path, encoding="utf-8") as fh:
        edl = json.load(fh)
print(json.dumps({
    "version": 1,
    "exported_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    "host": socket.gethostname(),
    "blocklist": parse(bl_path),
    "blocklist6": parse(bl6_path),
    "edl_state": edl,
}, ensure_ascii=False))
PY
    rm -f "$bl_file" "$bl6_file"
}

import_one_set() {
    local state_path="$1" key="$2" setname="$3" tmp elems elem imported=0 skipped=0
    tmp="$(mktemp)"
    python3 - "$state_path" "$key" > "$tmp" <<'PY'
import json, sys
with open(sys.argv[1], encoding="utf-8") as fh:
    d = json.load(fh)
v = d.get(sys.argv[2])
if v is not None:
    print(json.dumps(v))
PY
    if [[ -s "$tmp" ]]; then
        elems="$(python3 "$INSTALL_DIR/nftset_elems.py" < "$tmp" 2>/dev/null || true)"
        while IFS= read -r elem; do
            [[ -n "$elem" ]] || continue
            if nft add element inet secstack "$setname" "{ $elem }" 2>/dev/null; then
                imported=$((imported + 1))
            else
                skipped=$((skipped + 1))
            fi
        done <<< "$elems"
    fi
    rm -f "$tmp"
    printf '%s 匯入 %d 筆（略過 %d）\n' "$setname" "$imported" "$skipped"
}

import_state_payload() {
    need_dir
    [[ -f "$INSTALL_DIR/nftset_elems.py" ]] || die "找不到 $INSTALL_DIR/nftset_elems.py"
    local payload="$1" state_path edl_dir edl_file
    state_path="$(mktemp)"
    printf '%s' "$payload" > "$state_path"
    python3 -c 'import json,sys; d=json.load(open(sys.argv[1], encoding="utf-8")); assert d.get("version")==1' "$state_path" \
        || die "狀態檔格式不正確"
    import_one_set "$state_path" blocklist blocklist
    import_one_set "$state_path" blocklist6 blocklist6
    edl_dir="$INSTALL_DIR/od-bridge/state/edl"
    edl_file="$edl_dir/state.json"
    if python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8")).get("edl_state") is not None)' "$state_path" | grep -q True; then
        mkdir -p "$edl_dir"
        [[ -f "$edl_file" ]] && cp -a "$edl_file" "$edl_file.bak"
        python3 - "$state_path" "$edl_file" <<'PY'
import json, sys
with open(sys.argv[1], encoding="utf-8") as fh:
    d = json.load(fh)
with open(sys.argv[2], "w", encoding="utf-8") as fh:
    json.dump(d["edl_state"], fh, ensure_ascii=False, indent=2)
    fh.write("\n")
PY
        log_info "EDL 狀態已匯入：$edl_file"
    else
        log_info "EDL 狀態為空，略過"
    fi
    rm -f "$state_path"
}

do_import_state() {
    local file="${STATE_FILE:-}"
    [[ -n "$file" ]] || die "import-state 需要 --state-file FILE 或 -"
    import_state_payload "$(read_state_payload "$file")"
}

# cloudflared 有沒有連上，以它自己的 /ready 端點為準（readyConnections > 0）。
# 不要靠 docker logs：實測主機硬重置後 json-file log 會停止更新，容器明明已註冊、log 卻停在 precheck，
# 用 log 判定會誤報「120 秒內尚未註冊」。/ready 的 metrics 埠預設從 20241 起找五個。
cloudflared_ready() {
    local ip port
    ip="$(get_env CLOUDFLARED_IP)"; ip="${ip:-172.18.0.250}"
    for port in 20241 20242 20243 20244 20245; do
        if curl -s -m 2 "http://$ip:$port/ready" 2>/dev/null | grep -Eq '"readyConnections":[1-9]'; then
            return 0
        fi
    done
    return 1
}

wait_cloudflared() {
    local start_epoch="$1" elapsed now
    for elapsed in $(seq 0 120); do
        if cloudflared_ready; then
            now="$(date +%s)"
            log_info "cloudflared 已註冊（/ready），耗時 $((now - start_epoch)) 秒"
            echo "CLOUDFLARED_REGISTERED_AT=$now"
            return 0
        fi
        sleep 1
    done
    log_warn "cloudflared 120 秒內尚未就緒（/ready 無連線）；請用 status 與 curl 確認實況再決定是否回退"
    return 1
}

print_summary() {
    local iface="$1" prefix="$2"
    echo
    echo "摘要："
    echo "  服務 IP：$SERVICE_IP"
    echo "  路由 src：$(route_src "$prefix" "$iface")"
    echo "  容器出站 SNAT：$(snat_present && echo 有 || echo 無)"
    echo "  cloudflared：$(service_state cloudflared)"
    echo "  od-bridge：$(service_state od-bridge)"
    echo "  blocklist：$(count_set blocklist) 筆；blocklist6：$(count_set blocklist6) 筆"
}

takeover() {
    need_env
    [[ -n "$SERVICE_IP" ]] || die "takeover 需要 --service-ip"
    local iface cidr prefix cf_start
    iface="$(resolve_iface)"
    cidr="$(first_global_cidr "$iface")"; [[ -n "$cidr" ]] || die "$iface 沒有 global IPv4"
    [[ -n "$(mgmt_ip "$iface")" ]] || die "$iface 上除了服務 IP 沒有其他位址；管理 IP 必須先綁好（固定 IP）"
    prefix="$(subnet_prefix "$cidr")"
    sysctl -w "net.ipv4.conf.$iface.arp_notify=1" >/dev/null
    rm -f "$FENCE_FLAG"
    local holder
    if holder="$(service_ip_taken "$iface")"; then
        if [[ $FORCE -eq 1 ]]; then
            log_warn "服務 IP $SERVICE_IP 已有別台在回應（$holder），--force 強制接手"
        elif [[ $BOOT_MODE -eq 1 ]]; then
            printf '%s' "${holder:-unknown}" > "$FENCE_FLAG"
            log_warn "服務 IP $SERVICE_IP 已被別台持有（$holder），本機不接手（fence）"
            exit 0
        else
            die "服務 IP $SERVICE_IP 已有別台在回應（$holder）。先在對方執行 release，或確定對方已死再加 --force"
        fi
    fi
    if service_ip_bound "$iface"; then
        log_info "服務 IP 已綁定：$SERVICE_IP"
    else
        ip addr add "$SERVICE_IP/${cidr#*/}" dev "$iface"
        log_info "已綁定服務 IP：$SERVICE_IP"
    fi
    replace_route_src "$prefix" "$iface" "$SERVICE_IP"
    replace_route_src default "$iface" "$SERVICE_IP"
    ensure_snat "$iface"
    announce_arp "$iface"
    write_unit "$SERVICE_IP"
    if [[ -n "$STATE_FILE" ]]; then
        import_state_payload "$(read_state_payload "$STATE_FILE")"
    fi
    if [[ $NO_SERVICES -eq 0 ]]; then
        compose up -d od-bridge
        if [[ $NO_TUNNEL -eq 0 ]]; then
            if [[ "$(service_state cloudflared)" == "running" ]]; then
                log_info "cloudflared 已在運行，不重啟"
            else
                cf_start="$(date +%s)"
                compose --profile tunnel up -d cloudflared
                wait_cloudflared "$cf_start"
            fi
        fi
    fi
    print_summary "$iface" "$prefix"
}

release() {
    need_env
    [[ -n "$SERVICE_IP" ]] || die "release 需要 --service-ip"
    local iface cidr mgmt prefix
    iface="$(resolve_iface)"
    cidr="$(first_global_cidr "$iface")"; [[ -n "$cidr" ]] || die "$iface 沒有 global IPv4"
    mgmt="$(mgmt_ip "$iface")"
    [[ -n "$mgmt" ]] || die "$iface 上除了服務 IP 沒有其他位址，釋放後會失聯；請先綁好管理 IP"
    prefix="$(subnet_prefix "$cidr")"
    if [[ $KEEP_SERVICES -eq 0 ]]; then
        # -t 3：cloudflared 一收到 SIGTERM 就會向 Cloudflare 註銷，不必等 compose 預設的 10 秒
        compose --profile tunnel stop -t 3 cloudflared >/dev/null 2>&1 || true
        compose stop -t 3 od-bridge >/dev/null 2>&1 || true
    fi
    disable_unit
    remove_snat
    # 順序不能反：kernel 刪除位址時會連帶刪掉 prefsrc 指向它的路由（子網路由與 default 都會消失，
    # 主機立刻失聯、連 ARP 都不回）。所以先把 src 改回管理 IP，再刪服務 IP。
    local def_json; def_json="$(route_json default "$iface")"
    replace_route_src "$prefix" "$iface" "$mgmt"
    replace_route_src default "$iface" "$mgmt"
    if service_ip_bound "$iface"; then
        ip addr del "$SERVICE_IP/${cidr#*/}" dev "$iface"
        log_info "已釋放服務 IP：$SERVICE_IP"
    else
        log_info "服務 IP 未綁定，略過釋放：$SERVICE_IP"
    fi
    restore_routes_if_missing "$iface" "$prefix" "$mgmt" "$def_json"
    print_summary "$iface" "$prefix"
}

case "$MODE" in
    status) status_json ;;
    takeover) takeover ;;
    release) release ;;
    export-state) export_state ;;
    fence-check) fence_check ;;
    import-state) do_import_state ;;
    *) die "未知子命令：$MODE（--help 看用法）" ;;
esac
