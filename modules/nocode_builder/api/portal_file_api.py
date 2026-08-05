"""
NoCode Builder Portal File API
平台側 portal 檔案元件管理端點。
"""
from __future__ import annotations

import logging

from flask import jsonify, request
from flask_babel import gettext as _
from flask_login import current_user

from app import csrf, db
from app.models.file_access_log import FileAccessLog
from app.security.client_ip import get_client_ip
from app.security.decorators import admin_required
from app.security.resource_gateway import ResourceGateway
from app.services import file_service
from app.services.capability_service import permission_required

from . import api_bp
from .portal_org_api import _get_owned_sub_system
from ..models import DcPageLayout
from ..services.page_ownership_service import get_owner_sub_system_codes
from ..services import portal_file_service as portal_files

logger = logging.getLogger(__name__)


def _message(message, status):
    return jsonify({'success': False, 'message': message}), status


def _portal_db_not_found_message():
    return _message(_('子系統 portal.db 不存在，請先初始化 Portal'), 400)


def _file_payload(row: dict) -> dict:
    return {
        'secure_code': row.get('secure_code'),
        'original_name': row.get('original_name'),
        'file_size': row.get('file_size'),
        'file_ext': row.get('file_ext'),
        'uploader_ref': row.get('uploader_ref'),
        'created_at': row.get('created_at'),
    }


def _get_page_file_box(ss_sc, page_sc, widget_id):
    page_sc = (page_sc or '').strip()
    widget_id = (widget_id or '').strip()
    if not page_sc or not widget_id:
        return None, None, _message(_('page_sc 與 widget_id 為必填'), 400)

    if ss_sc not in get_owner_sub_system_codes(page_sc):
        return None, None, _message(_('資源不存在'), 404)

    page = ResourceGateway.get(
        DcPageLayout,
        page_sc,
        raise_on_not_found=False,
        check_permission=False,
    )
    if not page or page.is_deleted:
        return None, None, _message(_('資源不存在'), 404)

    widget = portal_files.find_file_box_widget(page.layout_json, widget_id)
    if not widget:
        return None, None, _message(_('資源不存在'), 404)
    return page, widget, None


def _preflight_sub_system(ss_sc):
    sub_system = _get_owned_sub_system(ss_sc)
    if not sub_system:
        return None, _message(_('資源不存在'), 404)
    return sub_system, None


def _audit_file(record, action, sub_system):
    try:
        log = FileAccessLog(
            org_secure_code=sub_system.org_secure_code,
            file_secure_code=record.secure_code,
            original_name=record.original_name,
            context_type=record.context_type,
            context_id=record.context_id,
            action=action,
            user_secure_code=current_user.secure_code,
            username=current_user.display_name or current_user.username,
            ip_address=get_client_ip(),
        )
        db.session.add(log)
        db.session.commit()
    except Exception as exc:
        logger.warning("portal_file 稽核寫入失敗: %s", exc)
        try:
            db.session.rollback()
        except Exception:
            pass


@api_bp.route("/sub-systems/<ss_sc>/portal-files", methods=["POST"])
@csrf.exempt
@admin_required
@permission_required("nocode_builder.manage")
def upload_portal_file(ss_sc):
    sub_system, error = _preflight_sub_system(ss_sc)
    if error:
        return error

    page_sc = (request.form.get('page_sc') or '').strip()
    widget_id = (request.form.get('widget_id') or '').strip()
    page, widget, error = _get_page_file_box(ss_sc, page_sc, widget_id)
    if error:
        return error

    if 'file' not in request.files:
        return _message(_('未提供檔案'), 400)

    setting = portal_files.widget_setting(widget)
    if setting['upload_by'] != 'designer':
        return _message(_('此元件不允許設計者上傳'), 400)

    upload = request.files['file']
    ext = ''
    if upload.filename and '.' in upload.filename:
        ext = upload.filename.rsplit('.', 1)[1].lower()
    if ext not in file_service.CONTEXT_ALLOWED_EXT['portal_file']:
        return _message(_('不支援的檔案格式'), 400)
    if setting['allowed_ext'] and ext not in setting['allowed_ext']:
        return _message(_('不支援的檔案格式'), 400)

    uploader_ref = f'{portal_files.DESIGNER_REF_PREFIX}{current_user.secure_code}'
    limit = setting['max_files']
    try:
        if portal_files.count_uploader_files(ss_sc, page_sc, widget_id, uploader_ref) >= limit:
            return _message(_('已達此元件的上傳上限（%(limit)s 個檔案）', limit=limit), 400)
    except FileNotFoundError:
        return _portal_db_not_found_message()

    try:
        record = file_service.upload_file(
            org_sc=sub_system.org_secure_code,
            file=upload,
            context_type='portal_file',
            context_id=page.secure_code,
            uploader_sc=current_user.secure_code,
        )
        db.session.commit()
    except ValueError as exc:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(exc)}), 400
    except Exception:
        db.session.rollback()
        logger.exception("portal_file 上傳失敗")
        return _message(_('檔案上傳失敗'), 500)

    try:
        row = portal_files.create_file_record(
            ss_sc,
            platform_file_sc=record.secure_code,
            page_sc=page.secure_code,
            widget_id=widget_id,
            uploader_ref=uploader_ref,
            original_name=record.original_name,
            file_size=record.file_size,
            file_ext=record.file_ext,
        )
    except FileNotFoundError:
        file_service.delete_file(record)
        db.session.commit()
        return _portal_db_not_found_message()
    except Exception:
        logger.exception("portal_file SQLite 對照列寫入失敗，回收 platform_files: %s", record.secure_code)
        try:
            file_service.delete_file(record)
            db.session.commit()
        except Exception:
            db.session.rollback()
            logger.exception("portal_file 補償刪除失敗，可能產生孤兒檔: %s", record.secure_code)
        return jsonify({'success': False, 'message': _('檔案登錄失敗')}), 500

    _audit_file(record, 'upload', sub_system)
    return jsonify({'success': True, 'data': _file_payload(row), 'message': _('已儲存')}), 201


@api_bp.route("/sub-systems/<ss_sc>/portal-files", methods=["GET"])
@csrf.exempt
@admin_required
@permission_required("nocode_builder.manage")
def list_portal_files(ss_sc):
    sub_system, error = _preflight_sub_system(ss_sc)
    if error:
        return error

    page_sc = (request.args.get('page') or '').strip()
    widget_id = (request.args.get('widget') or '').strip()
    _page, widget, error = _get_page_file_box(ss_sc, page_sc, widget_id)
    if error:
        return error

    try:
        rows = portal_files.list_widget_files(ss_sc, page_sc, widget_id)
        include_acl = portal_files.widget_setting(widget)['per_file_acl']
        data = []
        for row in rows:
            item = _file_payload(row)
            if include_acl:
                item['acl'] = portal_files.list_file_acl(ss_sc, row['secure_code'])
            data.append(item)
    except FileNotFoundError:
        return _portal_db_not_found_message()

    return jsonify({'success': True, 'data': {'files': data}, 'message': _('已取得')})


@api_bp.route("/sub-systems/<ss_sc>/portal-files/<file_sc>", methods=["DELETE"])
@csrf.exempt
@admin_required
@permission_required("nocode_builder.manage")
def delete_portal_file(ss_sc, file_sc):
    sub_system, error = _preflight_sub_system(ss_sc)
    if error:
        return error

    try:
        row = portal_files.get_file(ss_sc, file_sc)
    except FileNotFoundError:
        return _portal_db_not_found_message()
    if not row:
        return _message(_('資源不存在'), 404)

    try:
        if not portal_files.soft_delete_file(ss_sc, file_sc):
            return _message(_('檔案刪除失敗'), 500)
    except FileNotFoundError:
        return _portal_db_not_found_message()
    except Exception:
        logger.exception("portal_file SQLite 軟刪失敗: %s", file_sc)
        return _message(_('檔案刪除失敗'), 500)

    try:
        record = file_service.get_file_by_sc(
            row['platform_file_sc'],
            org_sc=sub_system.org_secure_code,
        )
        if record:
            file_service.delete_file(record)
            db.session.commit()
            _audit_file(record, 'delete', sub_system)
    except Exception:
        db.session.rollback()
        logger.exception("portal_file platform_files 刪除失敗: %s", row.get('platform_file_sc'))
        return _message(_('檔案刪除失敗'), 500)

    return jsonify({'success': True, 'data': {'secure_code': file_sc}, 'message': _('已刪除')})


@api_bp.route("/sub-systems/<ss_sc>/portal-files/<file_sc>/acl", methods=["PUT"])
@csrf.exempt
@admin_required
@permission_required("nocode_builder.manage")
def update_portal_file_acl(ss_sc, file_sc):
    sub_system, error = _preflight_sub_system(ss_sc)
    if error:
        return error

    try:
        row = portal_files.get_file(ss_sc, file_sc)
    except FileNotFoundError:
        return _portal_db_not_found_message()
    if not row:
        return _message(_('資源不存在'), 404)

    _page, widget, error = _get_page_file_box(ss_sc, row['page_sc'], row['widget_id'])
    if error:
        return error
    if not portal_files.widget_setting(widget)['per_file_acl']:
        return _message(_('此元件未啟用個別檔案授權'), 400)

    data = request.get_json() or {}
    entries = data.get('entries')
    if not isinstance(entries, list):
        return _message(_('entries 必須是陣列'), 400)

    normalized = []
    seen = set()
    for entry in entries:
        if not isinstance(entry, dict):
            return _message(_('授權項目格式不正確'), 400)
        grantee_type = (entry.get('grantee_type') or '').strip()
        grantee_code = (entry.get('grantee_code') or '').strip()
        if grantee_type not in {'user', 'role'}:
            return _message(_('授權類型不正確'), 400)
        if not grantee_code:
            return _message(_('授權對象為必填'), 400)
        key = (grantee_type, grantee_code)
        if key in seen:
            continue
        seen.add(key)
        normalized.append({'grantee_type': grantee_type, 'grantee_code': grantee_code})

    try:
        ok, missing = portal_files.acl_grantees_exist(ss_sc, normalized)
        if not ok:
            return _message(_('授權對象不存在：%(code)s', code=missing), 400)
        acl = portal_files.set_file_acl(ss_sc, file_sc, normalized)
    except FileNotFoundError:
        return _portal_db_not_found_message()

    return jsonify({'success': True, 'data': {'acl': acl}, 'message': _('已儲存')})
