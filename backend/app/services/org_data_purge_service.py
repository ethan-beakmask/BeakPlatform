"""
企業資料刪除的共用核心（org_data_purge_service）

被兩個不同層面的功能共用，兩邊都不得自行複製這裡的邏輯：

- 企業層：`/organizations/` 的「硬刪除已軟刪除的企業」
  （對象是還存在於 organizations 表的軟刪除企業）
- 主機層：`/hostconfig/data-maintenance` 的「清理企業孤兒資料」
  （對象是 org_secure_code 指向已不存在企業的殘留）

表清單一律動態掃 information_schema（`get_org_scoped_tables()`），
只有真正有 FK 依賴的順序寫在 HARD_DELETE_ORDER，其餘動態帶入，
再由 `run_delete_with_retries()` 用三趟重試自我修復順序問題。
新增模組表不必改這裡。
"""
from sqlalchemy import bindparam

from app import db

# 需要固定先後順序的表（其餘由 get_org_scoped_tables() 動態帶入，排在本清單之前）
# 只列真正有 FK 依賴的，不再手工維護完整清單
HARD_DELETE_ORDER = [
    'store_installations',      # -> store_items（模組表之間唯一一條 FK）
    'store_items',
    # 以下是平台表的既有刪除順序（Phase 1 葉節點 → Phase 4 企業設定）
    'role_permissions', 'user_role_assignments', 'user_unit_assignments',
    'user_unit_memberships', 'password_reset_tokens', 'password_history',
    'delegations', 'employee_positions', 'contracts', 'personal_schedules',
    'schedule_adjustments', 'schedule_holidays', 'audit_logs',
    'timeout_trackers', 'conglomerate_logs', 'used_user_numbers',
    'user_numbering_counters', 'job_level_approval_limits',
    'menu_permissions', 'menu_role_requirements', 'broadcast_acknowledgments',
    'module_access_control', 'lookup_items', 'workflow_node_definitions',
    'workflow_node_categories', 'duties', 'duty_categories',
    'approval_categories', 'lookup_categories', 'job_titles',
    'user_numbering_rules', 'users', 'roles', 'organizational_units',
    'job_levels', 'job_families', 'menu_items', 'shift_types',
    'work_schedules', 'pages', 'modules', 'smtp_configs', 'telegram_configs',
    'recipient_groups',
]

# 無 org_secure_code 的表：透過父表間接過濾
# {table: (local_fk_column, parent_table)}
HARD_DELETE_INDIRECT = {
    'role_permissions': ('role_secure_code', 'roles'),
    'password_history': ('user_secure_code', 'users'),
    'menu_permissions': ('menu_secure_code', 'menu_items'),
    'schedule_holidays': ('schedule_secure_code', 'work_schedules'),
}

# 表名 → 中文顯示名（缺的直接顯示表名）
HARD_DELETE_DISPLAY_NAMES = {
    'role_permissions': '角色權限',
    'user_role_assignments': '用戶角色指派',
    'user_unit_assignments': '用戶單位指派',
    'user_unit_memberships': '用戶單位成員',
    'password_reset_tokens': '密碼重設 Token',
    'password_history': '密碼歷程',
    'delegations': '代理設定',
    'employee_positions': '企業成員職位',
    'contracts': '合約',
    'personal_schedules': '個人班表',
    'schedule_adjustments': '班表調整',
    'schedule_holidays': '班表假日',
    'audit_logs': '稽核日誌',
    'timeout_trackers': '逾時追蹤',
    'conglomerate_logs': '集團日誌',
    'used_user_numbers': '已用企業成員編號',
    'user_numbering_counters': '企業成員編號計數器',
    'job_level_approval_limits': '職等簽核額度',
    'menu_permissions': '選單權限',
    'menu_role_requirements': '選單角色需求',
    'broadcast_acknowledgments': '公告確認',
    'module_access_control': '模組使用權',
    'lookup_items': '查找項目',
    'workflow_node_definitions': '流程節點定義',
    'workflow_node_categories': '流程節點分類',
    'duties': '職責',
    'duty_categories': '職責分類',
    'approval_categories': '簽核類別',
    'lookup_categories': '查找分類',
    'job_titles': '職稱',
    'user_numbering_rules': '企業成員編號規則',
    'users': '用戶',
    'roles': '角色',
    'organizational_units': '組織單位',
    'job_levels': '職等',
    'job_families': '職系',
    'menu_items': '選單項目',
    'shift_types': '班別',
    'work_schedules': '班表',
    'pages': '頁面',
    'modules': '模組',
    'smtp_configs': 'SMTP 設定',
    'telegram_configs': 'Telegram 設定',
    'recipient_groups': '收件人群組',
    'organizations': '企業',
    'api_key_claims': 'API Key 領取記錄',
    'api_keys': 'API Key',
    'dc_backgrounds': '底圖 (NoCode)',
    'dc_bridge_logs': '資料橋接日誌 (NoCode)',
    'dc_crud_views': 'CRUD 視圖 (NoCode)',
    'dc_page_layouts': '頁面版面 (NoCode)',
    'dc_page_templates': '頁面樣板 (NoCode)',
    'dc_permission_policy_groups': '權限政策群組 (NoCode)',
    'dc_permission_policy_rules': '權限政策規則 (NoCode)',
    'dc_shared_components': '共用元件 (NoCode)',
    'dc_shared_menus': '共用選單 (NoCode)',
    'dc_site_map_nodes': 'Site Map 節點 (NoCode)',
    'dc_site_map_permissions': 'Site Map 權限 (NoCode)',
    'dc_sub_system_pages': '子系統頁面掛載 (NoCode)',
    'dc_sub_system_template_hides': '子系統樣板隱藏 (NoCode)',
    'dc_sub_systems': '子系統 (NoCode)',
    'egress_audit_logs': '出口稽核日誌',
    'egress_field_policies': '出口欄位政策',
    'egress_tier_thresholds': '出口層級門檻',
    'file_access_logs': '檔案存取日誌',
    'fw_ai_usage_records': 'AI 用量記錄 (FormFlow)',
    'fw_approval_records': '簽核記錄 (FormFlow)',
    'fw_categories': '分類 (FormFlow)',
    'fw_column_display_config': '欄位顯示設定 (FormFlow)',
    'fw_demo_inventory': '示範庫存 (FormFlow)',
    'fw_form_field_changes': '欄位變更記錄 (FormFlow)',
    'fw_form_instances': '表單實例 (FormFlow)',
    'fw_form_templates': '表單範本 (FormFlow)',
    'fw_form_themes': '表單主題 (FormFlow)',
    'fw_form_workflow_mappings': '表單流程對應 (FormFlow)',
    'fw_mapping_permissions': '配對權限 (FormFlow)',
    'fw_node_execution_logs': '節點執行日誌 (FormFlow)',
    'fw_node_execution_queue': '節點執行佇列 (FormFlow)',
    'fw_org_databases': '企業資料庫 (FormFlow)',
    'fw_published_form_workflows': '已發行表單流程 (FormFlow)',
    'fw_spec_schema': '規格 Schema (SpecFormulate)',
    'fw_spec_schema_histories': '規格 Schema 歷程 (SpecFormulate)',
    'fw_sql_form_registries': 'SQL 同步登錄 (FormFlow)',
    'fw_sql_procedures': 'SQL 白名單程序 (FormFlow)',
    'fw_sync_queue': '同步佇列 (FormFlow)',
    'fw_workflow_backgrounds': '流程背景圖 (FormFlow)',
    'fw_workflow_instances': '流程實例 (FormFlow)',
    'fw_workflow_templates': '流程範本 (FormFlow)',
    'fw_workflow_variables': '流程變數 (FormFlow)',
    'od_defense_decisions': '防禦決策 (OpenDefense)',
    'od_form_template_mappings': '表單路由規則 (OpenDefense)',
    'od_intake_events': '受理事件 (OpenDefense)',
    'od_payload_profiles': 'Payload 設定檔 (OpenDefense)',
    'od_protected_targets': '封鎖保護清單 (OpenDefense)',
    'od_service_accounts': '服務帳號 (OpenDefense)',
    'org_encryption_keys': '企業加密金鑰',
    'platform_files': '平台檔案',
    'store_installations': '模組安裝記錄',
    'store_items': '模組商店項目',
}

ORG_DISPLAY_NAME = HARD_DELETE_DISPLAY_NAMES['organizations']


def physical_error_entry(error):
    resource = error.get('resource', '')
    return {
        'table': '',
        'display_name': resource,
        'error': error.get('error', ''),
        'resource': resource,
    }




def get_org_scoped_tables():
    """動態取得所有帶 org_secure_code 欄位的表名（set）。

    取代手工維護的表清單 —— 新模組加表後不必再改這裡。
    """
    result = db.session.execute(db.text(
        "SELECT table_name FROM information_schema.columns "
        "WHERE table_schema = 'public' AND column_name = 'org_secure_code'"
    ))
    return {row[0] for row in result}


def table_exists(table_name):
    """檢查 public schema 內是否存在指定表。"""
    result = db.session.execute(db.text(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_name = :table"
    ), {'table': table_name})
    return result.scalar() is not None


def build_hard_delete_sequence():
    """回傳 (ordered_tables, all_tables)。

    ordered_tables: 實際要刪的表名清單，不含 organizations。
      順序 = [動態掃到但不在 HARD_DELETE_ORDER 內的表（sorted）]
             + [HARD_DELETE_ORDER 內且實際存在的表]
    動態表排前面的理由：模組表沒有 FK 指向平台表（已查證），
    未知的新表當成子表先刪最安全。
    """
    org_scoped_tables = get_org_scoped_tables()
    indirect_tables = {table for table in HARD_DELETE_INDIRECT if table_exists(table)}
    all_tables = (org_scoped_tables | indirect_tables) - {'organizations'}
    ordered_set = set(HARD_DELETE_ORDER)
    ordered_tables = sorted(all_tables - ordered_set)
    ordered_tables.extend(table for table in HARD_DELETE_ORDER if table in all_tables)
    return ordered_tables, all_tables


def hard_delete_stmts(table_name, all_tables):
    """回傳 (count_stmt, delete_stmt)，兩者都用 expanding bindparam :orgs。"""
    if table_name not in all_tables:
        raise ValueError('table not allowed')

    if table_name in HARD_DELETE_INDIRECT:
        fk_col, parent = HARD_DELETE_INDIRECT[table_name]
        sub = f"SELECT secure_code FROM {parent} WHERE org_secure_code IN :orgs"
        count_sql = f"SELECT COUNT(*) FROM {table_name} WHERE {fk_col} IN ({sub})"
        delete_sql = f"DELETE FROM {table_name} WHERE {fk_col} IN ({sub})"
    else:
        count_sql = f"SELECT COUNT(*) FROM {table_name} WHERE org_secure_code IN :orgs"
        delete_sql = f"DELETE FROM {table_name} WHERE org_secure_code IN :orgs"
    param = bindparam('orgs', expanding=True)
    return (
        db.text(count_sql).bindparams(param),
        db.text(delete_sql).bindparams(param),
    )


def orphan_count_stmt(table_name, org_scoped_tables):
    """回傳指定 org-scoped 表的孤兒計數 statement。"""
    if table_name not in org_scoped_tables:
        raise ValueError('table not allowed')

    sql = (
        f"SELECT COUNT(*) FROM {table_name} x "
        "WHERE x.org_secure_code IS NOT NULL "
        "AND NOT EXISTS ("
        "SELECT 1 FROM organizations o WHERE o.secure_code = x.org_secure_code"
        ")"
    )
    return db.text(sql)


def orphan_group_stmt(table_name, org_scoped_tables):
    """回傳指定 org-scoped 表依 org_secure_code 彙總孤兒數的 statement。"""
    if table_name not in org_scoped_tables:
        raise ValueError('table not allowed')

    sql = (
        f"SELECT x.org_secure_code, COUNT(*) FROM {table_name} x "
        "WHERE x.org_secure_code IS NOT NULL "
        "AND NOT EXISTS ("
        "SELECT 1 FROM organizations o WHERE o.secure_code = x.org_secure_code"
        ") "
        "GROUP BY x.org_secure_code"
    )
    return db.text(sql)


def orphan_delete_stmt(table_name, org_scoped_tables):
    """回傳指定 org-scoped 表的孤兒刪除 statement。"""
    if table_name not in org_scoped_tables:
        raise ValueError('table not allowed')

    sql = (
        f"DELETE FROM {table_name} x "
        "WHERE x.org_secure_code IS NOT NULL "
        "AND NOT EXISTS ("
        "SELECT 1 FROM organizations o WHERE o.secure_code = x.org_secure_code"
        ")"
    )
    return db.text(sql)


def run_delete_with_retries(ordered_tables, stmt_builder):
    """以 SAVEPOINT + 最多三趟重試刪除，回傳 (counts, errors)。"""
    deleted_counts = {}
    pending = list(ordered_tables)
    last_errors = {}

    for _pass in range(3):
        failed = []
        for table_name in pending:
            try:
                with db.session.begin_nested():
                    built = stmt_builder(table_name)
                    if isinstance(built, tuple):
                        delete_stmt, params = built
                    else:
                        delete_stmt, params = built, {}
                    res = db.session.execute(delete_stmt, params)
                    if res.rowcount > 0:
                        deleted_counts[table_name] = deleted_counts.get(table_name, 0) + res.rowcount
            except Exception as e:
                failed.append(table_name)
                last_errors[table_name] = str(e)
        if not failed or len(failed) == len(pending):
            pending = failed
            break
        pending = failed

    errors = [
        {
            'table': table_name,
            'display_name': HARD_DELETE_DISPLAY_NAMES.get(table_name, table_name),
            'error': last_errors[table_name],
        }
        for table_name in pending
    ]
    return deleted_counts, errors


