#!/bin/bash

# BeakMask 服務重啟腳本 (systemd 版本)
# 同時重啟主服務 (5007) 和 DevTools (5008)

set -e

echo "======================================"
echo "  BeakMask 服務重啟"
echo "======================================"
echo ""

echo "[1/4] 重啟主服務 (beakmask)..."
sudo systemctl restart beakmask
echo "  ✓ 主服務重啟指令已發送"

echo "[2/4] 重啟 DevTools (beakmask-devtools)..."
sudo systemctl restart beakmask-devtools
echo "  ✓ DevTools 重啟指令已發送"
echo ""

echo "[3/4] 等待服務啟動..."
sleep 2

# 檢查主服務
if systemctl is-active --quiet beakmask; then
    echo "  ✓ 主服務運行中"
else
    echo "  ✗ 主服務啟動失敗"
    journalctl -u beakmask -n 10 --no-pager
fi

# 檢查 DevTools
if systemctl is-active --quiet beakmask-devtools; then
    echo "  ✓ DevTools 運行中"
else
    echo "  ✗ DevTools 啟動失敗"
    journalctl -u beakmask-devtools -n 10 --no-pager
fi
echo ""

echo "[4/4] 測試服務響應..."
if curl -s --max-time 5 http://localhost:5007/health > /dev/null; then
    echo "  ✓ 主服務 (5007) 響應正常"
else
    echo "  ⚠ 主服務 (5007) 可能未正常響應"
fi

if curl -s --max-time 5 http://localhost:5008/health > /dev/null; then
    echo "  ✓ DevTools (5008) 響應正常"
else
    echo "  ⚠ DevTools (5008) 可能未正常響應"
fi
echo ""

echo "======================================"
echo "  重啟完成！"
echo "======================================"
echo ""
echo "服務狀態："
systemctl status beakmask --no-pager | head -5
echo ""
systemctl status beakmask-devtools --no-pager | head -5
echo ""
echo "常用指令："
echo "  查看日誌:   journalctl -u beakmask -f"
echo "              journalctl -u beakmask-devtools -f"
echo ""
echo "服務訪問地址："
echo "  主服務:     http://192.168.0.16:5007"
echo "  DevTools:   http://192.168.0.16:5008 (內網限定)"
echo ""

journalctl -u beakmask -f

