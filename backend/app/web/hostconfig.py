"""
BeakPlatform Host Config
主機設定區 - 系統管理員專用

用途：
- 伺服器設定 (E-MailRelay 等)
- Flask 重啟
- 資料維護 (硬刪除)
- 其他主機級操作
"""
import subprocess
from flask import Blueprint, render_template, jsonify

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
        # 使用 nohup 讓腳本在背景執行，避免被中斷
        subprocess.Popen(
            ['nohup', '/opt/BeakPlatform/restart_flask.sh'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )
        return jsonify({'success': True, 'message': '重啟指令已發送，頁面將在 5 秒後重新整理'})
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
