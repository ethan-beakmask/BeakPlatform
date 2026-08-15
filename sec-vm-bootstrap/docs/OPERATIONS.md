# Operations — 日常維運

> day-2 操作手冊。配合 `PITFALLS.md` 看故障排除。

## 啟停 / 健康檢查

```bash
cd /home/ethan/sec-vm-bootstrap

# 看狀態
sudo docker compose ps

# 重啟單個服務
sudo docker compose restart od-bridge

# 重新建構 bridge image(改了 od-bridge/ 程式碼後)
sudo docker compose build od-bridge
sudo docker compose up -d --force-recreate od-bridge

# 全停 / 全起
sudo docker compose down       # 注意:會留 volume,但中斷服務
sudo docker compose up -d
```

## 看日誌

```bash
sudo docker compose logs -f od-bridge        # bridge ingest + executor
sudo docker compose logs -f vector           # 含 debug_* sinks 的 stdout
sudo docker compose logs -f waf-nginx        # nginx + ModSec startup messages
sudo docker compose logs -f cloudflared      # tunnel 連線狀態
sudo docker compose logs -f crowdsec         # LAPI / scenarios

# 最近 5 分鐘 + 過濾
sudo docker compose logs --since 5m od-bridge | grep -E 'decision|error'
```

## 測試 / 驗證

### 端到端 intake(從 sec-vm 自己)
```bash
curl -X POST http://127.0.0.1:8500/events \
  -H 'Content-Type: application/json' \
  -d "{
    \"correlation_id\": \"$(uuidgen)\",
    \"source_system\": \"coraza\",
    \"event_class\": \"web_activity\",
    \"occurred_at\": \"$(date -u +%FT%TZ)\",
    \"severity_id\": 3,
    \"finding\": {\"title\": \"smoke\", \"rule_id\": \"X\", \"rule_set\": \"manual\"},
    \"actor\": {\"ip\": \"203.0.113.99\"},
    \"target\": {\"host\": \"smoke\", \"url\": \"/\"}
  }"
```
預期 200 + `case_secure_code`。

### WAF 攻擊偵測
```bash
curl -s -o /dev/null -w 'SQLi=%{http_code}\n' \
    "http://127.0.0.1:8080/?id=1%20UNION%20SELECT%201--"
# 預期 SQLi=403
```

### 看當前阻擋
```bash
sudo nft list set inet secstack blocklist
# 或 JSON
sudo nft -j list set inet secstack blocklist | jq
```

### ClickHouse 查詢
```bash
PASS=$(grep ^CLICKHOUSE_PASSWORD .env | cut -d= -f2)
curl -s -u secstack:$PASS \
  "http://127.0.0.1:8123/?query=SELECT count() FROM secstack.events"

# 過去 1 小時各 source 命中
curl -s -u secstack:$PASS \
  "http://127.0.0.1:8123/?query=SELECT source_system,count() FROM secstack.events WHERE event_time>now()-INTERVAL+1+HOUR GROUP+BY+source_system FORMAT+PrettyCompact"
```

### BP 端決策觀察(需要 SA 憑證)
```bash
# 取 token
TOKEN=$(curl -s -X POST $SA_LOGIN_URL \
    -H 'Content-Type: application/json' \
    -d "{\"sa_id\":\"$SA_ID\",\"sa_secret\":\"$SA_SECRET\"}" \
    | jq -r .access_token)

# 看當前 pending
curl -s -H "Authorization: Bearer $TOKEN" \
    "$DECISIONS_URL?status=pending&limit=20" | jq

# 過去 applied
curl -s -H "Authorization: Bearer $TOKEN" \
    "$DECISIONS_URL?status=applied&limit=20" | jq
```

## 規則更新

```bash
# Suricata ET Open
sudo docker compose exec suricata suricata-update --no-test
sudo docker compose restart suricata

# OWASP CRS:跟 image 走,docker compose pull 即更新
sudo docker compose pull waf-nginx
sudo docker compose up -d waf-nginx

# CrowdSec collections
sudo docker compose exec crowdsec cscli collections install crowdsecurity/nginx
sudo docker compose exec crowdsec cscli collections list
sudo docker compose restart crowdsec
```

## 修改設定

### ModSec 從 DetectionOnly 切到 Block
```yaml
# docker-compose.yml waf-nginx 環境變數
MODSEC_RULE_ENGINE: "On"        # 開始阻擋
PARANOIA: 2                      # 提高敏感度
```
重建:
```bash
sudo docker compose up -d --force-recreate waf-nginx
```

### 調 executor 輪詢頻率
```bash
# .env
POLL_INTERVAL=10   # 預設 5

# 重啟 bridge 套用
sudo docker compose restart od-bridge
```

### 加新 enforcement_point
1. 在 `od-bridge/od_bridge/enforcers/` 寫 `xxx.py`,export `async def apply(decision, cfg)` 回 `{"ok": bool, ...}`
2. 在 `executor.py` 的 `ENFORCERS` dict 加 entry
3. `.env` 的 `MY_ENFORCEMENT_POINTS` 加 `xxx`
4. `docker compose build od-bridge && docker compose up -d --force-recreate od-bridge`

### 加新 source(要餵進 BP)
1. Vector source(file / http / tcp / kafka / ...)
2. Vector transform → OCSF
3. 把它加到 `bridge_intake` 與 `ch_events_from_ocsf` 的 inputs
4. `docker compose restart vector`

## 備份 / 還原

### 備份(小規模)
```bash
# ClickHouse 全 dump
docker compose exec clickhouse clickhouse-client \
    --user secstack --password $PASS \
    --query "BACKUP DATABASE secstack TO Disk('default','backup_$(date +%F).zip')"

# 或冷備:停掉服務後 tar volume
docker compose down
sudo tar -czf clickhouse-data.tgz \
    -C /var/lib/docker/volumes/secstack_clickhouse-data .
```

### 還原
```bash
docker compose down
sudo tar -xzf clickhouse-data.tgz \
    -C /var/lib/docker/volumes/secstack_clickhouse-data .
docker compose up -d
```

## 升級

### docker images
```bash
# 個別 service
sudo docker compose pull clickhouse
sudo docker compose up -d clickhouse

# 全部
sudo docker compose pull
sudo docker compose up -d
```

### 升 ClickHouse / 升 Vector / 升 CrowdSec
鎖定 image tag 在 `docker-compose.yml`。升級時改 tag → pull → up。注意:
- ClickHouse:跨大版本(24→25)看 release notes
- Vector:VRL 語法版本可能有 breaking change
- CrowdSec:scenarios / collections 跟版本,有時舊 acquis.yaml 要改

### 升 OWASP CRS / Suricata 規則
規則更新與 image 升級分開。日常用 `suricata-update` / `pull waf-nginx` 即可。

## 監控接入(後續可加)

### Prometheus + Grafana
```yaml
# 加進 docker-compose.yml
prometheus:
  image: prom/prometheus
  volumes: [./prometheus.yml:/etc/prometheus/prometheus.yml:ro]
  ports: ["127.0.0.1:9090:9090"]

grafana:
  image: grafana/grafana
  ports: ["3000:3000"]
  environment: { GF_SECURITY_ADMIN_PASSWORD: changeme }
```
metrics 來源:
- `node-exporter`(host)
- `cadvisor`(container)
- Vector 自己的 prometheus_exporter sink
- ClickHouse 內建 `:8123/metrics`(需開)
- CrowdSec `cscli metrics`

### Loki(日誌集中)
若要把 docker logs 集中,加 `promtail` 收 docker logs → loki。或讓 vector 加一條 docker logs source → loki sink。

## 常用 troubleshoot 命令

```bash
# 看 vector pipeline 即時通量
sudo docker compose exec vector vector top

# 查 vector 卡哪一級
sudo docker compose logs vector | grep -iE 'error|drop'

# 查 ModSec 規則命中
sudo tail -f waf/log/audit.log | jq -c '.transaction.messages | .[]?'

# 查 CrowdSec 看到哪些行為
sudo docker compose exec crowdsec cscli alerts list
sudo docker compose exec crowdsec cscli decisions list

# 看當前所有阻擋來源
sudo docker compose exec crowdsec cscli decisions list -o json | jq '.[].decisions[] | {origin, scenario, value}'

# bridge SA token 健康
sudo docker compose exec od-bridge sh -c 'cat /tmp/last_token_status 2>/dev/null || true'
sudo docker compose logs --since 1h od-bridge | grep 'SA login'
```

## 緊急情況

### 全 stop(WAF 開洞情況)
```bash
sudo docker compose stop waf-nginx
# Cloudflare 流量會在 cloudflared 端 connection refused
# 先到 Zero Trust UI 把 hostname 暫時指到 maintenance page
```

### 突發大量誤判 / 阻擋過多
```bash
# 切回 DetectionOnly,看不擋只記
# .env 改 MODSEC_RULE_ENGINE=DetectionOnly
sudo docker compose up -d --force-recreate waf-nginx

# 或臨時放白某 IP
sudo nft delete element inet secstack blocklist '{ 1.2.3.4 }'
# 但下一輪 BP 決策還是會加回去 — 要從 BP 端 revoke
```

### bridge 卡死或失控
```bash
# 暫停 executor(讓 BP 決策堆積但不執行)
# .env 把 SA_ID 清空,executor 自動 disabled
sudo docker compose restart od-bridge

# 確認沒在執行了
sudo docker compose logs --since 30s od-bridge
```

### 重置:全清重來
```bash
sudo docker compose down -v   # ⚠️ -v 會刪掉所有 volume(全資料丟失)
sudo bash bootstrap.sh         # 從零再裝
```
