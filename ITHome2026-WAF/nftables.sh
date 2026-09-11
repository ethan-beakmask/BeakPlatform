#!/bin/bash
# =============================================================================
# 防禦節點主機防火牆（nftables）——由 install.sh 呼叫，也可單獨執行
# =============================================================================
# 產生 /etc/nftables.conf 並套用，內容：
#   - inet secstack 表：od-bridge 落地封鎖決策的 blocklist / blocklist6 set
#   - allowlist 自鎖保險：平台主機與管理來源永遠不會被封鎖決策鎖死
#   - ingest 面來源管制：8080（WAF）、8688（Vector 注入口）、8500（od-bridge）
#     只有平台主機與 ADMIN_IPS 能從實體網卡打進來
#   - 管理面來源管制：3000 / 5636 / 8686 / 9443 同上
#   - SSH 來源管制（SSH_GUARD=1 才啟用）
#
# 刻意「不」flush ruleset：docker 的 nat / filter 表由 docker 自己管，flush 會
# 打斷所有 port forwarding。只以 delete + create 重建 inet secstack 一張表。
#
# 副作用：重建會清空 blocklist 現有元素。本腳本會先記下再補回。
#
# 用法：sudo bash nftables.sh <安裝目錄>   （讀 <安裝目錄>/.env）
# =============================================================================
set -euo pipefail

DEST="${1:-$(cd "$(dirname "$0")" && pwd)}"
ENV_FILE="$DEST/.env"
CONF=/etc/nftables.conf

[[ $EUID -eq 0 ]] || { echo "[!] 請用 sudo 執行" >&2; exit 1; }
[[ -f "$ENV_FILE" ]] || { echo "[!] 找不到 $ENV_FILE" >&2; exit 1; }
command -v nft >/dev/null || { echo "[!] 找不到 nft，請先安裝 nftables" >&2; exit 1; }

get_env() { grep -E "^$1=" "$ENV_FILE" | tail -1 | cut -d= -f2- ; }

NODE_IFACE="$(get_env NODE_IFACE)"
ADMIN_IPS="$(get_env ADMIN_IPS)"
SSH_GUARD="$(get_env SSH_GUARD)"
BEAK_BASE_URL="$(get_env BEAK_BASE_URL)"
PLATFORM_IP="$(printf '%s' "$BEAK_BASE_URL" | sed -E 's#^[a-z]+://##; s#[:/].*$##')"

[[ -n "$NODE_IFACE" ]] || { echo "[!] .env 缺 NODE_IFACE" >&2; exit 1; }

# 平台主機若是網域名稱而非 IP，解析一次（失敗就不放進白名單，不擋安裝）
if [[ -n "$PLATFORM_IP" ]] && ! [[ "$PLATFORM_IP" =~ ^[0-9.]+$ ]]; then
    PLATFORM_IP="$(getent ahostsv4 "$PLATFORM_IP" | awk 'NR==1{print $1}' || true)"
fi

# 組成 nft set 元素清單（去重、去空白）
build_set() {
    printf '%s\n' "$@" | tr ',' '\n' | sed 's/[[:space:]]//g' | grep -E '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+(/[0-9]+)?$' | sort -u | paste -sd, -
}
ADMIN_SET="$(build_set "$ADMIN_IPS" "$PLATFORM_IP")"
if [[ -z "$ADMIN_SET" ]]; then
    echo "[!] ADMIN_IPS 與平台 IP 都是空的，套用後所有管理面與 ingest 面都會被擋。中止。" >&2
    exit 1
fi
INGEST_SET="$(build_set "$ADMIN_IPS" "$PLATFORM_IP")"

SSH_BLOCK=""
if [[ "$SSH_GUARD" == "1" ]]; then
SSH_BLOCK=$(cat <<NFT
    # SSH 來源管制（SSH_GUARD=1）。自鎖時最後退路是主機 console。
    chain ssh_guard_input {
        type filter hook input priority -150; policy accept;
        iifname != "$NODE_IFACE" accept
        tcp dport 22 ip saddr { $ADMIN_SET } counter accept
        tcp dport 22 limit rate 20/minute log prefix "SSHGUARD_DROP " level info
        tcp dport 22 counter drop
    }
NFT
)
fi

# 先保存 blocklist 現有元素
SAVED_BL=""; SAVED_BL6=""
if nft list set inet secstack blocklist >/dev/null 2>&1; then
    SAVED_BL="$(nft -j list set inet secstack blocklist 2>/dev/null || true)"
    SAVED_BL6="$(nft -j list set inet secstack blocklist6 2>/dev/null || true)"
fi

[[ -f "$CONF" ]] && cp -a "$CONF" "$CONF.bak.$(date +%Y%m%d-%H%M%S)"

cat > "$CONF" <<NFT
#!/usr/sbin/nft -f
#
# 防禦節點主機防火牆（由 ITHome2026-WAF/nftables.sh 產生，勿手改；改 .env 後重跑）
#
# 不使用 flush ruleset：docker 的 ip nat / ip filter 由 docker 管理。
# 只以 delete + create 重建 inet secstack 一張表。

table inet secstack
delete table inet secstack

table inet secstack {
    # 自鎖保險：命中者一律 accept，永遠不會被封鎖決策鎖死
    set allowlist {
        type ipv4_addr
        flags interval
        elements = { $ADMIN_SET }
    }

    # od-bridge 的 nftables enforcer 以 nft add element 填入
    set blocklist {
        type ipv4_addr
        flags interval, timeout
    }

    set blocklist6 {
        type ipv6_addr
        flags interval, timeout
    }

    chain input {
        type filter hook input priority -100; policy accept;
        ip saddr @allowlist accept
        ip  saddr @blocklist  drop
        ip6 saddr @blocklist6 drop
    }

    # ---- ingest 面來源管制 ----
    # 能直連這三個埠的人就能偽造來源歸因（Cf-Connecting-Ip）或直接注入事件，
    # 所以只放行平台主機與管理來源。docker 發布的埠（8080/8688）走 DNAT 後進
    # forward hook；od-bridge 是 host network，8500 進 input hook。
    # 兩條都以「非實體網卡一律 accept」開頭：本機 127.0.0.1 與 docker 網段內部
    # （cloudflared → WAF、vector → od-bridge）不受影響。
    chain ingest_guard_forward {
        type filter hook forward priority -150; policy accept;
        iifname != "$NODE_IFACE" accept
        tcp dport { 8080, 8082, 8688 } ip saddr { $INGEST_SET } accept
        tcp dport { 8080, 8082, 8688 } drop
    }

    chain ingest_guard_input {
        type filter hook input priority -150; policy accept;
        iifname != "$NODE_IFACE" accept
        tcp dport 8500 ip saddr { $INGEST_SET } accept
        tcp dport 8500 drop
    }

    # ---- 管理面來源管制 ----
    # Grafana(3000) / EveBox(5636，無認證) / Vector API(8686，無認證) / Portainer(9443，掛 docker.sock)
    chain mgmt_guard_forward {
        type filter hook forward priority -150; policy accept;
        iifname != "$NODE_IFACE" accept
        tcp dport { 3000, 5636, 8686, 9443 } ip saddr { $ADMIN_SET } counter accept
        tcp dport { 3000, 5636, 8686, 9443 } counter drop
    }
$SSH_BLOCK
}
NFT

nft -c -f "$CONF"
nft -f "$CONF"
systemctl enable nftables >/dev/null 2>&1 || true
systemctl start nftables 2>/dev/null || true

# 補回封鎖清單（含剩餘 timeout）
restore_set() {
    local json="$1" setname="$2" elems elem
    [[ -n "$json" ]] || return 0
    elems="$(python3 "$(dirname "${BASH_SOURCE[0]}")/nftset_elems.py" <<< "$json" 2>/dev/null || true)"
    while IFS= read -r elem; do
        [[ -n "$elem" ]] || continue
        nft add element inet secstack "$setname" "{ $elem }" 2>/dev/null || true
    done <<< "$elems"
}
restore_set "$SAVED_BL" blocklist
restore_set "$SAVED_BL6" blocklist6

echo "[nft] /etc/nftables.conf 已寫入並套用（開機由 nftables.service 還原）"
echo "[nft] 管理／ingest 白名單：$ADMIN_SET"
[[ "$SSH_GUARD" == "1" ]] && echo "[nft] SSH 也已限制為上述來源（SSH_GUARD=1）"
exit 0
