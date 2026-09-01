-- 106: SqlExecutor 節點的預存程序白名單（含 fw_sp schema 與範例 SP）
--
-- 對應 handler: modules/form_workflow/services/node_handlers/sqlexecutor_handler.py
--
-- 安全設計（改這個檔案之前先讀完）：
--   1. SqlExecutor **只能**呼叫 schema `fw_sp` 內的函式。handler 組 SQL 時
--      schema 名是寫死的字面值，函式名另經白名單表 + pg_proc 雙重比對。
--      也就是說：即使流程 graph JSON 被竄改、即使白名單表被寫入惡意內容，
--      可觸及的範圍仍鎖在這個 schema 內。**不要為了方便而放寬成可指定 schema。**
--   2. 每支 SP 的第一個參數固定是 `p_org_secure_code`，由 handler 從流程所屬企業
--      強制帶入，設計者無從指定。SP 內部必須拿它當實際 filter 條件
--      —— 平台主庫多數表沒有 RLS（只有 10 張有，且都不是 FORCE），
--      `beakplatform` 又是表的 owner，**RLS 不會替你擋，租戶邊界就在 SP 的 WHERE 裡**。
--   3. SP 一律 SECURITY INVOKER（預設）。handler 執行前會查 pg_proc.prosecdef，
--      是 SECURITY DEFINER 就拒絕執行。
--   4. 呼叫一律在 READ ONLY 交易內（handler 負責），所以這裡登錄的 SP 只能是查詢型。
--
-- 使用方式：
--   PGPASSWORD=postgres123 psql -h localhost -U beakplatform -d beakplatform_dev \
--     -f scripts/migrations/106_sqlexecutor_whitelist.sql
-- 冪等，可重複執行。

BEGIN;

-- ---------------------------------------------------------------------------
-- 1. 專用 schema
-- ---------------------------------------------------------------------------
CREATE SCHEMA IF NOT EXISTS fw_sp;
COMMENT ON SCHEMA fw_sp IS
    'SqlExecutor 流程節點唯一可呼叫的 schema。放進來的函式等同開放給流程設計者呼叫，'
    '每支的第一個參數必須是 p_org_secure_code 且必須拿它做租戶過濾。';

-- 不讓其他角色（例如企業獨立資料庫的帳號）碰到這個 schema
REVOKE ALL ON SCHEMA fw_sp FROM PUBLIC;

-- ---------------------------------------------------------------------------
-- 2. 白名單表
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fw_sql_procedures (
    id              SERIAL PRIMARY KEY,
    secure_code     VARCHAR(32)  NOT NULL UNIQUE,
    -- NULL = 全平台共用；有值 = 只有該企業的流程可以選用
    org_secure_code VARCHAR(32),
    -- 流程 config 存的穩定識別碼（與實際函式名解耦，函式改名不必改流程）
    code            VARCHAR(64)  NOT NULL,
    -- fw_sp schema 內的函式名
    function_name   VARCHAR(63)  NOT NULL,
    display_name    VARCHAR(200) NOT NULL,
    description     TEXT,
    -- [{"name","type","label","required","description"}]，第一個必須是 p_org_secure_code
    parameters      JSONB        NOT NULL DEFAULT '[]'::jsonb,
    -- scalar=單值 / row=單列 / rows=多列
    result_mode     VARCHAR(10)  NOT NULL DEFAULT 'rows',
    -- [{"name","label"}]，純文件用途，給設計器顯示
    result_columns  JSONB        NOT NULL DEFAULT '[]'::jsonb,
    -- 回傳列數上限（handler 另有硬上限，取兩者較小值）
    max_rows        INTEGER      NOT NULL DEFAULT 100,
    is_active       BOOLEAN      NOT NULL DEFAULT TRUE,
    is_deleted      BOOLEAN      NOT NULL DEFAULT FALSE,
    deleted_at      TIMESTAMP,
    created_at      TIMESTAMP    NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP    NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_fw_sql_proc_result_mode CHECK (result_mode IN ('scalar', 'row', 'rows')),
    CONSTRAINT ck_fw_sql_proc_max_rows    CHECK (max_rows BETWEEN 1 AND 1000),
    CONSTRAINT ck_fw_sql_proc_code        CHECK (code ~ '^[a-z][a-z0-9_]{0,62}$'),
    -- 函式名同樣受限，讓「白名單表被寫入奇怪內容」也組不出合法識別碼
    CONSTRAINT ck_fw_sql_proc_function    CHECK (function_name ~ '^[a-z][a-z0-9_]{0,62}$')
);

COMMENT ON TABLE fw_sql_procedures IS
    'SqlExecutor 節點的預存程序白名單。登錄一筆 = 允許流程設計者呼叫該 SP，'
    '等同授權，維護走 migration 不開放 Web UI。';

CREATE UNIQUE INDEX IF NOT EXISTS ux_fw_sql_proc_org_code
    ON fw_sql_procedures (COALESCE(org_secure_code, ''), code)
    WHERE is_deleted = FALSE;

CREATE INDEX IF NOT EXISTS ix_fw_sql_proc_org
    ON fw_sql_procedures (org_secure_code);

-- ---------------------------------------------------------------------------
-- 3. 範例業務資料表（示範用，不是平台功能）
--    場景：請料單在核可前先查庫存是否足夠
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fw_demo_inventory (
    id              SERIAL PRIMARY KEY,
    secure_code     VARCHAR(32)   NOT NULL UNIQUE DEFAULT generate_secure_code(),
    org_secure_code VARCHAR(32)   NOT NULL,
    item_code       VARCHAR(64)   NOT NULL,
    item_name       VARCHAR(200)  NOT NULL,
    qty_on_hand     NUMERIC(14,2) NOT NULL DEFAULT 0,
    safety_qty      NUMERIC(14,2) NOT NULL DEFAULT 0,
    unit            VARCHAR(20)   NOT NULL DEFAULT 'PCS',
    is_deleted      BOOLEAN       NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMP     NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP     NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE fw_demo_inventory IS
    'SqlExecutor 範例用庫存表（示範資料，非平台功能）。兩家企業刻意放同樣的料號，'
    '用來驗證跨企業隔離。';

CREATE UNIQUE INDEX IF NOT EXISTS ux_fw_demo_inventory_org_item
    ON fw_demo_inventory (org_secure_code, item_code)
    WHERE is_deleted = FALSE;

-- ---------------------------------------------------------------------------
-- 4. 範例 SP（三支，分別示範 row / rows / scalar 三種回傳型態）
--    共通規則：第一參數 p_org_secure_code，且它必須是實際的 filter 條件。
-- ---------------------------------------------------------------------------

-- 4a. row：查單一料號的庫存
CREATE OR REPLACE FUNCTION fw_sp.check_stock(
    p_org_secure_code TEXT,
    p_item_code       TEXT
)
RETURNS TABLE (
    item_code       VARCHAR,
    item_name       VARCHAR,
    qty_on_hand     NUMERIC,
    safety_qty      NUMERIC,
    unit            VARCHAR,
    is_below_safety BOOLEAN
)
LANGUAGE sql
STABLE
SECURITY INVOKER
AS $$
    SELECT inv.item_code,
           inv.item_name,
           inv.qty_on_hand,
           inv.safety_qty,
           inv.unit,
           (inv.qty_on_hand < inv.safety_qty) AS is_below_safety
    FROM public.fw_demo_inventory inv
    WHERE inv.org_secure_code = p_org_secure_code   -- 租戶邊界，不可移除
      AND inv.item_code = p_item_code
      AND inv.is_deleted = FALSE
    LIMIT 1;
$$;

COMMENT ON FUNCTION fw_sp.check_stock(TEXT, TEXT) IS
    '依料號查詢該企業目前庫存量與安全存量（SqlExecutor 白名單 check_stock）';

-- 4b. rows：列出低於安全存量的料號
CREATE OR REPLACE FUNCTION fw_sp.low_stock_items(
    p_org_secure_code TEXT
)
RETURNS TABLE (
    item_code   VARCHAR,
    item_name   VARCHAR,
    qty_on_hand NUMERIC,
    safety_qty  NUMERIC,
    shortage    NUMERIC
)
LANGUAGE sql
STABLE
SECURITY INVOKER
AS $$
    SELECT inv.item_code,
           inv.item_name,
           inv.qty_on_hand,
           inv.safety_qty,
           (inv.safety_qty - inv.qty_on_hand) AS shortage
    FROM public.fw_demo_inventory inv
    WHERE inv.org_secure_code = p_org_secure_code   -- 租戶邊界，不可移除
      AND inv.is_deleted = FALSE
      AND inv.qty_on_hand < inv.safety_qty
    ORDER BY (inv.safety_qty - inv.qty_on_hand) DESC, inv.item_code;
$$;

COMMENT ON FUNCTION fw_sp.low_stock_items(TEXT) IS
    '列出該企業所有低於安全存量的料號（SqlExecutor 白名單 low_stock_items）';

-- 4c. scalar：單一料號的現有庫存量（給 Branch 條件直接比大小用）
CREATE OR REPLACE FUNCTION fw_sp.stock_qty(
    p_org_secure_code TEXT,
    p_item_code       TEXT
)
RETURNS NUMERIC
LANGUAGE sql
STABLE
SECURITY INVOKER
AS $$
    SELECT COALESCE(MAX(inv.qty_on_hand), 0)
    FROM public.fw_demo_inventory inv
    WHERE inv.org_secure_code = p_org_secure_code   -- 租戶邊界，不可移除
      AND inv.item_code = p_item_code
      AND inv.is_deleted = FALSE;
$$;

COMMENT ON FUNCTION fw_sp.stock_qty(TEXT, TEXT) IS
    '回傳該企業某料號的現有庫存量，查無資料回 0（SqlExecutor 白名單 stock_qty）';

-- ---------------------------------------------------------------------------
-- 5. 白名單登錄（全平台共用 → org_secure_code 留 NULL）
-- ---------------------------------------------------------------------------
INSERT INTO fw_sql_procedures
    (secure_code, org_secure_code, code, function_name, display_name, description,
     parameters, result_mode, result_columns, max_rows)
SELECT generate_secure_code(), NULL, 'check_stock', 'check_stock', '查詢庫存',
       '依料號查詢本企業目前庫存量與安全存量，回傳單列。',
       '[{"name":"p_org_secure_code","type":"text","label":"企業識別碼","required":true,"description":"由系統自動帶入"},
         {"name":"p_item_code","type":"text","label":"料號","required":true,"description":"要查詢的料號，例如 A-1001"}]'::jsonb,
       'row',
       '[{"name":"item_code","label":"料號"},{"name":"item_name","label":"品名"},
         {"name":"qty_on_hand","label":"現有庫存"},{"name":"safety_qty","label":"安全存量"},
         {"name":"unit","label":"單位"},{"name":"is_below_safety","label":"低於安全存量"}]'::jsonb,
       1
WHERE NOT EXISTS (
    SELECT 1 FROM fw_sql_procedures
    WHERE code = 'check_stock' AND org_secure_code IS NULL AND is_deleted = FALSE
);

INSERT INTO fw_sql_procedures
    (secure_code, org_secure_code, code, function_name, display_name, description,
     parameters, result_mode, result_columns, max_rows)
SELECT generate_secure_code(), NULL, 'low_stock_items', 'low_stock_items', '低於安全存量清單',
       '列出本企業所有低於安全存量的料號，缺口大的排前面。',
       '[{"name":"p_org_secure_code","type":"text","label":"企業識別碼","required":true,"description":"由系統自動帶入"}]'::jsonb,
       'rows',
       '[{"name":"item_code","label":"料號"},{"name":"item_name","label":"品名"},
         {"name":"qty_on_hand","label":"現有庫存"},{"name":"safety_qty","label":"安全存量"},
         {"name":"shortage","label":"缺口"}]'::jsonb,
       50
WHERE NOT EXISTS (
    SELECT 1 FROM fw_sql_procedures
    WHERE code = 'low_stock_items' AND org_secure_code IS NULL AND is_deleted = FALSE
);

INSERT INTO fw_sql_procedures
    (secure_code, org_secure_code, code, function_name, display_name, description,
     parameters, result_mode, result_columns, max_rows)
SELECT generate_secure_code(), NULL, 'stock_qty', 'stock_qty', '庫存量（單一數值）',
       '回傳本企業某料號的現有庫存量，查無資料回 0。適合直接放進 Branch 條件比大小。',
       '[{"name":"p_org_secure_code","type":"text","label":"企業識別碼","required":true,"description":"由系統自動帶入"},
         {"name":"p_item_code","type":"text","label":"料號","required":true,"description":"要查詢的料號"}]'::jsonb,
       'scalar',
       '[]'::jsonb,
       1
WHERE NOT EXISTS (
    SELECT 1 FROM fw_sql_procedures
    WHERE code = 'stock_qty' AND org_secure_code IS NULL AND is_deleted = FALSE
);

-- ---------------------------------------------------------------------------
-- 6. 範例庫存資料（兩家企業刻意用同樣的料號，數量不同 → 可驗跨企業隔離）
-- ---------------------------------------------------------------------------
INSERT INTO fw_demo_inventory (org_secure_code, item_code, item_name, qty_on_hand, safety_qty, unit)
SELECT v.org, v.item_code, v.item_name, v.qty, v.safety, v.unit
FROM (VALUES
    ('_9c8TewkRkCBEf3XsUdqeF', 'A-1001', '六角螺絲 M6',      1200.00, 500.00, 'PCS'),
    ('_9c8TewkRkCBEf3XsUdqeF', 'A-1002', '不鏽鋼墊片 M6',      80.00, 300.00, 'PCS'),
    ('_9c8TewkRkCBEf3XsUdqeF', 'B-2001', '防靜電手套 L',      450.00, 200.00, 'PAIR'),
    ('_9c8TewkRkCBEf3XsUdqeF', 'B-2002', '無塵擦拭紙',         30.00, 100.00, 'BOX'),
    ('G4vbVX8IiBsm0koHISSYFs', 'A-1001', '六角螺絲 M6',        5.00, 500.00, 'PCS'),
    ('G4vbVX8IiBsm0koHISSYFs', 'C-3001', '碳粉匣 CT-12',      12.00,  10.00, 'PCS')
) AS v(org, item_code, item_name, qty, safety, unit)
WHERE NOT EXISTS (
    SELECT 1 FROM fw_demo_inventory d
    WHERE d.org_secure_code = v.org AND d.item_code = v.item_code AND d.is_deleted = FALSE
);

-- ---------------------------------------------------------------------------
-- 7. 更新節點定義（原本的 config_schema 是空殼且 handler 檔案不存在）
-- ---------------------------------------------------------------------------
UPDATE workflow_node_definitions
SET description = '呼叫平台白名單內的預存程序（唯讀），結果寫入流程變數，'
                  '可選擇插入一筆簽核註記。企業識別碼由系統強制帶入。',
    config_schema = '{"procedure_code":"string","params":"object","result_var":"string",'
                    '"timeout_seconds":"integer","write_approval_note":"boolean",'
                    '"note_template":"string","on_error":"string"}'::jsonb,
    display_name = 'SQL 執行',
    is_active = TRUE,
    updated_at = NOW()
WHERE node_type = 'SqlExecutor';

COMMIT;
