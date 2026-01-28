#!/bin/bash

# BeakPlatform 服務重啟腳本
# 使用 systemd 管理服務

set -e

echo "======================================"
echo "  BeakPlatform 服務重啟"
echo "======================================"
echo ""

# 重啟 systemd 服務
echo "[1/3] 重啟服務..."
sudo systemctl restart beakplatform
echo "  ✓ 服務重啟指令已送出"

# 等待啟動
echo "[2/3] 等待服務啟動..."
sleep 3

# 測試服務
echo "[3/3] 測試服務響應..."
if curl -s --max-time 5 http://localhost:7000/health > /dev/null 2>&1; then
    echo "  ✓ 服務響應正常"
else
    echo "  ⚠ 服務可能未正常響應"
fi
echo ""

# 顯示狀態
echo "======================================"
echo "  服務狀態"
echo "======================================"
sudo systemctl status beakplatform --no-pager -l | head -15
echo ""

echo "服務訪問地址: http://192.168.0.16:7000"
echo "查看日誌:     sudo journalctl -u beakplatform -f"
echo ""
