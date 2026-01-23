# TimeContext 架構討論紀錄

> 討論日期：2026-01-15
> 狀態：概念討論中，尚未實作

## 背景

BeakMask 定位為**跨系統整合中介平台**，用表單流程串接企業的行政和資安。

「時間」是「人事時地物」五大元素中唯一形而上的抽象，需要設計統一的管理方式。

## 問題描述

不同系統各自有時間概念，但彼此不對話：

```
[SIEM] 10:03:45 告警 ──────────────────── 誰該處理？
[HR系統] 張三今天請假 ─────────────────── 所以不是他
[班表] 10:00-18:00 李四值班 ───────────── 應該是李四
[專案] 李四正在處理客戶A的案子 ─────────── 但他正忙
```

需求：給定一個時間點，能查出當下的「世界快照」。

## 時間物件分類

| 類型 | 來源 | 特性 | 例子 |
|------|------|------|------|
| **事件時間** | 系統 log | 精確時間戳、被動產生 | 登入 10:03:45、設備告警 |
| **規劃時間** | 班表/排班 | 時段區間、週期性 | 09:00-18:00 週一到五 |
| **權益時間** | 年休/特休 | 額度、到期日 | 年假 14 天、補休 8 小時 |
| **專案時間** | 專案管理 | 預估/實際、里程碑 | Sprint 2 週、交付日 |

## 架構設計

### 兩層架構

**第一層：狀態表（State Tables）** - 存「時間段」的狀態

```sql
-- 班表狀態（時間段）
work_schedules: user_id, start_time, end_time, status
-- 請假狀態（時間段）
leaves: user_id, start_time, end_time, type
-- 資產狀態（時間段，有變化才新增一筆）
asset_status: asset_id, valid_from, valid_to, status
```

**第二層：事件表（Event Log）** - 存精確時間戳的事件

```sql
-- 統一事件格式
time_events (
    id,
    occurred_at TIMESTAMPTZ,  -- 精確時間
    source_system,            -- SIEM, HR, PROJECT...
    event_type,
    entity_type,              -- user, asset, case...
    entity_id,
    payload JSONB
)
```

### TimeContext（時間情境）

**不是 PostgreSQL 內建功能**，是應用層抽象概念。

```
TimeContext
├── instant: 2026-01-14T10:03:45+08:00
├── who_on_duty: [李四, 王五]
├── who_on_leave: [張三]
├── active_assets: [firewall-01, db-prod]
├── active_cases: [CASE-2026-0042]
└── computed_at: (查詢當下產生)
```

**實現方式**：
- PostgreSQL Function（接受時間參數，返回 JSONB）
- Python Service 層（跨表查詢後組裝）
- 不需要預存，查詢時即時組裝

## 技術架構

### 目標架構

```
Log 來源 → Kafka（緩衝 3 天）→ TimescaleDB
                              ↓
                         BeakMask（關聯分析 + 流程觸發）
```

### Kafka 角色

- Kafka 是串流訂閱，不是查詢
- 需要 **Kafka Consumer** 持續拉資料寫入 TimescaleDB
- 建議用 **Kafka Connect + JDBC Sink**（設定檔驅動，不用寫程式）
- BeakMask 只需要讀 TimescaleDB，不直接對接 Kafka

### 資料訂閱策略

- 不需要全量 log，只訂閱需要的 Kafka Topic
- 過濾在 Kafka 端做（ksqlDB 或預處理）
- BeakMask 只收精煉過的事件

### 儲存策略

| 資料類型 | 儲存策略 | 原因 |
|----------|----------|------|
| 告警事件 | 落地 TimescaleDB | 事後追溯、報表、合規 |
| 即時比對結果 | 記憶體處理 | 比對完觸發動作就丟 |
| 聚合統計 | 落地 | 但只存聚合結果，不存原始 |

### 資料庫架構

**建議起步方案：同一個 PostgreSQL 實例**

```
PostgreSQL 實例
├── beakmask_dev（主庫）
│   └── users, work_schedules, cases...
└── beakmask_ts（TimescaleDB 庫）
    └── time_events (hypertable)
```

優點：可直接 JOIN，TimeContext 組裝簡單

等資料量大到影響主庫效能，再拆分實例 + FDW。

## 硬體評估（這台 VM）

| 資源 | 現況 | 結論 |
|------|------|------|
| CPU | 4 核 Xeon | ✅ 開發測試夠用 |
| RAM | 12GB（可用 7.7GB） | ✅ 勉強夠 |
| Disk | 31GB 可用 | ⚠️ 測試夠，生產不夠 |

可以 All-in-One 安裝 TimescaleDB + Kafka 做開發測試。

## 下一步驗證計畫

```
第一步：裝 TimescaleDB（PostgreSQL 擴展）
        ↓
第二步：建 hypertable，手動塞測試資料
        ↓
第三步：確認 TimeContext 查詢邏輯可行
        ↓
第四步：裝 Kafka（Docker 單節點）
        ↓
第五步：Python 假資料 → Kafka → TimescaleDB
        ↓
第六步：驗證完整流程
```

## 測試資料方案

公司前端 log 申請麻煩，可用以下方式取得測試資料：

1. **Python 產生假資料** - 用 Faker 產生模擬 log
2. **從 SQL 讀** - 讀現有 BeakMask 資料送到 Kafka
3. **從 ELK 讀** - Elasticsearch API 查詢後轉送
4. **從檔案讀** - 讀 log 檔送進去

## 待討論問題

1. TimeContext 的具體欄位定義
2. 事件的標準化格式（統一訊息格式）
3. 與現有表單流程的整合方式
4. 權限控制（誰能查什麼時間範圍的資料）

---

*下次對話繼續：從安裝 TimescaleDB 開始驗證*
