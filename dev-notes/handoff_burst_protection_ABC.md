# 交接：BeakPlatform 爆量防護 A+B+C 實作

> **下次對話使用此文件作為起始 prompt。** 由 2026-05-13 雪崩事件衍生。

## 背景（請先讀）

2026-05-13 sec-stack（在 192.168.0.20）因 Suricata STREAM sanity-check 規則 false positive，3 小時內產生 4063 個 OD intake events。BeakPlatform-Dev executor 為每個 node 派 170MB Python subprocess，RAM 衝到 9.4GB，load 70，整台 VM 雪崩。

事件處置已完成（Suricata 規則 disable + Vector intake_filter），詳見 `dev-notes/security_incidents.md`。本任務是**強化 BeakPlatform 本身對爆量的抵抗力**。

## 待做事項（合計約 2-3 小時）

### A. systemd 資源上限（兜底，5 分鐘）

Service: `beakplatform-dev-executor.service`
- `MemoryMax=2G`
- `TasksMax=20`
- `MemorySwapMax=0`（避免吃 swap 拖整台）

Production service 同步加但 `MemoryMax=4G` `TasksMax=40`（如果 production 有跑同款 executor）。

**注意**：systemd unit 修改屬 OS 層級變更，需先備份原檔，並提示用戶現場確認後再 `systemctl daemon-reload`。

### B. Executor 並發 semaphore（封頂，30 分鐘）

檔案：`/opt/BeakPlatform-dev/backend/workflow_executor_main.py`

現況：對每個 PENDING queue item 直接 `subprocess.Popen` node_runner，無上限。

實作：
- 加 `asyncio.Semaphore(N)` 或 `multiprocessing.BoundedSemaphore`，N 預設 8（從環境變數 `EXECUTOR_MAX_CONCURRENT` 讀，預設 8）
- spawn 前 acquire，subprocess 結束後 release
- 達到上限時 PENDING 任務排隊等下一輪 poll

驗證：用 `pgrep -c node_runner` 看不會超過 N。

### C. Intake 層 dedup（治本，1-2 小時）

**這是核心改動**，重點：

#### Schema 擴充（新 migration）

`od_intake_events` 表現況：每個事件獨立一筆，每筆觸發一個 workflow_instance。

擴充方案：**新增 `od_intake_aggregations` 表**，保留 `od_intake_events` 為 raw store（不動），但 **case 建立邏輯改為查 aggregation**。

```
od_intake_aggregations:
  id, secure_code, org_secure_code
  dedup_key VARCHAR(256) -- 形如 "suricata|2210020|192.168.0.20|35.190.46.17"
  first_seen_at, last_seen_at  -- 用於 window 判斷
  event_count INTEGER          -- 累計事件數
  status VARCHAR(20)           -- 'open' | 'closed'
  case_secure_code VARCHAR(32) -- 對應 workflow_instance (僅在第一筆建立時產生)
  severity_max SMALLINT        -- 觀察期間最高嚴重度
  sample_event_ids INTEGER[]   -- 前 N + 後 N 共 ~20 筆 od_intake_events.id
  aggregated_dimensions JSONB  -- 變動維度集合，如 {"dst_ports": [22,3389,...], "src_ips": [...]}
  escalation_log JSONB         -- 觸發升級的歷史
  created_at, updated_at, is_deleted
  
UNIQUE (org_secure_code, dedup_key) WHERE status='open'  -- 同 dedup_key 同時只能有 1 個 open
INDEX (status, last_seen_at)                              -- 用於背景 close-by-idle
```

#### Dedup key 設計

預設：`{source_system}|{rule_id}|{actor.ip}|{target.host}`

可由 intake_key（per HMAC key）設定客製化 key template（將來擴充）。

#### Window 策略（採方案 b）

- 新事件進來 → 算 dedup_key
- 查同 org + 同 key + status='open' 的 aggregation
  - 有 → UPDATE last_seen_at + event_count++ + 抽樣決定是否加入 sample_event_ids + 累積 aggregated_dimensions
  - 沒有 → INSERT 新 aggregation + 建立 workflow_instance + 開新 case
- **背景 job**（單獨小腳本，crontab 每分鐘跑）：將 last_seen_at 超過 5 分鐘的 aggregation 標 status='closed'

#### Escalation 階梯（建議內建）

count=1 開 case；count 達 10/100/1000 各升級 severity_max 並寫 escalation_log；不重開 case，但通知通道可基於 event_count 做門檻過濾。

#### intake_service.py 改動

`intake_service.process_event()` 流程：
1. 寫 raw 到 `od_intake_events`（不變）
2. 算 dedup_key
3. UPSERT `od_intake_aggregations`
4. 若新建（INSERT），啟動 workflow_instance（同現行邏輯）
5. 若已存在（UPDATE），不啟動 workflow，只更新統計

#### Sample 抽樣策略

- count <= 10：每筆都進 sample_event_ids
- 10 < count <= 100：每 10 筆抽 1 筆
- count > 100：每 100 筆抽 1 筆，外加保留最後 5 筆

#### 通知通道

不在本任務範圍，但 escalation_log 要設計成能讓未來的 notifier 讀取。

## Manifest 更新

完成後同步更新 `dev-notes/manifests/mod-open-defense.yaml`，加入新增的 model（aggregation）、新增的 service method、新增的 migration。

## 驗證計畫

1. 用 http_test 端點注入 100 個同 dedup_key 的事件
2. 預期：只 1 個 workflow_instance，od_intake_aggregations 有 1 筆 event_count=100
3. 預期：sample_event_ids 有約 19 筆 ID
4. 用不同 dedup_key 注入 → 各開獨立 aggregation

## 完成判定

- A：`systemctl show beakplatform-dev-executor` 看得到 MemoryMax 等限制
- B：壓測時 `pgrep -c node_runner` 永遠 <= N
- C：上述驗證通過，且 manifest 更新

---

## 不要做的事

- 不要動 Vector 過濾（已完成，見 `/home/ethan/sec-vm-bootstrap/vector/vector.production.yaml`）
- 不要動 Suricata 規則（已 disable 3 條 false positive）
- 不要碰 security-core 檔案
- 不要動 production 的 executor（只動 dev）

## 完成後

提示用戶啟動 dev executor：`sudo systemctl start beakplatform-dev-executor.service`
然後可以開新對話處理 Guardian（見 `dev-notes/handoff_beakwatch_guardian.md`）。
