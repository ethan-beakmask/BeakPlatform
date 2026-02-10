#!/bin/bash

# BeakPlatform 服務重啟腳本
# 主服務 (port 7000) + DevTools (port 7001)

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
sudo systemctl stop beakmask 2>/dev/null || true
sudo systemctl stop beakmask-executor 2>/dev/null || true

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

# --- 2. 確保 executor service 保持停用 ---
echo "[2/5] 確保獨立 executor 服務停用..."
sudo systemctl disable beakplatform-executor 2>/dev/null || true
sudo systemctl disable beakmask-executor 2>/dev/null || true
echo "  done (Flask 內建 executor 模式)"

# --- 3. 重啟主服務 (systemd) ---
echo "[3/5] 重啟主服務 (port 7000)..."
sudo systemctl restart beakplatform
echo "  done"

# --- 4. 啟動 DevTools ---
echo "[4/5] 啟動 DevTools (port 7001)..."
cd /opt/BeakPlatform
source venv/bin/activate
set -a && source .env && set +a
nohup python devtools/app.py > /tmp/devtools.log 2>&1 &
echo "  done"

# --- 5. 驗證 ---
echo "[5/5] 等待服務啟動..."
sleep 3

MAIN_OK=false
DEV_OK=false

if curl -s --max-time 5 http://localhost:7000/health > /dev/null 2>&1; then
    MAIN_OK=true
fi
if curl -s --max-time 5 http://localhost:7001/health > /dev/null 2>&1; then
    DEV_OK=true
fi

# 檢查 executor 狀態
EXECUTOR_COUNT=$(pgrep -f "workflow_executor_main" | wc -l)

echo ""
echo "======================================"
echo "  服務狀態"
echo "======================================"
if $MAIN_OK; then
    echo "  主服務     http://192.168.0.16:7000  OK"
else
    echo "  主服務     http://192.168.0.16:7000  FAIL"
fi
if $DEV_OK; then
    echo "  DevTools   http://192.168.0.16:7001  OK"
else
    echo "  DevTools   http://192.168.0.16:7001  FAIL"
fi
echo "  Executor   Flask 內建 (獨立服務: ${EXECUTOR_COUNT}個)"
if [ "$EXECUTOR_COUNT" -gt 0 ]; then
    echo "  ⚠ 警告: 偵測到獨立 executor 進程，可能造成節點重複執行"
fi
echo ""
echo "查看日誌:"
echo "  主服務:   sudo journalctl -u beakplatform -f"
echo "  DevTools: tail -f /tmp/devtools.log"
echo ""
