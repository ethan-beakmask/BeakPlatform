-- fw_sp_setup.sql — SysSqlExecutor 白名單 schema 與擁有權分離（安裝用）
--
-- 來源：整併退役的 migration 106（schema 部分）與 133（owner 分離），
-- demo 表 / demo SP / 白名單資料不在此檔（那些是資料，不是 schema）。
--
-- 安全設計（背景見 dev-notes/SQL_EXECUTOR_SPEC.md）：
--   - SysSqlExecutor 節點只能呼叫 fw_sp schema 內的函式
--   - schema 與函式由 NOLOGIN 角色 fw_sp_owner 擁有，app 角色只有 USAGE+EXECUTE，
--     平台他處的 SQL 寫入漏洞無法在白名單 schema 種後門 SP
--
-- 執行（必須用 postgres superuser，app_user 帶入應用程式的 DB 角色名）：
--   sudo -u postgres psql -d <資料庫> -v app_user=beakplatform -f scripts/sql/fw_sp_setup.sql
-- 冪等，可重複執行。

BEGIN;

-- 1. 專用 schema
CREATE SCHEMA IF NOT EXISTS fw_sp;
COMMENT ON SCHEMA fw_sp IS
    'SysSqlExecutor 流程節點唯一可呼叫的 schema。放進來的函式等同開放給流程設計者呼叫，'
    '每支的第一個參數必須是 p_org_secure_code 且必須拿它做租戶過濾。';

-- 2. 專用 NOLOGIN 角色（只當 owner，不能登入）
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'fw_sp_owner') THEN
        CREATE ROLE fw_sp_owner NOLOGIN;
    END IF;
END $$;

COMMENT ON ROLE fw_sp_owner IS
    'SysSqlExecutor 白名單 schema fw_sp 的專用 owner（NOLOGIN）。'
    'app role 只有 USAGE+EXECUTE，不能在 fw_sp 建立或改寫函式（PF-190 P3-1）';

-- 3. schema ownership
ALTER SCHEMA fw_sp OWNER TO fw_sp_owner;

-- 4. 展覽館範例 SP（三支，分別示範 row / rows / scalar 三種回傳型態）
--    共通規則：第一參數 p_org_secure_code，且它必須是實際的 filter 條件。
--    這份檔在全新安裝時先於 db.create_all() 執行，public.fw_demo_inventory 還不存在；
--    LANGUAGE sql 的函式本體預設會在建立時驗證資料表，所以關掉本體檢查（只影響本連線）。
SET check_function_bodies = off;

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
    WHERE inv.org_secure_code = p_org_secure_code
      AND inv.item_code = p_item_code
      AND inv.is_deleted = FALSE
    LIMIT 1;
$$;

COMMENT ON FUNCTION fw_sp.check_stock(TEXT, TEXT) IS
    '依料號查詢該企業目前庫存量與安全存量（SysSqlExecutor 白名單 check_stock）';

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
    WHERE inv.org_secure_code = p_org_secure_code
      AND inv.is_deleted = FALSE
      AND inv.qty_on_hand < inv.safety_qty
    ORDER BY (inv.safety_qty - inv.qty_on_hand) DESC, inv.item_code;
$$;

COMMENT ON FUNCTION fw_sp.low_stock_items(TEXT) IS
    '列出該企業所有低於安全存量的料號（SysSqlExecutor 白名單 low_stock_items）';

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
    WHERE inv.org_secure_code = p_org_secure_code
      AND inv.item_code = p_item_code
      AND inv.is_deleted = FALSE;
$$;

COMMENT ON FUNCTION fw_sp.stock_qty(TEXT, TEXT) IS
    '回傳該企業某料號的現有庫存量，查無資料回 0（SysSqlExecutor 白名單 stock_qty）';

-- 4. 既有函式 ownership（全新安裝時無函式，重跑時把漏網的收齊）
DO $$
DECLARE
    fn RECORD;
BEGIN
    FOR fn IN
        SELECT p.oid::regprocedure AS sig
        FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'fw_sp'
    LOOP
        EXECUTE format('ALTER FUNCTION %s OWNER TO fw_sp_owner', fn.sig);
    END LOOP;
END $$;

-- 5. schema ACL：app 角色只留 USAGE，PUBLIC 全收
REVOKE ALL ON SCHEMA fw_sp FROM PUBLIC;
REVOKE ALL ON SCHEMA fw_sp FROM :"app_user";
GRANT USAGE ON SCHEMA fw_sp TO :"app_user";

-- 6. 函式 EXECUTE：收掉 PUBLIC 預設授權，明確只給 app 角色
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA fw_sp FROM PUBLIC;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA fw_sp TO :"app_user";

-- 7. 未來由 fw_sp_owner 建立的函式自動套同一組授權。
--    REVOKE 必須用「全域」形式：schema 範圍的 default privileges 收不掉內建的
--    PUBLIC EXECUTE（實測 IN SCHEMA 版 REVOKE 無效）。fw_sp_owner 只在 fw_sp
--    建函式，全域收掉無副作用。
ALTER DEFAULT PRIVILEGES FOR ROLE fw_sp_owner
    REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE fw_sp_owner IN SCHEMA fw_sp
    GRANT EXECUTE ON FUNCTIONS TO :"app_user";

COMMIT;
