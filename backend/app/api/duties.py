"""
BeakMask Duty API
職務管理 API

職務（Duty）是部門內的職責標籤，用於標記用戶在部門中的特定職責。
與 Role（系統權限）和 JobTitle（HR 職稱）不同。
"""
import logging
from datetime import datetime

from flask import Blueprint, request, jsonify
from flask_babel import gettext as _
from flask_login import current_user

from ..security.decorators import admin_required, login_required
from ..security.resource_gateway import ResourceGateway
from ..models import Duty, DutyCategory, OrganizationalUnit
from .. import db

logger = logging.getLogger(__name__)

duties_bp = Blueprint('api_duties', __name__, url_prefix='/api/duties')


# =====================================================
# 職務分類 API
# =====================================================

@duties_bp.route('/categories', methods=['GET'])
@admin_required
def list_categories():
    """
    取得職務分類列表

    GET /api/duties/categories
    Query params:
        - active_only: true = 只返回啟用的分類
    """
    active_only = request.args.get('active_only', 'false').lower() == 'true'

    filters = {'is_deleted': False}
    if active_only:
        filters['is_active'] = True

    categories = ResourceGateway.filter(
        DutyCategory,
        order_by='sort_order',
        **filters
    )

    return jsonify({
        'categories': [c.to_dict() for c in categories]
    }), 200


@duties_bp.route('/categories/<secure_code>', methods=['GET'])
@admin_required
def get_category(secure_code: str):
    """
    取得單一職務分類

    GET /api/duties/categories/<secure_code>
    """
    category = ResourceGateway.get_by(
        DutyCategory,
        secure_code=secure_code,
        is_deleted=False
    )

    if not category:
        return jsonify({'error': _('職務分類不存在')}), 404

    return jsonify({
        'category': category.to_dict()
    }), 200


@duties_bp.route('/categories', methods=['POST'])
@admin_required
def create_category():
    """
    建立職務分類

    POST /api/duties/categories
    Body: {
        "code": "TECH",
        "name": "技術類",
        "description": "技術相關職務",
        "sort_order": 0
    }
    """
    data = request.get_json()
    if not data:
        return jsonify({'error': _('請提供分類資料')}), 400

    required_fields = ['code', 'name']
    for field in required_fields:
        if not data.get(field):
            return jsonify({'error': _('缺少必要欄位: %(field)s', field=field)}), 400

    # 檢查代碼是否重複
    if ResourceGateway.exists(
        DutyCategory,
        code=data['code'].upper(),
        is_deleted=False
    ):
        return jsonify({'error': _('代碼 %(code)s 已存在', code=data["code"])}), 400

    try:
        category = DutyCategory(
            org_secure_code=current_user.org_secure_code,
            code=data['code'].upper(),
            name=data['name'],
            description=data.get('description'),
            sort_order=data.get('sort_order', 0),
            is_active=True
        )
        db.session.add(category)
        db.session.commit()

        logger.info(f"DutyCategory created: {category.code} by {current_user.email}")

        return jsonify({
            'message': _('職務分類建立成功'),
            'category': category.to_dict()
        }), 201

    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to create duty category: {e}")
        return jsonify({'error': _('建立職務分類失敗')}), 500


@duties_bp.route('/categories/<secure_code>', methods=['PUT'])
@admin_required
def update_category(secure_code: str):
    """
    更新職務分類

    PUT /api/duties/categories/<secure_code>
    """
    category = ResourceGateway.get_by(
        DutyCategory,
        secure_code=secure_code,
        is_deleted=False
    )

    if not category:
        return jsonify({'error': _('職務分類不存在')}), 404

    data = request.get_json()
    if not data:
        return jsonify({'error': _('請提供更新資料')}), 400

    try:
        if 'name' in data:
            category.name = data['name']
        if 'description' in data:
            category.description = data['description']
        if 'sort_order' in data:
            category.sort_order = data['sort_order']
        if 'is_active' in data:
            category.is_active = data['is_active']

        db.session.commit()

        return jsonify({
            'message': _('職務分類更新成功'),
            'category': category.to_dict()
        }), 200

    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to update duty category: {e}")
        return jsonify({'error': _('更新職務分類失敗')}), 500


@duties_bp.route('/categories/<secure_code>', methods=['DELETE'])
@admin_required
def delete_category(secure_code: str):
    """
    刪除職務分類 (軟刪除)

    DELETE /api/duties/categories/<secure_code>
    """
    category = ResourceGateway.get_by(
        DutyCategory,
        secure_code=secure_code,
        is_deleted=False
    )

    if not category:
        return jsonify({'error': _('職務分類不存在')}), 404

    # 檢查是否有職務使用此分類
    duty_count = ResourceGateway.count(
        Duty,
        category_secure_code=secure_code,
        is_deleted=False
    )

    if duty_count > 0:
        return jsonify({
            'error': _('此分類有 %(count)s 個職務使用中，請先刪除或移動職務', count=duty_count)
        }), 400

    try:
        category.is_deleted = True
        category.deleted_at = datetime.utcnow()
        db.session.commit()

        return jsonify({
            'message': _('職務分類已刪除')
        }), 200

    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to delete duty category: {e}")
        return jsonify({'error': _('刪除職務分類失敗')}), 500


# =====================================================
# 職務 API
# =====================================================

@duties_bp.route('/', methods=['GET'])
@admin_required
def list_duties():
    """
    取得職務列表

    GET /api/duties
    Query params:
        - unit: 篩選特定部門
        - category: 篩選特定分類
        - active_only: true = 只返回啟用的職務
    """
    unit_code = request.args.get('unit')
    category_code = request.args.get('category')
    active_only = request.args.get('active_only', 'false').lower() == 'true'

    filters = {'is_deleted': False}
    if unit_code:
        filters['unit_secure_code'] = unit_code
    if category_code:
        filters['category_secure_code'] = category_code
    if active_only:
        filters['is_active'] = True

    duties = ResourceGateway.filter(
        Duty,
        order_by='sort_order',
        **filters
    )

    return jsonify({
        'duties': [d.to_dict() for d in duties]
    }), 200


@duties_bp.route('/<secure_code>', methods=['GET'])
@admin_required
def get_duty(secure_code: str):
    """
    取得單一職務

    GET /api/duties/<secure_code>
    """
    duty = ResourceGateway.get_by(
        Duty,
        secure_code=secure_code,
        is_deleted=False
    )

    if not duty:
        return jsonify({'error': _('職務不存在')}), 404

    return jsonify({
        'duty': duty.to_dict()
    }), 200


@duties_bp.route('/', methods=['POST'])
@admin_required
def create_duty():
    """
    建立職務

    POST /api/duties
    Body: {
        "unit_secure_code": "xxx",
        "category_secure_code": "xxx",
        "name": "防火牆管理員",
        "description": "負責防火牆設定與維護",
        "sort_order": 0
    }
    """
    data = request.get_json()
    if not data:
        return jsonify({'error': _('請提供職務資料')}), 400

    required_fields = ['unit_secure_code', 'category_secure_code', 'name']
    for field in required_fields:
        if not data.get(field):
            return jsonify({'error': _('缺少必要欄位: %(field)s', field=field)}), 400

    # 驗證部門
    unit = ResourceGateway.get_by(
        OrganizationalUnit,
        secure_code=data['unit_secure_code'],
        is_deleted=False
    )
    if not unit:
        return jsonify({'error': _('部門不存在')}), 400

    # 驗證分類
    category = ResourceGateway.get_by(
        DutyCategory,
        secure_code=data['category_secure_code'],
        is_deleted=False
    )
    if not category:
        return jsonify({'error': _('職務分類不存在')}), 400

    # 檢查唯一性 (部門 + 分類 + 名稱)
    existing = ResourceGateway.get_by(
        Duty,
        unit_secure_code=data['unit_secure_code'],
        category_secure_code=data['category_secure_code'],
        name=data['name'],
        is_deleted=False
    )
    if existing:
        return jsonify({
            'error': _('此部門的 %(category)s 分類已有名為「%(name)s」的職務', category=category.name, name=data["name"])
        }), 400

    try:
        duty = Duty(
            org_secure_code=current_user.org_secure_code,
            unit_secure_code=data['unit_secure_code'],
            category_secure_code=data['category_secure_code'],
            name=data['name'],
            description=data.get('description'),
            sort_order=data.get('sort_order', 0),
            is_active=True
        )
        db.session.add(duty)
        db.session.commit()

        logger.info(f"Duty created: {duty.name} in {unit.name} by {current_user.email}")

        return jsonify({
            'message': _('職務建立成功'),
            'duty': duty.to_dict()
        }), 201

    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to create duty: {e}")
        return jsonify({'error': _('建立職務失敗')}), 500


@duties_bp.route('/<secure_code>', methods=['PUT'])
@admin_required
def update_duty(secure_code: str):
    """
    更新職務

    PUT /api/duties/<secure_code>
    """
    duty = ResourceGateway.get_by(
        Duty,
        secure_code=secure_code,
        is_deleted=False
    )

    if not duty:
        return jsonify({'error': _('職務不存在')}), 404

    data = request.get_json()
    if not data:
        return jsonify({'error': _('請提供更新資料')}), 400

    try:
        # 如果要更新名稱，需要檢查唯一性
        if 'name' in data and data['name'] != duty.name:
            existing = ResourceGateway.get_by(
                Duty,
                unit_secure_code=duty.unit_secure_code,
                category_secure_code=duty.category_secure_code,
                name=data['name'],
                is_deleted=False
            )
            if existing:
                return jsonify({
                    'error': _('此部門的分類已有名為「%(name)s」的職務', name=data["name"])
                }), 400
            duty.name = data['name']

        if 'description' in data:
            duty.description = data['description']
        if 'sort_order' in data:
            duty.sort_order = data['sort_order']
        if 'is_active' in data:
            duty.is_active = data['is_active']

        # 如果要更換分類
        if 'category_secure_code' in data and data['category_secure_code'] != duty.category_secure_code:
            category = ResourceGateway.get_by(
                DutyCategory,
                secure_code=data['category_secure_code'],
                is_deleted=False
            )
            if not category:
                return jsonify({'error': _('職務分類不存在')}), 400

            # 檢查新分類下是否有同名職務
            existing = ResourceGateway.get_by(
                Duty,
                unit_secure_code=duty.unit_secure_code,
                category_secure_code=data['category_secure_code'],
                name=duty.name,
                is_deleted=False
            )
            if existing:
                return jsonify({
                    'error': _('目標分類已有名為「%(name)s」的職務', name=duty.name)
                }), 400

            duty.category_secure_code = data['category_secure_code']

        db.session.commit()

        return jsonify({
            'message': _('職務更新成功'),
            'duty': duty.to_dict()
        }), 200

    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to update duty: {e}")
        return jsonify({'error': _('更新職務失敗')}), 500


@duties_bp.route('/<secure_code>', methods=['DELETE'])
@admin_required
def delete_duty(secure_code: str):
    """
    刪除職務 (軟刪除)

    DELETE /api/duties/<secure_code>
    """
    duty = ResourceGateway.get_by(
        Duty,
        secure_code=secure_code,
        is_deleted=False
    )

    if not duty:
        return jsonify({'error': _('職務不存在')}), 404

    # TODO: 檢查是否有用戶使用此職務 (UserDuty 之後實作)

    try:
        duty.is_deleted = True
        duty.deleted_at = datetime.utcnow()
        db.session.commit()

        return jsonify({
            'message': _('職務已刪除')
        }), 200

    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to delete duty: {e}")
        return jsonify({'error': _('刪除職務失敗')}), 500


# =====================================================
# 便捷 API
# =====================================================

@duties_bp.route('/by-unit/<unit_secure_code>', methods=['GET'])
@admin_required
def list_duties_by_unit(unit_secure_code: str):
    """
    取得部門的所有職務（依分類分組）

    GET /api/duties/by-unit/<unit_secure_code>
    """
    # 驗證部門
    unit = ResourceGateway.get_by(
        OrganizationalUnit,
        secure_code=unit_secure_code,
        is_deleted=False
    )
    if not unit:
        return jsonify({'error': _('部門不存在')}), 404

    # 取得該部門的所有職務
    duties = ResourceGateway.filter(
        Duty,
        unit_secure_code=unit_secure_code,
        is_deleted=False,
        order_by='sort_order'
    )

    # 依分類分組
    grouped = {}
    for duty in duties:
        cat_code = duty.category_secure_code
        if cat_code not in grouped:
            grouped[cat_code] = {
                'category': duty.category.to_dict() if duty.category else None,
                'duties': []
            }
        grouped[cat_code]['duties'].append(duty.to_dict(include_relations=False))

    return jsonify({
        'unit': {
            'secure_code': unit.secure_code,
            'name': unit.name,
            'code': unit.code
        },
        'groups': list(grouped.values())
    }), 200
