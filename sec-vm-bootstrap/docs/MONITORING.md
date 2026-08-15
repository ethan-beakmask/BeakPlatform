# Monitoring — 看得到什麼,看不到什麼

> 這份是真實視野邊界,不是廣告。布署前請了解這套堆疊「不是萬能」的部分。

## 完整可見(高保真)

### HTTP 流量(經 cloudflared → WAF)
WAF 是 in-line 全文檢視:
- 完整 request line / headers / body
- ModSec 規則命中標籤(rule_id, rule_set, msg, severity)
- Anomaly score(per request inbound + outbound)
- Response status / 部分 body
- 每筆 audit log JSON 即時寫 `/var/log/modsec/audit.log` → Vector → ClickHouse + BP

⚠️ **必須 cloudflared → waf-nginx 鏈在路徑上**才會見到。直連繞過 cloudflared 的流量看不到。

### od_defense_decisions 生命週期
從 BP API 拉得到完整時序:
- `pending → picked_up → applied/partial/failed`
- `decided_at` / `picked_up_at` / `applied_at`(BP 端記)
- `applied_by`(哪台 sec-vm 處理的)

### Bridge / Executor 健康
- 容器層:`docker compose ps`,`docker compose logs -f od-bridge`
- 端點:`curl http://127.0.0.1:8500/health` → `{"ok":true}`
- 行為:executor 每 5 秒 GET decisions,有資料就 log `got N pending decisions`

### nftables blocklist 即時狀態
```bash
sudo nft list set inet secstack blocklist
sudo nft -j list set inet secstack blocklist | jq
```
看當前阻擋的 IP、剩餘 timeout。

### ClickHouse 事件儲存(歷史 SIEM)
任何 SQL 查詢:
```sql
-- 過去 1 小時各 source 命中數
SELECT source_system, count()
FROM secstack.events
WHERE event_time > now() - INTERVAL 1 HOUR
GROUP BY source_system;

-- 高嚴重度的 web 攻擊
SELECT event_time, actor_ip, target_url, finding_title
FROM secstack.events
WHERE event_class='web_activity' AND severity_id >= 4
ORDER BY event_time DESC LIMIT 100;
```

### Cloudflare edge(若加 API token)
Cloudflare 邊緣 WAF 命中 / DDoS / Bot Fight log,可 logpush 進 ClickHouse(目前未配)。

## 部分可見(有時差或抽樣)

### Suricata 看到的網路事件
**只有**:sec-vm `ens18` 介面的入出站封包。
**包含**:cloudflared QUIC 出站到 Cloudflare 邊緣、cloudflared ↔ waf-nginx 之間明文 HTTP(同主機 docker bridge,通常 sniff 不到 docker network 流量,**除非把 Suricata 放 host net 並監聽 docker bridge**)、執行端對 BP 的 LAN 連線等。
**不包含**:其他 LAN host(BP VM、別 VM)之間或對外的 unicast 流量(switch 不轉)。

### CrowdSec scenarios
依據 acquis.yaml 收集的 source(目前 Suricata EVE + journalctl sshd),命中內建 scenarios 後產 alerts。**只看到收到的 log,不看現場流量**。

### Falco(尚未啟用)
若啟用,host syscall + container 行為可見。**啟用前**:0。

## 看不到 / 不可監控

### 加密通道內的內容
- **Cloudflare ↔ user**:TLS 加密,在我們的 stack 之前已被 Cloudflare 終結再用 tunnel 給我們(明文進 WAF)。但邊緣到使用者那段我們沒視野。
- **TLS 直連 BP (`:7000`)**:目前 BP 跑 HTTP 不是 HTTPS,此處不適用,但若改 HTTPS 我們也不解密。

### Cloudflare 邊緣全貌
- 沒有 API token 就看不到 Cloudflare 邊緣 WAF 命中 / 阻擋的細節
- DDoS、Bot Fight、Rate Limit 計數都在 Cloudflare 控制台
- 想拉進 ClickHouse 要設 Cloudflare Logpush(Pro 以上 plan)

### 跨 VM(LAN 內)的橫向流量
sec-vm 不是 promiscuous,switch 不會把別人的 unicast 給它。要看就要:
1. PVE host 上把 vmbr0 開 promisc(影響全節點)
2. 用 mirror port(實體 switch 才有的功能)
3. 或在 BP VM 自己跑 sniffer(但那台是黑盒,使用者只允許 read-only)

### BP VM 內部詳情
- BP 端 form_instance / workflow execution log:**只能透過 BP UI 或 BP 端的 Claude 取**
- BP DB 直接查詢:沒授權,我們不該繞過

### 已 expired 的決策歷史細節
GET `/decisions?status=expired` 仍可拿,但 `application_result` / `error_message` 不在列表 API。要詳查得從 BP UI 看單筆。

### 個別決策的執行時間延遲
我們知道 `decided_at` 與 `applied_at`(BP 記 PATCH 時間),**但拉的瞬間**(executor 拉到 vs PATCH picked_up)在 bridge 端 log 才有,不在 BP API。

## 已內建 UI(這次施工已加)

> 完整 URL / 帳密 / 用法見 [`UI.md`](UI.md)。

| UI | 主要看什麼 |
|---|---|
| **Grafana** :3000 | 自動 provision 的 ClickHouse datasource + Secstack Overview dashboard(事件流、TopN IP、TopN 規則) |
| **Portainer** :9443 | 容器健康度、即時 log、exec |
| **EveBox** :5636 | Suricata alerts(目前因 L2 限制有限) |
| **ClickHouse Play** :8123/play | 任意 SQL 查歷史 |
| **od-bridge** :8500/stats | bridge 自家計數:intake / executor / SA token / 最近 errors |
| **Vector** :8686/playground | GraphQL 查 metrics |

## 推薦的監控告警(自己加)

### 邏輯告警
| 告警 | 規則 |
|---|---|
| executor 卡死 | bridge 容器 alive 但連續 60s 沒 `forwarded ... status=200` log,而 ClickHouse 同期有事件流 |
| BP unreachable | bridge log 連續 5 次 `forwarded ... status=502/503` |
| 大量 decisions failed | `SELECT count() FROM ... WHERE status='failed' AND decided_at > now()-30min` ≥ 3 |
| WAF 沒過濾流量 | `audit.log` 30 分鐘無新增,但 cloudflared 有流量 |
| Suricata down | 容器 `Restarting` 狀態 |
| ClickHouse 寫入停滯 | events 表 30 分鐘無新 row |

### 容量告警
| 指標 | 閾值 |
|---|---|
| ClickHouse disk | volume usage > 80% |
| Suricata eve.json | 單檔 > 1 GB(rotate 設定) |
| ModSec audit.log | 同上 |
| docker logs(per container) | 看 docker daemon 設定的 max-size |

### 推薦工具
- **Prometheus + Alertmanager + node_exporter + cadvisor**:host + container metrics
- **Grafana**:儀表板,可從 ClickHouse plugin 直接拉 SIEM 資料
- **Vector 內建 metrics**:`vector top` / Prometheus exporter
- **CrowdSec metrics**:`cscli metrics`

目前堆疊**沒**內建這些(避免一次撐太大)。文件後續加裝步驟見 `OPERATIONS.md`。

## 哲學:單一視野的限制

這套堆疊主動選擇了「**所有 HTTP 必經 cloudflared → WAF**」的窄門設計。優點:
- WAF 看到完整內容
- 可在邊緣阻擋
- 不需 promisc / 鏡像 port

代價:
- 不走這條的流量(東西向、直連、本地 LAN 服務)看不到
- cloudflared 死了 = 服務不可達(單點故障)

針對東西向想擴大視野,可:
- 每台 VM 跑 Falco / CrowdSec agent → 經 LAPI 集中
- vmbr0 開 promiscuous + Suricata 監看(會看到大量別 VM 流量,需評估隱私)

## 視野盲區處理建議

對於「我知道我看不到的部分」,目前策略:
- **東西向流量**:依靠 BP VM 自己的存取控制(認證、RLS、audit_log)
- **加密內容**:不打算解,除非把 BP TLS 終結放本 stack(目前 BP 自管)
- **Cloudflare 邊緣**:訂 logpush(未來)

對於「我不知道我看不到的部分」,定期 review:
- 每月跑一次 `git log` 看設定變更
- 每月對照 `events` 表中各 `source_system` 的事件量,確認沒有突然歸零(偵測管線斷掉)
