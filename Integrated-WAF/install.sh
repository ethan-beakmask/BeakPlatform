#!/bin/bash
# =============================================================================
# Integrated-WAF 已移到獨立的 repo
# =============================================================================
# 防禦節點自 v2.0.0 起不再放在 BeakPlatform repo 內，這支腳本只印出新位置。
#   https://github.com/ethan-beakmask/Integrated-WAF
# =============================================================================

cat <<'MSG'
Integrated-WAF（防禦節點）已移到獨立的 repo：
  https://github.com/ethan-beakmask/Integrated-WAF

安裝指令（v2.0.0，iThome 2026 鐵人賽文章對應的版本）：
  curl -fsSL https://raw.githubusercontent.com/ethan-beakmask/Integrated-WAF/v2.0.0/install.sh -o ~/integrated-waf-install.sh
  sudo bash ~/integrated-waf-install.sh --pair '<開通字串>' --backend http://<被保護網站IP>:<埠> --yes

原本貼上的參數照抄到第二行即可；不加 --to 時安裝 v2.x 最新正式版。
說明文件：https://github.com/ethan-beakmask/Integrated-WAF/blob/main/docs/install.md
MSG

case "${1:-}" in
    -h|--help) exit 0 ;;
esac
exit 1
