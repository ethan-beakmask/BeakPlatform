"""
BeakMask Host Config
主機設定區 - 系統管理員專用

用途：
- 伺服器設定 (E-MailRelay 等)
- 資料維護 (硬刪除、清除標記刪除資料)
- 其他主機級操作
"""
from flask import Blueprint, render_template, jsonify, request, redirect, url_for
from flask_babel import gettext as _
from sqlalchemy import bindparam

from app.security.decorators import system_admin_required
from app import db
from app.services.org_physical_cleanup_service import (
    collect_org_file_records,
    delete_org_files,
    delete_physical_orphans,
    list_org_existing_directories,
    list_org_database_manual_items,
    remove_org_directories,
    scan_physical_orphans,
)

hostconfig_bp = Blueprint('hostconfig', __name__)

# 需要固定先後順序的表（其餘由 _get_org_scoped_tables() 動態帶入，排在本清單之前）
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

_ORG_DISPLAY_NAME = HARD_DELETE_DISPLAY_NAMES['organizations']


def _physical_error_for_hostconfig(error):
    resource = error.get('resource', '')
    return {
        'table': '',
        'display_name': resource,
        'error': error.get('error', ''),
        'resource': resource,
    }


@hostconfig_bp.route('/')
@system_admin_required
def index():
    """主機設定首頁 - 重導向至伺服器設定"""
    return redirect(url_for('hostconfig.server_settings'))


@hostconfig_bp.route('/data-maintenance')
@system_admin_required
def data_maintenance():
    """資料維護頁面 - 硬刪除、清除軟刪除記錄"""
    return render_template('pages/hostconfig/data_maintenance.html')


@hostconfig_bp.route('/server-settings')
@system_admin_required
def server_settings():
    """
    伺服器設定頁面 (系統級)

    這是系統管理員專用的伺服器級設定，
    與企業級「系統設定」(/admin/settings) 區分。

    左右結構：
    - 左側：設定分類選單
    - 右側：設定內容

    設定分類：
    - E-MailRelay：系統郵件服務設定
    """
    return render_template('pages/hostconfig/system_settings.html')


def _get_org_scoped_tables():
    """動態取得所有帶 org_secure_code 欄位的表名（set）。

    取代手工維護的表清單 —— 新模組加表後不必再改這裡。
    """
    result = db.session.execute(db.text(
        "SELECT table_name FROM information_schema.columns "
        "WHERE table_schema = 'public' AND column_name = 'org_secure_code'"
    ))
    return {row[0] for row in result}


def _table_exists(table_name):
    """檢查 public schema 內是否存在指定表。"""
    result = db.session.execute(db.text(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_name = :table"
    ), {'table': table_name})
    return result.scalar() is not None


def _build_hard_delete_sequence():
    """回傳 (ordered_tables, all_tables)。

    ordered_tables: 實際要刪的表名清單，不含 organizations。
      順序 = [動態掃到但不在 HARD_DELETE_ORDER 內的表（sorted）]
             + [HARD_DELETE_ORDER 內且實際存在的表]
    動態表排前面的理由：模組表沒有 FK 指向平台表（已查證），
    未知的新表當成子表先刪最安全。
    """
    org_scoped_tables = _get_org_scoped_tables()
    indirect_tables = {table for table in HARD_DELETE_INDIRECT if _table_exists(table)}
    all_tables = (org_scoped_tables | indirect_tables) - {'organizations'}
    ordered_set = set(HARD_DELETE_ORDER)
    ordered_tables = sorted(all_tables - ordered_set)
    ordered_tables.extend(table for table in HARD_DELETE_ORDER if table in all_tables)
    return ordered_tables, all_tables


def _hard_delete_stmts(table_name, all_tables):
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


def _orphan_count_stmt(table_name, org_scoped_tables):
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


def _orphan_group_stmt(table_name, org_scoped_tables):
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


def _orphan_delete_stmt(table_name, org_scoped_tables):
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


def _run_delete_with_retries(ordered_tables, stmt_builder):
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


@hostconfig_bp.route('/hard-delete/preview', methods=['GET'])
@system_admin_required
def hard_delete_preview():
    """
    預覽硬刪除將刪除的資料

    Returns:
        - deleted_orgs: 已軟刪除的企業列表
        - table_counts: 各表預計刪除的筆數
    """
    try:
        # 繞過 RLS，確保能看到所有企業隔離的資料
        db.session.execute(db.text("SET LOCAL app.is_system_admin = 'true'"))

        # 取得已軟刪除的企業
        result = db.session.execute(db.text(
            "SELECT secure_code, code, name, domain_name "
            "FROM organizations WHERE is_deleted = true"
        ))
        deleted_orgs = [
            {'secure_code': row[0], 'code': row[1], 'name': row[2], 'domain_name': row[3]}
            for row in result
        ]

        if not deleted_orgs:
            return jsonify({
                'success': True,
                'deleted_orgs': [],
                'table_counts': [],
                'physical': {
                    'file_count': 0,
                    'directories': [],
                    'manual_required': [],
                },
                'message': _('沒有已軟刪除的企業')
            })

        # 取得各表預計刪除的筆數
        org_codes = [org['secure_code'] for org in deleted_orgs]
        ordered_tables, all_tables = _build_hard_delete_sequence()

        table_counts = []
        for table_name in ordered_tables:
            try:
                with db.session.begin_nested():
                    count_stmt, _unused = _hard_delete_stmts(table_name, all_tables)
                    count = db.session.execute(count_stmt, {'orgs': org_codes}).scalar()
                    if count > 0:
                        table_counts.append({
                            'table': table_name,
                            'display_name': HARD_DELETE_DISPLAY_NAMES.get(table_name, table_name),
                            'count': count
                        })
            except Exception:
                # savepoint 自動 rollback，表可能不存在，跳過
                pass

        table_counts.append({
            'table': 'organizations',
            'display_name': HARD_DELETE_DISPLAY_NAMES.get('organizations', 'organizations'),
            'count': len(deleted_orgs),
        })
        physical = {
            'file_count': len(collect_org_file_records(org_codes)),
            'directories': list_org_existing_directories(org_codes),
            'manual_required': list_org_database_manual_items(org_codes),
        }

        return jsonify({
            'success': True,
            'deleted_orgs': deleted_orgs,
            'table_counts': table_counts,
            'physical': physical,
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@hostconfig_bp.route('/hard-delete/execute', methods=['POST'])
@system_admin_required
def hard_delete_execute():
    """
    執行硬刪除

    刪除所有已軟刪除企業的相關資料（永久刪除，無法復原）
    """
    try:
        # 繞過 RLS，確保能刪除所有企業隔離的資料
        db.session.execute(db.text("SET LOCAL app.is_system_admin = 'true'"))

        # 取得已軟刪除的企業
        result = db.session.execute(db.text(
            "SELECT secure_code FROM organizations WHERE is_deleted = true"
        ))
        org_codes = [row[0] for row in result]

        if not org_codes:
            return jsonify({
                'success': True,
                'message': _('沒有需要刪除的資料'),
                'deleted_counts': {},
                'has_errors': False,
                'errors': [],
                'physical': {
                    'files_deleted': 0,
                    'files_missing': 0,
                    'dirs_removed': [],
                    'manual_required': [],
                },
            })

        deleted_counts = {}
        errors = []
        manual_items = list_org_database_manual_items(org_codes)
        file_result = delete_org_files(org_codes)
        ordered_tables, all_tables = _build_hard_delete_sequence()

        # 按順序刪除各表（用 SAVEPOINT 隔離個別表的錯誤）
        table_counts, table_errors = _run_delete_with_retries(
            ordered_tables,
            lambda table_name: (
                _hard_delete_stmts(table_name, all_tables)[1],
                {'orgs': org_codes},
            ),
        )
        for table_name, count in table_counts.items():
            display_name = HARD_DELETE_DISPLAY_NAMES.get(table_name, table_name)
            deleted_counts[display_name] = deleted_counts.get(display_name, 0) + count
        errors.extend(table_errors)

        try:
            with db.session.begin_nested():
                result = db.session.execute(db.text(
                    "DELETE FROM organizations WHERE is_deleted = true"
                ))
                if result.rowcount > 0:
                    deleted_counts[_ORG_DISPLAY_NAME] = result.rowcount
        except Exception as e:
            errors.append({
                'table': 'organizations',
                'display_name': _ORG_DISPLAY_NAME,
                'error': str(e),
            })

        db.session.commit()
        dir_result = remove_org_directories(org_codes)
        errors.extend(_physical_error_for_hostconfig(error) for error in file_result['errors'])
        errors.extend(_physical_error_for_hostconfig(error) for error in dir_result['errors'])
        for error in errors:
            deleted_counts[f"{error['display_name']} (錯誤)"] = error['error']

        return jsonify({
            'success': True,
            'message': (
                _('刪除過程有 %(n)s 項失敗，企業可能未完全刪除', n=len(errors))
                if errors else _('已刪除 %(count)s 個企業及其相關資料', count=len(org_codes))
            ),
            'deleted_counts': deleted_counts,
            'has_errors': bool(errors),
            'errors': errors,
            'physical': {
                'files_deleted': file_result['files_deleted'],
                'files_missing': file_result['files_missing'],
                'dirs_removed': dir_result['dirs_removed'],
                'manual_required': manual_items,
            },
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@hostconfig_bp.route('/orphan-cleanup/preview', methods=['GET'])
@system_admin_required
def orphan_cleanup_preview():
    """預覽指向已不存在企業的孤兒資料。"""
    try:
        # 繞過 RLS，確保能看到所有企業隔離的資料
        db.session.execute(db.text("SET LOCAL app.is_system_admin = 'true'"))

        ordered_tables, _all_tables = _build_hard_delete_sequence()
        org_scoped_tables = _get_org_scoped_tables() - {'organizations'}
        ordered_tables = [table for table in ordered_tables if table in org_scoped_tables]
        tables_with_counts = []
        orphan_org_totals = {}
        total = 0

        for table_name in ordered_tables:
            try:
                with db.session.begin_nested():
                    count = db.session.execute(
                        _orphan_count_stmt(table_name, org_scoped_tables)
                    ).scalar()
                    if count and count > 0:
                        display_name = HARD_DELETE_DISPLAY_NAMES.get(table_name, table_name)
                        tables_with_counts.append({
                            'table': table_name,
                            'display_name': display_name,
                            'count': count,
                        })
                        total += count

                        rows = db.session.execute(
                            _orphan_group_stmt(table_name, org_scoped_tables)
                        )
                        for row in rows:
                            org_secure_code = row[0]
                            orphan_org_totals[org_secure_code] = (
                                orphan_org_totals.get(org_secure_code, 0) + row[1]
                            )
            except Exception:
                pass

        orphan_orgs = [
            {'org_secure_code': org, 'count': count}
            for org, count in sorted(
                orphan_org_totals.items(),
                key=lambda item: (-item[1], item[0]),
            )
        ]

        return jsonify({
            'success': True,
            'tables': tables_with_counts,
            'orphan_orgs': orphan_orgs,
            'total': total,
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@hostconfig_bp.route('/orphan-cleanup/execute', methods=['POST'])
@system_admin_required
def orphan_cleanup_execute():
    """刪除所有孤兒記錄（永久，無法復原）。"""
    try:
        # 繞過 RLS，確保能刪除所有企業隔離的資料
        db.session.execute(db.text("SET LOCAL app.is_system_admin = 'true'"))

        ordered_tables, _all_tables = _build_hard_delete_sequence()
        org_scoped_tables = _get_org_scoped_tables() - {'organizations'}
        ordered_tables = [table for table in ordered_tables if table in org_scoped_tables]

        deleted_counts, errors = _run_delete_with_retries(
            ordered_tables,
            lambda table_name: _orphan_delete_stmt(table_name, org_scoped_tables),
        )

        db.session.commit()

        results = [
            {
                'table': table_name,
                'display_name': HARD_DELETE_DISPLAY_NAMES.get(table_name, table_name),
                'deleted': deleted_counts[table_name],
            }
            for table_name in ordered_tables
            if table_name in deleted_counts
        ]
        total_deleted = sum(deleted_counts.values())

        return jsonify({
            'success': True,
            'message': (
                _('孤兒資料清理有 %(n)s 張表失敗', n=len(errors))
                if errors else _('已清理 %(count)s 筆企業孤兒資料', count=total_deleted)
            ),
            'results': results,
            'total_deleted': total_deleted,
            'has_errors': bool(errors),
            'errors': errors,
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@hostconfig_bp.route('/physical-orphans/preview', methods=['GET'])
@system_admin_required
def physical_orphans_preview():
    """預覽實體層企業孤兒資源。"""
    try:
        # 繞過 RLS，確保能看到所有企業隔離的資料
        db.session.execute(db.text("SET LOCAL app.is_system_admin = 'true'"))

        return jsonify({
            'success': True,
            **scan_physical_orphans(),
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@hostconfig_bp.route('/physical-orphans/execute', methods=['POST'])
@system_admin_required
def physical_orphans_execute():
    """刪除實體層企業孤兒資源；企業獨立資料庫只列人工處理清單。"""
    try:
        # 繞過 RLS，確保能看到所有企業隔離的資料
        db.session.execute(db.text("SET LOCAL app.is_system_admin = 'true'"))

        return jsonify({
            'success': True,
            'message': _('已清理實體層企業孤兒資源'),
            **delete_physical_orphans(),
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


# ============================================================
# 清除標記刪除的資料 (Purge soft-deleted records)
# 與「硬刪除已軟刪除的企業」不同：
# - 硬刪除：刪除整個被標記刪除的企業及其所有資料
# - 清除：刪除各表中 is_deleted=true 的個別記錄
# ============================================================

# 各表中文顯示名稱
PURGE_DISPLAY_NAMES = {
    'role_permissions': '角色權限',
    'user_role_assignments': '用戶角色指派',
    'user_unit_assignments': '用戶單位指派',
    'user_unit_memberships': '用戶單位成員',
    'delegations': '代理設定',
    'employee_positions': '企業成員職位',
    'contracts': '合約',
    'personal_schedules': '個人班表',
    'schedule_adjustments': '班表調整',
    'password_reset_tokens': '密碼重設 Token',
    'audit_logs': '稽核日誌',
    'used_user_numbers': '已用企業成員編號',
    'user_numbering_counters': '企業成員編號計數器',
    'job_level_approval_limits': '職等簽核額度',
    'approval_categories': '簽核類別',
    'conglomerate_logs': '集團日誌',
    'schedule_holidays': '班表假日',
    'duties': '職責',
    'menu_permissions': '選單權限',
    'menu_role_requirements': '選單角色需求',
    'broadcast_acknowledgments': '公告確認',
    'duty_categories': '職責分類',
    'job_titles': '職稱',
    'users': '用戶',
    'roles': '角色',
    'organizational_units': '組織單位',
    'job_levels': '職等',
    'job_families': '職系',
    'menu_items': '選單項目',
    'pages': '頁面',
    'modules': '模組',
    'work_schedules': '班表',
    'shift_types': '班別',
    'smtp_configs': 'SMTP 設定',
    'telegram_configs': 'Telegram 設定',
    'recipient_groups': '收件人群組',
    'user_numbering_rules': '企業成員編號規則',
    'conglomerates': '集團',
    'permissions': '權限',
    'permission_conditions': '權限條件',
    'system_settings': '系統設定',
    # FormFlow 模組
    'fw_approval_records': '簽核記錄 (FormFlow)',
    'fw_form_field_changes': '欄位變更記錄 (FormFlow)',
    'fw_node_execution_logs': '節點執行日誌 (FormFlow)',
    'fw_node_execution_queue': '節點執行佇列 (FormFlow)',
    'fw_sync_queue': '同步佇列 (FormFlow)',
    'fw_workflow_backgrounds': '流程背景圖 (FormFlow)',
    'fw_sql_form_registries': 'SQL 同步登錄 (FormFlow)',
    'fw_published_form_workflows': '已發行表單流程 (FormFlow)',
    'fw_form_workflow_mappings': '表單流程對應 (FormFlow)',
    'fw_form_instances': '表單實例 (FormFlow)',
    'fw_workflow_instances': '流程實例 (FormFlow)',
    'fw_categories': '分類 (FormFlow)',
    'fw_form_templates': '表單範本 (FormFlow)',
    'fw_workflow_templates': '流程範本 (FormFlow)',
    'fw_org_databases': '企業資料庫 (FormFlow)',
    # 平台流程節點定義（仍在使用）
    'workflow_node_definitions': '流程節點定義',
}

# 不納入清除範圍的表（由其他功能處理或不適合自動清除）
PURGE_EXCLUDE_TABLES = {'organizations'}

# 刪除順序（子表在前，父表在後）
PURGE_DELETE_ORDER = [
    # Phase 1: 純葉節點
    'role_permissions', 'user_role_assignments', 'user_unit_assignments',
    'user_unit_memberships', 'delegations', 'employee_positions', 'contracts',
    'personal_schedules', 'schedule_adjustments', 'password_reset_tokens',
    'audit_logs', 'used_user_numbers', 'user_numbering_counters',
    'job_level_approval_limits', 'approval_categories', 'conglomerate_logs',
    'schedule_holidays', 'duties', 'menu_permissions',
    'menu_role_requirements', 'broadcast_acknowledgments',
    'permission_conditions',
    # FormFlow 葉節點
    'fw_approval_records', 'fw_form_field_changes', 'fw_node_execution_logs',
    'fw_node_execution_queue', 'fw_sync_queue', 'fw_workflow_backgrounds',
    'fw_sql_form_registries', 'fw_published_form_workflows',
    'fw_form_workflow_mappings',
    # Phase 2: 中層表
    'duty_categories', 'job_titles', 'users',
    'fw_form_instances', 'fw_workflow_instances', 'fw_categories',
    # Phase 3: 上層表
    'roles', 'organizational_units', 'job_levels', 'job_families',
    'menu_items', 'pages', 'modules', 'work_schedules', 'shift_types',
    'fw_form_templates', 'fw_workflow_templates', 'fw_org_databases',
    'workflow_node_definitions',
    'permissions',
    # Phase 4: 頂層表
    'smtp_configs', 'telegram_configs', 'recipient_groups',
    'user_numbering_rules', 'system_settings', 'conglomerates',
]

# 無 org_secure_code 的表 - 透過父表間接過濾
# 格式: {table: (local_fk_col, parent_table, parent_pk_col)}
PURGE_INDIRECT_ORG_FILTER = {
    'role_permissions': ('role_secure_code', 'roles', 'secure_code'),
    'menu_permissions': ('menu_secure_code', 'menu_items', 'secure_code'),
    'schedule_holidays': ('schedule_secure_code', 'work_schedules', 'secure_code'),
}

# 系統級表（無企業關聯，僅在 scope=all 時處理）
PURGE_SYSTEM_TABLES = {
    'permissions', 'permission_conditions', 'system_settings', 'conglomerates',
}

# 孤兒清理：刪除 soft-deleted 父記錄前，先處理指向它的子記錄
# 格式: {parent_table: [(child_table, fk_column, action)]}
# action: 'delete'（預設）= 刪除子記錄, 'set_null' = FK 欄位置 NULL
PURGE_ORPHAN_CLEANUP = {
    'users': [
        # NOT NULL FK -- 刪除子記錄
        ('user_role_assignments', 'user_secure_code', 'delete'),
        ('user_unit_assignments', 'user_secure_code', 'delete'),
        ('user_unit_memberships', 'user_secure_code', 'delete'),
        ('delegations', 'delegator_secure_code', 'delete'),
        ('delegations', 'delegate_secure_code', 'delete'),
        ('employee_positions', 'user_secure_code', 'delete'),
        ('personal_schedules', 'user_secure_code', 'delete'),
        ('schedule_adjustments', 'user_secure_code', 'delete'),
        ('broadcast_acknowledgments', 'user_secure_code', 'delete'),
        ('password_history', 'user_secure_code', 'delete'),
        ('timeout_trackers', 'assignee_secure_code', 'delete'),
        # NULLABLE FK -- 保留子記錄，置 NULL
        ('audit_logs', 'user_secure_code', 'set_null'),
        ('used_user_numbers', 'user_secure_code', 'set_null'),
        ('contracts', 'created_by_secure_code', 'set_null'),
        ('contracts', 'modified_by_secure_code', 'set_null'),
        ('employee_positions', 'direct_manager_secure_code', 'set_null'),
        ('employee_positions', 'dotted_line_manager_secure_code', 'set_null'),
        ('schedule_adjustments', 'substitute_user_secure_code', 'set_null'),
        # 自引用 (nullable)
        ('users', 'bound_employee_secure_code', 'set_null'),
    ],
    'roles': [
        ('role_permissions', 'role_secure_code', 'delete'),
        ('user_role_assignments', 'role_secure_code', 'delete'),
        ('menu_role_requirements', 'role_secure_code', 'delete'),
        # 自引用 (nullable)
        ('roles', 'parent_secure_code', 'set_null'),
        ('roles', 'inherits_from_secure_code', 'set_null'),
    ],
    'organizational_units': [
        ('user_unit_assignments', 'unit_secure_code', 'delete'),
        ('user_unit_memberships', 'unit_secure_code', 'delete'),
        ('duties', 'unit_secure_code', 'delete'),
        ('employee_positions', 'unit_secure_code', 'delete'),
        # NULLABLE FK
        ('roles', 'bound_unit_secure_code', 'set_null'),
        ('user_role_assignments', 'unit_secure_code', 'set_null'),
        ('users', 'primary_unit_secure_code', 'set_null'),
        # 自引用 (nullable)
        ('organizational_units', 'parent_secure_code', 'set_null'),
    ],
    'menu_items': [
        ('menu_permissions', 'menu_secure_code', 'delete'),
        ('menu_role_requirements', 'menu_secure_code', 'delete'),
        # 自引用 (nullable)
        ('menu_items', 'parent_secure_code', 'set_null'),
    ],
    'work_schedules': [
        ('schedule_holidays', 'schedule_secure_code', 'delete'),
        ('users', 'work_schedule_secure_code', 'set_null'),
    ],
    'shift_types': [
        ('personal_schedules', 'shift_type_secure_code', 'set_null'),
    ],
    'job_titles': [
        ('employee_positions', 'job_title_secure_code', 'delete'),
    ],
    'job_levels': [
        ('job_level_approval_limits', 'job_level_secure_code', 'delete'),
        ('job_titles', 'job_level_secure_code', 'delete'),
    ],
    'job_families': [
        ('job_titles', 'job_family_secure_code', 'delete'),
        # 自引用 (nullable)
        ('job_families', 'parent_secure_code', 'set_null'),
    ],
    'approval_categories': [
        ('job_level_approval_limits', 'category_secure_code', 'delete'),
    ],
    'modules': [
        ('menu_items', 'module_secure_code', 'set_null'),
        ('pages', 'module_secure_code', 'set_null'),
    ],
    'permissions': [
        ('role_permissions', 'permission_secure_code', 'delete'),
    ],
    'user_numbering_rules': [
        ('user_numbering_counters', 'rule_secure_code', 'delete'),
        ('used_user_numbers', 'rule_secure_code', 'set_null'),
    ],
    'conglomerates': [
        ('conglomerate_logs', 'conglomerate_secure_code', 'delete'),
        ('organizations', 'conglomerate_secure_code', 'set_null'),
    ],
    'fw_form_templates': [
        ('fw_form_workflow_mappings', 'form_template_secure_code', 'delete'),
        ('fw_published_form_workflows', 'source_form_template_secure_code', 'delete'),
        ('fw_form_instances', 'form_template_secure_code', 'delete'),
    ],
    'fw_workflow_templates': [
        ('fw_form_workflow_mappings', 'workflow_template_secure_code', 'delete'),
        ('fw_published_form_workflows', 'source_workflow_template_secure_code', 'delete'),
        ('fw_workflow_instances', 'workflow_template_secure_code', 'delete'),
    ],
}


def _get_purge_tables():
    """動態取得所有有 is_deleted 欄位的表"""
    result = db.session.execute(db.text(
        "SELECT table_name FROM information_schema.columns "
        "WHERE column_name = 'is_deleted' AND table_schema = 'public' "
        "ORDER BY table_name"
    ))
    return {row[0] for row in result}


_column_cache = {}


def _has_column(table_name, column_name):
    """檢查表是否有指定欄位（帶快取，避免重複查詢）"""
    key = (table_name, column_name)
    if key in _column_cache:
        return _column_cache[key]
    try:
        with db.session.begin_nested():
            result = db.session.execute(db.text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = :table AND column_name = :col "
                "AND table_schema = 'public'"
            ), {'table': table_name, 'col': column_name})
            found = result.scalar() is not None
    except Exception:
        found = False
    _column_cache[key] = found
    return found


def _purge_count_sql(table_name, scope):
    """
    產生計數 SQL (只計 is_deleted=true 的記錄)

    Args:
        table_name: 表名
        scope: 'all' 或 org_secure_code
    Returns:
        (sql_string, params_dict) 或 None（表示此表在此 scope 下不適用）
    """
    params = {}

    if scope == 'all':
        return f"SELECT COUNT(*) FROM {table_name} WHERE is_deleted = true", params

    # 特定企業 scope
    if table_name in PURGE_SYSTEM_TABLES:
        return None  # 系統表不適用企業 scope

    if table_name in PURGE_INDIRECT_ORG_FILTER:
        fk_col, parent_table, parent_pk = PURGE_INDIRECT_ORG_FILTER[table_name]
        sql = (
            f"SELECT COUNT(*) FROM {table_name} "
            f"WHERE is_deleted = true AND {fk_col} IN "
            f"(SELECT {parent_pk} FROM {parent_table} WHERE org_secure_code = :org)"
        )
        params['org'] = scope
        return sql, params

    if _has_column(table_name, 'org_secure_code'):
        sql = (
            f"SELECT COUNT(*) FROM {table_name} "
            f"WHERE is_deleted = true AND org_secure_code = :org"
        )
        params['org'] = scope
        return sql, params

    return None  # 無法按企業過濾


def _purge_delete_sql(table_name, scope):
    """
    產生刪除 SQL (刪除 is_deleted=true 的記錄)

    Returns:
        (sql_string, params_dict) 或 None
    """
    params = {}

    if scope == 'all':
        return f"DELETE FROM {table_name} WHERE is_deleted = true", params

    if table_name in PURGE_SYSTEM_TABLES:
        return None

    if table_name in PURGE_INDIRECT_ORG_FILTER:
        fk_col, parent_table, parent_pk = PURGE_INDIRECT_ORG_FILTER[table_name]
        sql = (
            f"DELETE FROM {table_name} "
            f"WHERE is_deleted = true AND {fk_col} IN "
            f"(SELECT {parent_pk} FROM {parent_table} WHERE org_secure_code = :org)"
        )
        params['org'] = scope
        return sql, params

    if _has_column(table_name, 'org_secure_code'):
        sql = (
            f"DELETE FROM {table_name} "
            f"WHERE is_deleted = true AND org_secure_code = :org"
        )
        params['org'] = scope
        return sql, params

    return None


def _purge_orphan_cleanup(parent_table, scope):
    """
    清理孤兒記錄：處理指向 soft-deleted 父記錄的子記錄

    支援兩種動作：
    - delete: 刪除子記錄（NOT NULL FK 或無意義的關聯記錄）
    - set_null: FK 欄位置 NULL（保留子記錄，如稽核日誌）

    Returns:
        dict {child_table: affected_count}
    """
    if parent_table not in PURGE_ORPHAN_CLEANUP:
        return {}

    results = {}
    has_org = _has_column(parent_table, 'org_secure_code')

    # 建立父表 subquery
    if scope == 'all' or not has_org:
        parent_subquery = f"SELECT secure_code FROM {parent_table} WHERE is_deleted = true"
        params = {}
    else:
        parent_subquery = (
            f"SELECT secure_code FROM {parent_table} "
            f"WHERE is_deleted = true AND org_secure_code = :org"
        )
        params = {'org': scope}

    for entry in PURGE_ORPHAN_CLEANUP[parent_table]:
        child_table, fk_col = entry[0], entry[1]
        action = entry[2] if len(entry) > 2 else 'delete'

        try:
            with db.session.begin_nested():
                if action == 'set_null':
                    sql = (
                        f"UPDATE {child_table} SET {fk_col} = NULL "
                        f"WHERE {fk_col} IN ({parent_subquery})"
                    )
                else:
                    sql = (
                        f"DELETE FROM {child_table} "
                        f"WHERE {fk_col} IN ({parent_subquery})"
                    )
                result = db.session.execute(db.text(sql), params)
                if result.rowcount > 0:
                    results[child_table] = results.get(child_table, 0) + result.rowcount
        except Exception:
            pass  # savepoint 自動 rollback，不影響外部交易

    return results


@hostconfig_bp.route('/purge-deleted/preview', methods=['GET'])
@system_admin_required
def purge_deleted_preview():
    """
    預覽清除標記刪除的資料

    Query params:
        scope: 'all' 或 org_secure_code

    Returns:
        - tables: [{table, display_name, count}]  有 soft-deleted 記錄的表
        - orgs: [{secure_code, name, domain_name}]  活躍企業列表（供前端選擇）
    """
    try:
        # 繞過 RLS，確保能看到所有企業隔離的資料
        db.session.execute(db.text("SET LOCAL app.is_system_admin = 'true'"))

        scope = request.args.get('scope', 'all')

        # 取得活躍企業列表
        org_result = db.session.execute(db.text(
            "SELECT secure_code, name, domain_name FROM organizations "
            "WHERE is_deleted = false AND is_active = true ORDER BY name"
        ))
        orgs = [
            {'secure_code': row[0], 'name': row[1], 'domain_name': row[2]}
            for row in org_result
        ]

        # 動態掃描所有有 is_deleted 的表
        all_tables = _get_purge_tables()
        tables_with_counts = []

        def _scan_table(table_name):
            """掃描單一表的 soft-deleted 記錄數（用 SAVEPOINT 隔離錯誤）"""
            try:
                with db.session.begin_nested():
                    result = _purge_count_sql(table_name, scope)
                    if result is None:
                        return
                    sql, params = result
                    count = db.session.execute(db.text(sql), params).scalar()
                    if count and count > 0:
                        display_name = PURGE_DISPLAY_NAMES.get(table_name, table_name)
                        tables_with_counts.append({
                            'table': table_name,
                            'display_name': display_name,
                            'count': count,
                        })
            except Exception:
                pass

        for table_name in PURGE_DELETE_ORDER:
            if table_name not in all_tables or table_name in PURGE_EXCLUDE_TABLES:
                continue
            _scan_table(table_name)

        # 處理不在 PURGE_DELETE_ORDER 中但 DB 中存在的表
        remaining = all_tables - set(PURGE_DELETE_ORDER) - PURGE_EXCLUDE_TABLES
        for table_name in sorted(remaining):
            _scan_table(table_name)

        return jsonify({
            'success': True,
            'tables': tables_with_counts,
            'orgs': orgs,
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@hostconfig_bp.route('/purge-deleted/execute', methods=['POST'])
@system_admin_required
def purge_deleted_execute():
    """
    執行清除標記刪除的資料

    Body JSON:
        scope: 'all' 或 org_secure_code

    按 FK 安全順序刪除各表 is_deleted=true 的記錄。
    對父表會先清理指向它的孤兒子記錄。
    """
    try:
        # 繞過 RLS，確保能刪除所有企業隔離的資料
        db.session.execute(db.text("SET LOCAL app.is_system_admin = 'true'"))

        data = request.get_json() or {}
        scope = data.get('scope', 'all')

        all_tables = _get_purge_tables()
        deleted_counts = {}
        orphan_counts = {}

        # 按順序處理
        ordered_tables = list(PURGE_DELETE_ORDER)
        remaining = all_tables - set(ordered_tables) - PURGE_EXCLUDE_TABLES
        ordered_tables.extend(sorted(remaining))

        for table_name in ordered_tables:
            if table_name not in all_tables:
                continue
            if table_name in PURGE_EXCLUDE_TABLES:
                continue

            # Step 1: 孤兒清理（刪父表前先清子表）
            orphans = _purge_orphan_cleanup(table_name, scope)
            for child, count in orphans.items():
                orphan_counts[child] = orphan_counts.get(child, 0) + count

            # Step 2: 刪除 soft-deleted 記錄（用 SAVEPOINT 隔離錯誤）
            result = _purge_delete_sql(table_name, scope)
            if result is None:
                continue
            sql, params = result
            try:
                with db.session.begin_nested():
                    res = db.session.execute(db.text(sql), params)
                    if res.rowcount > 0:
                        deleted_counts[table_name] = res.rowcount
            except Exception as e:
                deleted_counts[f'{table_name} (錯誤)'] = str(e)

        db.session.commit()

        # 組合結果
        total_deleted = sum(v for v in deleted_counts.values() if isinstance(v, int))
        total_orphans = sum(orphan_counts.values())

        results = []
        for table_name in ordered_tables:
            if table_name in deleted_counts:
                display = PURGE_DISPLAY_NAMES.get(table_name, table_name)
                count = deleted_counts[table_name]
                orphan = orphan_counts.get(table_name, 0)
                entry = {'table': table_name, 'display_name': display, 'deleted': count}
                if orphan > 0:
                    entry['orphan_cleaned'] = orphan
                results.append(entry)
            elif table_name in orphan_counts:
                display = PURGE_DISPLAY_NAMES.get(table_name, table_name)
                results.append({
                    'table': table_name,
                    'display_name': display,
                    'deleted': 0,
                    'orphan_cleaned': orphan_counts[table_name],
                })

        # 加入不在 ordered 中的錯誤
        for key, val in deleted_counts.items():
            if '錯誤' in key and key not in [r.get('table') for r in results]:
                results.append({'table': key, 'display_name': key, 'deleted': val})

        return jsonify({
            'success': True,
            'message': _('已清除 %(count)s 筆標記刪除的記錄', count=total_deleted)
                       + (_('，另清理 %(count)s 筆孤兒記錄', count=total_orphans) if total_orphans > 0 else ''),
            'results': results,
            'total_deleted': total_deleted,
            'total_orphans': total_orphans,
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500
