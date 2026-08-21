"""
時區工具
提供 IANA 時區列表（按洲分組），供模板下拉選單使用
"""
from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo, available_timezones


# 洲名中文對照
CONTINENT_LABELS = {
    'Asia': 'Asia 亞洲',
    'Europe': 'Europe 歐洲',
    'America': 'America 美洲',
    'Africa': 'Africa 非洲',
    'Pacific': 'Pacific 太平洋',
    'Australia': 'Australia 澳洲',
    'Atlantic': 'Atlantic 大西洋',
    'Indian': 'Indian 印度洋',
    'Antarctica': 'Antarctica 南極洲',
    'Arctic': 'Arctic 北極',
}

# 排序優先順序（亞太區優先）
CONTINENT_ORDER = [
    'Asia', 'Australia', 'Pacific',
    'Europe', 'America', 'Africa',
    'Atlantic', 'Indian', 'Antarctica', 'Arctic',
]


def get_timezone_choices():
    """
    取得 IANA 時區列表，按洲分組

    Returns:
        list of (label, [(tz_name, tz_name), ...])
        例: [('Asia 亞洲', [('Asia/Taipei', 'Asia/Taipei'), ...]), ...]
    """
    tzs = sorted([
        t for t in available_timezones()
        if '/' in t and not t.startswith('Etc/')
    ])

    groups = defaultdict(list)
    for tz in tzs:
        continent = tz.split('/', 1)[0]
        groups[continent].append(tz)

    result = []
    for continent in CONTINENT_ORDER:
        if continent in groups:
            label = CONTINENT_LABELS.get(continent, continent)
            items = [(tz, tz) for tz in sorted(groups[continent])]
            result.append((label, items))

    # 收入未列在 CONTINENT_ORDER 中的（以防萬一）
    for continent in sorted(groups.keys()):
        if continent not in CONTINENT_ORDER:
            label = CONTINENT_LABELS.get(continent, continent)
            items = [(tz, tz) for tz in sorted(groups[continent])]
            result.append((label, items))

    return result


def local_day_start_utc(tz_name: str, ref: datetime = None) -> datetime:
    """回傳「該時區當地今日零點」對應的 naive UTC datetime（TZ-01）。

    DB 存 naive UTC，但統計的日界必須依使用者看到的當地日曆日切分，
    否則台北 08:00 之前的「今日」實際涵蓋的是當地昨天 08:00 起。

    ref 視為 naive UTC（預設 datetime.utcnow()）；時區名稱無效時退回 Asia/Taipei。
    """
    try:
        target_tz = ZoneInfo(tz_name)
    except Exception:
        target_tz = ZoneInfo('Asia/Taipei')

    utc_tz = ZoneInfo('UTC')
    if ref is None:
        ref = datetime.utcnow()
    if ref.tzinfo is None:
        ref_utc = ref.replace(tzinfo=utc_tz)
    else:
        ref_utc = ref.astimezone(utc_tz)

    local_now = ref_utc.astimezone(target_tz)
    # DST 邊界：極少數時區當地零點不存在時，replace 的結果由 fold 規則決定；
    # 最多可能有 1 小時誤差，屬此 naive UTC 儲存模型下的已知限制。
    local_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    return local_start.astimezone(utc_tz).replace(tzinfo=None)


def local_month_start_utc(tz_name: str, ref: datetime = None) -> datetime:
    """回傳「該時區當地本月 1 日零點」對應的 naive UTC datetime（TZ-01）。

    DB 存 naive UTC，但統計的月界必須依使用者看到的當地日曆月切分，
    不能直接用 UTC 月初，否則跨時區企業在月初幾小時會被算到錯誤月份。

    ref 視為 naive UTC（預設 datetime.utcnow()）；時區名稱無效時退回 Asia/Taipei。
    """
    try:
        target_tz = ZoneInfo(tz_name)
    except Exception:
        target_tz = ZoneInfo('Asia/Taipei')

    utc_tz = ZoneInfo('UTC')
    if ref is None:
        ref = datetime.utcnow()
    if ref.tzinfo is None:
        ref_utc = ref.replace(tzinfo=utc_tz)
    else:
        ref_utc = ref.astimezone(utc_tz)

    local_now = ref_utc.astimezone(target_tz)
    # DST 邊界：沿用 local_day_start_utc 的限制與處理方式。
    local_start = local_now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return local_start.astimezone(utc_tz).replace(tzinfo=None)
