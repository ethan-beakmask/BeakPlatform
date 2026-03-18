"""
Spec Formulate Module - Multifaceted Specs API
多面向規格 CRUD API

URL prefix: /api/spec-formulate/multifaceted
"""
import json
import logging
import secrets
import tempfile
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request, send_file

from app import db
from app.security.decorators import module_access_required
from app.platform.auth import current_user
from app.platform.data import get_current_org

logger = logging.getLogger(__name__)

multifaceted_bp = Blueprint(
    'spec_formulate_multifaceted',
    __name__,
    url_prefix='/api/spec-formulate/multifaceted'
)


# ── Helper ──

def _get_user_info():
    """取得當前用戶資訊"""
    user_sc = current_user.secure_code
    user_name = (
        getattr(current_user, 'display_name', None)
        or current_user.username
    )
    return user_sc, user_name


def _fields_identical(old_fields, new_fields):
    """比較兩版 fields 是否完全一致"""
    return json.dumps(old_fields, sort_keys=True) == json.dumps(
        new_fields, sort_keys=True
    )


def _merge_formio_into_fields(old_fields, formio_fields):
    """
    將 FormIO 反向轉出的欄位合併到現有 spec fields

    策略：
    - 以 formio_fields 的順序和欄位清單為準（新增、刪除、排序）
    - 已存在的欄位保留 core 和其他 facets（postgresql、excel、csv）
    - formio facet 以最新值覆蓋
    - 新欄位直接採用 formio 反向轉出的結果
    """
    old_map = {}
    for f in (old_fields or []):
        key = f.get('field_key')
        if key:
            old_map[key] = f

    merged = []
    for i, nf in enumerate(formio_fields or []):
        key = nf.get('field_key')
        if not key:
            continue

        old = old_map.get(key)
        if old:
            # 已存在：保留 old 的 core 和其他 facets，更新 formio facet + 排序
            field = json.loads(json.dumps(old))
            field['sort_order'] = i
            field['label'] = nf.get('label') or field.get('label', '')
            field['description'] = nf.get('description') or field.get('description', '')
            # 更新 core.required（FormIO 可能改了）
            if 'core' not in field:
                field['core'] = {}
            field['core']['required'] = nf.get('core', {}).get('required', False)
            # 更新 formio facet
            if 'facets' not in field:
                field['facets'] = {}
            field['facets']['formio'] = nf.get('facets', {}).get('formio', {})
        else:
            # 新欄位：直接用 formio 反向轉出的結果
            field = nf
            field['sort_order'] = i

        merged.append(field)

    return merged


def _sync_form_to_spec(spec, ft_sc, org_sc):
    """從表單模板同步最新 schema 到 spec（合併式，保留其他 facets）"""
    from modules.form_workflow.models import FwFormTemplate
    from modules.spec_formulate.models import FwSpecMultifacetedHistory

    template = FwFormTemplate.query.filter_by(
        secure_code=ft_sc,
        org_secure_code=org_sc,
    ).first()
    if not template or not template.schema:
        return

    formio_fields = _formio_schema_to_multifaceted_fields(template.schema)
    merged = _merge_formio_into_fields(spec.fields, formio_fields)

    # 比較合併結果與現有欄位
    if _fields_identical(spec.fields, merged):
        return

    # 寫入歷史
    history = FwSpecMultifacetedHistory(
        org_secure_code=org_sc,
        spec_secure_code=spec.secure_code,
        version=spec.version,
        fields_snapshot=spec.fields or [],
        active_facets_snapshot=spec.active_facets or [],
        change_description='從表單設計器同步',
        changed_by=current_user.secure_code,
        changed_by_name=(
            getattr(current_user, 'display_name', None)
            or current_user.username
        ),
    )
    db.session.add(history)

    spec.fields = merged
    spec.version = (spec.version or 0) + 1
    if 'formio' not in (spec.active_facets or []):
        spec.active_facets = list(spec.active_facets or []) + ['formio']
    db.session.commit()

    logger.info(
        'Synced form %s -> spec %s (v%d, %d fields)',
        ft_sc, spec.secure_code, spec.version, len(merged),
    )


# FormIO component_type -> data_class 反向映射
_FORMIO_TO_DC = {
    'textfield': 'text',
    'textarea': 'text_long',
    'number': 'integer',
    'currency': 'currency',
    'checkbox': 'boolean',
    'radio': 'enum_single',
    'select': 'enum_single',
    'selectboxes': 'enum_multi',
    'day': 'date',
    'datetime': 'datetime',
    'email': 'email',
    'phoneNumber': 'phone',
    'phone': 'phone',
    'url': 'url',
    'tags': 'tags',
    'signature': 'signature',
    'file': 'binary',
    'password': 'text',
    'hidden': 'text',
}

# 不轉為 spec 欄位的 component types（佈局/裝飾用）
_FORMIO_SKIP_TYPES = {
    'htmlelement', 'content', 'button', 'panel', 'columns',
    'fieldset', 'tabs', 'well', 'table',
}


def _formio_schema_to_multifaceted_fields(schema):
    """
    從 FormIO schema 反向轉為 multifaceted spec fields

    遞迴處理巢狀 components（panel/columns 等容器內的欄位也提取）。
    """
    if not schema:
        return []

    components = schema.get('components', [])
    fields = []
    _extract_components(components, fields, 0)
    return fields


def _extract_components(components, fields, sort_start):
    """遞迴提取 FormIO components 為 multifaceted fields"""
    for comp in (components or []):
        ctype = comp.get('type', '')

        # 容器型：遞迴進入子 components
        if ctype in ('panel', 'fieldset', 'well', 'tabs'):
            _extract_components(
                comp.get('components', []), fields, len(fields)
            )
            continue
        if ctype == 'columns':
            for col in (comp.get('columns') or []):
                _extract_components(
                    col.get('components', []), fields, len(fields)
                )
            continue
        if ctype == 'table':
            for row_list in (comp.get('rows') or []):
                for cell in (row_list or []):
                    _extract_components(
                        cell.get('components', []), fields, len(fields)
                    )
            continue

        # 跳過裝飾/佈局元件
        if ctype in _FORMIO_SKIP_TYPES:
            continue

        key = comp.get('key', '')
        if not key:
            continue

        label = comp.get('label', '') or key
        validate = comp.get('validate') or {}
        properties = comp.get('properties') or {}
        dc = _FORMIO_TO_DC.get(ctype, 'text')

        # 帶小數驗證的 number -> decimal
        if ctype == 'number' and validate.get('step') and '.' in str(validate['step']):
            dc = 'decimal'

        field = {
            'field_key': key,
            'label': label,
            'description': comp.get('description', '') or '',
            'sort_order': len(fields),
            'core': {
                'data_class': dc,
                'required': bool(validate.get('required')),
                'is_pii': properties.get('pii') == 'true',
                'default_value': comp.get('defaultValue'),
            },
            'facets': {
                'formio': {
                    'component_type': ctype,
                },
            },
        }

        # 保留 formio 驗證設定
        formio_validate = {}
        for vk in ('maxLength', 'minLength', 'min', 'max', 'pattern', 'custom'):
            if validate.get(vk) is not None:
                formio_validate[vk] = validate[vk]
        if formio_validate:
            field['facets']['formio']['validate'] = formio_validate

        fields.append(field)


# ── 翻譯輔助 API ──

@multifaceted_bp.route('/translate', methods=['POST'])
@module_access_required('spec_formulate')
def translate_name():
    """
    將中文名稱翻譯為英文識別碼（小寫 snake_case）

    POST body:
    {
        "name": "文具庫存表",
        "prefix": "spec_",      // 選填，預設空
        "mode": "table_name"    // table_name 或 field_key
    }

    Response: { "success": true, "code": "spec_stationery_inventory" }
    """
    from app.services.code_generator import get_code_generator

    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'success': False, 'error': '名稱不可為空'}), 400

    prefix = (data.get('prefix') or '').strip()

    generator = get_code_generator()
    try:
        raw = generator.generate(name, exists_checker=None)
        # 轉小寫 snake_case
        code = raw.lower()
        if prefix:
            code = prefix + code
        return jsonify({'success': True, 'code': code})
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400


# ── Data Class Registry API ──

@multifaceted_bp.route('/data-classes', methods=['GET'])
@module_access_required('spec_formulate')
def list_data_classes():
    """取得所有 data_class 清單（含格式支援資訊）"""
    from modules.spec_formulate.services.multifaceted.data_class_registry import (
        get_data_class_list,
    )
    return jsonify({'success': True, 'data': get_data_class_list()})


@multifaceted_bp.route('/data-classes/<data_class>/facet-defaults/<facet_name>',
                       methods=['GET'])
@module_access_required('spec_formulate')
def get_data_class_facet_defaults(data_class, facet_name):
    """取得指定 data_class 在特定格式下的預設 facet 值"""
    from modules.spec_formulate.services.multifaceted.data_class_registry import (
        get_facet_defaults,
        is_facet_supported,
        get_unsupported_reason,
    )
    if not is_facet_supported(data_class, facet_name):
        reason = get_unsupported_reason(data_class, facet_name)
        return jsonify({
            'success': False,
            'supported': False,
            'reason': reason,
        }), 200

    defaults = get_facet_defaults(data_class, facet_name)
    # 過濾掉 meta 欄位
    clean = {
        k: v for k, v in defaults.items()
        if k not in ('supported', 'reason', 'note')
    }
    return jsonify({
        'success': True,
        'supported': True,
        'defaults': clean,
        'note': defaults.get('note'),
    })


# ── SPEC CRUD ──

@multifaceted_bp.route('/specs', methods=['GET'])
@module_access_required('spec_formulate')
def list_specs():
    """列出所有多面向規格"""
    from modules.spec_formulate.models import FwSpecMultifaceted

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': '無法取得企業資訊'}), 403

    specs = FwSpecMultifaceted.query.filter_by(
        org_secure_code=org.secure_code,
        is_deleted=False,
    ).order_by(
        FwSpecMultifaceted.updated_at.desc()
    ).all()

    result = []
    for s in specs:
        d = s.to_dict()
        d['field_count'] = len(s.fields or [])
        result.append(d)

    return jsonify({'success': True, 'data': result})


@multifaceted_bp.route('/specs', methods=['POST'])
@module_access_required('spec_formulate')
def create_spec():
    """建立多面向規格"""
    from modules.spec_formulate.models import FwSpecMultifaceted
    from modules.spec_formulate.services.multifaceted.field_normalizer import (
        normalize_fields,
    )

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': '無法取得企業資訊'}), 403

    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'success': False, 'error': '規格名稱必填'}), 400

    table_name = (data.get('table_name') or '').strip()
    description = (data.get('description') or '').strip()
    raw_fields = data.get('fields', [])

    # 正規化與驗證
    fields, warnings, errors = normalize_fields(raw_fields)
    if errors:
        return jsonify({
            'success': False,
            'error': '欄位驗證失敗',
            'details': errors,
        }), 400

    user_sc, user_name = _get_user_info()

    spec = FwSpecMultifaceted(
        org_secure_code=org.secure_code,
        name=name,
        table_name=table_name or None,
        description=description,
        version=1,
        fields=fields,
        active_facets=[],
        status='active',
        last_modified_by=user_sc,
        last_modified_by_name=user_name,
    )
    db.session.add(spec)
    db.session.commit()

    result = spec.to_dict()
    result['field_count'] = len(fields)
    result['warnings'] = warnings

    return jsonify({
        'success': True,
        'data': result,
        'message': f'已建立規格「{name}」',
    }), 201


@multifaceted_bp.route('/specs/<spec_sc>', methods=['GET'])
@module_access_required('spec_formulate')
def get_spec(spec_sc):
    """取得單一多面向規格"""
    from modules.spec_formulate.models import FwSpecMultifaceted

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': '無法取得企業資訊'}), 403

    spec = FwSpecMultifaceted.query.filter_by(
        secure_code=spec_sc,
        org_secure_code=org.secure_code,
        is_deleted=False,
    ).first()

    if not spec:
        return jsonify({'success': False, 'error': '規格不存在'}), 404

    result = spec.to_dict()
    result['field_count'] = len(spec.fields or [])

    # 補上關聯表單名稱
    if spec.linked_form_template_sc:
        from modules.form_workflow.models.form_template import FwFormTemplate
        ft = FwFormTemplate.query.filter_by(
            secure_code=spec.linked_form_template_sc,
            is_deleted=False,
        ).first()
        result['linked_form_template_name'] = ft.name if ft else ''

    return jsonify({'success': True, 'data': result})


@multifaceted_bp.route('/specs/<spec_sc>', methods=['POST'])
@module_access_required('spec_formulate')
def update_spec(spec_sc):
    """更新多面向規格（自動版本遞增 + 歷史記錄）"""
    from modules.spec_formulate.models import (
        FwSpecMultifaceted,
        FwSpecMultifacetedHistory,
    )
    from modules.spec_formulate.services.multifaceted.field_normalizer import (
        normalize_fields,
        compute_diff,
    )

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': '無法取得企業資訊'}), 403

    spec = FwSpecMultifaceted.query.filter_by(
        secure_code=spec_sc,
        org_secure_code=org.secure_code,
        is_deleted=False,
    ).first()

    if not spec:
        return jsonify({'success': False, 'error': '規格不存在'}), 404

    data = request.get_json(silent=True) or {}
    raw_fields = data.get('fields', [])

    # 正規化與驗證
    fields, warnings, errors = normalize_fields(raw_fields)
    if errors:
        return jsonify({
            'success': False,
            'error': '欄位驗證失敗',
            'details': errors,
        }), 400

    # 檢查是否有實際變更
    old_fields = spec.fields or []
    name = (data.get('name') or '').strip() or spec.name
    table_name = (data.get('table_name') or '').strip()
    description = data.get('description', spec.description)

    if _fields_identical(old_fields, fields) and name == spec.name:
        return jsonify({
            'success': True,
            'data': spec.to_dict(),
            'message': '內容無變更，未建立新版本',
        })

    # 計算差異
    diff = compute_diff(old_fields, fields)
    user_sc, user_name = _get_user_info()

    # 寫入歷史（儲存舊版快照）
    history = FwSpecMultifacetedHistory(
        spec_secure_code=spec.secure_code,
        version=spec.version,
        fields_snapshot=old_fields,
        active_facets_snapshot=list(spec.active_facets or []),
        change_description=data.get('change_description', ''),
        change_diff=diff,
        changed_by=user_sc,
        changed_by_name=user_name,
        org_secure_code=org.secure_code,
    )
    db.session.add(history)

    # 更新 spec
    spec.name = name
    if table_name:
        spec.table_name = table_name
    spec.description = description
    spec.version += 1
    spec.fields = fields
    spec.last_modified_by = user_sc
    spec.last_modified_by_name = user_name
    spec.updated_at = datetime.now(timezone.utc)

    db.session.commit()

    result = spec.to_dict()
    result['field_count'] = len(fields)
    result['warnings'] = warnings
    result['diff'] = diff

    return jsonify({
        'success': True,
        'data': result,
        'message': f'已更新至 v{spec.version}',
    })


@multifaceted_bp.route('/specs/<spec_sc>', methods=['DELETE'])
@module_access_required('spec_formulate')
def delete_spec(spec_sc):
    """軟刪除多面向規格"""
    from modules.spec_formulate.models import FwSpecMultifaceted

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': '無法取得企業資訊'}), 403

    spec = FwSpecMultifaceted.query.filter_by(
        secure_code=spec_sc,
        org_secure_code=org.secure_code,
        is_deleted=False,
    ).first()

    if not spec:
        return jsonify({'success': False, 'error': '規格不存在'}), 404

    spec.is_deleted = True
    spec.deleted_at = datetime.now(timezone.utc)
    spec.status = 'archived'
    db.session.commit()

    return jsonify({'success': True, 'message': f'已刪除規格「{spec.name}」'})


# ── 版本歷史 ──

@multifaceted_bp.route('/specs/<spec_sc>/history', methods=['GET'])
@module_access_required('spec_formulate')
def get_history(spec_sc):
    """取得規格版本歷史"""
    from modules.spec_formulate.models import (
        FwSpecMultifaceted,
        FwSpecMultifacetedHistory,
    )

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': '無法取得企業資訊'}), 403

    spec = FwSpecMultifaceted.query.filter_by(
        secure_code=spec_sc,
        org_secure_code=org.secure_code,
        is_deleted=False,
    ).first()

    if not spec:
        return jsonify({'success': False, 'error': '規格不存在'}), 404

    histories = FwSpecMultifacetedHistory.query.filter_by(
        spec_secure_code=spec_sc,
        is_deleted=False,
    ).order_by(
        FwSpecMultifacetedHistory.version.desc()
    ).all()

    return jsonify({
        'success': True,
        'data': [h.to_dict() for h in histories],
    })


# ── Facet 填充 ──

@multifaceted_bp.route('/specs/<spec_sc>/populate-facet', methods=['POST'])
@module_access_required('spec_formulate')
def populate_facet(spec_sc):
    """
    為規格的所有欄位填入指定格式的預設 facet 值

    Body: { "facet_name": "postgresql" }
    """
    from modules.spec_formulate.models import FwSpecMultifaceted
    from modules.spec_formulate.services.multifaceted.data_class_registry import (
        populate_facet_defaults,
        is_facet_supported,
        get_unsupported_reason,
        ALL_FACETS,
    )

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': '無法取得企業資訊'}), 403

    spec = FwSpecMultifaceted.query.filter_by(
        secure_code=spec_sc,
        org_secure_code=org.secure_code,
        is_deleted=False,
    ).first()

    if not spec:
        return jsonify({'success': False, 'error': '規格不存在'}), 404

    data = request.get_json(silent=True) or {}
    facet_name = data.get('facet_name', '').strip()
    if facet_name not in ALL_FACETS:
        return jsonify({
            'success': False,
            'error': f'未知的格式: {facet_name}（可用: {", ".join(ALL_FACETS)}）',
        }), 400

    fields = list(spec.fields or [])
    skipped = []
    populated = []

    for f in fields:
        dc = f.get('core', {}).get('data_class', 'text')
        fk = f.get('field_key', '?')

        if not is_facet_supported(dc, facet_name):
            reason = get_unsupported_reason(dc, facet_name)
            skipped.append({'field_key': fk, 'reason': reason})
            continue

        result = populate_facet_defaults(f, facet_name)
        if result:
            populated.append(fk)

    # 更新 spec
    spec.fields = fields
    spec.add_facet(facet_name)
    spec.updated_at = datetime.now(timezone.utc)
    db.session.commit()

    return jsonify({
        'success': True,
        'data': {
            'populated_count': len(populated),
            'populated_fields': populated,
            'skipped_count': len(skipped),
            'skipped_fields': skipped,
            'active_facets': spec.active_facets,
        },
        'message': f'已為 {len(populated)} 個欄位填入 {facet_name} 預設值',
    })


# ── DOCX 匯出 ──

@multifaceted_bp.route('/export/docx', methods=['POST'])
@module_access_required('spec_formulate')
def export_docx():
    """
    匯出多面向規格書為 Word 文件。

    POST body:
    {
        "doc_title": "資料結構規格書",   // 選填
        "specs": [
            {
                "spec_sc": "xxx",
                "version": 3,           // 選填，預設最新版
                "facets": ["postgresql", "excel"]
            }
        ]
    }
    """
    from modules.spec_formulate.models import (
        FwSpecMultifaceted,
        FwSpecMultifacetedHistory,
    )
    from modules.spec_formulate.services.multifaceted.docx_writer import (
        generate_spec_docx,
    )

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': '無法取得企業資訊'}), 403

    data = request.get_json(silent=True) or {}
    spec_refs = data.get('specs', [])
    if not spec_refs:
        return jsonify({'success': False, 'error': '請至少選擇一個規格'}), 400

    doc_title = (data.get('doc_title') or '').strip() or '資料結構規格書'

    entries = []
    for ref in spec_refs:
        spec_sc = ref.get('spec_sc')
        if not spec_sc:
            return jsonify({'success': False, 'error': '每個項目需有 spec_sc'}), 400

        req_version = ref.get('version')  # None = 最新版
        facets = ref.get('facets', [])
        if not facets:
            return jsonify({
                'success': False,
                'error': f'規格 {spec_sc} 未指定匯出格式',
            }), 400

        # 查詢 spec
        spec = FwSpecMultifaceted.query.filter_by(
            secure_code=spec_sc,
            org_secure_code=org.secure_code,
            is_deleted=False,
        ).first()

        if not spec:
            return jsonify({'success': False, 'error': f'規格不存在: {spec_sc}'}), 404

        # 取得指定版本的 fields
        if req_version and req_version != spec.version:
            # 從歷史記錄取
            history = FwSpecMultifacetedHistory.query.filter_by(
                spec_secure_code=spec_sc,
                version=req_version,
                is_deleted=False,
            ).first()

            if not history:
                return jsonify({
                    'success': False,
                    'error': f'找不到 {spec.name} 的版本 v{req_version}',
                }), 404

            fields = history.fields_snapshot or []
            active_facets = history.active_facets_snapshot or []
            version = history.version
        else:
            fields = spec.fields or []
            active_facets = spec.active_facets or []
            version = spec.version

        # 驗證所選 facet 是否在 active_facets 中
        invalid_facets = [f for f in facets if f not in active_facets]
        if invalid_facets:
            return jsonify({
                'success': False,
                'error': (
                    f'{spec.name} v{version} 未啟用格式: '
                    f'{", ".join(invalid_facets)}'
                ),
            }), 400

        entries.append({
            'name': spec.name,
            'description': spec.description or '',
            'version': version,
            'fields': fields,
            'active_facets': active_facets,
            'facets': facets,
        })

    # 產生 DOCX
    try:
        tmp = tempfile.NamedTemporaryFile(suffix='.docx', delete=False)
        tmp.close()

        generate_spec_docx(entries, tmp.name, doc_title=doc_title)

        # 檔名
        if len(entries) == 1:
            filename = f"{entries[0]['name']}_spec.docx"
        else:
            names = '_'.join(e['name'] for e in entries[:3])
            filename = f"{names}_spec.docx"

        return send_file(
            tmp.name,
            mimetype=(
                'application/vnd.openxmlformats-officedocument'
                '.wordprocessingml.document'
            ),
            as_attachment=True,
            download_name=filename,
        )
    except Exception as e:
        logger.exception('DOCX 匯出失敗')
        return jsonify({'success': False, 'error': f'匯出失敗: {str(e)}'}), 500


@multifaceted_bp.route('/specs/<spec_sc>/versions', methods=['GET'])
@module_access_required('spec_formulate')
def list_versions(spec_sc):
    """取得規格的所有版本號清單（供匯出選擇版本用）"""
    from modules.spec_formulate.models import (
        FwSpecMultifaceted,
        FwSpecMultifacetedHistory,
    )

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': '無法取得企業資訊'}), 403

    spec = FwSpecMultifaceted.query.filter_by(
        secure_code=spec_sc,
        org_secure_code=org.secure_code,
        is_deleted=False,
    ).first()

    if not spec:
        return jsonify({'success': False, 'error': '規格不存在'}), 404

    # 歷史版本
    histories = FwSpecMultifacetedHistory.query.filter_by(
        spec_secure_code=spec_sc,
        is_deleted=False,
    ).order_by(
        FwSpecMultifacetedHistory.version.desc()
    ).all()

    versions = []
    # 當前版本（最新）
    versions.append({
        'version': spec.version,
        'is_current': True,
        'active_facets': spec.active_facets or [],
        'field_count': len(spec.fields or []),
    })
    # 歷史版本
    for h in histories:
        versions.append({
            'version': h.version,
            'is_current': False,
            'active_facets': h.active_facets_snapshot or [],
            'field_count': len(h.fields_snapshot or []),
        })

    return jsonify({'success': True, 'data': versions})


# ── 表單關聯 / 建立 ──

@multifaceted_bp.route('/by-form-template/<ft_sc>', methods=['GET', 'POST'])
@module_access_required('spec_formulate')
def get_or_create_spec_by_form_template(ft_sc):
    """
    依表單模板查找或自動建立關聯的 multifaceted spec

    GET  -- 查找，找不到回 404
    POST -- 查找，找不到則自動建立空 spec 並關聯，回 201
    """
    from modules.spec_formulate.models import FwSpecMultifaceted
    from modules.form_workflow.models import FwFormTemplate

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'no org'}), 403

    spec = FwSpecMultifaceted.query.filter_by(
        org_secure_code=org.secure_code,
        linked_form_template_sc=ft_sc,
        is_deleted=False,
        status='active',
    ).first()

    if spec:
        if request.method == 'POST':
            try:
                _sync_form_to_spec(spec, ft_sc, org.secure_code)
            except Exception as e:
                logger.error('表單同步到 spec 失敗: %s', e, exc_info=True)
                # 同步失敗不阻斷跳轉，仍讓使用者進入 spec 編輯器

        return jsonify({
            'success': True,
            'data': {'secure_code': spec.secure_code, 'name': spec.name},
        })

    # 找不到
    if request.method == 'GET':
        return jsonify({'success': False, 'error': '此表單尚未關聯規格'}), 404

    # POST: 自動建立 spec 並關聯，從 FormIO schema 匯入欄位
    template = FwFormTemplate.query.filter_by(
        secure_code=ft_sc,
        org_secure_code=org.secure_code,
    ).first()
    if not template:
        return jsonify({'success': False, 'error': '表單模板不存在'}), 404

    user_sc, user_name = _get_user_info()

    # 從 FormIO schema 反向轉為 multifaceted fields
    fields = _formio_schema_to_multifaceted_fields(template.schema)
    active_facets = ['formio'] if fields else []

    spec = FwSpecMultifaceted(
        org_secure_code=org.secure_code,
        name=template.name or ft_sc,
        table_name=None,
        description=f'由表單「{template.name}」自動建立',
        version=1,
        fields=fields,
        active_facets=active_facets,
        status='active',
        linked_form_template_sc=ft_sc,
        last_modified_by=user_sc,
        last_modified_by_name=user_name,
    )
    db.session.add(spec)
    db.session.commit()

    return jsonify({
        'success': True,
        'data': {'secure_code': spec.secure_code, 'name': spec.name},
        'message': f'已自動建立規格「{spec.name}」',
    }), 201


@multifaceted_bp.route('/available-templates', methods=['GET'])
@module_access_required('spec_formulate')
def available_templates():
    """列出可關聯的表單模板（未被任何 multifaceted spec 佔用的）"""
    from modules.spec_formulate.models import FwSpecMultifaceted
    from modules.form_workflow.models import FwFormTemplate

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': '無法取得企業資訊'}), 403

    # 已被佔用的 form_template secure_codes
    occupied = set()
    specs = FwSpecMultifaceted.query.filter_by(
        org_secure_code=org.secure_code,
        is_deleted=False,
        status='active',
    ).all()
    for s in specs:
        if s.linked_form_template_sc:
            occupied.add(s.linked_form_template_sc)

    # 查可用的 form_template
    templates = FwFormTemplate.query.filter_by(
        org_secure_code=org.secure_code,
        is_active=True,
        is_deleted=False,
    ).order_by(FwFormTemplate.name).all()

    result = []
    for t in templates:
        if t.secure_code not in occupied:
            result.append({
                'secure_code': t.secure_code,
                'name': t.name,
                'code': t.code,
            })

    return jsonify({'success': True, 'data': result})


@multifaceted_bp.route('/specs/<spec_sc>/link-form', methods=['POST'])
@module_access_required('spec_formulate')
def link_form(spec_sc):
    """
    關聯現有表單模板到 multifaceted spec

    Body: { "form_template_secure_code": "xxx" }
    """
    from modules.spec_formulate.models import FwSpecMultifaceted
    from modules.form_workflow.models import FwFormTemplate

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': '無法取得企業資訊'}), 403

    spec = FwSpecMultifaceted.query.filter_by(
        secure_code=spec_sc,
        org_secure_code=org.secure_code,
        is_deleted=False,
    ).first()
    if not spec:
        return jsonify({'success': False, 'error': '規格不存在'}), 404

    data = request.get_json(silent=True) or {}
    ft_sc = (data.get('form_template_secure_code') or '').strip()
    if not ft_sc:
        return jsonify({'success': False, 'error': '缺少 form_template_secure_code'}), 400

    template = FwFormTemplate.query.filter_by(
        secure_code=ft_sc,
        org_secure_code=org.secure_code,
        is_active=True,
        is_deleted=False,
    ).first()
    if not template:
        return jsonify({'success': False, 'error': '表單模板不存在'}), 404

    # 檢查是否已被其他 spec 佔用
    existing = FwSpecMultifaceted.query.filter_by(
        org_secure_code=org.secure_code,
        linked_form_template_sc=ft_sc,
        is_deleted=False,
        status='active',
    ).first()
    if existing and existing.secure_code != spec_sc:
        return jsonify({
            'success': False,
            'error': f'此表單模板已被「{existing.name}」關聯',
        }), 409

    spec.linked_form_template_sc = ft_sc
    db.session.commit()

    return jsonify({
        'success': True,
        'data': {
            'linked_form_template_sc': ft_sc,
            'template_name': template.name,
            'template_code': template.code,
        },
        'message': f'已關聯表單模板「{template.name}」',
    })


@multifaceted_bp.route('/specs/<spec_sc>/unlink-form', methods=['POST'])
@module_access_required('spec_formulate')
def unlink_form(spec_sc):
    """解除表單關聯"""
    from modules.spec_formulate.models import FwSpecMultifaceted

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': '無法取得企業資訊'}), 403

    spec = FwSpecMultifaceted.query.filter_by(
        secure_code=spec_sc,
        org_secure_code=org.secure_code,
        is_deleted=False,
    ).first()
    if not spec:
        return jsonify({'success': False, 'error': '規格不存在'}), 404

    spec.linked_form_template_sc = None
    db.session.commit()

    return jsonify({'success': True, 'message': '已解除表單關聯'})


@multifaceted_bp.route('/specs/<spec_sc>/sync-to-form', methods=['POST'])
@module_access_required('spec_formulate')
def sync_to_form(spec_sc):
    """
    將 spec 的 formio facet 同步回關聯的表單模板

    以 spec fields 產生新的 FormIO schema，覆蓋表單模板的 schema。
    保留表單模板原有的非欄位設定（如 display、settings 等）。
    """
    from modules.spec_formulate.models import FwSpecMultifaceted
    from modules.form_workflow.models import FwFormTemplate
    from modules.spec_formulate.services.multifaceted.formio_generator import (
        multifaceted_to_formio_schema,
    )

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': '無法取得企業資訊'}), 403

    spec = FwSpecMultifaceted.query.filter_by(
        secure_code=spec_sc,
        org_secure_code=org.secure_code,
        is_deleted=False,
    ).first()
    if not spec:
        return jsonify({'success': False, 'error': '規格不存在'}), 404

    if not spec.linked_form_template_sc:
        return jsonify({'success': False, 'error': '此規格尚未關聯表單'}), 400

    template = FwFormTemplate.query.filter_by(
        secure_code=spec.linked_form_template_sc,
        org_secure_code=org.secure_code,
    ).first()
    if not template:
        return jsonify({'success': False, 'error': '關聯的表單模板不存在'}), 404

    # 產生新的 FormIO schema
    new_schema = multifaceted_to_formio_schema(spec.fields or [], form_title=None)

    # 保留原 schema 的非 components 設定
    old_schema = template.schema or {}
    for k, v in old_schema.items():
        if k != 'components':
            new_schema[k] = v

    template.schema = new_schema
    db.session.commit()

    field_count = len(new_schema.get('components', []))
    return jsonify({
        'success': True,
        'message': f'已同步 {field_count} 個欄位回表單「{template.name}」',
        'data': {
            'template_name': template.name,
            'field_count': field_count,
        },
    })


@multifaceted_bp.route('/specs/<spec_sc>/create-form', methods=['POST'])
@module_access_required('spec_formulate')
def create_form(spec_sc):
    """
    從 multifaceted spec 建立新的 FormIO 表單模板

    Body: {
        "name": "表單名稱",
        "code": "FT_CODE",          // 選填，自動產生
        "category_secure_code": ""   // 選填
    }
    """
    from modules.spec_formulate.models import FwSpecMultifaceted
    from modules.form_workflow.models import FwFormTemplate
    from modules.spec_formulate.services.multifaceted.formio_generator import (
        multifaceted_to_formio_schema,
    )

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': '無法取得企業資訊'}), 403

    spec = FwSpecMultifaceted.query.filter_by(
        secure_code=spec_sc,
        org_secure_code=org.secure_code,
        is_deleted=False,
    ).first()
    if not spec:
        return jsonify({'success': False, 'error': '規格不存在'}), 404

    data = request.get_json(silent=True) or {}
    form_name = (data.get('name') or '').strip() or spec.name
    form_code = (data.get('code') or '').strip()
    category_sc = (data.get('category_secure_code') or '').strip() or None

    # 自動產生 code
    if not form_code:
        form_code = f'FT{secrets.token_hex(4).upper()}'

    # 檢查 code 唯一性
    dup = FwFormTemplate.query.filter_by(
        org_secure_code=org.secure_code,
        code=form_code,
        is_deleted=False,
    ).first()
    if dup:
        return jsonify({
            'success': False,
            'error': f'表單代碼 {form_code} 已存在',
        }), 409

    # 確認有 formio facet
    if 'formio' not in (spec.active_facets or []):
        return jsonify({
            'success': False,
            'error': '此規格尚未啟用 FormIO 格式，請先填充 FormIO facet',
        }), 400

    # 產生 FormIO schema
    schema = multifaceted_to_formio_schema(
        spec.fields or [], form_title=form_name
    )

    # 建立 FwFormTemplate
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

    # 關聯到 spec
    spec.linked_form_template_sc = template.secure_code
    db.session.commit()

    return jsonify({
        'success': True,
        'data': {
            'spec': spec.to_dict(),
            'form_template': {
                'secure_code': template.secure_code,
                'name': template.name,
                'code': template.code,
            },
        },
        'message': f'已建立並關聯表單「{form_name}」({form_code})',
    })


# ── PostgreSQL 資料表操作 ──

@multifaceted_bp.route('/pg/ensure-db', methods=['POST'])
@module_access_required('spec_formulate')
def pg_ensure_db():
    """確保企業專屬 DB 存在，回傳 DB 資訊"""
    from modules.spec_formulate.services.multifaceted.pg_table_manager import (
        ensure_org_database,
    )

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': '無法取得企業資訊'}), 403

    try:
        org_db = ensure_org_database(org)
        return jsonify({
            'success': True,
            'data': {
                'db_name': org_db.db_name,
                'is_ready': org_db.is_ready,
            },
        })
    except Exception as e:
        logger.exception('企業 DB 建立失敗')
        return jsonify({'success': False, 'error': f'資料庫建立失敗: {str(e)}'}), 500


@multifaceted_bp.route('/pg/tables', methods=['GET'])
@module_access_required('spec_formulate')
def pg_list_tables():
    """列出企業 DB 中的所有資料表"""
    from modules.spec_formulate.services.multifaceted.pg_table_manager import (
        list_tables,
        ensure_org_database,
    )

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': '無法取得企業資訊'}), 403

    try:
        ensure_org_database(org)
        tables = list_tables(org.secure_code)
        return jsonify({'success': True, 'data': tables})
    except Exception as e:
        logger.exception('列出資料表失敗')
        return jsonify({'success': False, 'error': str(e)}), 500


@multifaceted_bp.route('/pg/tables/<table_name>/introspect', methods=['GET'])
@module_access_required('spec_formulate')
def pg_introspect_table(table_name):
    """讀取資料表結構"""
    from modules.spec_formulate.services.multifaceted.pg_table_manager import (
        introspect_table,
    )

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': '無法取得企業資訊'}), 403

    try:
        columns = introspect_table(org.secure_code, table_name)
        return jsonify({'success': True, 'data': columns})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@multifaceted_bp.route('/specs/<spec_sc>/pg/compare/<table_name>', methods=['GET'])
@module_access_required('spec_formulate')
def pg_compare(spec_sc, table_name):
    """比對 SPEC 與資料表結構"""
    from modules.spec_formulate.models import FwSpecMultifaceted
    from modules.spec_formulate.services.multifaceted.pg_table_manager import (
        introspect_table,
        compare_spec_with_table,
    )

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': '無法取得企業資訊'}), 403

    spec = FwSpecMultifaceted.query.filter_by(
        secure_code=spec_sc,
        org_secure_code=org.secure_code,
        is_deleted=False,
    ).first()
    if not spec:
        return jsonify({'success': False, 'error': '規格不存在'}), 404

    try:
        columns = introspect_table(org.secure_code, table_name)
        diff = compare_spec_with_table(spec.fields, columns)
        return jsonify({'success': True, 'data': diff})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@multifaceted_bp.route('/specs/<spec_sc>/pg/create-table', methods=['POST'])
@module_access_required('spec_formulate')
def pg_create_table(spec_sc):
    """
    從 SPEC 建立資料表

    Body: { "table_name": "spec_xxx" }  // 選填，預設用 spec.table_name
    """
    from modules.spec_formulate.models import FwSpecMultifaceted
    from modules.spec_formulate.services.multifaceted.pg_table_manager import (
        ensure_org_database,
        create_table_from_spec,
    )

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': '無法取得企業資訊'}), 403

    spec = FwSpecMultifaceted.query.filter_by(
        secure_code=spec_sc,
        org_secure_code=org.secure_code,
        is_deleted=False,
    ).first()
    if not spec:
        return jsonify({'success': False, 'error': '規格不存在'}), 404

    if 'postgresql' not in (spec.active_facets or []):
        return jsonify({
            'success': False,
            'error': '此規格尚未啟用 PostgreSQL 格式',
        }), 400

    data = request.get_json(silent=True) or {}
    table_name = (data.get('table_name') or '').strip() or spec.table_name
    if not table_name:
        return jsonify({
            'success': False,
            'error': '請指定資料表名稱',
        }), 400

    # 驗證表名
    import re
    if not re.match(r'^[a-z][a-z0-9_]*$', table_name):
        return jsonify({
            'success': False,
            'error': '資料表名稱只能包含小寫英文、數字和底線，且以英文開頭',
        }), 400

    try:
        ensure_org_database(org)
        result = create_table_from_spec(org.secure_code, table_name, spec.fields)

        if result['success']:
            # 記錄關聯
            spec.linked_sql_table = table_name
            db.session.commit()

        return jsonify({
            'success': result['success'],
            'data': result,
            'message': result['message'],
        })
    except Exception as e:
        logger.exception('建立資料表失敗')
        return jsonify({'success': False, 'error': str(e)}), 500


@multifaceted_bp.route('/specs/<spec_sc>/pg/apply-to-table', methods=['POST'])
@module_access_required('spec_formulate')
def pg_apply_to_table(spec_sc):
    """
    SPEC 覆蓋既有資料表（新增/修改欄位）

    Body: { "table_name": "xxx" }
    """
    from modules.spec_formulate.models import FwSpecMultifaceted
    from modules.spec_formulate.services.multifaceted.pg_table_manager import (
        introspect_table,
        apply_spec_to_table,
    )

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': '無法取得企業資訊'}), 403

    spec = FwSpecMultifaceted.query.filter_by(
        secure_code=spec_sc,
        org_secure_code=org.secure_code,
        is_deleted=False,
    ).first()
    if not spec:
        return jsonify({'success': False, 'error': '規格不存在'}), 404

    data = request.get_json(silent=True) or {}
    table_name = (data.get('table_name') or '').strip()
    if not table_name:
        return jsonify({'success': False, 'error': '請指定資料表名稱'}), 400

    try:
        columns = introspect_table(org.secure_code, table_name)
        result = apply_spec_to_table(
            org.secure_code, table_name, spec.fields, columns
        )

        if result['success']:
            spec.linked_sql_table = table_name
            db.session.commit()

        return jsonify({
            'success': result['success'],
            'data': result,
            'message': result['message'],
        })
    except Exception as e:
        logger.exception('覆蓋資料表失敗')
        return jsonify({'success': False, 'error': str(e)}), 500


@multifaceted_bp.route('/specs/<spec_sc>/pg/unlink-table', methods=['POST'])
@module_access_required('spec_formulate')
def pg_unlink_table(spec_sc):
    """解除資料表關聯"""
    from modules.spec_formulate.models import FwSpecMultifaceted

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': '無法取得企業資訊'}), 403

    spec = FwSpecMultifaceted.query.filter_by(
        secure_code=spec_sc,
        org_secure_code=org.secure_code,
        is_deleted=False,
    ).first()
    if not spec:
        return jsonify({'success': False, 'error': '規格不存在'}), 404

    spec.linked_sql_table = None
    db.session.commit()

    return jsonify({'success': True, 'message': '已解除資料表關聯'})
