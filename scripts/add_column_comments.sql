-- BeakMask 資料庫欄位註解
-- 執行方式: psql -U beakmask -d beakmask_dev -f scripts/add_column_comments.sql
-- 產生時間: 2025-12-20

-- ============================================================================
-- 共用欄位註解 (多數表都有)
-- ============================================================================

-- conglomerates (集團)
COMMENT ON TABLE conglomerates IS '集團 - 多個企業的聯合體';
COMMENT ON COLUMN conglomerates.id IS '內部自增 ID';
COMMENT ON COLUMN conglomerates.secure_code IS '外部識別碼 (URL-safe token)';
COMMENT ON COLUMN conglomerates.code IS '集團代碼 (唯一)';
COMMENT ON COLUMN conglomerates.name IS '集團名稱';
COMMENT ON COLUMN conglomerates.description IS '集團描述';
COMMENT ON COLUMN conglomerates.is_active IS '是否啟用';
COMMENT ON COLUMN conglomerates.created_at IS '建立時間';
COMMENT ON COLUMN conglomerates.updated_at IS '更新時間';
COMMENT ON COLUMN conglomerates.is_deleted IS '是否已刪除 (軟刪除)';
COMMENT ON COLUMN conglomerates.deleted_at IS '刪除時間';

-- organizations (企業)
COMMENT ON TABLE organizations IS '企業/組織 - 多租戶隔離的最上層單位';
COMMENT ON COLUMN organizations.id IS '內部自增 ID';
COMMENT ON COLUMN organizations.secure_code IS '外部識別碼 (URL-safe token)';
COMMENT ON COLUMN organizations.code IS '企業代碼 (唯一)';
COMMENT ON COLUMN organizations.name IS '企業名稱';
COMMENT ON COLUMN organizations.domain_name IS '登入網域 (如: acme.com.tw)';
COMMENT ON COLUMN organizations.description IS '企業描述';
COMMENT ON COLUMN organizations.customer_type IS '客戶類型: TRIAL/FORMAL/BLACKLIST';
COMMENT ON COLUMN organizations.user_limit IS '帳號數量上限';
COMMENT ON COLUMN organizations.is_active IS '是否啟用';
COMMENT ON COLUMN organizations.settings IS '企業設定 (JSON)';
COMMENT ON COLUMN organizations.contact_person IS '聯絡人姓名';
COMMENT ON COLUMN organizations.contact_email IS '聯絡人 Email';
COMMENT ON COLUMN organizations.contact_phone IS '聯絡人電話';
COMMENT ON COLUMN organizations.address IS '企業地址';
COMMENT ON COLUMN organizations.conglomerate_secure_code IS '所屬集團 (可為空)';
COMMENT ON COLUMN organizations.created_at IS '建立時間';
COMMENT ON COLUMN organizations.updated_at IS '更新時間';
COMMENT ON COLUMN organizations.is_deleted IS '是否已刪除 (軟刪除)';
COMMENT ON COLUMN organizations.deleted_at IS '刪除時間';

-- users (用戶)
COMMENT ON TABLE users IS '用戶 - 系統使用者';
COMMENT ON COLUMN users.id IS '內部自增 ID';
COMMENT ON COLUMN users.secure_code IS '外部識別碼';
COMMENT ON COLUMN users.org_secure_code IS '所屬企業';
COMMENT ON COLUMN users.username IS '用戶名 (組織內唯一)';
COMMENT ON COLUMN users.email IS 'Email (全系統唯一)';
COMMENT ON COLUMN users.password_hash IS '密碼雜湊值 (bcrypt)';
COMMENT ON COLUMN users.display_name IS '顯示名稱';
COMMENT ON COLUMN users.user_type IS '用戶類型: SYSTEM_ADMIN/ORG_ADMIN/EMPLOYEE/EXTERNAL';
COMMENT ON COLUMN users.is_active IS '是否啟用';
COMMENT ON COLUMN users.last_login_at IS '最後登入時間';
COMMENT ON COLUMN users.primary_unit_secure_code IS '主要組織單位';
COMMENT ON COLUMN users.preferences IS '用戶偏好設定 (JSON)';
COMMENT ON COLUMN users.created_at IS '建立時間';
COMMENT ON COLUMN users.updated_at IS '更新時間';
COMMENT ON COLUMN users.is_deleted IS '是否已刪除';
COMMENT ON COLUMN users.deleted_at IS '刪除時間';

-- contracts (合約)
COMMENT ON TABLE contracts IS '合約 - 企業服務合約';
COMMENT ON COLUMN contracts.id IS '內部自增 ID';
COMMENT ON COLUMN contracts.secure_code IS '外部識別碼';
COMMENT ON COLUMN contracts.org_secure_code IS '所屬企業';
COMMENT ON COLUMN contracts.contract_number IS '合約編號 (格式: CTR-YYYYMMDD-XXXX)';
COMMENT ON COLUMN contracts.name IS '合約名稱';
COMMENT ON COLUMN contracts.description IS '合約描述';
COMMENT ON COLUMN contracts.start_date IS '合約開始日期';
COMMENT ON COLUMN contracts.end_date IS '合約結束日期';
COMMENT ON COLUMN contracts.amount IS '合約金額';
COMMENT ON COLUMN contracts.status IS '合約狀態: ACTIVE/DISABLED';
COMMENT ON COLUMN contracts.modules_config IS '模組配置 (JSON)';
COMMENT ON COLUMN contracts.notes IS '備註';
COMMENT ON COLUMN contracts.created_at IS '建立時間';
COMMENT ON COLUMN contracts.updated_at IS '更新時間';
COMMENT ON COLUMN contracts.is_deleted IS '是否已刪除';
COMMENT ON COLUMN contracts.deleted_at IS '刪除時間';

-- organizational_units (組織單位)
COMMENT ON TABLE organizational_units IS '組織單位 - 部門/群組 (樹狀結構)';
COMMENT ON COLUMN organizational_units.id IS '內部自增 ID';
COMMENT ON COLUMN organizational_units.secure_code IS '外部識別碼';
COMMENT ON COLUMN organizational_units.org_secure_code IS '所屬企業';
COMMENT ON COLUMN organizational_units.unit_type IS '單位類型: DEPARTMENT/GROUP';
COMMENT ON COLUMN organizational_units.code IS '單位代碼 (組織內唯一)';
COMMENT ON COLUMN organizational_units.name IS '單位名稱';
COMMENT ON COLUMN organizational_units.description IS '單位描述';
COMMENT ON COLUMN organizational_units.parent_secure_code IS '父層單位 (NULL=根層級)';
COMMENT ON COLUMN organizational_units.full_path IS '完整路徑 (如: /總公司/業務部)';
COMMENT ON COLUMN organizational_units.level IS '層級深度 (從 1 開始)';
COMMENT ON COLUMN organizational_units.sort_order IS '排序順序';
COMMENT ON COLUMN organizational_units.is_active IS '是否啟用';
COMMENT ON COLUMN organizational_units.created_at IS '建立時間';
COMMENT ON COLUMN organizational_units.updated_at IS '更新時間';
COMMENT ON COLUMN organizational_units.is_deleted IS '是否已刪除';
COMMENT ON COLUMN organizational_units.deleted_at IS '刪除時間';

-- roles (角色/職務)
COMMENT ON TABLE roles IS '角色/職務 - 權限分配單位 (樹狀結構)';
COMMENT ON COLUMN roles.id IS '內部自增 ID';
COMMENT ON COLUMN roles.secure_code IS '外部識別碼';
COMMENT ON COLUMN roles.org_secure_code IS '所屬企業';
COMMENT ON COLUMN roles.role_type IS '角色類型: POSITION/ROLE';
COMMENT ON COLUMN roles.scope_type IS '適用範圍: GLOBAL/DEPARTMENT/GROUP';
COMMENT ON COLUMN roles.role_level IS '角色層級: SYSTEM/ORG/MODULE/MEMBER';
COMMENT ON COLUMN roles.exclusive_group IS '互斥群組: EMPLOYEE/EXTERNAL (同群組不能同時指派)';
COMMENT ON COLUMN roles.inherits_from_secure_code IS '權限繼承來源角色';
COMMENT ON COLUMN roles.code IS '角色代碼 (組織內唯一)';
COMMENT ON COLUMN roles.name IS '角色名稱';
COMMENT ON COLUMN roles.description IS '角色描述';
COMMENT ON COLUMN roles.parent_secure_code IS '父層角色 (樹狀結構)';
COMMENT ON COLUMN roles.full_path IS '完整路徑';
COMMENT ON COLUMN roles.level IS '層級深度';
COMMENT ON COLUMN roles.sort_order IS '排序順序';
COMMENT ON COLUMN roles.is_manager IS '是否為管理者角色';
COMMENT ON COLUMN roles.is_system_role IS '是否為系統預設角色 (不可刪除)';
COMMENT ON COLUMN roles.is_active IS '是否啟用';
COMMENT ON COLUMN roles.permissions IS '[已棄用] 改用 RolePermission';
COMMENT ON COLUMN roles.bound_unit_secure_code IS '綁定的組織單位';
COMMENT ON COLUMN roles.created_at IS '建立時間';
COMMENT ON COLUMN roles.updated_at IS '更新時間';
COMMENT ON COLUMN roles.is_deleted IS '是否已刪除';
COMMENT ON COLUMN roles.deleted_at IS '刪除時間';

-- modules (功能模組)
COMMENT ON TABLE modules IS '功能模組 - No-Code Builder 的基礎單位';
COMMENT ON COLUMN modules.id IS '內部自增 ID';
COMMENT ON COLUMN modules.secure_code IS '外部識別碼';
COMMENT ON COLUMN modules.org_secure_code IS '所屬企業';
COMMENT ON COLUMN modules.code IS '模組代碼 (企業內唯一)';
COMMENT ON COLUMN modules.name IS '模組名稱';
COMMENT ON COLUMN modules.description IS '模組描述';
COMMENT ON COLUMN modules.icon IS '模組圖標 (文字符號)';
COMMENT ON COLUMN modules.is_system_module IS '是否系統內建模組';
COMMENT ON COLUMN modules.is_active IS '是否啟用';
COMMENT ON COLUMN modules.display_order IS '顯示順序';
COMMENT ON COLUMN modules.settings IS '模組設定 (JSON)';
COMMENT ON COLUMN modules.created_at IS '建立時間';
COMMENT ON COLUMN modules.updated_at IS '更新時間';
COMMENT ON COLUMN modules.is_deleted IS '是否已刪除';
COMMENT ON COLUMN modules.deleted_at IS '刪除時間';

-- pages (頁面)
COMMENT ON TABLE pages IS '頁面 - No-Code Builder 生成的網頁';
COMMENT ON COLUMN pages.id IS '內部自增 ID';
COMMENT ON COLUMN pages.secure_code IS '外部識別碼';
COMMENT ON COLUMN pages.org_secure_code IS '所屬企業';
COMMENT ON COLUMN pages.module_secure_code IS '所屬模組';
COMMENT ON COLUMN pages.code IS '頁面代碼 (企業內唯一)';
COMMENT ON COLUMN pages.title IS '頁面標題';
COMMENT ON COLUMN pages.description IS '頁面描述';
COMMENT ON COLUMN pages.page_type IS '頁面類型: list/detail/form/dashboard/custom';
COMMENT ON COLUMN pages.url_path IS 'URL 路徑';
COMMENT ON COLUMN pages.flask_route IS '對應的 Flask route';
COMMENT ON COLUMN pages.template IS '頁面模板';
COMMENT ON COLUMN pages.required_access IS '存取權限: public/authenticated/org_admin/system_admin';
COMMENT ON COLUMN pages.is_active IS '是否啟用';
COMMENT ON COLUMN pages.settings IS '頁面設定 (JSON)';
COMMENT ON COLUMN pages.created_at IS '建立時間';
COMMENT ON COLUMN pages.updated_at IS '更新時間';
COMMENT ON COLUMN pages.is_deleted IS '是否已刪除';
COMMENT ON COLUMN pages.deleted_at IS '刪除時間';

-- menu_items (選單項目)
COMMENT ON TABLE menu_items IS '選單項目 - 樹狀結構的動態選單';
COMMENT ON COLUMN menu_items.id IS '內部自增 ID';
COMMENT ON COLUMN menu_items.secure_code IS '外部識別碼';
COMMENT ON COLUMN menu_items.org_secure_code IS '所屬企業';
COMMENT ON COLUMN menu_items.module_secure_code IS '所屬模組';
COMMENT ON COLUMN menu_items.parent_secure_code IS '父選單項目 (NULL=根層級)';
COMMENT ON COLUMN menu_items.code IS '選單代碼 (企業內唯一)';
COMMENT ON COLUMN menu_items.title IS '選單標題';
COMMENT ON COLUMN menu_items.icon IS '選單圖標 (文字符號)';
COMMENT ON COLUMN menu_items.link_type IS '連結類型: page/url/route/divider/header';
COMMENT ON COLUMN menu_items.link_target IS '連結目標';
COMMENT ON COLUMN menu_items.open_in_new_tab IS '是否在新視窗開啟';
COMMENT ON COLUMN menu_items.display_order IS '顯示順序 (同層級內)';
COMMENT ON COLUMN menu_items.depth IS '層級深度';
COMMENT ON COLUMN menu_items.is_expanded IS '是否預設展開';
COMMENT ON COLUMN menu_items.is_active IS '是否啟用';
COMMENT ON COLUMN menu_items.required_level IS '[已棄用] 改用 MenuPermission';
COMMENT ON COLUMN menu_items.is_shared IS '是否為系統共用選單 (僅 BeakPlatform 系統級可設為 True)';
COMMENT ON COLUMN menu_items.required_permission IS '需要的權限代碼 (如 user:manage)，用於 RBAC 過濾';
COMMENT ON COLUMN menu_items.created_at IS '建立時間';
COMMENT ON COLUMN menu_items.updated_at IS '更新時間';
COMMENT ON COLUMN menu_items.is_deleted IS '是否已刪除';
COMMENT ON COLUMN menu_items.deleted_at IS '刪除時間';

-- menu_permissions (選單權限)
COMMENT ON TABLE menu_permissions IS '選單權限 - 定義哪種用戶類型可見哪些選單';
COMMENT ON COLUMN menu_permissions.id IS '內部自增 ID';
COMMENT ON COLUMN menu_permissions.secure_code IS '外部識別碼';
COMMENT ON COLUMN menu_permissions.menu_secure_code IS '選單項目';
COMMENT ON COLUMN menu_permissions.user_type IS '用戶類型: SYSTEM_ADMIN/ORG_ADMIN/EMPLOYEE/EXTERNAL';
COMMENT ON COLUMN menu_permissions.conditions IS '額外條件 (JSON)';
COMMENT ON COLUMN menu_permissions.created_at IS '建立時間';
COMMENT ON COLUMN menu_permissions.updated_at IS '更新時間';
COMMENT ON COLUMN menu_permissions.is_deleted IS '是否已刪除';
COMMENT ON COLUMN menu_permissions.deleted_at IS '刪除時間';

-- job_levels (職等)
COMMENT ON TABLE job_levels IS '職等 - 定義組織內的層級結構';
COMMENT ON COLUMN job_levels.id IS '內部自增 ID';
COMMENT ON COLUMN job_levels.secure_code IS '外部識別碼';
COMMENT ON COLUMN job_levels.org_secure_code IS '所屬企業';
COMMENT ON COLUMN job_levels.code IS '職等代碼 (如: L1-L9)';
COMMENT ON COLUMN job_levels.name IS '職等名稱 (中文)';
COMMENT ON COLUMN job_levels.name_en IS '職等名稱 (英文)';
COMMENT ON COLUMN job_levels.level_order IS '職等數值 (越大越高)';
COMMENT ON COLUMN job_levels.approval_limit IS '簽核權限金額上限 (NULL=無上限)';
COMMENT ON COLUMN job_levels.approval_currency IS '簽核權限幣別';
COMMENT ON COLUMN job_levels.is_manager_level IS '是否為管理職等';
COMMENT ON COLUMN job_levels.management_scope IS '管理幅度說明';
COMMENT ON COLUMN job_levels.description IS '職等描述';
COMMENT ON COLUMN job_levels.sort_order IS '排序順序';
COMMENT ON COLUMN job_levels.is_system_default IS '是否為系統預設';
COMMENT ON COLUMN job_levels.is_active IS '是否啟用';
COMMENT ON COLUMN job_levels.created_at IS '建立時間';
COMMENT ON COLUMN job_levels.updated_at IS '更新時間';
COMMENT ON COLUMN job_levels.is_deleted IS '是否已刪除';
COMMENT ON COLUMN job_levels.deleted_at IS '刪除時間';

-- job_families (職系)
COMMENT ON TABLE job_families IS '職系 - 定義職涯發展軌道';
COMMENT ON COLUMN job_families.id IS '內部自增 ID';
COMMENT ON COLUMN job_families.secure_code IS '外部識別碼';
COMMENT ON COLUMN job_families.org_secure_code IS '所屬企業';
COMMENT ON COLUMN job_families.family_type IS '職系類型: MANAGER/PROFESSIONAL';
COMMENT ON COLUMN job_families.code IS '職系代碼 (如: MGR, SALES)';
COMMENT ON COLUMN job_families.name IS '職系名稱 (中文)';
COMMENT ON COLUMN job_families.name_en IS '職系名稱 (英文)';
COMMENT ON COLUMN job_families.parent_secure_code IS '父職系';
COMMENT ON COLUMN job_families.description IS '職系描述';
COMMENT ON COLUMN job_families.sort_order IS '排序順序';
COMMENT ON COLUMN job_families.is_system_default IS '是否為系統預設';
COMMENT ON COLUMN job_families.is_active IS '是否啟用';
COMMENT ON COLUMN job_families.created_at IS '建立時間';
COMMENT ON COLUMN job_families.updated_at IS '更新時間';
COMMENT ON COLUMN job_families.is_deleted IS '是否已刪除';
COMMENT ON COLUMN job_families.deleted_at IS '刪除時間';

-- job_titles (職稱)
COMMENT ON TABLE job_titles IS '職稱 - 職等+職系的具體組合';
COMMENT ON COLUMN job_titles.id IS '內部自增 ID';
COMMENT ON COLUMN job_titles.secure_code IS '外部識別碼';
COMMENT ON COLUMN job_titles.org_secure_code IS '所屬企業';
COMMENT ON COLUMN job_titles.code IS '職稱代碼';
COMMENT ON COLUMN job_titles.name IS '職稱名稱 (中文)';
COMMENT ON COLUMN job_titles.name_en IS '職稱名稱 (英文)';
COMMENT ON COLUMN job_titles.short_name IS '職稱簡稱';
COMMENT ON COLUMN job_titles.job_level_secure_code IS '對應職等';
COMMENT ON COLUMN job_titles.job_family_secure_code IS '對應職系';
COMMENT ON COLUMN job_titles.description IS '職責說明';
COMMENT ON COLUMN job_titles.is_supervisor IS '是否為主管職稱';
COMMENT ON COLUMN job_titles.sort_order IS '排序順序';
COMMENT ON COLUMN job_titles.is_system_default IS '是否為系統預設';
COMMENT ON COLUMN job_titles.is_active IS '是否啟用';
COMMENT ON COLUMN job_titles.created_at IS '建立時間';
COMMENT ON COLUMN job_titles.updated_at IS '更新時間';
COMMENT ON COLUMN job_titles.is_deleted IS '是否已刪除';
COMMENT ON COLUMN job_titles.deleted_at IS '刪除時間';

-- employee_positions (企業成員職位)
COMMENT ON TABLE employee_positions IS '企業成員職位 - 紀錄企業成員的職位指派';
COMMENT ON COLUMN employee_positions.id IS '內部自增 ID';
COMMENT ON COLUMN employee_positions.secure_code IS '外部識別碼';
COMMENT ON COLUMN employee_positions.org_secure_code IS '所屬企業';
COMMENT ON COLUMN employee_positions.user_secure_code IS '企業成員';
COMMENT ON COLUMN employee_positions.job_title_secure_code IS '職稱';
COMMENT ON COLUMN employee_positions.unit_secure_code IS '所屬部門';
COMMENT ON COLUMN employee_positions.position_type IS '職位類型: PRIMARY/CONCURRENT/ACTING/TEMPORARY';
COMMENT ON COLUMN employee_positions.is_unit_head IS '是否為該部門主管';
COMMENT ON COLUMN employee_positions.dotted_line_manager_secure_code IS '虛線主管 (Matrix 組織用)';
COMMENT ON COLUMN employee_positions.effective_from IS '生效日期';
COMMENT ON COLUMN employee_positions.effective_until IS '失效日期 (NULL=無期限)';
COMMENT ON COLUMN employee_positions.remarks IS '指派原因/備註';
COMMENT ON COLUMN employee_positions.assigned_by IS '指派者';
COMMENT ON COLUMN employee_positions.assigned_at IS '指派時間';
COMMENT ON COLUMN employee_positions.is_active IS '是否啟用';
COMMENT ON COLUMN employee_positions.created_at IS '建立時間';
COMMENT ON COLUMN employee_positions.updated_at IS '更新時間';
COMMENT ON COLUMN employee_positions.is_deleted IS '是否已刪除';
COMMENT ON COLUMN employee_positions.deleted_at IS '刪除時間';

-- delegations (代理授權)
COMMENT ON TABLE delegations IS '代理授權 - 職務代理機制';
COMMENT ON COLUMN delegations.id IS '內部自增 ID';
COMMENT ON COLUMN delegations.secure_code IS '外部識別碼';
COMMENT ON COLUMN delegations.org_secure_code IS '所屬企業';
COMMENT ON COLUMN delegations.delegator_secure_code IS '授權人';
COMMENT ON COLUMN delegations.delegate_secure_code IS '被授權人 (代理人)';
COMMENT ON COLUMN delegations.delegation_type IS '代理類型: FULL/APPROVAL/SPECIFIC';
COMMENT ON COLUMN delegations.status IS '狀態: PENDING/ACTIVE/EXPIRED/REVOKED';
COMMENT ON COLUMN delegations.effective_from IS '生效日期';
COMMENT ON COLUMN delegations.effective_until IS '失效日期';
COMMENT ON COLUMN delegations.approval_limit IS '金額上限 (NULL=無上限)';
COMMENT ON COLUMN delegations.approval_currency IS '金額幣別';
COMMENT ON COLUMN delegations.allowed_process_types IS '允許的流程類型 (JSON 陣列)';
COMMENT ON COLUMN delegations.reason IS '授權原因';
COMMENT ON COLUMN delegations.created_by IS '建立者';
COMMENT ON COLUMN delegations.revoked_at IS '撤銷時間';
COMMENT ON COLUMN delegations.revoked_by IS '撤銷者';
COMMENT ON COLUMN delegations.revoke_reason IS '撤銷原因';
COMMENT ON COLUMN delegations.created_at IS '建立時間';
COMMENT ON COLUMN delegations.updated_at IS '更新時間';
COMMENT ON COLUMN delegations.is_deleted IS '是否已刪除';
COMMENT ON COLUMN delegations.deleted_at IS '刪除時間';

-- user_unit_assignments (用戶-組織單位關聯)
COMMENT ON TABLE user_unit_assignments IS '用戶-組織單位關聯表';
COMMENT ON COLUMN user_unit_assignments.id IS '內部自增 ID';
COMMENT ON COLUMN user_unit_assignments.secure_code IS '外部識別碼';
COMMENT ON COLUMN user_unit_assignments.org_secure_code IS '所屬企業';
COMMENT ON COLUMN user_unit_assignments.user_secure_code IS '用戶';
COMMENT ON COLUMN user_unit_assignments.unit_secure_code IS '組織單位';
COMMENT ON COLUMN user_unit_assignments.is_primary IS '是否為主要單位';
COMMENT ON COLUMN user_unit_assignments.assigned_at IS '指派時間';
COMMENT ON COLUMN user_unit_assignments.assigned_by IS '指派者';
COMMENT ON COLUMN user_unit_assignments.created_at IS '建立時間';
COMMENT ON COLUMN user_unit_assignments.updated_at IS '更新時間';
COMMENT ON COLUMN user_unit_assignments.is_deleted IS '是否已刪除';
COMMENT ON COLUMN user_unit_assignments.deleted_at IS '刪除時間';

-- user_role_assignments (用戶-角色關聯)
COMMENT ON TABLE user_role_assignments IS '用戶-角色關聯表';
COMMENT ON COLUMN user_role_assignments.id IS '內部自增 ID';
COMMENT ON COLUMN user_role_assignments.secure_code IS '外部識別碼';
COMMENT ON COLUMN user_role_assignments.org_secure_code IS '所屬企業';
COMMENT ON COLUMN user_role_assignments.user_secure_code IS '用戶';
COMMENT ON COLUMN user_role_assignments.role_secure_code IS '角色';
COMMENT ON COLUMN user_role_assignments.unit_secure_code IS '在哪個組織單位擔任此角色';
COMMENT ON COLUMN user_role_assignments.valid_from IS '生效日期';
COMMENT ON COLUMN user_role_assignments.valid_until IS '失效日期';
COMMENT ON COLUMN user_role_assignments.assigned_at IS '指派時間';
COMMENT ON COLUMN user_role_assignments.assigned_by IS '指派者';
COMMENT ON COLUMN user_role_assignments.created_at IS '建立時間';
COMMENT ON COLUMN user_role_assignments.updated_at IS '更新時間';
COMMENT ON COLUMN user_role_assignments.is_deleted IS '是否已刪除';
COMMENT ON COLUMN user_role_assignments.deleted_at IS '刪除時間';

-- ============================================================================
-- RBAC/ABAC 權限表 (2025-12-21 新增)
-- ============================================================================

-- permissions (權限定義)
COMMENT ON TABLE permissions IS '權限定義 - 資源+操作的組合 (全局，不屬於特定企業)';
COMMENT ON COLUMN permissions.id IS '內部自增 ID';
COMMENT ON COLUMN permissions.secure_code IS '外部識別碼';
COMMENT ON COLUMN permissions.resource_type IS '資源類型: USER/ORGANIZATION/FORM_TEMPLATE/...';
COMMENT ON COLUMN permissions.action IS '操作類型: CREATE/READ/UPDATE/DELETE/APPROVE/...';
COMMENT ON COLUMN permissions.code IS '權限代碼 (格式: resource_type:action，唯一)';
COMMENT ON COLUMN permissions.name IS '權限名稱';
COMMENT ON COLUMN permissions.description IS '權限描述';
COMMENT ON COLUMN permissions.permission_level IS '權限層級: SYSTEM/ORG/MODULE (控制誰可授予)';
COMMENT ON COLUMN permissions.is_system_permission IS '是否為系統內建權限 (不可刪除)';
COMMENT ON COLUMN permissions.is_active IS '是否啟用';
COMMENT ON COLUMN permissions.created_at IS '建立時間';
COMMENT ON COLUMN permissions.updated_at IS '更新時間';
COMMENT ON COLUMN permissions.is_deleted IS '是否已刪除';
COMMENT ON COLUMN permissions.deleted_at IS '刪除時間';

-- permission_conditions (ABAC 條件定義)
COMMENT ON TABLE permission_conditions IS 'ABAC 條件定義 - 動態權限評估規則 (全局)';
COMMENT ON COLUMN permission_conditions.id IS '內部自增 ID';
COMMENT ON COLUMN permission_conditions.secure_code IS '外部識別碼';
COMMENT ON COLUMN permission_conditions.code IS '條件代碼 (唯一)';
COMMENT ON COLUMN permission_conditions.name IS '條件名稱';
COMMENT ON COLUMN permission_conditions.description IS '條件描述';
COMMENT ON COLUMN permission_conditions.condition_type IS '條件類型: OWNERSHIP/ORG/RANK/TIME/STATUS/DELEGATE';
COMMENT ON COLUMN permission_conditions.expression IS '條件表達式 (JSON)';
COMMENT ON COLUMN permission_conditions.requires_param IS '是否需要參數';
COMMENT ON COLUMN permission_conditions.param_description IS '參數說明';
COMMENT ON COLUMN permission_conditions.is_system_condition IS '是否為系統內建條件 (不可刪除)';
COMMENT ON COLUMN permission_conditions.is_active IS '是否啟用';
COMMENT ON COLUMN permission_conditions.created_at IS '建立時間';
COMMENT ON COLUMN permission_conditions.updated_at IS '更新時間';
COMMENT ON COLUMN permission_conditions.is_deleted IS '是否已刪除';
COMMENT ON COLUMN permission_conditions.deleted_at IS '刪除時間';

-- role_permissions (角色-權限關聯)
COMMENT ON TABLE role_permissions IS '角色-權限關聯表 - 支援 ABAC 條件 (全局)';
COMMENT ON COLUMN role_permissions.id IS '內部自增 ID';
COMMENT ON COLUMN role_permissions.secure_code IS '外部識別碼';
COMMENT ON COLUMN role_permissions.role_secure_code IS '角色';
COMMENT ON COLUMN role_permissions.permission_secure_code IS '權限';
COMMENT ON COLUMN role_permissions.condition_json IS 'ABAC 條件 (JSON，可選)';
COMMENT ON COLUMN role_permissions.is_active IS '是否啟用';
COMMENT ON COLUMN role_permissions.created_at IS '建立時間';
COMMENT ON COLUMN role_permissions.updated_at IS '更新時間';
COMMENT ON COLUMN role_permissions.is_deleted IS '是否已刪除';
COMMENT ON COLUMN role_permissions.deleted_at IS '刪除時間';

-- 完成訊息
DO $$
BEGIN
    RAISE NOTICE '欄位註解已全部套用完成';
END $$;
