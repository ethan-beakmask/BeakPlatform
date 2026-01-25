#!/bin/bash

# BeakPlatform 服務重啟腳本
# 開發環境使用

set -e

cd /opt/BeakPlatform

echo "======================================"
echo "  BeakPlatform 服務重啟"
echo "======================================"
echo ""

# 停止現有進程
echo "[1/4] 停止現有 Flask 進程..."
pkill -f "flask run.*--port=5009" 2>/dev/null || true
sleep 1
echo "  ✓ 已停止"

# 啟動服務
echo "[2/4] 啟動 Flask 服務..."
source venv/bin/activate
set -a && source .env && set +a
cd backend
nohup flask run --host=0.0.0.0 --port=5009 > /tmp/beakplatform.log 2>&1 &
cd ..
echo "  ✓ Flask 已在背景啟動"

# 等待啟動
echo "[3/4] 等待服務啟動..."
sleep 3

# 測試服務
echo "[4/4] 測試服務響應..."
if curl -s --max-time 5 http://localhost:5009/health > /dev/null; then
    echo "  ✓ 服務 (5009) 響應正常"
else
    echo "  ⚠ 服務可能未正常響應，查看日誌: tail -f /tmp/beakplatform.log"
fi
echo ""

echo "======================================"
echo "  重啟完成！"
echo "======================================"
echo ""
echo "服務訪問地址: http://192.168.0.16:5009"
echo "查看日誌:     tail -f /tmp/beakplatform.log"
echo ""
