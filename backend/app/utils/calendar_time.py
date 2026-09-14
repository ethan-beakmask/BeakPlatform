"""行事曆時區轉換工具。"""
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo


def local_date_to_utc(tz_name: str, d: date) -> datetime:
    return local_naive_to_utc(tz_name, datetime.combine(d, time.min))


def local_naive_to_utc(tz_name: str, naive_local_dt: datetime) -> datetime:
    return (
        naive_local_dt
        .replace(tzinfo=ZoneInfo(tz_name))
        .astimezone(ZoneInfo('UTC'))
        .replace(tzinfo=None)
    )


def utc_to_local(tz_name: str, dt: datetime) -> datetime:
    return dt.replace(tzinfo=ZoneInfo('UTC')).astimezone(ZoneInfo(tz_name))


def format_local(dt: datetime) -> str:
    return dt.strftime('%Y-%m-%dT%H:%M')


def event_local_dates(all_day: bool, start_local: datetime, end_local: datetime) -> tuple[date, date]:
    start_date = start_local.date()
    end_date = end_local.date()
    if all_day and end_local.time() == time.min and end_local.date() > start_date:
        end_date = end_local.date() - timedelta(days=1)
    return start_date, end_date
