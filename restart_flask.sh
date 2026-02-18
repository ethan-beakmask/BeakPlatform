#!/bin/bash

# BeakPlatform 服務重啟腳本
# 主服務 (port 7000) + Executor + DevTools (port 7001)

set -e

echo "======================================"
echo "  BeakPlatform 服務重啟"
echo "======================================"
echo ""

# --- 1. 清理所有相關進程 ---
echo "[1/5] 清理舊進程..."

# 1a. 停止 systemd 服務
sudo systemctl stop beakplatform 2>/dev/null || true
sudo systemctl stop beakplatform-executor 2>/dev/null || true

# 1b. 殺殘留的 flask / executor / node_runner 進程
pkill -f "flask run.*7000" 2>/dev/null || true
pkill -f "workflow_executor_main" 2>/dev/null || true
pkill -f "node_runner" 2>/dev/null || true

# 1c. 清理 port 佔用（以防 pkill 沒殺乾淨）
for PORT in 7000 7001; do
    PIDS=$(sudo lsof -ti :$PORT 2>/dev/null || true)
    if [ -n "$PIDS" ]; then
        echo "  Port $PORT 佔用中 (PID: $PIDS)，終止中..."
        echo "$PIDS" | xargs sudo kill -9 2>/dev/null || true
    fi
done

# 1d. 殺殘留的 DevTools
pkill -f "devtools/app.py" 2>/dev/null || true

sleep 1
echo "  done"

# --- 2. 重啟主服務 (systemd) ---
echo "[2/5] 重啟主服務 (port 7000)..."
sudo systemctl restart beakplatform
echo "  done"

# --- 3. 確認 Executor 服務運行 ---
echo "[3/6] 確認 Executor 服務..."
if systemctl is-active --quiet beakplatform-executor; then
    echo "  已在運行中"
else
    echo "  未運行，啟動中..."
    sudo systemctl start beakplatform-executor
    echo "  done"
fi

# --- 3b. 重啟 Sync Worker ---
echo "[3b/6] 重啟 Sync Worker..."
sudo systemctl restart beakplatform-sync-worker 2>/dev/null || true
if systemctl is-active --quiet beakplatform-sync-worker; then
    echo "  done"
else
    echo "  未安裝或啟動失敗（非必要服務）"
fi

# --- 4. 啟動 DevTools ---
echo "[4/6] 啟動 DevTools (port 7001)..."
cd /opt/BeakPlatform
source venv/bin/activate
set -a && source .env && set +a
nohup python devtools/app.py > /tmp/devtools.log 2>&1 &
echo "  done"

# --- 5. 確認相依服務 ---
echo "[5/6] 確認相依服務..."

# E-MailRelay
if systemctl is-active --quiet emailrelay; then
    echo "  E-MailRelay    running"
else
    echo "  E-MailRelay    stopped → 啟動中..."
    sudo systemctl start emailrelay
    echo "  E-MailRelay    started"
fi

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

# --- 驗證 ---
echo ""
echo "等待服務啟動..."
sleep 7

MAIN_OK=false
DEV_OK=false
EXEC_OK=false
SYNC_OK=false

if curl -s --max-time 5 http://localhost:7000/health > /dev/null 2>&1; then
    MAIN_OK=true
fi
if curl -s --max-time 5 http://localhost:7001/health > /dev/null 2>&1; then
    DEV_OK=true
fi
if systemctl is-active --quiet beakplatform-executor; then
    EXEC_OK=true
fi
if systemctl is-active --quiet beakplatform-sync-worker; then
    SYNC_OK=true
fi

echo "======================================"
echo "  服務狀態"
echo "======================================"
if $MAIN_OK; then
    echo "  主服務       http://192.168.0.16:7000  OK"
else
    echo "  主服務       http://192.168.0.16:7000  FAIL"
fi
if $EXEC_OK; then
    echo "  Executor     beakplatform-executor     OK"
else
    echo "  Executor     beakplatform-executor     FAIL"
fi
if $SYNC_OK; then
    echo "  Sync Worker  beakplatform-sync-worker  OK"
else
    echo "  Sync Worker  beakplatform-sync-worker  FAIL"
fi
if $DEV_OK; then
    echo "  DevTools     http://192.168.0.16:7001  OK"
else
    echo "  DevTools     http://192.168.0.16:7001  FAIL"
fi
echo ""
echo "查看日誌:"
echo "  主服務:      sudo journalctl -u beakplatform -f"
echo "  Executor:    sudo journalctl -u beakplatform-executor -f"
echo "  Sync Worker: sudo journalctl -u beakplatform-sync-worker -f"
echo "  DevTools:    tail -f /tmp/devtools.log"
echo ""
