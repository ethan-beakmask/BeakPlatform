#!/bin/bash

# BeakPlatform 開發環境重啟腳本
# 開發主服務 (port 7000) + DevTools (port 7001)
# 安裝環境 (/opt/BeakPlatform) 由 systemd 管理，不在此腳本範圍

set -e

DEV_DIR="/opt/BeakPlatform-dev"

echo "======================================"
echo "  BeakPlatform 開發環境重啟"
echo "======================================"
echo ""

# --- 1. 清理開發環境進程 ---
echo "[1/4] 清理開發環境舊進程..."

pkill -f "flask run.*7000" 2>/dev/null || true
pkill -f "devtools/app.py" 2>/dev/null || true

# 清理 port 佔用
for PORT in 7000 7001; do
    PIDS=$(sudo lsof -ti :$PORT 2>/dev/null || true)
    if [ -n "$PIDS" ]; then
        echo "  Port $PORT 佔用中 (PID: $PIDS)，終止中..."
        echo "$PIDS" | xargs sudo kill -9 2>/dev/null || true
    fi
done

sleep 1
echo "  done"

# --- 2. 啟動開發主服務 (Flask dev server) ---
echo "[2/4] 啟動開發主服務 (port 7000)..."
cd "$DEV_DIR"
source venv/bin/activate
set -a && source .env && set +a
cd backend
nohup flask run --host=127.0.0.1 --port=7000 > /tmp/beakplatform-dev-flask.log 2>&1 &
echo "  PID: $!"
echo "  done"

# --- 3. 啟動 DevTools ---
echo "[3/4] 啟動 DevTools (port 7001)..."
cd "$DEV_DIR"
nohup python devtools/app.py > /tmp/beakplatform-dev-devtools.log 2>&1 &
echo "  PID: $!"
echo "  done"

# --- 4. 確認共用服務 ---
echo "[4/4] 確認共用服務..."

# PostgreSQL
if systemctl is-active --quiet postgresql; then
    echo "  PostgreSQL     running"
else
    echo "  PostgreSQL     NOT RUNNING (請手動檢查)"
fi

# Nginx
if systemctl is-active --quiet nginx; then
    echo "  Nginx          running"
else
    echo "  Nginx          NOT RUNNING (請手動檢查)"
fi

# E-MailRelay
if systemctl is-active --quiet emailrelay; then
    echo "  E-MailRelay    running"
else
    echo "  E-MailRelay    stopped → 啟動中..."
    sudo systemctl start emailrelay
    echo "  E-MailRelay    started"
fi

# 安裝環境 (systemd)
if systemctl is-active --quiet beakplatform; then
    echo "  安裝環境(8000) running"
else
    echo "  安裝環境(8000) stopped"
fi

# --- 驗證 ---
echo ""
echo "等待服務啟動..."
sleep 5

DEV_OK=false
DEVTOOLS_OK=false

if curl -s --max-time 5 http://localhost:7000/health > /dev/null 2>&1; then
    DEV_OK=true
fi
if curl -s --max-time 5 http://localhost:7001/health > /dev/null 2>&1; then
    DEVTOOLS_OK=true
fi

echo "======================================"
echo "  開發環境狀態"
echo "======================================"
if $DEV_OK; then
    echo "  Flask          dev.beakmask.org (7000)   OK"
else
    echo "  Flask          dev.beakmask.org (7000)   FAIL"
fi
if $DEVTOOLS_OK; then
    echo "  DevTools       localhost:7001             OK"
else
    echo "  DevTools       localhost:7001             FAIL"
fi
echo ""
echo "查看日誌:"
echo "  Flask:     tail -f /tmp/beakplatform-dev-flask.log"
echo "  DevTools:  tail -f /tmp/beakplatform-dev-devtools.log"
echo ""
