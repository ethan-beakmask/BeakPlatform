# Pitfalls — 本次建置實測踩到的坑

> 全部都是真坑。每條附錯誤訊息與修法,讓未來重做時不必再撞一次。

## 網路 / 防火牆

### P-NET-1:VM 上 fail2ban 把實體機封掉
**症狀**:從 PVE host 連 BP VM 突然 22 / 80 全 timeout,但稍早能通。
**根因**:多次 SSH 重試(sshpass 帶 PTY hang)觸發 fail2ban,把 PVE host IP 加進 jail。
**修**:
```bash
# 在 BP VM 上
sudo fail2ban-client unban 192.168.0.100
# 長期:在 /etc/fail2ban/jail.local 把 ignoreip 加 192.168.0.0/24
```

### P-NET-2:新 VM 無法連 BP API
**症狀**:`curl http://192.168.0.16:7000/...` 5 秒 timeout。
**根因**:BP VM iptables 只把舊 IP 列白名單,新 sec-vm IP 沒加。
**修**:在 BP VM 上 `iptables -I INPUT 11 -s <new-ip> -p tcp --dport 7000 -j ACCEPT`(對應 `--dport 8000`),`netfilter-persistent save`。

### P-NET-4:nftables 封鎖規則重開機就消失,而且**完全靜默**

**症狀**:`od_defense_decisions` 一路 `applied`,案件看起來處置完成,
但實際上什麼都沒封。查 `application_result` 才看到
`nft: Error: No such file or directory ... add element inet secstack blocklist`。

**成因**:`nftables-bootstrap.sh` 原本只在執行時把表建進**記憶體中的 ruleset**,
而 Ubuntu 預設 `nftables.service` 是 disabled、`/etc/nftables.conf` 不存在,
所以**開機不會還原**。.20 於 2026-07-15 02:30 重開機後,當天 21:51 起
每一筆封鎖都失敗,**沒有任何告警,持續三週**才在 2026-08-09 被發現。

**修法**(已納入 `nftables-bootstrap.sh`):寫入 `/etc/nftables.conf` +
`systemctl enable --now nftables`。

**改的時候別踩第二個坑**:`/etc/nftables.conf` **不可以用 `flush ruleset`**。
.20 的 `ip nat` / `ip filter` 由 docker(iptables-nft)管理,flush 掉所有
port forwarding 會一起沒。要用這個慣用法只重建自己那張表:

```
table inet secstack
delete table inet secstack
table inet secstack { ... }
```

**檢查方式**:

```bash
systemctl is-enabled nftables          # 應為 enabled
sudo nft list table inet secstack      # 應看得到 blocklist / allowlist
```

### P-NET-3:PVE host 與 sec-vm 同 L2 看不到對方流量
**症狀**:Suricata 在 sec-vm 上 sniff `ens18`,但看不到 BP VM ⇄ 外部的 unicast 流量。
**根因**:vmbr0 是 Linux bridge,但實體 switch 不會把 unicast 給 sec-vm —— 只看到自己的入出站。
**結論**:Suricata 在當前架構**只看 sec-vm 自己的入站**(經 cloudflared 進來那條)。要看別 VM 流量必須用 port mirror 或讓 vmbr 進 promiscuous。**這就是把 cloudflared 移到 sec-vm 的關鍵理由**:讓所有外網流量都過 sec-vm 一次。

## ClickHouse

### P-CH-1:TTL 不吃 DateTime64
**症狀**:
```
Code: 450. DB::Exception: TTL expression result column should have DateTime or Date type, but has DateTime64(3, 'UTC').
```
**修**:`TTL toDateTime(event_time) + INTERVAL 90 DAY`。

### P-CH-2:HTTP API 不接受 multi-statement
**症狀**:
```
Syntax error (Multi-statements are not allowed): failed at position ... ;
```
試過 `?multiquery=1` query string 也不通(`UNKNOWN_SETTING`)。
**修**:從 container 內走 client:
```bash
docker compose cp clickhouse/init.sql clickhouse:/tmp/init.sql
docker compose exec -T clickhouse clickhouse-client --user X --password Y \
    --multiquery --queries-file /tmp/init.sql
```

### P-CH-3:ISO timestamp `Z` 結尾不解析
**症狀**:
```
Code: 27. DB::Exception: Cannot parse input: expected '"' before: 'Z","correlation_id":...
```
**根因**:DateTime64 column 不接受 `2026-05-09T03:25:00Z`,要 `2026-05-09 03:25:00.000`(空格、無 Z、有 ms)。
**修**:Vector VRL 預先 parse 再 reformat:
```vrl
ts_input = to_string(.occurred_at) ?? ""
ts_parsed = parse_timestamp(ts_input, "%+") ?? now()
ts_ch = format_timestamp!(ts_parsed, "%Y-%m-%d %H:%M:%S%.3f")
```

### P-CH-4:第一次 init.sql 失敗後 schema 不再自動補
**症狀**:dock-entrypoint 第一次跑 init.sql 失敗,即使後面修好,容器重啟看到 data dir 非空就 `Skipping initialization`。
**修**:bootstrap.sh 主動再跑一次 schema apply。Idempotent(用 `CREATE TABLE IF NOT EXISTS`)。

## Vector / VRL

### P-VRL-1:`?? "default"` 在 infallible 表達式上是錯
**症狀**:
```
error[E651]: unnecessary error coalescing operation
.flow_id ?? "" — this expression never resolves
```
**根因**:VRL 知道 `.flow_id`(即使 missing)只回 null 不會 error,所以 `??` 沒意義。
**修**:`??` 只用在「會 error 的函式」上,不要用在 field access。
```vrl
# 錯
to_string(.foo ?? "")
# 對
to_string(.foo) ?? ""    # to_string(null) error 才需要 fallback
```

### P-VRL-2:`encode_json` 是 infallible,別 tuple 接
**症狀**:
```
error[E701]: call to undefined variable: raw
raw, _ = encode_json(.)   # ← 這寫法錯
```
**修**:`raw = encode_json(.)`(直接賦值)。

### P-VRL-3:`length(...)` / `is_empty(...)` 對 any-type 報錯
**症狀**:
```
error[E110]: invalid argument type
length(msgs) — but the parameter "value" expects one of string, array or object
```
**修**:用 `array(...) ?? []` 收斂型別:
```vrl
msgs = array(.audit_data.messages) ?? []
length(msgs)   # OK
```

### P-VRL-4:Vector port 衝突
**症狀**:
```
ERROR: Address in use (os error 98)
```
**根因**:Vector API(`api.address`)與某 source(`http_test`)用同一 port。
**修**:分開 port(api 8686,http_test 8688)。

### P-VRL-5:Vector container 沒 port mapping 就連不到 source
**症狀**:從 host 打 `http://192.168.0.20:8688` 一直無回應(curl hang)。
**根因**:Vector 在 docker bridge network,沒 publish。
**修**:`docker-compose.yml` 加:
```yaml
ports:
  - "8688:8688"
```

### P-VRL-6:Vector 跨 network 連 host-mode 容器
**症狀**:Vector 推 bridge_intake 502 / connect refused。
**根因**:Vector 在 secstack network,od-bridge 在 host net,Vector 不知道怎麼 resolve host。
**修**:在 vector service 加:
```yaml
extra_hosts:
  - "host.docker.internal:host-gateway"
```
然後 sink URL 用 `http://host.docker.internal:8500/events`。

## Suricata

### P-SUR-1:Image 啟動 chown read-only mount 失敗
**症狀**:
```
chown: changing ownership of '/etc/suricata/suricata.yaml': Read-only file system
```
無限重啟。
**修**:`docker-compose.yml` 對 suricata.yaml 與 rules dir **去掉 `:ro`**(image 入口會 chown,需可寫;但本身內容不會被 image 改)。

### P-SUR-2:`suricata-update` 自我測試失敗
**症狀**:
```
Suricata test failed, aborting. Restoring previous rules.
```
**根因**:預設 ET Open 含 SCADA(dnp3, modbus)規則,當前 Suricata 7 + 預設 yaml 沒啟用對應 protocol → 規則 parse error → `-T` 失敗 → 全部回滾。
**修**:`suricata-update --no-test`。容器啟動時部分規則會 error log,但其他正確規則照常載入。

## WAF (modsecurity-crs:nginx)

### P-WAF-1:nginx user 寫不進 named volume
**症狀**:
```
touch: cannot touch '/var/log/modsec/test': Permission denied
```
audit.log 不存在。
**根因**:Docker named volume 預設 owner=root,nginx 容器內以 uid 101 跑。
**修**:改用 bind mount,bootstrap 預先 chown:
```bash
mkdir -p ./waf/log
chown -R 101:101 ./waf/log
```
docker-compose:
```yaml
volumes:
  - ./waf/log:/var/log/modsec
```

### P-WAF-2:預設 `_` host header backend 回 502
**症狀**:`curl http://127.0.0.1:8080/` 回 502,但攻擊 pattern(`?id=1' OR ...`)正常 403。
**根因**:WAF 反代到 BP `:8000`,BP 不接 host=`_` 的請求。
**結論**:這是 backend 端設定,與 WAF 無關。當 cloudflared 把真實 hostname 帶進來時就正常。**不必修**,只是測試時要意識到 502 ≠ WAF 失敗。

## Cloudflared

### P-CF-1:Connector token vs API token 混淆
**症狀**:`Register tunnel error: Unauthorized: Invalid tunnel secret`。
**根因**:user 給的 token 對應的 tunnel ID 不存在或已被刪。
**確認方式**:base64url decode token,看裡面 JSON `{"a":account_id, "t":tunnel_id, "s":secret}`,在 Cloudflare Zero Trust UI 確認該 tunnel ID 還在。
**修**:在 Zero Trust UI 重新建一個 tunnel,複製新 token。

### P-CF-2:Token 帶換行
**症狀**:某些 token 的尾巴有 `\n`,`docker run --token "..."` 會 reject。
**修**:確認 .env 的 `CLOUDFLARE_TUNNEL_TOKEN=` 後面整段一行,沒換行。

### P-CF-3:UDP buffer size 警告
**症狀**:
```
failed to sufficiently increase receive buffer size (was: 208 kiB, wanted: 7168 kiB, got: 416 kiB)
```
**結論**:warning 不致命,QUIC 仍能跑。長期想最佳化:host 上 `sysctl -w net.core.rmem_max=7340032`。

## VM / cloud-init

### P-VM-1:Desktop 樣板的 cloud-init 不生效
**症狀**:`qm set 110 --ipconfig0 ip=...` 設了 192.168.0.20,但 VM 起來變 DHCP 取得別的 IP。
**根因**:Ubuntu desktop ISO 安裝出來的樣板,cloud-init 已 finalized(`iid-datasource-none`),不再讀 Proxmox ConfigDrive。
**修**:用 cloud image 樣板(雲端官方),或手動 SSH 進去改 netplan:
```yaml
# /etc/netplan/01-static.yaml
network:
  version: 2
  ethernets:
    ens18:
      dhcp4: false
      addresses: [192.168.0.20/24]
      routes: [{to: default, via: 192.168.0.1}]
      nameservers: {addresses: [1.1.1.1]}
```
然後 `netplan apply`(會斷線,新 IP 連回)。

## SSH / 自動化

### P-SSH-1:setsid + SSH_ASKPASS 在某些 harness 下會被當背景失敗
**症狀**:`setsid -w ssh ...` 看似成功但 exit 255,output 為空。
**修**:用 `sshpass`(`apt-get install sshpass`),或更好:儘早設 SSH key 進目標機 `authorized_keys`,後續純 key auth。

### P-SSH-2:多次密碼錯誤觸發 fail2ban
參見 P-NET-1。

## od-bridge / executor

### P-EXE-1:401 立即重登 → SA login 限速
**症狀**:executor 每 2-3 秒 SA login 一次,直到撞 10/min 限速。
**根因**:GET /decisions 401 → invalidate token → 下個 iter 重登 → 又 401(因 BP 端 decorator 漏)→ 死循環。
**修**:
1. **修 BP 端**(根本):補 decorator(`@service_account_required`)
2. **修 executor**(防呆):連續 2 次 401 開始指數退避,401 不立即 continue
3. **修 SA login 429 處理**:遇 429 直接睡 90 秒,不重試

實作見 `od-bridge/od_bridge/executor.py:run_executor_loop`。

### P-EXE-2:nft delete idempotent 字串比對錯
**症狀**:第一個 unblock 決策被 PATCH `failed`。
**根因**:enforcer 認 `"No such file"`,但 nft 實際輸出是 `"Error: element does not exist"`。
**修**:
```python
if rc != 0 and ("does not exist" in out_l or "no such file" in out_l):
    return {"ok": True, "note": "already_absent"}
```

### P-EXE-3:status=failed 後不能再轉
**結論**:契約 §5.2,`failed` 終態,executor 寫進去就無法重試。**設計為這樣** —— 由人或 BP 端處理。如果你修了 enforcer bug,舊的 failed 決策維持原狀(化石),只影響 UI 紅色記錄,不影響功能。

### P-EXE-4:bridge 502 upstream 看似 enforcer 問題,實為網路
intake `/events` 收到非 2xx 都回 502 給 client。**真正原因看 BP**(401 / 403 / 422 / 500),從 bridge container log `forwarded ... status=XXX` 才看得到上游碼。

## 整合 / 流程

### P-INT-1:source_system 不在 allowed list 回 403
參見 BEAKPLATFORM_INTEGRATION.md。`modsecurity` 不通,改 `coraza`。

### P-INT-2:event_class 沒 mapping 回 422
新 event_class 必須請 BP admin 在 form_workflow 那邊加 form template mapping。我們實測 4 種(`web_activity`/`network_activity`/`process_activity`/`detection_finding`)後來都通了。

### P-INT-3:concurrent intake 撞 BP execution_code unique
6 並發第一輪幾筆 500。BP advisory lock 已修。executor 端**不需重試 500** —— BP 會把 case 建好(冪等以 `correlation_id` 為準);若收到 500,改用同 correlation_id 重發即可。

## UI / 容器部署

### P-UI-1:Docker Hub TLS handshake 偶發 timeout
**症狀**:`docker compose build` 取 base image 時:
```
failed to fetch anonymous token: ... net/http: TLS handshake timeout
```
**修**:重試。Docker Hub 偶發,1-2 分鐘後通常正常。

### P-UI-2:重複 deploy 撞到同名容器
**症狀**:
```
Conflict. The container name "/secstack-XXX-1" is already in use by container ...
```
**根因**:兩個並行 deploy session 同時改容器。
**修**:
```bash
sudo docker rm -f $(sudo docker ps -aq --filter 'name=secstack-' --filter 'status=created')
sudo docker compose up -d --force-recreate <service>
```

### P-UI-3:`set -e` + rsync exit 23 連鎖殺死 deploy
**症狀**:遠端 ssh 內 bash `set -e` 啟動,rsync 因 perm 警告退出 23,後續所有命令都不跑。
**修**:長 deploy script **不要** `set -e`,各步驟個別判定 exit code 或寫進 array 報告。

### P-UI-4:jasonish/evebox image 入口要 binary 全路徑
**症狀**:
```
exec: "server": no such file or directory
exec: "/usr/local/bin/evebox": stat ... no such file or directory
```
**根因**:image 內 binary 在 `/usr/bin/evebox`,且預設 entrypoint 不會自動加 `evebox` prefix(只在第一個參數以 `-` 開頭時才加)。
**修**:docker-compose 寫:
```yaml
entrypoint: ["/usr/bin/evebox"]
command: ["server", "--no-auth", ...]
```

### P-UI-5:EveBox 預設啟自簽 TLS
**症狀**:`http://...:5636/` 回應為空,curl 退出 000。
**修**:用 `https://...:5636/`,瀏覽器接受自簽憑證警告。

### P-UI-6:od-bridge 改了 Python 檔但 image 沒重 build
**症狀**:`/stats`、`/forwards`、`/decisions` 仍 404 即使檔案已 sync 到 host。
**根因**:Python 程式打包進 image 時 build,改 host 上檔案不影響容器內。
**修**:
```bash
sudo docker compose build --no-cache od-bridge
sudo docker compose up -d --force-recreate od-bridge
```

## 文件 / 命名

### P-DOC-1:contract 文件不在 HTTP serve 範圍
`/opt/open_defense_contract.md` 是 BP VM 上的 plain file,`http://...:7000/.../open_defense_contract.md` 404。
要拿契約只能 SSH 進去 `cat`,或請 admin 直接複製。

### P-DOC-2:`decided_via` 字串受 CHECK 約束
我提議 `system`,實際 DB 只認 `human/auto/ai`。BP 自動轉成 `auto` 並把原值塞 `decision_metadata.requested_via`。executor 不應依此欄位作行為。
