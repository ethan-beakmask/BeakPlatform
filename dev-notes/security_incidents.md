# 資安事件追溯紀錄

記錄處置過、但未完全追究到底的 IP / 行為，再次出現時可快速回查。

## 格式

每筆獨立區段。包含：時間、IP/實體、行為、判斷、處置、待追事項。

---

## 2026-05-13 35.190.46.17 (GCP / AS396982 Google LLC)

### 事件摘要
- 時段：04:22 - 07:20 UTC（約 3 小時持續）
- 流向：`192.168.0.20 ↔ 35.190.46.17`（出站長連線）
- 觸發 Suricata 規則：sid 2210020 / 2210029 / 2210045（STREAM packet out of window / invalid ack）
- 共產生 7700+ OD intake events，4949 個 workflow_instance，導致 BeakPlatform-Dev executor 雪崩（RAM 9.4GB，load 70）

### 判斷
- 觸發規則全為 Suricata TCP stream sanity check，**非攻擊偵測**
- 35.190.46.17 屬 GCP Cloud Load Balancing IP 池（共用 IP）
- VirusTotal 歷史紀錄 2026-04-17 顯示 53/72 命中 `Stub.exe`，但現查 0/72 — **典型 GCP 動態 IP 重用污染**，過去某 GCP 客戶被植入 malware 當 C2，IP 已釋回池中換手
- 結論：**誤報 + IP 歷史污染**，非實際攻擊

### 處置
- Suricata：disable sid 2210020/2210029/2210045（檔案內 `# DISABLED 2026-05-13 burst-fp` 標記）
- Vector：新增 `intake_filter` transform，內網↔內網 / 自家域名 / Suricata sev≤1 全 drop
- BeakPlatform：清掉該批 workflow + queue

### 待追（再次出現時做）
- .20 上是哪個 process 連 35.190.46.17（cloudflared / SaaS telemetry / 自動更新 ？）
  - 偵測方法：`sudo tcpdump -i any host 35.190.46.17 -nn -w /tmp/cap.pcap` + `ss -tnp | grep 35.190`
  - 或事先設 nftables log rule：`nft add rule inet filter output ip daddr 35.190.46.17 log prefix \"trace-35.190.46.17 \" group 0`
- 若同一 src process 又連到 VT 高命中的 GCP IP，需立刻人工確認該 process 身分
