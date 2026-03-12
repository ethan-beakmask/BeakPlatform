"""
Spec Formulate Module - Field Specs API
欄位規格 API

提供欄位規格的 CRUD、雙向轉換、三向比對等功能。
URL prefix: /api/spec-formulate/specs
"""
import copy
import json
import logging
import re
import secrets
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request

from app import csrf, db
from app.platform.auth import current_user, require_permission
from app.platform.data import get_current_org

logger = logging.getLogger(__name__)

field_specs_bp = Blueprint(
    'spec_formulate_field_specs',
    __name__,
    url_prefix='/api/spec-formulate/specs'
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


_FIELD_KEY_RE = re.compile(r'^[a-zA-Z0-9_]+$')


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

        if not _FIELD_KEY_RE.match(field_key):
            return False, f'field_key "{field_key}" 只能使用英文字母、數字與底線'

        if field_key in seen_keys:
            return False, f'field_key "{field_key}" 重複'
        seen_keys.add(field_key)

        if not f.get('formio_type'):
            return False, f'fields[{i}] ({field_key}) 缺少 formio_type'

        # 子欄位也要驗證
        grid_children = f.get('grid_children') or []
        for ci, child in enumerate(grid_children):
            child_key = (child.get('field_key') or '').strip()
            if child_key and not _FIELD_KEY_RE.match(child_key):
                return False, f'field_key "{field_key}" 的子欄位 "{child_key}" 只能使用英文字母、數字與底線'

    return True, ''


# =============================================================================
# CRUD
# =============================================================================

@field_specs_bp.route('/<form_template_sc>')
@require_permission('form_workflow.template.view')
def get_spec(form_template_sc):
    """取得表單的 active spec"""
    from modules.spec_formulate.models import FwFormFieldSpec

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
    from modules.form_workflow.models import FwFormTemplate
    from modules.spec_formulate.models import FwFormFieldSpec, FwFormFieldSpecHistory

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
        # 防重複版本：fields 完全一致時不建新版
        old_fields = copy.deepcopy(existing.fields or [])
        if json.dumps(normalized, sort_keys=True, ensure_ascii=False) == \
           json.dumps(old_fields, sort_keys=True, ensure_ascii=False):
            return jsonify({
                'success': True,
                'data': existing.to_dict(),
                'message': '內容無變更，未建新版'
            })

        # 更新：版本遞增 + 寫 history
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
    from modules.spec_formulate.models import FwFormFieldSpecHistory

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
    from modules.spec_formulate.models import FwFormFieldSpec

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

    from modules.spec_formulate.services.field_spec.spec_generator import spec_to_formio_schema
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
    from modules.form_workflow.models import FwFormTemplate

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

    from modules.spec_formulate.services.field_spec.spec_generator import formio_schema_to_spec_fields
    fields = formio_schema_to_spec_fields(form_schema)

    if not fields:
        return jsonify({'success': False, 'error': '未偵測到可轉換的資料欄位'}), 400

    # 儲存邏輯
    from modules.spec_formulate.models import FwFormFieldSpec, FwFormFieldSpecHistory
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
    from modules.form_workflow.models import FwFormTemplate
    from modules.spec_formulate.models import FwFormFieldSpec

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

    from modules.spec_formulate.services.field_spec.spec_generator import (
        spec_to_formio_schema,
        apply_spec_to_existing_schema,
    )

    if mode == 'preview':
        new_schema = apply_spec_to_existing_schema(
            spec.fields, template.schema, form_title=spec.name
        )
        return jsonify({
            'success': True,
            'data': {'schema': new_schema},
            'message': '預覽模式，未寫入'
        })

    # replace 模式
    new_schema = apply_spec_to_existing_schema(
        spec.fields, template.schema, form_title=spec.name
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

# =============================================================================
# 資料表規格管理頁面 API
# =============================================================================

@field_specs_bp.route('/registry-overview')
@require_permission('form_workflow.template.manage')
def registry_overview():
    """
    資料表規格總覽

    以 form_template / standalone spec 為分組主軸，列出所有有 spec 的表單，
    以及每個表單下的 SQL registry。包含有 spec 但尚無 registry 的表單。
    """
    from modules.form_workflow.models import (
        FwSqlFormRegistry, FwFormTemplate, FwPublishedFormWorkflow,
    )
    from modules.spec_formulate.models import FwFormFieldSpec

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    org_sc = org.secure_code

    # 1. 查所有 active registry
    registries = FwSqlFormRegistry.query.filter_by(
        org_secure_code=org_sc,
        status='active',
    ).all()

    # 2. 查所有綁定表單的 active specs（獨立規格由 standalone API 處理）
    bound_specs = FwFormFieldSpec.query.filter(
        FwFormFieldSpec.org_secure_code == org_sc,
        FwFormFieldSpec.status == 'active',
        FwFormFieldSpec.is_deleted == False,
        FwFormFieldSpec.form_template_secure_code.isnot(None),
    ).all()

    if not registries and not bound_specs:
        return jsonify({'success': True, 'data': []})

    # 3. 收集需要查的 secure_code 集合
    ft_scs = set()
    pub_scs = set()
    for r in registries:
        if r.form_template_secure_code:
            ft_scs.add(r.form_template_secure_code)
        if r.published_secure_code:
            pub_scs.add(r.published_secure_code)
    for s in bound_specs:
        ft_scs.add(s.form_template_secure_code)

    # 4. 批次查 form_templates（過濾已刪除的）
    tpl_map = {}
    if ft_scs:
        templates = FwFormTemplate.query.filter(
            FwFormTemplate.secure_code.in_(ft_scs),
            FwFormTemplate.org_secure_code == org_sc,
            FwFormTemplate.is_deleted == False,
        ).all()
        tpl_map = {t.secure_code: t for t in templates}

    # 5. 建立 spec 查找 map
    spec_by_ft = {}
    for s in bound_specs:
        # 過濾掉指向已刪除 template 的孤兒 spec
        if s.form_template_secure_code in tpl_map:
            spec_by_ft[s.form_template_secure_code] = s

    # 6. 批次查 published versions
    pub_map = {}
    if pub_scs:
        publisheds = FwPublishedFormWorkflow.query.filter(
            FwPublishedFormWorkflow.secure_code.in_(pub_scs),
            FwPublishedFormWorkflow.org_secure_code == org_sc,
            FwPublishedFormWorkflow.is_deleted == False,
        ).all()
        pub_map = {p.secure_code: p for p in publisheds}

    # 7. 以 form_template_secure_code 分組
    grouped = {}

    def _ensure_ft_group(ft_sc):
        """確保 form_template 分組存在"""
        if ft_sc in grouped or ft_sc not in tpl_map:
            return
        tpl = tpl_map[ft_sc]
        spec = spec_by_ft.get(ft_sc)
        grouped[ft_sc] = {
            'form_template_secure_code': ft_sc,
            'form_template_name': tpl.name,
            'form_template_code': tpl.code or '',
            'spec_secure_code': spec.secure_code if spec else None,
            'spec_status': spec.status if spec else None,
            'spec_version': spec.version if spec else None,
            'spec_field_count': len(spec.fields or []) if spec else None,
            'registries': [],
        }

    # 8. 將 registries 分組（只處理綁定表單的 registry）
    for r in registries:
        ft_sc = r.form_template_secure_code
        if not ft_sc or ft_sc not in tpl_map:
            continue
        _ensure_ft_group(ft_sc)

        pub = pub_map.get(r.published_secure_code) if r.published_secure_code else None
        col_mapping = r.column_mapping or {}
        column_count = len([k for k in col_mapping if not k.startswith('_')])

        grouped[ft_sc]['registries'].append({
            'registry_secure_code': r.secure_code,
            'published_secure_code': r.published_secure_code,
            'publish_version': r.publish_version or (pub.publish_version if pub else None),
            'published_name': pub.name if pub else '',
            'published_status': pub.status if pub else '',
            'table_name': r.table_name,
            'column_count': column_count,
            'row_count': r.row_count or 0,
            'last_synced_at': r.last_synced_at.isoformat() if r.last_synced_at else None,
        })

    # 9. 納入有 spec 但無 registry 的表單（template 必須存在）
    for ft_sc in spec_by_ft:
        _ensure_ft_group(ft_sc)

    # 子列按 publish_version 排序
    for g in grouped.values():
        g['registries'].sort(key=lambda r: r['publish_version'] or 0)

    # 主列按表單名稱排序
    result = sorted(grouped.values(), key=lambda x: x['form_template_name'])

    return jsonify({'success': True, 'data': result})


@field_specs_bp.route('/available-templates')
@require_permission('form_workflow.template.manage')
def available_templates():
    """
    列出尚無 active spec 的表單範本

    供「新增資料表規格」Modal 使用。
    """
    from modules.form_workflow.models import FwFormTemplate
    from modules.spec_formulate.models import FwFormFieldSpec

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    org_sc = org.secure_code

    # 查所有已有 active spec 的 form_template_secure_code
    existing_scs = db.session.query(
        FwFormFieldSpec.form_template_secure_code
    ).filter(
        FwFormFieldSpec.org_secure_code == org_sc,
        FwFormFieldSpec.status == 'active',
        FwFormFieldSpec.is_deleted == False,
    ).all()
    existing_set = {row[0] for row in existing_scs}

    # 查所有表單範本
    templates = FwFormTemplate.query.filter_by(
        org_secure_code=org_sc,
        is_deleted=False,
        is_active=True,
    ).order_by(FwFormTemplate.name).all()

    result = []
    for t in templates:
        if t.secure_code not in existing_set:
            result.append({
                'secure_code': t.secure_code,
                'name': t.name,
                'code': t.code,
            })

    return jsonify({'success': True, 'data': result})


# =============================================================================
# Phase 3 端點（三向比對）
# =============================================================================

@field_specs_bp.route('/<form_template_sc>/compare')
@require_permission('form_workflow.template.view')
def compare(form_template_sc):
    """三向比對：Spec vs FormIO vs SQL"""
    from modules.form_workflow.models import FwFormTemplate, FwSqlFormRegistry
    from modules.spec_formulate.models import FwFormFieldSpec

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

    from modules.spec_formulate.services.field_spec.drift_detector import three_way_compare
    result = three_way_compare(
        spec.fields,
        template.schema,
        column_mapping,
    )

    # 附加版本資訊
    result['versions'] = {
        'spec_version': spec.version,
        'form_version': f'{template.version or "AA"}{template.revision or ""}',
        'sql_table_name': registry.table_name if registry else None,
    }

    return jsonify({
        'success': True,
        'data': result
    })


# =============================================================================
# 共用 helper: 正規化 fields + 儲存 spec
# =============================================================================

def _normalize_fields(fields):
    """正規化 fields 陣列"""
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
    return normalized


def _save_spec_core(existing, normalized, org_sc, user_sc, user_name,
                    description='', form_template_sc=None, spec_name=None):
    """
    共用的 spec 儲存邏輯

    Args:
        existing: 現有 FwFormFieldSpec (可為 None)
        normalized: 正規化後的 fields
        org_sc: org_secure_code
        user_sc: 當前用戶 secure_code
        user_name: 當前用戶名稱
        description: 變更描述
        form_template_sc: 表單模板 sc (可為 None)
        spec_name: 獨立 spec 名稱 (可為 None)

    Returns:
        tuple: (spec_dict, diff_or_none, message, is_new)
    """
    from modules.spec_formulate.models import FwFormFieldSpec, FwFormFieldSpecHistory

    if existing:
        # 防重複版本
        old_fields = copy.deepcopy(existing.fields or [])
        if json.dumps(normalized, sort_keys=True, ensure_ascii=False) == \
           json.dumps(old_fields, sort_keys=True, ensure_ascii=False):
            return existing.to_dict(), None, '內容無變更，未建新版', False

        new_version = existing.version + 1
        diff = _compute_diff(old_fields, normalized)

        history = FwFormFieldSpecHistory(
            org_secure_code=org_sc,
            spec_secure_code=existing.secure_code,
            form_template_secure_code=form_template_sc or existing.form_template_secure_code,
            version=existing.version,
            fields_snapshot=old_fields,
            change_description=description or f'更新至 v{new_version}',
            change_diff=diff,
            changed_by=user_sc,
            changed_by_name=user_name,
        )
        db.session.add(history)

        existing.fields = normalized
        existing.version = new_version
        existing.description = description
        existing.last_modified_by = user_sc
        existing.last_modified_by_name = user_name
        if spec_name is not None:
            existing.name = spec_name

        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(existing, 'fields')
        db.session.commit()

        return existing.to_dict(), diff, f'欄位規格已更新至 v{new_version}', False
    else:
        spec = FwFormFieldSpec(
            org_secure_code=org_sc,
            form_template_secure_code=form_template_sc,
            name=spec_name,
            version=1,
            fields=normalized,
            status='active',
            description=description,
            last_modified_by=user_sc,
            last_modified_by_name=user_name,
        )
        db.session.add(spec)
        db.session.flush()

        history = FwFormFieldSpecHistory(
            org_secure_code=org_sc,
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

        return spec.to_dict(), None, '欄位規格已建立 (v1)', True


# lazy import helper (避免循環匯入)
FwFormFieldSpec = None
FwFormFieldSpecHistory = None


def _ensure_models():
    global FwFormFieldSpec, FwFormFieldSpecHistory
    if FwFormFieldSpec is None:
        from modules.spec_formulate.models import FwFormFieldSpec as _S, FwFormFieldSpecHistory as _H
        FwFormFieldSpec = _S
        FwFormFieldSpecHistory = _H


# =============================================================================
# 獨立 Spec CRUD
# =============================================================================

@field_specs_bp.route('/standalone')
@require_permission('form_workflow.template.manage')
def list_standalone():
    """列出所有獨立 spec（form_template_secure_code IS NULL）"""
    _ensure_models()

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    specs = FwFormFieldSpec.query.filter_by(
        org_secure_code=org.secure_code,
        status='active',
        is_deleted=False,
    ).filter(
        FwFormFieldSpec.form_template_secure_code.is_(None)
    ).order_by(FwFormFieldSpec.updated_at.desc()).all()

    return jsonify({
        'success': True,
        'data': [s.to_dict() for s in specs]
    })


@field_specs_bp.route('/standalone', methods=['POST'])
@csrf.exempt
@require_permission('form_workflow.template.manage')
def create_standalone():
    """建立獨立 spec（name + fields）"""
    _ensure_models()

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    data = request.get_json() or {}
    name = (data.get('name') or '').strip()
    fields = data.get('fields', [])
    description = data.get('description', '')

    if not name:
        return jsonify({'success': False, 'error': '獨立規格必須提供名稱'}), 400

    valid, err = _validate_fields(fields)
    if not valid:
        return jsonify({'success': False, 'error': err}), 400

    normalized = _normalize_fields(fields)
    user_sc = current_user.secure_code
    user_name = getattr(current_user, 'display_name', None) or current_user.username

    spec_dict, diff, message, is_new = _save_spec_core(
        None, normalized, org.secure_code, user_sc, user_name,
        description=description, form_template_sc=None, spec_name=name,
    )

    return jsonify({
        'success': True,
        'data': spec_dict,
        'message': message,
    }), 201


@field_specs_bp.route('/standalone/<spec_sc>')
@require_permission('form_workflow.template.view')
def get_standalone(spec_sc):
    """取得獨立 spec"""
    _ensure_models()

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    spec = FwFormFieldSpec.query.filter_by(
        org_secure_code=org.secure_code,
        secure_code=spec_sc,
        status='active',
        is_deleted=False,
    ).first()

    if not spec:
        return jsonify({'success': False, 'error': '找不到規格'}), 404

    return jsonify({
        'success': True,
        'data': spec.to_dict()
    })


@field_specs_bp.route('/standalone/<spec_sc>', methods=['POST'])
@csrf.exempt
@require_permission('form_workflow.template.edit')
def update_standalone(spec_sc):
    """更新獨立 spec（版本遞增）"""
    _ensure_models()

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    spec = FwFormFieldSpec.query.filter_by(
        org_secure_code=org.secure_code,
        secure_code=spec_sc,
        status='active',
        is_deleted=False,
    ).first()

    if not spec:
        return jsonify({'success': False, 'error': '找不到規格'}), 404

    data = request.get_json() or {}
    fields = data.get('fields', [])
    description = data.get('description', '')
    name = data.get('name')

    valid, err = _validate_fields(fields)
    if not valid:
        return jsonify({'success': False, 'error': err}), 400

    normalized = _normalize_fields(fields)
    user_sc = current_user.secure_code
    user_name = getattr(current_user, 'display_name', None) or current_user.username

    spec_dict, diff, message, is_new = _save_spec_core(
        spec, normalized, org.secure_code, user_sc, user_name,
        description=description,
        form_template_sc=spec.form_template_secure_code,
        spec_name=name,
    )

    result = {'success': True, 'data': spec_dict, 'message': message}
    if diff:
        result['diff'] = diff
    return jsonify(result)


@field_specs_bp.route('/standalone/<spec_sc>/history')
@require_permission('form_workflow.template.view')
def get_standalone_history(spec_sc):
    """取得獨立 spec 版本歷史"""
    _ensure_models()

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    histories = FwFormFieldSpecHistory.query.filter_by(
        spec_secure_code=spec_sc,
        is_deleted=False,
    ).order_by(FwFormFieldSpecHistory.version.desc()).all()

    return jsonify({
        'success': True,
        'data': {'histories': [h.to_dict() for h in histories]}
    })


@field_specs_bp.route('/standalone/<spec_sc>', methods=['DELETE'])
@csrf.exempt
@require_permission('form_workflow.template.manage')
def delete_standalone(spec_sc):
    """刪除獨立 spec（軟刪除）"""
    _ensure_models()

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    spec = FwFormFieldSpec.query.filter_by(
        secure_code=spec_sc,
        org_secure_code=org.secure_code,
        is_deleted=False,
    ).first()
    if not spec:
        return jsonify({'success': False, 'error': '找不到規格'}), 404

    # 只允許刪除獨立 spec（無 form_template_secure_code）
    if spec.form_template_secure_code:
        return jsonify({'success': False, 'error': '此規格已綁定表單，不可直接刪除'}), 400

    spec.is_deleted = True
    spec.status = 'deleted'
    db.session.commit()

    return jsonify({'success': True, 'message': '規格已刪除'})


@field_specs_bp.route('/standalone/<spec_sc>/link-form', methods=['POST'])
@csrf.exempt
@require_permission('form_workflow.template.manage')
def link_form(spec_sc):
    """將獨立 spec 關聯到既有 form_template"""
    _ensure_models()
    from modules.form_workflow.models import FwFormTemplate

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    spec = FwFormFieldSpec.query.filter_by(
        org_secure_code=org.secure_code,
        secure_code=spec_sc,
        status='active',
        is_deleted=False,
    ).first()

    if not spec:
        return jsonify({'success': False, 'error': '找不到規格'}), 404

    data = request.get_json() or {}
    ft_sc = data.get('form_template_secure_code')
    if not ft_sc:
        return jsonify({'success': False, 'error': '缺少 form_template_secure_code'}), 400

    template = FwFormTemplate.query.filter_by(
        secure_code=ft_sc,
        org_secure_code=org.secure_code,
        is_deleted=False,
    ).first()
    if not template:
        return jsonify({'success': False, 'error': '找不到表單模板'}), 404

    # 檢查該表單是否已有 spec
    existing = FwFormFieldSpec.query.filter_by(
        org_secure_code=org.secure_code,
        form_template_secure_code=ft_sc,
        status='active',
        is_deleted=False,
    ).first()
    if existing and existing.secure_code != spec_sc:
        return jsonify({'success': False, 'error': '該表單已有 active 規格'}), 409

    spec.form_template_secure_code = ft_sc
    db.session.commit()

    return jsonify({
        'success': True,
        'data': spec.to_dict(),
        'message': f'已關聯到表單「{template.name}」'
    })


@field_specs_bp.route('/standalone/<spec_sc>/create-form', methods=['POST'])
@csrf.exempt
@require_permission('form_workflow.template.manage')
def create_form_from_spec(spec_sc):
    """從獨立 spec 建立新 FwFormTemplate"""
    _ensure_models()
    from modules.form_workflow.models import FwFormTemplate

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    spec = FwFormFieldSpec.query.filter_by(
        org_secure_code=org.secure_code,
        secure_code=spec_sc,
        status='active',
        is_deleted=False,
    ).first()

    if not spec:
        return jsonify({'success': False, 'error': '找不到規格'}), 404

    data = request.get_json() or {}
    form_name = (data.get('name') or spec.name or '').strip()
    form_code = (data.get('code') or '').strip().upper()
    category_sc = (data.get('category_secure_code') or '').strip() or None

    if not form_name:
        return jsonify({'success': False, 'error': '缺少表單名稱'}), 400

    # 自動產生 code
    if not form_code:
        form_code = f'FT{secrets.token_hex(4).upper()}'

    # 檢查 code 是否重複
    existing_tpl = FwFormTemplate.query.filter_by(
        code=form_code,
        org_secure_code=org.secure_code,
        is_deleted=False,
    ).first()
    if existing_tpl:
        return jsonify({'success': False, 'error': f'Code {form_code} 已存在'}), 400

    # 從 spec 生成 FormIO schema（含 formTitle）
    from modules.spec_formulate.services.field_spec.spec_generator import spec_to_formio_schema
    schema = spec_to_formio_schema(spec.fields, form_title=form_name)

    template = FwFormTemplate(
        org_secure_code=org.secure_code,
        name=form_name,
        code=form_code,
        schema=schema,
        category_secure_code=category_sc,
        is_active=True,
    )
    db.session.add(template)
    db.session.flush()

    # 關聯 spec 到新表單
    spec.form_template_secure_code = template.secure_code
    db.session.commit()

    return jsonify({
        'success': True,
        'data': {
            'spec': spec.to_dict(),
            'form_template': template.to_dict(),
        },
        'message': f'已建立表單「{form_name}」並關聯規格'
    }), 201


# =============================================================================
# Phase 2: SQL 結構讀取 + SQL->Spec 反向同步
# =============================================================================

@field_specs_bp.route('/<form_template_sc>/sql-schema')
@require_permission('form_workflow.template.view')
def get_sql_schema(form_template_sc):
    """讀取企業 DB 實際表結構（唯讀）"""
    from modules.form_workflow.models import FwSqlFormRegistry

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    registry = FwSqlFormRegistry.query.filter_by(
        form_template_secure_code=form_template_sc,
        org_secure_code=org.secure_code,
        status='active',
    ).order_by(FwSqlFormRegistry.id.desc()).first()

    if not registry:
        return jsonify({'success': False, 'error': '找不到 active SQL registry'}), 404

    try:
        from modules.form_workflow.services.sql_sync.schema_reader import read_table_columns
        columns = read_table_columns(org.secure_code, registry.table_name)
    except Exception as e:
        logger.error(f'讀取企業 DB 表結構失敗: {e}')
        return jsonify({'success': False, 'error': f'讀取表結構失敗: {e}'}), 500

    return jsonify({
        'success': True,
        'data': {
            'table_name': registry.table_name,
            'columns': columns,
            'column_mapping': registry.column_mapping,
        }
    })


@field_specs_bp.route('/<form_template_sc>/sync-from-sql', methods=['POST'])
@csrf.exempt
@require_permission('form_workflow.template.edit')
def sync_from_sql(form_template_sc):
    """SQL -> Spec（從企業 DB 反向建立/更新 spec）"""
    _ensure_models()
    from modules.form_workflow.models import FwSqlFormRegistry

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    registry = FwSqlFormRegistry.query.filter_by(
        form_template_secure_code=form_template_sc,
        org_secure_code=org.secure_code,
        status='active',
    ).order_by(FwSqlFormRegistry.id.desc()).first()

    if not registry:
        return jsonify({'success': False, 'error': '找不到 active SQL registry'}), 404

    try:
        from modules.form_workflow.services.sql_sync.schema_reader import read_table_columns, pg_columns_to_spec_fields
        columns = read_table_columns(org.secure_code, registry.table_name)
        fields = pg_columns_to_spec_fields(columns, registry.column_mapping)
    except Exception as e:
        logger.error(f'從 SQL 反向同步失敗: {e}')
        return jsonify({'success': False, 'error': f'讀取表結構失敗: {e}'}), 500

    if not fields:
        return jsonify({'success': False, 'error': '未偵測到可轉換的資料欄位'}), 400

    existing = FwFormFieldSpec.query.filter_by(
        org_secure_code=org.secure_code,
        form_template_secure_code=form_template_sc,
        status='active',
        is_deleted=False,
    ).first()

    user_sc = current_user.secure_code
    user_name = getattr(current_user, 'display_name', None) or current_user.username

    spec_dict, diff, message, is_new = _save_spec_core(
        existing, fields, org.secure_code, user_sc, user_name,
        description='從 SQL 表結構同步',
        form_template_sc=form_template_sc,
    )

    result = {'success': True, 'data': spec_dict, 'message': message}
    if diff:
        result['diff'] = diff
    return jsonify(result)


# =============================================================================
# Phase 3: Spec->SQL ALTER TABLE
# =============================================================================

@field_specs_bp.route('/<form_template_sc>/alter-plan', methods=['POST'])
@csrf.exempt
@require_permission('form_workflow.template.manage')
def alter_plan(form_template_sc):
    """計算 ALTER 計劃（不執行）"""
    _ensure_models()
    from modules.form_workflow.models import FwSqlFormRegistry

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

    registry = FwSqlFormRegistry.query.filter_by(
        form_template_secure_code=form_template_sc,
        org_secure_code=org.secure_code,
        status='active',
    ).order_by(FwSqlFormRegistry.id.desc()).first()
    if not registry:
        return jsonify({'success': False, 'error': '找不到 active SQL registry'}), 404

    try:
        from modules.form_workflow.services.sql_sync.alter_manager import compute_alter_plan
        plan = compute_alter_plan(
            registry.column_mapping,
            spec.fields,
            org.secure_code,
            registry.table_name,
        )
    except Exception as e:
        logger.error(f'計算 ALTER 計劃失敗: {e}')
        return jsonify({'success': False, 'error': f'計算 ALTER 計劃失敗: {e}'}), 500

    return jsonify({
        'success': True,
        'data': plan,
    })


@field_specs_bp.route('/<form_template_sc>/alter-execute', methods=['POST'])
@csrf.exempt
@require_permission('form_workflow.template.manage')
def alter_execute(form_template_sc):
    """執行 ALTER（需帶 confirm_token）"""
    _ensure_models()
    from modules.form_workflow.models import FwSqlFormRegistry

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    data = request.get_json() or {}
    confirm_token = data.get('confirm_token')
    confirm_table_name = data.get('confirm_table_name')

    if not confirm_token:
        return jsonify({'success': False, 'error': '缺少 confirm_token'}), 400

    registry = FwSqlFormRegistry.query.filter_by(
        form_template_secure_code=form_template_sc,
        org_secure_code=org.secure_code,
        status='active',
    ).order_by(FwSqlFormRegistry.id.desc()).first()
    if not registry:
        return jsonify({'success': False, 'error': '找不到 active SQL registry'}), 404

    spec = FwFormFieldSpec.query.filter_by(
        org_secure_code=org.secure_code,
        form_template_secure_code=form_template_sc,
        status='active',
        is_deleted=False,
    ).first()
    if not spec:
        return jsonify({'success': False, 'error': '找不到 active 欄位規格'}), 404

    try:
        from modules.form_workflow.services.sql_sync.alter_manager import compute_alter_plan, execute_alter_plan
        plan = compute_alter_plan(
            registry.column_mapping,
            spec.fields,
            org.secure_code,
            registry.table_name,
        )
        result = execute_alter_plan(
            org.secure_code,
            registry.table_name,
            plan,
            confirm_token,
            confirm_table_name=confirm_table_name,
        )
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        logger.error(f'執行 ALTER 失敗: {e}')
        return jsonify({'success': False, 'error': f'執行 ALTER 失敗: {e}'}), 500

    # 更新 column_mapping
    if result.get('success'):
        new_mapping = result.get('new_column_mapping')
        if new_mapping:
            registry.column_mapping = new_mapping
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(registry, 'column_mapping')
            db.session.commit()

    return jsonify({
        'success': True,
        'data': result,
        'message': 'ALTER TABLE 已執行'
    })


# =============================================================================
# Phase 4: 三面相完整狀態 + 6 方向同步
# =============================================================================


@field_specs_bp.route('/<form_template_sc>/sync-spec-to-formio', methods=['POST'])
@csrf.exempt
@require_permission('form_workflow.template.manage')
def sync_spec_to_formio(form_template_sc):
    """Spec -> FormIO（將 Spec 欄位套用到表單 schema）"""
    _ensure_models()
    from modules.form_workflow.models import FwFormTemplate

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
        return jsonify({'success': False, 'error': '找不到 Spec'}), 404

    template = FwFormTemplate.query.filter_by(
        secure_code=form_template_sc,
        org_secure_code=org.secure_code,
        is_deleted=False,
    ).first()
    if not template:
        return jsonify({'success': False, 'error': '找不到表單模板'}), 404

    from modules.spec_formulate.services.field_spec.spec_generator import apply_spec_to_existing_schema
    new_schema = apply_spec_to_existing_schema(
        spec.fields, template.schema, form_title=spec.name
    )
    template.schema = new_schema

    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(template, 'schema')
    db.session.commit()

    return jsonify({
        'success': True,
        'data': {'field_count': len(spec.fields or [])},
        'message': f'Spec -> FormIO 同步完成（{len(spec.fields or [])} 個欄位）'
    })


@field_specs_bp.route('/<form_template_sc>/sync-spec-to-sql', methods=['POST'])
@csrf.exempt
@require_permission('form_workflow.template.manage')
def sync_spec_to_sql(form_template_sc):
    """Spec -> SQL（計算 ALTER 計劃並執行）"""
    _ensure_models()
    from modules.form_workflow.models import FwSqlFormRegistry

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
        return jsonify({'success': False, 'error': '找不到 Spec'}), 404

    registry = FwSqlFormRegistry.query.filter_by(
        form_template_secure_code=form_template_sc,
        org_secure_code=org.secure_code,
        status='active',
    ).order_by(FwSqlFormRegistry.id.desc()).first()
    if not registry:
        return jsonify({'success': False, 'error': '找不到 active SQL registry'}), 404

    try:
        from modules.form_workflow.services.sql_sync.alter_manager import compute_alter_plan, execute_alter_plan
        plan = compute_alter_plan(
            registry.column_mapping,
            spec.fields,
            org.secure_code,
            registry.table_name,
        )

        if not plan.get('add_columns') and not plan.get('alter_types') and not plan.get('drop_columns'):
            return jsonify({
                'success': True,
                'data': {'no_changes': True},
                'message': 'Spec 與 SQL 結構一致，無需變更'
            })

        req_data = request.get_json() or {}
        confirm_table = req_data.get('confirm_table_name')

        result = execute_alter_plan(
            org.secure_code,
            registry.table_name,
            plan,
            plan['confirmation_token'],
            confirm_table_name=confirm_table,
        )

        if result.get('success') and result.get('new_column_mapping'):
            registry.column_mapping = result['new_column_mapping']
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(registry, 'column_mapping')
            db.session.commit()

    except Exception as e:
        logger.error(f'Spec->SQL 同步失敗: {e}')
        return jsonify({'success': False, 'error': f'同步失敗: {e}'}), 500

    return jsonify({
        'success': True,
        'data': result,
        'message': 'Spec -> SQL 同步完成'
    })


@field_specs_bp.route('/<form_template_sc>/full-status')
@require_permission('form_workflow.template.view')
def full_status(form_template_sc):
    """三面相完整狀態（含 metadata + 6 方向可用性）"""
    _ensure_models()
    from modules.form_workflow.models import FwFormTemplate, FwSqlFormRegistry

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    org_sc = org.secure_code

    # Spec
    spec = FwFormFieldSpec.query.filter_by(
        org_secure_code=org_sc,
        form_template_secure_code=form_template_sc,
        status='active',
        is_deleted=False,
    ).first()

    # FormIO (template)
    template = FwFormTemplate.query.filter_by(
        secure_code=form_template_sc,
        org_secure_code=org_sc,
        is_deleted=False,
    ).first()

    # SQL registry
    registry = FwSqlFormRegistry.query.filter_by(
        form_template_secure_code=form_template_sc,
        org_secure_code=org_sc,
        status='active',
    ).order_by(FwSqlFormRegistry.id.desc()).first()

    spec_info = None
    if spec:
        spec_info = {
            'exists': True,
            'secure_code': spec.secure_code,
            'version': spec.version,
            'field_count': len(spec.fields or []),
            'last_modified_by_name': spec.last_modified_by_name,
            'last_modified_at': spec.updated_at.isoformat() if spec.updated_at else None,
        }
    else:
        spec_info = {'exists': False}

    formio_info = None
    if template:
        schema = template.schema or {}
        from modules.spec_formulate.services.field_spec.drift_detector import _extract_formio_fields
        formio_fields = _extract_formio_fields(schema)
        formio_info = {
            'exists': True,
            'form_name': template.name,
            'field_count': len(formio_fields),
            'updated_at': template.updated_at.isoformat() if template.updated_at else None,
        }
    else:
        formio_info = {'exists': False}

    sql_info = None
    if registry:
        col_mapping = registry.column_mapping or {}
        col_count = len([k for k in col_mapping if not k.startswith('_')])
        sql_info = {
            'exists': True,
            'table_name': registry.table_name,
            'column_count': col_count,
            'row_count': registry.row_count or 0,
            'last_synced_at': registry.last_synced_at.isoformat() if registry.last_synced_at else None,
        }
    else:
        sql_info = {'exists': False}

    # 比對
    comparisons = {}
    if spec and template:
        from modules.spec_formulate.services.field_spec.drift_detector import compare_spec_vs_formio
        sf_drifts = compare_spec_vs_formio(spec.fields, template.schema)
        comparisons['spec_vs_formio'] = {
            'status': 'match' if not sf_drifts else 'mismatch',
            'drift_count': len(sf_drifts),
        }
    else:
        comparisons['spec_vs_formio'] = {'status': 'unavailable', 'drift_count': 0}

    if spec and registry:
        from modules.spec_formulate.services.field_spec.drift_detector import compare_spec_vs_sql
        ss_drifts = compare_spec_vs_sql(spec.fields, registry.column_mapping)
        comparisons['spec_vs_sql'] = {
            'status': 'match' if not ss_drifts else 'mismatch',
            'drift_count': len(ss_drifts),
        }
    else:
        comparisons['spec_vs_sql'] = {'status': 'unavailable', 'drift_count': 0}

    if template and registry:
        from modules.spec_formulate.services.field_spec.drift_detector import compare_formio_vs_sql
        fs_drifts = compare_formio_vs_sql(template.schema, registry.column_mapping)
        comparisons['formio_vs_sql'] = {
            'status': 'match' if not fs_drifts else 'mismatch',
            'drift_count': len(fs_drifts),
        }
    else:
        comparisons['formio_vs_sql'] = {'status': 'unavailable', 'drift_count': 0}

    return jsonify({
        'success': True,
        'data': {
            'spec': spec_info,
            'formio': formio_info,
            'sql': sql_info,
            'comparisons': comparisons,
        }
    })


@field_specs_bp.route('/<ft_sc>/sync-formio-to-sql', methods=['POST'])
@csrf.exempt
@require_permission('form_workflow.template.manage')
def sync_formio_to_sql(ft_sc):
    """JSONB -> SQL（可勾選同時更新 Spec）"""
    _ensure_models()
    from modules.form_workflow.models import FwFormTemplate, FwSqlFormRegistry

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    data = request.get_json() or {}
    also_update_spec = data.get('also_update_spec', False)

    template = FwFormTemplate.query.filter_by(
        secure_code=ft_sc,
        org_secure_code=org.secure_code,
        is_deleted=False,
    ).first()
    if not template:
        return jsonify({'success': False, 'error': '找不到表單模板'}), 404

    registry = FwSqlFormRegistry.query.filter_by(
        form_template_secure_code=ft_sc,
        org_secure_code=org.secure_code,
        status='active',
    ).order_by(FwSqlFormRegistry.id.desc()).first()
    if not registry:
        return jsonify({'success': False, 'error': '找不到 active SQL registry'}), 404

    # 從 FormIO schema 擷取欄位
    from modules.spec_formulate.services.field_spec.spec_generator import formio_schema_to_spec_fields
    formio_fields = formio_schema_to_spec_fields(template.schema)

    if also_update_spec:
        # 先更新 Spec（新增一版）
        existing_spec = FwFormFieldSpec.query.filter_by(
            org_secure_code=org.secure_code,
            form_template_secure_code=ft_sc,
            status='active',
            is_deleted=False,
        ).first()

        user_sc = current_user.secure_code
        user_name = getattr(current_user, 'display_name', None) or current_user.username

        _save_spec_core(
            existing_spec, formio_fields, org.secure_code, user_sc, user_name,
            description='從 FormIO->SQL 同步時同步更新',
            form_template_sc=ft_sc,
        )

    # 計算 ALTER 計劃並執行
    try:
        from modules.form_workflow.services.sql_sync.alter_manager import compute_alter_plan, execute_alter_plan
        plan = compute_alter_plan(
            registry.column_mapping,
            formio_fields,
            org.secure_code,
            registry.table_name,
        )

        if not plan.get('add_columns') and not plan.get('alter_types') and not plan.get('drop_columns'):
            return jsonify({
                'success': True,
                'data': {'no_changes': True},
                'message': 'FormIO 與 SQL 結構一致，無需變更'
            })

        result = execute_alter_plan(
            org.secure_code,
            registry.table_name,
            plan,
            plan['confirmation_token'],
        )

        if result.get('success') and result.get('new_column_mapping'):
            registry.column_mapping = result['new_column_mapping']
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(registry, 'column_mapping')
            db.session.commit()

    except Exception as e:
        logger.error(f'FormIO->SQL 同步失敗: {e}')
        return jsonify({'success': False, 'error': f'同步失敗: {e}'}), 500

    return jsonify({
        'success': True,
        'data': result,
        'message': 'FormIO -> SQL 同步完成'
    })


@field_specs_bp.route('/<ft_sc>/sync-sql-to-formio', methods=['POST'])
@csrf.exempt
@require_permission('form_workflow.template.manage')
def sync_sql_to_formio(ft_sc):
    """SQL -> JSONB（可勾選同時更新 Spec）"""
    _ensure_models()
    from modules.form_workflow.models import FwFormTemplate, FwSqlFormRegistry

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    data = request.get_json() or {}
    also_update_spec = data.get('also_update_spec', False)

    template = FwFormTemplate.query.filter_by(
        secure_code=ft_sc,
        org_secure_code=org.secure_code,
        is_deleted=False,
    ).first()
    if not template:
        return jsonify({'success': False, 'error': '找不到表單模板'}), 404

    registry = FwSqlFormRegistry.query.filter_by(
        form_template_secure_code=ft_sc,
        org_secure_code=org.secure_code,
        status='active',
    ).order_by(FwSqlFormRegistry.id.desc()).first()
    if not registry:
        return jsonify({'success': False, 'error': '找不到 active SQL registry'}), 404

    # 從 SQL 讀取實際表結構
    try:
        from modules.form_workflow.services.sql_sync.schema_reader import read_table_columns, pg_columns_to_spec_fields
        columns = read_table_columns(org.secure_code, registry.table_name)
        sql_fields = pg_columns_to_spec_fields(columns, registry.column_mapping)
    except Exception as e:
        logger.error(f'SQL->FormIO 同步失敗: {e}')
        return jsonify({'success': False, 'error': f'讀取表結構失敗: {e}'}), 500

    if not sql_fields:
        return jsonify({'success': False, 'error': '未偵測到可轉換的資料欄位'}), 400

    if also_update_spec:
        existing_spec = FwFormFieldSpec.query.filter_by(
            org_secure_code=org.secure_code,
            form_template_secure_code=ft_sc,
            status='active',
            is_deleted=False,
        ).first()

        user_sc = current_user.secure_code
        user_name = getattr(current_user, 'display_name', None) or current_user.username

        _save_spec_core(
            existing_spec, sql_fields, org.secure_code, user_sc, user_name,
            description='從 SQL->FormIO 同步時同步更新',
            form_template_sc=ft_sc,
        )

    # 從 sql_fields 生成 FormIO schema 並套用
    from modules.spec_formulate.services.field_spec.spec_generator import apply_spec_to_existing_schema
    new_schema = apply_spec_to_existing_schema(sql_fields, template.schema)
    template.schema = new_schema

    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(template, 'schema')
    db.session.commit()

    return jsonify({
        'success': True,
        'data': {'field_count': len(sql_fields)},
        'message': f'SQL -> FormIO 同步完成（{len(sql_fields)} 個欄位）'
    })


# =============================================================================
# Phase 4: Spec SQL Table 直接操作（設計階段）
# =============================================================================

@field_specs_bp.route('/sql-tables')
@require_permission('form_workflow.template.view')
def list_sql_tables():
    """列出企業 DB 中所有表"""
    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    try:
        from modules.spec_formulate.services.field_spec.spec_sql_table import list_org_tables
        tables = list_org_tables(org.secure_code)
    except Exception as e:
        logger.error(f'列出 org DB 表失敗: {e}')
        return jsonify({'success': False, 'error': f'無法連線企業資料庫: {e}'}), 500

    return jsonify({'success': True, 'data': tables})


@field_specs_bp.route('/<form_template_sc>/sync-from-sql-table', methods=['POST'])
@csrf.exempt
@require_permission('form_workflow.template.edit')
def sync_from_sql_table(form_template_sc):
    """從指定 SQL 表讀取欄位定義（不依賴 registry）"""
    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    data = request.get_json() or {}
    table_name = (data.get('table_name') or '').strip()
    if not table_name:
        return jsonify({'success': False, 'error': '缺少 table_name'}), 400

    try:
        from modules.form_workflow.services.sql_sync.schema_reader import read_table_columns, pg_columns_to_spec_fields
        columns = read_table_columns(org.secure_code, table_name)
        fields = pg_columns_to_spec_fields(columns)
    except Exception as e:
        logger.error(f'從 SQL Table 讀取欄位失敗: {e}')
        return jsonify({'success': False, 'error': f'讀取表結構失敗: {e}'}), 500

    if not fields:
        return jsonify({'success': False, 'error': '未偵測到可轉換的資料欄位'}), 400

    return jsonify({
        'success': True,
        'data': {'fields': fields, 'table_name': table_name},
        'message': f'從 {table_name} 讀取到 {len(fields)} 個欄位'
    })


@field_specs_bp.route('/<form_template_sc>/apply-to-sql-table', methods=['POST'])
@csrf.exempt
@require_permission('form_workflow.template.manage')
def apply_to_sql_table(form_template_sc):
    """將 spec 欄位定義建立/更新到 SQL Table（template 模式）"""
    _ensure_models()
    from modules.form_workflow.models import FwFormTemplate

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
        return jsonify({'success': False, 'error': '找不到表單範本'}), 404

    data = request.get_json() or {}
    confirm = bool(data.get('confirm', False))

    try:
        from modules.spec_formulate.services.field_spec.spec_sql_table import (
            compute_spec_table_name, ensure_org_db, apply_spec_to_sql,
        )
        ensure_org_db(org.secure_code, org.id)
        table_name = compute_spec_table_name(spec, form_template=template)
        result = apply_spec_to_sql(
            org.secure_code, table_name, spec.fields, confirm=confirm,
        )
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        logger.error(f'套用 spec 到 SQL Table 失敗: {e}')
        return jsonify({'success': False, 'error': f'操作失敗: {e}'}), 500

    if confirm and spec.sql_table_code:
        db.session.commit()

    return jsonify({'success': True, 'data': result})


@field_specs_bp.route('/standalone/<spec_sc>/sync-from-sql-table', methods=['POST'])
@csrf.exempt
@require_permission('form_workflow.template.edit')
def standalone_sync_from_sql_table(spec_sc):
    """從指定 SQL 表讀取欄位定義（standalone 模式）"""
    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    data = request.get_json() or {}
    table_name = (data.get('table_name') or '').strip()
    if not table_name:
        return jsonify({'success': False, 'error': '缺少 table_name'}), 400

    try:
        from modules.form_workflow.services.sql_sync.schema_reader import read_table_columns, pg_columns_to_spec_fields
        columns = read_table_columns(org.secure_code, table_name)
        fields = pg_columns_to_spec_fields(columns)
    except Exception as e:
        logger.error(f'從 SQL Table 讀取欄位失敗: {e}')
        return jsonify({'success': False, 'error': f'讀取表結構失敗: {e}'}), 500

    if not fields:
        return jsonify({'success': False, 'error': '未偵測到可轉換的資料欄位'}), 400

    return jsonify({
        'success': True,
        'data': {'fields': fields, 'table_name': table_name},
        'message': f'從 {table_name} 讀取到 {len(fields)} 個欄位'
    })


@field_specs_bp.route('/standalone/<spec_sc>/apply-to-sql-table', methods=['POST'])
@csrf.exempt
@require_permission('form_workflow.template.manage')
def standalone_apply_to_sql_table(spec_sc):
    """將 spec 欄位定義建立/更新到 SQL Table（standalone 模式）"""
    _ensure_models()

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    spec = FwFormFieldSpec.query.filter_by(
        org_secure_code=org.secure_code,
        secure_code=spec_sc,
        status='active',
        is_deleted=False,
    ).first()
    if not spec:
        return jsonify({'success': False, 'error': '找不到 active 欄位規格'}), 404

    data = request.get_json() or {}
    confirm = bool(data.get('confirm', False))

    try:
        from modules.spec_formulate.services.field_spec.spec_sql_table import (
            compute_spec_table_name, ensure_org_db, apply_spec_to_sql,
        )
        ensure_org_db(org.secure_code, org.id)
        table_name = compute_spec_table_name(spec)

        if spec.sql_table_code:
            db.session.commit()

        result = apply_spec_to_sql(
            org.secure_code, table_name, spec.fields, confirm=confirm,
        )
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        logger.error(f'套用 spec 到 SQL Table 失敗: {e}')
        return jsonify({'success': False, 'error': f'操作失敗: {e}'}), 500

    # confirm=True 且有實際執行時，補建/更新 Registry
    if confirm and result.get('executed'):
        try:
            from modules.form_workflow.models import FwSqlFormRegistry
            from modules.spec_formulate.services.field_spec.spec_generator import spec_to_formio_schema
            from modules.spec_formulate.services.field_spec.spec_sql_table import spec_fields_to_columns
            from modules.form_workflow.services.sql_sync.converter import build_column_mapping

            form_schema = spec_to_formio_schema(spec.fields)
            columns = spec_fields_to_columns(spec.fields)
            column_mapping = build_column_mapping(columns)

            existing = FwSqlFormRegistry.query.filter_by(
                org_secure_code=org.secure_code,
                table_name=result['table_name'],
            ).first()

            if existing:
                existing.form_schema = form_schema
                existing.column_mapping = column_mapping
                existing.create_ddl = result.get('ddl')
                existing.spec_secure_code = spec.secure_code
                existing.status = 'active'
            else:
                registry = FwSqlFormRegistry(
                    org_secure_code=org.secure_code,
                    mapping_secure_code=None,
                    published_secure_code=None,
                    form_template_secure_code=spec.form_template_secure_code,
                    spec_secure_code=spec.secure_code,
                    table_name=result['table_name'],
                    form_schema=form_schema,
                    column_mapping=column_mapping,
                    create_ddl=result.get('ddl'),
                    status='active',
                )
                db.session.add(registry)

            db.session.commit()
            logger.info(f'SpecSQL: Registry {"updated" if existing else "created"} for {result["table_name"]}')
        except Exception as e:
            logger.error(f'建立 Registry 失敗: {e}')
            db.session.rollback()

    return jsonify({'success': True, 'data': result})
