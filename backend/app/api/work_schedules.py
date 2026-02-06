"""
共用班表管理 API

[標準 AUTH-02] 所有路由使用統一認證 decorator
[標準 URL-01] 使用 secure_code 取代自增 ID
[標準 TENANT-02] 透過 ResourceGateway 存取資源

端點：
- GET    /api/admin/work-schedules              列出班表
- POST   /api/admin/work-schedules              新增班表
- GET    /api/admin/work-schedules/<id>         取得班表詳情
- PUT    /api/admin/work-schedules/<id>         更新班表
- DELETE /api/admin/work-schedules/<id>         刪除班表
- PUT    /api/admin/work-schedules/<id>/default 設為預設

假日管理：
- GET    /api/admin/work-schedules/<id>/holidays         列出假日
- POST   /api/admin/work-schedules/<id>/holidays         新增假日
- PUT    /api/admin/work-schedules/<id>/holidays/<hid>   更新假日
- DELETE /api/admin/work-schedules/<id>/holidays/<hid>   刪除假日
- POST   /api/admin/work-schedules/<id>/holidays/batch   批次匯入假日
"""
from datetime import datetime, date
from flask import Blueprint, jsonify, request
from flask_login import current_user

from .. import db
from ..models import WorkSchedule, ScheduleHoliday
from ..security.decorators import admin_required
from ..security.resource_gateway import ResourceGateway


api_work_schedules = Blueprint('api_work_schedules', __name__, url_prefix='/api/admin')


# ==================== 班表 CRUD ====================

@api_work_schedules.route('/work-schedules', methods=['GET'])
@admin_required
def list_schedules():
    """
    列出所有班表

    Query:
        include_inactive: 是否包含停用的班表 (default: false)

    Returns:
        JSON: { "success": true, "data": [...] }
    """
    include_inactive = request.args.get('include_inactive', 'false').lower() == 'true'

    filters = {'is_deleted': False}
    if not include_inactive:
        filters['is_active'] = True

    schedules = ResourceGateway.filter(
        WorkSchedule,
        order_by='-is_default,name',
        **filters
    )

    return jsonify({
        'success': True,
        'data': [s.to_dict() for s in schedules]
    })


@api_work_schedules.route('/work-schedules', methods=['POST'])
@admin_required
def create_schedule():
    """
    新增班表

    Body:
        schedule_code: 班表代碼 (必填)
        name: 班表名稱 (必填)
        timezone: 時區 (預設 Asia/Taipei)
        weekly_hours: 週間工時 JSON
        description: 描述
        is_default: 是否為預設

    Returns:
        JSON: { "success": true, "data": {...} }
    """
    data = request.get_json()

    if not data:
        return jsonify({'success': False, 'message': '請提供資料'}), 400

    schedule_code = data.get('schedule_code', '').strip()
    name = data.get('name', '').strip()

    if not schedule_code:
        return jsonify({'success': False, 'message': '請輸入班表代碼'}), 400

    if not name:
        return jsonify({'success': False, 'message': '請輸入班表名稱'}), 400

    # 檢查代碼是否重複
    existing = ResourceGateway.get_by(WorkSchedule, schedule_code=schedule_code, is_deleted=False)
    if existing:
        return jsonify({'success': False, 'message': f'班表代碼 "{schedule_code}" 已存在'}), 400

    # 驗證週間工時格式
    weekly_hours = data.get('weekly_hours', {})
    if not _validate_weekly_hours(weekly_hours):
        return jsonify({'success': False, 'message': '週間工時格式錯誤'}), 400

    # 如果設為預設，先取消其他預設
    is_default = data.get('is_default', False)
    if is_default:
        _clear_default_schedule()

    # 建立班表
    schedule = WorkSchedule(
        org_secure_code=current_user.org_secure_code,
        schedule_code=schedule_code,
        name=name,
        timezone=data.get('timezone', 'Asia/Taipei'),
        weekly_hours=weekly_hours,
        description=data.get('description'),
        is_default=is_default
    )

    db.session.add(schedule)
    db.session.commit()

    return jsonify({
        'success': True,
        'message': '班表已建立',
        'data': schedule.to_dict()
    }), 201


@api_work_schedules.route('/work-schedules/<secure_code>', methods=['GET'])
@admin_required
def get_schedule(secure_code):
    """取得班表詳情"""
    schedule = ResourceGateway.get_by(
        WorkSchedule,
        secure_code=secure_code,
        is_deleted=False
    )

    if not schedule:
        return jsonify({'success': False, 'message': '班表不存在'}), 404

    return jsonify({
        'success': True,
        'data': schedule.to_dict()
    })


@api_work_schedules.route('/work-schedules/<secure_code>', methods=['PUT'])
@admin_required
def update_schedule(secure_code):
    """
    更新班表

    Body: (所有欄位可選)
        name: 班表名稱
        timezone: 時區
        weekly_hours: 週間工時 JSON
        description: 描述
        is_active: 是否啟用
    """
    schedule = ResourceGateway.get_by(
        WorkSchedule,
        secure_code=secure_code,
        is_deleted=False
    )

    if not schedule:
        return jsonify({'success': False, 'message': '班表不存在'}), 404

    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'message': '請提供資料'}), 400

    # 更新欄位
    if 'name' in data:
        name = data['name'].strip()
        if not name:
            return jsonify({'success': False, 'message': '名稱不可為空'}), 400
        schedule.name = name

    if 'timezone' in data:
        schedule.timezone = data['timezone']

    if 'weekly_hours' in data:
        weekly_hours = data['weekly_hours']
        if not _validate_weekly_hours(weekly_hours):
            return jsonify({'success': False, 'message': '週間工時格式錯誤'}), 400
        schedule.weekly_hours = weekly_hours

    if 'description' in data:
        schedule.description = data['description']

    if 'is_active' in data:
        schedule.is_active = bool(data['is_active'])

    db.session.commit()

    return jsonify({
        'success': True,
        'message': '班表已更新',
        'data': schedule.to_dict()
    })


@api_work_schedules.route('/work-schedules/<secure_code>', methods=['DELETE'])
@admin_required
def delete_schedule(secure_code):
    """
    刪除班表（軟刪除）

    注意：
    - 預設班表不可刪除
    - 已指派給用戶的班表不可刪除
    """
    schedule = ResourceGateway.get_by(
        WorkSchedule,
        secure_code=secure_code,
        is_deleted=False
    )

    if not schedule:
        return jsonify({'success': False, 'message': '班表不存在'}), 404

    if schedule.is_default:
        return jsonify({'success': False, 'message': '預設班表不可刪除'}), 400

    # 檢查是否有用戶使用此班表
    from ..models import User
    user_count = User.query.filter_by(  # nosemgrep: beakplatform-direct-model-query-in-api
        work_schedule_secure_code=schedule.secure_code,
        is_deleted=False
    ).count()

    if user_count > 0:
        return jsonify({
            'success': False,
            'message': f'此班表已指派給 {user_count} 位用戶，無法刪除'
        }), 400

    # 軟刪除
    schedule.is_deleted = True
    schedule.deleted_at = datetime.utcnow()
    db.session.commit()

    return jsonify({
        'success': True,
        'message': '班表已刪除'
    })


@api_work_schedules.route('/work-schedules/<secure_code>/default', methods=['PUT'])
@admin_required
def set_default_schedule(secure_code):
    """設為企業預設班表"""
    schedule = ResourceGateway.get_by(
        WorkSchedule,
        secure_code=secure_code,
        is_deleted=False
    )

    if not schedule:
        return jsonify({'success': False, 'message': '班表不存在'}), 404

    # 取消其他預設
    _clear_default_schedule()

    # 設為預設
    schedule.is_default = True
    db.session.commit()

    return jsonify({
        'success': True,
        'message': f'已將 "{schedule.name}" 設為預設班表'
    })


# ==================== 假日管理 ====================

@api_work_schedules.route('/work-schedules/<secure_code>/holidays', methods=['GET'])
@admin_required
def list_holidays(secure_code):
    """
    列出班表假日

    Query:
        year: 年份 (預設當年)

    Returns:
        JSON: { "success": true, "data": [...] }
    """
    schedule = ResourceGateway.get_by(
        WorkSchedule,
        secure_code=secure_code,
        is_deleted=False
    )

    if not schedule:
        return jsonify({'success': False, 'message': '班表不存在'}), 404

    year = request.args.get('year', date.today().year, type=int)

    # 查詢指定年份的假日
    holidays = ScheduleHoliday.query.filter(  # nosemgrep: beakplatform-direct-model-query-in-api
        ScheduleHoliday.schedule_secure_code == schedule.secure_code,
        ScheduleHoliday.is_deleted == False,
        db.extract('year', ScheduleHoliday.holiday_date) == year
    ).order_by(ScheduleHoliday.holiday_date).all()

    return jsonify({
        'success': True,
        'data': [h.to_dict() for h in holidays]
    })


@api_work_schedules.route('/work-schedules/<secure_code>/holidays', methods=['POST'])
@admin_required
def create_holiday(secure_code):
    """
    新增假日/補班日

    Body:
        holiday_date: 日期 (必填, YYYY-MM-DD)
        holiday_type: 類型 (必填, HOLIDAY 或 WORKDAY)
        work_periods: 工作時段 (補班日必填)
        description: 說明

    Returns:
        JSON: { "success": true, "data": {...} }
    """
    schedule = ResourceGateway.get_by(
        WorkSchedule,
        secure_code=secure_code,
        is_deleted=False
    )

    if not schedule:
        return jsonify({'success': False, 'message': '班表不存在'}), 404

    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'message': '請提供資料'}), 400

    # 驗證必填欄位
    holiday_date_str = data.get('holiday_date')
    holiday_type = data.get('holiday_type', '').upper()

    if not holiday_date_str:
        return jsonify({'success': False, 'message': '請選擇日期'}), 400

    if holiday_type not in ('HOLIDAY', 'WORKDAY'):
        return jsonify({'success': False, 'message': '類型必須是 HOLIDAY 或 WORKDAY'}), 400

    try:
        holiday_date = datetime.strptime(holiday_date_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'success': False, 'message': '日期格式錯誤，請使用 YYYY-MM-DD'}), 400

    # 補班日需要工作時段
    work_periods = data.get('work_periods')
    if holiday_type == 'WORKDAY' and not work_periods:
        return jsonify({'success': False, 'message': '補班日請設定工作時段'}), 400

    # 檢查日期是否重複
    existing = ScheduleHoliday.query.filter_by(  # nosemgrep: beakplatform-direct-model-query-in-api
        schedule_secure_code=schedule.secure_code,
        holiday_date=holiday_date,
        is_deleted=False
    ).first()

    if existing:
        return jsonify({'success': False, 'message': f'{holiday_date_str} 已設定過'}), 400

    # 建立假日
    holiday = ScheduleHoliday(
        schedule_secure_code=schedule.secure_code,
        holiday_date=holiday_date,
        holiday_type=holiday_type,
        work_periods=work_periods if holiday_type == 'WORKDAY' else None,
        description=data.get('description')
    )

    db.session.add(holiday)
    db.session.commit()

    return jsonify({
        'success': True,
        'message': '已新增',
        'data': holiday.to_dict()
    }), 201


@api_work_schedules.route('/work-schedules/<secure_code>/holidays/<holiday_secure_code>', methods=['PUT'])
@admin_required
def update_holiday(secure_code, holiday_secure_code):
    """更新假日"""
    schedule = ResourceGateway.get_by(
        WorkSchedule,
        secure_code=secure_code,
        is_deleted=False
    )

    if not schedule:
        return jsonify({'success': False, 'message': '班表不存在'}), 404

    holiday = ScheduleHoliday.query.filter_by(  # nosemgrep: beakplatform-direct-model-query-in-api
        secure_code=holiday_secure_code,
        schedule_secure_code=schedule.secure_code,
        is_deleted=False
    ).first()

    if not holiday:
        return jsonify({'success': False, 'message': '假日不存在'}), 404

    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'message': '請提供資料'}), 400

    if 'holiday_type' in data:
        holiday_type = data['holiday_type'].upper()
        if holiday_type not in ('HOLIDAY', 'WORKDAY'):
            return jsonify({'success': False, 'message': '類型必須是 HOLIDAY 或 WORKDAY'}), 400
        holiday.holiday_type = holiday_type

        # 切換類型時調整 work_periods
        if holiday_type == 'HOLIDAY':
            holiday.work_periods = None

    if 'work_periods' in data:
        if holiday.holiday_type == 'WORKDAY':
            holiday.work_periods = data['work_periods']

    if 'description' in data:
        holiday.description = data['description']

    db.session.commit()

    return jsonify({
        'success': True,
        'message': '已更新',
        'data': holiday.to_dict()
    })


@api_work_schedules.route('/work-schedules/<secure_code>/holidays/<holiday_secure_code>', methods=['DELETE'])
@admin_required
def delete_holiday(secure_code, holiday_secure_code):
    """刪除假日"""
    schedule = ResourceGateway.get_by(
        WorkSchedule,
        secure_code=secure_code,
        is_deleted=False
    )

    if not schedule:
        return jsonify({'success': False, 'message': '班表不存在'}), 404

    holiday = ScheduleHoliday.query.filter_by(  # nosemgrep: beakplatform-direct-model-query-in-api
        secure_code=holiday_secure_code,
        schedule_secure_code=schedule.secure_code,
        is_deleted=False
    ).first()

    if not holiday:
        return jsonify({'success': False, 'message': '假日不存在'}), 404

    holiday.is_deleted = True
    holiday.deleted_at = datetime.utcnow()
    db.session.commit()

    return jsonify({
        'success': True,
        'message': '已刪除'
    })


@api_work_schedules.route('/work-schedules/<secure_code>/holidays/batch', methods=['POST'])
@admin_required
def batch_import_holidays(secure_code):
    """
    批次匯入假日

    Body:
        holidays: [
            { "date": "2026-01-01", "type": "HOLIDAY", "description": "元旦" },
            { "date": "2026-02-14", "type": "WORKDAY", "work_periods": ["09:00-17:00"], "description": "補班" },
            ...
        ]
        replace_year: 是否取代該年度所有假日 (預設 false)

    Returns:
        JSON: { "success": true, "imported": 10, "skipped": 2 }
    """
    schedule = ResourceGateway.get_by(
        WorkSchedule,
        secure_code=secure_code,
        is_deleted=False
    )

    if not schedule:
        return jsonify({'success': False, 'message': '班表不存在'}), 404

    data = request.get_json()
    if not data or 'holidays' not in data:
        return jsonify({'success': False, 'message': '請提供假日資料'}), 400

    holidays_data = data['holidays']
    replace_year = data.get('replace_year', False)

    imported = 0
    skipped = 0
    years_to_replace = set()

    # 收集要取代的年份
    if replace_year:
        for item in holidays_data:
            try:
                d = datetime.strptime(item.get('date', ''), '%Y-%m-%d').date()
                years_to_replace.add(d.year)
            except ValueError:
                continue

        # 刪除這些年份的現有假日
        for year in years_to_replace:
            ScheduleHoliday.query.filter(  # nosemgrep: beakplatform-direct-model-query-in-api
                ScheduleHoliday.schedule_secure_code == schedule.secure_code,
                ScheduleHoliday.is_deleted == False,
                db.extract('year', ScheduleHoliday.holiday_date) == year
            ).update({'is_deleted': True, 'deleted_at': datetime.utcnow()})

    # 匯入假日
    for item in holidays_data:
        try:
            holiday_date = datetime.strptime(item.get('date', ''), '%Y-%m-%d').date()
            holiday_type = item.get('type', 'HOLIDAY').upper()

            if holiday_type not in ('HOLIDAY', 'WORKDAY'):
                skipped += 1
                continue

            # 檢查是否存在（非取代模式）
            if not replace_year:
                existing = ScheduleHoliday.query.filter_by(  # nosemgrep: beakplatform-direct-model-query-in-api
                    schedule_secure_code=schedule.secure_code,
                    holiday_date=holiday_date,
                    is_deleted=False
                ).first()

                if existing:
                    skipped += 1
                    continue

            holiday = ScheduleHoliday(
                schedule_secure_code=schedule.secure_code,
                holiday_date=holiday_date,
                holiday_type=holiday_type,
                work_periods=item.get('work_periods') if holiday_type == 'WORKDAY' else None,
                description=item.get('description')
            )

            db.session.add(holiday)
            imported += 1

        except (ValueError, KeyError):
            skipped += 1
            continue

    db.session.commit()

    return jsonify({
        'success': True,
        'message': f'已匯入 {imported} 筆，略過 {skipped} 筆',
        'imported': imported,
        'skipped': skipped
    })


# ==================== 輔助函數 ====================

def _validate_weekly_hours(weekly_hours: dict) -> bool:
    """
    驗證週間工時格式

    有效格式：
    {
        "mon": ["09:00-12:00", "13:00-18:00"],
        "tue": ["09:00-18:00"],
        "sat": null,  # 休息
        "sun": []     # 休息
    }
    """
    if not isinstance(weekly_hours, dict):
        return False

    valid_days = {'mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'}

    for day, periods in weekly_hours.items():
        if day not in valid_days:
            return False

        # null 或空陣列表示休息
        if periods is None or periods == []:
            continue

        if not isinstance(periods, list):
            return False

        # 驗證每個時段格式
        for period in periods:
            if not isinstance(period, str):
                return False
            if not _validate_time_period(period):
                return False

    return True


def _validate_time_period(period: str) -> bool:
    """
    驗證時段格式 (HH:MM-HH:MM)
    """
    try:
        start, end = period.split('-')
        datetime.strptime(start.strip(), '%H:%M')
        datetime.strptime(end.strip(), '%H:%M')
        return True
    except (ValueError, AttributeError):
        return False


def _clear_default_schedule():
    """取消所有預設班表標記"""
    schedules = ResourceGateway.filter(
        WorkSchedule,
        is_default=True,
        is_deleted=False
    )
    for s in schedules:
        s.is_default = False
