"""
BeakPlatform - i18n 工具模組

提供 Flask-Babel locale selector 和相關工具函式。

BeakPlatform 內部使用 BCP 47 格式 (zh-TW, zh-CN)，
但 Babel 需要底線格式 (zh_TW, zh_CN)。
本模組負責兩者之間的轉換。
"""
from flask import g


# 平台支援的語言 (BCP 47 格式)
SUPPORTED_LANGUAGES = {
    'zh-TW': '繁體中文',
    'zh-CN': '简体中文',
    'en': 'English',
    'ja': '日本語',
}

# BCP 47 → Babel locale 映射
_BABEL_LOCALE_MAP = {
    'zh-TW': 'zh_Hant_TW',
    'zh-CN': 'zh_CN',
    'en': 'en',
    'ja': 'ja',
}


def get_locale():
    """
    Flask-Babel locale selector

    優先級：g.locale (由 auth_interceptor 設定) > fallback 'zh-TW'

    Returns:
        Babel 可識別的 locale 字串
    """
    locale = getattr(g, 'locale', 'zh-TW')
    # 轉換為 Babel 格式
    return _BABEL_LOCALE_MAP.get(locale, locale.replace('-', '_'))
