#!/bin/bash
# =============================================================================
# ITHome2026-WAF 防禦節點一鍵安裝
# 適用於 Ubuntu 22.04 / 24.04 LTS（amd64），需要 sudo 與可連 Internet
# =============================================================================
# 這台主機會裝上：
#   WAF（nginx + ModSecurity + OWASP CRS）、Suricata（網路 IDS）、CrowdSec、
#   Vector（事件正規化）、ClickHouse（事件庫）、od-bridge（把事件送進 BeakPlatform、
#   把平台的封鎖決策落地到 nftables / CrowdSec / EDL）、cloudflared（對外入口）
#   以及選用的 Grafana / EveBox / Portainer。
#
# 用法：
#   sudo bash install.sh --pair '<開通字串>' --backend http://<被保護網站>:<埠> [其他選項]
#   sudo bash install.sh --reconfigure          改過 .env 後重新產生設定並套用
#   sudo bash install.sh --status               看服務狀態
#   sudo bash install.sh --verify               健康檢查（不產生事件）
#   sudo bash install.sh --test-event           送一筆測試事件到平台，驗證整條鏈
#   sudo bash install.sh --update               從 GitHub 更新程式後重新套用
#   sudo bash install.sh --update-rules         重新下載 Suricata 規則（套用 suricata/disable.conf）並重載
#   sudo bash install.sh --uninstall            停止並移除（資料卷保留，加 --purge 才刪）
#
# 選項（都可以之後在 <安裝目錄>/.env 改，再跑 --reconfigure）：
#   --pair '<ODN1...>'        平台端 scripts/od_node_pairing.py 產生的開通字串
#                             （內含平台網址、事件受理金鑰、執行帳號）
#   --base-url URL            平台網址（不用開通字串時手動填，含 /beakplatform 前綴）
#   --intake-key-id ID --intake-secret S --sa-id ID --sa-secret S   同上，手動填
#   --backend URL             【必填】被保護網站在內網的位址，例 http://192.168.1.30:8000
#   --tunnel-token TOKEN      Cloudflare Zero Trust 後台複製的 connector token
#   --cf-api-token T --cf-hostname app.example.com [--cf-tunnel-name NAME]
#                             改用 Cloudflare API 自動建 tunnel / DNS / ingress
#   --welcome-hostname www.example.com
#                             「歡迎頁」（示意首頁），有自己的 WAF；搭配 --cf-api-token 會自動加
#                             ingress 與 DNS。可以和 --cf-hostname 同名：此時根路徑是歡迎頁，
#                             只有 --backend-path 的路徑導到被保護網站
#   --backend-path /app       被保護網站在對外 hostname 下的路徑前綴（與歡迎頁同名時必填）
#   --admin-ips a.b.c.d,...   允許管理本機的來源 IP（預設：平台主機 + 你 SSH 進來的那台）
#   --ip / --iface            本機 IP 與網卡（預設由預設路由自動偵測）
#   --home-net '[..]'         Suricata HOME_NET（預設三段私有網段）
#   --no-ui                   不啟動 Grafana / EveBox / Portainer
#   --ssh-guard               SSH 也限制成只有 ADMIN_IPS 能連（確定清單無誤再開）
#   --dir DIR                 安裝目錄（預設 /opt/ithome2026-waf）
#   --yes                     非互動，缺值直接報錯
#
# 環境變數（只在需要從 GitHub 抓程式時用到）：
#   GITHUB_REPO   預設 https://github.com/ethan-beakmask/BeakPlatform.git
#   GITHUB_TOKEN  repo 為私有時的 Personal Access Token
#   GIT_REF       分支或 tag（預設 main）
# =============================================================================
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/ithome2026-waf}"
GITHUB_REPO="${GITHUB_REPO:-https://github.com/ethan-beakmask/BeakPlatform.git}"
GIT_REF="${GIT_REF:-main}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
log_info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1" >&2; }
log_step()  { echo -e "${BLUE}[$1]${NC} $2"; }
die()       { log_error "$1"; exit 1; }

# ----------------------------------------------------------------------------
# 參數
# ----------------------------------------------------------------------------
MODE="install"
OPT_PAIR=""; OPT_BASE_URL=""; OPT_KEY_ID=""; OPT_SECRET=""; OPT_SA_ID=""; OPT_SA_SECRET=""
OPT_BACKEND=""; OPT_TUNNEL_TOKEN=""; OPT_CF_TOKEN=""; OPT_CF_HOST=""; OPT_CF_TUNNEL="ithome2026-waf"
OPT_ADMIN_IPS=""; OPT_IP=""; OPT_IFACE=""; OPT_HOME_NET=""; OPT_NO_UI=0; OPT_SSH_GUARD=""; OPT_WELCOME=""; OPT_BACKEND_PATH=""
OPT_YES=0; OPT_PURGE=0

usage() { sed -n '2,45p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; }

while [[ $# -gt 0 ]]; do
    case "$1" in
        --pair)           OPT_PAIR="$2"; shift 2 ;;
        --base-url)       OPT_BASE_URL="$2"; shift 2 ;;
        --intake-key-id)  OPT_KEY_ID="$2"; shift 2 ;;
        --intake-secret)  OPT_SECRET="$2"; shift 2 ;;
        --sa-id)          OPT_SA_ID="$2"; shift 2 ;;
        --sa-secret)      OPT_SA_SECRET="$2"; shift 2 ;;
        --backend)        OPT_BACKEND="$2"; shift 2 ;;
        --tunnel-token)   OPT_TUNNEL_TOKEN="$2"; shift 2 ;;
        --cf-api-token)   OPT_CF_TOKEN="$2"; shift 2 ;;
        --cf-hostname)    OPT_CF_HOST="$2"; shift 2 ;;
        --cf-tunnel-name) OPT_CF_TUNNEL="$2"; shift 2 ;;
        --welcome-hostname) OPT_WELCOME="$2"; shift 2 ;;
        --backend-path)   OPT_BACKEND_PATH="$2"; shift 2 ;;
        --admin-ips)      OPT_ADMIN_IPS="$2"; shift 2 ;;
        --ip)             OPT_IP="$2"; shift 2 ;;
        --iface)          OPT_IFACE="$2"; shift 2 ;;
        --home-net)       OPT_HOME_NET="$2"; shift 2 ;;
        --no-ui)          OPT_NO_UI=1; shift ;;
        --ssh-guard)      OPT_SSH_GUARD=1; shift ;;
        --dir)            INSTALL_DIR="$2"; shift 2 ;;
        --yes|-y)         OPT_YES=1; shift ;;
        --purge)          OPT_PURGE=1; shift ;;
        --reconfigure)    MODE="reconfigure"; shift ;;
        --status)         MODE="status"; shift ;;
        --verify)         MODE="verify"; shift ;;
        --test-event)     MODE="test-event"; shift ;;
        --update)         MODE="update"; shift ;;
        --update-rules)   MODE="update-rules"; shift ;;
        --uninstall)      MODE="uninstall"; shift ;;
        -h|--help)        usage; exit 0 ;;
        *) die "未知參數：$1（--help 看用法）" ;;
    esac
done

[[ $EUID -eq 0 ]] || die "請用 sudo 執行：sudo bash $0 ..."
ENV_FILE="$INSTALL_DIR/.env"

# ----------------------------------------------------------------------------
# 小工具
# ----------------------------------------------------------------------------
get_env() { grep -E "^$1=" "$ENV_FILE" 2>/dev/null | tail -1 | cut -d= -f2- ; }
set_env() {   # set_env KEY VALUE  （存在就取代，不存在就追加）
    local k="$1" v="$2"
    if grep -qE "^$k=" "$ENV_FILE"; then
        python3 - "$ENV_FILE" "$k" "$v" <<'PY'
import sys, re
path, key, val = sys.argv[1:4]
lines = open(path, encoding="utf-8").read().splitlines()
out = []
for line in lines:
    if re.match(r"^%s=" % re.escape(key), line):
        out.append("%s=%s" % (key, val))
    else:
        out.append(line)
open(path, "w", encoding="utf-8").write("\n".join(out) + "\n")
PY
    else
        printf '%s=%s\n' "$k" "$v" >> "$ENV_FILE"
    fi
}
set_env_if_empty() { [[ -n "$(get_env "$1")" ]] || set_env "$1" "$2"; }
gen_secret() { python3 -c 'import secrets; print(secrets.token_urlsafe(32))'; }
platform_ip_from_url() { printf '%s' "$1" | sed -E 's#^[a-z]+://##; s#[:/].*$##'; }
compose() { (cd "$INSTALL_DIR" && docker compose "$@"); }

detect_iface() { ip -4 route show default 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="dev"){print $(i+1); exit}}'; }
detect_ip()    { ip -4 -o addr show dev "$1" 2>/dev/null | awk '{print $4}' | cut -d/ -f1 | head -1; }
ssh_client_ip() {
    local ip=""
    [[ -n "${SSH_CONNECTION:-}" ]] && ip="${SSH_CONNECTION%% *}"
    [[ -z "$ip" && -n "${SUDO_USER:-}" ]] && ip="$(who 2>/dev/null | awk -v u="$SUDO_USER" '$1==u && $NF ~ /^\(/ {gsub(/[()]/,"",$NF); print $NF; exit}')"
    [[ "$ip" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] && printf '%s' "$ip" || true
}
uniq_csv() { printf '%s\n' "$@" | tr ',' '\n' | sed 's/[[:space:]]//g' | grep -v '^$' | awk '!seen[$0]++' | paste -sd, -; }

decode_pair() {   # 印出 KEY=VALUE 行
    python3 - "$1" <<'PY'
import base64, json, sys
s = sys.argv[1].strip()
if not s.startswith("ODN1."):
    sys.exit("開通字串格式不對（應以 ODN1. 開頭）")
raw = s[5:]
raw += "=" * (-len(raw) % 4)
d = json.loads(base64.urlsafe_b64decode(raw.encode()).decode())
mapping = {"base_url": "BEAK_BASE_URL", "key_id": "INTAKE_KEY_ID", "secret": "INTAKE_SECRET_B64",
           "sa_id": "SA_ID", "sa_secret": "SA_SECRET"}
for k, env in mapping.items():
    if d.get(k):
        print("%s=%s" % (env, d[k]))
if d.get("org"):
    print("PAIR_ORG=%s" % d["org"])
PY
}

# ----------------------------------------------------------------------------
# 1. 套件
# ----------------------------------------------------------------------------
install_packages() {
    log_step "1/8" "安裝套件（docker、nftables、git、python3）"
    local need=()
    command -v docker >/dev/null || need+=(docker.io)
    docker compose version >/dev/null 2>&1 || need+=(docker-compose-v2)
    command -v nft >/dev/null || need+=(nftables)
    command -v git >/dev/null || need+=(git)
    command -v python3 >/dev/null || need+=(python3)
    command -v curl >/dev/null || need+=(curl)
    command -v rsync >/dev/null || need+=(rsync)
    if [[ ${#need[@]} -gt 0 ]]; then
        export DEBIAN_FRONTEND=noninteractive
        apt-get update -qq
        apt-get install -y -qq "${need[@]}"
    fi
    systemctl enable --now docker >/dev/null 2>&1 || true
    docker compose version >/dev/null 2>&1 || die "docker compose plugin 不可用"
    log_info "docker $(docker --version | awk '{print $3}' | tr -d ,)、$(docker compose version --short 2>/dev/null | sed 's/^/compose /')"
}

# ----------------------------------------------------------------------------
# 2. 程式來源 → 安裝目錄
# ----------------------------------------------------------------------------
fetch_source() {
    log_step "2/8" "準備安裝目錄 $INSTALL_DIR"
    local src=""
    if [[ -f "$HERE/docker-compose.yml" && -f "$HERE/nftables.sh" ]]; then
        src="$HERE"
    else
        local tmp; tmp="$(mktemp -d)"
        local url="$GITHUB_REPO"
        if [[ -n "${GITHUB_TOKEN:-}" && "$url" == https://github.com/* ]]; then
            url="https://${GITHUB_TOKEN}@github.com/${url#https://github.com/}"
        fi
        log_info "從 $GITHUB_REPO（$GIT_REF）取得 ITHome2026-WAF/"
        git clone --quiet --depth 1 --branch "$GIT_REF" --filter=blob:none --sparse "$url" "$tmp/repo" \
            || die "git clone 失敗（私有 repo 請設 GITHUB_TOKEN）"
        (cd "$tmp/repo" && git sparse-checkout set ITHome2026-WAF --quiet)
        [[ -f "$tmp/repo/ITHome2026-WAF/docker-compose.yml" ]] || die "repo 內找不到 ITHome2026-WAF/"
        src="$tmp/repo/ITHome2026-WAF"
    fi
    mkdir -p "$INSTALL_DIR"
    if [[ "$(cd "$src" && pwd)" != "$(cd "$INSTALL_DIR" && pwd)" ]]; then
        rsync -a --exclude '.env' --exclude 'generated/' --exclude 'od-bridge/state/' \
              --exclude 'suricata/rules/' --exclude 'waf/log/' --exclude '.git/' \
              "$src/" "$INSTALL_DIR/"
    fi
    mkdir -p "$INSTALL_DIR/generated" "$INSTALL_DIR/od-bridge/state" \
             "$INSTALL_DIR/suricata/rules" "$INSTALL_DIR/waf/log"
    chown -R 101:101 "$INSTALL_DIR/waf/log"
    chmod +x "$INSTALL_DIR/nftables.sh" "$INSTALL_DIR/install.sh" "$INSTALL_DIR/cf_tunnel.py" 2>/dev/null || true
}

# ----------------------------------------------------------------------------
# 3. .env
# ----------------------------------------------------------------------------
build_env() {
    log_step "3/8" "寫入設定 $ENV_FILE"
    [[ -f "$ENV_FILE" ]] || { cp "$INSTALL_DIR/.env.example" "$ENV_FILE"; chmod 600 "$ENV_FILE"; }
    # 新版 .env.example 多出來的鍵補進既有 .env（值留空由下面補）
    while IFS= read -r line; do
        [[ "$line" =~ ^[A-Z_]+= ]] || continue
        local k="${line%%=*}"
        grep -qE "^$k=" "$ENV_FILE" || printf '%s\n' "$line" >> "$ENV_FILE"
    done < "$INSTALL_DIR/.env.example"

    # 開通字串
    if [[ -n "$OPT_PAIR" ]]; then
        local out; out="$(decode_pair "$OPT_PAIR")" || die "開通字串解析失敗"
        while IFS= read -r kv; do
            [[ -n "$kv" ]] && set_env "${kv%%=*}" "${kv#*=}"
        done <<< "$out"
        log_info "已套用開通字串（企業：$(get_env PAIR_ORG)）"
    fi
    [[ -n "$OPT_BASE_URL" ]]  && set_env BEAK_BASE_URL "${OPT_BASE_URL%/}"
    [[ -n "$OPT_KEY_ID" ]]    && set_env INTAKE_KEY_ID "$OPT_KEY_ID"
    [[ -n "$OPT_SECRET" ]]    && set_env INTAKE_SECRET_B64 "$OPT_SECRET"
    [[ -n "$OPT_SA_ID" ]]     && set_env SA_ID "$OPT_SA_ID"
    [[ -n "$OPT_SA_SECRET" ]] && set_env SA_SECRET "$OPT_SA_SECRET"
    [[ -n "$OPT_BACKEND" ]]   && set_env WAF_BACKEND_URL "$OPT_BACKEND"
    [[ -n "$OPT_TUNNEL_TOKEN" ]] && set_env CLOUDFLARE_TUNNEL_TOKEN "$OPT_TUNNEL_TOKEN"
    [[ -n "$OPT_HOME_NET" ]]  && set_env HOME_NET "$OPT_HOME_NET"
    [[ -n "$OPT_SSH_GUARD" ]] && set_env SSH_GUARD "$OPT_SSH_GUARD"

    # 本機網路
    local iface ip
    iface="${OPT_IFACE:-$(get_env NODE_IFACE)}"; [[ -n "$iface" ]] || iface="$(detect_iface)"
    [[ -n "$iface" ]] || die "偵測不到預設路由的網卡，請用 --iface 指定"
    ip="${OPT_IP:-}"; [[ -n "$ip" ]] || ip="$(detect_ip "$iface")"
    [[ -n "$ip" ]] || die "偵測不到 $iface 的 IPv4，請用 --ip 指定"
    set_env NODE_IFACE "$iface"; set_env NODE_IP "$ip"

    [[ -n "$OPT_WELCOME" ]] && set_env WELCOME_HOSTNAME "$OPT_WELCOME"
    [[ -n "$OPT_BACKEND_PATH" ]] && set_env WAF_BACKEND_PATH "$OPT_BACKEND_PATH"

    # Cloudflare API 自動建 tunnel（主站 + 歡迎頁）
    if [[ -n "$OPT_CF_TOKEN" ]]; then
        [[ -n "$OPT_CF_HOST" ]] || die "--cf-api-token 要搭配 --cf-hostname"
        local main_path=""
        if [[ -n "$(get_env WELCOME_HOSTNAME)" && "$(get_env WELCOME_HOSTNAME)" == "$OPT_CF_HOST" ]]; then
            [[ -n "$(get_env WAF_BACKEND_PATH)" ]] || die "歡迎頁與主站同名時要給 --backend-path（被保護網站的路徑前綴，例 /beakplatform）"
            main_path="^$(get_env WAF_BACKEND_PATH)(/|\$)"
        fi
        CF_API_TOKEN="$OPT_CF_TOKEN" python3 "$INSTALL_DIR/cf_tunnel.py" setup \
            --hostname "$OPT_CF_HOST" --tunnel-name "$OPT_CF_TUNNEL" --write-env "$ENV_FILE" \
            ${main_path:+--path "$main_path"} \
            || die "Cloudflare tunnel 建置失敗"
        set_env CF_HOSTNAME "$OPT_CF_HOST"
        set_env CF_TUNNEL_NAME "$OPT_CF_TUNNEL"
        if [[ -n "$(get_env WELCOME_HOSTNAME)" ]]; then
            CF_API_TOKEN="$OPT_CF_TOKEN" python3 "$INSTALL_DIR/cf_tunnel.py" setup \
                --hostname "$(get_env WELCOME_HOSTNAME)" --tunnel-name "$OPT_CF_TUNNEL" \
                --service http://waf-welcome:8080 --write-env "$ENV_FILE" \
                || die "Cloudflare 歡迎頁 ingress 建置失敗"
        fi
    fi

    # 管理來源：既有 + 參數 + 平台主機 + SSH 來源
    local platform_ip; platform_ip="$(platform_ip_from_url "$(get_env BEAK_BASE_URL)")"
    local admin; admin="$(uniq_csv "$(get_env ADMIN_IPS)" "$OPT_ADMIN_IPS" "$platform_ip" "$(ssh_client_ip)")"
    if [[ -z "$admin" ]]; then
        if [[ $OPT_YES -eq 1 ]]; then die "ADMIN_IPS 為空，請用 --admin-ips 指定管理來源 IP"; fi
        read -rp "允許管理本機的來源 IP（逗號分隔，例 192.168.1.10）: " admin
        [[ -n "$admin" ]] || die "ADMIN_IPS 不可為空"
    fi
    set_env ADMIN_IPS "$admin"

    # 秘密與衍生值
    set_env_if_empty CLICKHOUSE_PASSWORD "$(gen_secret)"
    set_env_if_empty GRAFANA_ADMIN_PASSWORD "$(gen_secret)"
    set_env_if_empty BRIDGE_INGEST_TOKEN "$(gen_secret)"
    set_env_if_empty CLOUDFLARED_IP "172.18.0.250"
    set_env_if_empty DOCKER_SUBNET "172.18.0.0/16"
    set_env_if_empty DOCKER_GATEWAY "172.18.0.1"
    set_env TRUSTED_INGRESS_LIST "$(uniq_csv "$(get_env CLOUDFLARED_IP)" "$(get_env TRUSTED_INGRESS_EXTRA)")"
    set_env_if_empty APPLIED_BY "od-bridge@$(hostname -s)"

    local profiles="ui"
    [[ $OPT_NO_UI -eq 1 ]] && profiles=""
    if [[ $OPT_NO_UI -eq 0 && "$(get_env COMPOSE_PROFILES)" != *ui* && -n "$(get_env COMPOSE_PROFILES)" ]]; then profiles=""; fi
    [[ -n "$(get_env CLOUDFLARE_TUNNEL_TOKEN)" ]] && profiles="${profiles:+$profiles,}tunnel"
    [[ -n "$(get_env WELCOME_HOSTNAME)" ]] && profiles="${profiles:+$profiles,}welcome"
    set_env COMPOSE_PROFILES "$profiles"

    # 必填檢查
    local missing=()
    for k in BEAK_BASE_URL INTAKE_KEY_ID INTAKE_SECRET_B64 WAF_BACKEND_URL; do
        [[ -n "$(get_env "$k")" ]] || missing+=("$k")
    done
    if [[ ${#missing[@]} -gt 0 ]]; then
        log_error "以下必填設定為空：${missing[*]}"
        echo "  用 --pair '<開通字串>' 帶入平台端資訊、--backend 指定被保護網站，"
        echo "  或直接編輯 $ENV_FILE 後執行：sudo bash $INSTALL_DIR/install.sh --reconfigure"
        exit 1
    fi
    [[ -n "$(get_env SA_ID)" ]] || log_warn "SA_ID 為空：本節點只會送事件，不會執行平台的封鎖決策"
    [[ -n "$(get_env CLOUDFLARE_TUNNEL_TOKEN)" ]] || log_warn "CLOUDFLARE_TUNNEL_TOKEN 為空：不啟動 cloudflared，WAF 只能從內網 8080 打到"
}

# ----------------------------------------------------------------------------
# 4. 由樣板產生設定檔
# ----------------------------------------------------------------------------
render_templates() {
    log_step "4/8" "產生設定檔（generated/）"
    local g="$INSTALL_DIR/generated"; mkdir -p "$g"
    local home_net iface subnet admin platform_ip
    home_net="$(get_env HOME_NET)"; iface="$(get_env NODE_IFACE)"; subnet="$(get_env DOCKER_SUBNET)"
    admin="$(get_env ADMIN_IPS)"; platform_ip="$(platform_ip_from_url "$(get_env BEAK_BASE_URL)")"

    sed -e "s|@@HOME_NET@@|$home_net|" -e "s|@@NODE_IFACE@@|$iface|" \
        "$INSTALL_DIR/suricata/suricata.yaml.tmpl" > "$g/suricata.yaml"

    local ips_xml=""
    for ip in $(uniq_csv "$admin" "$platform_ip" | tr ',' ' '); do
        [[ "$ip" =~ ^[0-9.]+(/[0-9]+)?$ ]] || continue
        ips_xml+="        <ip>$ip</ip>\n"
    done
    python3 - "$INSTALL_DIR/clickhouse/users.d/zz-network-allowlist.xml.tmpl" "$g/clickhouse-network-allowlist.xml" "$subnet" "$ips_xml" <<'PY'
import sys
src, dst, subnet, ips = sys.argv[1:5]
t = open(src, encoding="utf-8").read()
t = t.replace("@@DOCKER_SUBNET@@", subnet).replace("@@ALLOWLIST_IPS@@", ips.replace("\\n", "\n").rstrip("\n"))
open(dst, "w", encoding="utf-8").write(t)
PY

    mkdir -p "$g/welcome"
    sed -e "s|@@WELCOME_HOSTNAME@@|$(get_env WELCOME_HOSTNAME)|g" \
        "$INSTALL_DIR/welcome/index.html.tmpl" > "$g/welcome/index.html"

    sed -e "s|@@INSTALL_DIR@@|$INSTALL_DIR|" \
        "$INSTALL_DIR/host-cron/secstack-rotate-logs.tmpl" > "$g/secstack-rotate-logs"
    install -m 755 "$g/secstack-rotate-logs" /etc/cron.hourly/secstack-rotate-logs
    log_info "suricata.yaml、ClickHouse 白名單、log 輪替排程已產生"
}

# ----------------------------------------------------------------------------
# 5. 主機防火牆
# ----------------------------------------------------------------------------
apply_firewall() {
    log_step "5/8" "套用主機防火牆（nftables）"
    bash "$INSTALL_DIR/nftables.sh" "$INSTALL_DIR"
    if command -v ufw >/dev/null && ufw status 2>/dev/null | grep -q "Status: active"; then
        log_warn "ufw 啟用中：補上 od-bridge 8500 與管理埠的放行規則"
        ufw allow from "$(get_env DOCKER_SUBNET)" to any port 8500 proto tcp >/dev/null || true
        for ip in $(get_env ADMIN_IPS | tr ',' ' '); do
            ufw allow from "$ip" to any port 8500,3000,5636,8686,9443,8080 proto tcp >/dev/null || true
        done
    fi
}

# ----------------------------------------------------------------------------
# 6. Suricata 規則
# ----------------------------------------------------------------------------
update_rules() {
    log_step "6/8" "Suricata 規則集（Emerging Threats Open）"
    if [[ -s "$INSTALL_DIR/suricata/rules/suricata.rules" && "${1:-}" != "force" ]]; then
        log_info "規則檔已存在，略過（要更新：sudo bash $INSTALL_DIR/install.sh --update-rules）"
        return 0
    fi
    log_info "下載規則集（約 40MB，視網路 1~3 分鐘）"
    if ! compose run --rm --no-deps suricata suricata-update --no-test \
            --disable-conf /etc/suricata-update/disable.conf 2>&1 | grep -E "Loaded|Writing|Disabled|ERROR|Error" | tail -5; then
        log_warn "規則下載失敗，Suricata 會以空規則啟動；稍後可重跑本步驟"
    fi
}

# ----------------------------------------------------------------------------
# 7. 啟動
# ----------------------------------------------------------------------------
bring_up() {
    log_step "7/8" "啟動服務（docker compose up -d --build）"
    compose config -q || die "docker-compose.yml 或 .env 有誤"
    compose up -d --build --remove-orphans

    log_info "等待 ClickHouse 就緒"
    local chpw; chpw="$(get_env CLICKHOUSE_PASSWORD)"
    for _ in $(seq 1 30); do
        curl -fs "http://127.0.0.1:8123/ping" >/dev/null 2>&1 && break
        sleep 2
    done
    compose cp clickhouse/init.sql clickhouse:/tmp/init.sql >/dev/null
    compose exec -T clickhouse clickhouse-client --user secstack --password "$chpw" \
        --multiquery --queries-file /tmp/init.sql 2>&1 | grep -v '^$' || true

    if [[ ! -s "$INSTALL_DIR/od-bridge/state/crowdsec_machine.json" ]]; then
        log_info "把 od-bridge 註冊成 CrowdSec machine"
        sleep 5
        local pw; pw="$(python3 -c 'import secrets; print(secrets.token_hex(24))')"
        if compose exec -T crowdsec cscli machines add od-bridge --password "$pw" --force >/dev/null 2>&1; then
            printf '{"machine_id": "od-bridge", "password": "%s"}\n' "$pw" > "$INSTALL_DIR/od-bridge/state/crowdsec_machine.json"
            chmod 600 "$INSTALL_DIR/od-bridge/state/crowdsec_machine.json"
            compose restart od-bridge >/dev/null
        else
            log_warn "CrowdSec machine 註冊失敗（稍後可重跑 --reconfigure）"
        fi
    fi
}

# ----------------------------------------------------------------------------
# 8. 驗證與摘要
# ----------------------------------------------------------------------------
http_code() { local c; c="$(curl -s -o /dev/null -m 8 -w '%{http_code}' "$@" 2>/dev/null)"; printf '%s' "${c:-000}"; }

do_verify() {
    local ok=1
    echo "== 容器 =="
    compose ps --format 'table {{.Service}}\t{{.Status}}'
    echo
    echo "== 本機健康 =="
    local c
    local nip; nip="$(get_env NODE_IP)"
    c="$(http_code "http://127.0.0.1:8123/ping")";      printf '  ClickHouse /ping        %s\n' "$c"; [[ "$c" == 200 ]] || ok=0
    c="$(http_code http://127.0.0.1:8500/health)"; printf '  od-bridge  /health      %s\n' "$c"; [[ "$c" == 200 ]] || ok=0
    c="$(http_code "http://$nip:8080/")";          printf '  WAF        /            %s（後端 %s；502＝WAF 活著但連不到後端，000＝後端對根路徑不回應，很多站台刻意如此）\n' "$c" "$(get_env WAF_BACKEND_URL)"
    c="$(http_code "http://$nip:8080/?id=1%27%20OR%201=1--")"; printf '  WAF        SQLi 探測     %s（403 代表 WAF 規則引擎有在擋）\n' "$c"; [[ "$c" == 403 ]] || ok=0
    if compose exec -T vector vector validate /etc/vector/vector.yaml >/dev/null 2>&1; then
        echo "  Vector     設定檔        OK"
    else
        echo "  Vector     設定檔        FAIL"; ok=0
    fi
    echo
    echo "== 平台連線 =="
    local base; base="$(get_env BEAK_BASE_URL)"
    c="$(http_code -X POST -H 'Content-Type: application/json' -d '{}' "$base/api/open_defense/sa/login")"
    printf '  %s  →  HTTP %s（400/401 代表連得到；000 代表連不到，請查平台主機防火牆是否放行本機）\n' "$base" "$c"
    [[ "$c" != "000" ]] || ok=0
    if [[ -n "$(get_env SA_ID)" ]]; then
        if compose logs --since 10m od-bridge 2>/dev/null | grep -q "SA login ok"; then
            echo "  執行帳號登入            OK（od-bridge 已取得決策輪詢 token）"
        else
            echo "  執行帳號登入            尚未看到成功記錄（剛啟動可等 30 秒再看：docker compose logs od-bridge）"
        fi
    fi
    echo
    echo "== 對外入口 =="
    if [[ -n "$(get_env CLOUDFLARE_TUNNEL_TOKEN)" ]]; then
        if compose logs cloudflared 2>/dev/null | grep -q "Registered tunnel connection"; then
            echo "  cloudflared             已連上 Cloudflare（Registered tunnel connection）"
            [[ -n "$(get_env CF_HOSTNAME)" ]] && printf '  對外網址                https://%s/\n' "$(get_env CF_HOSTNAME)"
            [[ -n "$(get_env WELCOME_HOSTNAME)" ]] && printf '  歡迎頁                  https://%s/\n' "$(get_env WELCOME_HOSTNAME)"
        else
            echo "  cloudflared             尚未註冊連線（docker compose logs cloudflared）"; ok=0
        fi
    else
        echo "  未設定 tunnel token，只能從內網打 http://$(get_env NODE_IP):8080"
    fi
    echo
    echo "== 主機防火牆 =="
    if nft list table inet secstack >/dev/null 2>&1; then
        printf '  inet secstack           OK，封鎖中 %s 筆\n' "$(nft -j list set inet secstack blocklist 2>/dev/null | python3 -c 'import json,sys; d=json.load(sys.stdin); print(sum(len(x["set"].get("elem",[])) for x in d["nftables"] if "set" in x))' 2>/dev/null || echo '?')"
    else
        echo "  inet secstack           缺少（重跑 --reconfigure）"; ok=0
    fi
    echo
    [[ $ok -eq 1 ]] && log_info "驗證通過" || log_warn "有項目未通過，見上方"
    return 0
}

do_test_event() {
    local rid="TEST-$(date +%s)"
    local body
    body="$(python3 -c "
import json, datetime
print(json.dumps({
  'correlation_id': '$(python3 -c 'import uuid; print(uuid.uuid4())')',
  'source_system': 'vector', 'event_class': 'web_activity',
  'occurred_at': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
  'severity_id': 3,
  'finding': {'title': '防禦節點安裝測試事件 $rid', 'rule_id': '$rid', 'rule_set': 'manual'},
  'actor': {'ip': '203.0.113.42'},
  'target': {'host': 'ithome2026-waf-test.example', 'url': '/install-test'}
}))")"
    log_info "送一筆測試事件進 Vector（來源 vector、規則 $rid、攻擊者 203.0.113.42）"
    curl -s -X POST -H 'Content-Type: application/json' --data "$body" http://127.0.0.1:8688/ >/dev/null \
        || die "Vector 注入口 127.0.0.1:8688 沒有回應"
    sleep 6
    echo "== od-bridge 轉送記錄（期望 status=200 或 201）=="
    compose logs --since 1m od-bridge 2>/dev/null | grep -E "forwarded|401|403|422|status=" | tail -5 || true
    echo
    echo "平台端：登入 BeakPlatform → 開放防禦 → 資安案件處置中心，應出現標題含「$rid」的案件。"
    echo "若看到 status=422 no_mapping，代表企業尚未設定事件路由（平台端請跑 provision_od_intake_for_org.py 或在「事件路由設定」建規則）。"
}

print_summary() {
    log_step "8/8" "完成"
    local ip; ip="$(get_env NODE_IP)"
    cat <<EOT

安裝目錄：$INSTALL_DIR（設定在 .env，改完跑 sudo bash $INSTALL_DIR/install.sh --reconfigure）

  對外入口   $( [[ -n "$(get_env CF_HOSTNAME)" ]] && echo "https://$(get_env CF_HOSTNAME)$(get_env WAF_BACKEND_PATH)/" || echo "（未設 tunnel）" )
  歡迎頁     $( [[ -n "$(get_env WELCOME_HOSTNAME)" ]] && echo "https://$(get_env WELCOME_HOSTNAME)/  （內網驗證 http://$ip:8082/）" || echo "（未啟用）" )
  被保護網站 $(get_env WAF_BACKEND_URL)
  平台       $(get_env BEAK_BASE_URL)
  管理來源   $(get_env ADMIN_IPS)

  WAF（內網驗證）  http://$ip:8080/
  Grafana          http://$ip:3000/      admin / $(get_env GRAFANA_ADMIN_PASSWORD)
  EveBox           http://$ip:5636/      （Suricata 告警，無密碼，來源受防火牆限制）
  Portainer        https://$ip:9443/     （首次開啟時設定管理員密碼）
  ClickHouse       http://$ip:8123/play  secstack / $(get_env CLICKHOUSE_PASSWORD)
  od-bridge        http://$ip:8500/stats  /forwards  /decisions  /edl
  Vector API       http://$ip:8686/

下一步：
  sudo bash $INSTALL_DIR/install.sh --verify        健康檢查
  sudo bash $INSTALL_DIR/install.sh --test-event    送一筆測試事件，到平台的資安案件處置中心確認有建案
  docker compose -f $INSTALL_DIR/docker-compose.yml logs -f od-bridge
EOT
}

do_status() {
    compose ps --format 'table {{.Service}}\t{{.Status}}\t{{.Ports}}'
    echo
    nft list set inet secstack blocklist 2>/dev/null || echo "（nft inet secstack 不存在）"
    if [[ -n "$(get_env CLOUDFLARE_TUNNEL_TOKEN)" ]]; then
        echo; compose logs --tail 3 cloudflared 2>/dev/null | tail -3
    fi
}

do_uninstall() {
    [[ -d "$INSTALL_DIR" ]] || die "$INSTALL_DIR 不存在"
    if [[ $OPT_YES -eq 0 ]]; then
        read -rp "確定移除防禦節點？服務會停止$( [[ $OPT_PURGE -eq 1 ]] && echo '，資料卷也會刪除' )。輸入 YES 繼續: " a
        [[ "$a" == "YES" ]] || exit 0
    fi
    if [[ $OPT_PURGE -eq 1 ]]; then compose down -v --remove-orphans || true; else compose down --remove-orphans || true; fi
    nft delete table inet secstack 2>/dev/null || true
    if [[ -f /etc/nftables.conf ]] && grep -q "ITHome2026-WAF/nftables.sh" /etc/nftables.conf; then
        printf '#!/usr/sbin/nft -f\n' > /etc/nftables.conf
    fi
    rm -f /etc/cron.hourly/secstack-rotate-logs
    log_info "已停止。$INSTALL_DIR 與 .env 保留；要徹底清除：rm -rf $INSTALL_DIR"
}

# ----------------------------------------------------------------------------
# 主流程
# ----------------------------------------------------------------------------
case "$MODE" in
    install)
        install_packages
        fetch_source
        build_env
        render_templates
        apply_firewall
        update_rules
        bring_up
        print_summary
        sleep 3
        do_verify
        ;;
    reconfigure)
        [[ -f "$ENV_FILE" ]] || die "找不到 $ENV_FILE，請先執行安裝"
        install_packages
        # 從另一份原始碼目錄執行時（例如 git checkout），順便把程式同步進安裝目錄
        if [[ -f "$HERE/docker-compose.yml" && "$(cd "$HERE" && pwd)" != "$(cd "$INSTALL_DIR" && pwd)" ]]; then
            fetch_source
        fi
        build_env
        render_templates
        apply_firewall
        update_rules
        bring_up
        print_summary
        ;;
    update)
        [[ -f "$ENV_FILE" ]] || die "找不到 $ENV_FILE，請先執行安裝"
        HERE="/nonexistent"     # 強制從 GitHub 重新取得
        install_packages
        fetch_source
        build_env
        render_templates
        apply_firewall
        update_rules
        bring_up
        print_summary
        ;;
    update-rules)
        [[ -f "$ENV_FILE" ]] || die "找不到 $ENV_FILE，請先執行安裝"
        update_rules force
        compose restart suricata >/dev/null && log_info "Suricata 已重啟"
        ;;
    status)     do_status ;;
    verify)     do_verify ;;
    test-event) do_test_event ;;
    uninstall)  do_uninstall ;;
esac
