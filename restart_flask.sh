#!/bin/bash

# BeakPlatform 服務重啟腳本
# 主服務 (port 7000) + DevTools (port 7001)

set -e

echo "======================================"
echo "  BeakPlatform 服務重啟"
echo "======================================"
echo ""

# --- 1. 清理 port 佔用 ---
echo "[1/4] 清理 port 佔用..."
for PORT in 7000 7001; do
    PIDS=$(sudo lsof -ti :$PORT 2>/dev/null || true)
    if [ -n "$PIDS" ]; then
        echo "  Port $PORT 佔用中 (PID: $PIDS)，終止中..."
        echo "$PIDS" | xargs sudo kill -9 2>/dev/null || true
        sleep 1
    fi
done
echo "  done"

# --- 2. 重啟主服務 (systemd) ---
echo "[2/4] 重啟主服務 (port 7000)..."
sudo systemctl restart beakplatform
echo "  done"

# --- 3. 啟動 DevTools ---
echo "[3/4] 啟動 DevTools (port 7001)..."
cd /opt/BeakPlatform
source venv/bin/activate
set -a && source .env && set +a
nohup python devtools/app.py > /tmp/devtools.log 2>&1 &
echo "  done"

# --- 4. 驗證 ---
echo "[4/4] 等待服務啟動..."
sleep 3

MAIN_OK=false
DEV_OK=false

if curl -s --max-time 5 http://localhost:7000/health > /dev/null 2>&1; then
    MAIN_OK=true
fi
if curl -s --max-time 5 http://localhost:7001/health > /dev/null 2>&1; then
    DEV_OK=true
fi

echo ""
echo "======================================"
echo "  服務狀態"
echo "======================================"
if $MAIN_OK; then
    echo "  主服務   http://192.168.0.16:7000  OK"
else
    echo "  主服務   http://192.168.0.16:7000  FAIL"
fi
if $DEV_OK; then
    echo "  DevTools http://192.168.0.16:7001  OK"
else
    echo "  DevTools http://192.168.0.16:7001  FAIL"
fi
echo ""
echo "查看日誌:"
echo "  主服務:   sudo journalctl -u beakplatform -f"
echo "  DevTools: tail -f /tmp/devtools.log"
echo ""
