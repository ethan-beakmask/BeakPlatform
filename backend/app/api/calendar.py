"""企業行事曆 API。"""
import logging
from datetime import datetime

from flask import Blueprint, jsonify, request, url_for
from flask_babel import gettext as _
from flask_login import current_user

from app import db
from app.security.decorators import admin_required, page_keys_required
from app.services.calendar_event_service import CalendarEventError, CalendarEventService
from app.services.calendar_projection_service import CalendarProjectionService
from app.services.time_context_service import TimeContextService
from app.utils.calendar_time import local_naive_to_utc

logger = logging.getLogger(__name__)

api_calendar = Blueprint('api_calendar', __name__, url_prefix='/api/calendar')


@api_calendar.route('/org/events', methods=['GET'])
@page_keys_required('calendar')
def org_events():
    return _events('org')


@api_calendar.route('/me/events', methods=['GET'])
@page_keys_required('calendar_me')
def me_events():
    return _events('me')


@api_calendar.route('/events', methods=['POST'])
@page_keys_required('calendar_me')
def create_event():
    payload = request.get_json(silent=True)
    if payload is None:
        return jsonify({'success': False, 'error': 'validation', 'message': _('請求格式錯誤')}), 400
    try:
        row = CalendarEventService.create(current_user.organization, current_user, payload)
        hint = _proxy_hint(row)
        db.session.commit()
        return jsonify({'success': True, 'event': row.to_dict(), 'proxy_hint': hint}), 201
    except CalendarEventError as exc:
        db.session.rollback()
        return jsonify({'success': False, 'error': exc.code, 'message': exc.message}), exc.status
    except Exception:
        db.session.rollback()
        logger.exception("Calendar event create failed")
        return jsonify({'success': False, 'error': 'server_error', 'message': _('儲存失敗')}), 500


@api_calendar.route('/events/<secure_code>', methods=['PUT'])
@page_keys_required('calendar_me')
def update_event(secure_code):
    payload = request.get_json(silent=True)
    if payload is None:
        return jsonify({'success': False, 'error': 'validation', 'message': _('請求格式錯誤')}), 400
    try:
        row = CalendarEventService.update(current_user.organization, current_user, secure_code, payload)
        hint = _proxy_hint(row)
        db.session.commit()
        return jsonify({'success': True, 'event': row.to_dict(), 'proxy_hint': hint})
    except CalendarEventError as exc:
        db.session.rollback()
        return jsonify({'success': False, 'error': exc.code, 'message': exc.message}), exc.status
    except Exception:
        db.session.rollback()
        logger.exception("Calendar event update failed")
        return jsonify({'success': False, 'error': 'server_error', 'message': _('儲存失敗')}), 500


@api_calendar.route('/events/<secure_code>', methods=['DELETE'])
@page_keys_required('calendar_me')
def delete_event(secure_code):
    try:
        CalendarEventService.delete(current_user.organization, current_user, secure_code)
        db.session.commit()
        return jsonify({'success': True})
    except CalendarEventError as exc:
        db.session.rollback()
        return jsonify({'success': False, 'error': exc.code, 'message': exc.message}), exc.status
    except Exception:
        db.session.rollback()
        logger.exception("Calendar event delete failed")
        return jsonify({'success': False, 'error': 'server_error', 'message': _('儲存失敗')}), 500


@api_calendar.route('/time-context', methods=['GET'])
@admin_required
def time_context():
    """TimeContext 快照（ORG_ADMIN 專用）。

    `who_on_leave` 會揭露成員「此刻在假中」（含可見性 PRIVATE 的事件），這是給路由與簽核者解析用的
    伺服器端能力，對一般成員開放會繞過行事曆的可見性規則，所以只掛 admin_required、不走雙鑰匙。
    `at` 是企業當地時間 `YYYY-MM-DDTHH:MM`（與行事曆 API 的當地時間慣例一致），省略＝現在。
    """
    org = current_user.organization
    instant = None
    at = (request.args.get('at') or '').strip()
    if at:
        try:
            local_naive = datetime.strptime(at, '%Y-%m-%dT%H:%M')
        except ValueError:
            return jsonify({'success': False, 'error': 'invalid_at', 'message': _('at 參數格式錯誤')}), 400
        instant = local_naive_to_utc(org.get_setting('timezone', 'Asia/Taipei'), local_naive)
    try:
        snapshot = TimeContextService.snapshot(org, instant)
    except Exception:
        logger.exception("TimeContext snapshot failed")
        return jsonify({'success': False, 'error': 'server_error', 'message': _('行事曆載入失敗')}), 500
    return jsonify({'success': True, **snapshot})


def _events(scope: str):
    start, end, error = _parse_range()
    if error:
        return jsonify({'success': False, 'message': error}), 400

    org = current_user.organization
    try:
        result = CalendarProjectionService.build(org, current_user, scope, start, end)
    except ValueError:
        return jsonify({'success': False, 'message': _('日期範圍不合法')}), 400
    except Exception:
        logger.exception("Calendar load failed")
        return jsonify({'success': False, 'message': _('行事曆載入失敗')}), 500

    return jsonify({
        'success': True,
        'scope': scope,
        'timezone': result['timezone'],
        'today': org.local_today().isoformat(),
        'range': result['range'],
        'days': result['days'],
        'events': result['events'],
    })


def _proxy_hint(row):
    hint = CalendarEventService.proxy_hint(current_user.organization, current_user, row)
    if hint is None:
        return None
    if current_user.is_org_admin or current_user.is_employee:
        hint['create_url'] = url_for(
            'main.personal_settings',
            proxy='new',
            effective_from=hint['start_date'],
            effective_until=hint['end_date'],
            reason=row.title,
            next=url_for('calendar_web.my_calendar'),
            _anchor='my-proxy-assignments',
        )
    else:
        hint['create_url'] = None
    return hint


def _parse_range():
    start_str = request.args.get('start')
    end_str = request.args.get('end')
    if not start_str or not end_str:
        return None, None, _('請提供 start 與 end')
    try:
        start = datetime.strptime(start_str, '%Y-%m-%d').date()
        end = datetime.strptime(end_str, '%Y-%m-%d').date()
    except ValueError:
        return None, None, _('日期格式錯誤，請使用 YYYY-MM-DD')
    return start, end, None
