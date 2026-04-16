#!/bin/bash
# =============================================================================
# BeakPlatform 開發環境更新腳本
# 用於這台開發主機，執行兩件事：
#   1. 呼叫 install.sh --update 更新安裝環境 (/opt/BeakPlatform)
#   2. 補上 Nginx vhost (app.beakmask.org → 8000 安裝環境)
#      開發環境 (dev.beakmask.org → 7000)
#      IP 直連回 444
# =============================================================================
# 用法:
#   sudo bash dev_update.sh                 更新安裝環境 + 補 Nginx
#   sudo bash dev_update.sh --nginx-only    只重新設定 Nginx（不更新安裝環境）
# =============================================================================
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_step()  { echo -e "${BLUE}[$1]${NC} $2"; }

# === 權限檢查 ===
if [ "$(id -u)" -ne 0 ]; then
    log_error "請使用 sudo 執行"
    exit 1
fi

NGINX_ONLY=false
if [ "$1" = "--nginx-only" ]; then
    NGINX_ONLY=true
fi

# === Step 1: 更新安裝環境 ===
if [ "$NGINX_ONLY" = false ]; then
    log_step "1/2" "更新安裝環境 (/opt/BeakPlatform)..."
    echo ""
    bash /opt/BeakPlatform-dev/scripts/install.sh --update
    echo ""
    log_info "安裝環境更新完成"
else
    log_step "1/2" "跳過安裝環境更新 (--nginx-only)"
fi

# === Step 2: 設定 Nginx vhost ===
log_step "2/2" "設定 Nginx vhost..."

# 備份現有設定
if [ -f /etc/nginx/sites-available/beakplatform ]; then
    cp /etc/nginx/sites-available/beakplatform "/etc/nginx/sites-available/beakplatform.bak.$(date +%Y%m%d%H%M%S)"
fi

# --- 安裝環境: app.beakmask.org → 8000 (CloudFlare Tunnel) ---
cat > /etc/nginx/sites-available/beakplatform << 'NGXEOF'
# === 安裝環境 (模擬用戶安裝, CloudFlare Tunnel 入口) ===
upstream beakplatform_prod {
    server 127.0.0.1:8000;
}

server {
    listen 80;
    server_name app.beakmask.org;

    client_max_body_size 20M;

    add_header X-Frame-Options SAMEORIGIN always;
    add_header X-Content-Type-Options nosniff always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy strict-origin-when-cross-origin always;

    location / {
        proxy_pass http://beakplatform_prod;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 30s;
        proxy_read_timeout 60s;
        proxy_send_timeout 60s;
    }

    location /static/ {
        proxy_pass http://beakplatform_prod;
        expires 7d;
        add_header Cache-Control "public, immutable";
    }

    location /health {
        proxy_pass http://beakplatform_prod;
        access_log off;
    }
}
NGXEOF

# --- 開發環境: dev.beakmask.org → 7000 ---
cat > /etc/nginx/sites-available/beakplatform-dev << 'NGXEOF'
# === 開發環境 ===
upstream beakplatform_dev {
    server 127.0.0.1:7000;
}

server {
    listen 80;
    server_name dev.beakmask.org;

    client_max_body_size 20M;

    add_header X-Frame-Options SAMEORIGIN always;
    add_header X-Content-Type-Options nosniff always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy strict-origin-when-cross-origin always;

    location / {
        proxy_pass http://beakplatform_dev;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 30s;
        proxy_read_timeout 60s;
        proxy_send_timeout 60s;
    }

    location /static/ {
        proxy_pass http://beakplatform_dev;
        expires 7d;
        add_header Cache-Control "public, immutable";
    }

    location /health {
        proxy_pass http://beakplatform_dev;
        access_log off;
    }
}
NGXEOF

# --- IP 直連拒絕 ---
cat > /etc/nginx/sites-available/default << 'NGXEOF'
# === 拒絕 IP 直連或未知 domain ===
server {
    listen 80 default_server;
    server_name _;
    return 444;
}
NGXEOF

# 啟用站台
ln -sf /etc/nginx/sites-available/beakplatform /etc/nginx/sites-enabled/
ln -sf /etc/nginx/sites-available/beakplatform-dev /etc/nginx/sites-enabled/
ln -sf /etc/nginx/sites-available/default /etc/nginx/sites-enabled/

# 測試並 reload
if nginx -t 2>&1; then
    systemctl reload nginx
    log_info "Nginx 設定完成"
else
    log_error "Nginx 設定有誤，請檢查"
    exit 1
fi

echo ""
echo "======================================"
echo "  Nginx vhost 設定"
echo "======================================"
echo "  app.beakmask.org  → 127.0.0.1:8000 (安裝環境, CloudFlare Tunnel)"
echo "  dev.beakmask.org  → 127.0.0.1:7000 (開發環境)"
echo "  IP 直連 / 其他     → 444 (拒絕)"
echo ""
