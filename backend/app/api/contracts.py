"""
BeakMask Contract API
合約管理 API
"""
import json
import logging
from datetime import datetime

from flask import Blueprint, request, jsonify
from flask_babel import gettext as _

from ..security.decorators import system_admin_required, admin_required
from ..security.resource_gateway import ResourceGateway
from ..models import Contract, ContractStatus, Organization
from ..services.organization_service import OrganizationService
from .. import db

logger = logging.getLogger(__name__)

contracts_bp = Blueprint('api_contracts', __name__, url_prefix='/api/contracts')


@contracts_bp.route('/', methods=['GET'])
@system_admin_required
def list_contracts():
    """
    取得合約列表 (系統管理員)

    GET /api/contracts
    Query params:
        - org_id: 企業 secure_code (篩選)
        - status: 合約狀態 (篩選)
        - page: 頁碼
        - per_page: 每頁數量
    """
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    org_id = request.args.get('org_id')
    status = request.args.get('status')

    # 建立查詢條件
    filters = {'is_deleted': False}
    if org_id:
        filters['org_secure_code'] = org_id
    if status:
        filters['status'] = status

    # 系統管理員跨租戶查詢
    result = ResourceGateway.list(
        Contract,
        page=page,
        per_page=per_page,
        order_by='-created_at',
        skip_tenant_filter=True,
        **filters
    )

    return jsonify({
        'contracts': [c.to_dict(include_org=True) for c in result['items']],
        'pagination': {
            'page': result['page'],
            'per_page': result['per_page'],
            'total': result['total'],
            'pages': result['pages'],
        }
    }), 200


@contracts_bp.route('/<secure_code>', methods=['GET'])
@system_admin_required
def get_contract(secure_code: str):
    """
    取得單一合約 (系統管理員)

    GET /api/contracts/<secure_code>
    """
    contract = ResourceGateway.get_by(
        Contract,
        secure_code=secure_code,
        is_deleted=False,
        skip_tenant_filter=True
    )

    if not contract:
        return jsonify({'error': _('合約不存在')}), 404

    return jsonify({
        'contract': contract.to_dict(include_org=True)
    }), 200


@contracts_bp.route('/', methods=['POST'])
@system_admin_required
def create_contract():
    """
    建立合約 (系統管理員)

    POST /api/contracts
    Body: {
        "org_id": "企業 secure_code",
        "start_date": "2025-01-01",
        "end_date": "2025-12-31",
        "name": "合約名稱",
        "amount": 100000,
        "notes": "備註"
    }
    """
    from flask_login import current_user

    data = request.get_json()
    if not data:
        return jsonify({'error': _('請提供合約資料')}), 400

    required_fields = ['org_id', 'start_date', 'end_date']
    for field in required_fields:
        if field not in data:
            return jsonify({'error': _('缺少必要欄位: %(field)s', field=field)}), 400

    try:
        start_date = datetime.strptime(data['start_date'], '%Y-%m-%d').date()
        end_date = datetime.strptime(data['end_date'], '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'error': _('日期格式錯誤，請使用 YYYY-MM-DD')}), 400

    try:
        modules_config = data.get('modules_config')
        modules_config_str = json.dumps(modules_config) if modules_config else None

        contract = OrganizationService.create_contract(
            org_secure_code=data['org_id'],
            start_date=start_date,
            end_date=end_date,
            name=data.get('name'),
            description=data.get('description'),
            amount=data.get('amount'),
            modules_config=modules_config_str,
            notes=data.get('notes'),
            created_by=current_user.secure_code
        )
        db.session.commit()

        return jsonify({
            'message': _('合約建立成功'),
            'contract': contract.to_dict()
        }), 201

    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to create contract: {e}")
        return jsonify({'error': _('建立合約失敗')}), 500


@contracts_bp.route('/<secure_code>', methods=['PUT'])
@system_admin_required
def update_contract(secure_code: str):
    """
    更新合約 (系統管理員)
    合約建立後不可修改內容（稽核要求），僅可透過 PATCH /disable 停用。

    PUT /api/contracts/<secure_code>
    """
    return jsonify({
        'error': _('合約建立後不可修改內容（稽核要求）。如需停用請使用停用功能，如需變更請建立新合約。')
    }), 403


@contracts_bp.route('/<secure_code>', methods=['DELETE'])
@system_admin_required
def delete_contract(secure_code: str):
    """
    刪除合約 (軟刪除，系統管理員)

    DELETE /api/contracts/<secure_code>
    """
    from flask_login import current_user

    contract = ResourceGateway.get_by(
        Contract,
        secure_code=secure_code,
        is_deleted=False,
        skip_tenant_filter=True
    )

    if not contract:
        return jsonify({'error': _('合約不存在')}), 404

    try:
        contract.is_deleted = True
        contract.deleted_at = datetime.utcnow()
        contract.modified_by_secure_code = current_user.secure_code
        contract.modified_at = datetime.utcnow()
        db.session.commit()

        logger.info(f"Contract deleted: {contract.contract_number} by {current_user.email}")

        return jsonify({
            'message': _('合約已刪除')
        }), 200

    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to delete contract: {e}")
        return jsonify({'error': _('刪除合約失敗')}), 500


@contracts_bp.route('/<secure_code>/disable', methods=['PATCH'])
@system_admin_required
def disable_contract(secure_code: str):
    """
    停用合約 (系統管理員)

    PATCH /api/contracts/<secure_code>/disable
    """
    from flask_login import current_user

    contract = ResourceGateway.get_by(
        Contract,
        secure_code=secure_code,
        is_deleted=False,
        skip_tenant_filter=True
    )

    if not contract:
        return jsonify({'error': _('合約不存在')}), 404

    if contract.status == ContractStatus.DISABLED:
        return jsonify({'error': _('合約已是停用狀態')}), 400

    try:
        contract.status = ContractStatus.DISABLED
        contract.modified_by_secure_code = current_user.secure_code
        contract.modified_at = datetime.utcnow()
        db.session.commit()

        logger.info(f"Contract disabled: {contract.contract_number} by {current_user.email}")

        return jsonify({
            'message': _('合約已停用'),
            'contract': contract.to_dict()
        }), 200

    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to disable contract: {e}")
        return jsonify({'error': _('停用合約失敗')}), 500


@contracts_bp.route('/<secure_code>/enable', methods=['PATCH'])
@system_admin_required
def enable_contract(secure_code: str):
    """
    啟用合約 — 已停用，合約停用為單向操作，不可逆。
    保留端點回傳明確錯誤訊息，避免前端或 API 呼叫端困惑。
    """
    return jsonify({
        'error': _('合約停用後不可再啟用（單向操作）。如需恢復服務，請建立新合約。')
    }), 403


# =====================================================
# 企業合約管理 (企業管理員可檢視自己企業的合約)
# =====================================================

@contracts_bp.route('/my', methods=['GET'])
@admin_required
def list_my_contracts():
    """
    取得自己企業的合約列表 (企業管理員)

    GET /api/contracts/my
    """
    # 使用 ResourceGateway 的租戶過濾
    # check_permission=False: contract:read 為 SYSTEM 級，企業管理員看自己
    # 企業的合約由 @admin_required + 租戶過濾把關
    contracts = ResourceGateway.filter(
        Contract,
        order_by='-start_date',
        is_deleted=False,
        check_permission=False
    )

    return jsonify({
        'contracts': [c.to_dict() for c in contracts]
    }), 200
