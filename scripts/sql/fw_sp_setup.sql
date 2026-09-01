-- fw_sp_setup.sql — SqlExecutor 白名單 schema 與擁有權分離（安裝用）
--
-- 來源：整併退役的 migration 106（schema 部分）與 133（owner 分離），
-- demo 表 / demo SP / 白名單資料不在此檔（那些是資料，不是 schema）。
--
-- 安全設計（背景見 dev-notes/SQL_EXECUTOR_SPEC.md）：
--   - SqlExecutor 節點只能呼叫 fw_sp schema 內的函式
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
    'SqlExecutor 流程節點唯一可呼叫的 schema。放進來的函式等同開放給流程設計者呼叫，'
    '每支的第一個參數必須是 p_org_secure_code 且必須拿它做租戶過濾。';

-- 2. 專用 NOLOGIN 角色（只當 owner，不能登入）
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'fw_sp_owner') THEN
        CREATE ROLE fw_sp_owner NOLOGIN;
    END IF;
END $$;

COMMENT ON ROLE fw_sp_owner IS
    'SqlExecutor 白名單 schema fw_sp 的專用 owner（NOLOGIN）。'
    'app role 只有 USAGE+EXECUTE，不能在 fw_sp 建立或改寫函式（PF-190 P3-1）';

-- 3. schema ownership
ALTER SCHEMA fw_sp OWNER TO fw_sp_owner;

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
