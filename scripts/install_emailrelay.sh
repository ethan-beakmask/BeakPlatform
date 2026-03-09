#!/bin/bash
# ==============================================================================
# E-MailRelay 安裝腳本
# 為 BeakMask 平台安裝並設定 E-MailRelay 郵件中繼服務
#
# 使用方式:
#   ./install_emailrelay.sh --prefix /opt/E-MailRelay
#   ./install_emailrelay.sh --prefix /opt/emailrelay --copy-from /opt/E-MailRelay
#   ./install_emailrelay.sh --prefix /opt/emailrelay --source /path/to/emailrelay-2.6-src.tar.gz
#   ./install_emailrelay.sh --prefix /opt/emailrelay --download
#
# 選項:
#   --prefix DIR        安裝目錄 (必填)
#   --copy-from DIR     從現有安裝複製二進位檔 (與 --source/--download 擇一)
#   --source FILE       從本機原始碼壓縮檔編譯安裝 (與 --copy-from/--download 擇一)
#   --download          自動從 SourceForge 下載原始碼編譯 (與 --copy-from/--source 擇一)
#   --smtp-server HOST  SMTP 轉發伺服器 (預設: smtp.gmail.com:587)
#   --user USER         服務執行帳號 (預設: 目前使用者)
#   --no-service        不建立 systemd service
#   --help              顯示此說明
# ==============================================================================

set -euo pipefail

# 預設值
PREFIX=""
COPY_FROM=""
SOURCE_FILE=""
DOWNLOAD=false
SMTP_SERVER="smtp.gmail.com:587"
SERVICE_USER="$(whoami)"
CREATE_SERVICE=true
EMAILRELAY_VERSION="2.6"

# 顏色輸出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

# ==============================================================================
# 參數說明
# ==============================================================================
show_usage() {
    cat <<'USAGE'
E-MailRelay 安裝腳本 - BeakMask 平台

用途:
  安裝並設定 E-MailRelay 郵件中繼服務，供 BeakMask 平台使用。
  安裝完成後，請至 BeakMask 主機設定頁面設定安裝路徑與 SMTP 認證。

使用方式:
  ./install_emailrelay.sh --prefix DIR [選項]

必填參數:
  --prefix DIR        安裝目錄 (例: /opt/E-MailRelay)

安裝來源 (擇一):
  --copy-from DIR     從現有安裝複製二進位檔 (最快)
  --source FILE       從本機原始碼壓縮檔編譯安裝
  --download          自動從 SourceForge 下載原始碼編譯 (需要網路和編譯工具)

選用參數:
  --smtp-server HOST  SMTP 轉發伺服器 (預設: smtp.gmail.com:587)
  --user USER         服務執行帳號 (預設: 目前使用者)
  --no-service        不建立 systemd service
  --help              顯示此說明

範例:
  # 從現有安裝複製到新路徑
  ./install_emailrelay.sh --prefix /opt/emailrelay --copy-from /opt/E-MailRelay

  # 下載原始碼編譯安裝
  ./install_emailrelay.sh --prefix /opt/E-MailRelay --download

  # 從本機原始碼安裝
  ./install_emailrelay.sh --prefix /opt/E-MailRelay --source ~/emailrelay-2.6-src.tar.gz

安裝完成後:
  1. 進入 BeakMask 主機設定 > E-MailRelay
  2. 設定「安裝路徑」為此腳本的 --prefix 值
  3. 設定 SMTP 認證 (Gmail 帳號 + 應用程式密碼)
  4. 發送測試郵件確認
USAGE
}

# ==============================================================================
# 參數解析
# ==============================================================================
if [ $# -eq 0 ]; then
    show_usage
    exit 0
fi

while [ $# -gt 0 ]; do
    case "$1" in
        --prefix)
            PREFIX="$2"
            shift 2
            ;;
        --copy-from)
            COPY_FROM="$2"
            shift 2
            ;;
        --source)
            SOURCE_FILE="$2"
            shift 2
            ;;
        --download)
            DOWNLOAD=true
            shift
            ;;
        --smtp-server)
            SMTP_SERVER="$2"
            shift 2
            ;;
        --user)
            SERVICE_USER="$2"
            shift 2
            ;;
        --no-service)
            CREATE_SERVICE=false
            shift
            ;;
        --help|-h)
            show_usage
            exit 0
            ;;
        *)
            log_error "未知參數: $1"
            echo "使用 --help 查看說明"
            exit 1
            ;;
    esac
done

# 驗證必填參數
if [ -z "$PREFIX" ]; then
    log_error "必須指定 --prefix 安裝目錄"
    exit 1
fi

# 移除尾部斜線
PREFIX="${PREFIX%/}"

# 驗證安裝來源
SOURCE_COUNT=0
[ -n "$COPY_FROM" ] && SOURCE_COUNT=$((SOURCE_COUNT + 1))
[ -n "$SOURCE_FILE" ] && SOURCE_COUNT=$((SOURCE_COUNT + 1))
[ "$DOWNLOAD" = true ] && SOURCE_COUNT=$((SOURCE_COUNT + 1))

if [ "$SOURCE_COUNT" -eq 0 ]; then
    log_error "必須指定安裝來源: --copy-from、--source 或 --download"
    exit 1
fi

if [ "$SOURCE_COUNT" -gt 1 ]; then
    log_error "--copy-from、--source、--download 只能擇一使用"
    exit 1
fi

# ==============================================================================
# 前置檢查
# ==============================================================================
log_info "E-MailRelay 安裝腳本"
log_info "安裝目錄: $PREFIX"
log_info "SMTP 伺服器: $SMTP_SERVER"
log_info "服務帳號: $SERVICE_USER"
echo ""

# 檢查目標目錄
if [ -d "$PREFIX" ]; then
    if [ -f "$PREFIX/sbin/emailrelay" ]; then
        log_warn "目標目錄已有 E-MailRelay 安裝: $PREFIX"
        read -p "要覆蓋安裝嗎? (y/N) " confirm
        if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
            log_info "取消安裝"
            exit 0
        fi
    fi
fi

# ==============================================================================
# 安裝方式: 複製現有安裝
# ==============================================================================
install_by_copy() {
    local src="$1"
    log_info "從 $src 複製安裝..."

    # 驗證來源
    if [ ! -f "$src/sbin/emailrelay" ]; then
        log_error "來源目錄不包含有效的 E-MailRelay 安裝: $src"
        exit 1
    fi

    if [ ! -f "$src/sbin/emailrelay-submit" ]; then
        log_error "來源目錄缺少 emailrelay-submit: $src/sbin/"
        exit 1
    fi

    # 建立目錄結構
    sudo mkdir -p "$PREFIX"/{sbin,etc,spool,logs,share/doc/emailrelay,libexec/emailrelay}

    # 複製二進位檔
    sudo cp "$src/sbin/emailrelay" "$PREFIX/sbin/"
    sudo cp "$src/sbin/emailrelay-submit" "$PREFIX/sbin/"
    if [ -f "$src/sbin/emailrelay-passwd" ]; then
        sudo cp "$src/sbin/emailrelay-passwd" "$PREFIX/sbin/"
    fi

    # 複製文件
    if [ -d "$src/share/doc/emailrelay" ]; then
        sudo cp -r "$src/share/doc/emailrelay/"* "$PREFIX/share/doc/emailrelay/" 2>/dev/null || true
    fi

    # 複製 libexec (範例腳本等)
    if [ -d "$src/libexec/emailrelay" ]; then
        sudo cp -r "$src/libexec/emailrelay/"* "$PREFIX/libexec/emailrelay/" 2>/dev/null || true
    fi

    log_info "二進位檔複製完成"
}

# ==============================================================================
# 安裝方式: 從原始碼編譯
# ==============================================================================
install_by_compile() {
    local source_path="$1"
    log_info "從原始碼編譯安裝..."

    # 檢查編譯工具
    local missing_deps=()
    command -v gcc >/dev/null 2>&1 || missing_deps+=("gcc")
    command -v g++ >/dev/null 2>&1 || missing_deps+=("g++")
    command -v make >/dev/null 2>&1 || missing_deps+=("make")

    if [ ${#missing_deps[@]} -gt 0 ]; then
        log_info "安裝編譯工具: ${missing_deps[*]}"
        sudo apt-get update -qq
        sudo apt-get install -y -qq build-essential libssl-dev
    fi

    # 檢查 OpenSSL 開發標頭
    if ! dpkg -l libssl-dev >/dev/null 2>&1; then
        log_info "安裝 libssl-dev..."
        sudo apt-get install -y -qq libssl-dev
    fi

    # 解壓
    local build_dir
    build_dir=$(mktemp -d)
    log_info "解壓到 $build_dir"
    tar -xzf "$source_path" -C "$build_dir"

    # 找到解壓後的目錄
    local src_dir
    src_dir=$(find "$build_dir" -maxdepth 1 -type d -name "emailrelay-*" | head -1)
    if [ -z "$src_dir" ]; then
        log_error "無法找到解壓後的原始碼目錄"
        rm -rf "$build_dir"
        exit 1
    fi

    # 編譯
    cd "$src_dir"
    log_info "執行 configure --prefix=$PREFIX"
    ./configure --prefix="$PREFIX" --quiet

    log_info "編譯中 (make)..."
    make -j"$(nproc)" --quiet

    log_info "安裝中 (make install)..."
    sudo make install --quiet

    # 清理
    cd /
    rm -rf "$build_dir"

    log_info "編譯安裝完成"
}

# ==============================================================================
# 安裝方式: 下載後編譯
# ==============================================================================
install_by_download() {
    log_info "從 SourceForge 下載 E-MailRelay v${EMAILRELAY_VERSION}..."

    # 檢查 wget
    if ! command -v wget >/dev/null 2>&1; then
        log_info "安裝 wget..."
        sudo apt-get update -qq
        sudo apt-get install -y -qq wget
    fi

    local download_url="https://sourceforge.net/projects/emailrelay/files/emailrelay/${EMAILRELAY_VERSION}/emailrelay-${EMAILRELAY_VERSION}-src.tar.gz/download"
    local tmp_file
    tmp_file=$(mktemp --suffix=.tar.gz)

    log_info "下載: $download_url"
    wget -q --show-progress -O "$tmp_file" "$download_url"

    if [ ! -s "$tmp_file" ]; then
        log_error "下載失敗或檔案為空"
        rm -f "$tmp_file"
        exit 1
    fi

    install_by_compile "$tmp_file"
    rm -f "$tmp_file"
}

# ==============================================================================
# 執行安裝
# ==============================================================================
if [ -n "$COPY_FROM" ]; then
    install_by_copy "$COPY_FROM"
elif [ -n "$SOURCE_FILE" ]; then
    if [ ! -f "$SOURCE_FILE" ]; then
        log_error "原始碼檔案不存在: $SOURCE_FILE"
        exit 1
    fi
    install_by_compile "$SOURCE_FILE"
elif [ "$DOWNLOAD" = true ]; then
    install_by_download
fi

# ==============================================================================
# 建立目錄結構
# ==============================================================================
log_info "建立目錄結構..."
sudo mkdir -p "$PREFIX"/{spool,logs,etc}
sudo chown -R "$SERVICE_USER":"$SERVICE_USER" "$PREFIX"
chmod 755 "$PREFIX"/spool
chmod 755 "$PREFIX"/logs

# ==============================================================================
# 產生 emailrelay.conf
# ==============================================================================
CONF_FILE="$PREFIX/etc/emailrelay.conf"
if [ ! -f "$CONF_FILE" ]; then
    log_info "產生設定檔: $CONF_FILE"
    cat > "$CONF_FILE" <<CONF
# E-MailRelay Configuration
# ========================
# 安裝路徑: ${PREFIX} (自包含，不依賴系統路徑)

# Spool 目錄
spool-dir ${PREFIX}/spool

# 定期檢查 spool 目錄（秒）
poll 10

# 目標 SMTP 伺服器
forward-to ${SMTP_SERVER}

# 啟用 TLS 加密
client-tls

# SMTP 認證檔案
client-auth ${PREFIX}/etc/emailrelay.auth

# 日誌設定
log-file ${PREFIX}/logs/emailrelay-%d.log

# 不啟動 SMTP 監聽（使用 emailrelay-submit 提交）
no-smtp
CONF
else
    log_warn "設定檔已存在，跳過: $CONF_FILE"
fi

# ==============================================================================
# 產生 emailrelay.auth (空範本)
# ==============================================================================
AUTH_FILE="$PREFIX/etc/emailrelay.auth"
if [ ! -f "$AUTH_FILE" ]; then
    log_info "產生認證檔範本: $AUTH_FILE"
    # 空範本，使用者需透過 BeakMask Web UI 設定
    cat > "$AUTH_FILE" <<'AUTH'
# E-MailRelay SMTP Authentication
# 請透過 BeakMask 主機設定 > E-MailRelay > SMTP 認證設定 進行設定
# 格式: client plain:b <email_base64> <password_base64>
AUTH
    chmod 600 "$AUTH_FILE"
else
    log_warn "認證檔已存在，跳過: $AUTH_FILE"
fi

# ==============================================================================
# 建立 systemd service
# ==============================================================================
if [ "$CREATE_SERVICE" = true ]; then
    SERVICE_FILE="/etc/systemd/system/emailrelay.service"
    log_info "建立 systemd service: $SERVICE_FILE"

    sudo tee "$SERVICE_FILE" > /dev/null <<SERVICE
[Unit]
Description=E-MailRelay
After=network-online.target
Wants=network-online.target

[Service]
Type=forking
Restart=on-failure
RestartSec=10
User=${SERVICE_USER}
Group=${SERVICE_USER}
WorkingDirectory=${PREFIX}
ExecStart=${PREFIX}/sbin/emailrelay --as-server --pid-file ${PREFIX}/emailrelay.pid ${PREFIX}/etc/emailrelay.conf
ExecStop=/bin/kill -15 \$MAINPID
PIDFile=${PREFIX}/emailrelay.pid

[Install]
WantedBy=multi-user.target
SERVICE

    sudo systemctl daemon-reload
    sudo systemctl enable emailrelay
    log_info "systemd service 已建立並啟用"
fi

# ==============================================================================
# 驗證安裝
# ==============================================================================
log_info "驗證安裝..."
ERRORS=0

if [ ! -x "$PREFIX/sbin/emailrelay" ]; then
    log_error "emailrelay 二進位檔不存在或不可執行"
    ((ERRORS++))
fi

if [ ! -x "$PREFIX/sbin/emailrelay-submit" ]; then
    log_error "emailrelay-submit 二進位檔不存在或不可執行"
    ((ERRORS++))
fi

if [ ! -d "$PREFIX/spool" ]; then
    log_error "spool 目錄不存在"
    ((ERRORS++))
fi

if [ ! -f "$PREFIX/etc/emailrelay.conf" ]; then
    log_error "設定檔不存在"
    ((ERRORS++))
fi

if [ "$ERRORS" -gt 0 ]; then
    log_error "安裝驗證失敗 ($ERRORS 個錯誤)"
    exit 1
fi

# 取得版本
VERSION=$("$PREFIX/sbin/emailrelay" --version 2>&1 | grep -oP 'V\K[0-9.]+' | head -1 || echo "unknown")

# ==============================================================================
# 完成
# ==============================================================================
echo ""
echo "=============================================="
log_info "E-MailRelay 安裝完成"
echo "=============================================="
echo ""
echo "  版本:       v${VERSION}"
echo "  安裝路徑:   ${PREFIX}"
echo "  設定檔:     ${PREFIX}/etc/emailrelay.conf"
echo "  認證檔:     ${PREFIX}/etc/emailrelay.auth"
echo "  Spool:      ${PREFIX}/spool"
echo "  日誌:       ${PREFIX}/logs"
echo "  服務帳號:   ${SERVICE_USER}"
if [ "$CREATE_SERVICE" = true ]; then
    echo "  服務名稱:   emailrelay.service"
fi
echo ""
echo "後續步驟:"
echo "  1. 啟動服務:     sudo systemctl start emailrelay"
echo "  2. 進入 BeakMask 主機設定 > E-MailRelay"
echo "  3. 設定安裝路徑為: ${PREFIX}"
echo "  4. 設定 SMTP 認證 (Gmail 帳號 + 應用程式密碼)"
echo "  5. 發送測試郵件確認"
echo ""
