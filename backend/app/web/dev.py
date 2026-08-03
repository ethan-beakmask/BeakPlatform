"""
BeakMask Development Tools
開發工具 - 僅限內網 IP 存取

路徑：/dev/*
限制：內網 IP only (192.168.*, 10.*, 172.16-31.*, 127.0.0.1)

功能：
- 快速登入（免密碼切換帳號）
"""
import logging
from functools import wraps
from flask import Blueprint, render_template, request, abort, jsonify, redirect, url_for
from flask_babel import gettext as _
from flask_login import login_user, logout_user, current_user
from sqlalchemy import text

from .. import db, csrf
from ..models import User, Organization
from ..security.decorators import public_route

logger = logging.getLogger(__name__)


dev_bp = Blueprint('dev', __name__)


def internal_network_only(f):
    """限制只有內網 IP 可以存取"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        client_ip = request.remote_addr

        allowed_prefixes = (
            '192.168.',
            '10.',
            '172.16.', '172.17.', '172.18.', '172.19.',
            '172.20.', '172.21.', '172.22.', '172.23.',
            '172.24.', '172.25.', '172.26.', '172.27.',
            '172.28.', '172.29.', '172.30.', '172.31.',
            '127.0.0.1',
            '::1',
        )

        if not client_ip or not client_ip.startswith(allowed_prefixes):
            abort(403, description='此功能僅限內網存取')

        return f(*args, **kwargs)
    return decorated_function


# ==================== 快速登入頁面 ====================

@dev_bp.route('/quick-login')
@public_route  # 開發工具，內網限制
@internal_network_only
def quick_login_page():
    """快速登入頁面"""
    return render_template('pages/dev/quick_login.html')


def _is_safe_relative_path(value):
    """只允許本站相對路徑，避免 open redirect。"""
    return bool(value and value.startswith('/') and not value.startswith('//'))


def _portal_sub_systems():
    from modules.nocode_builder.models.sub_system import DcSubSystem
    from modules.nocode_builder.services.data_source_manager import DataSourceManager
    from modules.nocode_builder.services.portal_path_service import get_by_sub_system

    mgr = DataSourceManager()
    sub_systems = DcSubSystem.query.filter(
        DcSubSystem.is_deleted == False,
        DcSubSystem.is_active == True,
    ).order_by(DcSubSystem.name).all()

    data = []
    for ss in sub_systems:
        if not mgr.has_sqlite(ss.secure_code):
            continue
        portal_path = get_by_sub_system(ss.secure_code)
        data.append({
            'secure_code': ss.secure_code,
            'name': ss.name,
            'code': ss.code or '',
            'portal_path_id': portal_path.code if portal_path else '',
        })
    return data


def _get_portal_sub_system(sub_system_sc):
    return next(
        (item for item in _portal_sub_systems() if item['secure_code'] == sub_system_sc),
        None,
    )


def _portal_admin_roles(sess, user_id):
    rows = sess.execute(
        text(
            'SELECT r.code '
            'FROM portal_user_roles AS ur '
            'JOIN portal_admin_roles AS r ON r.id = ur.role_id '
            'WHERE ur.user_id = :user_id '
            'AND r.enabled = 1 '
            "AND (ur.valid_from IS NULL OR ur.valid_from <= datetime('now')) "
            "AND (ur.valid_until IS NULL OR ur.valid_until > datetime('now')) "
            'ORDER BY r.display_order ASC, r.code ASC'
        ),
        {'user_id': user_id},
    ).mappings().all()
    return [row['code'] for row in rows]


def _portal_users(sub_system_sc):
    from modules.nocode_builder.services.data_source_manager import DataSourceManager, ensure_portal_schema
    from modules.nocode_builder.services.portal_auth_service import _level_rank

    ensure_portal_schema(sub_system_sc)
    mgr = DataSourceManager()
    with mgr.get_session(sub_system_sc, 'portal') as sess:
        rows = sess.execute(
            text(
                'SELECT id, secure_code, username, display_name, email, role_code, '
                'group_code, level_code, is_active, created_at '
                'FROM portal_users ORDER BY username ASC'
            )
        ).mappings().all()
        users = []
        for row in rows:
            level_code, level_rank = _level_rank(sess, row['level_code'])
            admin_roles = _portal_admin_roles(sess, row['id'])
            users.append({
                'id': row['secure_code'],
                'secure_code': row['secure_code'],
                'username': row['username'],
                'display_name': row['display_name'] or row['username'],
                'email': row['email'] or '',
                'role_code': row['role_code'],
                'group_code': row['group_code'],
                'level_code': level_code,
                'level_rank': level_rank,
                'roles': [row['role_code']],
                'admin_roles': admin_roles,
                'is_active': bool(row['is_active']),
                'created_at': row['created_at'],
            })
        return users


@dev_bp.route('/portal-quick-login')
@public_route  # 開發工具，內網限制
@internal_network_only
def portal_quick_login_page():
    """Portal 帳號快速切換頁面"""
    sub_systems = _portal_sub_systems()
    requested_sub = (request.args.get('sub') or '').strip()
    selected_sub = requested_sub if any(ss['secure_code'] == requested_sub for ss in sub_systems) else ''
    safe_next = request.args.get('next') if _is_safe_relative_path(request.args.get('next')) else ''
    return render_template(
        'pages/dev/portal_quick_login.html',
        sub_systems=sub_systems,
        selected_sub_system_sc=selected_sub,
        safe_next=safe_next,
    )


# ==================== API 端點 ====================

@dev_bp.route('/get-orgs')
@public_route  # 開發工具，內網限制
@internal_network_only
def get_organizations():
    """取得所有企業列表"""
    try:
        orgs = Organization.query.filter(
            Organization.is_deleted == False,
            Organization.is_active == True
        ).order_by(Organization.name).all()

        return jsonify({
            'success': True,
            'data': [
                {
                    'secure_code': org.secure_code,
                    'name': org.name,
                    'domain_name': org.domain_name,
                    'display_name': f"{org.name} ({org.domain_name})",
                    'is_active': org.is_active,
                    'is_deleted': org.is_deleted
                }
                for org in orgs
            ]
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500


@dev_bp.route('/get-users/<org_secure_code>')
@public_route  # 開發工具，內網限制
@internal_network_only
def get_users(org_secure_code):
    """取得指定企業的用戶列表"""
    try:
        users = User.query.filter(
            User.org_secure_code == org_secure_code,
            User.is_deleted == False,
            User.is_active == True,
            User.is_service_account == False
        ).order_by(User.user_type, User.username).all()

        return jsonify({
            'success': True,
            'data': [
                {
                    'id': user.secure_code,
                    'username': user.username,
                    'display_name': user.display_name or user.username,
                    'email': user.email,
                    'user_type': user.user_type,
                    'user_type_display': get_user_type_display(user.user_type),
                    'is_active': user.is_active,
                    'is_deleted': user.is_deleted
                }
                for user in users
            ]
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500


@dev_bp.route('/portal-quick-login/users/<sub_system_sc>')
@public_route  # 開發工具，內網限制
@internal_network_only
def get_portal_quick_login_users(sub_system_sc):
    """取得指定公開子系統的 portal 帳號列表"""
    try:
        sub_system = _get_portal_sub_system(sub_system_sc)
        if not sub_system:
            return jsonify({
                'success': False,
                'message': _('找不到子系統，或此子系統沒有 portal.db')
            }), 400

        return jsonify({
            'success': True,
            'data': _portal_users(sub_system_sc),
            'sub_system': sub_system,
        })
    except FileNotFoundError:
        return jsonify({
            'success': False,
            'message': _('此子系統尚未初始化 portal.db')
        }), 400
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500


@dev_bp.route('/quick-login', methods=['POST'])
@public_route  # 開發工具，內網限制
@csrf.exempt  # 快速登入不需要 CSRF（開發工具，僅內網存取）
@internal_network_only
def quick_login():
    """執行快速登入"""
    try:
        data = request.get_json()
        user_id = data.get('user_id')

        if not user_id:
            return jsonify({
                'success': False,
                'message': '請選擇用戶'
            }), 400

        user = User.query.filter(
            User.secure_code == user_id,
            User.is_deleted == False,
            User.is_service_account == False
        ).first()

        if not user:
            return jsonify({
                'success': False,
                'message': '用戶不存在'
            }), 404

        if not user.is_active:
            return jsonify({
                'success': False,
                'message': '用戶已停用'
            }), 403

        # 執行登入
        login_user(user, remember=True)
        from flask import session as flask_session
        flask_session['_session_org'] = user.org_secure_code  # load_user 交叉驗證用

        return jsonify({
            'success': True,
            'message': f'已登入：{user.display_name or user.username}',
            'data': {
                'redirect_url': f'{request.script_root}/',
                'user': {
                    'username': user.username,
                    'display_name': user.display_name,
                    'user_type': user.user_type
                }
            }
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500


@dev_bp.route('/portal-quick-login', methods=['POST'])
@public_route  # 開發工具，內網限制
@csrf.exempt  # 快速登入不需要 CSRF（開發工具，僅內網存取）
@internal_network_only
def portal_quick_login():
    """執行 portal 帳號快速切換"""
    try:
        data = request.get_json() or {}
        sub_system_sc = (data.get('sub_system_sc') or '').strip()
        user_secure_code = (data.get('user_secure_code') or '').strip()

        if not sub_system_sc:
            return jsonify({
                'success': False,
                'message': _('請選擇子系統')
            }), 400
        if not user_secure_code:
            return jsonify({
                'success': False,
                'message': _('請選擇帳號')
            }), 400

        sub_system = _get_portal_sub_system(sub_system_sc)
        if not sub_system:
            return jsonify({
                'success': False,
                'message': _('找不到子系統，或此子系統沒有 portal.db')
            }), 400

        # 免密碼切換的邏輯刻意留在 dev.py（本檔已在 push_github.sh 排除清單，
        # 正式部署會整個移除）。portal_auth_service 只提供「組裝／寫入 session」
        # 這兩個不含身分驗證語意的介面，避免正式服務層留下可免密碼登入的函式。
        from modules.nocode_builder.services.data_source_manager import (
            DataSourceManager, ensure_portal_schema,
        )
        from modules.nocode_builder.services import portal_auth_service

        try:
            ensure_portal_schema(sub_system_sc)
            with DataSourceManager().get_session(sub_system_sc, 'portal') as sess:
                row = sess.execute(
                    text(
                        'SELECT id, secure_code, username, display_name, '
                        'password_hash, role_code, group_code, level_code, is_active '
                        'FROM portal_users WHERE secure_code = :sc'
                    ),
                    {'sc': user_secure_code},
                ).mappings().first()
                if not row:
                    return jsonify({
                        'success': False,
                        'message': _('帳號不存在')
                    }), 400
                session_data = portal_auth_service.build_session_data(sub_system_sc, sess, row)
        except FileNotFoundError:
            return jsonify({
                'success': False,
                'message': _('系統尚未初始化')
            }), 400

        portal_auth_service.store_session(sub_system_sc, session_data)
        logger.info(
            'Portal dev quick login: user=%s sub_system=%s',
            session_data.get('user_id'), sub_system_sc,
        )

        return jsonify({
            'success': True,
            'data': session_data
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500


@dev_bp.route('/portal-quick-login/logout', methods=['POST'])
@public_route  # 開發工具，內網限制
@csrf.exempt  # 登出不需要 CSRF（開發工具，僅內網存取）
@internal_network_only
def portal_quick_login_logout():
    """清除 portal session"""
    from flask import session as flask_session
    from modules.nocode_builder.services.portal_auth_service import logout as portal_logout

    try:
        data = request.get_json(silent=True) or {}
        sub_system_sc = (data.get('sub_system_sc') or '').strip()
        if sub_system_sc:
            portal_logout(sub_system_sc)
        else:
            for existing_sub in list((flask_session.get('portal_sessions') or {}).keys()):
                portal_logout(existing_sub)

        return jsonify({
            'success': True,
            'message': _('Portal session 已清除')
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500


@dev_bp.route('/logout', methods=['POST'])
@public_route  # 開發工具，內網限制
@csrf.exempt  # 登出不需要 CSRF（開發工具，僅內網存取）
@internal_network_only
def dev_logout():
    """登出 - 完整清除所有登入狀態"""
    from flask import session
    try:
        # 1. Flask-Login 登出
        logout_user()

        # 2. 完全清除 session 資料
        session.clear()
        session.modified = True

        return jsonify({
            'success': True,
            'message': '已登出'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500


def get_user_type_display(user_type):
    """取得用戶類型顯示名稱"""
    type_map = {
        'SYSTEM_ADMIN': '系統管理員',
        'ORG_ADMIN': '企業管理員',
        'MEMBER': '一般用戶'
    }
    return type_map.get(user_type, user_type)


@dev_bp.route('/test-grid')
@public_route
@internal_network_only
def test_grid():
    """測試 Grid 佈局"""
    return render_template('pages/test_grid.html')


@dev_bp.route('/graph-simplify')
@public_route
@internal_network_only
def graph_simplify_demo():
    """流程圖簡化演算法模擬"""
    import json
    workflow_data = []

    try:
        rows = db.session.execute(text(
            "SELECT secure_code, name, graph "
            "FROM fw_workflow_templates "
            "WHERE graph IS NOT NULL "
            "AND jsonb_array_length(graph->'nodes') >= 3 "
            "ORDER BY jsonb_array_length(graph->'nodes') DESC"
        )).fetchall()

        for row in rows:
            graph = row[2] if isinstance(row[2], dict) else json.loads(row[2])
            workflow_data.append({
                'secure_code': row[0],
                'name': row[1],
                'graph': graph
            })
    except Exception as e:
        print(f'[graph-simplify] DB error: {e}')

    return render_template('dev/graph_simplify_demo.html',
                           workflow_data=workflow_data)


@dev_bp.route('/graph-flatten')
@public_route
@internal_network_only
def graph_flatten_demo():
    """子流程展開模擬（全圖）"""
    import json
    workflow_data = []

    try:
        rows = db.session.execute(text(
            "SELECT secure_code, name, graph, code "
            "FROM fw_workflow_templates "
            "WHERE graph IS NOT NULL "
            "AND jsonb_array_length(graph->'nodes') >= 2 "
            "ORDER BY jsonb_array_length(graph->'nodes') DESC"
        )).fetchall()

        for row in rows:
            graph = row[2] if isinstance(row[2], dict) else json.loads(row[2])
            workflow_data.append({
                'secure_code': row[0],
                'name': row[1],
                'graph': graph,
                'code': row[3] or ''
            })
    except Exception as e:
        print(f'[graph-flatten] DB error: {e}')

    return render_template('dev/graph_flatten_demo.html',
                           workflow_data=workflow_data)
