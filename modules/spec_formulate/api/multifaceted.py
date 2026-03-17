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
