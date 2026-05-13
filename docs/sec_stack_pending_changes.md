# sec-stack (192.168.0.20) 變更記錄 — 待整合進「一鍵建立防護主機」程式

> 本檔記錄 2026-05-13 雪崩事件後在 sec-stack 主機 (.20) 手動套用的變更。
> 未來建立 sec-stack 一鍵部署程式時，**這些變更必須內建到模板中**，否則新部署的主機會重蹈覆轍。

## 來源主機

- IP：`192.168.0.20`
- 角色：sec-stack（Suricata + Vector + ClickHouse + od-bridge + 其他容器化資安組件）
- Bootstrap 專案路徑：`/home/ethan/sec-vm-bootstrap/`（獨立 repo，非 BeakPlatform）
- Docker compose：`/opt/sec-stack/docker-compose.yml`

## 變更項目

### 1. Suricata 規則檔：disable 3 條 STREAM sanity-check 規則

**檔案**：`/home/ethan/sec-vm-bootstrap/suricata/rules/suricata.rules`
（容器內路徑 `/var/lib/suricata/rules/suricata.rules`，由 host 路徑 bind mount）

**動作**：將以下 3 條規則的 `alert` 行加 `# DISABLED 2026-05-13 burst-fp:` 前綴註解掉。

| SID | 規則名稱 | 原因 |
|---|---|---|
| 2210020 | SURICATA STREAM ESTABLISHED packet out of window | TCP stream 重組 sanity check，FP 王 |
| 2210029 | SURICATA STREAM ESTABLISHED invalid ack | 同上 |
| 2210045 | SURICATA STREAM Packet with invalid ack | 同上 |

**規則原文**（用於辨識，未來規則庫更新時請保持 disable）：
```
alert tcp any any -> any any (msg:"SURICATA STREAM ESTABLISHED packet out of window"; stream-event:est_packet_out_of_window; classtype:protocol-command-decode; sid:2210020; rev:2;)
alert tcp any any -> any any (msg:"SURICATA STREAM ESTABLISHED invalid ack"; stream-event:est_invalid_ack; classtype:protocol-command-decode; sid:2210029; rev:2;)
alert tcp any any -> any any (msg:"SURICATA STREAM Packet with invalid ack"; stream-event:pkt_invalid_ack; classtype:protocol-command-decode; sid:2210045; rev:2;)
```

**生效方式**：`docker kill --signal=USR2 secstack-suricata-1`（規則 reload，不需重啟容器）

**未來建議**：使用 `disable.conf` 機制（suricata-update 標準作法）取代直接改 rules file，避免規則庫更新覆寫。

### 2. Vector 設定：新增 intake_filter transform

**檔案**：`/home/ethan/sec-vm-bootstrap/vector/vector.production.yaml`
（符號連結 `/home/ethan/sec-vm-bootstrap/vector/vector.yaml` 指向此檔；容器內掛載到 `/etc/vector/vector.yaml`）

**動作**：在 `# ---------------- sinks ----------------` 區段前，插入以下 transform；並把 `bridge_intake.inputs` 改為 `[intake_filter]`。

```yaml
  # 過濾規則：避免內網雜訊、自家域名、低嚴重度 Suricata 噪音灌爆 BeakPlatform
  # (ClickHouse 仍保留全部事件供事後查詢，只過濾「進入 case 流程」的部份)
  intake_filter:
    type: filter
    inputs: [ocsf_from_suricata, ocsf_from_modsec, http_test]
    condition:
      type: vrl
      source: |
        actor_ip = to_string(.actor.ip) ?? ""
        target_h = to_string(.target.host) ?? ""
        sev = to_int(.severity_id) ?? 0
        src = to_string(.source_system) ?? ""

        # 內網 ↔ 內網 全 drop (sec-stack 自家 webhook、內網設備自連)
        internal_actor = starts_with(actor_ip, "192.168.") || starts_with(actor_ip, "10.") || starts_with(actor_ip, "127.")
        internal_target = starts_with(target_h, "192.168.") || starts_with(target_h, "10.") || starts_with(target_h, "127.")

        # 自家域名 (target 是我們自己的服務,不需自我警報)
        self_domain = ends_with(target_h, "beakmask.org") || ends_with(target_h, "beakplatform.local")

        # 低嚴重度 Suricata: OCSF 1=Info 才 drop. Low(2) 以上保留，避免漏掉真實低嚴重度告警。
        # ModSec/Coraza 是 inline WAF 已實際阻擋, severity 不過濾.
        low_sev_suricata = src == "suricata" && sev <= 1

        drop = (internal_actor && internal_target) || self_domain || low_sev_suricata
        !drop
```

並修改：
```yaml
  bridge_intake:
    type: http
    inputs: [intake_filter]   # 原為 [ocsf_from_suricata, ocsf_from_modsec, http_test]
```

**未來部署參數化建議**：
- 內網網段 (`192.168.`、`10.`) 應從 config 讀取（不同企業內網不同）
- 自家域名 (`beakmask.org`、`beakplatform.local`) 應從 config 讀取
- severity 門檻應可調

### 3. Vector 設定：移除 3 個 debug console sinks

**檔案**：同上 `vector.production.yaml`

**動作**：移除以下三段（這些是 debug 期間遺留，會把所有事件寫進 docker stdout，造成 log 膨脹與效能負擔）：

```yaml
  debug_http_raw:
    type: console
    inputs: [http_test]
    encoding:
      codec: json
    target: stdout

  debug_ocsf:
    type: console
    inputs: [ocsf_from_suricata]
    encoding:
      codec: json
    target: stdout

  debug_chrows:
    type: console
    inputs: [ch_events_from_ocsf]
    encoding:
      codec: json
    target: stdout
```

**生效方式**：`docker restart secstack-vector-1`（SIGHUP reload 對於拓樸大改可能不夠，建議硬重啟）

### 4. 既存 Vector 配置潛在問題（未修，但須知）

- `api.address: 0.0.0.0:8686`：對 LAN 開放，企業部署應改為 `127.0.0.1:8686` 或加防火牆規則
- `http_test source: 0.0.0.0:8688`：同上，部署到正式環境應 disabled 或綁 127.0.0.1
- `vector.yaml` 是 symlink 指 `vector.production.yaml`，部署腳本須注意 symlink 處理

## 備份檔

手動處置時建立的備份（一鍵部署不需保留，僅供本次事件追溯）：
- `/home/ethan/sec-vm-bootstrap/vector/vector.production.yaml.bak.20260513_073421`
- Suricata rules 檔備份（複製到 `.bak.YYYYMMDD_HHMMSS`）

## 一鍵部署程式應該提供的能力（給未來開發者）

1. **冪等**：重複執行不會把已 disable 的規則重新啟用
2. **可參數化**：內網網段、自家域名、severity 門檻從 config 讀
3. **規則庫管理**：用 suricata-update + disable.conf，而非直接編輯 rules 檔
4. **健康檢查**：部署完跑 `vector validate` + `suricata-engine -T -c ...` 確認 config 過得了
5. **整合 BeakPlatform 端**：deploy 時要詢問 BeakPlatform 主機位址 + 寫 od-bridge 對應的 intake_key（這部份需要 BeakPlatform 端先建立 service account / intake key）

## 未列入但建議補強的項目

- Coraza WAF / ModSecurity 也有類似的低品質規則需 baseline disable
- Falco、CrowdSec 規則同理
- 整體應建立「規則白名單 / 黑名單」機制，而非 disable 一條救一次火
