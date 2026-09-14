"""
資料出口政策 API

[標準 AUTH-02] 統一認證 decorator
[標準 TENANT-01] 強制企業隔離
規格：dev-notes/EGRESS_POLICY_SPEC.md

端點：
- POST /api/egress/reveal            揭示單一 masked 格（登入用戶）
- GET  /api/egress/policies          政策列表（企業管理員）
- POST /api/egress/policies          建立政策（企業管理員）
- PATCH /api/egress/policies/<sc>    更新政策（企業管理員）
- DELETE /api/egress/policies/<sc>   刪除政策（企業管理員）
- GET/POST /api/egress/thresholds    閾值列表/建立（企業管理員）
"""
from flask import Blueprint, jsonify, request
from flask_babel import gettext as _
from flask_login import current_user

from .. import db
from ..models.egress_policy import (
    EgressFieldPolicy, EgressTierThreshold,
    EGRESS_CONTEXTS, EGRESS_METERS, VISIBILITY_ORDER,
)
from ..security.decorators import login_required, admin_required
from ..services import egress_service
from ..utils.security import generate_secure_code

egress_bp = Blueprint('api_egress', __name__, url_prefix='/api/egress')

# 平台資源揭示通道註冊（模組資源由各模組載入時自行註冊）
from ..models.user import User  # noqa: E402
egress_service.register_model_resource('user', User)


@egress_bp.route('/reveal', methods=['POST'])
@login_required
def reveal_field():
    """揭示單一 masked 格的真值（逐格、逐次稽核）"""
    data = request.get_json(silent=True) or {}
    resource = data.get('resource')
    record_sc = data.get('record_sc')
    field = data.get('field')
    if not resource or not record_sc or not field:
        return jsonify({'success': False,
                        'message': _('缺少必要參數')}), 400

    try:
        value = egress_service.reveal(resource, record_sc, field)
    except egress_service.RevealDenied as e:
        return jsonify({'success': False, 'message': str(e)}), 403
    except Exception:
        return jsonify({'success': False,
                        'message': _('揭示失敗')}), 404

    return jsonify({'success': True, 'value': value})


# =============================================================================
# 政策管理（企業管理員）
# =============================================================================

def _validate_policy_payload(data: dict):
    if data.get('context') not in EGRESS_CONTEXTS:
        return _('context 必須為 %(v)s 之一', v=', '.join(EGRESS_CONTEXTS))
    if data.get('visibility') not in VISIBILITY_ORDER:
        return _('visibility 必須為 clear / masked / hidden')
    if not data.get('resource_code') or not data.get('field_name'):
        return _('resource_code 與 field_name 為必填')
    return None


@egress_bp.route('/policies', methods=['GET'])
@admin_required
def list_policies():
    policies = EgressFieldPolicy.query.filter_by(
        org_secure_code=current_user.org_secure_code,
        is_deleted=False,
    ).order_by(EgressFieldPolicy.resource_code,
               EgressFieldPolicy.field_name).all()
    return jsonify({'success': True,
                    'policies': [p.to_dict() for p in policies]})


@egress_bp.route('/policies', methods=['POST'])
@admin_required
def create_policy():
    data = request.get_json(silent=True) or {}
    error = _validate_policy_payload(data)
    if error:
        return jsonify({'success': False, 'message': error}), 400

    policy = EgressFieldPolicy(
        secure_code=generate_secure_code(),
        org_secure_code=current_user.org_secure_code,
        resource_code=data['resource_code'],
        field_name=data['field_name'],
        context=data['context'],
        role_secure_code=data.get('role_secure_code'),
        department_secure_code=data.get('department_secure_code'),
        node_key=data.get('node_key'),
        visibility=data['visibility'],
        tier=data.get('tier', 'normal'),
        is_active=data.get('is_active', True),
    )
    db.session.add(policy)
    db.session.commit()
    egress_service.invalidate_cache(current_user.org_secure_code)
    return jsonify({'success': True, 'policy': policy.to_dict()}), 201


@egress_bp.route('/policies/<secure_code>', methods=['PATCH'])
@admin_required
def update_policy(secure_code):
    policy = EgressFieldPolicy.query.filter_by(
        secure_code=secure_code,
        org_secure_code=current_user.org_secure_code,
        is_deleted=False,
    ).first()
    if policy is None:
        return jsonify({'success': False, 'message': _('找不到政策')}), 404

    data = request.get_json(silent=True) or {}
    if 'visibility' in data and data['visibility'] not in VISIBILITY_ORDER:
        return jsonify({'success': False,
                        'message': _('visibility 必須為 clear / masked / hidden')}), 400
    for field in ('visibility', 'tier', 'is_active',
                  'role_secure_code', 'department_secure_code', 'node_key'):
        if field in data:
            setattr(policy, field, data[field])
    db.session.commit()
    egress_service.invalidate_cache(current_user.org_secure_code)
    return jsonify({'success': True, 'policy': policy.to_dict()})


@egress_bp.route('/policies/<secure_code>', methods=['DELETE'])
@admin_required
def delete_policy(secure_code):
    policy = EgressFieldPolicy.query.filter_by(
        secure_code=secure_code,
        org_secure_code=current_user.org_secure_code,
        is_deleted=False,
    ).first()
    if policy is None:
        return jsonify({'success': False, 'message': _('找不到政策')}), 404
    policy.is_deleted = True
    db.session.commit()
    egress_service.invalidate_cache(current_user.org_secure_code)
    return jsonify({'success': True})


# =============================================================================
# 水表閾值管理（企業管理員）
# =============================================================================

@egress_bp.route('/thresholds', methods=['GET'])
@admin_required
def list_thresholds():
    rows = EgressTierThreshold.query.filter_by(
        org_secure_code=current_user.org_secure_code,
        is_deleted=False,
    ).order_by(EgressTierThreshold.tier, EgressTierThreshold.meter).all()
    return jsonify({'success': True,
                    'thresholds': [t.to_dict() for t in rows]})


@egress_bp.route('/thresholds', methods=['POST'])
@admin_required
def upsert_threshold():
    """建立或更新 (tier, meter) 閾值"""
    data = request.get_json(silent=True) or {}
    tier = data.get('tier')
    meter = data.get('meter')
    threshold = data.get('threshold')
    if not tier or meter not in EGRESS_METERS or not isinstance(threshold, int):
        return jsonify({'success': False,
                        'message': _('tier、meter、threshold 為必填且格式需正確')}), 400

    row = EgressTierThreshold.query.filter_by(
        org_secure_code=current_user.org_secure_code,
        tier=tier, meter=meter, is_deleted=False,
    ).first()
    if row is None:
        row = EgressTierThreshold(
            secure_code=generate_secure_code(),
            org_secure_code=current_user.org_secure_code,
            tier=tier, meter=meter,
            threshold=threshold,
            window_minutes=data.get('window_minutes', 60),
        )
        db.session.add(row)
    else:
        row.threshold = threshold
        row.window_minutes = data.get('window_minutes', row.window_minutes)
        row.is_active = data.get('is_active', row.is_active)
    db.session.commit()
    return jsonify({'success': True, 'threshold': row.to_dict()})
