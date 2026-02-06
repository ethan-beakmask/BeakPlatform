"""
時區工具
提供 IANA 時區列表（按洲分組），供模板下拉選單使用
"""
from collections import defaultdict
from zoneinfo import available_timezones


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
