"""
共用班表 Web 路由

提供班表管理的頁面路由：
- /admin/settings/work-schedules - 基本班表列表
- /admin/settings/work-schedules/<code>/holidays - 共用月曆（假日管理）
"""
from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_babel import gettext as _
from flask_login import current_user

from ..security.decorators import admin_required
from ..models import WorkSchedule, ScheduleHoliday
from .. import db

work_schedules_bp = Blueprint('work_schedules', __name__)


@work_schedules_bp.route('/admin/settings/work-schedules')
@admin_required
def list_schedules():
    """基本班表列表頁面"""
    schedules = WorkSchedule.query.filter_by(
        org_secure_code=current_user.org_secure_code,
        is_deleted=False
    ).order_by(
        WorkSchedule.is_default.desc(),
        WorkSchedule.name
    ).all()

    # 預先序列化，避免 Jinja2 map(attribute='method') 問題
    schedules_data = [s.to_dict() for s in schedules]

    return render_template(
        'pages/admin/time/schedules.html',
        schedules=schedules,
        schedules_json=schedules_data
    )


@work_schedules_bp.route('/admin/settings/work-schedules/<secure_code>/holidays')
@admin_required
def schedule_holidays(secure_code):
    """
    共用月曆（假日管理）頁面

    Args:
        secure_code: 班表 secure_code
    """
    schedule = WorkSchedule.query.filter_by(
        org_secure_code=current_user.org_secure_code,
        secure_code=secure_code,
        is_deleted=False
    ).first()

    if not schedule:
        flash(_('班表不存在'), 'error')
        return redirect(url_for('work_schedules.list_schedules'))

    # 取得年份參數，預設當年
    from datetime import date
    year = request.args.get('year', date.today().year, type=int)

    return render_template(
        'pages/admin/time/holidays.html',
        schedule=schedule,
        year=year
    )
