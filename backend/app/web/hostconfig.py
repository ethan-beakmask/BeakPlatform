"""
BeakMask Host Config
主機設定區 - 系統管理員專用

用途：
- 伺服器設定 (E-MailRelay 等)
- Flask 重啟
- 資料維護 (硬刪除、清除標記刪除資料)
- 其他主機級操作
"""
import subprocess
from flask import Blueprint, render_template, jsonify, request

from app.security.decorators import system_admin_required
from app import db

hostconfig_bp = Blueprint('hostconfig', __name__)

# 硬刪除涉及的資料表（按刪除順序排列，子表在前）
# 注意：順序非常重要，必須先刪除有外鍵依賴的子表
HARD_DELETE_TABLES = [
    # 合約 (依賴 users)
    ('contracts', 'org_secure_code', '合約'),

    # 權限相關 (role_permissions 依賴 roles)
    ('role_permissions', 'role_secure_code', '角色權限', 'roles'),

    # 用戶與角色相關
    ('user_role_assignments', 'org_secure_code', '用戶角色指派'),
    ('user_unit_assignments', 'org_secure_code', '用戶單位指派'),
    ('password_reset_tokens', 'org_secure_code', '密碼重設 Token'),
    ('delegations', 'org_secure_code', '代理設定'),
    ('employee_positions', 'org_secure_code', '員工職位'),
    ('roles', 'org_secure_code', '角色'),
    ('users', 'org_secure_code', '用戶'),

    # 組織結構 (duties 依賴 organizational_units)
    ('duties', 'org_secure_code', '職責'),
    ('duty_categories', 'org_secure_code', '職責分類'),
    ('organizational_units', 'org_secure_code', '組織單位'),
    ('job_titles', 'org_secure_code', '職稱'),
    ('job_levels', 'org_secure_code', '職等'),
    ('job_families', 'org_secure_code', '職系'),

    # 選單相關 (menu_permissions 依賴 menu_items)
    ('menu_permissions', 'menu_secure_code', '選單權限', 'menu_items'),
    ('menu_items', 'org_secure_code', '選單項目'),

    # 企業設定
    ('smtp_configs', 'org_secure_code', 'SMTP 設定'),
    ('telegram_configs', 'org_secure_code', 'Telegram 設定'),
    ('recipient_groups', 'org_secure_code', '收件人群組'),
    ('pages', 'org_secure_code', '頁面'),
    ('modules', 'org_secure_code', '模組'),

    # 企業本身 (最後刪除)
    ('organizations', 'secure_code', '企業'),
]


@hostconfig_bp.route('/')
@system_admin_required
def index():
    """主機設定首頁"""
    return render_template('pages/hostconfig/index.html')


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


@hostconfig_bp.route('/restart-flask', methods=['POST'])
@system_admin_required
def restart_flask():
    """執行 Flask 重啟腳本"""
    try:
        # 用 systemd-run (transient service) 讓 PID 1 直接啟動腳本，
        # 完全脫離 beakplatform.service 的 cgroup，
        # 避免 systemctl stop 連帶殺掉腳本自身。
        # --collect: 執行完畢自動清除 transient unit
        subprocess.Popen(
            [
                'sudo', 'systemd-run',
                '--collect',
                '--unit=beakplatform-restart',
                '--property=Type=oneshot',
                '/opt/BeakPlatform/restart_flask.sh',
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )
        return jsonify({'success': True, 'message': '重啟指令已發送，頁面將在 15 秒後重新整理'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


def _get_delete_sql(table_name, key_column, org_placeholders, parent_table=None):
    """
    產生刪除 SQL 語句

    Args:
        table_name: 要刪除的表
        key_column: 該表的關聯欄位
        org_placeholders: 企業 secure_code 佔位符
        parent_table: 間接關聯的父表 (如 role_permissions 透過 roles)
    """
    if table_name == 'organizations':
        return f"SELECT COUNT(*) FROM {table_name} WHERE is_deleted = true", \
               f"DELETE FROM {table_name} WHERE is_deleted = true"

    if parent_table:
        # 間接關聯：先找父表中屬於這些企業的記錄，再刪除子表
        subquery = f"SELECT secure_code FROM {parent_table} WHERE org_secure_code IN ({org_placeholders})"
        count_sql = f"SELECT COUNT(*) FROM {table_name} WHERE {key_column} IN ({subquery})"
        delete_sql = f"DELETE FROM {table_name} WHERE {key_column} IN ({subquery})"
    else:
        # 直接關聯
        count_sql = f"SELECT COUNT(*) FROM {table_name} WHERE {key_column} IN ({org_placeholders})"
        delete_sql = f"DELETE FROM {table_name} WHERE {key_column} IN ({org_placeholders})"

    return count_sql, delete_sql


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
                'message': '沒有已軟刪除的企業'
            })

        # 取得各表預計刪除的筆數
        org_codes = [org['secure_code'] for org in deleted_orgs]
        placeholders = ','.join([f"'{code}'" for code in org_codes])

        table_counts = []
        for table_def in HARD_DELETE_TABLES:
            table_name = table_def[0]
            key_column = table_def[1]
            display_name = table_def[2]
            parent_table = table_def[3] if len(table_def) > 3 else None

            try:
                count_sql, _ = _get_delete_sql(table_name, key_column, placeholders, parent_table)
                count = db.session.execute(db.text(count_sql)).scalar()
                if count > 0:
                    table_counts.append({
                        'table': table_name,
                        'display_name': display_name,
                        'count': count
                    })
            except Exception:
                # 表可能不存在，跳過
                pass

        return jsonify({
            'success': True,
            'deleted_orgs': deleted_orgs,
            'table_counts': table_counts
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
        # 取得已軟刪除的企業
        result = db.session.execute(db.text(
            "SELECT secure_code FROM organizations WHERE is_deleted = true"
        ))
        org_codes = [row[0] for row in result]

        if not org_codes:
            return jsonify({
                'success': True,
                'message': '沒有需要刪除的資料',
                'deleted_counts': {}
            })

        placeholders = ','.join([f"'{code}'" for code in org_codes])
        deleted_counts = {}

        # 按順序刪除各表
        for table_def in HARD_DELETE_TABLES:
            table_name = table_def[0]
            key_column = table_def[1]
            display_name = table_def[2]
            parent_table = table_def[3] if len(table_def) > 3 else None

            try:
                _, delete_sql = _get_delete_sql(table_name, key_column, placeholders, parent_table)
                result = db.session.execute(db.text(delete_sql))
                if result.rowcount > 0:
                    deleted_counts[display_name] = result.rowcount
            except Exception as e:
                # 記錄錯誤但繼續
                deleted_counts[f'{display_name} (錯誤)'] = str(e)

        db.session.commit()

        return jsonify({
            'success': True,
            'message': f'已刪除 {len(org_codes)} 個企業及其相關資料',
            'deleted_counts': deleted_counts
        })
    except Exception as e:
        db.session.rollback()
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
    'employee_positions': '員工職位',
    'contracts': '合約',
    'personal_schedules': '個人班表',
    'schedule_adjustments': '班表調整',
    'password_reset_tokens': '密碼重設 Token',
    'audit_logs': '稽核日誌',
    'used_user_numbers': '已用員工編號',
    'user_numbering_counters': '員工編號計數器',
    'job_level_approval_limits': '職等簽核額度',
    'approval_categories': '簽核類別',
    'conglomerate_logs': '集團日誌',
    'schedule_holidays': '班表假日',
    'duties': '職責',
    'menu_permissions': '選單權限',
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
    'user_numbering_rules': '員工編號規則',
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
    # 平台表單流程
    'form_approval_comments': '簽核意見',
    'published_form_workflows': '已發行表單流程',
    'form_workflow_mappings': '表單流程對應',
    'node_execution_queue': '節點執行佇列',
    'node_execution_queue_archive': '節點執行佇列封存',
    'workflow_variables': '流程變數',
    'form_instances': '表單實例',
    'form_categories': '表單分類',
    'workflow_instances': '流程實例',
    'form_templates': '表單範本',
    'workflow_templates': '流程範本',
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
    'permission_conditions',
    # FormFlow 葉節點
    'fw_approval_records', 'fw_form_field_changes', 'fw_node_execution_logs',
    'fw_node_execution_queue', 'fw_sync_queue', 'fw_workflow_backgrounds',
    'fw_sql_form_registries', 'fw_published_form_workflows',
    'fw_form_workflow_mappings',
    # 平台葉節點
    'form_approval_comments', 'published_form_workflows', 'form_workflow_mappings',
    'node_execution_queue', 'node_execution_queue_archive', 'workflow_variables',
    # Phase 2: 中層表
    'duty_categories', 'job_titles', 'users',
    'fw_form_instances', 'fw_workflow_instances', 'fw_categories',
    'form_instances', 'form_categories', 'workflow_instances',
    # Phase 3: 上層表
    'roles', 'organizational_units', 'job_levels', 'job_families',
    'menu_items', 'pages', 'modules', 'work_schedules', 'shift_types',
    'fw_form_templates', 'fw_workflow_templates', 'fw_org_databases',
    'form_templates', 'workflow_templates', 'workflow_node_definitions',
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

# 孤兒清理：刪除 soft-deleted 父記錄前，先刪指向它的子記錄
# 格式: {parent_table: [(child_table, fk_column)]}
PURGE_ORPHAN_CLEANUP = {
    'users': [
        ('user_role_assignments', 'user_secure_code'),
        ('user_unit_assignments', 'user_secure_code'),
        ('user_unit_memberships', 'user_secure_code'),
        ('delegations', 'delegator_secure_code'),
        ('delegations', 'delegate_secure_code'),
        ('employee_positions', 'user_secure_code'),
        ('personal_schedules', 'user_secure_code'),
        ('schedule_adjustments', 'user_secure_code'),
        ('used_user_numbers', 'user_secure_code'),
    ],
    'roles': [
        ('role_permissions', 'role_secure_code'),
        ('user_role_assignments', 'role_secure_code'),
    ],
    'organizational_units': [
        ('user_unit_assignments', 'unit_secure_code'),
        ('user_unit_memberships', 'unit_secure_code'),
        ('duties', 'unit_secure_code'),
        ('employee_positions', 'unit_secure_code'),
    ],
    'menu_items': [
        ('menu_permissions', 'menu_secure_code'),
    ],
    'work_schedules': [
        ('schedule_holidays', 'schedule_secure_code'),
    ],
    'job_titles': [
        ('employee_positions', 'job_title_secure_code'),
    ],
    'fw_form_templates': [
        ('fw_form_workflow_mappings', 'form_template_secure_code'),
        ('fw_published_form_workflows', 'source_form_template_secure_code'),
        ('fw_form_instances', 'form_template_secure_code'),
    ],
    'fw_workflow_templates': [
        ('fw_form_workflow_mappings', 'workflow_template_secure_code'),
        ('fw_published_form_workflows', 'source_workflow_template_secure_code'),
        ('fw_workflow_instances', 'workflow_template_secure_code'),
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
    清理孤兒記錄：刪除指向 soft-deleted 父記錄的子記錄

    Returns:
        dict {child_table: deleted_count}
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

    for child_table, fk_col in PURGE_ORPHAN_CLEANUP[parent_table]:
        try:
            with db.session.begin_nested():
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
            'message': f'已清除 {total_deleted} 筆標記刪除的記錄'
                       + (f'，另清理 {total_orphans} 筆孤兒記錄' if total_orphans > 0 else ''),
            'results': results,
            'total_deleted': total_deleted,
            'total_orphans': total_orphans,
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500
