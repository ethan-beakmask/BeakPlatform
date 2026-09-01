-- 133_fw_sp_owner_separation.sql
--
-- PF-190 P3-1（縱深防禦）：fw_sp schema 與其函式改由獨立 NOLOGIN 角色
-- fw_sp_owner 擁有，app role（beakplatform）只留 USAGE + EXECUTE。
--
-- 目的：beakplatform 原本是 fw_sp 的 owner（ACL 含 CREATE），平台他處若有
-- SQL 寫入漏洞就能在 SqlExecutor 的白名單 schema 種後門 SP。
-- 白名單 SP 一律 SECURITY INVOKER（以呼叫者 beakplatform 的權限讀表），
-- 所以換 owner 不影響任何既有流程的執行，只拿掉 app role 的 DDL 能力。
--
-- 執行（必須用 postgres superuser——beakplatform 無權建 role 與轉移 ownership）：
--   sudo -u postgres psql -d beakplatform_dev \
--     -f scripts/migrations/133_fw_sp_owner_separation.sql
--
-- 此後新增 SP 的 migration 也必須用 postgres 跑，並在 CREATE FUNCTION 後補
-- ALTER FUNCTION ... OWNER TO fw_sp_owner 與 EXECUTE 授權
-- （範本見 dev-notes/SQL_EXECUTOR_SPEC.md「白名單維護」一節）。
--
-- 前置：fw_sp schema 必須已存在（106_sqlexecutor_whitelist.sql）。
-- 冪等，可重複執行。

BEGIN;

-- 1. 專用 NOLOGIN 角色（只當 owner，不能登入）
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'fw_sp_owner') THEN
        CREATE ROLE fw_sp_owner NOLOGIN;
    END IF;
END $$;

COMMENT ON ROLE fw_sp_owner IS
    'SqlExecutor 白名單 schema fw_sp 的專用 owner（NOLOGIN）。'
    'app role 只有 USAGE+EXECUTE，不能在 fw_sp 建立或改寫函式（PF-190 P3-1）';

-- 2. schema ownership 轉移
ALTER SCHEMA fw_sp OWNER TO fw_sp_owner;

-- 3. 既有函式 ownership 轉移
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

-- 4. schema ACL：beakplatform 只留 USAGE（收掉 CREATE），PUBLIC 全收
REVOKE ALL ON SCHEMA fw_sp FROM PUBLIC;
REVOKE ALL ON SCHEMA fw_sp FROM beakplatform;
GRANT USAGE ON SCHEMA fw_sp TO beakplatform;

-- 5. 函式 EXECUTE：收掉 PostgreSQL 對 PUBLIC 的預設授權，明確只給 beakplatform
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA fw_sp FROM PUBLIC;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA fw_sp TO beakplatform;

-- 6. 未來由 fw_sp_owner 建立的函式自動套同一組授權。
--    REVOKE 必須用「全域」形式：schema 範圍的 default privileges 只能在內建預設
--    之上加授權，收不掉內建的 PUBLIC EXECUTE（實測 IN SCHEMA 版 REVOKE 無效，
--    新函式 ACL 仍出現 =X/）。fw_sp_owner 只在 fw_sp 建函式，全域收掉無副作用。
ALTER DEFAULT PRIVILEGES FOR ROLE fw_sp_owner
    REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE fw_sp_owner IN SCHEMA fw_sp
    GRANT EXECUTE ON FUNCTIONS TO beakplatform;

COMMIT;
