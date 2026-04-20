"""
BeakMask Development Tools
開發工具 - 僅限內網 IP 存取

路徑：/dev/*
限制：內網 IP only (192.168.*, 10.*, 172.16-31.*, 127.0.0.1)

功能：
- 快速登入（免密碼切換帳號）
"""
from functools import wraps
from flask import Blueprint, render_template, request, abort, jsonify, redirect, url_for
from flask_login import login_user, logout_user, current_user
from sqlalchemy import text

from .. import db, csrf
from ..models import User, Organization
from ..security.decorators import public_route


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
            User.is_active == True
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
            User.is_deleted == False
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
