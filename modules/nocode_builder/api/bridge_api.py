"""
Data CRUD Module - Bridge API
資料橋接 API 端點

提供 DataBridgeService 的 HTTP 介面，讓 Studio 和排程呼叫。
"""
import logging
import uuid

from flask import jsonify, request
from flask_login import current_user

from app import csrf, db
from app.security.decorators import module_access_required
from app.security.resource_gateway import ResourceGateway

from . import api_bp
from .project_api import _check_developer_access

logger = logging.getLogger(__name__)


def _get_sub_system(secure_code: str):
    """取得子系統記錄，回傳 (sub_system, error_response)"""
    from ..models import DcSubSystem

    ss = ResourceGateway.get(
        DcSubSystem, secure_code,
        raise_on_not_found=False,
        check_permission=False,
    )
    if not ss or ss.is_deleted:
        return None, (jsonify({'success': False, 'error': '子系統不存在'}), 404)
    return ss, None


# =============================================================================
# 橋接操作
# =============================================================================

@api_bp.route('/projects/<secure_code>/bridge/publish', methods=['POST'])
@csrf.exempt
@module_access_required('nocode_builder')
def bridge_publish(secure_code):
    """PG -> SQLite INSERT (發布公開資料)"""
    if not _check_developer_access(secure_code):
        return jsonify({'success': False, 'error': '無權限'}), 403

    ss, err = _get_sub_system(secure_code)
    if err:
        return err

    data = request.get_json() or {}
    source_table = data.get('source_table', '').strip()
    target_table = data.get('target_table', '').strip()
    record_key = data.get('record_key')
    field_mapping = data.get('field_mapping')

    if not all([source_table, target_table, record_key, field_mapping]):
        return jsonify({
            'success': False,
            'error': '缺少必要參數: source_table, target_table, record_key, field_mapping',
        }), 400

    from ..services.data_bridge_service import DataBridgeService
    bridge = DataBridgeService()
    result = bridge.publish(
        sub_system_sc=secure_code,
        source_table=source_table,
        target_table=target_table,
        record_key=record_key,
        field_mapping=field_mapping,
        org_secure_code=ss.org_secure_code,
        operator_sc=current_user.secure_code,
    )

    if not result.get('success'):
        return jsonify(result), 400
    return jsonify(result)


@api_bp.route('/projects/<secure_code>/bridge/update', methods=['POST'])
@csrf.exempt
@module_access_required('nocode_builder')
def bridge_update(secure_code):
    """PG -> SQLite UPSERT (更新已發布的公開資料)"""
    if not _check_developer_access(secure_code):
        return jsonify({'success': False, 'error': '無權限'}), 403

    ss, err = _get_sub_system(secure_code)
    if err:
        return err

    data = request.get_json() or {}
    source_table = data.get('source_table', '').strip()
    target_table = data.get('target_table', '').strip()
    record_key = data.get('record_key')
    field_mapping = data.get('field_mapping')
    key_field = data.get('key_field', 'secure_code').strip()

    if not all([source_table, target_table, record_key, field_mapping]):
        return jsonify({
            'success': False,
            'error': '缺少必要參數: source_table, target_table, record_key, field_mapping',
        }), 400

    from ..services.data_bridge_service import DataBridgeService
    bridge = DataBridgeService()
    result = bridge.update(
        sub_system_sc=secure_code,
        source_table=source_table,
        target_table=target_table,
        record_key=record_key,
        field_mapping=field_mapping,
        org_secure_code=ss.org_secure_code,
        key_field=key_field,
        operator_sc=current_user.secure_code,
    )

    if not result.get('success'):
        return jsonify(result), 400
    return jsonify(result)


@api_bp.route('/projects/<secure_code>/bridge/collect', methods=['POST'])
@csrf.exempt
@module_access_required('nocode_builder')
def bridge_collect(secure_code):
    """SQLite -> PG (受限回收，需指定 context)"""
    if not _check_developer_access(secure_code):
        return jsonify({'success': False, 'error': '無權限'}), 403

    ss, err = _get_sub_system(secure_code)
    if err:
        return err

    data = request.get_json() or {}
    source_table = data.get('source_table', '').strip()
    target_table = data.get('target_table', '').strip()
    field_mapping = data.get('field_mapping')
    context = data.get('context', '').strip()
    collect_filter = data.get('collect_filter')
    key_field = data.get('key_field')

    if not all([source_table, target_table, field_mapping, context]):
        return jsonify({
            'success': False,
            'error': '缺少必要參數: source_table, target_table, field_mapping, context',
        }), 400

    from ..services.data_bridge_service import DataBridgeService
    bridge = DataBridgeService()
    result = bridge.collect(
        sub_system_sc=secure_code,
        source_table=source_table,
        target_table=target_table,
        field_mapping=field_mapping,
        context=context,
        org_secure_code=ss.org_secure_code,
        collect_filter=collect_filter,
        key_field=key_field.strip() if key_field else None,
        operator_sc=current_user.secure_code,
    )

    if not result.get('success'):
        return jsonify(result), 400
    return jsonify(result)


@api_bp.route('/projects/<secure_code>/bridge/execute-rule', methods=['POST'])
@csrf.exempt
@module_access_required('nocode_builder')
def bridge_execute_rule(secure_code):
    """依規則 ID 執行橋接操作"""
    if not _check_developer_access(secure_code):
        return jsonify({'success': False, 'error': '無權限'}), 403

    ss, err = _get_sub_system(secure_code)
    if err:
        return err

    data = request.get_json() or {}
    rule_id = data.get('rule_id', '').strip()
    record_key = data.get('record_key')
    collect_context = data.get('collect_context')
    collect_filter = data.get('collect_filter')

    if not rule_id:
        return jsonify({'success': False, 'error': '缺少 rule_id'}), 400

    # 從子系統的 bridge_rules 找出對應規則
    rules = ss.bridge_rules or []
    rule = None
    for r in rules:
        if r.get('rule_id') == rule_id:
            rule = r
            break

    if not rule:
        return jsonify({'success': False, 'error': f'找不到規則: {rule_id}'}), 404

    from ..services.data_bridge_service import DataBridgeService
    bridge = DataBridgeService()
    result = bridge.execute_rule(
        sub_system_sc=secure_code,
        rule=rule,
        record_key=record_key,
        org_secure_code=ss.org_secure_code,
        operator_sc=current_user.secure_code,
        collect_context=collect_context,
        collect_filter=collect_filter,
    )

    if not result.get('success'):
        return jsonify(result), 400
    return jsonify(result)


@api_bp.route('/projects/<secure_code>/bridge/validate-rule', methods=['POST'])
@csrf.exempt
@module_access_required('nocode_builder')
def bridge_validate_rule(secure_code):
    """驗證橋接規則結構"""
    if not _check_developer_access(secure_code):
        return jsonify({'success': False, 'error': '無權限'}), 403

    data = request.get_json() or {}
    if not data:
        return jsonify({'success': False, 'error': '缺少規則內容'}), 400

    from ..services.data_bridge_service import DataBridgeService
    result = DataBridgeService.validate_rule(data)
    return jsonify({'success': True, 'data': result})


@api_bp.route('/projects/<secure_code>/bridge/logs')
@module_access_required('nocode_builder')
def bridge_logs(secure_code):
    """查詢子系統的橋接操作日誌"""
    if not _check_developer_access(secure_code):
        return jsonify({'success': False, 'error': '無權限'}), 403

    ss, err = _get_sub_system(secure_code)
    if err:
        return err

    from ..models.bridge_log import DcBridgeLog

    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    per_page = min(per_page, 200)
    direction = request.args.get('direction', '').strip()
    status = request.args.get('status', '').strip()

    query = DcBridgeLog.query.filter_by(
        org_secure_code=ss.org_secure_code,
        sub_system_secure_code=secure_code,
        is_deleted=False,
    )

    if direction:
        query = query.filter_by(direction=direction)
    if status:
        query = query.filter_by(status=status)

    query = query.order_by(DcBridgeLog.created_at.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    return jsonify({
        'success': True,
        'data': [log.to_dict() for log in pagination.items],
        'pagination': {
            'page': pagination.page,
            'per_page': pagination.per_page,
            'total': pagination.total,
            'pages': pagination.pages,
        },
    })


# =============================================================================
# Bridge Rules CRUD
# =============================================================================

@api_bp.route('/projects/<secure_code>/bridge/rules')
@module_access_required('nocode_builder')
def list_bridge_rules(secure_code):
    """列出子系統的橋接規則"""
    if not _check_developer_access(secure_code):
        return jsonify({'success': False, 'error': '無權限'}), 403

    ss, err = _get_sub_system(secure_code)
    if err:
        return err

    rules = ss.bridge_rules or []
    return jsonify({'success': True, 'data': rules})


@api_bp.route('/projects/<secure_code>/bridge/rules', methods=['POST'])
@csrf.exempt
@module_access_required('nocode_builder')
def create_bridge_rule(secure_code):
    """新增橋接規則"""
    if not _check_developer_access(secure_code):
        return jsonify({'success': False, 'error': '無權限'}), 403

    ss, err = _get_sub_system(secure_code)
    if err:
        return err

    data = request.get_json() or {}

    # 驗證規則結構
    from ..services.data_bridge_service import DataBridgeService
    validation = DataBridgeService.validate_rule(data)
    if not validation['valid']:
        return jsonify({
            'success': False,
            'error': '規則驗證失敗',
            'details': validation['errors'],
        }), 400

    # 自動產生 rule_id
    if not data.get('rule_id'):
        data['rule_id'] = str(uuid.uuid4())[:8]

    # 檢查 rule_id 重複
    rules = list(ss.bridge_rules or [])
    for r in rules:
        if r.get('rule_id') == data['rule_id']:
            return jsonify({
                'success': False,
                'error': f'rule_id 已存在: {data["rule_id"]}',
            }), 400

    # 設定預設值
    data.setdefault('is_active', True)
    data.setdefault('key_field', 'secure_code')

    rules.append(data)
    ss.bridge_rules = rules
    db.session.commit()

    return jsonify({
        'success': True,
        'data': data,
        'message': '規則已建立',
    })


@api_bp.route('/projects/<secure_code>/bridge/rules/<rule_id>', methods=['PUT'])
@csrf.exempt
@module_access_required('nocode_builder')
def update_bridge_rule(secure_code, rule_id):
    """更新橋接規則"""
    if not _check_developer_access(secure_code):
        return jsonify({'success': False, 'error': '無權限'}), 403

    ss, err = _get_sub_system(secure_code)
    if err:
        return err

    data = request.get_json() or {}

    # 驗證規則結構（合併現有規則再驗證）
    rules = list(ss.bridge_rules or [])
    target_idx = None
    for i, r in enumerate(rules):
        if r.get('rule_id') == rule_id:
            target_idx = i
            break

    if target_idx is None:
        return jsonify({'success': False, 'error': f'找不到規則: {rule_id}'}), 404

    # 合併更新（保留 rule_id 不可變）
    updated_rule = {**rules[target_idx], **data}
    updated_rule['rule_id'] = rule_id  # rule_id 不可改

    from ..services.data_bridge_service import DataBridgeService
    validation = DataBridgeService.validate_rule(updated_rule)
    if not validation['valid']:
        return jsonify({
            'success': False,
            'error': '規則驗證失敗',
            'details': validation['errors'],
        }), 400

    rules[target_idx] = updated_rule
    ss.bridge_rules = rules
    db.session.commit()

    return jsonify({
        'success': True,
        'data': updated_rule,
        'message': '規則已更新',
    })


@api_bp.route('/projects/<secure_code>/bridge/rules/<rule_id>', methods=['DELETE'])
@csrf.exempt
@module_access_required('nocode_builder')
def delete_bridge_rule(secure_code, rule_id):
    """刪除橋接規則"""
    if not _check_developer_access(secure_code):
        return jsonify({'success': False, 'error': '無權限'}), 403

    ss, err = _get_sub_system(secure_code)
    if err:
        return err

    rules = list(ss.bridge_rules or [])
    new_rules = [r for r in rules if r.get('rule_id') != rule_id]

    if len(new_rules) == len(rules):
        return jsonify({'success': False, 'error': f'找不到規則: {rule_id}'}), 404

    ss.bridge_rules = new_rules
    db.session.commit()

    return jsonify({
        'success': True,
        'message': '規則已刪除',
    })
