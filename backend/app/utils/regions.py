"""Country/region helpers for organization defaults."""
from typing import Optional

import pytz
from babel import Locale


DEFAULT_WORK_PERIODS = ['09:00-12:00', '13:00-18:00']
DEFAULT_WEEKEND = (5, 6)
WEEKEND_BY_COUNTRY = {
    'SA': (4, 5), 'EG': (4, 5), 'IL': (4, 5), 'IQ': (4, 5), 'JO': (4, 5), 'KW': (4, 5),
    'LY': (4, 5), 'OM': (4, 5), 'QA': (4, 5), 'SD': (4, 5), 'SY': (4, 5), 'YE': (4, 5),
    'BH': (4, 5), 'AF': (3, 4), 'IR': (4,), 'DJ': (4,), 'NP': (5,),
}

_DAY_KEYS = ('mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun')


def weekend_days(country_code) -> tuple:
    """Return weekend weekdays for an ISO 3166-1 alpha-2 country code."""
    if not country_code:
        return DEFAULT_WEEKEND
    return WEEKEND_BY_COUNTRY.get(str(country_code).upper(), DEFAULT_WEEKEND)


def is_valid_country(code) -> bool:
    """Validate an uppercase two-letter country code known to pytz."""
    if not isinstance(code, str):
        return False
    return len(code) == 2 and code.isupper() and code in pytz.country_names


def country_from_timezone(tz_name) -> Optional[str]:
    """Infer country code from an IANA timezone name."""
    if not tz_name or tz_name == 'UTC':
        return None
    for country_code, timezones in pytz.country_timezones.items():
        if tz_name in timezones:
            return country_code
    return None


def country_choices(locale='zh-TW') -> list[tuple[str, str]]:
    """Return localized country choices sorted by display name."""
    try:
        parsed_locale = Locale.parse((locale or 'en').replace('-', '_'))
    except Exception:
        parsed_locale = Locale.parse('en')

    choices = []
    for code, english_name in pytz.country_names.items():
        display_name = parsed_locale.territories.get(code, english_name)
        choices.append((code, display_name))
    return sorted(choices, key=lambda item: item[1])


def build_default_weekly_hours(country_code) -> dict:
    """Build weekly hours with country-specific weekends marked as rest days."""
    weekends = set(weekend_days(country_code))
    return {
        day_key: None if weekday in weekends else list(DEFAULT_WORK_PERIODS)
        for weekday, day_key in enumerate(_DAY_KEYS)
    }
