-- ============================================================
-- SQL Form Sync 資料庫初始化
-- 建立 beakform 帳號和 beakform_data 獨立資料庫
--
-- 用途：form.io JSONB 資料的 SQL 結構化同步副本
-- 執行方式：sudo -u postgres psql -f scripts/sql_form_setup.sql
-- ============================================================

-- 1. 建立專用帳號（若不存在）
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'beakform') THEN
        CREATE USER beakform WITH PASSWORD 'postgres123';
        RAISE NOTICE 'User beakform created.';
    ELSE
        RAISE NOTICE 'User beakform already exists.';
    END IF;
END
$$;

-- 2. 建立獨立資料庫（若不存在）
SELECT 'CREATE DATABASE beakform_data OWNER beakform'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'beakform_data');
\gexec

-- 3. 授權
GRANT ALL PRIVILEGES ON DATABASE beakform_data TO beakform;

-- 4. 連線到 beakform_data 建立 registry 表
\c beakform_data

-- 確保 beakform 擁有 public schema 的完整權限
GRANT ALL ON SCHEMA public TO beakform;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO beakform;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO beakform;

RAISE NOTICE 'beakform_data database setup complete.';
