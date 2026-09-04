from app.utils.regions import (
    build_default_weekly_hours,
    country_choices,
    country_from_timezone,
    is_valid_country,
    weekend_days,
)


def test_weekend_days_defaults_and_overrides():
    assert weekend_days('TW') == (5, 6)
    assert weekend_days('SA') == (4, 5)
    assert weekend_days(None) == (5, 6)


def test_country_from_timezone():
    assert country_from_timezone('Asia/Taipei') == 'TW'
    assert country_from_timezone('UTC') is None


def test_is_valid_country_requires_known_uppercase_code():
    assert is_valid_country('TW') is True
    assert is_valid_country('XX') is False
    assert is_valid_country('tw') is False


def test_build_default_weekly_hours_uses_country_weekend():
    weekly_hours = build_default_weekly_hours('SA')
    assert weekly_hours['fri'] is None
    assert weekly_hours['sat'] is None
    assert weekly_hours['sun'] == ['09:00-12:00', '13:00-18:00']


def test_country_choices_are_localized_and_locale_fallback_is_safe():
    assert ('TW', '台灣') in country_choices('zh-TW')
    assert country_choices('not-a-locale')
