"""Work-period interval helpers.

This module is intentionally independent from database models and time zones.
Inputs and outputs are local-day minute offsets and ``HH:MM-HH:MM`` strings.
"""


def parse_period(period: str) -> tuple[int, int] | None:
    """Parse ``HH:MM-HH:MM`` into minute offsets.

    Periods whose end is earlier than or equal to the start are treated as
    crossing midnight.
    """
    try:
        start_str, end_str = period.split('-', 1)
        start_h, start_m = map(int, start_str.split(':', 1))
        end_h, end_m = map(int, end_str.split(':', 1))
    except (AttributeError, ValueError):
        return None

    if not (0 <= start_h <= 23 and 0 <= start_m <= 59 and 0 <= end_h <= 23 and 0 <= end_m <= 59):
        return None

    start_min = start_h * 60 + start_m
    end_min = end_h * 60 + end_m
    if end_min <= start_min:
        end_min += 1440
    return start_min, end_min


def format_period(start_min: int, end_min: int) -> str:
    """Format minute offsets as ``HH:MM-HH:MM`` without emitting ``24:00``."""
    start = start_min % 1440
    end = end_min % 1440
    return f'{start // 60:02d}:{start % 60:02d}-{end // 60:02d}:{end % 60:02d}'


def merge_intervals(intervals: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Merge overlapping or adjacent intervals, dropping empty intervals."""
    normalized = sorted((start, end) for start, end in intervals if start < end)
    if not normalized:
        return []

    merged = [normalized[0]]
    for start, end in normalized[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return merged


def subtract_periods(base_periods: list[str], leave_intervals: list[tuple[int, int]]) -> list[str]:
    """Subtract leave intervals from base work periods.

    If a cross-midnight base period is split and a remaining segment starts on
    the next local day (``start >= 1440``), that segment is intentionally
    dropped. ``schedule_adjustments`` stores one local day's remaining work
    periods, so next-day fragments are not preserved here.
    """
    leaves = merge_intervals(leave_intervals)
    remaining_periods = []
    for period in base_periods or []:
        parsed = parse_period(period)
        if parsed is None:
            continue

        if not leaves:
            remaining_periods.append(format_period(*parsed))
            continue

        segments = [parsed]
        for leave_start, leave_end in leaves:
            next_segments = []
            for start, end in segments:
                if leave_end <= start or leave_start >= end:
                    next_segments.append((start, end))
                    continue
                if start < leave_start:
                    next_segments.append((start, min(leave_start, end)))
                if leave_end < end:
                    next_segments.append((max(leave_end, start), end))
            segments = next_segments
            if not segments:
                break

        for start, end in segments:
            if start >= 1440 or start >= end:
                continue
            remaining_periods.append(format_period(start, end))

    return remaining_periods
