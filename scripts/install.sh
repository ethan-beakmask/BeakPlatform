#!/bin/bash
# =============================================================================
# BeakPlatform 安裝與升級腳本
# 適用於 Ubuntu 22.04/24.04 LTS
# =============================================================================
# 用法:
#   sudo bash install.sh                         全新安裝 (互動式設定密碼)
#   sudo bash install.sh --demo                  全新環境先安裝平台；已安裝環境佈建示範企業與防禦節點開通字串
#   sudo bash install.sh --update                升級更新 (保留資料)
#   sudo bash install.sh --status                查看服務狀態
#   sudo bash install.sh --start                 啟動服務
#   sudo bash install.sh --stop                  停止服務
#   sudo bash install.sh --uninstall             移除安裝
#
# 環境變數 (可選):
#   INSTALL_DIR            安裝目錄 (預設: /opt/BeakPlatform)
#   DB_NAME                資料庫名稱 (預設: beakplatform)
#   DB_USER                資料庫使用者 (預設: beakplatform)
#   DB_PASS                資料庫密碼 (不設定則自動產生 24 碼英數隨機密碼，寫入 .env)
#   BEAK_PORT              BeakPlatform 存取 port (預設: 8000，被佔用時自動找空 port)
#   ADMIN_INITIAL_PASSWORD 管理員初始密碼 (不設定則互動式輸入)
#   INSTALL_DEMO           設為 1 時等同 --demo（適用 curl | sudo ... bash）
#   DEMO_ORG_CODE          示範企業 code (預設: DEMOSOC)
#   DEMO_ORG_DOMAIN        示範企業 domain (預設: demo-soc.example)
#   GITHUB_TOKEN           GitHub Personal Access Token (公開 repo 不需要；私有 fork 才設定)
#   SKIP_NODE_SHOWCASE     設為 1 時全新安裝不種入「node展覽館」範例資料包 (預設種入；--update 不受影響)
#   GITHUB_REPO            GitHub clone URL (預設: https://github.com/ethan-beakmask/BeakPlatform.git)
# =============================================================================
set -e

# === 設定 ===
INSTALL_DIR="${INSTALL_DIR:-/opt/BeakPlatform}"
DB_NAME="${DB_NAME:-beakplatform}"
DB_USER="${DB_USER:-beakplatform}"
# 未指定時自動產生 24 碼英數隨機密碼。只用英數字母：密碼會內嵌在 DATABASE_URL
# 與 psql 的 SQL 字串裡，:@/?#% 與引號等符號會破壞解析。
DB_PASS_GENERATED=0
if [ -z "${DB_PASS:-}" ]; then
    DB_PASS="$(tr -dc 'A-Za-z0-9' < /dev/urandom | head -c 24)"
    DB_PASS_GENERATED=1
fi
BEAK_PORT="${BEAK_PORT:-8000}"
GITHUB_REPO="${GITHUB_REPO:-https://github.com/ethan-beakmask/BeakPlatform.git}"
SERVICE_NAME="beakplatform"
SERVICE_USER="beakplatform"
HEALTH_TIMEOUT=60

# === 顏色 ===
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_step()  { echo -e "${BLUE}[$1]${NC} $2"; }

# === 共用函式 ===

check_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "此腳本需要 root 權限執行"
        echo "  用法: sudo bash $0 $*"
        exit 1
    fi
}

check_ubuntu() {
    if ! grep -q "Ubuntu" /etc/os-release 2>/dev/null; then
        log_warn "此腳本針對 Ubuntu 22.04/24.04 設計，其他系統可能需要調整"
    fi
}

# 檢查 port 是否被佔用（0=空閒, 1=佔用）
is_port_in_use() {
    ss -tlnH "sport = :$1" 2>/dev/null | grep -q . && return 0
    return 1
}

# 從指定 port 開始找一個空閒 port
find_free_port() {
    local port=$1
    local max_try=100
    local i=0
    while [ $i -lt $max_try ]; do
        if ! is_port_in_use "$port"; then
            echo "$port"
            return 0
        fi
        port=$((port + 1))
        i=$((i + 1))
    done
    return 1
}

# 解析 port：檢查用戶指定的 BEAK_PORT，佔用則自動找空 port
# 同時設定 NGINX_PORT（外部）和 APP_PORT（內部 Gunicorn）
resolve_ports() {
    NGINX_PORT="$BEAK_PORT"

    if is_port_in_use "$NGINX_PORT"; then
        local new_port
        new_port=$(find_free_port "$NGINX_PORT")
        if [ -z "$new_port" ]; then
            log_error "無法找到可用的 port（從 $NGINX_PORT 開始搜尋）"
            exit 1
        fi
        log_warn "Port $NGINX_PORT 已被佔用，自動改用 port $new_port"
        NGINX_PORT="$new_port"
    fi

    # Gunicorn 內部 port = NGINX_PORT + 1，綁 127.0.0.1
    APP_PORT=$((NGINX_PORT + 1))
    if is_port_in_use "$APP_PORT"; then
        APP_PORT=$(find_free_port "$((NGINX_PORT + 2))")
        if [ -z "$APP_PORT" ]; then
            log_error "無法找到 Gunicorn 內部可用 port"
            exit 1
        fi
    fi

    # APP_PREFIX 預設 /beakplatform（與 Python 端 __init__.py 一致）
    local health_prefix="${APP_PREFIX:-/beakplatform}"
    HEALTH_URL="http://localhost:${APP_PORT}${health_prefix}/health"
}

health_check() {
    log_info "健康檢查 (等待最多 ${HEALTH_TIMEOUT}s)..."
    local elapsed=0
    while [ $elapsed -lt $HEALTH_TIMEOUT ]; do
        if curl -sf "$HEALTH_URL" 2>/dev/null | grep -q '"healthy"'; then
            log_info "健康檢查通過"
            # 穩定性驗證：等 5 秒後確認服務仍在運行
            sleep 5
            if systemctl is-active --quiet "$SERVICE_NAME"; then
                log_info "服務穩定性驗證通過"
                return 0
            else
                log_error "服務在健康檢查後崩潰"
                log_warn "最近日誌:"
                journalctl -u "$SERVICE_NAME" -n 20 --no-pager 2>/dev/null || true
                return 1
            fi
        fi
        sleep 3
        elapsed=$((elapsed + 3))
        printf "."
    done
    echo ""
    log_error "健康檢查逾時 (${HEALTH_TIMEOUT}s)"
    log_warn "最近日誌:"
    journalctl -u "$SERVICE_NAME" -n 20 --no-pager 2>/dev/null || true
    return 1
}

load_env() {
    if [ -f "$INSTALL_DIR/.env" ]; then
        set -a
        source "$INSTALL_DIR/.env"
        set +a
    fi
}

activate_venv() {
    source "$INSTALL_DIR/venv/bin/activate"
}

ensure_service_user() {
    if ! id -u "$SERVICE_USER" >/dev/null 2>&1; then
        useradd --system --home-dir "$INSTALL_DIR" --no-create-home --shell /usr/sbin/nologin "$SERVICE_USER"
        log_info "系統帳號 $SERVICE_USER 已建立"
    fi
}

fix_ownership() {
    chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"
    # 確保 log 目錄可寫（1777 sticky bit，允許多帳號寫入但不能互刪）
    mkdir -p /opt/tmp
    chown "$SERVICE_USER:$SERVICE_USER" /opt/tmp
    chmod 1777 /opt/tmp
}

# 以應用帳號身分執行指令（載入 venv + .env）
run_as_app() {
    sudo -u "$SERVICE_USER" bash -c "
        set -a; source '$INSTALL_DIR/.env'; set +a
        export PATH='$INSTALL_DIR/venv/bin':\$PATH
        export HOME='$INSTALL_DIR'
        cd '$INSTALL_DIR'
        $1
    "
}

# 需要 postgres superuser 的 DB 物件（PF-211 分工線）：extension 與 fw_sp schema／
# 擁有權分離。其餘 seed 全部在 scripts/bootstrap_db.py（以應用帳號執行，不需 sudo）。
# 冪等，安裝與更新共用。
apply_superuser_db_objects() {
    sudo -u postgres psql -d "$DB_NAME" -c "CREATE EXTENSION IF NOT EXISTS pgcrypto;" 2>/dev/null || true
    sudo -u postgres psql -d "$DB_NAME" -v ON_ERROR_STOP=1 -v app_user="$DB_USER" \
        -q -f "$INSTALL_DIR/scripts/sql/fw_sp_setup.sql"
}

# 企業專屬資料庫佈建角色：只要 CREATEDB + CREATEROLE，刻意不給 superuser。
# superuser 可以 COPY ... TO PROGRAM（等同 OS 命令執行），不該放進交付給客戶的 .env。
ensure_provisioner_role() {
    PROV_USER="${DB_USER}_prov"
    PROV_PASS=$(python3 -c "import secrets,string;print(''.join(secrets.choice(string.ascii_letters+string.digits) for _ in range(28)))")
    sudo -u postgres psql -c "CREATE ROLE \"$PROV_USER\" WITH LOGIN PASSWORD '$PROV_PASS' CREATEDB CREATEROLE;" >/dev/null 2>&1 || true
    # ALTER 是唯一權威（角色已存在時要確保密碼與屬性正確）。失敗就是真的壞了，
    # 不能靜默略過——沒有這個角色，新建企業一律沒有專屬資料庫。
    if ! prov_err=$(sudo -u postgres psql -v ON_ERROR_STOP=1 \
            -c "ALTER ROLE \"$PROV_USER\" WITH LOGIN PASSWORD '$PROV_PASS' CREATEDB CREATEROLE;" 2>&1 >/dev/null); then
        log_error "無法建立企業資料庫佈建角色 $PROV_USER：$prov_err"
        exit 1
    fi
}

# PG15 以下的 CREATEROLE 可以奪取任何非 superuser 角色，
# 「非 superuser 的佈建角色」這個隔離假設在那些版本不成立。
check_pg_version() {
    local pg_ver
    pg_ver=$(sudo -u postgres psql -tAc "SHOW server_version_num" 2>/dev/null || echo 0)
    if [ "${pg_ver:-0}" -lt 160000 ]; then
        log_warn "PostgreSQL 版本低於 16，CREATEROLE 角色可奪取任何非 superuser 角色，企業資料庫佈建帳號的權限隔離在此版本不成立"
    fi
}

# 單一 DB bootstrap 入口（PF-211）。$1 為 --fresh 或 --update。
# 管理員密碼只經環境變數傳遞，不進命令列字串（避免引號問題與 ps 洩漏）。
run_bootstrap() {
    sudo -u "$SERVICE_USER" env \
        ADMIN_INITIAL_PASSWORD="${ADMIN_PASS:-}" \
        SKIP_NODE_SHOWCASE="${SKIP_NODE_SHOWCASE:-}" \
        HOME="$INSTALL_DIR" \
        bash -c "
            set -a; source '$INSTALL_DIR/.env'; set +a
            export PATH='$INSTALL_DIR/venv/bin':\$PATH
            cd '$INSTALL_DIR/backend'
            python3 ../scripts/bootstrap_db.py $1
        "
}

password_meets_demo_policy() {
    local pw="${1:-}"
    [[ ${#pw} -ge 12 ]] || return 1
    [[ "$pw" =~ [A-Z] ]] || return 1
    [[ "$pw" =~ [a-z] ]] || return 1
    [[ "$pw" =~ [0-9] ]] || return 1
    [[ "$pw" =~ [^A-Za-z0-9] ]] || return 1
    return 0
}

detect_server_ip() {
    local detected
    detected=$(ip -4 route get 8.8.8.8 2>/dev/null | awk '/src/ {print $7; exit}')
    detected="${detected:-$(hostname -I 2>/dev/null | awk '{print $1}')}"
    detected="${detected:-$(hostname -f 2>/dev/null)}"
    echo "$detected"
}

# 操作者工作機的 IP：給主機 B 的 --admin-ips 用（允許從哪裡開 Grafana 等管理介面）。
# 可用環境變數 WORKSTATION_IP 指定；否則取目前 SSH 連進本機的來源。
# sudo 會清掉 SSH_CONNECTION，所以另外看 who 與 sshd 已建立連線的對端位址。
detect_workstation_ips() {
    local ips="${WORKSTATION_IP:-}"
    if [ -z "$ips" ]; then
        [ -n "${SSH_CONNECTION:-}" ] && ips="${SSH_CONNECTION%% *}"
        ips="$ips,$(who 2>/dev/null | awk '$NF ~ /^\(/ {gsub(/[()]/,"",$NF); print $NF}' | paste -sd, -)"
        ips="$ips,$(ss -Htn state established '( sport = :22 )' 2>/dev/null | awk '{print $NF}' | sed -E 's/:[0-9]+$//; s/^\[::ffff:([0-9.]+)\]$/\1/' | paste -sd, -)"
    fi
    printf '%s\n' "$ips" | tr ',' '\n' | grep -E '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$' | awk '!seen[$0]++' | paste -sd, - || true
}

resolve_display_url_from_install() {
    local server_ip listen_port
    server_ip=$(detect_server_ip)
    listen_port=$(sed -n 's/^[[:space:]]*listen[[:space:]]\+\([0-9]\+\).*/\1/p' \
        "/etc/nginx/sites-available/$SERVICE_NAME" 2>/dev/null | head -1)
    if [ -z "$listen_port" ]; then
        listen_port="${BEAK_PORT:-8000}"
    fi
    if [ "$listen_port" = "80" ]; then
        DISPLAY_URL="http://$server_ip"
    else
        DISPLAY_URL="http://$server_ip:$listen_port"
    fi
}

print_last_lines() {
    local file="$1"
    if [ -f "$file" ]; then
        tail -30 "$file" || true
    fi
}

run_demo_provision() {
    local fatal="${1:-0}"
    local demo_code="${DEMO_ORG_CODE:-DEMOSOC}"
    local demo_domain="${DEMO_ORG_DOMAIN:-demo-soc.example}"
    local seed_log pair_log seed_rc pair_rc demo_password demo_admin pair_string waf_command waf_download workstation_ips cred_file old_umask

    echo ""
    log_step "demo" "佈建示範企業與防禦節點開通字串..."

    if [ ! -f "$INSTALL_DIR/.env" ]; then
        log_warn "找不到 $INSTALL_DIR/.env，無法佈建示範企業"
        [ "$fatal" = "1" ] && return 1
        return 0
    fi
    if [ ! -x "$INSTALL_DIR/venv/bin/python" ]; then
        log_warn "找不到 $INSTALL_DIR/venv/bin/python，無法佈建示範企業"
        [ "$fatal" = "1" ] && return 1
        return 0
    fi

    if [ -z "${DISPLAY_URL:-}" ]; then
        resolve_display_url_from_install
    fi

    seed_log=$(mktemp)
    pair_log=$(mktemp)

    if password_meets_demo_policy "${ADMIN_PASS:-}"; then
        if sudo -u "$SERVICE_USER" env \
            DEMO_ORG_PASSWORD="$ADMIN_PASS" \
            DEMO_ORG_CODE="$demo_code" \
            DEMO_ORG_DOMAIN="$demo_domain" \
            HOME="$INSTALL_DIR" \
            bash -c "
                set -a; source '$INSTALL_DIR/.env'; set +a
                export PATH='$INSTALL_DIR/venv/bin':\$PATH
                cd '$INSTALL_DIR'
                python3 scripts/seed_demo_org.py --apply --code \"\$DEMO_ORG_CODE\" --domain \"\$DEMO_ORG_DOMAIN\"
            " >"$seed_log" 2>&1; then
            seed_rc=0
        else
            seed_rc=$?
        fi
    else
        if sudo -u "$SERVICE_USER" env \
            DEMO_ORG_CODE="$demo_code" \
            DEMO_ORG_DOMAIN="$demo_domain" \
            HOME="$INSTALL_DIR" \
            bash -c "
                set -a; source '$INSTALL_DIR/.env'; set +a
                export PATH='$INSTALL_DIR/venv/bin':\$PATH
                cd '$INSTALL_DIR'
                python3 scripts/seed_demo_org.py --apply --code \"\$DEMO_ORG_CODE\" --domain \"\$DEMO_ORG_DOMAIN\"
            " >"$seed_log" 2>&1; then
            seed_rc=0
        else
            seed_rc=$?
        fi
    fi

    if [ "$seed_rc" -eq 2 ]; then
        log_info "示範企業 $demo_domain 已存在，略過建立"
    elif [ "$seed_rc" -ne 0 ]; then
        log_warn "示範企業佈建失敗（exit $seed_rc），最後 30 行輸出如下："
        print_last_lines "$seed_log"
        log_warn "可事後手動重跑：cd $INSTALL_DIR && set -a && source .env && set +a && venv/bin/python scripts/seed_demo_org.py --apply --code $demo_code --domain $demo_domain"
        rm -f "$seed_log" "$pair_log"
        [ "$fatal" = "1" ] && return 1
        return 0
    fi

    demo_password=$(sed -n 's/^示範帳號共用密碼 .*: //p' "$seed_log" | tail -1)
    demo_admin=$(sed -n 's/^管理員帳號: //p' "$seed_log" | tail -1)
    if [ -z "$demo_password" ] && [ -f "$INSTALL_DIR/demo-credentials.txt" ]; then
        demo_password=$(sed -n 's/^示範帳號共用密碼: //p' "$INSTALL_DIR/demo-credentials.txt" | tail -1)
    fi
    if [ -z "$demo_password" ]; then
        demo_password="（示範企業已存在；請使用先前佈建時保存的密碼）"
    fi
    if [ -z "$demo_admin" ]; then
        demo_admin="admin-<username>@$demo_domain"
    fi

    if sudo -u "$SERVICE_USER" env \
        HOME="$INSTALL_DIR" \
        DEMO_ORG_DOMAIN="$demo_domain" \
        DEMO_BASE_URL="${DISPLAY_URL%/}/beakplatform" \
        bash -c "
            set -a; source '$INSTALL_DIR/.env'; set +a
            export PATH='$INSTALL_DIR/venv/bin':\$PATH
            cd '$INSTALL_DIR'
            python3 scripts/od_node_pairing.py --org \"\$DEMO_ORG_DOMAIN\" --base-url \"\$DEMO_BASE_URL\" --provision --apply
        " >"$pair_log" 2>&1; then
        pair_rc=0
    else
        pair_rc=$?
    fi

    if [ "$pair_rc" -ne 0 ]; then
        log_warn "防禦節點配對字串產生失敗（exit $pair_rc），最後 30 行輸出如下："
        print_last_lines "$pair_log"
        log_warn "可事後手動重跑：cd $INSTALL_DIR && set -a && source .env && set +a && venv/bin/python scripts/od_node_pairing.py --org $demo_domain --base-url ${DISPLAY_URL%/}/beakplatform --provision --apply"
        rm -f "$seed_log" "$pair_log"
        [ "$fatal" = "1" ] && return 1
        return 0
    fi

    pair_string=$(grep '^ODN1\.' "$pair_log" | tail -1 || true)
    if [ -z "$pair_string" ]; then
        log_warn "示範佈建輸出解析失敗，最後 30 行輸出如下："
        print_last_lines "$seed_log"
        print_last_lines "$pair_log"
        log_warn "可事後手動重跑 seed_demo_org.py 與 od_node_pairing.py 取得憑證"
        rm -f "$seed_log" "$pair_log"
        [ "$fatal" = "1" ] && return 1
        return 0
    fi

    # 整段可直接貼到主機 B：--backend 預設保護平台本身；管理來源 IP 由 WAF 安裝腳本
    # 自動納入平台主機與 SSH 來源，練習環境不必另外給 --admin-ips
    waf_download="curl -fsSL ${GITHUB_REPO%.git}/raw/main/Integrated-WAF/install.sh -o /tmp/install.sh"
    workstation_ips="$(detect_workstation_ips)"
    waf_command="sudo bash /tmp/install.sh --pair '$pair_string' --backend ${DISPLAY_URL%/}${workstation_ips:+ --admin-ips $workstation_ips} --yes"
    cred_file="$INSTALL_DIR/demo-credentials.txt"
    old_umask=$(umask)
    umask 077
    {
        echo "BeakPlatform 示範企業與防禦節點開通資訊"
        echo "產生時間: $(date '+%Y-%m-%d %H:%M:%S %z')"
        echo ""
        echo "示範企業: $demo_code / $demo_domain"
        echo "登入網址: ${DISPLAY_URL%/}/beakplatform/auth/org/$demo_domain/login"
        echo "示範企業管理員: $demo_admin"
        echo "示範帳號共用密碼: $demo_password"
        echo ""
        echo "防禦節點開通字串:"
        echo "$pair_string"
        echo ""
        echo "主機 B（防禦節點）安裝指令，共兩道（中間空一列隔開），整段複製貼上即可，不需修改:"
        echo "$waf_download"
        echo ""
        echo "$waf_command"
    } > "$cred_file"
    umask "$old_umask"
    chown root:root "$cred_file"
    chmod 600 "$cred_file"
    rm -f "$seed_log" "$pair_log"

    echo ""
    log_info "示範企業與防禦節點開通資訊"
    echo "  示範企業: $demo_code / $demo_domain"
    echo "  登入網址: ${DISPLAY_URL%/}/beakplatform/auth/org/$demo_domain/login"
    echo "  示範企業管理員: $demo_admin"
    echo "  示範帳號共用密碼: $demo_password"
    echo "  已存到 $cred_file（只有 root 可讀，之後可用 sudo cat 再看一次）"
    echo ""
    echo "  ---- 下一步：到主機 B（防禦節點）執行下面兩道指令（中間空一列隔開），整段複製貼上即可，不需修改 ----"
    echo ""
    echo "$waf_download"
    echo ""
    echo "$waf_command"
    echo ""
    echo "  （--backend 是要被 WAF 保護的網站，這裡預設填本平台；要保護別的網站才需要改）"
    if [ -n "$workstation_ips" ]; then
        echo "  （--admin-ips 是允許開啟主機 B 管理介面 Grafana／EveBox／Portainer 的來源，已自動填入你現在連線進來的工作機 $workstation_ips）"
    else
        log_warn "偵測不到你的工作機 IP（不是用 SSH 連進來的？）。請在第二道指令的 --yes 前面自行加上 --admin-ips <你的工作機IP>，否則從工作機打不開主機 B 的管理介面"
    fi
    return 0
}

# === 參數處理 ===
ACTION="fresh"
WITH_DEMO="${INSTALL_DEMO:-0}"
ACTION_SET=0

usage() {
    echo "BeakPlatform 安裝與升級腳本"
    echo ""
    echo "用法:"
    echo "  sudo bash install.sh                  全新安裝"
    echo "  sudo bash install.sh --demo           佈建示範企業與防禦節點開通字串；全新環境會先安裝平台"
    echo "  sudo bash install.sh --update         升級更新 (保留資料)"
    echo "  sudo bash install.sh --status         查看服務狀態"
    echo "  sudo bash install.sh --start          啟動服務"
    echo "  sudo bash install.sh --stop           停止服務"
    echo "  sudo bash install.sh --uninstall      移除安裝"
    echo ""
    echo "環境變數:"
    echo "  INSTALL_DIR=$INSTALL_DIR"
    echo "  DB_NAME=$DB_NAME"
    echo "  BEAK_PORT=$BEAK_PORT (存取 port，預設 8000，被佔用時自動找空 port)"
    echo "  INSTALL_DEMO=1 (等同 --demo)"
    echo "  DEMO_ORG_CODE=DEMOSOC"
    echo "  DEMO_ORG_DOMAIN=demo-soc.example"
    echo "  GITHUB_TOKEN=<GitHub PAT> (公開 repo 不需要；私有 fork 才設定)"
}

for arg in "$@"; do
    case "$arg" in
        --help|-h)
            usage
            exit 0
            ;;
        --demo)
            WITH_DEMO=1
            ;;
        --update|--status|--start|--stop|--uninstall)
            if [ "$ACTION_SET" -eq 1 ]; then
                usage
                exit 1
            fi
            ACTION="${arg#--}"
            ACTION_SET=1
            ;;
        *)
            usage
            exit 1
            ;;
    esac
done

if [ "$WITH_DEMO" = "1" ] && [ "$ACTION_SET" -eq 0 ] && [ -f "$INSTALL_DIR/.env" ]; then
    ACTION="demo"
fi

if [ "$ACTION" = "fresh" ] && [ "$WITH_DEMO" = "1" ]; then
    :
elif [ "$WITH_DEMO" = "1" ] && [ "$ACTION" != "demo" ]; then
    log_warn "--demo 只會搭配全新安裝或單獨 demo 入口；目前動作 $ACTION 會忽略 demo 佈建"
fi

case "$ACTION" in
    fresh|demo|update|status|start|stop|uninstall) ;;
    *)
        usage
        exit 1
        ;;
esac


# =========================================================================
#  --status
# =========================================================================
if [ "$ACTION" = "status" ]; then
    echo "=== BeakPlatform 服務狀態 ==="
    echo ""

    # systemd service
    if systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
        log_info "服務狀態: 運行中"
        systemctl status "$SERVICE_NAME" --no-pager -l 2>/dev/null | head -15
    else
        log_warn "服務狀態: 未運行"
    fi

    echo ""

    # 健康檢查
    if curl -sf "$HEALTH_URL" 2>/dev/null | grep -q '"healthy"'; then
        log_info "健康檢查: 正常"
    else
        log_warn "健康檢查: 無回應"
    fi

    # Nginx
    echo ""
    if systemctl is-active --quiet nginx 2>/dev/null; then
        log_info "Nginx: 運行中"
    else
        log_warn "Nginx: 未運行"
    fi

    # Redis
    if systemctl is-active --quiet redis-server 2>/dev/null; then
        log_info "Redis: 運行中"
    else
        log_warn "Redis: 未運行"
    fi

    # PostgreSQL
    if systemctl is-active --quiet postgresql 2>/dev/null; then
        log_info "PostgreSQL: 運行中"
    else
        log_warn "PostgreSQL: 未運行"
    fi

    exit 0
fi


# =========================================================================
#  --start
# =========================================================================
if [ "$ACTION" = "start" ]; then
    check_root
    # 從已安裝的 .env 讀取 Gunicorn port 與 APP_PREFIX，設定 health check URL
    local_app_port=$(grep '^GUNICORN_BIND=' "$INSTALL_DIR/.env" 2>/dev/null | sed 's/.*://' || echo "")
    local_app_prefix=$(grep '^APP_PREFIX=' "$INSTALL_DIR/.env" 2>/dev/null | cut -d'=' -f2- || echo "")
    HEALTH_URL="http://localhost:${local_app_port:-8001}${local_app_prefix:-/beakplatform}/health"
    log_info "啟動 BeakPlatform..."
    systemctl start "$SERVICE_NAME"
    health_check
    exit 0
fi


# =========================================================================
#  --stop
# =========================================================================
if [ "$ACTION" = "stop" ]; then
    check_root
    log_info "停止 BeakPlatform..."
    systemctl stop "$SERVICE_NAME"
    log_info "服務已停止"
    exit 0
fi


# =========================================================================
#  --uninstall
# =========================================================================
if [ "$ACTION" = "uninstall" ]; then
    check_root
    echo "=== BeakPlatform 移除 ==="
    echo ""
    log_warn "此操作將移除:"
    echo "  - systemd 服務 ($SERVICE_NAME)"
    echo "  - Nginx 設定"
    echo "  - 安裝目錄 ($INSTALL_DIR)"
    echo "  - 示範憑證檔 ($INSTALL_DIR/demo-credentials.txt)"
    echo "  - 資料庫 ($DB_NAME)"
    echo "  - 企業專屬資料庫 (org_*) 與集團資料庫 (cg_*)"
    echo ""
    read -p "確定要移除嗎？(輸入 YES 確認): " CONFIRM
    if [ "$CONFIRM" != "YES" ]; then
        echo "取消移除"
        exit 0
    fi

    # 停止服務
    systemctl stop "$SERVICE_NAME" 2>/dev/null || true
    systemctl disable "$SERVICE_NAME" 2>/dev/null || true
    rm -f "/etc/systemd/system/${SERVICE_NAME}.service"
    systemctl daemon-reload

    # 移除 Nginx 設定
    rm -f "/etc/nginx/sites-enabled/$SERVICE_NAME"
    rm -f "/etc/nginx/sites-available/$SERVICE_NAME"
    systemctl reload nginx 2>/dev/null || true

    # 移除資料庫
    # 企業／集團專屬資料庫與其專用角色
    for dbn in $(sudo -u postgres psql -tAc "SELECT datname FROM pg_database WHERE datname ~ '^(org|cg)_[0-9]+$'" 2>/dev/null || true); do
        sudo -u postgres psql -c "DROP DATABASE IF EXISTS \"$dbn\" WITH (FORCE);" >/dev/null 2>&1 || true
    done
    for rol in $(sudo -u postgres psql -tAc "SELECT rolname FROM pg_roles WHERE rolname ~ '^(bfadmin|bfsync|cgadmin|cgmember)_[0-9]+$'" 2>/dev/null || true); do
        sudo -u postgres psql -c "DROP ROLE IF EXISTS \"$rol\";" >/dev/null 2>&1 || true
    done
    sudo -u postgres psql -c "DROP ROLE IF EXISTS \"${DB_USER}_prov\";" >/dev/null 2>&1 || true
    sudo -u postgres psql -c "DROP DATABASE IF EXISTS \"$DB_NAME\";" 2>/dev/null || true

    # 移除安裝目錄
    rm -rf "$INSTALL_DIR"

    # 移除系統帳號
    if id -u "$SERVICE_USER" >/dev/null 2>&1; then
        userdel "$SERVICE_USER" 2>/dev/null || true
        log_info "系統帳號 $SERVICE_USER 已移除"
    fi

    log_info "移除完成"
    exit 0
fi


# =========================================================================
#  --demo 示範企業與防禦節點開通字串
# =========================================================================
if [ "$ACTION" = "demo" ]; then
    check_root
    ADMIN_PASS="${ADMIN_PASS:-${ADMIN_INITIAL_PASSWORD:-}}"
    resolve_display_url_from_install
    if run_demo_provision 1; then
        exit 0
    fi
    exit 1
fi


# =========================================================================
#  --update 升級更新
# =========================================================================
if [ "$ACTION" = "update" ]; then
    check_root

    echo "============================================"
    echo "  BeakPlatform 升級更新"
    echo "============================================"

    if [ ! -d "$INSTALL_DIR/.git" ]; then
        log_error "安裝目錄不存在或不是 git repo: $INSTALL_DIR"
        log_error "請先執行全新安裝: sudo bash install.sh"
        exit 1
    fi

    cd "$INSTALL_DIR"

    # [1] 拉取最新程式碼
    log_step "1/4" "拉取最新程式碼..."

    # 允許 root 操作非 root 擁有的 repo
    git config --global --add safe.directory "$INSTALL_DIR" 2>/dev/null || true

    # 公開 repo 直接用 GITHUB_REPO；只有設定 GITHUB_TOKEN（私有 fork）時才帶 token。
    # token 必須用 https://x-access-token:<PAT>@github.com/... 格式：token 只放 username
    # 位置時 git 會轉去問 credential helper，無 tty 環境（cron、腳本）必定失敗。
    if [ -n "${GITHUB_TOKEN:-}" ]; then
        git remote set-url origin "https://x-access-token:${GITHUB_TOKEN}@${GITHUB_REPO#https://}"
    else
        git remote set-url origin "$GITHUB_REPO"
    fi

    git fetch origin main
    local_hash=$(git rev-parse HEAD)
    remote_hash=$(git rev-parse origin/main)

    if [ "$local_hash" = "$remote_hash" ]; then
        log_info "程式碼已是最新版本 ($(git log --oneline -1))"
        log_info "仍會執行 schema 同步與出廠資料補種（冪等），修復上次可能中斷的更新"
    else
        git reset --hard origin/main
        log_info "更新至: $(git log --oneline -1)"
    fi

    # 確保服務帳號存在 + 修正檔案所有權
    ensure_service_user
    fix_ownership

    # [2] 更新 Python 依賴（以應用帳號執行）
    log_step "2/4" "更新 Python 依賴與 .env..."
    sudo -u "$SERVICE_USER" "$INSTALL_DIR/venv/bin/pip" install --upgrade pip -q
    sudo -u "$SERVICE_USER" "$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/backend/requirements.txt" -q

    # [2.5] 補齊舊版 .env 缺少的檔案加密設定（冪等）
    if ! grep -q '^ENCRYPTION_MASTER_KEY=' "$INSTALL_DIR/.env" 2>/dev/null; then
        log_warn ".env 缺少 ENCRYPTION_MASTER_KEY，自動產生..."
        NEW_EMK=$(python3 -c "import os, base64; print(base64.urlsafe_b64encode(os.urandom(32)).decode())")
        {
            echo ""
            echo "# 檔案加密 (FILE-01) - AES-256-GCM Master Key，遺失將無法解密既有加密附件"
            echo "ENCRYPTION_MASTER_KEY=$NEW_EMK"
        } >> "$INSTALL_DIR/.env"
    fi
    if ! grep -q '^ENCRYPTED_STORAGE_DIR=' "$INSTALL_DIR/.env" 2>/dev/null; then
        echo "ENCRYPTED_STORAGE_DIR=$INSTALL_DIR/backend/encrypted_storage" >> "$INSTALL_DIR/.env"
    fi
    if ! grep -q '^SYNC_PG_ADMIN_URL=' "$INSTALL_DIR/.env" 2>/dev/null; then
        log_warn ".env 缺少 SYNC_PG_ADMIN_URL（企業專屬資料庫佈建），自動建立佈建角色..."
        check_pg_version
        ensure_provisioner_role
        {
            echo ""
            echo "# 企業專屬資料庫佈建（非 superuser：LOGIN + CREATEDB + CREATEROLE）"
            echo "SYNC_PG_ADMIN_URL=postgresql://$PROV_USER:$PROV_PASS@localhost/postgres"
        } >> "$INSTALL_DIR/.env"
    fi
    if ! grep -q '^SYNC_CREDENTIAL_KEY=' "$INSTALL_DIR/.env" 2>/dev/null; then
        log_warn ".env 缺少 SYNC_CREDENTIAL_KEY，自動產生..."
        log_warn "若此環境先前已有企業專屬資料庫，舊的加密帳密將無法解密，"
        log_warn "請到「企業獨立資料庫管理」頁對顯示異常的企業按【補建】重新產生帳密"
        NEW_SYNC_CRED_KEY=$(python3 -c "import os, base64; print(base64.urlsafe_b64encode(os.urandom(32)).decode())")
        {
            echo ""
            echo "# 企業專屬資料庫憑證加密金鑰 (Fernet)，遺失將無法解密既有企業庫帳密"
            echo "SYNC_CREDENTIAL_KEY=$NEW_SYNC_CRED_KEY"
        } >> "$INSTALL_DIR/.env"
    fi
    if ! grep -q '^OD_SA_JWT_SECRET=' "$INSTALL_DIR/.env" 2>/dev/null; then
        log_warn ".env 缺少 OD_SA_JWT_SECRET（防禦節點執行帳號 JWT），自動產生..."
        NEW_OD_SA_JWT=$(python3 -c "import os, base64; print(base64.urlsafe_b64encode(os.urandom(32)).decode())")
        {
            echo ""
            echo "# Open Defense 防禦節點執行帳號的 JWT 簽章金鑰 (HS256, base64url 32 bytes)"
            echo "# 缺少時 /api/open_defense/sa/login 一律 500，防禦節點永遠拉不到封鎖決策"
            echo "OD_SA_JWT_SECRET=$NEW_OD_SA_JWT"
        } >> "$INSTALL_DIR/.env"
    fi
    if ! grep -q '^NOCODE_BUILDER_MENU=' "$INSTALL_DIR/.env" 2>/dev/null; then
        {
            echo ""
            echo "# 子系統開發模組選單；off 時不註冊選單"
            echo "NOCODE_BUILDER_MENU=on"
        } >> "$INSTALL_DIR/.env"
    fi
    chmod 600 "$INSTALL_DIR/.env"
    mkdir -p "$INSTALL_DIR/backend/encrypted_storage"
    chown "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR/backend/encrypted_storage"
    chmod 700 "$INSTALL_DIR/backend/encrypted_storage"

    # [3] 同步資料庫 schema 與出廠資料
    #     model 即權威：create_all 只補「新表」，不改既有表的欄位。
    #     欄位級的升級機制目前刻意不存在（尚無任何已公開的既有環境需要升級），
    #     公開後首次需要時另行設計，不要回頭復活 run_migrations。
    log_step "3/4" "DB bootstrap（schema、SQL extras、選單、權限、模組同步）..."
    apply_superuser_db_objects
    run_bootstrap --update

    # [4] 重啟服務
    log_step "4/4" "重啟服務..."
    # 從已安裝的 .env 讀取 Gunicorn port 與 APP_PREFIX，設定 health check URL
    local_app_port=$(grep '^GUNICORN_BIND=' "$INSTALL_DIR/.env" 2>/dev/null | sed 's/.*://' || echo "")
    local_app_prefix=$(grep '^APP_PREFIX=' "$INSTALL_DIR/.env" 2>/dev/null | cut -d'=' -f2- || echo "")
    HEALTH_URL="http://localhost:${local_app_port:-8001}${local_app_prefix:-/beakplatform}/health"
    systemctl restart "$SERVICE_NAME"

    health_check

    echo ""
    echo "============================================"
    log_info "升級更新完成"
    echo "  版本: $(cd "$INSTALL_DIR" && git log --oneline -1)"
    echo "============================================"
    exit 0
fi


# =========================================================================
#  全新安裝
# =========================================================================
check_root
check_ubuntu

echo "============================================"
echo "  BeakPlatform 全新安裝"
echo "============================================"
echo ""

# 解析 port（檢查佔用，自動分配）
resolve_ports

echo "  安裝目錄: $INSTALL_DIR"
echo "  資料庫:   $DB_NAME"
echo "  Port:     $NGINX_PORT (Nginx) / $APP_PORT (Gunicorn internal)"
echo "  來源:     $GITHUB_REPO"
echo ""

# 如果目錄已存在且有 .env，警告
if [ -f "$INSTALL_DIR/.env" ]; then
    log_warn "偵測到既有安裝: $INSTALL_DIR"
    read -p "要覆蓋安裝嗎？既有資料將被清除 (y/N): " OVERWRITE
    if [[ ! "$OVERWRITE" =~ ^[yY]$ ]]; then
        echo "取消安裝。如需升級請用: sudo bash install.sh --update"
        exit 0
    fi
    # 停掉舊服務
    systemctl stop "$SERVICE_NAME" 2>/dev/null || true
    # 備份舊 .env（含手動調整的設定）
    cp "$INSTALL_DIR/.env" "$INSTALL_DIR/.env.bak.$(date +%s)"
    log_info "已備份舊 .env"
fi


# === [1/9] 系統依賴 ===
log_step "1/9" "檢查系統依賴..."

REQUIRED_PKGS=(python3 python3-venv python3-pip postgresql postgresql-contrib redis-server nginx git curl sudo)
MISSING_PKGS=()

for pkg in "${REQUIRED_PKGS[@]}"; do
    if dpkg -l "$pkg" 2>/dev/null | grep -q "^ii"; then
        printf "  %-25s %s\n" "$pkg" "OK"
    else
        printf "  %-25s %s\n" "$pkg" "缺少"
        MISSING_PKGS+=("$pkg")
    fi
done

if [ ${#MISSING_PKGS[@]} -eq 0 ]; then
    log_info "所有系統依賴已安裝，跳過"
else
    log_info "需要安裝: ${MISSING_PKGS[*]}"
    # apt-get update 加 120 秒 timeout，避免在封閉網路無限等待
    timeout 120 apt-get update -q || log_warn "apt update 逾時或失敗，嘗試直接安裝..."
    apt-get install -y -q "${MISSING_PKGS[@]}"
fi

# 確保服務啟動
systemctl enable --now postgresql 2>/dev/null || true
systemctl enable --now redis-server 2>/dev/null || true
systemctl enable --now nginx 2>/dev/null || true

log_info "系統依賴安裝完成"

# 建立應用服務帳號
ensure_service_user


# === [2/9] PostgreSQL ===
log_step "2/9" "設定 PostgreSQL..."

sudo -u postgres psql -c "CREATE USER $DB_USER WITH PASSWORD '$DB_PASS';" 2>/dev/null || true
sudo -u postgres psql -c "ALTER USER $DB_USER WITH PASSWORD '$DB_PASS';" 2>/dev/null || true

# 全新安裝：先清除舊 DB 再建立（避免殘留資料衝突）
# 斷開所有連線後再 DROP，並驗證結果
sudo -u postgres psql -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='$DB_NAME' AND pid <> pg_backend_pid();" > /dev/null 2>&1 || true
sleep 1
if ! sudo -u postgres psql -c "DROP DATABASE IF EXISTS $DB_NAME;" 2>/dev/null; then
    log_error "無法刪除資料庫 $DB_NAME（可能有程式佔用連線）"
    log_error "請先停止所有連線此資料庫的程式，再重新執行安裝"
    exit 1
fi
sudo -u postgres psql -c "CREATE DATABASE $DB_NAME OWNER $DB_USER;" 2>/dev/null
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;" 2>/dev/null

# 全新安裝一併清掉前一次安裝留下的企業／集團專屬資料庫與其專用角色。
# 不清的話，新環境的 org_1 會直接沿用舊環境的 org_1（provision 看到庫已存在就不重建），
# 等於把前一套的企業資料接到新企業身上。順序不可顛倒：角色是資料庫 owner。
for dbn in $(sudo -u postgres psql -tAc "SELECT datname FROM pg_database WHERE datname ~ '^(org|cg)_[0-9]+$'" 2>/dev/null || true); do
    sudo -u postgres psql -c "DROP DATABASE IF EXISTS \"$dbn\" WITH (FORCE);" >/dev/null 2>&1 || true
done
for rol in $(sudo -u postgres psql -tAc "SELECT rolname FROM pg_roles WHERE rolname ~ '^(bfadmin|bfsync|cgadmin|cgmember)_[0-9]+$'" 2>/dev/null || true); do
    sudo -u postgres psql -c "DROP ROLE IF EXISTS \"$rol\";" >/dev/null 2>&1 || true
done

check_pg_version
ensure_provisioner_role

log_info "PostgreSQL 設定完成 (DB: $DB_NAME)"


# === [3/9] 取得程式碼 ===
log_step "3/9" "取得程式碼..."

# 公開 repo 不需要 token；私有 fork 才設定 GITHUB_TOKEN。
# 帶 token 時 x-access-token: 前綴不可省——token 只放 username 位置時 git 會另外索取 password，
# 無 tty 環境會直接失敗（fatal: could not read Password）
if [ -n "${GITHUB_TOKEN:-}" ]; then
    GITHUB_CLONE_URL="https://x-access-token:${GITHUB_TOKEN}@${GITHUB_REPO#https://}"
else
    GITHUB_CLONE_URL="$GITHUB_REPO"
fi

# 允許 root 操作非 root 擁有的 repo（覆蓋安裝時目錄已 chown 給 service user）
git config --global --add safe.directory "$INSTALL_DIR" 2>/dev/null || true

if [ -d "$INSTALL_DIR/.git" ]; then
    cd "$INSTALL_DIR"

    # 更新 remote URL（token 可能已變更）
    git remote set-url origin "$GITHUB_CLONE_URL"

    # 拉取最新版本並同步（force push 環境下本地 commit 必然脫離 remote 歷史，直接 reset）
    git fetch origin main 2>/dev/null
    git reset --hard origin/main
    log_info "程式碼已同步至最新版本"
else
    if [ -d "$INSTALL_DIR" ]; then
        # 目錄存在但不是 git repo，備份後重新 clone
        mv "$INSTALL_DIR" "${INSTALL_DIR}.bak.$(date +%s)"
        log_warn "既有目錄已備份"
    fi
    git clone "$GITHUB_CLONE_URL" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
    log_info "程式碼 clone 完成: $(git log --oneline -1)"
fi

# 修正檔案所有權（git 以 root clone/reset，需轉移給應用帳號）
fix_ownership


# === [4/9] Python 虛擬環境 ===
log_step "4/9" "建立 Python 虛擬環境..."
cd "$INSTALL_DIR"
sudo -u "$SERVICE_USER" python3 -m venv "$INSTALL_DIR/venv"
sudo -u "$SERVICE_USER" "$INSTALL_DIR/venv/bin/pip" install --upgrade pip -q
sudo -u "$SERVICE_USER" "$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/backend/requirements.txt" -q
log_info "Python 環境建立完成"


# === [5/9] 環境變數 ===
log_step "5/9" "設定環境變數..."

SYS_ORG_CODE=$(python3 -c "import secrets; print('sys-' + secrets.token_hex(6))")
SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
ENCRYPTION_MASTER_KEY=$(python3 -c "import os, base64; print(base64.urlsafe_b64encode(os.urandom(32)).decode())")
SYNC_CRED_KEY=$(python3 -c "import os, base64; print(base64.urlsafe_b64encode(os.urandom(32)).decode())")
OD_SA_JWT_SECRET=$(python3 -c "import os, base64; print(base64.urlsafe_b64encode(os.urandom(32)).decode())")

cat > "$INSTALL_DIR/.env" << ENVEOF
# BeakPlatform 環境設定
# 自動產生於 $(date '+%Y-%m-%d %H:%M')
FLASK_APP=app
FLASK_ENV=production

# 系統企業識別碼 (每套部署唯一，勿變更)
SYSTEM_ORG_CODE=$SYS_ORG_CODE

# 應用程式
SECRET_KEY=$SECRET_KEY
ENABLE_DEV_TOOLS=false

# URL 前綴 (Nginx location / DispatcherMiddleware 路徑)
APP_PREFIX=/beakplatform

# 子系統開發模組選單；off 時不註冊選單
NOCODE_BUILDER_MENU=on

# 資料庫
DATABASE_URL=postgresql://$DB_USER:$DB_PASS@localhost/$DB_NAME

# Redis
REDIS_URL=redis://localhost:6379/0

# Rate Limiting (速率限制)
# RATELIMIT_DEFAULT: 全站 API 總量上限 (每日/每分鐘，已登入用戶 per-user、未登入 per-IP)
# RATELIMIT_LOGIN: 登入端點限制 (per-IP，防暴力破解)
# RATELIMIT_FORGOT_PASSWORD: 忘記密碼端點限制 (per-IP)
# RATELIMIT_RESET_PASSWORD: 重設密碼端點限制 (per-IP)
RATELIMIT_ENABLED=true
RATELIMIT_DEFAULT="200000 per day;6000 per minute"
RATELIMIT_LOGIN="50 per minute"
RATELIMIT_FORGOT_PASSWORD="30 per hour"
RATELIMIT_RESET_PASSWORD="50 per hour"

# Gunicorn
GUNICORN_BIND=127.0.0.1:${APP_PORT}
GUNICORN_WORKERS=3
GUNICORN_THREADS=2

# Session
SESSION_COOKIE_SECURE=false

# 檔案加密 (FILE-01) - AES-256-GCM Master Key，遺失將無法解密既有加密附件
ENCRYPTION_MASTER_KEY=$ENCRYPTION_MASTER_KEY
ENCRYPTED_STORAGE_DIR=$INSTALL_DIR/backend/encrypted_storage

# 企業專屬資料庫佈建（非 superuser：LOGIN + CREATEDB + CREATEROLE）
# 缺少此設定時，新建企業不會有專屬資料庫，企業級對照表與簽核片語將無法使用
SYNC_PG_ADMIN_URL=postgresql://$PROV_USER:$PROV_PASS@localhost/postgres

# 企業專屬資料庫憑證加密金鑰 (Fernet)，遺失將無法解密既有企業庫帳密
SYNC_CREDENTIAL_KEY=$SYNC_CRED_KEY

# Open Defense 防禦節點執行帳號的 JWT 簽章金鑰 (HS256, base64url 32 bytes)
# 缺少時 /api/open_defense/sa/login 一律 500，防禦節點永遠拉不到封鎖決策
OD_SA_JWT_SECRET=$OD_SA_JWT_SECRET
ENVEOF

mkdir -p "$INSTALL_DIR/backend/encrypted_storage"
chown "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR/backend/encrypted_storage"
chmod 700 "$INSTALL_DIR/backend/encrypted_storage"

chown "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR/.env"
chmod 600 "$INSTALL_DIR/.env"
log_info "環境變數設定完成 (SYSTEM_ORG_CODE=$SYS_ORG_CODE)"


# === [6/9] 管理員密碼 ===
log_step "6/9" "設定管理員密碼..."

if [ -n "${ADMIN_INITIAL_PASSWORD:-}" ]; then
    ADMIN_PASS="$ADMIN_INITIAL_PASSWORD"
    log_info "使用環境變數 ADMIN_INITIAL_PASSWORD"
else
    while true; do
        read -s -p "請輸入系統管理員初始密碼 (至少 8 字元): " ADMIN_PASS
        echo ""
        if [ ${#ADMIN_PASS} -lt 8 ]; then
            log_error "密碼長度不足 8 字元，請重新輸入"
            continue
        fi
        read -s -p "請再輸入一次確認: " ADMIN_PASS_CONFIRM
        echo ""
        if [ "$ADMIN_PASS" != "$ADMIN_PASS_CONFIRM" ]; then
            log_error "兩次密碼不一致，請重新輸入"
            continue
        fi
        break
    done
fi


# === [7/9] 初始化資料庫 ===
log_step "7/9" "初始化資料庫..."
cd "$INSTALL_DIR/backend"
load_env

# 清除舊 session（Redis + filesystem）
# 必須清 Redis，否則舊 session 可跨安裝穿越，繼承前一套系統的登入狀態
redis-cli FLUSHDB > /dev/null 2>&1 || log_warn "Redis FLUSHDB 失敗，請手動清除"
rm -rf /tmp/beakplatform_sessions* /tmp/beakplatform_test_sessions* 2>/dev/null || true

apply_superuser_db_objects
run_bootstrap --fresh

log_info "資料庫初始化完成"


# === [8/9] systemd 服務 ===
log_step "8/9" "設定 systemd 服務..."

cat > "/etc/systemd/system/${SERVICE_NAME}.service" << SVCEOF
[Unit]
Description=BeakPlatform Gunicorn Service
After=network.target postgresql.service redis-server.service
Requires=postgresql.service redis-server.service

[Service]
Type=exec
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$INSTALL_DIR/backend
EnvironmentFile=$INSTALL_DIR/.env
ExecStart=$INSTALL_DIR/venv/bin/gunicorn -c gunicorn.conf.py wsgi:application
ExecReload=/bin/kill -s HUP \$MAINPID
Restart=on-failure
RestartSec=5
KillMode=mixed
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
SVCEOF

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
log_info "systemd 服務已建立: ${SERVICE_NAME}.service"


# === [9/9] Nginx ===
log_step "9/9" "設定 Nginx..."

# 自動偵測 server IP（供 nginx server_name 和完成訊息使用）
SERVER_IP=$(detect_server_ip)

cat > "/etc/nginx/sites-available/$SERVICE_NAME" << 'NGXEOF'
upstream beakplatform {
    server 127.0.0.1:APP_PORT_PLACEHOLDER;
}

server {
    listen NGINX_PORT_PLACEHOLDER;
    server_name SERVER_NAME_PLACEHOLDER;

    client_max_body_size 20M;

    # Security headers
    add_header X-Frame-Options SAMEORIGIN always;
    add_header X-Content-Type-Options nosniff always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy strict-origin-when-cross-origin always;

    location / {
        proxy_pass http://beakplatform;
        proxy_http_version 1.1;
        proxy_set_header Host $http_host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 30s;
        proxy_read_timeout 60s;
        proxy_send_timeout 60s;
    }

    location /static/ {
        proxy_pass http://beakplatform;
        expires 7d;
        add_header Cache-Control "public, immutable";
    }

    location /health {
        proxy_pass http://beakplatform;
        access_log off;
    }
}
NGXEOF

# 替換 placeholders
sed -i "s/APP_PORT_PLACEHOLDER/${APP_PORT}/" "/etc/nginx/sites-available/$SERVICE_NAME"
sed -i "s/NGINX_PORT_PLACEHOLDER/${NGINX_PORT}/" "/etc/nginx/sites-available/$SERVICE_NAME"
sed -i "s/SERVER_NAME_PLACEHOLDER/${SERVER_IP}/" "/etc/nginx/sites-available/$SERVICE_NAME"

ln -sf "/etc/nginx/sites-available/$SERVICE_NAME" "/etc/nginx/sites-enabled/"

# 移除可能衝突的舊站台設定（僅限 BeakPlatform 前身，不動用戶的其他設定）
for old_conf in beakmask; do
    if [ -f "/etc/nginx/sites-enabled/$old_conf" ]; then
        rm -f "/etc/nginx/sites-enabled/$old_conf"
        log_warn "移除舊 Nginx 設定: $old_conf"
    fi
done

nginx -t && systemctl reload nginx
log_info "Nginx 設定完成 (port $NGINX_PORT -> Gunicorn $APP_PORT)"


# === 啟動服務 ===
log_info "啟動 BeakPlatform..."
systemctl restart "$SERVICE_NAME"

health_check

# 讀取部署資訊
deployed_org_code=$(grep '^SYSTEM_ORG_CODE=' "$INSTALL_DIR/.env" | cut -d'=' -f2-)

# 組裝 URL（port 80 不顯示 port，其他 port 要帶上）
if [ "$NGINX_PORT" = "80" ]; then
    DISPLAY_URL="http://$SERVER_IP"
else
    DISPLAY_URL="http://$SERVER_IP:$NGINX_PORT"
fi

# 種入系統對外網址（URL-02：未設定時領取頁等處只會顯示「尚未設定」，
# 安裝當下就知道正確值，直接種入；已設定的不覆蓋，管理員可在
# /hostconfig/server-settings 調整）
sudo -u postgres psql -d "$DB_NAME" -q -c "
INSERT INTO system_settings (secure_code, key, value, value_type, category, created_at, updated_at, is_deleted)
SELECT substr(md5(random()::text),1,22), 'system_base_url', '$DISPLAY_URL', 'string', 'general',
       now() AT TIME ZONE 'UTC', now() AT TIME ZONE 'UTC', false
WHERE NOT EXISTS (SELECT 1 FROM system_settings WHERE key='system_base_url' AND is_deleted=false);
" 2>/dev/null || log_warn "system_base_url 種入失敗，可事後在 /hostconfig/server-settings 設定"

echo ""
echo "============================================"
log_info "全新安裝完成"
echo ""
echo "  登入網址: ${DISPLAY_URL%/}${APP_PREFIX:-/beakplatform}/auth/login"
echo "            （埠號與 ${APP_PREFIX:-/beakplatform} 缺一不可，少了會是 Not Found）"
echo ""
echo "  系統企業: $deployed_org_code"
echo "  出廠帳號（兩組共用安裝時設定的密碼，首次登入都會強制變更密碼）:"
echo "    admin@$deployed_org_code       系統管理員（管所有企業），改完密碼即可使用"
echo "    enterprise@$deployed_org_code  系統企業的原始管理員，改完密碼後進初始設定精靈"
echo ""
if [ "$DB_PASS_GENERATED" = "1" ]; then
echo "  資料庫密碼: 已自動產生，存於 $INSTALL_DIR/.env 的 DATABASE_URL（僅 root 與服務帳號可讀）"
echo ""
fi
echo "  初始設定精靈（僅 enterprise@ 與日後新建企業的 admin@ 會遇到）的說明文件在主機上："
echo "    $INSTALL_DIR/docs/install/first_login.html"
echo "    （這是檔案路徑不是網址；複製到自己電腦用瀏覽器開，不需要平台在執行中）"
echo ""
echo "  服務管理:"
echo "    sudo bash $INSTALL_DIR/scripts/install.sh --status"
echo "    sudo bash $INSTALL_DIR/scripts/install.sh --update"
echo "    sudo bash $INSTALL_DIR/scripts/install.sh --stop"
echo "    sudo bash $INSTALL_DIR/scripts/install.sh --start"
echo ""
echo "  日誌查看:"
echo "    journalctl -u $SERVICE_NAME -f"
echo "============================================"

# --demo：示範企業與防禦節點開通字串（放在總結之後，讓憑證區塊留在畫面最下方）
if [ "$WITH_DEMO" = "1" ]; then
    run_demo_provision 0
fi
