"""
流程節點企業授權管理 API。

系統管理員可在平台層列舉受限節點、企業與有效授權，並執行授權/撤銷。
"""
import logging

from flask import Blueprint, jsonify, request
from flask_babel import gettext as _
from flask_login import current_user

from app import db
from app.models import Organization
from app.security.decorators import system_admin_required
from app.security.resource_gateway import ResourceGateway


logger = logging.getLogger(__name__)

node_grants_api_bp = Blueprint(
    'node_grants_api',
    __name__,
    url_prefix='/api/node-grants',
)


def _json_error(error, message, status=400):
    return jsonify({
        'success': False,
        'error': error,
        'message': message,
    }), status


# NodeGrantError 的訊息是服務層用 f-string 動態組出來的（內含 node_type /
# org_secure_code），直接 _(str(exc)) 會讓 msgid 是執行期字串、pybabel 抓不到，
# 英文介面永遠顯示中文。改用 code 對照的靜態 msgid（lambda 延遲到 request 內求值）。
_ERROR_MESSAGES = {
    'node_not_found': lambda: _('找不到指定的節點型別'),
    'node_not_restricted': lambda: _('此節點型別不需要企業授權'),
    'org_not_found': lambda: _('找不到指定的企業'),
}


def _node_grant_error(exc):
    code = getattr(exc, 'code', 'invalid_payload')
    builder = _ERROR_MESSAGES.get(code)
    return _json_error(code, builder() if builder else _('操作失敗'))


def _payload():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return None
    return data


def _required_string(data, key):
    value = data.get(key) if isinstance(data, dict) else None
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def _node_org_payload():
    data = _payload()
    node_type = _required_string(data, 'node_type')
    org_secure_code = _required_string(data, 'org_secure_code')
    if not node_type or not org_secure_code:
        return None, None, _json_error(
            'invalid_payload',
            _('請提供有效的 node_type 與 org_secure_code'),
        )
    return node_type, org_secure_code, None


@node_grants_api_bp.route('/matrix', methods=['GET'])
@system_admin_required
def matrix():
    try:
        from modules.form_workflow.models import WorkflowNodeDefinition, WorkflowNodeOrgGrant

        nodes = WorkflowNodeDefinition.query.filter(
            WorkflowNodeDefinition.org_restricted.is_(True),
            WorkflowNodeDefinition.is_deleted.is_(False),
        ).order_by(WorkflowNodeDefinition.node_type).all()

        # @system_admin_required 已是身分硬界線；本頁職責就是跨企業列舉，
        # 開啟 organization:read 檢查會擋掉沒有該 permission 的系統管理員（TENANT-02 雷三）。
        orgs = ResourceGateway.filter(
            Organization,
            check_permission=False,
            is_deleted=False,
            # 系統預設企業排最前，判定用 is_system_org 旗標（每套部署只有一筆
            # true），不可比對名稱或 secure_code —— 開發環境是 system.local，
            # 正式部署是隨機字串。前端另有一層相同排序，不倚賴這裡。
            order_by='-is_system_org,name',
        )

        grants = WorkflowNodeOrgGrant.query.filter(
            WorkflowNodeOrgGrant.is_deleted.is_(False),
        ).all()

        grant_matrix = {}
        restricted_types = {node.node_type for node in nodes}
        org_codes = {org.secure_code for org in orgs}
        for grant in grants:
            if grant.node_type not in restricted_types:
                continue
            if grant.org_secure_code not in org_codes:
                continue
            grant_matrix.setdefault(grant.node_type, {})[grant.org_secure_code] = {
                'granted_by_name': grant.granted_by_name or '',
                'created_at': grant.created_at.isoformat() if grant.created_at else '',
            }

        return jsonify({
            'success': True,
            'data': {
                'nodes': [
                    {
                        'node_type': node.node_type,
                        'display_name': node.display_name,
                        'category': node.category,
                        'is_active': bool(node.is_active),
                        'description': node.description or '',
                    }
                    for node in nodes
                ],
                'orgs': [
                    {
                        'secure_code': org.secure_code,
                        'code': org.code,
                        'name': org.name,
                        'display_name': org.display_name or '',
                        'is_active': bool(org.is_active),
                        'is_system_org': bool(org.is_system_org),
                    }
                    for org in orgs
                ],
                'grants': grant_matrix,
            },
        })
    except Exception:
        db.session.rollback()
        logger.exception('node grants matrix failed')
        return _json_error(
            'internal_error',
            _('讀取節點授權矩陣失敗'),
            status=500,
        )


@node_grants_api_bp.route('/grant', methods=['POST'])
@system_admin_required
def grant():
    node_type, org_secure_code, error_response = _node_org_payload()
    if error_response:
        return error_response

    from modules.form_workflow.services.node_grant_service import (
        NodeGrantError,
        grant_node_to_org,
    )

    try:
        changed = grant_node_to_org(
            node_type,
            org_secure_code,
            granted_by_secure_code=current_user.secure_code,
            granted_by_name=current_user.display_name,
        )
        return jsonify({'success': True, 'changed': changed})
    except NodeGrantError as exc:
        return _node_grant_error(exc)
    except Exception:
        db.session.rollback()
        logger.exception('node grant API failed')
        return _json_error('internal_error', _('授權失敗'), status=500)


@node_grants_api_bp.route('/revoke', methods=['POST'])
@system_admin_required
def revoke():
    node_type, org_secure_code, error_response = _node_org_payload()
    if error_response:
        return error_response

    from modules.form_workflow.services.node_grant_service import (
        NodeGrantError,
        revoke_node_from_org,
    )

    try:
        changed = revoke_node_from_org(node_type, org_secure_code)
        return jsonify({'success': True, 'changed': changed})
    except NodeGrantError as exc:
        return _node_grant_error(exc)
    except Exception:
        db.session.rollback()
        logger.exception('node revoke API failed')
        return _json_error('internal_error', _('撤銷授權失敗'), status=500)


@node_grants_api_bp.route('/bulk', methods=['POST'])
@system_admin_required
def bulk():
    data = _payload()
    node_type = _required_string(data, 'node_type')
    action = _required_string(data, 'action')
    if not node_type or action not in ('grant', 'revoke'):
        return _json_error(
            'invalid_payload',
            _('請提供有效的 node_type 與 action'),
        )

    from modules.form_workflow.services.node_grant_service import (
        NodeGrantError,
        grant_node_to_org,
        revoke_node_from_org,
    )

    try:
        orgs = ResourceGateway.filter(
            Organization,
            check_permission=False,
            is_deleted=False,
            # 系統預設企業排最前，判定用 is_system_org 旗標（每套部署只有一筆
            # true），不可比對名稱或 secure_code —— 開發環境是 system.local，
            # 正式部署是隨機字串。前端另有一層相同排序，不倚賴這裡。
            order_by='-is_system_org,name',
        )
        changed_count = 0
        for org in orgs:
            if action == 'grant':
                changed = grant_node_to_org(
                    node_type,
                    org.secure_code,
                    granted_by_secure_code=current_user.secure_code,
                    granted_by_name=current_user.display_name,
                )
            else:
                changed = revoke_node_from_org(node_type, org.secure_code)
            if changed:
                changed_count += 1

        return jsonify({'success': True, 'changed_count': changed_count})
    except NodeGrantError as exc:
        return _node_grant_error(exc)
    except Exception:
        db.session.rollback()
        logger.exception('node grants bulk API failed')
        return _json_error('internal_error', _('批次操作失敗'), status=500)
