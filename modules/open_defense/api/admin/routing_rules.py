"""Admin API:routing rules CRUD + 試算"""
import logging
from datetime import datetime

from flask import jsonify, request
from flask_babel import gettext as _
from flask_login import current_user

from app import db
from app.security.decorators import admin_required
from app.services.capability_service import permission_required
from modules.form_workflow.models import FwFormTemplate

from . import admin_bp
from ...models import OdFormTemplateMapping
from ...schemas.intake import VALID_EVENT_CLASSES, validate_intake_body, IntakeValidationError
from ...services.routing_service import evaluate_routing_rules, validate_match_rules

logger = logging.getLogger(__name__)


def _error(code, message, status=400):
    return jsonify({'error': code, 'message': message}), status


def _normalize_event_class(value):
    if value in (None, ''):
        return None
    return value


def _validate_event_class(event_class):
    if event_class is not None and event_class not in VALID_EVENT_CLASSES:
        return _('event_class 必須為 %(classes)s 之一', classes=VALID_EVENT_CLASSES)
    return None


def _validate_form_template(org_sc, form_template_sc):
    if not form_template_sc:
        return _('form_template_secure_code 必填')
    template = FwFormTemplate.query.filter_by(
        secure_code=form_template_sc,
        org_secure_code=org_sc,
        is_deleted=False,
    ).first()
    if not template:
        return _('form_template_secure_code 不存在或不屬於本企業')
    return None


def _rule_payload(record):
    return record.to_dict()


@admin_bp.route('/routing-rules', methods=['GET'])
@admin_required
@permission_required('open_defense.admin')
def list_routing_rules():
    rows = OdFormTemplateMapping.query.filter_by(
        org_secure_code=current_user.org_secure_code,
        is_deleted=False,
    ).order_by(
        OdFormTemplateMapping.priority.desc(),
        OdFormTemplateMapping.id.asc(),
    ).all()
    return jsonify({'routing_rules': [_rule_payload(r) for r in rows]})


@admin_bp.route('/routing-rules', methods=['POST'])
@admin_required
@permission_required('open_defense.admin')
def create_routing_rule():
    body = request.get_json(force=True, silent=True) or {}
    org_sc = current_user.org_secure_code

    match_rules = body.get('match_rules')
    ok, message = validate_match_rules(match_rules)
    if not ok:
        return _error('invalid_match_rules', message, 400)

    event_class = _normalize_event_class(body.get('event_class'))
    event_error = _validate_event_class(event_class)
    if event_error:
        return _error('invalid_event_class', event_error, 400)

    form_template_sc = (body.get('form_template_secure_code') or '').strip()
    template_error = _validate_form_template(org_sc, form_template_sc)
    if template_error:
        return _error('invalid_form_template', template_error, 400)

    try:
        priority = int(body.get('priority') or 0)
    except (TypeError, ValueError):
        return _error('invalid_priority', _('priority 必須為整數'), 400)

    record = OdFormTemplateMapping(
        org_secure_code=org_sc,
        name=(body.get('name') or '').strip() or None,
        event_class=event_class,
        form_template_secure_code=form_template_sc,
        priority=priority,
        match_rules=match_rules,
        is_active=bool(body.get('is_active', True)),
        note=(body.get('note') or '').strip() or None,
    )
    db.session.add(record)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.exception('create od routing rule failed')
        return _error('save_failed', _('儲存路由規則失敗'), 500)

    return jsonify({'success': True, 'routing_rule': _rule_payload(record)}), 201


@admin_bp.route('/routing-rules/<secure_code>', methods=['PUT'])
@admin_required
@permission_required('open_defense.admin')
def update_routing_rule(secure_code):
    org_sc = current_user.org_secure_code
    record = OdFormTemplateMapping.query.filter_by(
        secure_code=secure_code,
        org_secure_code=org_sc,
        is_deleted=False,
    ).first()
    if not record:
        return _error('not_found', _('路由規則不存在'), 404)

    body = request.get_json(force=True, silent=True) or {}

    if 'match_rules' in body:
        ok, message = validate_match_rules(body.get('match_rules'))
        if not ok:
            return _error('invalid_match_rules', message, 400)

    if 'event_class' in body:
        event_class = _normalize_event_class(body.get('event_class'))
        event_error = _validate_event_class(event_class)
        if event_error:
            return _error('invalid_event_class', event_error, 400)

    if 'form_template_secure_code' in body:
        form_template_sc = (body.get('form_template_secure_code') or '').strip()
        template_error = _validate_form_template(org_sc, form_template_sc)
        if template_error:
            return _error('invalid_form_template', template_error, 400)

    try:
        if 'priority' in body:
            record.priority = int(body.get('priority') or 0)
    except (TypeError, ValueError):
        return _error('invalid_priority', _('priority 必須為整數'), 400)

    if 'name' in body:
        record.name = (body.get('name') or '').strip() or None
    if 'event_class' in body:
        record.event_class = _normalize_event_class(body.get('event_class'))
    if 'form_template_secure_code' in body:
        record.form_template_secure_code = (body.get('form_template_secure_code') or '').strip()
    if 'match_rules' in body:
        record.match_rules = body.get('match_rules')
    if 'is_active' in body:
        record.is_active = bool(body.get('is_active'))
    if 'note' in body:
        record.note = (body.get('note') or '').strip() or None

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.exception('update od routing rule failed secure_code=%s', secure_code)
        return _error('save_failed', _('儲存路由規則失敗'), 500)

    return jsonify({'success': True, 'routing_rule': _rule_payload(record)})


@admin_bp.route('/routing-rules/<secure_code>', methods=['DELETE'])
@admin_required
@permission_required('open_defense.admin')
def delete_routing_rule(secure_code):
    record = OdFormTemplateMapping.query.filter_by(
        secure_code=secure_code,
        org_secure_code=current_user.org_secure_code,
        is_deleted=False,
    ).first()
    if not record:
        return _error('not_found', _('路由規則不存在'), 404)

    record.is_deleted = True
    record.deleted_at = datetime.utcnow()
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.exception('delete od routing rule failed secure_code=%s', secure_code)
        return _error('save_failed', _('刪除路由規則失敗'), 500)

    return jsonify({'success': True})


@admin_bp.route('/routing-rules/test', methods=['POST'])
@admin_required
@permission_required('open_defense.admin')
def test_routing_rule():
    raw_body = request.get_json(force=True, silent=True) or {}
    try:
        event_body = validate_intake_body(raw_body)
    except IntakeValidationError as exc:
        return jsonify({
            'error': 'invalid_event_body',
            'message': _('事件 body 格式不合法'),
            'details': exc.details,
        }), 400

    matched, evaluated = evaluate_routing_rules(
        current_user.org_secure_code,
        event_body,
    )
    matched_payload = None
    if matched:
        matched_payload = {
            'secure_code': matched.secure_code,
            'name': matched.name,
            'form_template_secure_code': matched.form_template_secure_code,
        }

    return jsonify({
        'matched': matched_payload,
        'evaluated': evaluated,
    })
