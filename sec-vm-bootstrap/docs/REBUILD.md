# Rebuild — 從零重建

> 全套堆疊重建的標準步驟。對照本流程可在任何乾淨 Proxmox 主機 + Ubuntu VM 重建一份。
> 假設你拿到的是「兩台 Linux」(實體機 + 一台 VM),想加開源 SOC 防護。

## 前提

- **PVE 主機**(實體機),Proxmox VE,vmbr0 = LAN bridge
- 一台 Ubuntu cloud-image 或乾淨 desktop 樣板可 clone
- 該 LAN 上有 BeakPlatform 部署(本契約對端),已開放對 sec-vm 來源的 7000(或對應 nginx port)
- 至少一個 Cloudflare 帳號(建 tunnel 用)
- 知道 BeakPlatform admin 聯絡管道(申請 intake key + service account)

## Phase 0 — 規劃 IP / VMID

| 角色 | 預設 |
|---|---|
| 實體機(PVE host) | `192.168.0.100` |
| BeakPlatform VM | `192.168.0.16`(假設,已有) |
| sec-vm | `192.168.0.20` |
| 新 VMID | `110`(改成你環境下一個空號) |

## Phase 1 — clone sec-vm

```bash
# 在 PVE host 上:
qm clone <TEMPLATE_VMID> 110 --name sec-vm
qm set 110 --cores 4 --memory 8192 --agent enabled=1
qm set 110 --ide0 local-lvm:cloudinit
qm set 110 --ciuser ethan --sshkey /root/.ssh/id_rsa.pub
qm set 110 --ipconfig0 ip=192.168.0.20/24,gw=192.168.0.1
qm set 110 --nameserver 1.1.1.1
qm start 110
```

> ⚠️ 若樣板是 desktop 安裝(不是 cloud image),cloud-init 可能不啟用 — 見 `PITFALLS.md` §VM。
> 解法:先以 DHCP 取得 IP、密碼登入,手動寫 `/etc/netplan/01-static.yaml` 並 `netplan apply`。

從 PVE host SSH 進去(用 key,如 cloud-init 失敗則用 VM 樣板原密——實際值見 .20 CREDENTIALS.md,不入庫):
```bash
ssh ethan@192.168.0.20
```

## Phase 2 — sec-vm 上裝 Docker

```bash
sudo apt-get update -qq
sudo apt-get install -y -qq ca-certificates curl gnupg jq
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
    | sudo tee /etc/apt/keyrings/docker.asc >/dev/null
. /etc/os-release
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $VERSION_CODENAME stable" \
    | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
sudo apt-get update -qq
sudo apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker $USER
sudo systemctl enable --now docker
```

## Phase 3 — 取得整合憑證

向 BeakPlatform admin 申請(契約 §10):
- **Intake Key**:`key_id`(以 `ik_` 開頭)+ `secret_b64`(只能取一次)
- **Service Account**:`sa_id`(BP 會強制加 `_xxxxxx` 隨機後綴)+ `sa_secret`(只能取一次)
- **allowed_source_systems** 清單:確認包含你的事件源(`coraza`、`suricata`、`falco`、`crowdsec`、`vector` 等)
- **每個 event_class 都已 mapping 到 BP 表單模板**(`web_activity`、`network_activity`、`process_activity`、`detection_finding`)

向 Cloudflare 申請:
- Zero Trust → Networks → Tunnels → Create a tunnel(`sec-vm`)→ 複製 connector token
- 後續(切流量時)在 **Public Hostnames** 把你的 domain 指到 `http://waf-nginx:8080`

## Phase 4 — 部署 stack

```bash
# 複製此 repo 到 sec-vm:/home/ethan/sec-vm-bootstrap
git clone <your-repo> /home/ethan/sec-vm-bootstrap
cd /home/ethan/sec-vm-bootstrap
cp .env.example .env
$EDITOR .env   # 填 INTAKE_KEY_ID/SECRET, SA_ID/SECRET, TUNNEL_TOKEN, CLICKHOUSE_PASSWORD

sudo bash bootstrap.sh
```

`bootstrap.sh` 做的事(idempotent):
1. 驗 .env 必填項
2. 建 `inet/secstack` nftables table(若已存在跳過)
3. 預先 chown WAF audit log 目錄為 uid 101(nginx in container)
4. `docker compose pull`,`docker compose up -d`
5. 等 ClickHouse healthy
6. 套用 schema(`clickhouse-client --queries-file`,**從 container 內**跑,不要走 HTTP multiquery)
7. 註冊 od-bridge 為 CrowdSec machine,寫憑證到 `od-bridge/state/crowdsec_machine.json`
8. 重啟 od-bridge(讓它讀到 CrowdSec 憑證)

## Phase 5 — 驗證

```bash
# 服務全 up?
docker compose ps

# 各端點存活?
curl -s -o /dev/null -w 'CH       %{http_code}\n' http://127.0.0.1:8123/ping
curl -s -o /dev/null -w 'bridge   %{http_code}\n' http://127.0.0.1:8500/health
curl -s -o /dev/null -w 'WAF      %{http_code}\n' http://127.0.0.1:8080/
curl -s -o /dev/null -w 'WAF SQLi %{http_code}\n' \
    "http://127.0.0.1:8080/?id=1%20UNION%20SELECT%201--"   # expect 403
```

打一筆測試 intake(從 sec-vm 自己):
```bash
curl -X POST http://127.0.0.1:8500/events \
  -H 'Content-Type: application/json' \
  -d "{
    \"correlation_id\": \"$(uuidgen)\",
    \"source_system\": \"coraza\",
    \"event_class\": \"web_activity\",
    \"occurred_at\": \"$(date -u +%FT%TZ)\",
    \"severity_id\": 3,
    \"finding\": {\"title\": \"rebuild verify\", \"rule_id\": \"X\", \"rule_set\": \"manual\"},
    \"actor\": {\"ip\": \"203.0.113.1\"},
    \"target\": {\"host\": \"verify\", \"url\": \"/\"}
  }"
```
預期回 `{"case_secure_code":"...","duplicate":false,"success":true,"workflow_started":true}`。

## Phase 6 — Cloudflare hostname 切過來

到 Cloudflare Zero Trust UI:
1. **Networks → Tunnels → 你的 tunnel → Public Hostnames**
2. **Add a public hostname**
   - Subdomain + Domain 選你的
   - Service: `HTTP`
   - URL: `waf-nginx:8080`
3. 立即生效(Cloudflare 邊緣 DNS 直接重指)
4. 流量開始進 sec-vm,WAF 開始過濾,Suricata 開始 sniff(**只看到** sec-vm 自己的入站封包,因為 L2 switch 不轉 unicast)

## Phase 7 — 規則更新

```bash
# Suricata ET Open(約 4 萬條啟用)
docker compose exec suricata suricata-update --no-test
docker compose restart suricata

# CrowdSec 預設 collections 已透過 env COLLECTIONS 啟動,可加更多
docker compose exec crowdsec cscli collections install crowdsecurity/nginx
docker compose restart crowdsec

# OWASP CRS 自帶最新版,paranoia 由 .env 的 PARANOIA 控制(1=寬鬆,4=嚴格)
```

## Phase 8 — 驗整套迴圈(end-to-end)

請 BP admin(或你自己)在 BP 端建一筆測試決策:
```
action=block, target_type=ip, target_value=203.0.113.42,
enforcement_points=["nftables"], ttl_seconds=60
```

預期:
- T+5s:executor 拉、`nft add element` 進 `inet secstack blocklist`,PATCH applied
- T+60s:host kernel TTL 自然 expire(已不在 set)
- T+60~120s:BP cron 下 unblock 決策,executor 拉、`nft delete`(回 `already_absent`),PATCH applied

驗證:
```bash
# 黑名單目前內容
sudo nft list set inet secstack blocklist

# BP 那邊查狀態(換成你的 SA_ID/SECRET)
curl -s -X POST http://192.168.0.16:7000/beakplatform/api/open_defense/sa/login \
    -H 'Content-Type: application/json' \
    -d '{"sa_id":"...","sa_secret":"..."}'
# 拿到 access_token 後:
curl -s -H "Authorization: Bearer <jwt>" \
    'http://192.168.0.16:7000/beakplatform/api/open_defense/decisions?status=applied'
```

## Phase 9 — 把工作目錄推進 git

```bash
cd /home/ethan/sec-vm-bootstrap
# .gitignore 已排除 .env / od-bridge/state / waf/log
git init -b main
git add -A
git commit -m "Initial Open Defense stack"
git remote add origin <your-forgejo-or-github-url>
git push -u origin main
```

## 完成

到此堆疊上線。日常 ops 見 `OPERATIONS.md`,故障排除見 `PITFALLS.md`,監控視野邊界見 `MONITORING.md`。
