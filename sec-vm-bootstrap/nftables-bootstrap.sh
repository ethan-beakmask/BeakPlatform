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

    # ---------------- PF-109：ingest 面來源管制（2026-08-16 新增）----------------
    #
    # 問題：Suricata 的 xff 模組與（PF-109 修正前的）vector modsec transform 都沒有
    # 「信任代理比對」——誰能直連 .20 的 ingest 埠，誰就能偽造來源歸因。實測後果是
    # 讓 CrowdSec 封鎖任意第三方 IP（PF-105 期間讓真實 AWS 位址 3.3.3.3 被 ban）。
    # 這是可被利用的 DoS 面：偽造成 DNS / 更新來源 / 上游 API 就能讓自家系統斷線，
    # 下方 allowlist 那道自鎖保險只擋得住「封掉自己」，擋不住「封掉外部關鍵服務」。
    #
    # 管三個埠，各自的偽造能力不同：
    #   8080 waf-nginx  偽造 Cf-Connecting-Ip → Suricata src_ip 被 overwrite + Coraza actor_ip
    #   8688 vector     http_test source，直接 POST 任意 OCSF 事件（compose 另已收成 127.0.0.1）
    #   8500 od-bridge  /events 完全無認證，且它持有平台 API key 會自動 HMAC 簽名轉送，
    #                   繞過 vector 全部 filter 與 throttle——三扇門裡最直接的一扇
    #
    # 分成兩條 chain 是因為封包路徑不同，不是重複：
    #   forward — 8080/8688 在 docker bridge，LAN 流量走 DNAT 後進 forward hook
    #   input   — od-bridge 是 network_mode: host，流量直接進 host input hook
    #
    # 兩條都以 `iifname != "ens18" accept` 開頭，所以這兩條必要路徑完全不受影響：
    #   .20 自己打 127.0.0.1:8080（hourly canary 走這條，經 docker-proxy 走 lo）
    #   vector container → host.docker.internal:8500（走 docker bridge 介面）
    # 只有從實體網卡進來的流量才比對來源。ens18 是 .20 唯一的實體介面，
    # suricata 的 af-packet 也綁它——換網卡名時這裡要一起改。
    #
    # policy accept + 明列 drop：本 chain 只管這三個埠，不接管 .20 的整體防火牆政策。
    # IPv6 沒有 accept 分支，一律落到 drop——正式入口 cloudflared@.16 走 IPv4。
    #
    # 8080 放行 .10/.100 是用戶 2026-08-16 的決定：保留從 Windows 工作站與 PVE 母機
    # 手動驗證 WAF 的能力。殘餘風險限縮成「那兩台被入侵才可偽造」。
    # 8500 不放行它們——無認證 + 持有平台憑證，代價是 od-bridge 的 stats UI
    # （http://192.168.0.20:8500/）從 .10 的瀏覽器連不到，要看得先 SSH 進 .20。

    chain ingest_guard_forward {
        type filter hook forward priority -150; policy accept;
        iifname != "ens18" accept
        tcp dport { 8080, 8688 } ip saddr { 192.168.0.16, 192.168.0.10, 192.168.0.100 } accept
        tcp dport { 8080, 8688 } drop
    }

    chain ingest_guard_input {
        type filter hook input priority -150; policy accept;
        iifname != "ens18" accept
        tcp dport 8500 ip saddr 192.168.0.16 accept
        tcp dport 8500 drop
    }
}
NFT

nft -f "$CONF"
systemctl enable nftables >/dev/null 2>&1 || true
systemctl start nftables

echo "[nft] /etc/nftables.conf 已寫入，nftables.service 已啟用（開機自動還原）"
nft list table inet secstack
