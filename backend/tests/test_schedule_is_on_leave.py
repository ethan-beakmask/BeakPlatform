import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app import db  # noqa: E402
from app.models import ScheduleAdjustment, User, UserType  # noqa: E402
from app.services.schedule_service import ScheduleService  # noqa: E402


def _user(sc, org, username):
    user = User(
        secure_code=sc,
        org_secure_code=org.secure_code,
        username=username,
        email=f'{username}@example.com',
        display_name=username,
        user_type=UserType.EMPLOYEE,
        is_active=True,
        is_deleted=False,
    )
    user.set_password('password123')
    db.session.add(user)
    db.session.commit()
    return user


def _leave(user, adjust_date, adjusted_periods, original_periods=None,
           status='APPROVED', is_deleted=False, adjust_type='LEAVE'):
    row = ScheduleAdjustment(
        org_secure_code=user.org_secure_code,
        user_secure_code=user.secure_code,
        adjust_date=adjust_date,
        adjust_type=adjust_type,
        original_periods=original_periods,
        adjusted_periods=adjusted_periods,
        status=status,
        is_deleted=is_deleted,
    )
    db.session.add(row)
    db.session.commit()
    return row


def test_empty_adjusted_periods_means_full_day_leave(test_org, test_user):
    _leave(test_user, date(2026, 9, 5), [])

    assert ScheduleService.is_on_leave(test_user, datetime(2026, 9, 5, 10, 0)) is True
    assert ScheduleService.is_on_leave(test_user, datetime(2026, 9, 5, 20, 0)) is True


def test_null_adjusted_periods_means_full_day_leave(test_org, test_user):
    _leave(test_user, date(2026, 9, 5), None)

    assert ScheduleService.is_on_leave(test_user, datetime(2026, 9, 5, 10, 0)) is True


def test_partial_leave_uses_original_minus_adjusted_periods(test_org, test_user):
    _leave(
        test_user,
        date(2026, 9, 5),
        ['09:00-12:00'],
        ['09:00-12:00', '13:00-18:00'],
    )

    assert ScheduleService.is_on_leave(test_user, datetime(2026, 9, 5, 14, 0)) is True
    assert ScheduleService.is_on_leave(test_user, datetime(2026, 9, 5, 10, 0)) is False
    assert ScheduleService.is_on_leave(test_user, datetime(2026, 9, 5, 19, 0)) is False


def test_multiple_leave_segments_are_derived_from_remaining_work(test_org, test_user):
    _leave(
        test_user,
        date(2026, 9, 5),
        ['10:00-11:00'],
        ['09:00-12:00', '13:00-18:00'],
    )

    assert ScheduleService.is_on_leave(test_user, datetime(2026, 9, 5, 9, 30)) is True
    assert ScheduleService.is_on_leave(test_user, datetime(2026, 9, 5, 10, 30)) is False
    assert ScheduleService.is_on_leave(test_user, datetime(2026, 9, 5, 13, 30)) is True


def test_ignores_unapproved_deleted_and_non_leave_adjustments(test_org):
    pending = _user('leave_pending_user', test_org, 'leavepending')
    deleted = _user('leave_deleted_user', test_org, 'leavedeleted')
    overtime = _user('leave_overtime_user', test_org, 'leaveovertime')
    _leave(pending, date(2026, 9, 5), [], status='PENDING')
    _leave(deleted, date(2026, 9, 5), [], is_deleted=True)
    _leave(overtime, date(2026, 9, 5), [], adjust_type='OVERTIME')

    assert ScheduleService.is_on_leave(pending, datetime(2026, 9, 5, 10, 0)) is False
    assert ScheduleService.is_on_leave(deleted, datetime(2026, 9, 5, 10, 0)) is False
    assert ScheduleService.is_on_leave(overtime, datetime(2026, 9, 5, 10, 0)) is False


def test_other_date_full_day_leave_does_not_apply(test_org, test_user):
    _leave(test_user, date(2026, 9, 6), [])

    assert ScheduleService.is_on_leave(test_user, datetime(2026, 9, 5, 10, 0)) is False


def test_missing_base_periods_only_full_day_leave_counts(test_org):
    inconsistent = _user('leave_no_base_user', test_org, 'leavenobase')
    full_day = _user('leave_no_base_full_user', test_org, 'leavenobasefull')
    _leave(inconsistent, date(2026, 9, 5), ['09:00-12:00'], [])
    _leave(full_day, date(2026, 9, 5), [], [])

    assert ScheduleService.is_on_leave(inconsistent, datetime(2026, 9, 5, 10, 0)) is False
    assert ScheduleService.is_on_leave(full_day, datetime(2026, 9, 5, 10, 0)) is True


def test_cross_midnight_leave_periods_match_next_day_minutes(test_org, test_user):
    _leave(
        test_user,
        date(2026, 9, 5),
        ['22:00-02:00'],
        ['22:00-06:00'],
    )

    assert ScheduleService.is_on_leave(test_user, datetime(2026, 9, 5, 3, 0)) is True
    assert ScheduleService.is_on_leave(test_user, datetime(2026, 9, 5, 23, 0)) is False
