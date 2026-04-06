"""
FormWorkflow Module - Forms API
表單設計器 API

提供與 A6 相容的 API 端點，支援表單設計器前端。
"""
import secrets
from datetime import datetime
from flask import Blueprint, render_template, jsonify, request
from flask_login import current_user

from app.security.decorators import module_access_required
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

import re

_CJK_RE = re.compile(r'[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]')


def _apply_placeholder_as_label(schema):
    """
    CJK 標籤處理：form.io 的 camelCase key 生成不支援中文，
    因此用戶以 placeholder 輸入中文欄位名稱，儲存時交換到 label。
    僅處理 placeholder 含 CJK 字元的元件，英文 placeholder 保持原樣。
    """
    def _process(components):
        for comp in (components or []):
            placeholder = comp.get('placeholder', '')
            if placeholder and _CJK_RE.search(placeholder):
                comp['label'] = placeholder
                comp['placeholder'] = ''
            if 'components' in comp:
                _process(comp['components'])
            if 'columns' in comp:
                for col in (comp.get('columns') or []):
                    _process(col.get('components'))
            if 'rows' in comp:
                for row in (comp.get('rows') or []):
                    for cell in (row or []):
                        _process((cell or {}).get('components'))
    if schema and 'components' in schema:
        _process(schema['components'])
    return schema


def _get_default_schema():
    """取得預設空白表單 schema"""
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
@module_access_required('form_workflow')
def list_page():
    """表單模板列表頁面"""
    return render_template(
        'modules/form_workflow/template_list.html',
        active_menu_code='form_workflow.templates'
    )


@forms_bp.route('/designer')
@forms_bp.route('/designer/<secure_code>')
@module_access_required('form_workflow')
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
        form=template.to_dict(include_schema=True) if template else None,
        user_type=current_user.user_type
    )


# =============================================================================
# 分類 API
# =============================================================================

@forms_bp.route('/data/categories')
@module_access_required('form_workflow')
def list_categories():
    """
    取得表單分類列表（供設計器 select/optgroup 使用）

    回傳扁平清單，每筆含 secure_code, name, parent_name, display
    """
    from ..models import FwCategory
    from app.platform.data import get_current_org
    from app import db

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'message': 'Organization not found'}), 400

    context = request.args.get('context', 'form_design')

    # 查詢：系統分類 + 當前企業分類
    query = FwCategory.query.filter_by(is_deleted=False).filter(
        db.or_(
            FwCategory.org_secure_code.is_(None),
            FwCategory.org_secure_code == org.secure_code
        )
    )

    # 情境過濾（對父分類生效）
    if context == 'form_design':
        query = query.filter(
            db.or_(
                FwCategory.parent_secure_code.isnot(None),
                FwCategory.show_in_form_design == True
            )
        )
    elif context == 'workflow_design':
        query = query.filter(
            db.or_(
                FwCategory.parent_secure_code.isnot(None),
                FwCategory.show_in_workflow_design == True
            )
        )

    all_cats = query.order_by(FwCategory.display_order, FwCategory.name).all()

    # 分出父/子分類
    parents = [c for c in all_cats if c.is_parent]
    children = [c for c in all_cats if c.is_child]
    parent_map = {c.secure_code: c.name for c in parents}
    # 有子分類的父分類 set
    parents_with_children = {c.parent_secure_code for c in children}

    # 靈活結構：
    # - 有子分類的父 → 列出子分類（display = "父 / 子"）
    # - 無子分類的父 → 列出父分類自己（display = 父名）
    result = []
    for parent in parents:
        if parent.secure_code in parents_with_children:
            # 有子分類 → 列子分類
            for child in children:
                if child.parent_secure_code == parent.secure_code:
                    result.append({
                        'secure_code': child.secure_code,
                        'name': child.name,
                        'parent_secure_code': child.parent_secure_code,
                        'parent_name': parent.name,
                        'display': f'{parent.name} / {child.name}',
                    })
        else:
            # 無子分類 → 直接列父分類
            result.append({
                'secure_code': parent.secure_code,
                'name': parent.name,
                'parent_secure_code': None,
                'parent_name': None,
                'display': parent.name,
            })

    # 向後相容：也回傳 categories 欄位（舊格式）
    compat = [{'id': r['display'], 'name': r['display'], 'secure_code': r['secure_code']} for r in result]

    return jsonify({
        'success': True,
        'data': result,
        'categories': compat
    })


# =============================================================================
# 數據 API
# =============================================================================

@forms_bp.route('/data/templates')
@module_access_required('form_workflow')
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
@module_access_required('form_workflow')
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
@module_access_required('form_workflow')
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

    schema = _apply_placeholder_as_label(data.get('schema')) or _get_default_schema()

    user_name = getattr(current_user, 'display_name', '') or getattr(current_user, 'native_name', '') or ''

    template = FwFormTemplate(
        secure_code=secrets.token_urlsafe(16),
        org_secure_code=org.secure_code,
        name=name,
        code=code,
        description=data.get('description', ''),
        schema=schema,
        is_active=data.get('is_active', True),
        owner_secure_code=current_user.secure_code,
        created_by_secure_code=current_user.secure_code,
        created_by_name=user_name,
        updated_by_secure_code=current_user.secure_code,
        updated_by_name=user_name,
    )

    db.session.add(template)
    db.session.commit()

    # 背景生成縮圖
    thumbnail_pending = False
    if template.schema and template.schema.get('components'):
        try:
            from ..services.thumbnail_service import generate_form_thumbnails_async, is_available
            if is_available():
                from flask import current_app
                generate_form_thumbnails_async(
                    current_app._get_current_object(),
                    template.id,
                    template.schema,
                    template.name
                )
                thumbnail_pending = True
        except Exception as e:
            pass

    result = template.to_dict(include_schema=True)
    result['secure_code'] = template.secure_code
    return jsonify({
        'success': True,
        'data': result,
        'thumbnail_pending': thumbnail_pending,
        'message': '表單模板已建立'
    })


@forms_bp.route('/data/templates/<secure_code>', methods=['PUT'])
@csrf.exempt
@module_access_required('form_workflow')
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

    schema_changed = False

    if 'name' in data:
        template.name = data['name'].strip()
    if 'description' in data:
        template.description = data['description']
    if 'category_secure_code' in data:
        template.category_secure_code = data['category_secure_code']
        # 同步更新舊 category 字串（過渡期向後相容）
        from ..models import FwCategory
        cat = FwCategory.query.filter_by(
            secure_code=data['category_secure_code'], is_deleted=False
        ).first()
        if cat and cat.parent_secure_code:
            parent = FwCategory.query.filter_by(
                secure_code=cat.parent_secure_code, is_deleted=False
            ).first()
            template.category = parent.name if parent else cat.name
        elif cat:
            template.category = cat.name
    elif 'category' in data:
        template.category = data['category']
    if 'schema' in data:
        template.schema = _apply_placeholder_as_label(data['schema'])
        schema_changed = True
    if 'is_active' in data:
        template.is_active = data['is_active']
    if 'builder_config' in data:
        template.builder_config = data['builder_config']

    # 縮圖（前端直接傳遞的優先）
    if 'thumbnail_2x1' in data:
        template.thumbnail_2x1 = data['thumbnail_2x1']

    # 有實質內容變更時遞增 revision
    if 'schema' in data or 'builder_config' in data:
        template.revision = (template.revision or 0) + 1

    # 更新最後編輯者
    user_name = getattr(current_user, 'display_name', '') or getattr(current_user, 'native_name', '') or ''
    template.updated_by_secure_code = current_user.secure_code
    template.updated_by_name = user_name

    template.updated_at = datetime.utcnow()
    db.session.commit()

    # schema 變更且前端沒傳縮圖 → 背景生成
    thumbnail_pending = False
    if schema_changed and 'thumbnail_2x1' not in data and template.schema:
        try:
            from ..services.thumbnail_service import generate_form_thumbnails_async, is_available
            if is_available():
                from flask import current_app
                generate_form_thumbnails_async(
                    current_app._get_current_object(),
                    template.id,
                    template.schema,
                    template.name
                )
                thumbnail_pending = True
        except Exception as e:
            pass

    return jsonify({
        'success': True,
        'data': template.to_dict(include_schema=True),
        'thumbnail_pending': thumbnail_pending,
        'message': '表單模板已更新'
    })


@forms_bp.route('/data/templates/<secure_code>', methods=['DELETE'])
@csrf.exempt
@module_access_required('form_workflow')
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
@module_access_required('form_workflow')
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
@module_access_required('form_workflow')
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
@module_access_required('form_workflow')
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
        'description': '企業成員請假申請表單',
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
@module_access_required('form_workflow')
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
@module_access_required('form_workflow')
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
@module_access_required('form_workflow')
def save_new_version(secure_code):
    """另存新版：複製目前表單為新記錄，版本號遞增"""
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

    # 遞增版本號
    current_version = template.version or 'AA'
    if len(current_version) >= 2:
        first, second = current_version[0], current_version[1]
        if second == 'Z':
            new_version = chr(ord(first) + 1) + 'A'
        else:
            new_version = first + chr(ord(second) + 1)
    else:
        new_version = 'AB'

    # 建立新記錄（複製原表單）
    new_template = FwFormTemplate(
        secure_code=secrets.token_urlsafe(16),
        org_secure_code=org.secure_code,
        code=template.code,
        name=data.get('name') or template.name,
        description=data.get('description') or template.description,
        category=template.category,
        category_secure_code=template.category_secure_code,
        schema=data.get('schema') or template.schema,
        version=new_version,
        revision=1,
        builder_config=template.builder_config,
        is_active=True,
        is_published=False,
        permission_type=template.permission_type,
        owner_secure_code=current_user.secure_code,
    )

    db.session.add(new_template)
    db.session.commit()

    return jsonify({
        'success': True,
        'data': new_template.to_dict(include_schema=True),
        'message': f'已另存新版本 {new_version}'
    })
