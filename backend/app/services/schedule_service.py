"""
班表服務

提供統一的工時計算功能：
- 取得某人某日的工作時段
- 計算兩個時間點之間的工作秒數
- 檢查某時間點是否在工作時段內

優先級：排班調整 > 個人排班 > 共用班表
"""
from datetime import date, datetime, timedelta
from typing import List, Optional, Tuple

from ..models import (
    User, WorkSchedule, ScheduleHoliday,
    PersonalSchedule, ScheduleAdjustment
)
from .. import db
from ..utils.regions import build_default_weekly_hours


class ScheduleService:
    """班表服務類"""

    @staticmethod
    def ensure_default_schedule(org) -> Optional[WorkSchedule]:
        """企業沒有預設班表時建立一張；已有就原樣回傳。不 commit，由呼叫端決定。"""
        if org.is_system_org:
            return None

        existing = WorkSchedule.query.filter_by(
            org_secure_code=org.secure_code,
            is_default=True,
            is_deleted=False,
        ).first()
        if existing:
            return existing

        schedule_code = 'DEFAULT'
        suffix = 2
        while WorkSchedule.query.filter_by(
            org_secure_code=org.secure_code,
            schedule_code=schedule_code,
            is_deleted=False,
        ).first():
            schedule_code = f'DEFAULT-{suffix}'
            suffix += 1

        schedule = WorkSchedule(
            org_secure_code=org.secure_code,
            schedule_code=schedule_code,
            name='企業預設班表',
            timezone=org.get_setting('timezone', 'Asia/Taipei'),
            weekly_hours=build_default_weekly_hours(org.get_setting('country', 'TW')),
            is_default=True,
            is_active=True,
            description='依企業國家／地區自動產生的週休預設，請依實際情況調整',
        )
        db.session.add(schedule)
        db.session.flush()
        return schedule

    @staticmethod
    def get_user_schedule(user: User) -> Optional[WorkSchedule]:
        """
        取得用戶的共用班表

        Args:
            user: 用戶實體

        Returns:
            WorkSchedule: 用戶的班表，找不到時返回 None
        """
        # 1. 用戶指定的班表
        if user.work_schedule_secure_code:
            schedule = WorkSchedule.query.filter_by(
                secure_code=user.work_schedule_secure_code,
                is_deleted=False
            ).first()
            if schedule:
                return schedule

        # 2. 企業預設班表
        default_schedule = WorkSchedule.query.filter_by(
            org_secure_code=user.org_secure_code,
            is_default=True,
            is_deleted=False
        ).first()

        return default_schedule

    @staticmethod
    def get_work_periods(user: User, target_date: date) -> List[str]:
        """
        取得某人某日的工作時段

        計算優先級：LEAVE 調整 > 非 LEAVE 調整 > 個人排班 > 共用班表。
        舊行為在同日同時存在 LEAVE 與其他調整時依資料庫 first() 結果而定；
        現在 LEAVE 一律優先，且 adjusted_periods 為 NULL 時仍視為整天請假。

        Args:
            user: 用戶實體
            target_date: 目標日期

        Returns:
            工作時段列表，如 ["09:00-12:00", "13:00-18:00"]
            休息日返回空列表
        """
        leave_adjustment = ScheduleAdjustment.query.filter_by(
            org_secure_code=user.org_secure_code,
            user_secure_code=user.secure_code,
            adjust_date=target_date,
            adjust_type='LEAVE',
            status='APPROVED',
            is_deleted=False
        ).first()
        if leave_adjustment:
            return leave_adjustment.adjusted_periods or []

        return ScheduleService.get_base_work_periods(user, target_date)

    @staticmethod
    def get_base_work_periods(user: User, target_date: date) -> List[str]:
        """
        取得扣除請假前的基礎工作時段。

        此函式排除 LEAVE 調整列，供請假同步重算剩餘時段；CANCEL、
        OVERTIME、SWAP 仍依一般排班調整優先於個人排班與共用班表。
        """
        return ScheduleService._get_non_leave_work_periods(user, target_date)

    @staticmethod
    def _get_non_leave_work_periods(user: User, target_date: date) -> List[str]:
        """Resolve work periods without applying LEAVE adjustments."""
        adjustment = ScheduleAdjustment.query.filter(
            ScheduleAdjustment.org_secure_code == user.org_secure_code,
            ScheduleAdjustment.user_secure_code == user.secure_code,
            ScheduleAdjustment.adjust_date == target_date,
            ScheduleAdjustment.adjust_type != 'LEAVE',
            ScheduleAdjustment.status == 'APPROVED',
            ScheduleAdjustment.is_deleted == False,  # noqa: E712
        ).first()
        if adjustment:
            if adjustment.adjust_type == 'CANCEL':
                return []  # 取消班次
            elif adjustment.adjust_type in ('OVERTIME', 'SWAP'):
                return adjustment.adjusted_periods or []

        # 2. 查個人排班
        personal = PersonalSchedule.query.filter_by(
            org_secure_code=user.org_secure_code,
            user_secure_code=user.secure_code,
            schedule_date=target_date,
            is_deleted=False
        ).first()

        if personal:
            return personal.get_work_periods()

        # 3. 查共用班表（fallback）
        schedule = ScheduleService.get_user_schedule(user)
        if not schedule:
            return []  # 沒有班表設定

        return schedule.get_day_periods(target_date)

    @staticmethod
    def is_working_time(user: User, check_time: datetime) -> bool:
        """
        檢查指定時間是否在工作時段內

        Args:
            user: 用戶實體
            check_time: 要檢查的時間

        Returns:
            是否在工作時段內
        """
        periods = ScheduleService.get_work_periods(user, check_time.date())
        if not periods:
            return False

        check_minutes = check_time.hour * 60 + check_time.minute

        for period in periods:
            try:
                start_str, end_str = period.split('-')
                start_h, start_m = map(int, start_str.split(':'))
                end_h, end_m = map(int, end_str.split(':'))

                start_minutes = start_h * 60 + start_m
                end_minutes = end_h * 60 + end_m

                # 處理跨日（如 22:00-06:00）
                if end_minutes < start_minutes:
                    # 跨日：檢查是否在 start-24:00 或 00:00-end
                    if check_minutes >= start_minutes or check_minutes < end_minutes:
                        return True
                else:
                    if start_minutes <= check_minutes < end_minutes:
                        return True
            except (ValueError, AttributeError):
                continue

        return False

    @staticmethod
    def calculate_working_seconds(
        user: User,
        start_time: datetime,
        end_time: datetime
    ) -> int:
        """
        計算兩個時間點之間的工作秒數

        Args:
            user: 用戶實體
            start_time: 開始時間
            end_time: 結束時間

        Returns:
            工作秒數
        """
        if start_time >= end_time:
            return 0

        total_seconds = 0
        current = start_time

        while current.date() <= end_time.date():
            day_start = datetime.combine(current.date(), datetime.min.time())
            day_end = day_start + timedelta(days=1)

            # 在當天的範圍
            period_start = max(current, day_start)
            period_end = min(end_time, day_end)

            # 取得當日工作時段
            work_periods = ScheduleService.get_work_periods(user, current.date())

            for period in work_periods:
                try:
                    work_start_str, work_end_str = period.split('-')
                    work_start_h, work_start_m = map(int, work_start_str.split(':'))
                    work_end_h, work_end_m = map(int, work_end_str.split(':'))

                    work_start = datetime.combine(
                        current.date(),
                        datetime.min.time().replace(hour=work_start_h, minute=work_start_m)
                    )
                    work_end = datetime.combine(
                        current.date(),
                        datetime.min.time().replace(hour=work_end_h, minute=work_end_m)
                    )

                    # 處理跨日
                    if work_end <= work_start:
                        work_end += timedelta(days=1)

                    # 計算重疊
                    overlap_start = max(period_start, work_start)
                    overlap_end = min(period_end, work_end)

                    if overlap_start < overlap_end:
                        total_seconds += int((overlap_end - overlap_start).total_seconds())

                except (ValueError, AttributeError):
                    continue

            # 下一天
            current = datetime.combine(current.date() + timedelta(days=1), datetime.min.time())

        return total_seconds

    @staticmethod
    def get_next_working_time(user: User, from_time: datetime) -> Optional[datetime]:
        """
        取得下一個工作時間開始點

        Args:
            user: 用戶實體
            from_time: 起始時間

        Returns:
            下一個工作時間，找不到時返回 None（最多查 30 天）
        """
        current = from_time
        max_date = from_time + timedelta(days=30)

        while current < max_date:
            periods = ScheduleService.get_work_periods(user, current.date())

            for period in periods:
                try:
                    start_str, _ = period.split('-')
                    start_h, start_m = map(int, start_str.split(':'))

                    work_start = datetime.combine(
                        current.date(),
                        datetime.min.time().replace(hour=start_h, minute=start_m)
                    )

                    if work_start > from_time:
                        return work_start
                except (ValueError, AttributeError):
                    continue

            # 下一天
            current = datetime.combine(
                current.date() + timedelta(days=1),
                datetime.min.time()
            )

        return None

    @staticmethod
    def estimate_working_end_time(
        user: User,
        start_time: datetime,
        working_seconds: int
    ) -> datetime:
        """
        估算經過指定工作秒數後的結束時間

        Args:
            user: 用戶實體
            start_time: 開始時間
            working_seconds: 需要的工作秒數

        Returns:
            預估結束時間
        """
        remaining = working_seconds
        current = start_time
        max_date = start_time + timedelta(days=365)  # 最多計算一年

        while remaining > 0 and current < max_date:
            periods = ScheduleService.get_work_periods(user, current.date())

            for period in periods:
                try:
                    start_str, end_str = period.split('-')
                    start_h, start_m = map(int, start_str.split(':'))
                    end_h, end_m = map(int, end_str.split(':'))

                    work_start = datetime.combine(
                        current.date(),
                        datetime.min.time().replace(hour=start_h, minute=start_m)
                    )
                    work_end = datetime.combine(
                        current.date(),
                        datetime.min.time().replace(hour=end_h, minute=end_m)
                    )

                    # 處理跨日
                    if work_end <= work_start:
                        work_end += timedelta(days=1)

                    # 從目前時間開始計算
                    actual_start = max(current, work_start)

                    if actual_start < work_end:
                        available_seconds = int((work_end - actual_start).total_seconds())

                        if available_seconds >= remaining:
                            return actual_start + timedelta(seconds=remaining)
                        else:
                            remaining -= available_seconds

                except (ValueError, AttributeError):
                    continue

            # 下一天
            current = datetime.combine(
                current.date() + timedelta(days=1),
                datetime.min.time()
            )

        # 超過一年還沒算完，返回起始時間加上絕對秒數
        return start_time + timedelta(seconds=working_seconds)


# 便捷函數
def get_work_periods(user: User, target_date: date) -> List[str]:
    """取得某人某日的工作時段（便捷函數）"""
    return ScheduleService.get_work_periods(user, target_date)


def calculate_working_seconds(
    user: User,
    start_time: datetime,
    end_time: datetime
) -> int:
    """計算工作秒數（便捷函數）"""
    return ScheduleService.calculate_working_seconds(user, start_time, end_time)


def is_working_time(user: User, check_time: datetime) -> bool:
    """檢查是否在工作時段內（便捷函數）"""
    return ScheduleService.is_working_time(user, check_time)
