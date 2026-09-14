from app.utils.work_periods import (
    format_period,
    merge_intervals,
    parse_period,
    subtract_periods,
)


def test_parse_period_handles_normal_cross_midnight_and_bad_format():
    assert parse_period('09:00-18:00') == (540, 1080)
    assert parse_period('22:00-06:00') == (1320, 1800)
    assert parse_period('09:00') is None
    assert parse_period('24:00-25:00') is None


def test_format_period_never_emits_24_hour():
    values = [
        format_period(540, 1080),
        format_period(1320, 1440),
        format_period(1320, 1800),
    ]

    assert values == ['09:00-18:00', '22:00-00:00', '22:00-06:00']
    assert all('24:00' not in value for value in values)


def test_merge_intervals_merges_overlap_and_adjacent_and_drops_empty():
    assert merge_intervals([(60, 120), (100, 180), (180, 210), (300, 300), (420, 360)]) == [
        (60, 210)
    ]


def test_subtract_periods_handles_partial_leave():
    assert subtract_periods(['09:00-12:00', '13:00-18:00'], [(540, 720)]) == ['13:00-18:00']


def test_subtract_periods_can_split_middle_hole():
    assert subtract_periods(['09:00-18:00'], [(600, 660)]) == ['09:00-10:00', '11:00-18:00']


def test_subtract_periods_handles_full_day_outside_and_multiple_intervals():
    assert subtract_periods(['09:00-18:00'], [(0, 1440)]) == []
    assert subtract_periods(['09:00-18:00'], [(0, 480), (1140, 1200)]) == ['09:00-18:00']
    assert subtract_periods(['09:00-18:00'], [(540, 600), (660, 840)]) == ['10:00-11:00', '14:00-18:00']
    assert subtract_periods(['bad', '09:00-18:00'], []) == ['09:00-18:00']


def test_subtract_periods_drops_next_day_fragment_after_cross_midnight_split():
    assert subtract_periods(['22:00-06:00'], [(1380, 1440)]) == ['22:00-23:00']
