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
    #   .20 自己打 127.0.0.1:8080（經 docker-proxy 走 lo；已廢除的 hourly canary 走這條，
    #   也因此它完全繞過本層判定——新的演習要從 ens18 進來才驗得到防火牆）
    #   vector container → host.docker.internal:8500（走 docker bridge 介面）
    # 只有從實體網卡進來的流量才比對來源。ens18 是 .20 唯一的實體介面，
    # suricata 的 af-packet 也綁它——換網卡名時這裡要一起改。
    #
    # policy accept + 明列 drop：本 chain 只管這三個埠，不接管 .20 的整體防火牆政策。
    # IPv6 沒有 accept 分支，一律落到 drop——正式入口 cloudflared@.16 走 IPv4。
    #
    # 8080 放行 .10/.100 是用戶 2026-08-16 的決定：保留從 Windows 工作站與 PVE 母機
    # 手動驗證 WAF 的能力。殘餘風險限縮成「那兩台被入侵才可偽造」。
    # 8500 原本只放行 .16，理由是「無認證 + 持有平台憑證」。2026-08-24 起加放 .10：
    #   - PF-112（2026-08-16）之後 POST /events 已要求 Authorization: Bearer
    #     BRIDGE_INGEST_TOKEN 且 fail-closed，上面那段「完全無認證」只剩歷史脈絡
    #   - 用戶要從 Windows 工作站的瀏覽器直接讀 EDL（http://192.168.0.20:8500/edl）
    #     與 stats UI，而 .10 本來就在 SSH 與 8080/8688 白名單內
    # 殘餘風險：/stats /forwards /decisions /edl /state/nft 這些 GET 端點仍無認證
    # （待辦 PF-115），所以 .10 一旦被入侵即可讀取封鎖清單與轉送統計。
    # .100 維持不放行。

    chain ingest_guard_forward {
        type filter hook forward priority -150; policy accept;
        iifname != "ens18" accept
        tcp dport { 8080, 8688 } ip saddr { 192.168.0.16, 192.168.0.10, 192.168.0.100 } accept
        tcp dport { 8080, 8688 } drop
    }

    chain ingest_guard_input {
        type filter hook input priority -150; policy accept;
        iifname != "ens18" accept
        tcp dport 8500 ip saddr { 192.168.0.16, 192.168.0.10 } accept
        tcp dport 8500 drop
    }

    # ---------------- PF-107：SSH 來源管制（2026-08-16 新增）----------------
    #
    # 用戶 2026-08-16 的定調：與其輪替 OS 密碼（密碼一定會流進對話記錄與文件，
    # 交談式 AI 遲早讓它再外洩一次），不如把「密碼強度」這個變數從攻擊面移除——
    # 收 IP + 走金鑰，這是內部開發環境的合理停損點。
    #
    # sshd 綁 0.0.0.0:22，在此之前整個 LAN 都打得到，密碼認證也是開的
    # （/etc/ssh/sshd_config.d/50-cloud-init.conf 寫死 PasswordAuthentication yes）。
    # 本 chain 把來源收成三台，與 ingest_guard 同一個模式、同一個 priority。
    #
    # 三台的角色：.16 自動化與本專案所有 ssh 呼叫、.10 管理者 Windows 工作站、
    # .100 PVE 母機（console 救援之外的第二條路）。
    #
    # counter 是刻意加的：日後要判斷「連不上是被這條擋掉還是服務掛了」，
    # 看 drop 的 packets 有沒有跳就知道，不必再開 tcpdump。
    #
    # IPv6 沒有 accept 分支，一律落到 drop——與 ingest_guard 一致。
    # 目前所有 SSH 來源都走 IPv4；若日後要用 IPv6 進來，這裡要加對應規則。
    #
    # 自鎖風險：本 chain priority -150 早於下方 input(-100) 的 allowlist accept，
    # 所以 allowlist 救不了被本 chain drop 的來源。改動白名單前先確認自己在裡面，
    # 真的鎖死時的最後退路是 PVE Web UI 的 VM 110 console（不經過網路堆疊）。

    # log 規則是 2026-08-16 當場加的：規則上線半小時內 drop counter 就跳到 5
    # （一次 TCP SYN 重傳序列的量），但 counter 只給數字、給不出來源。
    # rate limit 壓在 20/分鐘，被掃描時不會灌爆 kernel log。查法：
    #     sudo journalctl -k --since '-1 day' | grep SSHGUARD_DROP
    # 只有 ssh 這條有 log，管理面那條沒有——那邊目前 drop 恆為 0，
    # 有需要時照這個樣子加。

    chain ssh_guard_input {
        type filter hook input priority -150; policy accept;
        iifname != "ens18" accept
        tcp dport 22 ip saddr { 192.168.0.10, 192.168.0.16, 192.168.0.100 } counter accept
        tcp dport 22 limit rate 20/minute log prefix "SSHGUARD_DROP " level info
        tcp dport 22 counter drop
    }

    # ---------------- PF-113：管理面來源管制（2026-08-16 新增）----------------
    #
    # PF-109 收完 ingest 面之後，.20 最寬的門就換成管理面。這四個埠在此之前
    # 都是 0.0.0.0，整個 LAN 直接可達，而它們的認證強度差距很大：
    #
    #   3000 Grafana       有登入門；admin 密碼在 PF-107 之前一直是清冊裡的樣板值
    #   9443 Portainer     有登入門；但它掛著 /var/run/docker.sock，拿下＝等同 .20 root
    #   5636 EveBox        **完全無認證**（compose 明寫 --no-auth），可讀全量 Suricata 告警
    #   8686 Vector API    **完全無認證**，可讀管線拓撲與指標
    #
    # 換密碼堵的是「用預設密碼登入」，堵不住無認證的那兩個、也堵不住暴力破解與
    # 未知 CVE。兩者不互斥，所以 PF-107 收斂密碼的同時把來源也一起收。
    #
    # 走 forward hook 而非 input：這四個都是 docker 發布的埠，LAN 流量經 DNAT 後
    # 進 forward——與 ingest_guard_forward 同理。掛錯 hook 的症狀是規則永遠不命中
    # （counter 恆為 0），而不是報錯。
    #
    # 平台端（.16）不消費這四個埠：clickhouse_client 打的是 8123，該埠另有
    # 帳號層網路白名單（clickhouse/users.d/），不在本 chain 管轄內。

    chain mgmt_guard_forward {
        type filter hook forward priority -150; policy accept;
        iifname != "ens18" accept
        tcp dport { 3000, 5636, 8686, 9443 } ip saddr { 192.168.0.10, 192.168.0.16, 192.168.0.100 } counter accept
        tcp dport { 3000, 5636, 8686, 9443 } counter drop
    }
}
NFT

nft -f "$CONF"
systemctl enable nftables >/dev/null 2>&1 || true
systemctl start nftables

echo "[nft] /etc/nftables.conf 已寫入，nftables.service 已啟用（開機自動還原）"
nft list table inet secstack
