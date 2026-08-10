# 統一 Raw Store + NAS 歸檔架構規格

**版本**: v1.0-draft
**建立**: 2026-05-13
**狀態**: **§8 的五個待決策已於 2026-08-10 全部拍板（見 §8）**，剩餘為實作
**最後現況對齊**: 2026-08-10（見 §0、§0.5）
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

**分界（2026-08-10 定）**：
form_data 扁平化負責「這一件案子的原文」，raw store 負責
「跨案件、跨資料源、跨時間的原文」。兩者不重複建設——
案件詳情頁的「事件明細」分頁讀 form_data（免網路往返、離線可讀），
「查原文」按鈕才走 §6 反向通道。

---

## 0.5 `.20` 實地量測（2026-08-10，取代 §7 的紙上估算）

用戶授權後實際登入 `.20` 取得，**這些數字是 §8 決策的依據**：

| 項目 | 實測值 | 與本規格假設的差異 |
|---|---|---|
| VM 磁碟 | `sda` 300G，`ubuntu-vg` **VFree 198G**，root LV 只切 100G（用 35G，38%） | §8.1 的「100 GB 起跳」**不需要動 VM 硬體**，`lvextend` 即可 |
| `secstack.events` 現量 | **2329 列 / 333.41 KiB on disk** | §7 估算表最小級距是「1 萬事件/日 → 90 天 1.4 GB」。實際量比該級距**低三個數量級** |
| 熱層 TTL | `TTL event_time + INTERVAL 180 DAY`（無 volume 搬移） | 本規格 §2/§3 寫 90 天。**以現況 180 天為準**，90 天改為「溫層轉檔門檻的建議下限」 |
| 壓縮 | `raw String CODEC(ZSTD(7))`、時間欄 `Delta + ZSTD(3)` | 已與 §3 的「payload 一律 ZSTD」一致 |
| 分區 | `PARTITION BY toYYYYMMDD(event_time)`（日分區） | §3 草案寫 `toYYYYMM`（月分區）。**以現況日分區為準**，溫層仍按月打包 |
| NAS | `mount` / `/etc/fstab` / `.env` 皆無 cifs / nfs / smb | §5 的 `nas://` 目標在 `.20` 上**不存在**，見 §8.2 決議 |

**結論：容量在可預見的將來不是瓶頸**，§7 的估算表留作規模成長後的參考，
不要拿它當現在的採購或配額依據。

---

## 1. 設計目標

| 目標 | 動機 |
|---|---|
| **跨資料源統一儲存** | OD intake / ELK / Splunk export / email / csv / xlsx / MariaDB / SQLite / JSON 全部歸到同一個 store，案件詳情頁查原文只要一個 API |
| **熱資料快查** | 案件詳情頁需 < 3 秒查到原文（最近 180 天案件最多被查） |
| **5 年保存** | 公司規定，但實際冷資料可離線 |
| **5 年後仍可讀** | 不被特定產品綁死，匯出格式必須 self-describing |
| **責任分層** | NAS 歸檔後由其他部門保管，本系統只負責「查得到、讀得出」 |

---

## 2. 三層儲存

```
┌─ 熱層（ClickHouse, on sec-vm）────────────┐
│  最近 180 天，案件詳情頁查詢用             │
│  表: secstack.events（見 §3.1，已存在）    │
└────────────────┬───────────────────────────┘
                 │ 180 天後轉檔（TTL 到期前匯出）
                 ▼
┌─ 溫層（Parquet, on sec-vm 本機）───────────┐
│  181 天 ~ 1 年，按月 partition             │
│  路徑: /var/raw_archive/YYYY-MM/*.parquet  │
│  仍可用 DuckDB / ClickHouse external 查詢  │
└────────────────┬───────────────────────────┘
                 │ 1 年後自動匯出
                 ▼
┌─ 冷層（過渡: .16 的 /mnt/smb；未來 NAS）───┐
│  1 年 ~ 5 年，Parquet + manifest + SOP     │
│  路徑: /mnt/smb/soc_archive/YYYY-MM/       │
│  （NAS 就緒後 → nas://soc_archive/YYYY-MM/）│
└────────────────────────────────────────────┘
```

熱→溫→冷三段保留各自的查詢能力，**冷層不要求即時查**，調舊資料時用 DuckDB 開檔即可。

**保留天數以 `.20` 現況 180 天為準**（§0.5）。原草案寫 90 天，
改動 TTL 會讓現有資料提早消失，沒有理由為了對齊文件而縮短保存期。

---

## 3. 熱層 ClickHouse Schema

> **2026-08-10：本節的 `raw_events` 是 2026-05-13 的草案，`.20` 上並不存在。**
> 實際運作的是 `secstack.events`（見 §3.1），欄位語意已覆蓋本草案的九成。
> **不要照本節建新表**，剩餘工作只有「補 `incident_id`」一項。
> 本草案保留供對照命名差異。

### 3.1 `.20` 現行表（實查，這才是實作依據）

```sql
CREATE TABLE secstack.events (
    event_time      DateTime64(3,'UTC') CODEC(Delta(8), ZSTD(3)),
    ingested_at     DateTime64(3,'UTC') DEFAULT now64() CODEC(Delta(8), ZSTD(3)),
    correlation_id  String CODEC(ZSTD(3)),
    source_system   LowCardinality(String),
    event_class     LowCardinality(String),
    severity_id     UInt8,
    confidence      UInt8 DEFAULT 0,
    actor_ip        IPv6,
    actor_asn       UInt32 DEFAULT 0,
    actor_country   FixedString(2) DEFAULT '\0\0',
    actor_ua        String CODEC(ZSTD(3)),
    target_host     String CODEC(ZSTD(3)),
    target_url      String CODEC(ZSTD(3)),
    target_service  LowCardinality(String),
    finding_title   String CODEC(ZSTD(3)),
    finding_rule_id String CODEC(ZSTD(3)),
    finding_rule_set LowCardinality(String),
    raw             String CODEC(ZSTD(7))
) ENGINE = MergeTree
PARTITION BY toYYYYMMDD(event_time)
ORDER BY (event_class, source_system, event_time, correlation_id)
TTL toDateTime(event_time) + toIntervalDay(180);
```

| 本草案欄位 | `secstack.events` 對應 | 備註 |
|---|---|---|
| `ts` | `event_time` | 命名不同，語意相同 |
| `payload` | `raw` | 同樣 ZSTD |
| `payload_format` | **無** | 目前單一格式，需要時再加 |
| `rule_id` | `finding_rule_id` | |
| `source` | `source_system` | |
| `incident_id` | **無** | **唯一實質缺口**，見 §3.2 |

### 3.2 唯一待補：`incident_id`

v2 契約 §2.2 的 `related_locators` 要能解析回原文，前提是熱層有 incident 維度。

```sql
ALTER TABLE secstack.events ADD COLUMN incident_id String CODEC(ZSTD(3)) AFTER correlation_id;
```

寫入端（Vector 或 od-bridge 的 Layer 4 聚合層）在聚合時一併填入。
**這是 `.20` 側工作**，權威文件 `/opt/Ethan_Lab/ITHome-2026/CLAUDE.md`。
`ORDER BY` 不動（改排序鍵要重建表，代價遠大於收益；`incident_id` 用
`WHERE` + 日分區裁剪已足夠，現量 2329 列更不成問題）。

### 3.3 原始草案（2026-05-13，僅供對照）

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

草案的設計重點，以及它們在現行表上的落實情況：

| 草案重點 | `secstack.events` 現況 |
|---|---|
| payload 一律 ZSTD 壓縮 | 已落實（`raw` 用 ZSTD(7)，比草案的 6 更高） |
| 常查欄位拉出來建索引 | 已落實，`ORDER BY (event_class, source_system, event_time, correlation_id)` |
| `payload_format` 標記 | **未落實**，目前單一格式。引入第二種 payload 格式時再加 |
| TTL 自動搬 volume | **未落實**，現行 TTL 是**直接刪除**——所以溫層匯出必須排程，見 §4 |

### 寫入路徑

Layer 1 parser → 統一 dict → 寫入 **`secstack.events`**（一個 source 一條 INSERT，批次 1000 筆）。
現行寫入端是 `.20` 的 Vector（`timberio/vector:0.41.1-alpine`）。

---

## 4. 溫層 Parquet 規格

ClickHouse 180 天 TTL 到期**前**，**每月 partition 由 cron 匯出為 Parquet**：

**順序是硬性的**：`secstack.events` 的 TTL 是直接刪除（無 `TO VOLUME`），
匯出排程必須在資料被 TTL 清掉之前跑完，否則就是永久遺失。
匯出腳本要先確認目標月份的 `max(event_time)` 距今 < 180 天才動手。

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

## 5. 冷層歸檔規格

> **2026-08-10 決議：公司 NAS 資訊未定，改用過渡歸檔目標，`nas://` 語意不變。**
> `.20` 上沒有任何 NAS 掛載，`.16` 已掛著 `//192.168.0.10/SMB`（327G，可用 106G）。
> 冷層先落在該處，NAS 就緒後**只換掛載點，目錄結構與 SOP 一字不改**。

### 5.0 過渡期歸檔目標與搬運路徑

```
[.20 溫層]                       [.16]                    [Windows 192.168.0.10]
/var/raw_archive/YYYY-MM/  ──rsync over ssh──►  /mnt/smb/soc_archive/YYYY-MM/
                             (.16 排程拉取)        （= D:\Server\SMB\soc_archive）
```

**由 `.16` 主動拉取，不在 `.20` 上新增 SMB 掛載與憑證**——
`.20` 是對外暴露面較大的那台，少一組憑證少一分風險，
且 `.16` 本來就掛好了 `/mnt/smb`（fstab，`nofail`，憑證在 `/etc/smb-credentials`）。

過渡方案的三個已知限制，實作時必須處理：

1. **`/mnt/smb` 是使用者 Windows 的共享，關機即不可寫**。
   fstab 用 `nofail`，開機掛不上會**靜默變成本機空目錄**——
   歸檔腳本必須先 `df /mnt/smb` 或檢查 magic file 確認真的掛著，
   **掛不上一律中止並告警，不可寫進本機空目錄後就刪掉 `.20` 上的來源**
2. **搬完不立即刪來源**。§5.3 的「清掉該月資料」在過渡期改為
   **校驗 sha256 通過後才刪**，且保留一個月緩衝
3. 這不是異地備援等級的保存，**只是 NAS 就緒前不讓資料堆在 `.20`**。
   真正的 5 年保存責任在拿到 NAS 之後才成立

### 5.1 觸發時機

每月 1 號 03:00，掃描溫層中**滿 12 個月**的 partition，整包搬冷層：

```
/mnt/smb/soc_archive/2025-05/          # NAS 就緒後 → nas://soc_archive/2025-05/
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
- 之後任何查舊資料的需求 → 走冷層（本系統提供「locator → 歸檔路徑」轉換工具）

**過渡期（NAS 未就緒）例外**：無檔案管理部門可移交，
`archive_handover.log` 仍留但 email 收件者改為本系統維運 owner；
刪來源改為 §5.0 的「sha256 校驗通過 + 一個月緩衝」。

---

## 6. 查詢介面（給 Platform 案件詳情頁用）

**狀態：2026-08-10 拍板要做**（v2 契約 §0.6 第 6/7 項），
部署方式定案為 **`.20` 上 nginx + Flask，平台端不直連 ClickHouse**。

對應 v2 契約 §3 的反向通道，sec-vm 上跑：

```
GET /api/raw_query?locator=<locator>
```

實作邏輯：

1. 解析 locator（格式 `raw_events/<YYYY-MM-DD>/<incident_id>`，見 v2 §0.6 第 3 項）
   取得 `incident_id` 與日期
2. 依時間判斷查熱 / 溫 / 冷層：
   - < 180 天 → ClickHouse `SELECT ... WHERE incident_id = ?`（需先完成 §3.2）
   - 181 天 ~ 1 年 → DuckDB 查 `/var/raw_archive/`
   - \> 1 年 → 回 `410 Gone` + 冷層路徑提示，由人工取
3. 回傳統一 JSON 格式（v2 契約 §3.3）

平台端的消費者是案件詳情頁的「查原文」按鈕（v2 遷移計畫 Phase 3b）。
`.20` 不可達時**不阻塞案件流轉**（v2 §3.5）。

---

## 7. 容量與資源估算

假設來源混合後 **平均事件大小 2 KB（壓縮前）/ 500 B（ZSTD 後）**：

| 規模 | 熱層（表列按 90 天算；現行 TTL 180 天需 ×2） | 溫層（1 年） | 5 年總量 |
|---|---|---|---|
| 1 萬事件/日 | ~1.4 GB | ~5.5 GB | ~27 GB |
| 10 萬事件/日 | ~14 GB | ~55 GB | ~270 GB |
| 100 萬事件/日 | ~140 GB | ~550 GB | ~2.7 TB |

sec-vm 端只需扛熱+溫，**不超過 100 GB** 對 VM 完全可接受。5 年總量丟 NAS 也不算大。

**2026-08-10 實測校正**：`.20` 現有 2329 列 / 333 KiB，
比上表最小級距低三個數量級。上表是規模成長後的參考，**不是現在的配額依據**（見 §0.5）。

---

## 8. 決策點（2026-08-10 全部結案）

**本節已無待決事項。** 決策依據見 §0.5 的 `.20` 實地量測。

### 8.1 sec-vm 磁碟配額 → **不預先切，用 LVM 餘裕按需擴**

`ubuntu-vg` 有 **198 GB VFree**，root LV 只切了 100 GB。
現階段資料量（333 KiB）離 100 GB 極遠，預先切一個空的
`/var/raw_archive` LV 只是把空間鎖死。

實作方式：溫層先用 root LV 下的 `/var/raw_archive/`；
**當 root 使用率超過 70% 時，`lvextend -L +100G` 再 `resize2fs`**（線上可做，不需停機）。
監控門檻寫進歸檔腳本的前置檢查。

### 8.2 NAS 路徑與帳號 → **過渡：`.16` 的 `/mnt/smb/soc_archive/`**

`.20` 上零 NAS 掛載，公司 NAS 資訊未取得。
改由 `.16` rsync 拉取後落 `/mnt/smb`，完整規格與三個限制見 §5.0。
**NAS 就緒後只換掛載點**，目錄結構、manifest、README SOP 全部不變。

### 8.3 單 incident 事件數上限 → **10000 筆，超過則拆包**

超過 10000 筆的 incident，`related_locators` 拆成多個 locator，
每個 locator 最多指向 10000 筆，命名 `<incident_id>#0` / `#1`。
反向通道（v2 §3）的 `limit` 預設 100、上限 1000，
回應的 `truncated: true` 即代表還有下一頁。

**現況下不會觸發**（總共 2329 列），這條是預防性上限，
目的是讓「單一 incident 撐爆查詢」在架構上不可能發生，而不是現在要做的事。

### 8.4 schema 演進 → **一律新增 nullable 欄位，不改既有欄位語意**

- 新 source 需要新欄位時：`ALTER TABLE ... ADD COLUMN <name> <type> DEFAULT <零值>`
- **禁止**改既有欄位的型別或語意（舊 Parquet 無法回填，會讓歷史資料讀出錯誤語意）
- 每次變更 bump `manifest.json` 的 `schema_version`，並在該月 `schema.md` 記錄差異
- 舊 Parquet 不回填；讀取工具遇到缺欄位視為 NULL

### 8.5 email 類資料的 PII → **raw 全存，不在 Layer 1 遮罩**

用戶 2026-08-10 定調：

> 資安人員要有足夠的資訊才方便處理案件，備份也該完整備份，
> 所以資安相關的功能應先提供足夠資料，至於是否看見太多或備份都是其他的議題。

因此本規格**只負責完整保存**。「誰看得到多少」屬於存取控制議題，
落在 ClickHouse 帳號最小授權與反向通道（v2 §3）的輸出控制，
**不在本規格範圍內展開**，也不因此在寫入路徑加遮罩。

---

## 9. 與既有系統的關係

- **不取代** Platform 端的 `od_intake_events` 表（v2 後該表只留 incident metadata，不再存原文）
- **不取代** sec-vm 既有的 ClickHouse。2026-08-10 已確認 `secstack.events` 存在且
  語意相符，本 spec 是**擴充該表（補 `incident_id`）而非另起**，見 §3.1／§3.2
- **不取代** 冷層目標上其他部門既有歸檔結構，只是新開一個 `soc_archive/` 目錄

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
