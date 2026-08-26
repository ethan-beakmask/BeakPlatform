"""
FormWorkflow Module - External Trigger API(外部發動閘道)

平台級 API Key(HMAC 簽章)發動一般表單:
  POST /api/trigger/form    送出表單並啟動流程
  GET  /api/trigger/forms   列出該 key scope 內可發動的表單

規格: dev-notes/API_KEY_TRIGGER_SPEC.md §3
scope 解釋(本模組負責):
  scopes.form_category : FwCategory SC 清單,父分類自動含子分類
  scopes.form          : published SC 直綁(例外用法)
"""
import logging

from flask import Blueprint, jsonify, request, g
from flask_babel import gettext as _

from app import db, limiter
from app.security.decorators import api_key_hmac_required
from app.security.rate_limiter import (
    key_func_from_api_key, auth_failure_limit_kwargs,
)

logger = logging.getLogger(__name__)

external_trigger_bp = Blueprint(
    'form_workflow_external_trigger',
    __name__,
    url_prefix='/api/trigger'
)

SOURCE_TYPE = 'API_KEY'


def _resolve_scope_filter(api_key):
    """取出 key 的表單授權範圍,回傳 (category_scs: set, form_scs: set)"""
    scopes = api_key.scopes or {}
    category_scs = set(scopes.get('form_category') or [])
    form_scs = set(scopes.get('form') or [])
    return category_scs, form_scs


def _published_in_scope(published, category_scs, form_scs):
    """判斷 published 表單是否在 key 的授權範圍內(父分類含子分類)"""
    if published.secure_code in form_scs:
        return True
    if not category_scs:
        return False

    from ..models import FwFormTemplate, FwCategory
    form_template = FwFormTemplate.query.filter_by(
        secure_code=published.source_form_template_secure_code,
        is_deleted=False
    ).first()
    if not form_template or not form_template.category_secure_code:
        return False

    cat_sc = form_template.category_secure_code
    if cat_sc in category_scs:
        return True

    # 父分類授權涵蓋子分類
    category = FwCategory.query.filter_by(
        secure_code=cat_sc, is_deleted=False
    ).first()
    if category and category.parent_secure_code:
        return category.parent_secure_code in category_scs
    return False


def _resolve_applicant(api_key):
    """
    解析 key 綁定的申請人。

    Returns:
        dict(applicant_* 欄位) -- 未綁定時申請人僅記 consumer_label
    Raises:
        ValueError -- 綁定的帳號不存在/停用/已刪(DATA-01),屬設定錯誤
    """
    fallback_name = api_key.consumer_label or api_key.name or 'API Key'
    if not api_key.applicant_user_secure_code:
        return {
            'applicant_secure_code': None,
            'applicant_name': fallback_name,
            'applicant_username': None,
            'applicant_email': None,
            'applicant_dept': None,
        }

    from app.models import User
    user = User.query.filter_by(
        secure_code=api_key.applicant_user_secure_code,
        org_secure_code=api_key.org_secure_code,
        is_deleted=False,
        is_active=True,
    ).first()
    if not user:
        raise ValueError(_('API Key 綁定的系統帳號不存在或已停用'))

    return {
        'applicant_secure_code': user.secure_code,
        'applicant_name': user.display_name or user.username,
        'applicant_username': user.username,
        'applicant_email': getattr(user, 'email', None),
        'applicant_dept': getattr(user, 'department_name', None),
    }


def _template_category_in_scope(template, category_scs):
    """未發行時只能靠 template 的分類判 scope(父分類含子分類)。"""
    from ..models import FwCategory

    cat_sc = template.category_secure_code
    if not cat_sc or not category_scs:
        return False
    if cat_sc in category_scs:
        return True
    category = FwCategory.query.filter_by(
        secure_code=cat_sc, is_deleted=False
    ).first()
    return bool(category and category.parent_secure_code
                and category.parent_secure_code in category_scs)


def _resolve_published_by_form_code(form_code, org_secure_code, category_scs):
    """以穩定 form template code 解析最新 Published 快照。"""
    from ..models import FwFormTemplate, FwPublishedFormWorkflow

    not_found = ({'success': False, 'error': 'form_not_found'}, 404)

    templates = FwFormTemplate.query.filter_by(
        code=form_code,
        org_secure_code=org_secure_code,
        is_deleted=False,
    ).all()
    if not templates:
        return None, not_found

    template_scs = [template.secure_code for template in templates]
    published = FwPublishedFormWorkflow.query.filter(
        FwPublishedFormWorkflow.source_form_template_secure_code.in_(template_scs),
        FwPublishedFormWorkflow.org_secure_code == org_secure_code,
        FwPublishedFormWorkflow.status == 'Published',
        FwPublishedFormWorkflow.is_deleted == False,  # noqa: E712
    ).order_by(FwPublishedFormWorkflow.created_at.desc()).first()
    if published:
        return published, None

    has_any_version = FwPublishedFormWorkflow.query.filter(
        FwPublishedFormWorkflow.source_form_template_secure_code.in_(template_scs),
        FwPublishedFormWorkflow.org_secure_code == org_secure_code,
        FwPublishedFormWorkflow.is_deleted == False,  # noqa: E712
    ).first() is not None

    # 未發行時無法用 published 判 scope,改判 template 分類;
    # 不在 scope 的一律 404,避免洩漏「這個 code 在本企業存在但沒發行」
    if not any(_template_category_in_scope(t, category_scs) for t in templates):
        return None, not_found

    if has_any_version:
        message = _('表單已有發行記錄，但目前沒有 Published 版本')
    else:
        message = _('表單尚未發行')

    return None, ({
        'success': False,
        'error': 'form_not_published',
        'message': message,
    }, 422)


@external_trigger_bp.route('/form', methods=['POST'])
@limiter.limit('100 per minute; 5000 per hour', key_func=key_func_from_api_key)
@limiter.limit(**auth_failure_limit_kwargs())
@api_key_hmac_required
def trigger_form():
    """外部發動表單:建立實例 + 啟動流程(僅正式模式)"""
    from ..models import FwPublishedFormWorkflow
    from ..services.form_submit_service import (
        allocate_serial_number, create_instance_and_start,
        extract_schema_field_keys, SubmitError,
    )

    api_key = g.api_key
    org_sc = g.api_key_org

    try:
        data = request.get_json(force=True, silent=False) or {}
    except Exception:
        return jsonify({'success': False, 'error': 'invalid_json'}), 400

    published_secure_code = (data.get('published_secure_code') or '').strip()
    form_code = (data.get('form_code') or '').strip()
    subject = (data.get('subject') or '').strip()
    form_data = data.get('form_data') or {}

    if not published_secure_code and not form_code:
        return jsonify({'success': False, 'error': 'missing_form_identifier'}), 400
    if not subject:
        return jsonify({'success': False, 'error': 'missing_subject'}), 400
    if not isinstance(form_data, dict):
        return jsonify({'success': False, 'error': 'form_data_must_be_object'}), 400

    category_scs, form_scs = _resolve_scope_filter(api_key)

    if published_secure_code:
        # 租戶隔離:published 必須屬 key 的企業
        published = FwPublishedFormWorkflow.query.filter_by(
            secure_code=published_secure_code,
            org_secure_code=org_sc,
            is_deleted=False
        ).first()
        if not published:
            return jsonify({'success': False, 'error': 'form_not_found'}), 404
        if published.status != 'Published':
            return jsonify({'success': False, 'error': 'form_not_published'}), 422
    else:
        published, error_response = _resolve_published_by_form_code(
            form_code, org_sc, category_scs
        )
        if error_response:
            body, status = error_response
            return jsonify(body), status

    # scope 授權
    if not _published_in_scope(published, category_scs, form_scs):
        logger.warning(
            'external_trigger: scope denied key_id=%s published=%s',
            api_key.key_id, published.secure_code,
        )
        if not published_secure_code and form_code:
            return jsonify({'success': False, 'error': 'form_not_found'}), 404
        return jsonify({'success': False, 'error': 'scope_denied'}), 403

    # 從快照取得表單和流程定義
    form_snapshot = published.form_snapshot or {}
    workflow_snapshot = published.workflow_snapshot or {}
    form_schema = form_snapshot.get('schema')
    workflow_graph = (workflow_snapshot.get('graph')
                      or workflow_snapshot.get('cytoscape_config') or {})

    # form_data 白名單驗證:僅允許 schema 中 input=true 的欄位 key
    allowed_keys = extract_schema_field_keys(form_schema)
    unknown = sorted(set(form_data.keys()) - allowed_keys)
    if unknown:
        return jsonify({
            'success': False,
            'error': 'unknown_field',
            'details': {'unknown_keys': unknown,
                        'allowed_keys': sorted(allowed_keys)},
        }), 400

    # 申請人(key 綁定的系統帳號)
    try:
        applicant = _resolve_applicant(api_key)
    except ValueError as exc:
        return jsonify({'success': False, 'error': 'applicant_invalid',
                        'message': str(exc)}), 422

    try:
        published.mark_as_used()

        serial_number, org_form_seq = allocate_serial_number(
            org_sc, is_test=False, published=published,
        )
        form_instance, workflow_instance = create_instance_and_start(
            org_secure_code=org_sc,
            serial_number=serial_number,
            org_form_seq=org_form_seq,
            subject=subject,
            form_data=form_data,
            is_test=False,
            source_type=SOURCE_TYPE,
            source_ip=request.remote_addr,
            source_api_key=api_key.key_id,
            form_name=form_snapshot.get('name'),
            form_code=form_snapshot.get('code'),
            form_version=published.source_form_version,
            form_schema=form_schema,
            form_builder_config=form_snapshot.get('builder_config'),
            workflow_name=workflow_snapshot.get('name'),
            workflow_version=published.source_workflow_version,
            workflow_graph=workflow_graph,
            source_form_template_id=published.source_form_template_id,
            source_form_template_secure_code=published.source_form_template_secure_code,
            source_workflow_template_id=published.source_workflow_template_id,
            source_workflow_template_secure_code=published.source_workflow_template_secure_code,
            published_sc=published.secure_code,
            proc_prefix='PROC-',
            **applicant,
        )
    except SubmitError as exc:
        return jsonify({'success': False, 'error': 'workflow_error',
                        'message': str(exc)}), 422
    except Exception as exc:
        db.session.rollback()
        logger.exception('external_trigger: submit failed key_id=%s',
                         api_key.key_id)
        return jsonify({'success': False, 'error': 'internal_error'}), 500

    logger.info(
        'external_trigger: form submitted key_id=%s org=%s serial=%s exec=%s',
        api_key.key_id, org_sc, form_instance.serial_number,
        workflow_instance.execution_code,
    )
    return jsonify({
        'success': True,
        'message': _('表單已送出，流程已啟動'),
        'data': {
            'form_instance_secure_code': form_instance.secure_code,
            'serial_number': form_instance.serial_number,
            'workflow_instance_secure_code': workflow_instance.secure_code,
            'execution_code': workflow_instance.execution_code,
        }
    }), 201


@external_trigger_bp.route('/forms', methods=['GET'])
@limiter.limit('60 per minute', key_func=key_func_from_api_key)
@limiter.limit(**auth_failure_limit_kwargs())
@api_key_hmac_required
def list_triggerable_forms():
    """列出該 key scope 內可發動的 published 表單(含欄位 key,供整合對接)"""
    from ..models import FwPublishedFormWorkflow
    from ..services.form_submit_service import extract_schema_field_keys

    api_key = g.api_key
    category_scs, form_scs = _resolve_scope_filter(api_key)

    published_list = FwPublishedFormWorkflow.query.filter_by(
        org_secure_code=g.api_key_org,
        status='Published',
        is_deleted=False,
    ).all()

    items = []
    for pub in published_list:
        if not _published_in_scope(pub, category_scs, form_scs):
            continue
        form_snapshot = pub.form_snapshot or {}
        items.append({
            'published_secure_code': pub.secure_code,
            'name': form_snapshot.get('name'),
            'code': form_snapshot.get('code'),
            'form_code': form_snapshot.get('code'),
            'version': pub.source_form_version,
            'field_keys': sorted(extract_schema_field_keys(
                form_snapshot.get('schema'))),
        })

    return jsonify({'success': True, 'data': items}), 200
