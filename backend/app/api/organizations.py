"""
BeakMask Organizations API
企業/組織管理路由
"""
import json
import logging
from datetime import datetime, date, timedelta

from flask import Blueprint, request, jsonify
from flask_babel import gettext as _
from flask_login import current_user

from ..security.decorators import login_required, admin_required, system_admin_required
from ..security.resource_gateway import ResourceGateway
from ..models import Organization, CustomerType, Contract
from ..services.organization_service import OrganizationService
from .. import db

logger = logging.getLogger(__name__)

organizations_bp = Blueprint('api_organizations', __name__)


@organizations_bp.route('/', methods=['GET'])
@system_admin_required
def list_organizations():
    """
    取得企業列表（僅限系統管理員）。

    GET /api/organizations?page=1&per_page=20
    Query params:
        - customer_type: 客戶類型篩選
        - is_active: 啟用狀態篩選
    """
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    customer_type = request.args.get('customer_type')
    is_active = request.args.get('is_active')

    filters = {'is_deleted': False}
    if customer_type:
        filters['customer_type'] = customer_type
    if is_active is not None:
        filters['is_active'] = (is_active.lower() == 'true')

    result = ResourceGateway.list(
        Organization,
        page=page,
        per_page=min(per_page, 100),
        order_by='-created_at',
        **filters
    )

    return jsonify({
        'organizations': [o.to_dict(include_contracts=True) for o in result['items']],
        'pagination': {
            'total': result['total'],
            'page': result['page'],
            'per_page': result['per_page'],
            'pages': result['pages']
        }
    }), 200


@organizations_bp.route('/current', methods=['GET'])
@login_required
def get_current_organization():
    """
    取得當前用戶所屬企業資訊。

    GET /api/organizations/current
    """
    org = ResourceGateway.get_by(
        Organization,
        secure_code=current_user.org_secure_code,
        is_deleted=False,
        check_permission=False
    )

    if not org:
        return jsonify({'error': _('企業不存在')}), 404

    return jsonify({'organization': org.to_dict(include_contracts=True)}), 200


@organizations_bp.route('/<secure_code>', methods=['GET'])
@system_admin_required
def get_organization(secure_code: str):
    """
    取得單一企業資訊（僅限系統管理員）。

    GET /api/organizations/<secure_code>
    """
    org = ResourceGateway.get_by(
        Organization,
        secure_code=secure_code,
        is_deleted=False,
        check_permission=False
    )

    if not org:
        return jsonify({'error': _('企業不存在')}), 404

    return jsonify({'organization': org.to_dict(include_contracts=True)}), 200


@organizations_bp.route('/', methods=['POST'])
@system_admin_required
def create_organization():
    """
    建立新企業（僅限系統管理員）。

    POST /api/organizations
    Body: {
        "code": "ACME",
        "name": "ACME Corporation",
        "domain_name": "acme.com.tw",
        "customer_type": "TRIAL",
        "user_limit": 50,
        "contact_person": "張三",
        "contact_email": "contact@acme.com.tw",
        "admin_password": "required_password"
    }
    """
    data = request.get_json()

    if not data:
        return jsonify({'error': _('請提供企業資料')}), 400

    required_fields = ['code', 'name', 'domain_name', 'admin_password']
    for field in required_fields:
        if not data.get(field):
            return jsonify({'error': _('缺少必要欄位: %(field)s', field=field)}), 400

    try:
        org, admin_user = OrganizationService.create_organization(
            code=data['code'],
            name=data['name'],
            domain_name=data['domain_name'],
            customer_type=data.get('customer_type', CustomerType.TRIAL),
            user_limit=data.get('user_limit', 5),
            description=data.get('description'),
            contact_person=data.get('contact_person'),
            contact_email=data.get('contact_email'),
            contact_phone=data.get('contact_phone'),
            address=data.get('address'),
            admin_password=data.get('admin_password'),
            created_by=current_user.email
        )

        # 自動建立 10 天試用合約（預設啟用流程模組）
        today = date.today()
        OrganizationService.create_contract(
            org_secure_code=org.secure_code,
            start_date=today,
            end_date=today + timedelta(days=10),
            name=f'{data["name"]} 試用合約',
            modules_config=json.dumps(['form_workflow']),
            created_by=current_user.secure_code
        )

        db.session.commit()

        result = {
            'message': _('企業建立成功'),
            'organization': org.to_dict()
        }

        if admin_user:
            result['admin'] = {
                'username': admin_user.username,
                'email': admin_user.email,
                'note': _('預設密碼為 ChangeMe123! (如未指定)')
            }

        return jsonify(result), 201

    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to create organization: {e}")
        return jsonify({'error': _('建立企業失敗')}), 500


@organizations_bp.route('/<secure_code>', methods=['PUT'])
@admin_required
def update_organization(secure_code: str):
    """
    更新企業資訊（企業管理員可更新自己的企業）。

    PUT /api/organizations/<secure_code>
    """
    org = ResourceGateway.get_by(
        Organization,
        secure_code=secure_code,
        is_deleted=False,
        check_permission=False
    )

    if not org:
        return jsonify({'error': _('企業不存在')}), 404

    # Check permission: org admin can only update their own org
    if not current_user.is_system_admin and org.secure_code != current_user.org_secure_code:
        return jsonify({'error': _('無權限')}), 403

    data = request.get_json()

    if not data:
        return jsonify({'error': _('請提供更新資料')}), 400

    try:
        # 系統管理員可更新的欄位
        if current_user.is_system_admin:
            allowed_fields = [
                'name', 'description', 'customer_type', 'user_limit',
                'is_active', 'contact_person', 'contact_email',
                'contact_phone', 'address'
            ]
        else:
            # 企業管理員只能更新有限欄位
            allowed_fields = [
                'name', 'description', 'contact_person',
                'contact_email', 'contact_phone', 'address'
            ]

        for field in allowed_fields:
            if field in data:
                setattr(org, field, data[field])

        db.session.commit()

        return jsonify({
            'message': _('企業更新成功'),
            'organization': org.to_dict()
        }), 200

    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to update organization: {e}")
        return jsonify({'error': _('更新企業失敗')}), 500


@organizations_bp.route('/<secure_code>', methods=['DELETE'])
@system_admin_required
def delete_organization(secure_code: str):
    """
    刪除企業 (軟刪除，僅限系統管理員)

    DELETE /api/organizations/<secure_code>
    """
    org = ResourceGateway.get_by(
        Organization,
        secure_code=secure_code,
        is_deleted=False,
        check_permission=False
    )

    if not org:
        return jsonify({'error': _('企業不存在')}), 404

    # 系統企業不可刪除
    if org.is_system_org:
        return jsonify({'error': _('系統企業不可刪除')}), 400

    try:
        now = datetime.utcnow()

        # 軟刪除相關合約
        contracts = Contract.query.filter_by(
            org_secure_code=org.secure_code,
            is_deleted=False
        ).all()
        for contract in contracts:
            contract.is_deleted = True
            contract.deleted_at = now

        # 軟刪除企業
        org.is_deleted = True
        org.deleted_at = now
        org.is_active = False
        db.session.commit()

        return jsonify({
            'message': _('企業已刪除'),
            'deleted_contracts': len(contracts)
        }), 200

    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to delete organization: {e}")
        return jsonify({'error': _('刪除企業失敗')}), 500


@organizations_bp.route('/<secure_code>/stats', methods=['GET'])
@system_admin_required
def get_organization_stats(secure_code: str):
    """
    取得企業統計資訊

    GET /api/organizations/<secure_code>/stats
    """
    org = ResourceGateway.get_by(
        Organization,
        secure_code=secure_code,
        is_deleted=False,
        check_permission=False
    )

    if not org:
        return jsonify({'error': _('企業不存在')}), 404

    return jsonify({
        'stats': {
            'user_count': org.get_active_user_count(),
            'user_limit': org.user_limit,
            'can_create_user': org.can_create_user(),
            'is_contract_valid': org.is_contract_valid(),
            'contract_range': None
        }
    }), 200
