# TimeContext 架構討論紀錄

> 討論日期：2026-01-15
> 狀態：概念討論中，尚未實作

## 背景

BeakPlatform 定位為**跨系統整合中介平台**，用表單流程串接企業的行政和資安。

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
                         BeakPlatform（關聯分析 + 流程觸發）
```

### Kafka 角色

- Kafka 是串流訂閱，不是查詢
- 需要 **Kafka Consumer** 持續拉資料寫入 TimescaleDB
- 建議用 **Kafka Connect + JDBC Sink**（設定檔驅動，不用寫程式）
- BeakPlatform 只需要讀 TimescaleDB，不直接對接 Kafka

### 資料訂閱策略

- 不需要全量 log，只訂閱需要的 Kafka Topic
- 過濾在 Kafka 端做（ksqlDB 或預處理）
- BeakPlatform 只收精煉過的事件

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
├── beakplatform_dev（主庫）
│   └── users, work_schedules, cases...
└── beakplatform_ts（TimescaleDB 庫）
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
2. **從 SQL 讀** - 讀現有 BeakPlatform 資料送到 Kafka
3. **從 ELK 讀** - Elasticsearch API 查詢後轉送
4. **從檔案讀** - 讀 log 檔送進去

## 待討論問題

1. TimeContext 的具體欄位定義
2. 事件的標準化格式（統一訊息格式）
3. 與現有表單流程的整合方式
4. 權限控制（誰能查什麼時間範圍的資料）

---

*下次對話繼續：從安裝 TimescaleDB 開始驗證*

---

## 2026-09-03 起步實作（PF-229 第三期第 3 項）

上面的 TimescaleDB／Kafka 都還沒動，先把「給一個時間點 → 誰在值班、誰在假中」做成 Python service，
供之後的 open_defense 事件路由與簽核者解析呼叫。**尚未接上任何消費端**（那是另案），目前只有一支查詢 API。

| 項目 | 實作 |
|---|---|
| 唯一實作 | `backend/app/services/time_context_service.py::TimeContextService`：`who_on_duty(org, instant_utc)`、`who_on_leave(org, instant_utc)`、`snapshot(org, instant_utc)`。時間以 naive UTC 進出，當地換算只走 `app/utils/calendar_time.py` |
| 成員集合 | 同企業、啟用中、未刪除、非服務帳號、`user_type` ∈ EMPLOYEE／ORG_ADMIN；EXTERNAL／SYSTEM_ADMIN 不在時間軸上 |
| `who_on_duty` | 逐人 `ScheduleService.is_working_time()`（含時段級請假，所以在假中的人自然不在名單）。N+1，每人最多 3 個查詢；企業上限 50 人，起步可接受，要優化就批次化 `get_work_periods`，不要加快取 |
| `who_on_leave` | 兩個集合查詢：行事曆 LEAVE／TRIP 個人事件涵蓋這一刻（`source='calendar'`，`until_local`＝事件當地結束）∪ 當地日的人工 LEAVE 調整列（`calendar_event_secure_code IS NULL`，整天，`source='manual'`，`until_local`＝隔天 00:00）。**刻意不看 `schedule_adjustments.adjusted_periods`**：那是剩餘工作時段，沒有班表的企業底是 `[]`，判不出此刻在不在假中 |
| API | `GET /api/calendar/time-context?at=YYYY-MM-DDTHH:MM`（企業當地時間，省略＝現在），**`@admin_required` 專用**：`who_on_leave` 會揭露成員此刻在假中（含 PRIVATE 事件），對一般成員開放會繞過行事曆可見性規則 |
| 測試 | `backend/tests/test_time_context_service.py`（8 條：成員集合、事件期間內外、人工整天列、下班／週末、企業時區換算、snapshot 欄位、API 身分與 `at` 解析） |

實作脈絡：codex 派工兩次都因 OpenAI 端 404 失敗（無變更），由主 Claude 直接實作。

