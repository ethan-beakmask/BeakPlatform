"""企業行事曆 API。"""
import logging
from datetime import datetime

from flask import Blueprint, jsonify, request
from flask_babel import gettext as _
from flask_login import current_user

from app.security.decorators import page_keys_required
from app.services.calendar_projection_service import CalendarProjectionService

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
