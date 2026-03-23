"""
BeakMask Code Service API
通用代碼產生與驗證 API

提供統一的 /api/code/generate 和 /api/code/validate 端點，
供所有需要唯一識別碼的建立表單使用。
"""
import logging
from flask import Blueprint, request, jsonify
from sqlalchemy import func

from ..security.decorators import login_required
from ..security.resource_gateway import ResourceGateway
from ..services.code_generator import get_code_generator
from ..models import (
    Role, OrganizationalUnit, JobTitle, JobFamily, JobLevel, MenuItem, Organization
)
# 延遲匯入模組 model（避免循環依賴）
def _get_dc_sub_system():
    from modules.nocode_builder.models.sub_system import DcSubSystem
    return DcSubSystem
from .. import csrf

logger = logging.getLogger(__name__)

code_bp = Blueprint('api_code', __name__, url_prefix='/api/code')

# 實體註冊表：定義各實體的 Model 與查詢條件
def _build_lookup_category_exists_checker():
    """建立 lookup_category 的重複檢查函數（查企業 DB）"""
    def exists_checker(code):
        from flask_login import current_user
        from ..services.lookup_org_service import LookupOrgService
        org_sc = current_user.org_secure_code
        cat = LookupOrgService.get_category_by_code(org_sc, code)
        return cat is not None
    return exists_checker


ENTITY_REGISTRY = {
    'role': {
        'model': Role,
        'tenant': True,
        'code_field': 'code',
    },
    'department': {
        'model': OrganizationalUnit,
        'tenant': True,
        'code_field': 'code',
        'extra': {'unit_type': 'DEPARTMENT'},
    },
    'group': {
        'model': OrganizationalUnit,
        'tenant': True,
        'code_field': 'code',
        'extra': {'unit_type': 'GROUP'},
    },
    'job_title': {
        'model': JobTitle,
        'tenant': True,
        'code_field': 'code',
    },
    'job_family': {
        'model': JobFamily,
        'tenant': True,
        'code_field': 'code',
    },
    'job_level': {
        'model': JobLevel,
        'tenant': True,
        'code_field': 'code',
    },
    'menu_item': {
        'model': MenuItem,
        'tenant': True,
        'code_field': 'code',
    },
    'organization': {
        'model': Organization,
        'tenant': False,
        'code_field': 'code',
    },
    'sub_system': {
        'model': None,  # 延遲載入
        'tenant': True,
        'code_field': 'code',
        '_lazy_model': _get_dc_sub_system,
    },
    'lookup_category': {
        'model': None,
        'tenant': True,
        'code_field': 'code',
        '_custom_exists': _build_lookup_category_exists_checker,
    },
}


def _build_exists_checker(entity_config):
    """建立 case-insensitive 的重複檢查函數"""
    # 自訂 exists checker（如 lookup_category 查企業 DB）
    custom_builder = entity_config.get('_custom_exists')
    if custom_builder:
        return custom_builder()

    lazy_loader = entity_config.get('_lazy_model')
    model = lazy_loader() if lazy_loader else entity_config['model']
    code_field = entity_config['code_field']
    extra = entity_config.get('extra', {})

    def exists_checker(code):
        query = model.query.filter(
            func.upper(getattr(model, code_field)) == code.upper(),
            model.is_deleted == False
        )
        for key, value in extra.items():
            query = query.filter(getattr(model, key) == value)

        if entity_config['tenant']:
            from flask_login import current_user
            query = query.filter(
                model.org_secure_code == current_user.org_secure_code
            )

        return query.first() is not None

    return exists_checker


@code_bp.route('/generate', methods=['POST'])
@csrf.exempt
@login_required
def generate_code():
    """
    產生建議代碼

    POST /api/code/generate
    Body: { "entity_type": "department", "name": "業務部" }
    Response: { "code": "SALES_DEPT", "suggestions": ["SALES_DEPT", "SALES_DEPT_01", ...] }
    """
    data = request.get_json()
    if not data:
        return jsonify({'error': '請提供 JSON 資料'}), 400

    entity_type = data.get('entity_type', '').strip()
    name = data.get('name', '').strip()

    if not entity_type or entity_type not in ENTITY_REGISTRY:
        return jsonify({
            'error': f'不支援的實體類型: {entity_type}',
            'supported': list(ENTITY_REGISTRY.keys())
        }), 400

    if not name:
        return jsonify({'error': '請提供名稱'}), 400

    entity_config = ENTITY_REGISTRY[entity_type]
    generator = get_code_generator()
    exists_checker = _build_exists_checker(entity_config)

    try:
        code = generator.generate(name, exists_checker=exists_checker)
        suggestions = generator.suggest(name, exists_checker=exists_checker, count=3)

        return jsonify({
            'code': code,
            'suggestions': suggestions
        }), 200

    except ValueError as e:
        return jsonify({'error': str(e)}), 400


@code_bp.route('/validate', methods=['POST'])
@csrf.exempt
@login_required
def validate_code():
    """
    驗證代碼格式與唯一性

    POST /api/code/validate
    Body: { "entity_type": "department", "code": "Sales_Dept" }
    Response: { "valid": true } 或 { "valid": false, "error": "..." }
    """
    data = request.get_json()
    if not data:
        return jsonify({'error': '請提供 JSON 資料'}), 400

    entity_type = data.get('entity_type', '').strip()
    code = data.get('code', '').strip()

    if not entity_type or entity_type not in ENTITY_REGISTRY:
        return jsonify({
            'error': f'不支援的實體類型: {entity_type}',
            'supported': list(ENTITY_REGISTRY.keys())
        }), 400

    if not code:
        return jsonify({'error': '請提供代碼'}), 400

    entity_config = ENTITY_REGISTRY[entity_type]
    generator = get_code_generator()
    exists_checker = _build_exists_checker(entity_config)

    # 先驗證格式（不做 .upper()，允許混合大小寫）
    is_valid, error = generator.validate(code)
    if not is_valid:
        return jsonify({'valid': False, 'error': error}), 200

    # 再做 case-insensitive 重複檢查
    if exists_checker(code):
        return jsonify({'valid': False, 'error': f'代碼 "{code}" 已存在（不區分大小寫）'}), 200

    return jsonify({'valid': True}), 200
