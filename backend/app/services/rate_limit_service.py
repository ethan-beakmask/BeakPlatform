"""
BeakPlatform Rate Limit Service
認證速率限制服務 - DB 可設定、username+IP key、POST only
"""
import logging
import re

from flask import current_app, request
from flask_limiter.util import get_remote_address

from ..models.system_setting import SystemSetting
from ..models.organization import Organization

logger = logging.getLogger(__name__)

# 五個分類定義
RATE_LIMIT_CATEGORIES = {
    'shared_login': {
        'label': '通用登入 (/auth/login)',
        'db_key': 'ratelimit_shared_login',
        'env_key': 'RATELIMIT_LOGIN',
        'default': '20 per 10 minutes',
    },
    'org_login': {
        'label': '企業員工登入 (/auth/org/*/login)',
        'db_key': 'ratelimit_org_login',
        'env_key': 'RATELIMIT_LOGIN',
        'default': '20 per 10 minutes',
    },
    'vendor_login': {
        'label': '廠商登入 (/auth/org/*/public/login)',
        'db_key': 'ratelimit_vendor_login',
        'env_key': 'RATELIMIT_LOGIN',
        'default': '20 per 10 minutes',
    },
    'forgot_password': {
        'label': '忘記密碼',
        'db_key': 'ratelimit_forgot_password',
        'env_key': 'RATELIMIT_FORGOT_PASSWORD',
        'default': '10 per 10 minutes',
    },
    'reset_password': {
        'label': '密碼重設驗證',
        'db_key': 'ratelimit_reset_password',
        'env_key': 'RATELIMIT_RESET_PASSWORD',
        'default': '10 per 10 minutes',
    },
}

# 驗證 rate limit 格式: "N per [M] unit[s]"
RATE_LIMIT_PATTERN = re.compile(
    r'^\d+\s+per\s+(\d+\s+)?(second|minute|hour|day)s?$',
    re.IGNORECASE
)


def validate_rate_limit_string(value: str) -> bool:
    """驗證 rate limit 字串格式是否合法"""
    return bool(RATE_LIMIT_PATTERN.match(value.strip()))


# 企業可自訂的分類（排除 shared_login、reset_password -- 系統級）
ORG_RATE_LIMIT_CATEGORIES = {
    k: v for k, v in RATE_LIMIT_CATEGORIES.items()
    if k in ('org_login', 'vendor_login', 'forgot_password')
}


class RateLimitService:
    """認證速率限制服務 -- DB 設定 + 快取"""

    _cached_settings = None  # dict: {category: value_string}
    _cache_miss_count = 0

    @classmethod
    def get_limit(cls, category: str) -> str:
        """取得某分類的限制值（帶快取）。

        Fallback chain: 快取 -> DB -> .env config -> 硬編碼預設值
        """
        cls._cache_miss_count += 1

        if cls._cached_settings is None or cls._cache_miss_count >= 100:
            cls._refresh_cache()

        if cls._cached_settings and category in cls._cached_settings:
            return cls._cached_settings[category]

        # fallback: 不應走到這裡，但以防萬一
        cat_def = RATE_LIMIT_CATEGORIES.get(category)
        if cat_def:
            return cat_def['default']
        return '20 per 10 minutes'

    @classmethod
    def _refresh_cache(cls):
        """從 DB 刷新快取，DB 無值時 fallback 到 .env config"""
        cls._cached_settings = {}
        cls._cache_miss_count = 0

        for category, cat_def in RATE_LIMIT_CATEGORIES.items():
            db_value = None
            try:
                db_value = SystemSetting.get(cat_def['db_key'])
            except Exception:
                pass

            if db_value:
                cls._cached_settings[category] = db_value
            else:
                # fallback: .env config -> hardcoded default
                env_value = current_app.config.get(cat_def['env_key'])
                cls._cached_settings[category] = env_value or cat_def['default']

    @classmethod
    def get_all_settings(cls) -> list:
        """取得全部分類設定（供 API 回傳）"""
        result = []
        for category, cat_def in RATE_LIMIT_CATEGORIES.items():
            db_value = None
            try:
                db_value = SystemSetting.get(cat_def['db_key'])
            except Exception:
                pass

            env_value = current_app.config.get(cat_def['env_key'])

            if db_value:
                source = 'db'
                value = db_value
            elif env_value:
                source = 'env'
                value = env_value
            else:
                source = 'default'
                value = cat_def['default']

            result.append({
                'key': category,
                'label': cat_def['label'],
                'value': value,
                'source': source,
                'default': cat_def['default'],
            })
        return result

    @classmethod
    def set_limit(cls, category: str, value: str, updated_by: str) -> bool:
        """設定某分類的限制值，寫入 DB 並清快取"""
        cat_def = RATE_LIMIT_CATEGORIES.get(category)
        if not cat_def:
            return False

        SystemSetting.set(
            key=cat_def['db_key'],
            value=value.strip(),
            value_type='string',
            description=cat_def['label'],
            category='security',
            updated_by=updated_by,
        )
        cls.invalidate_cache()
        return True

    @classmethod
    def invalidate_cache(cls):
        """強制清快取"""
        cls._cached_settings = None
        cls._cache_miss_count = 0

    # --- 企業級設定 ---

    @classmethod
    def get_org_limit(cls, category: str, domain_name: str) -> str:
        """取得企業級限制值。

        Fallback chain: 企業設定 -> 系統設定 -> .env -> 硬編碼預設
        """
        if category not in ORG_RATE_LIMIT_CATEGORIES:
            return cls.get_limit(category)

        if domain_name:
            try:
                org = Organization.query.filter_by(
                    domain_name=domain_name.lower(),
                    is_deleted=False,
                ).first()
                if org:
                    org_value = org.get_setting(f'ratelimit_{category}')
                    if org_value and validate_rate_limit_string(org_value):
                        return org_value
            except Exception:
                pass

        return cls.get_limit(category)

    @classmethod
    def get_org_settings(cls, org) -> list:
        """取得企業的 3 個速率限制設定（含 fallback 資訊）"""
        result = []
        for category, cat_def in ORG_RATE_LIMIT_CATEGORIES.items():
            org_value = org.get_setting(f'ratelimit_{category}') if org else None
            system_value = cls.get_limit(category)

            if org_value and validate_rate_limit_string(org_value):
                source = 'org'
                value = org_value
            else:
                source = 'system'
                value = system_value

            result.append({
                'key': category,
                'label': cat_def['label'],
                'value': value,
                'source': source,
                'system_default': system_value,
            })
        return result

    @classmethod
    def set_org_limit(cls, org, category: str, value: str) -> bool:
        """寫入企業級限制值到 Organization.settings"""
        if category not in ORG_RATE_LIMIT_CATEGORIES:
            return False
        org.set_setting(f'ratelimit_{category}', value.strip())
        return True

    @classmethod
    def clear_org_limit(cls, org, category: str) -> bool:
        """清除企業級覆寫，回歸系統預設"""
        if category not in ORG_RATE_LIMIT_CATEGORIES:
            return False
        settings = org.get_settings()
        key = f'ratelimit_{category}'
        if key in settings:
            del settings[key]
            import json
            org.settings = json.dumps(settings, ensure_ascii=False)
        return True


def make_auth_key_func(identifier_field: str, domain_from_url: bool = False):
    """產生 rate limit key function 工廠。

    Args:
        identifier_field: form 欄位名（'account', 'username', 'email', 'code'）
        domain_from_url: True 時從 URL path 的 <domain_name> 組合 identifier

    Returns:
        key function: '{identifier}:{IP}' 或 fallback '{IP}'
    """
    def key_func():
        ip = get_remote_address()

        if request.method != 'POST':
            return ip

        # 從 form 或 JSON 提取 identifier
        identifier = ''
        if request.is_json:
            data = request.get_json(silent=True) or {}
            identifier = data.get(identifier_field, '').strip().lower()
        else:
            identifier = request.form.get(identifier_field, '').strip().lower()

        # 組合 domain（org 路由：username -> username@domain）
        if domain_from_url and identifier and '@' not in identifier:
            domain = request.view_args.get('domain_name', '')
            if domain:
                identifier = f"{identifier}@{domain.lower()}"

        if identifier:
            return f"{identifier}:{ip}"
        return ip

    return key_func
