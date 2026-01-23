-- 009_time_management.sql
-- 時間管理機制：共用班表、班次定義、個人排班、排班調整
-- 建立日期: 2026-01-07

-- ============================================
-- 1. 共用班表 (WorkSchedule)
-- ============================================
CREATE TABLE IF NOT EXISTS work_schedules (
    id SERIAL PRIMARY KEY,
    secure_code VARCHAR(32) NOT NULL UNIQUE,
    org_secure_code VARCHAR(32) NOT NULL REFERENCES organizations(secure_code),

    schedule_code VARCHAR(50) NOT NULL,
    name VARCHAR(100) NOT NULL,
    timezone VARCHAR(50) NOT NULL DEFAULT 'Asia/Taipei',

    -- 週間預設工時 JSON
    -- {"mon": ["09:00-12:00", "13:00-18:00"], "tue": [...], "sat": null, "sun": null}
    weekly_hours JSONB NOT NULL DEFAULT '{}',

    is_default BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE,
    description TEXT,

    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    is_deleted BOOLEAN DEFAULT FALSE,
    deleted_at TIMESTAMP,

    UNIQUE(org_secure_code, schedule_code)
);

CREATE INDEX idx_work_schedules_org ON work_schedules(org_secure_code);
CREATE INDEX idx_work_schedules_default ON work_schedules(org_secure_code, is_default) WHERE is_default = TRUE;

COMMENT ON TABLE work_schedules IS '共用班表（企業+地區+時區）';
COMMENT ON COLUMN work_schedules.schedule_code IS '班表代碼，如 TW-STANDARD, JP-REMOTE';
COMMENT ON COLUMN work_schedules.timezone IS '時區，如 Asia/Taipei, Asia/Tokyo';
COMMENT ON COLUMN work_schedules.weekly_hours IS '週間工時，key: mon/tue/wed/thu/fri/sat/sun，value: 時段陣列或 null（休息）';
COMMENT ON COLUMN work_schedules.is_default IS '是否為企業預設班表';

-- ============================================
-- 2. 班表假日 (ScheduleHoliday)
-- ============================================
CREATE TABLE IF NOT EXISTS schedule_holidays (
    id SERIAL PRIMARY KEY,
    secure_code VARCHAR(32) NOT NULL UNIQUE,
    schedule_secure_code VARCHAR(32) NOT NULL REFERENCES work_schedules(secure_code),

    holiday_date DATE NOT NULL,
    holiday_type VARCHAR(20) NOT NULL,  -- HOLIDAY: 休假, WORKDAY: 補班

    -- 補班日的工作時段，HOLIDAY 時為 null
    work_periods JSONB,

    description VARCHAR(200),

    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    is_deleted BOOLEAN DEFAULT FALSE,
    deleted_at TIMESTAMP,

    UNIQUE(schedule_secure_code, holiday_date)
);

CREATE INDEX idx_schedule_holidays_schedule ON schedule_holidays(schedule_secure_code);
CREATE INDEX idx_schedule_holidays_date ON schedule_holidays(holiday_date);

COMMENT ON TABLE schedule_holidays IS '班表假日/補班日';
COMMENT ON COLUMN schedule_holidays.holiday_type IS 'HOLIDAY=休假, WORKDAY=補班';
COMMENT ON COLUMN schedule_holidays.work_periods IS '補班日的工作時段，如 ["09:00-12:00", "13:00-17:00"]';

-- ============================================
-- 3. 班次定義 (ShiftType)
-- ============================================
CREATE TABLE IF NOT EXISTS shift_types (
    id SERIAL PRIMARY KEY,
    secure_code VARCHAR(32) NOT NULL UNIQUE,
    org_secure_code VARCHAR(32) NOT NULL REFERENCES organizations(secure_code),

    shift_code VARCHAR(20) NOT NULL,
    name VARCHAR(50) NOT NULL,
    work_periods JSONB NOT NULL,  -- ["08:00-16:00"]
    color VARCHAR(7),  -- "#4CAF50" 月曆顯示色

    sort_order INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE,

    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    is_deleted BOOLEAN DEFAULT FALSE,
    deleted_at TIMESTAMP,

    UNIQUE(org_secure_code, shift_code)
);

CREATE INDEX idx_shift_types_org ON shift_types(org_secure_code);

COMMENT ON TABLE shift_types IS '班次定義（早班、中班、晚班等）';
COMMENT ON COLUMN shift_types.shift_code IS '班次代碼，如 MORNING, NIGHT';
COMMENT ON COLUMN shift_types.work_periods IS '工作時段，如 ["08:00-16:00"]';
COMMENT ON COLUMN shift_types.color IS '月曆顯示顏色，如 #4CAF50';

-- ============================================
-- 4. 個人排班 (PersonalSchedule)
-- ============================================
CREATE TABLE IF NOT EXISTS personal_schedules (
    id SERIAL PRIMARY KEY,
    secure_code VARCHAR(32) NOT NULL UNIQUE,
    org_secure_code VARCHAR(32) NOT NULL REFERENCES organizations(secure_code),

    user_secure_code VARCHAR(32) NOT NULL REFERENCES users(secure_code),
    schedule_date DATE NOT NULL,
    shift_type_secure_code VARCHAR(32) REFERENCES shift_types(secure_code),

    -- 或直接指定時段（不用班次）
    custom_periods JSONB,

    source VARCHAR(20) DEFAULT 'MANUAL',  -- MANUAL / TEMPLATE / SWAP
    note TEXT,

    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    is_deleted BOOLEAN DEFAULT FALSE,
    deleted_at TIMESTAMP,

    UNIQUE(user_secure_code, schedule_date)
);

CREATE INDEX idx_personal_schedules_user ON personal_schedules(user_secure_code);
CREATE INDEX idx_personal_schedules_date ON personal_schedules(schedule_date);
CREATE INDEX idx_personal_schedules_org_date ON personal_schedules(org_secure_code, schedule_date);

COMMENT ON TABLE personal_schedules IS '個人排班（覆蓋共用班表）';
COMMENT ON COLUMN personal_schedules.shift_type_secure_code IS '班次，null 時檢查 custom_periods 或表示排休';
COMMENT ON COLUMN personal_schedules.custom_periods IS '自訂時段，不使用班次定義時填寫';
COMMENT ON COLUMN personal_schedules.source IS 'MANUAL=手動排班, TEMPLATE=範本套用, SWAP=調班';

-- ============================================
-- 5. 排班調整 (ScheduleAdjustment) - 第三階段用
-- ============================================
CREATE TABLE IF NOT EXISTS schedule_adjustments (
    id SERIAL PRIMARY KEY,
    secure_code VARCHAR(32) NOT NULL UNIQUE,
    org_secure_code VARCHAR(32) NOT NULL REFERENCES organizations(secure_code),

    user_secure_code VARCHAR(32) NOT NULL REFERENCES users(secure_code),
    adjust_date DATE NOT NULL,
    adjust_type VARCHAR(20) NOT NULL,  -- LEAVE / OVERTIME / SWAP / CANCEL

    -- 調整內容
    original_periods JSONB,
    adjusted_periods JSONB,

    -- 關聯表單（第三階段用）
    form_instance_secure_code VARCHAR(32),

    -- 代班人（調班/請假找人補）
    substitute_user_secure_code VARCHAR(32) REFERENCES users(secure_code),

    status VARCHAR(20) DEFAULT 'PENDING',  -- PENDING / APPROVED / REJECTED
    approved_at TIMESTAMP,
    approved_by VARCHAR(32),

    note TEXT,

    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    is_deleted BOOLEAN DEFAULT FALSE,
    deleted_at TIMESTAMP,

    UNIQUE(user_secure_code, adjust_date, adjust_type)
);

CREATE INDEX idx_schedule_adjustments_user ON schedule_adjustments(user_secure_code);
CREATE INDEX idx_schedule_adjustments_date ON schedule_adjustments(adjust_date);
CREATE INDEX idx_schedule_adjustments_status ON schedule_adjustments(status);

COMMENT ON TABLE schedule_adjustments IS '排班調整（請假、加班、調班）';
COMMENT ON COLUMN schedule_adjustments.adjust_type IS 'LEAVE=請假, OVERTIME=加班, SWAP=調班, CANCEL=取消班次';
COMMENT ON COLUMN schedule_adjustments.original_periods IS '原本時段';
COMMENT ON COLUMN schedule_adjustments.adjusted_periods IS '調整後時段（加班用）';
COMMENT ON COLUMN schedule_adjustments.substitute_user_secure_code IS '代班人';

-- ============================================
-- 6. 用戶表新增班表關聯欄位
-- ============================================
ALTER TABLE users ADD COLUMN IF NOT EXISTS work_schedule_secure_code VARCHAR(32)
    REFERENCES work_schedules(secure_code);

COMMENT ON COLUMN users.work_schedule_secure_code IS '用戶的共用班表，null 時使用企業預設';

-- ============================================
-- 7. 逾時追蹤表 (TimeoutTracker) - 整合表單流程
-- ============================================
CREATE TABLE IF NOT EXISTS timeout_trackers (
    id SERIAL PRIMARY KEY,
    secure_code VARCHAR(32) NOT NULL UNIQUE,
    org_secure_code VARCHAR(32) NOT NULL REFERENCES organizations(secure_code),

    -- 關聯表單流程
    form_instance_secure_code VARCHAR(32) NOT NULL,
    node_instance_secure_code VARCHAR(32) NOT NULL,
    assignee_secure_code VARCHAR(32) NOT NULL REFERENCES users(secure_code),

    -- 逾時設定
    timeout_mode VARCHAR(20) NOT NULL,  -- ABSOLUTE, WORKING, BOTH
    timeout_absolute_seconds INTEGER,
    timeout_working_seconds INTEGER,

    -- 計算狀態
    timeout_absolute_at TIMESTAMP,
    remaining_working_seconds INTEGER,

    -- 請假標記（由請假流程寫入）
    on_leave BOOLEAN DEFAULT FALSE,
    on_leave_until TIMESTAMP,

    -- 狀態
    status VARCHAR(20) DEFAULT 'PENDING',  -- PENDING, TIMEOUT, COMPLETED, TRANSFERRED
    timeout_triggered_at TIMESTAMP,

    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    last_check_at TIMESTAMP
);

CREATE INDEX idx_timeout_trackers_status ON timeout_trackers(status, timeout_absolute_at);
CREATE INDEX idx_timeout_trackers_assignee ON timeout_trackers(assignee_secure_code, status);
CREATE INDEX idx_timeout_trackers_org ON timeout_trackers(org_secure_code);

COMMENT ON TABLE timeout_trackers IS '逾時追蹤表';
COMMENT ON COLUMN timeout_trackers.timeout_mode IS 'ABSOLUTE=絕對時間, WORKING=工作時間, BOTH=雙軌制';
COMMENT ON COLUMN timeout_trackers.on_leave IS '請假標記，由請假流程寫入';
COMMENT ON COLUMN timeout_trackers.status IS 'PENDING=等待中, TIMEOUT=已逾時, COMPLETED=已簽核, TRANSFERRED=已轉代理';
