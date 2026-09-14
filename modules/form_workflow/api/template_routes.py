"""
FormWorkflow Module - Template API Routes
表單模板 API

提供表單模板的 CRUD 與批次操作。
"""
import secrets
from datetime import datetime, timezone
from flask import jsonify, request

from app import csrf, db
from app.security.decorators import module_access_required, page_keys_required
from app.platform.auth import current_user, require_permission
from app.platform.data import get_current_org

from . import api_bp
from flask_babel import gettext as _


@api_bp.route('/templates')
@module_access_required('form_workflow')
@require_permission('form_workflow.template.view')
def list_templates():
    """取得表單模板列表"""
    from ..models import FwFormTemplate, FwFormWorkflowMapping

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

    # 查詢已配對的表單 ID 集合
    mapped_form_ids = set(
        r[0] for r in db.session.query(FwFormWorkflowMapping.form_template_id).filter_by(
            org_secure_code=org.secure_code, is_deleted=False
        ).all()
    )

    result = []
    for t in templates:
        d = t.to_dict(include_schema=False)
        d['is_mapped'] = t.id in mapped_form_ids
        result.append(d)

    return jsonify({
        'success': True,
        'data': {
            'templates': result
        }
    })


@api_bp.route('/templates/<secure_code>')
@module_access_required('form_workflow')
@require_permission('form_workflow.template.view')
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

    return jsonify({
        'success': True,
        'data': template.to_dict(include_schema=True)
    })


@api_bp.route('/templates', methods=['POST'])
@csrf.exempt
@module_access_required('form_workflow')
@require_permission('form_workflow.template.create')
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

    # 若未提供 schema，建立含表單標題的預設結構
    schema = data.get('schema') or {
        'components': [
            {
                'type': 'htmlelement',
                'tag': 'h3',
                'attrs': [{'attr': 'style', 'value': 'text-align:center; margin:0 0 0.5rem 0;'}],
                'content': name,
                'key': 'formTitle',
                'input': False,
                'tableView': False
            },
        ]
    }

    template = FwFormTemplate(
        secure_code=secrets.token_urlsafe(16),
        org_secure_code=org.secure_code,
        name=name,
        code=code,
        description=data.get('description', ''),
        category=data.get('category', '其他'),
        category_secure_code=data.get('category_secure_code') or 'SYS_CAT_WORKFLOW_REC',
        schema=schema,
        is_active=data.get('is_active', True)
    )

    db.session.add(template)
    db.session.commit()

    return jsonify({
        'success': True,
        'data': template.to_dict(include_schema=True),
        'message': _('表單模板已建立')
    })


@api_bp.route('/templates/<secure_code>', methods=['PUT'])
@csrf.exempt
@module_access_required('form_workflow')
@require_permission('form_workflow.template.edit')
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
    if 'category_secure_code' in data:
        template.category_secure_code = data['category_secure_code']
    if 'category' in data:
        template.category = data['category']
    if 'schema' in data:
        template.schema = data['schema']
    if 'is_active' in data:
        template.is_active = data['is_active']

    # 縮圖
    if 'thumbnail_2x1' in data:
        template.thumbnail_2x1 = data['thumbnail_2x1']

    db.session.commit()

    return jsonify({
        'success': True,
        'data': template.to_dict(include_schema=True),
        'message': _('表單模板已更新')
    })


@api_bp.route('/templates/batch/delete', methods=['POST'])
@csrf.exempt
@module_access_required('form_workflow')
@page_keys_required('form_workflow.templates')
@require_permission('form_workflow.template.delete')
def batch_delete_templates():
    """批次刪除表單模板（軟刪除）"""
    from ..models import FwFormTemplate

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    data = request.get_json() or {}
    secure_codes = data.get('secure_codes', [])
    if not secure_codes:
        return jsonify({'success': False, 'error': 'secure_codes is required'}), 400

    results = []
    succeeded = 0
    for sc in secure_codes:
        tpl = FwFormTemplate.query.filter_by(
            secure_code=sc, org_secure_code=org.secure_code, is_deleted=False
        ).first()
        if not tpl:
            results.append({'secure_code': sc, 'success': False, 'message': _('找不到表單')})
            continue
        tpl.is_deleted = True
        results.append({'secure_code': sc, 'success': True, 'message': _('已刪除')})
        succeeded += 1

    db.session.commit()
    return jsonify({
        'success': True,
        'results': results,
        'summary': {'total': len(secure_codes), 'succeeded': succeeded, 'failed': len(secure_codes) - succeeded}
    })


@api_bp.route('/templates/batch/export', methods=['POST'])
@csrf.exempt
@module_access_required('form_workflow')
@page_keys_required('form_workflow.templates')
@require_permission('form_workflow.template.view')
def batch_export_templates():
    """批次匯出表單模板（JSON）"""
    from ..models import FwFormTemplate

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    data = request.get_json() or {}
    secure_codes = data.get('secure_codes', [])
    if not secure_codes:
        return jsonify({'success': False, 'error': 'secure_codes is required'}), 400

    items = []
    for sc in secure_codes:
        tpl = FwFormTemplate.query.filter_by(
            secure_code=sc, org_secure_code=org.secure_code, is_deleted=False
        ).first()
        if not tpl:
            continue
        items.append({
            'code': tpl.code,
            'name': tpl.name,
            'description': tpl.description,
            'category': tpl.category,
            'category_secure_code': tpl.category_secure_code,
            'version': tpl.version,
            'schema': tpl.schema,
            'builder_config': tpl.builder_config,
        })

    return jsonify({
        'success': True,
        'data': {
            'export_type': 'forms',
            'exported_at': datetime.now(timezone.utc).isoformat(),
            'count': len(items),
            'items': items,
        }
    })


@api_bp.route('/templates/batch/import', methods=['POST'])
@csrf.exempt
@module_access_required('form_workflow')
@page_keys_required('form_workflow.templates')
@require_permission('form_workflow.template.create')
def batch_import_templates():
    """批次匯入表單模板（JSON）

    讀取 export 格式的 JSON，逐筆建立 FwFormTemplate。
    code 重複則跳過。category_secure_code 不存在則歸預設。
    """
    from ..models import FwFormTemplate

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    data = request.get_json() or {}

    # 防呆：檢查 export_type
    export_type = data.get('export_type', '')
    if export_type and export_type != 'forms':
        return jsonify({'success': False, 'error': _('檔案類型不符：期望 forms，實際為 %(export_type)s', export_type=export_type)}), 400

    items = data.get('items', [])
    if not items:
        return jsonify({'success': False, 'error': 'items is required'}), 400

    # 預載現有 code 集合（用於去重）
    existing_codes = set(
        r[0] for r in db.session.query(FwFormTemplate.code).filter_by(
            org_secure_code=org.secure_code, is_deleted=False
        ).all()
    )

    # 預載有效 category_secure_code 集合
    from ..models import FwCategory
    valid_cats = set(
        r[0] for r in db.session.query(FwCategory.secure_code).filter_by(
            org_secure_code=org.secure_code, is_deleted=False
        ).all()
    )

    default_cat_code = 'SYS_CAT_WORKFLOW_REC'

    results = []
    created = 0
    skipped = 0

    for item in items:
        code = (item.get('code') or '').strip()
        if not code:
            results.append({'code': code, 'status': 'skipped', 'reason': '缺少 code'})
            skipped += 1
            continue

        # 防呆：表單 code 必須以 FT 或 FORM_ 開頭
        code_upper = code.upper()
        if not (code_upper.startswith('FT') or code_upper.startswith('FORM_')):
            results.append({'code': code, 'status': 'skipped', 'reason': 'code 格式不符（需 FT 或 FORM_ 開頭）'})
            skipped += 1
            continue

        if code in existing_codes:
            results.append({'code': code, 'status': 'skipped', 'reason': 'code 已存在'})
            skipped += 1
            continue

        cat_code = item.get('category_secure_code') or default_cat_code
        if cat_code not in valid_cats:
            cat_code = default_cat_code

        tpl = FwFormTemplate(
            secure_code=secrets.token_urlsafe(16),
            org_secure_code=org.secure_code,
            code=code,
            name=item.get('name', code),
            description=item.get('description', ''),
            category=item.get('category', ''),
            category_secure_code=cat_code,
            version=item.get('version', 'AA'),
            revision=1,
            schema=item.get('schema') or {'components': []},
            builder_config=item.get('builder_config'),
            is_active=True,
            owner_secure_code=current_user.secure_code,
        )
        db.session.add(tpl)
        existing_codes.add(code)
        results.append({'code': code, 'status': 'created'})
        created += 1

    db.session.commit()

    return jsonify({
        'success': True,
        'summary': {'total': len(items), 'created': created, 'skipped': skipped},
        'results': results,
    })


@api_bp.route('/templates/batch/save-new-version', methods=['POST'])
@csrf.exempt
@module_access_required('form_workflow')
@page_keys_required('form_workflow.templates')
@require_permission('form_workflow.template.edit')
def batch_save_new_version_templates():
    """批次另存新版表單模板（複製出新記錄，版本號遞增）"""
    from ..models import FwFormTemplate

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    data = request.get_json() or {}
    secure_codes = data.get('secure_codes', [])
    if not secure_codes:
        return jsonify({'success': False, 'error': 'secure_codes is required'}), 400

    results = []
    succeeded = 0
    for sc in secure_codes:
        tpl = FwFormTemplate.query.filter_by(
            secure_code=sc, org_secure_code=org.secure_code, is_deleted=False
        ).first()
        if not tpl:
            results.append({'secure_code': sc, 'success': False, 'message': _('找不到表單')})
            continue
        current_version = tpl.version or 'AA'
        if len(current_version) >= 2:
            first, second = current_version[0], current_version[1]
            new_version = (chr(ord(first) + 1) + 'A') if second == 'Z' else (first + chr(ord(second) + 1))
        else:
            new_version = 'AA'
        new_tpl = FwFormTemplate(
            secure_code=secrets.token_urlsafe(16),
            org_secure_code=tpl.org_secure_code,
            code=f'FT{secrets.token_hex(4).upper()}',
            name=tpl.name,
            description=tpl.description,
            category=tpl.category,
            category_secure_code=tpl.category_secure_code,
            schema=tpl.schema,
            builder_config=tpl.builder_config,
            version=new_version,
            revision=1,
            thumbnail_2x1=tpl.thumbnail_2x1,
            is_active=tpl.is_active,
            owner_secure_code=current_user.secure_code,
        )
        db.session.add(new_tpl)
        results.append({'secure_code': sc, 'success': True, 'message': _('已另存為版本 %(version)s', version=new_version), 'new_secure_code': new_tpl.secure_code})
        succeeded += 1

    db.session.commit()
    return jsonify({
        'success': True,
        'results': results,
        'summary': {'total': len(secure_codes), 'succeeded': succeeded, 'failed': len(secure_codes) - succeeded}
    })


@api_bp.route('/templates/<secure_code>', methods=['DELETE'])
@csrf.exempt
@module_access_required('form_workflow')
@require_permission('form_workflow.template.delete')
def delete_template(secure_code):
    """
    刪除表單模板（軟刪除）

    Query Parameters:
        check: 若為 1，只回傳配對資訊不刪除（前端預檢用）
    """
    from ..models import FwFormTemplate, FwFormWorkflowMapping, FwWorkflowTemplate

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

    # 查詢關聯的配對
    mappings = FwFormWorkflowMapping.query.filter_by(
        form_template_id=template.id,
        is_deleted=False
    ).all()

    # 預檢模式：回傳配對資訊
    if request.args.get('check') == '1':
        mapping_info = []
        if mappings:
            wf_ids = [m.workflow_template_id for m in mappings]
            wf_map = {}
            if wf_ids:
                wfs = FwWorkflowTemplate.query.filter(FwWorkflowTemplate.id.in_(wf_ids)).all()
                wf_map = {w.id: w.name for w in wfs}
            for m in mappings:
                mapping_info.append({
                    'workflow_name': wf_map.get(m.workflow_template_id, '未知流程'),
                    'is_published': m.is_published,
                })
        return jsonify({
            'success': True,
            'has_mappings': len(mappings) > 0,
            'mappings': mapping_info,
        })

    template.is_deleted = True
    db.session.commit()

    return jsonify({
        'success': True,
        'message': _('表單模板已刪除')
    })
