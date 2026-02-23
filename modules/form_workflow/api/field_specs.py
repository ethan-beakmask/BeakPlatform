"""
FormWorkflow Module - Field Specs API
欄位規格 API

提供欄位規格的 CRUD、雙向轉換、三向比對等功能。
URL prefix: /api/form-workflow/specs
"""
import copy
import logging
import secrets
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request

from app import csrf, db
from app.platform.auth import current_user, require_permission
from app.platform.data import get_current_org

logger = logging.getLogger(__name__)

field_specs_bp = Blueprint(
    'form_workflow_field_specs',
    __name__,
    url_prefix='/api/form-workflow/specs'
)


def _compute_diff(old_fields, new_fields):
    """
    計算兩版 fields 的差異

    Returns:
        dict: {added: [...], modified: [...], removed: [...]}
    """
    old_map = {f['field_key']: f for f in (old_fields or []) if f.get('field_key')}
    new_map = {f['field_key']: f for f in (new_fields or []) if f.get('field_key')}

    old_keys = set(old_map.keys())
    new_keys = set(new_map.keys())

    added = []
    for k in (new_keys - old_keys):
        added.append({
            'field_key': k,
            'label': new_map[k].get('label', ''),
        })

    removed = []
    for k in (old_keys - new_keys):
        removed.append({
            'field_key': k,
            'label': old_map[k].get('label', ''),
        })

    modified = []
    for k in (old_keys & new_keys):
        old_f = old_map[k]
        new_f = new_map[k]
        changes = []
        for prop in ('label', 'formio_type', 'pg_type', 'is_pii', 'description'):
            if old_f.get(prop) != new_f.get(prop):
                changes.append({
                    'property': prop,
                    'old': old_f.get(prop),
                    'new': new_f.get(prop),
                })
        # constraints 比較
        old_c = old_f.get('constraints') or {}
        new_c = new_f.get('constraints') or {}
        for cprop in ('required', 'maxLength', 'minLength', 'min', 'max', 'pattern'):
            if old_c.get(cprop) != new_c.get(cprop):
                changes.append({
                    'property': f'constraints.{cprop}',
                    'old': old_c.get(cprop),
                    'new': new_c.get(cprop),
                })
        if changes:
            modified.append({
                'field_key': k,
                'label': new_f.get('label', ''),
                'changes': changes,
            })

    return {
        'added': added,
        'modified': modified,
        'removed': removed,
    }


def _validate_fields(fields):
    """
    驗證 fields 結構

    Returns:
        (bool, str): (is_valid, error_message)
    """
    if not isinstance(fields, list):
        return False, 'fields 必須是陣列'

    seen_keys = set()
    for i, f in enumerate(fields):
        if not isinstance(f, dict):
            return False, f'fields[{i}] 必須是物件'

        field_key = f.get('field_key', '').strip()
        if not field_key:
            return False, f'fields[{i}] 缺少 field_key'

        if field_key in seen_keys:
            return False, f'field_key "{field_key}" 重複'
        seen_keys.add(field_key)

        if not f.get('formio_type'):
            return False, f'fields[{i}] ({field_key}) 缺少 formio_type'

    return True, ''


# =============================================================================
# CRUD
# =============================================================================

@field_specs_bp.route('/<form_template_sc>')
@require_permission('form_workflow.template.view')
def get_spec(form_template_sc):
    """取得表單的 active spec"""
    from ..models import FwFormFieldSpec

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    spec = FwFormFieldSpec.query.filter_by(
        org_secure_code=org.secure_code,
        form_template_secure_code=form_template_sc,
        status='active',
        is_deleted=False,
    ).first()

    if not spec:
        return jsonify({
            'success': True,
            'data': None,
            'message': '此表單尚無欄位規格'
        })

    return jsonify({
        'success': True,
        'data': spec.to_dict()
    })


@field_specs_bp.route('/<form_template_sc>', methods=['POST'])
@csrf.exempt
@require_permission('form_workflow.template.edit')
def save_spec(form_template_sc):
    """
    建立或更新 spec

    - 若無 active spec：建立新 spec (version=1)
    - 若有 active spec：更新 fields，version 遞增，寫 history + diff
    """
    from ..models import FwFormFieldSpec, FwFormFieldSpecHistory, FwFormTemplate

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    # 檢查表單模板是否存在
    template = FwFormTemplate.query.filter_by(
        secure_code=form_template_sc,
        org_secure_code=org.secure_code,
        is_deleted=False,
    ).first()
    if not template:
        return jsonify({'success': False, 'error': '找不到表單模板'}), 404

    data = request.get_json() or {}
    fields = data.get('fields', [])
    description = data.get('description', '')

    # 驗證
    valid, err = _validate_fields(fields)
    if not valid:
        return jsonify({'success': False, 'error': err}), 400

    # 正規化 fields
    normalized = []
    for i, f in enumerate(fields):
        normalized.append({
            'field_key': f['field_key'].strip(),
            'label': f.get('label', '').strip(),
            'formio_type': f['formio_type'].strip(),
            'pg_type': f.get('pg_type', '').strip() or None,
            'constraints': {
                'required': bool(f.get('constraints', {}).get('required', False)),
                'maxLength': f.get('constraints', {}).get('maxLength'),
                'minLength': f.get('constraints', {}).get('minLength'),
                'min': f.get('constraints', {}).get('min'),
                'max': f.get('constraints', {}).get('max'),
                'pattern': f.get('constraints', {}).get('pattern'),
                'customValidation': f.get('constraints', {}).get('customValidation'),
            },
            'is_pii': bool(f.get('is_pii', False)),
            'description': f.get('description', '').strip(),
            'default_value': f.get('default_value'),
            'options': f.get('options'),
            'grid_children': f.get('grid_children'),
            'sort_order': f.get('sort_order', i),
        })

    # 查找現有 active spec
    existing = FwFormFieldSpec.query.filter_by(
        org_secure_code=org.secure_code,
        form_template_secure_code=form_template_sc,
        status='active',
        is_deleted=False,
    ).first()

    user_sc = current_user.secure_code
    user_name = getattr(current_user, 'display_name', None) or current_user.username

    if existing:
        # 更新：版本遞增 + 寫 history
        old_fields = copy.deepcopy(existing.fields or [])
        new_version = existing.version + 1

        diff = _compute_diff(old_fields, normalized)

        # 寫 history（記錄舊版本）
        history = FwFormFieldSpecHistory(
            org_secure_code=org.secure_code,
            spec_secure_code=existing.secure_code,
            form_template_secure_code=form_template_sc,
            version=existing.version,
            fields_snapshot=old_fields,
            change_description=description or f'更新至 v{new_version}',
            change_diff=diff,
            changed_by=user_sc,
            changed_by_name=user_name,
        )
        db.session.add(history)

        # 更新 spec
        existing.fields = normalized
        existing.version = new_version
        existing.description = description
        existing.last_modified_by = user_sc
        existing.last_modified_by_name = user_name

        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(existing, 'fields')

        db.session.commit()

        return jsonify({
            'success': True,
            'data': existing.to_dict(),
            'diff': diff,
            'message': f'欄位規格已更新至 v{new_version}'
        })

    else:
        # 建立新 spec
        spec = FwFormFieldSpec(
            org_secure_code=org.secure_code,
            form_template_secure_code=form_template_sc,
            version=1,
            fields=normalized,
            status='active',
            description=description,
            last_modified_by=user_sc,
            last_modified_by_name=user_name,
        )
        db.session.add(spec)
        db.session.flush()

        # 寫首版 history
        history = FwFormFieldSpecHistory(
            org_secure_code=org.secure_code,
            spec_secure_code=spec.secure_code,
            form_template_secure_code=form_template_sc,
            version=1,
            fields_snapshot=normalized,
            change_description=description or '初始建立',
            change_diff={'added': [
                {'field_key': f['field_key'], 'label': f['label']}
                for f in normalized
            ], 'modified': [], 'removed': []},
            changed_by=user_sc,
            changed_by_name=user_name,
        )
        db.session.add(history)
        db.session.commit()

        return jsonify({
            'success': True,
            'data': spec.to_dict(),
            'message': '欄位規格已建立 (v1)'
        })


@field_specs_bp.route('/<form_template_sc>/history')
@require_permission('form_workflow.template.view')
def get_history(form_template_sc):
    """取得版本歷史列表"""
    from ..models import FwFormFieldSpecHistory

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    # 透過 spec 的 org_secure_code 驗證（history 本身沒有 org 欄位，透過 spec 關聯）
    histories = FwFormFieldSpecHistory.query.filter_by(
        form_template_secure_code=form_template_sc,
        is_deleted=False,
    ).order_by(FwFormFieldSpecHistory.version.desc()).all()

    return jsonify({
        'success': True,
        'data': {
            'histories': [h.to_dict() for h in histories]
        }
    })


# =============================================================================
# Phase 2 端點（雙向轉換）
# =============================================================================

@field_specs_bp.route('/<form_template_sc>/generate-formio', methods=['POST'])
@csrf.exempt
@require_permission('form_workflow.template.view')
def generate_formio(form_template_sc):
    """從 spec 生成 FormIO schema（預覽，不寫入）"""
    from ..models import FwFormFieldSpec

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    spec = FwFormFieldSpec.query.filter_by(
        org_secure_code=org.secure_code,
        form_template_secure_code=form_template_sc,
        status='active',
        is_deleted=False,
    ).first()

    if not spec:
        return jsonify({'success': False, 'error': '找不到 active 欄位規格'}), 404

    from ..services.field_spec.spec_generator import spec_to_formio_schema
    schema = spec_to_formio_schema(spec.fields)

    return jsonify({
        'success': True,
        'data': {
            'schema': schema,
            'field_count': len(spec.fields or []),
            'version': spec.version,
        }
    })


@field_specs_bp.route('/<form_template_sc>/sync-from-formio', methods=['POST'])
@csrf.exempt
@require_permission('form_workflow.template.edit')
def sync_from_formio(form_template_sc):
    """從現有 FormIO schema 反向建立/更新 spec"""
    from ..models import FwFormTemplate

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    template = FwFormTemplate.query.filter_by(
        secure_code=form_template_sc,
        org_secure_code=org.secure_code,
        is_deleted=False,
    ).first()

    if not template:
        return jsonify({'success': False, 'error': '找不到表單模板'}), 404

    form_schema = template.schema
    if not form_schema or not form_schema.get('components'):
        return jsonify({'success': False, 'error': '表單無 schema 或無欄位'}), 400

    from ..services.field_spec.spec_generator import formio_schema_to_spec_fields
    fields = formio_schema_to_spec_fields(form_schema)

    if not fields:
        return jsonify({'success': False, 'error': '未偵測到可轉換的資料欄位'}), 400

    # 儲存邏輯
    from ..models import FwFormFieldSpec, FwFormFieldSpecHistory
    import copy as _copy

    user_sc = current_user.secure_code
    user_name = getattr(current_user, 'display_name', None) or current_user.username

    existing = FwFormFieldSpec.query.filter_by(
        org_secure_code=org.secure_code,
        form_template_secure_code=form_template_sc,
        status='active',
        is_deleted=False,
    ).first()

    if existing:
        old_fields = _copy.deepcopy(existing.fields or [])
        new_version = existing.version + 1
        diff = _compute_diff(old_fields, fields)

        history = FwFormFieldSpecHistory(
            org_secure_code=org.secure_code,
            spec_secure_code=existing.secure_code,
            form_template_secure_code=form_template_sc,
            version=existing.version,
            fields_snapshot=old_fields,
            change_description='從 FormIO schema 同步',
            change_diff=diff,
            changed_by=user_sc,
            changed_by_name=user_name,
        )
        db.session.add(history)

        existing.fields = fields
        existing.version = new_version
        existing.description = '從 FormIO schema 同步'
        existing.last_modified_by = user_sc
        existing.last_modified_by_name = user_name

        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(existing, 'fields')
        db.session.commit()

        return jsonify({
            'success': True,
            'data': existing.to_dict(),
            'diff': diff,
            'message': f'已從 FormIO schema 同步至 v{new_version}（{len(fields)} 個欄位）'
        })
    else:
        spec = FwFormFieldSpec(
            org_secure_code=org.secure_code,
            form_template_secure_code=form_template_sc,
            version=1,
            fields=fields,
            status='active',
            description='從 FormIO schema 同步',
            last_modified_by=user_sc,
            last_modified_by_name=user_name,
        )
        db.session.add(spec)
        db.session.flush()

        history = FwFormFieldSpecHistory(
            org_secure_code=org.secure_code,
            spec_secure_code=spec.secure_code,
            form_template_secure_code=form_template_sc,
            version=1,
            fields_snapshot=fields,
            change_description='從 FormIO schema 同步（初始建立）',
            change_diff={'added': [
                {'field_key': f['field_key'], 'label': f.get('label', '')}
                for f in fields
            ], 'modified': [], 'removed': []},
            changed_by=user_sc,
            changed_by_name=user_name,
        )
        db.session.add(history)
        db.session.commit()

        return jsonify({
            'success': True,
            'data': spec.to_dict(),
            'message': f'已從 FormIO schema 建立規格（{len(fields)} 個欄位）'
        })


@field_specs_bp.route('/<form_template_sc>/apply-to-form', methods=['POST'])
@csrf.exempt
@require_permission('form_workflow.template.edit')
def apply_to_form(form_template_sc):
    """
    將 spec 套用到 form_template.schema

    mode 參數:
    - replace (預設): 保留 layout 容器，data fields 用 spec 重建
    - preview: 只回傳預覽結果，不寫入
    """
    from ..models import FwFormFieldSpec, FwFormTemplate

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    spec = FwFormFieldSpec.query.filter_by(
        org_secure_code=org.secure_code,
        form_template_secure_code=form_template_sc,
        status='active',
        is_deleted=False,
    ).first()

    if not spec:
        return jsonify({'success': False, 'error': '找不到 active 欄位規格'}), 404

    template = FwFormTemplate.query.filter_by(
        secure_code=form_template_sc,
        org_secure_code=org.secure_code,
        is_deleted=False,
    ).first()

    if not template:
        return jsonify({'success': False, 'error': '找不到表單模板'}), 404

    data = request.get_json() or {}
    mode = data.get('mode', 'replace')

    from ..services.field_spec.spec_generator import (
        spec_to_formio_schema,
        apply_spec_to_existing_schema,
    )

    if mode == 'preview':
        new_schema = apply_spec_to_existing_schema(
            spec.fields, template.schema
        )
        return jsonify({
            'success': True,
            'data': {'schema': new_schema},
            'message': '預覽模式，未寫入'
        })

    # replace 模式
    new_schema = apply_spec_to_existing_schema(
        spec.fields, template.schema
    )
    template.schema = new_schema

    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(template, 'schema')
    db.session.commit()

    return jsonify({
        'success': True,
        'data': template.to_dict(include_schema=True),
        'message': f'已將 spec v{spec.version} 套用到表單（{len(spec.fields or [])} 個欄位）'
    })


# =============================================================================
# Phase 3 端點（三向比對）
# =============================================================================

@field_specs_bp.route('/<form_template_sc>/compare')
@require_permission('form_workflow.template.view')
def compare(form_template_sc):
    """三向比對：Spec vs FormIO vs SQL"""
    from ..models import FwFormFieldSpec, FwFormTemplate, FwSqlFormRegistry

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    spec = FwFormFieldSpec.query.filter_by(
        org_secure_code=org.secure_code,
        form_template_secure_code=form_template_sc,
        status='active',
        is_deleted=False,
    ).first()

    if not spec:
        return jsonify({'success': False, 'error': '找不到 active 欄位規格'}), 404

    template = FwFormTemplate.query.filter_by(
        secure_code=form_template_sc,
        org_secure_code=org.secure_code,
        is_deleted=False,
    ).first()

    if not template:
        return jsonify({'success': False, 'error': '找不到表單模板'}), 404

    # 查找最新 active registry
    registry = FwSqlFormRegistry.query.filter_by(
        form_template_secure_code=form_template_sc,
        org_secure_code=org.secure_code,
        status='active',
    ).order_by(FwSqlFormRegistry.id.desc()).first()

    column_mapping = registry.column_mapping if registry else None

    from ..services.field_spec.drift_detector import three_way_compare
    result = three_way_compare(
        spec.fields,
        template.schema,
        column_mapping,
    )

    return jsonify({
        'success': True,
        'data': result
    })
