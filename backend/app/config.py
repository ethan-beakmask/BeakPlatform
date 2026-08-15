"""
BeakMask Configuration
Security-focused configuration for different environments
"""
import os
from datetime import timedelta

import redis


class BaseConfig:
    """Base configuration with security defaults."""

    # Security: Never expose in production
    SECRET_KEY = os.getenv('SECRET_KEY')
    if not SECRET_KEY:
        raise ValueError("SECRET_KEY environment variable is required")

    # NET-01: 可信前置代理白名單（逗號分隔 IP）
    # 只有直連來源落在此清單時，才採信 CF-Connecting-IP 這類由代理注入的 header。
    # 本平台的 Cloudflare 路徑為：
    #   訪客 -> Cloudflare edge -> cloudflared -> nginx 192.168.0.20:8080 -> nginx :7000
    # 故 ProxyFix 還原出的 remote_addr 對 tunnel 流量恆為 192.168.0.20，
    # 真實訪客 IP 只能從 CF-Connecting-IP 取得。清單外的來源一律以 remote_addr 為準，
    # 避免直連者自帶 header 偽造來源 IP。
    TRUSTED_PROXY_IPS = tuple(
        ip.strip() for ip in os.getenv('TRUSTED_PROXY_IPS', '192.168.0.20').split(',')
        if ip.strip()
    )

    # PF-83: OpenDefense 封鎖決策的額外保護網段（逗號分隔 IP 或 CIDR）
    OD_PROTECTED_EXTRA_NETWORKS = tuple(
        item.strip() for item in os.getenv('OD_PROTECTED_EXTRA_NETWORKS', '').split(',')
        if item.strip()
    )

    # PF-106: `.20` ClickHouse（secstack）唯讀連線 -- 資安案件跨系統關聯串查。
    # 認證一律走 header（X-ClickHouse-User / X-ClickHouse-Key），
    # 禁止 URL query 帶密碼（會明文過 LAN 並觸發 Suricata 告警）。
    # 三者任一未設值時 clickhouse_client 視為不可用（回 None），呼叫端據此隱藏
    # 相關分頁，不讓案件頁整頁 500。
    CLICKHOUSE_URL = os.getenv('CLICKHOUSE_URL', 'http://192.168.0.20:8123')
    CLICKHOUSE_DB = os.getenv('CLICKHOUSE_DB', 'secstack')
    CLICKHOUSE_USER = os.getenv('CLICKHOUSE_USER', '')
    CLICKHOUSE_PASSWORD = os.getenv('CLICKHOUSE_PASSWORD', '')

    # OpenDefense od-bridge（.20）唯讀查詢 -- 決策頁對帳 EDL / nftables 實際狀態。
    # bridge_client 連不上時回 None，呼叫端 fail-soft 顯示平台端記錄。
    OD_BRIDGE_URL = os.getenv('OD_BRIDGE_URL', 'http://192.168.0.20:8500')

    # Database
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
        'pool_size': 10,
        'max_overflow': 20,
    }

    # Session Security
    SESSION_TYPE = 'redis'
    _redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
    SESSION_REDIS = redis.from_url(_redis_url) if _redis_url else None
    SESSION_PERMANENT = True
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_NAME = 'beakmask_session'
    SESSION_COOKIE_PATH = os.getenv('APP_PREFIX', '/beakplatform') or '/'
    SESSION_KEY_PREFIX = 'session:'

    # CSRF Protection
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = 3600  # 1 hour

    # Security Headers
    SECURITY_HEADERS = {
        'X-Frame-Options': 'SAMEORIGIN',
        'X-Content-Type-Options': 'nosniff',
        'X-XSS-Protection': '1; mode=block',
        'Referrer-Policy': 'strict-origin-when-cross-origin',
    }

    # i18n (Flask-Babel)
    BABEL_DEFAULT_LOCALE = 'zh-TW'
    BABEL_DEFAULT_TIMEZONE = 'Asia/Taipei'
    BABEL_TRANSLATION_DIRECTORIES = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'translations'
    )

    # Rate Limiting — 分層速率限制
    # key_func: 已認證用 user secure_code，未認證用來源 IP
    # 解決企業 NAT 共用 IP 導致多人互相消耗額度的問題
    RATELIMIT_ENABLED = os.getenv('RATELIMIT_ENABLED', 'true').lower() == 'true'
    RATELIMIT_STORAGE_URI = os.getenv('REDIS_URL', 'redis://localhost:6379/1')
    RATELIMIT_STRATEGY = 'fixed-window'
    RATELIMIT_HEADERS_ENABLED = True
    RATELIMIT_IN_MEMORY_FALLBACK_ENABLED = True   # Redis 斷線時回退到 in-memory，避免全站 429
    RATELIMIT_SWALLOW_ERRORS = True                # in-memory 也失敗時放行，不阻擋請求

    # L3 預設 (已認證用戶 per-user / 未認證 per-IP 共用此上限)
    RATELIMIT_DEFAULT = os.getenv('RATELIMIT_DEFAULT', '200000 per day;6000 per minute')

    # L1 嚴格 — 敏感端點 (per-IP，防暴力破解)
    RATELIMIT_LOGIN = os.getenv('RATELIMIT_LOGIN', '5 per minute')
    RATELIMIT_FORGOT_PASSWORD = os.getenv('RATELIMIT_FORGOT_PASSWORD', '3 per hour')
    RATELIMIT_RESET_PASSWORD = os.getenv('RATELIMIT_RESET_PASSWORD', '5 per hour')


class DevelopmentConfig(BaseConfig):
    """Development configuration."""

    DEBUG = True

    # Relax some security for development
    SESSION_COOKIE_SECURE = False

    # Allow missing SECRET_KEY in dev
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')

    # Session: 繼承 BaseConfig 的 Redis session（不再用 cachelib）
    # /tmp 的 FileSystemCache 會被 systemd-tmpfiles 清除導致 session 遺失
    # 雙版本隔離: cookie name + Redis key prefix 區分，Redis DB 由 REDIS_URL 控制
    SESSION_COOKIE_NAME = 'beakmask_dev_session'
    SESSION_COOKIE_PATH = os.getenv('APP_PREFIX', '/beakplatform') or '/'
    SESSION_KEY_PREFIX = 'dev_session:'


class ProductionConfig(BaseConfig):
    """Production configuration with strict security."""

    DEBUG = False
    TESTING = False

    # Secure cookies (can be disabled via env for non-SSL staging)
    SESSION_COOKIE_SECURE = os.getenv('SESSION_COOKIE_SECURE', 'true').lower() == 'true'

    # Stricter session lifetime
    PERMANENT_SESSION_LIFETIME = timedelta(hours=4)


class TestingConfig(BaseConfig):
    """Testing configuration."""

    TESTING = True
    DEBUG = True

    SECRET_KEY = 'test-secret-key-for-testing-only'  # nosemgrep: beakplatform-hardcoded-secret

    # Use DATABASE_URL from environment if available (CI uses PostgreSQL)
    # Fall back to SQLite for local quick tests (may not support all features like JSONB)
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', 'sqlite:///:memory:')

    # SQLite doesn't support pool options; PostgreSQL does
    _db_url = os.getenv('DATABASE_URL', '')
    if 'sqlite' in _db_url or not _db_url:
        SQLALCHEMY_ENGINE_OPTIONS = {}
    # else: inherit from BaseConfig

    # Use cachelib filesystem session for testing (no Redis dependency)
    # 根據專案路徑衍生目錄名，避免多實例共用同一目錄導致權限衝突
    SESSION_TYPE = 'cachelib'
    from cachelib import FileSystemCache
    import hashlib
    _project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    _session_suffix = hashlib.md5(_project_root.encode()).hexdigest()[:8]
    SESSION_CACHELIB = FileSystemCache(f'/tmp/beakplatform_test_sessions_{_session_suffix}')

    # Disable CSRF for testing
    WTF_CSRF_ENABLED = False

    # Disable rate limiting for tests
    RATELIMIT_ENABLED = False
