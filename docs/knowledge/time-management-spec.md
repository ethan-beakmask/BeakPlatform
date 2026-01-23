# 時間管理機制設計規格

> 建立日期: 2026-01-07
> 狀態: 討論完成，待開發

---

## 一、核心概念

### 1.1 班表層級（由上到下覆蓋）

| 層級 | 說明 | 優先級 | 開發階段 |
|------|------|--------|----------|
| 個人排班 | 部門主管排班、調班 | 高 | 第二階段 |
| 共用班表 | 企業+地區+時區合併 | 低（基準） | 第一階段 |

### 1.2 逾時規則

| 規則 | 名稱 | 計算方式 | 說明 |
|------|------|----------|------|
| 規則1 | 絕對時間 | 關卡到達即倒數，24/7 | 緊急表單用，無視上下班 |
| 規則2 | 工作時間 | 僅在簽核者班表內倒數 | 一般表單用，符合人性 |

流程設計時可選：
- 僅規則1
- 僅規則2
- 雙軌制（任一觸發即逾時）

### 1.3 設計原則

1. **共用班表簡化設計**：企業+地區+時區合併為一表，每人選擇一個作為基準
2. **請假是當下狀態**：關卡到達時決定採用哪個規則，不回溯計算
3. **代理人機制**：規則2 的防呆，請假時可提前轉代理人
4. **系統級防呆**：監控規則2 超時異常，通知企業管理員

---

## 二、資料模型

### 2.1 共用班表 (WorkSchedule)

```sql
CREATE TABLE work_schedules (
    id SERIAL PRIMARY KEY,
    secure_code VARCHAR(32) NOT NULL UNIQUE,
    org_secure_code VARCHAR(32) NOT NULL,

    schedule_code VARCHAR(50) NOT NULL,        -- "TW-STANDARD", "JP-REMOTE"
    name VARCHAR(100) NOT NULL,                -- "台灣標準班表"
    timezone VARCHAR(50) NOT NULL,             -- "Asia/Taipei"

    -- 週間預設工時 JSON
    -- {"mon": ["09:00-12:00", "13:00-18:00"], "tue": [...], "sat": null, "sun": null}
    weekly_hours JSONB NOT NULL,

    is_default BOOLEAN DEFAULT FALSE,          -- 企業預設班表
    is_active BOOLEAN DEFAULT TRUE,
    description TEXT,

    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP,
    is_deleted BOOLEAN DEFAULT FALSE,
    deleted_at TIMESTAMP,

    UNIQUE(org_secure_code, schedule_code)
);

COMMENT ON TABLE work_schedules IS '共用班表（企業+地區+時區）';
COMMENT ON COLUMN work_schedules.weekly_hours IS '週間工時，key: mon/tue/wed/thu/fri/sat/sun，value: 時段陣列或 null（休息）';
```

### 2.2 班表假日 (ScheduleHoliday)

```sql
CREATE TABLE schedule_holidays (
    id SERIAL PRIMARY KEY,
    secure_code VARCHAR(32) NOT NULL UNIQUE,
    schedule_secure_code VARCHAR(32) NOT NULL REFERENCES work_schedules(secure_code),

    holiday_date DATE NOT NULL,
    holiday_type VARCHAR(20) NOT NULL,         -- HOLIDAY: 休假, WORKDAY: 補班

    -- 補班日的工作時段，HOLIDAY 時為 null
    -- ["09:00-12:00", "13:00-17:00"]
    work_periods JSONB,

    description VARCHAR(200),                  -- "中秋節", "補班日"

    created_at TIMESTAMP DEFAULT NOW(),
    is_deleted BOOLEAN DEFAULT FALSE,

    UNIQUE(schedule_secure_code, holiday_date)
);

COMMENT ON TABLE schedule_holidays IS '班表假日/補班日';
COMMENT ON COLUMN schedule_holidays.holiday_type IS 'HOLIDAY=休假, WORKDAY=補班';
```

### 2.3 用戶班表關聯

```sql
-- 在 users 表新增欄位
ALTER TABLE users ADD COLUMN work_schedule_secure_code VARCHAR(32)
    REFERENCES work_schedules(secure_code);

COMMENT ON COLUMN users.work_schedule_secure_code IS '用戶的共用班表，null 時使用企業預設';
```

### 2.4 逾時追蹤表 (TimeoutTracker)

```sql
CREATE TABLE timeout_trackers (
    id SERIAL PRIMARY KEY,
    secure_code VARCHAR(32) NOT NULL UNIQUE,
    org_secure_code VARCHAR(32) NOT NULL,

    -- 關聯表單流程
    form_instance_secure_code VARCHAR(32) NOT NULL,
    node_instance_secure_code VARCHAR(32) NOT NULL,
    assignee_secure_code VARCHAR(32) NOT NULL,  -- 簽核者

    -- 逾時設定
    timeout_mode VARCHAR(20) NOT NULL,          -- ABSOLUTE, WORKING, BOTH
    timeout_absolute_seconds INT,               -- 規則1 設定秒數
    timeout_working_seconds INT,                -- 規則2 設定秒數

    -- 計算狀態
    timeout_absolute_at TIMESTAMP,              -- 規則1 預計逾時時間
    remaining_working_seconds INT,              -- 規則2 剩餘工作秒數

    -- 請假標記（由請假流程寫入）
    on_leave BOOLEAN DEFAULT FALSE,
    on_leave_until TIMESTAMP,                   -- 請假結束時間

    -- 狀態
    status VARCHAR(20) DEFAULT 'PENDING',       -- PENDING, TIMEOUT, COMPLETED, TRANSFERRED
    timeout_triggered_at TIMESTAMP,             -- 實際逾時觸發時間

    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP,
    last_check_at TIMESTAMP,                    -- 排程最後檢查時間

    INDEX idx_timeout_status (status, timeout_absolute_at),
    INDEX idx_timeout_assignee (assignee_secure_code, status)
);

COMMENT ON TABLE timeout_trackers IS '逾時追蹤表';
COMMENT ON COLUMN timeout_trackers.on_leave IS '請假標記，由請假流程寫入';
COMMENT ON COLUMN timeout_trackers.status IS 'PENDING=等待中, TIMEOUT=已逾時, COMPLETED=已簽核, TRANSFERRED=已轉代理';
```

---

## 三、開發階段

### 第一階段：時間表功能（企業管理員/人資）

**功能清單：**

1. **共用班表管理** `/admin/settings/work-schedules`
   - 班表 CRUD
   - 時區選擇
   - 週間工時設定（視覺化編輯器）
   - 設定企業預設班表

2. **班表假日管理** `/admin/settings/work-schedules/<code>/holidays`
   - 假日 CRUD
   - 補班日設定
   - 年度假日批次匯入（CSV/JSON）

3. **用戶班表指定**
   - 用戶編輯頁新增班表選擇欄位
   - 批次設定部門/職務預設班表

4. **逾時追蹤系統**
   - TimeoutTracker 資料表
   - 關卡到達時寫入邏輯（整合 WorkflowEngine）
   - 排程批次檢查（建議每分鐘）
   - 逾時觸發動作（通知/子流程）

5. **系統級防呆工具**
   - 掃描規則2 且超過 n 小時的表單
   - 掃描關卡到達後請假的簽核者
   - 通知企業管理員
   - 可配置警告閾值（預設 24 小時）

### 第二階段：排班功能（部門主管）

**功能清單：**

1. **班次定義** `/admin/settings/shifts`
   - 班次 CRUD（早班、中班、晚班...）
   - 班次時段設定

2. **個人排班** `/admin/scheduling`
   - 月曆視圖
   - 拖拉排班
   - 班表範本套用

3. **調班申請**
   - 調班表單
   - 主管審核

### 第三階段：請假整合（用戶設計）

**整合點：**

1. **請假單欄位**
   - 請假開始時間
   - 請假結束時間
   - 請假類型

2. **請假流程動作**
   - 請假核准後，寫入 TimeoutTracker.on_leave 標記
   - 更新 on_leave_until 時間
   - 觸發代理人轉移檢查

---

## 四、逾時計算流程

### 4.1 關卡到達時

```python
def on_node_reached(node_instance, assignee):
    """簽核關卡到達時，寫入逾時追蹤"""

    node_config = node_instance.node_definition.config
    timeout_mode = node_config.get('timeout_mode')  # ABSOLUTE, WORKING, BOTH

    if not timeout_mode:
        return  # 無逾時設定

    tracker = TimeoutTracker(
        form_instance_secure_code=node_instance.form_instance_secure_code,
        node_instance_secure_code=node_instance.secure_code,
        assignee_secure_code=assignee.secure_code,
        timeout_mode=timeout_mode,
        status='PENDING',
        created_at=now()
    )

    # 規則1：絕對時間
    if timeout_mode in ('ABSOLUTE', 'BOTH'):
        seconds = node_config.get('timeout_absolute_seconds')
        tracker.timeout_absolute_seconds = seconds
        tracker.timeout_absolute_at = now() + timedelta(seconds=seconds)

    # 規則2：工作時間
    if timeout_mode in ('WORKING', 'BOTH'):
        seconds = node_config.get('timeout_working_seconds')
        tracker.timeout_working_seconds = seconds
        tracker.remaining_working_seconds = seconds

    # 檢查當下是否請假中
    if is_on_leave(assignee, now()):
        tracker.on_leave = True
        tracker.on_leave_until = get_leave_end_time(assignee)

    db.session.add(tracker)
    db.session.commit()
```

### 4.2 排程批次檢查

```python
def check_timeouts():
    """排程：每分鐘檢查逾時"""

    pending = TimeoutTracker.query.filter_by(status='PENDING').all()

    for tracker in pending:
        is_timeout = False

        # 規則1 檢查
        if tracker.timeout_absolute_at:
            if now() >= tracker.timeout_absolute_at:
                is_timeout = True

        # 規則2 檢查
        if tracker.remaining_working_seconds is not None:
            # 計算從上次檢查到現在的「工作秒數」
            assignee = get_user(tracker.assignee_secure_code)
            work_seconds = calculate_working_seconds(
                assignee,
                tracker.last_check_at or tracker.created_at,
                now()
            )
            tracker.remaining_working_seconds -= work_seconds

            if tracker.remaining_working_seconds <= 0:
                is_timeout = True

        tracker.last_check_at = now()

        if is_timeout:
            trigger_timeout_action(tracker)
            tracker.status = 'TIMEOUT'
            tracker.timeout_triggered_at = now()

    db.session.commit()
```

### 4.3 計算工作秒數

```python
def calculate_working_seconds(user, start_time, end_time):
    """計算兩個時間點之間的工作秒數"""

    schedule = get_user_schedule(user)  # 取得用戶班表
    total_seconds = 0

    current = start_time
    while current < end_time:
        day_end = min(end_of_day(current), end_time)

        # 取得當日工作時段
        work_periods = get_work_periods(schedule, current.date())

        for period_start, period_end in work_periods:
            # 計算重疊時間
            overlap_start = max(current, period_start)
            overlap_end = min(day_end, period_end)

            if overlap_start < overlap_end:
                total_seconds += (overlap_end - overlap_start).total_seconds()

        current = start_of_next_day(current)

    return total_seconds
```

---

## 五、系統級防呆

### 5.1 監控項目

| 項目 | 條件 | 動作 |
|------|------|------|
| 規則2 超時警告 | 僅規則2 且超過 n 小時未簽核 | 通知企業管理員 |
| 請假衝突檢查 | 關卡到達後簽核者請假 | 通知 + 建議轉代理人 |
| 永不逾時偵測 | 規則2 剩餘時間長期不減少 | 通知企業管理員 |

### 5.2 配置參數

```python
SYSTEM_TIMEOUT_WARNINGS = {
    'working_time_max_hours': 24,      # 規則2 最大容忍小時數
    'leave_conflict_check': True,      # 啟用請假衝突檢查
    'check_interval_minutes': 5,       # 系統級檢查間隔
}
```

---

## 六、流程節點設定

### 6.1 簽核節點新增欄位

```json
{
  "node_type": "APPROVE",
  "config": {
    "timeout_mode": "BOTH",
    "timeout_absolute_seconds": 1800,
    "timeout_working_seconds": 7200,
    "timeout_action": {
      "type": "NOTIFICATION",
      "targets": ["ASSIGNEE", "ADMIN"],
      "channels": ["EMAIL", "TELEGRAM"]
    },
    "timeout_escalation": {
      "enabled": true,
      "transfer_to_deputy": true,
      "run_subflow": "timeout-handler"
    }
  }
}
```

---

## 七、待確認事項

1. **週間工時編輯器 UI**：純文字輸入 vs 視覺化時間軸拖拉
2. **假日批次匯入格式**：CSV 欄位定義
3. **逾時動作擴充**：除了通知和子流程，還需要什麼？
4. **排程執行方式**：Celery / APScheduler / 系統 cron

---

## 八、相關文件

- `docs/knowledge/frontend-pitfalls.md` - 前端開發陷阱
- `docs/knowledge/flask-security-checklist.md` - Flask 安全檢查清單
- 表單流程模組：`backend/app/models/form_workflow/`

---

*文件版本: v1.0*
*最後更新: 2026-01-07*
