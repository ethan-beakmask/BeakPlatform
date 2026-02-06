"""
BeakPlatform - I18n Mixin

提供 name + name_i18n JSONB 多語系支援的通用 Mixin。

使用方式：
    class JobTitle(TenantBaseModel, I18nMixin):
        name = Column(String(100), nullable=False)
        name_i18n = Column(JSONB, nullable=True, default=dict)
        name_en = Column(String(100), nullable=True)  # 舊欄位 (向下相容)

I18nMixin 提供：
    - get_localized_name(locale) — 取得本地化名稱
    - set_localized_name(locale, value) — 設定本地化名稱
"""
from flask import g


class I18nMixin:
    """
    多語系 Mixin

    需搭配 Model 上的以下欄位使用：
    - name: 主要名稱 (zh-TW)
    - name_i18n: JSONB 多語系名稱 (可選)
    """

    # 子類可覆寫，用於向下相容舊的獨立欄位
    _I18N_LEGACY_FIELD_MAP = {
        # 'en': 'name_en',
    }

    def get_localized_name(self, locale: str = None) -> str:
        """
        取得本地化名稱

        查找順序：
        1. name_i18n[locale]  (JSONB 新格式)
        2. 舊欄位  (向下相容)
        3. name (zh-TW 原文)

        Args:
            locale: 語系代碼，None 則從 g.locale 取

        Returns:
            本地化名稱
        """
        if locale is None:
            locale = getattr(g, 'locale', 'zh-TW')

        # zh-TW 直接返回 name
        if locale == 'zh-TW':
            return self.name

        # 1. 查 JSONB
        name_i18n = getattr(self, 'name_i18n', None)
        if name_i18n and isinstance(name_i18n, dict):
            value = name_i18n.get(locale)
            if value:
                return value

        # 2. Fallback 舊欄位
        legacy_field = self._I18N_LEGACY_FIELD_MAP.get(locale)
        if legacy_field:
            value = getattr(self, legacy_field, None)
            if value:
                return value

        # 3. Fallback name
        return self.name

    def set_localized_name(self, locale: str, value: str) -> None:
        """
        設定本地化名稱

        Args:
            locale: 語系代碼
            value: 翻譯值，空字串則刪除該語系
        """
        if locale == 'zh-TW':
            self.name = value
            return

        name_i18n = getattr(self, 'name_i18n', None) or {}
        if not isinstance(name_i18n, dict):
            name_i18n = {}

        if value:
            name_i18n[locale] = value
        else:
            name_i18n.pop(locale, None)

        self.name_i18n = name_i18n
