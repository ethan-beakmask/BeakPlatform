-- SQL Form POC - 建表 + 測試資料
-- 用途: 驗證動態 SQL → form.io CRUD 概念

-- Layout 儲存表
CREATE TABLE IF NOT EXISTS fw_sql_form_layouts (
    id SERIAL PRIMARY KEY,
    table_name VARCHAR(128) NOT NULL UNIQUE,
    layout JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- 測試用員工資料表
CREATE TABLE IF NOT EXISTS fw_data_employee (
    id SERIAL PRIMARY KEY,
    emp_name VARCHAR(100) NOT NULL,
    emp_email VARCHAR(200),
    department VARCHAR(100),
    hire_date DATE,
    salary INTEGER,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    notes TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- 測試資料
INSERT INTO fw_data_employee (emp_name, emp_email, department, hire_date, salary, is_active, notes)
VALUES
    ('王小明', 'wang@example.com', '資訊部', '2024-03-15', 55000, TRUE, '資深工程師'),
    ('李美玲', 'lee@example.com', '人資部', '2023-08-01', 48000, TRUE, NULL),
    ('張大偉', 'chang@example.com', '業務部', '2025-01-10', 42000, FALSE, '已離職')
ON CONFLICT DO NOTHING;
