# 統一 Raw Store + NAS 歸檔架構規格

**版本**: v1.0-draft
**建立**: 2026-05-13
**狀態**: 草稿
**最後現況對齊**: 2026-08-10（見 §0）
**對應契約**: Open Defense v2（incident envelope 內 `related_locators` 指向本 store）

---

## 0. 現況對齊（2026-08-10）

本規格寫於 2026-05-13。**平台側到目前為止一行都沒實作**，
本節只寫平台側可驗證的事實；sec-vm（`.20`）側的 ClickHouse 現況一律待確認，
權威在 `/opt/Ethan_Lab/ITHome-2026/CLAUDE.md`。

| 本規格假設 | 平台側現況（2026-08-10） |
|---|---|
| 熱層 ClickHouse 在 sec-vm | **已有雛形**（2026-08-10 實查 `.20` `secstack-clickhouse-1`，ClickHouse 24.8.14）：資料庫 `secstack` 有 `events`（2321 列）、`findings`（0 列）與三個物化視圖（`attacker_ip_daily` / `events_hourly_dim` / `events_per_minute`）。`events` 的欄位是 **OCSF v1 契約的扁平化版本**（`correlation_id` / `source_system` / `event_class` / `severity_id` / `actor_*` / `target_*` / `finding_*`）**且含 `raw String` 存原文**——本規格 §3 的熱層需求實質上已被覆蓋，差別只在表名與欄位命名不同，且沒有 §3 的 `incident_id` 維度。**要沿用它擴充，不要另建一套** |
| §9：v2 後 `od_intake_events` 只留 metadata、不再存原文 | **仍完整存 `raw_body` JSONB**。v2 未上線，這條還沒到執行時機 |
| §6 查詢介面（案件詳情頁「查原文」按鈕） | **零實作**。處置中心的「事件明細」分頁讀的是 `form_data` 內的明細陣列，不會打 sec-vm |
| 溫層 Parquet、冷層 NAS 歸檔 | 零實作，NAS 路徑與帳號（§8.2）仍未定 |

**因此本規格的剩餘工作實際上是三件**：熱層補 `incident_id` 維度（等 v2 定案）、
溫層 Parquet 與冷層 NAS（全新）、以及 §6 的查詢介面（平台端「查原文」按鈕，
即 v2 §3 反向通道）。**熱層不必重做。**

### 連線資訊（2026-08-10 用戶授權 Claude Code 直接進 .20 取環境資料）

```bash
ssh -i ~/.ssh/company-wsl ethan@192.168.0.20      # hostname sec-vm，ethan 有 sudo NOPASSWD
docker exec secstack-clickhouse-1 clickhouse-client -q 'SHOW TABLES FROM secstack'
```

`.20` 的運維權威文件在 `/opt/Ethan_Lab/ITHome-2026/CLAUDE.md`，
**查得到的事實寫在那邊或本節，不要在本 repo 另存一份會漂移的副本。**

### 一個新出現的相關事實

2026-08-10 起，原生 SOC 通報會**整包扁平化進 `fw_form_instances.form_data`**
（上限 256KB／500 個 key／明細 500 列），明細陣列直接渲染在案件詳情頁。
也就是說**「案件詳情頁看得到原文」這件事，在小資料量情境已經達成，
不需要反向通道**。本規格要解決的是另一個層級的問題：
事件量大到不能塞進 form_data、以及 5 年保存與跨資料源統一查詢。
定稿時要把兩者的分界寫清楚，避免重複建設。

---

## 1. 設計目標

| 目標 | 動機 |
|---|---|
| **跨資料源統一儲存** | OD intake / ELK / Splunk export / email / csv / xlsx / MariaDB / SQLite / JSON 全部歸到同一個 store，案件詳情頁查原文只要一個 API |
| **熱資料快查** | 案件詳情頁需 < 3 秒查到原文（最近 90 天案件最多被查） |
| **5 年保存** | 公司規定，但實際冷資料可離線 |
| **5 年後仍可讀** | 不被特定產品綁死，匯出格式必須 self-describing |
| **責任分層** | NAS 歸檔後由其他部門保管，本系統只負責「查得到、讀得出」 |

---

## 2. 三層儲存

```
┌─ 熱層（ClickHouse, on sec-vm）────────────┐
│  最近 90 天，案件詳情頁查詢用              │
│  schema: raw_events 表（見 §3）            │
└────────────────┬───────────────────────────┘
                 │ 90 天後自動轉檔
                 ▼
┌─ 溫層（Parquet, on sec-vm 本機）───────────┐
│  91 天 ~ 1 年，按月 partition              │
│  路徑: /var/raw_archive/YYYY-MM/*.parquet  │
│  仍可用 DuckDB / ClickHouse external 查詢  │
└────────────────┬───────────────────────────┘
                 │ 1 年後自動匯出
                 ▼
┌─ 冷層（NAS, 由其他部門保管）───────────────┐
│  1 年 ~ 5 年，Parquet + manifest + SOP     │
│  路徑: nas://soc_archive/YYYY-MM/          │
│  本系統不再持有，但保有「怎麼讀」的 SOP    │
└────────────────────────────────────────────┘
```

熱→溫→冷三段保留各自的查詢能力，**冷層不要求即時查**，調舊資料時用 DuckDB 開檔即可。

---

## 3. 熱層 ClickHouse Schema

```
CREATE TABLE raw_events (
    ts              DateTime64(3, 'UTC'),
    source          LowCardinality(String),     -- 'suricata' / 'coraza' / 'splunk' / 'email_csirt' / ...
    event_class     LowCardinality(String),     -- OCSF: 'web_activity' / 'network_activity' / ...
    severity_id     UInt8,
    incident_id     String,                     -- 對應 Platform 端案件
    actor_ip        IPv6,                       -- IPv4 自動轉 v6
    actor_country   FixedString(2),
    target_host     String,
    rule_id         String,
    payload         String CODEC(ZSTD(6)),      -- 原始 JSON，壓縮儲存
    payload_format  LowCardinality(String)      -- 'ocsf' / 'cef' / 'syslog' / 'raw_email' / ...
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(ts)
ORDER BY (ts, incident_id, source)
TTL ts + INTERVAL 90 DAY TO VOLUME 'warm'      -- 90 天後搬溫層
SETTINGS index_granularity = 8192;
```

設計重點：

- **payload 一律 ZSTD 壓縮**，混雜格式對壓縮率影響不大（同源資料重複度高）
- **常查欄位拉出來建索引**（ts/incident_id/actor_ip/source），其他丟 payload
- **payload_format 標記**，讀的時候才知道怎麼 parse
- TTL 自動搬 volume，不需要排程

### 寫入路徑

Layer 1 parser → 統一 dict → 寫入 raw_events 表（一個 source 一條 INSERT，批次 1000 筆）。

---

## 4. 溫層 Parquet 規格

ClickHouse 90 天 TTL 觸發後，**每月 partition 由 cron 匯出為 Parquet**：

```
/var/raw_archive/2026-02/
  raw_events_2026-02.parquet      # 主資料
  raw_events_2026-02.manifest.json # 中繼資料
  schema.md                        # 欄位字典（每月一份，防 schema 漂移）
```

### Parquet 結構

欄位順序與 ClickHouse 一致，使用 **Snappy 壓縮**（讀取速度快、與 ZSTD 容量差距小）。

每檔大小目標 **256 MB ~ 1 GB**，超過則 split（`raw_events_2026-02_part0.parquet` ...）。

### manifest.json

```json
{
  "month": "2026-02",
  "files": [
    {
      "name": "raw_events_2026-02.parquet",
      "sha256": "...",
      "row_count": 12345678,
      "size_bytes": 891234567,
      "min_ts": "2026-02-01T00:00:00Z",
      "max_ts": "2026-02-28T23:59:59Z"
    }
  ],
  "schema_version": "v1",
  "exported_at": "2026-03-01T03:00:00Z",
  "exporter_version": "raw_archive_export 1.0.0"
}
```

---

## 5. 冷層 NAS 歸檔規格

### 5.1 觸發時機

每月 1 號 03:00，掃描溫層中**滿 12 個月**的 partition，整包搬 NAS：

```
nas://soc_archive/2025-05/
  raw_events_2025-05.parquet
  raw_events_2025-05.manifest.json
  schema.md
  README_how_to_read.md         # 5 年後讀檔 SOP（每包都附一份）
```

### 5.2 README_how_to_read.md 內容（每包都附）

每份歸檔目錄獨立可讀，不依賴外部文件：

- 檔案清單與用途
- 欄位字典（schema.md 摘要）
- payload_format 各值的 schema 連結（OCSF 1.x / CEF / syslog RFC 等公開規範）
- 三種讀檔方式範例：
  - DuckDB: `SELECT * FROM read_parquet('raw_events_2025-05.parquet') LIMIT 10`
  - Python pandas: `pd.read_parquet(...)`
  - Apache Arrow CLI
- checksum 驗證指令
- 聯絡窗口（本系統維運 owner，5 年內 SOP 變更時更新）

**核心理念**：5 年後不論是哪位工程師、用什麼工具，打開 README 就知道怎麼讀。不依賴本專案的 wiki / Confluence / 公司內部資源（這些 5 年內極可能消失）。

### 5.3 搬移完成的責任移交

- 搬完後本系統發 email 給檔案管理部門 + 留 `archive_handover.log`
- 本系統 ClickHouse 與本機 `/var/raw_archive/` **清掉該月資料**
- 之後任何查舊資料的需求 → 走 NAS（本系統提供「locator → NAS 路徑」轉換工具）

---

## 6. 查詢介面（給 Platform 案件詳情頁用）

對應 v2 契約 §3 的反向通道，sec-vm 上跑：

```
GET /api/raw_query?locator=<locator>
```

實作邏輯：

1. 解析 locator 取得 `incident_id` 與 `ts` 範圍
2. 依時間判斷查熱 / 溫 / 冷層：
   - < 90 天 → ClickHouse SELECT
   - 91 天 ~ 1 年 → DuckDB 查 `/var/raw_archive/`
   - \> 1 年 → 回 `410 Gone` + NAS 路徑提示，由人工到 NAS 取
3. 回傳統一 JSON 格式（v2 契約 §3.3）

---

## 7. 容量與資源估算

假設來源混合後 **平均事件大小 2 KB（壓縮前）/ 500 B（ZSTD 後）**：

| 規模 | 熱層（90 天） | 溫層（1 年） | 5 年總量 |
|---|---|---|---|
| 1 萬事件/日 | ~1.4 GB | ~5.5 GB | ~27 GB |
| 10 萬事件/日 | ~14 GB | ~55 GB | ~270 GB |
| 100 萬事件/日 | ~140 GB | ~550 GB | ~2.7 TB |

sec-vm 端只需扛熱+溫，**不超過 100 GB** 對 VM 完全可接受。5 年總量丟 NAS 也不算大。

---

## 8. 待決策

1. **sec-vm VM 磁碟規劃**：需保留多少給 raw_archive？建議 100 GB 起跳
2. **NAS 路徑與帳號**：歸檔目標 SMB / NFS？掛載點？寫入帳號權限範圍？
3. **單一資料量上限**：單 incident 的 related_events 超過 N 筆（例 10000）時要不要拆？避免單一 incident 的 payload 撐爆查詢
4. **schema 演進**：未來新增 source 是否一律走「新增欄位 nullable」？舊 Parquet 不回填，新查詢工具相容處理
5. **email 類資料的 PII**：email 內文常含 PII，要在 Layer 1 parser 就遮罩，還是 raw 全存（合規風險）？建議遮罩後再進 store

---

## 9. 與既有系統的關係

- **不取代** Platform 端的 `od_intake_events` 表（v2 後該表只留 incident metadata，不再存原文）
- **不取代** sec-vm 既有的 ClickHouse（若已有，本 spec 是擴充 schema 而非另起）
- **不取代** NAS 上其他部門既有歸檔結構，只是新開一個 `soc_archive/` 目錄

---

## 10. SOC 人員使用分工（重要）

Platform 與 ClickHouse 不是「兩套都要熟」，而是**主從關係**：

| 場景 | 工具 | 比例 |
|---|---|---|
| 案件列表、簽核、處置決策 | **Platform UI（預設工作面）** | 95% |
| 案件詳情判斷不足時查原文 | Platform UI 的「查原文」按鈕（v2 §3 反向通道，UI 內嵌展開，不切環境） | 4% |
| 深度取證、跨案件關聯、稽核復盤 | 工程師親自 SSH sec-vm 寫 ClickHouse SQL | 1% |

設計原則：

- 值班人員只需熟 Platform UI，**不必懂 ClickHouse SQL**
- ClickHouse 直連權限**只給少數深度分析者**（最小授權）
- 反向通道 API 有 rate-limit 保護，防止 UI 用戶誤觸發爆量查詢拖垮 sec-vm（沿用 v2 §3.4 規格）
- 這條分工是避開「公司過去 ELK/Splunk 拉 SQL 鎖死」反模式的核心保障
