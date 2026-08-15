#!/bin/bash
# Bootstrap nftables enforcement sets that od-bridge will populate.
# Run as root on sec-vm host (NOT inside container; sets must live in host netns).
#
# 2026-08-09 修訂：改為「寫入 /etc/nftables.conf + 啟用 nftables.service」。
#   原版只在記憶體中建表，重開機即消失。實際事故：.20 於 2026-07-15 02:30 重開機後，
#   od_defense_decisions 從 21:51 起每一筆 block 都失敗
#   （nft: "No such file or directory" ← inet secstack 不存在），持續三週無人察覺。
#
# 另新增 allowlist 自鎖保險：關鍵基礎設施 IP 命中即 accept，
#   避免一筆錯誤的封鎖決策把管線接收端或管理者 SSH 鎖死。
set -euo pipefail

CONF=/etc/nftables.conf

cat > "$CONF" <<'NFT'
#!/usr/sbin/nft -f
#
# sec-vm host firewall — OpenDefense enforcement sets
#
# 注意：本檔刻意「不」使用 flush ruleset。
# .20 上的 ip nat / ip filter 由 docker(iptables-nft) 管理，flush 會打斷所有
# port forwarding。此處只以 delete+create 的慣用法重建 inet secstack 一張表。
#
# 由 od-bridge 的 nftables enforcer 以 `nft add element` 填入 blocklist。
# allowlist 是自鎖保險：命中者一律 accept，永遠不會被封鎖決策鎖死。

table inet secstack
delete table inet secstack

table inet secstack {
    set allowlist {
        type ipv4_addr
        flags interval
        elements = {
            192.168.0.16,    # BeakPlatform / 管線接收端，封掉會斷整條鏈
            192.168.0.10,    # 管理者工作站(SSH 來源)
            192.168.0.100    # Proxmox 母機
        }
    }

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
}
NFT

nft -f "$CONF"
systemctl enable nftables >/dev/null 2>&1 || true
systemctl start nftables

echo "[nft] /etc/nftables.conf 已寫入，nftables.service 已啟用（開機自動還原）"
nft list table inet secstack
