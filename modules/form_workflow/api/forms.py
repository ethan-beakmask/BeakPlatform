"""
FormWorkflow Module - Forms API
表單設計器 API

提供與 A6 相容的 API 端點，支援表單設計器前端。
"""
import secrets
from datetime import datetime
from flask import Blueprint, render_template, jsonify, request
from flask_login import current_user

from app.security.decorators import login_required
from app.platform.auth import (
    has_permission,
    require_permission,
)
from app.platform.data import get_current_org
from app import db, csrf

# 建立 API Blueprint - 使用與 A6 相同的路徑
forms_bp = Blueprint(
    'form_workflow_forms',
    __name__,
    url_prefix='/api/forms',
    template_folder='../templates'
)


# =============================================================================
# 輔助函數
# =============================================================================

def _get_default_schema():
    """
    取得預設表單 schema（空表單）
    """
    return {
        "display": "form",
        "components": []
    }


def extract_input_fields(components, fields=None):
    """
    遞迴提取 schema 中所有輸入欄位的 key 和 label

    Args:
        components: Form.io schema 的 components 陣列
        fields: 累積的欄位列表

    Returns:
        list: [{'key': str, 'label': str, 'type': str}, ...]
    """
    if fields is None:
        fields = []

    for comp in (components or []):
        key = comp.get('key', '')
        label = comp.get('label', '')
        comp_type = comp.get('type', '')

        # 只處理輸入型元件（排除 button, submit, htmlelement, content 等）
        if comp.get('input', False) and comp_type not in ('button', 'submit'):
            if key:
                fields.append({
                    'key': key,
                    'label': label or key,
                    'type': comp_type
                })

        # 遞迴處理巢狀結構
        if 'components' in comp:
            extract_input_fields(comp['components'], fields)
        if 'columns' in comp:
            for col in comp['columns']:
                extract_input_fields(col.get('components', []), fields)

    return fields


# =============================================================================
# 頁面路由
# =============================================================================

@forms_bp.route('/list')
@login_required
def list_page():
    """表單模板列表頁面"""
    return render_template(
        'modules/form_workflow/template_list.html',
        active_menu_code='form_workflow.templates'
    )


@forms_bp.route('/designer')
@forms_bp.route('/designer/<secure_code>')
@login_required
def designer(secure_code=None):
    """表單設計器頁面"""
    from ..models import FwFormTemplate

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    if secure_code:
        template = FwFormTemplate.query.filter_by(
            secure_code=secure_code,
            org_secure_code=org.secure_code,
            is_deleted=False
        ).first()

        if not template:
            return jsonify({'success': False, 'error': 'Template not found'}), 404
    else:
        template = None

    return render_template(
        'modules/form_workflow/form_designer.html',
        org_secure_code=org.secure_code,
        form_secure_code=secure_code,
        form=template.to_dict(include_schema=True) if template else None
    )


@forms_bp.route('/designer/standalone')
@login_required
def designer_standalone():
    """表單設計器獨立頁面（用於 iframe 嵌入或直接訪問）"""
    from ..models import FwFormTemplate

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    secure_code = request.args.get('id')
    template = None

    if secure_code:
        template = FwFormTemplate.query.filter_by(
            secure_code=secure_code,
            org_secure_code=org.secure_code,
            is_deleted=False
        ).first()

    return render_template(
        'modules/form_workflow/form_designer.html',
        org_secure_code=org.secure_code,
        form_secure_code=secure_code,
        form=template.to_dict(include_schema=True) if template else None
    )


# =============================================================================
# 分類 API
# =============================================================================

@forms_bp.route('/data/categories')
@login_required
def list_categories():
    """取得表單分類列表"""
    from ..models import FwCategory
    from app.platform.data import get_current_org
    from app import db

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'message': 'Organization not found'}), 400

    # 查詢：系統分類 + 當前企業分類
    query = FwCategory.query.filter_by(is_deleted=False).filter(
        db.or_(
            FwCategory.org_secure_code.is_(None),  # 系統分類
            FwCategory.org_secure_code == org.secure_code  # 企業分類
        )
    ).filter(FwCategory.show_in_form_design == True)

    categories = query.order_by(FwCategory.display_order, FwCategory.name).all()

    result = [
        {'id': cat.name, 'name': cat.name, 'description': cat.description or ''}
        for cat in categories
    ]
    return jsonify({
        'success': True,
        'data': result,
        'categories': result  # 向後相容
    })


# =============================================================================
# 數據 API
# =============================================================================

@forms_bp.route('/data/templates')
@login_required
def list_templates():
    """取得表單模板列表"""
    from ..models import FwFormTemplate

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    query = FwFormTemplate.query.filter_by(
        org_secure_code=org.secure_code,
        is_deleted=False
    )

    # 搜尋
    q = request.args.get('q', '').strip()
    if q:
        query = query.filter(
            FwFormTemplate.name.ilike(f'%{q}%') |
            FwFormTemplate.code.ilike(f'%{q}%')
        )

    templates = query.order_by(FwFormTemplate.updated_at.desc()).all()

    return jsonify({
        'success': True,
        'templates': [t.to_dict(include_schema=False) for t in templates]
    })


@forms_bp.route('/data/templates/<secure_code>')
@login_required
def get_template(secure_code):
    """取得單一表單模板"""
    from ..models import FwFormTemplate

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    template = FwFormTemplate.query.filter_by(
        secure_code=secure_code,
        org_secure_code=org.secure_code,
        is_deleted=False
    ).first()

    if not template:
        return jsonify({'success': False, 'error': 'Template not found'}), 404

    result = template.to_dict(include_schema=True)

    # 確保有預設的 schema
    if not result.get('schema'):
        result['schema'] = _get_default_schema()

    return jsonify({
        'success': True,
        'data': result
    })


@forms_bp.route('/data/templates', methods=['POST'])
@csrf.exempt
@login_required
def create_template():
    """建立表單模板"""
    from ..models import FwFormTemplate

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    data = request.get_json() or {}
    name = data.get('name', '').strip()

    if not name:
        return jsonify({'success': False, 'error': 'Name is required'}), 400

    # 自動產生 code
    code = data.get('code', '').strip().upper()
    if not code:
        code = f'FT{secrets.token_hex(4).upper()}'

    # 檢查 code 是否重複
    existing = FwFormTemplate.query.filter_by(
        code=code,
        org_secure_code=org.secure_code,
        is_deleted=False
    ).first()
    if existing:
        return jsonify({'success': False, 'error': f'Code {code} already exists'}), 400

    template = FwFormTemplate(
        secure_code=secrets.token_urlsafe(16),
        org_secure_code=org.secure_code,
        name=name,
        code=code,
        description=data.get('description', ''),
        schema=data.get('schema') or _get_default_schema(),
        is_active=data.get('is_active', True),
        owner_secure_code=current_user.secure_code
    )

    db.session.add(template)
    db.session.commit()

    result = template.to_dict(include_schema=True)
    result['secure_code'] = template.secure_code
    return jsonify({
        'success': True,
        'data': result,
        'message': '表單模板已建立'
    })


@forms_bp.route('/data/templates/<secure_code>', methods=['PUT'])
@csrf.exempt
@login_required
def update_template(secure_code):
    """更新表單模板"""
    from ..models import FwFormTemplate

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    template = FwFormTemplate.query.filter_by(
        secure_code=secure_code,
        org_secure_code=org.secure_code,
        is_deleted=False
    ).first()

    if not template:
        return jsonify({'success': False, 'error': 'Template not found'}), 404

    data = request.get_json() or {}

    if 'name' in data:
        template.name = data['name'].strip()
    if 'description' in data:
        template.description = data['description']
    if 'schema' in data:
        template.schema = data['schema']
    if 'is_active' in data:
        template.is_active = data['is_active']
    if 'builder_config' in data:
        template.builder_config = data['builder_config']

    template.updated_at = datetime.utcnow()
    db.session.commit()

    return jsonify({
        'success': True,
        'data': template.to_dict(include_schema=True),
        'message': '表單模板已更新'
    })


@forms_bp.route('/data/templates/<secure_code>', methods=['DELETE'])
@csrf.exempt
@login_required
def delete_template(secure_code):
    """刪除表單模板（軟刪除）"""
    from ..models import FwFormTemplate

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    template = FwFormTemplate.query.filter_by(
        secure_code=secure_code,
        org_secure_code=org.secure_code,
        is_deleted=False
    ).first()

    if not template:
        return jsonify({'success': False, 'error': 'Template not found'}), 404

    template.is_deleted = True
    template.updated_at = datetime.utcnow()
    db.session.commit()

    return jsonify({
        'success': True,
        'message': '表單模板已刪除'
    })


@forms_bp.route('/data/templates/<secure_code>/publish', methods=['POST'])
@csrf.exempt
@login_required
def publish_template(secure_code):
    """發布表單模板"""
    from ..models import FwFormTemplate

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    template = FwFormTemplate.query.filter_by(
        secure_code=secure_code,
        org_secure_code=org.secure_code,
        is_deleted=False
    ).first()

    if not template:
        return jsonify({'success': False, 'error': 'Template not found'}), 404

    # 檢查是否可以發布
    if not template.schema or not template.schema.get('components'):
        return jsonify({'success': False, 'error': '表單沒有任何欄位，無法發布'}), 400

    template.is_published = True
    template.publish_at = datetime.utcnow()
    template.updated_at = datetime.utcnow()
    db.session.commit()

    return jsonify({
        'success': True,
        'data': template.to_dict(include_schema=True),
        'message': '表單模板已發布'
    })


@forms_bp.route('/data/templates/<secure_code>/unpublish', methods=['POST'])
@csrf.exempt
@login_required
def unpublish_template(secure_code):
    """取消發布表單模板"""
    from ..models import FwFormTemplate

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    template = FwFormTemplate.query.filter_by(
        secure_code=secure_code,
        org_secure_code=org.secure_code,
        is_deleted=False
    ).first()

    if not template:
        return jsonify({'success': False, 'error': 'Template not found'}), 404

    template.is_published = False
    template.updated_at = datetime.utcnow()
    db.session.commit()

    return jsonify({
        'success': True,
        'data': template.to_dict(include_schema=True),
        'message': '表單模板已取消發布'
    })


# =============================================================================
# 欄位提取 API
# =============================================================================

@forms_bp.route('/data/templates/<secure_code>/fields')
@login_required
def get_template_fields(secure_code):
    """取得表單模板的欄位列表"""
    from ..models import FwFormTemplate

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    template = FwFormTemplate.query.filter_by(
        secure_code=secure_code,
        org_secure_code=org.secure_code,
        is_deleted=False
    ).first()

    if not template:
        return jsonify({'success': False, 'error': 'Template not found'}), 404

    # 從 schema 中提取欄位
    schema = template.schema or {}
    components = schema.get('components', [])
    fields = extract_input_fields(components)

    return jsonify({
        'success': True,
        'fields': fields,
        'form_code': template.code,
        'form_name': template.name
    })


# =============================================================================
# 版本 API
# =============================================================================

# =============================================================================
# Form.io 預設範本 API
# =============================================================================

# 預設的 Form.io 範本（供設計器載入使用）
_FORMIO_TEMPLATES = [
    {
        'id': 'basic_form',
        'name': '基本表單',
        'description': '包含常用欄位的基礎表單',
        'category': 'basic',
        'version': '1.0',
        'schema': {
            'display': 'form',
            'components': [
                {
                    'type': 'textfield',
                    'key': 'title',
                    'label': '標題',
                    'placeholder': '請輸入標題',
                    'input': True,
                    'validate': {'required': True}
                },
                {
                    'type': 'textarea',
                    'key': 'content',
                    'label': '內容',
                    'placeholder': '請輸入內容',
                    'input': True,
                    'rows': 5
                },
                {
                    'type': 'datetime',
                    'key': 'dueDate',
                    'label': '截止日期',
                    'input': True
                }
            ]
        }
    },
    {
        'id': 'leave_request',
        'name': '請假單',
        'description': '員工請假申請表單',
        'category': 'hr',
        'version': '1.0',
        'schema': {
            'display': 'form',
            'components': [
                {
                    'type': 'select',
                    'key': 'leaveType',
                    'label': '假別',
                    'input': True,
                    'validate': {'required': True},
                    'data': {
                        'values': [
                            {'label': '特休', 'value': 'annual'},
                            {'label': '事假', 'value': 'personal'},
                            {'label': '病假', 'value': 'sick'},
                            {'label': '婚假', 'value': 'marriage'},
                            {'label': '喪假', 'value': 'bereavement'}
                        ]
                    }
                },
                {
                    'type': 'datetime',
                    'key': 'startDate',
                    'label': '開始日期',
                    'input': True,
                    'validate': {'required': True}
                },
                {
                    'type': 'datetime',
                    'key': 'endDate',
                    'label': '結束日期',
                    'input': True,
                    'validate': {'required': True}
                },
                {
                    'type': 'number',
                    'key': 'days',
                    'label': '天數',
                    'input': True,
                    'validate': {'required': True, 'min': 0.5}
                },
                {
                    'type': 'textarea',
                    'key': 'reason',
                    'label': '請假事由',
                    'input': True,
                    'rows': 3
                }
            ]
        }
    },
    {
        'id': 'expense_claim',
        'name': '費用報銷單',
        'description': '費用報銷申請表單',
        'category': 'finance',
        'version': '1.0',
        'schema': {
            'display': 'form',
            'components': [
                {
                    'type': 'select',
                    'key': 'expenseType',
                    'label': '費用類別',
                    'input': True,
                    'validate': {'required': True},
                    'data': {
                        'values': [
                            {'label': '交通費', 'value': 'transport'},
                            {'label': '餐費', 'value': 'meal'},
                            {'label': '住宿費', 'value': 'lodging'},
                            {'label': '辦公用品', 'value': 'supplies'},
                            {'label': '其他', 'value': 'other'}
                        ]
                    }
                },
                {
                    'type': 'datetime',
                    'key': 'expenseDate',
                    'label': '發生日期',
                    'input': True,
                    'validate': {'required': True}
                },
                {
                    'type': 'number',
                    'key': 'amount',
                    'label': '金額',
                    'input': True,
                    'validate': {'required': True, 'min': 0},
                    'prefix': 'NT$'
                },
                {
                    'type': 'textarea',
                    'key': 'description',
                    'label': '費用說明',
                    'input': True,
                    'rows': 3
                },
                {
                    'type': 'file',
                    'key': 'receipts',
                    'label': '收據附件',
                    'input': True,
                    'multiple': True,
                    'storage': 'base64'
                }
            ]
        }
    },
    {
        'id': 'purchase_request',
        'name': '採購申請單',
        'description': '物品採購申請表單',
        'category': 'procurement',
        'version': '1.0',
        'schema': {
            'display': 'form',
            'components': [
                {
                    'type': 'textfield',
                    'key': 'itemName',
                    'label': '品項名稱',
                    'input': True,
                    'validate': {'required': True}
                },
                {
                    'type': 'number',
                    'key': 'quantity',
                    'label': '數量',
                    'input': True,
                    'validate': {'required': True, 'min': 1}
                },
                {
                    'type': 'number',
                    'key': 'unitPrice',
                    'label': '單價',
                    'input': True,
                    'validate': {'required': True, 'min': 0},
                    'prefix': 'NT$'
                },
                {
                    'type': 'number',
                    'key': 'totalAmount',
                    'label': '總金額',
                    'input': True,
                    'disabled': True,
                    'prefix': 'NT$',
                    'calculateValue': 'value = data.quantity * data.unitPrice'
                },
                {
                    'type': 'textarea',
                    'key': 'purpose',
                    'label': '採購用途',
                    'input': True,
                    'rows': 3,
                    'validate': {'required': True}
                },
                {
                    'type': 'textfield',
                    'key': 'vendor',
                    'label': '建議廠商',
                    'input': True
                }
            ]
        }
    }
]


@forms_bp.route('/data/formio-templates')
@login_required
def list_formio_templates():
    """取得 Form.io 預設範本列表"""
    return jsonify({
        'success': True,
        'data': [
            {
                'id': t['id'],
                'name': t['name'],
                'description': t['description'],
                'category': t['category'],
                'version': t['version']
            }
            for t in _FORMIO_TEMPLATES
        ]
    })


@forms_bp.route('/data/formio-templates/<template_id>')
@login_required
def get_formio_template(template_id):
    """取得單一 Form.io 預設範本"""
    template = next((t for t in _FORMIO_TEMPLATES if t['id'] == template_id), None)

    if not template:
        return jsonify({'success': False, 'error': 'Template not found'}), 404

    return jsonify({
        'success': True,
        'data': template
    })


# =============================================================================
# 版本 API
# =============================================================================

@forms_bp.route('/data/templates/<secure_code>/save-new-version', methods=['POST'])
@csrf.exempt
@login_required
def save_new_version(secure_code):
    """儲存新版本"""
    from ..models import FwFormTemplate

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    template = FwFormTemplate.query.filter_by(
        secure_code=secure_code,
        org_secure_code=org.secure_code,
        is_deleted=False
    ).first()

    if not template:
        return jsonify({'success': False, 'error': 'Template not found'}), 404

    data = request.get_json() or {}

    # 更新版本號
    current_version = template.version or 'AA'
    if len(current_version) >= 2:
        first, second = current_version[0], current_version[1]
        if second == 'Z':
            new_version = chr(ord(first) + 1) + 'A'
        else:
            new_version = first + chr(ord(second) + 1)
    else:
        new_version = 'AA'

    template.version = new_version
    template.revision = (template.revision or 0) + 1

    if 'schema' in data:
        template.schema = data['schema']

    template.updated_at = datetime.utcnow()
    db.session.commit()

    return jsonify({
        'success': True,
        'data': template.to_dict(include_schema=True),
        'message': f'已儲存新版本 {new_version}'
    })
