"""
BeakMask Configuration
Security-focused configuration for different environments
"""
import os
from datetime import timedelta


class BaseConfig:
    """Base configuration with security defaults."""

    # Security: Never expose in production
    SECRET_KEY = os.getenv('SECRET_KEY')
    if not SECRET_KEY:
        raise ValueError("SECRET_KEY environment variable is required")

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
    SESSION_REDIS = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
    SESSION_PERMANENT = True
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_NAME = 'beakmask_session'

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

    # Rate Limiting
    RATELIMIT_ENABLED = os.getenv('RATELIMIT_ENABLED', 'true').lower() == 'true'
    RATELIMIT_STORAGE_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/1')
    RATELIMIT_STRATEGY = 'fixed-window'
    RATELIMIT_HEADERS_ENABLED = True
    RATELIMIT_DEFAULT = os.getenv('RATELIMIT_DEFAULT', '200 per day;50 per hour')
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

    # Use filesystem session in development (no Redis required)
    SESSION_TYPE = 'filesystem'
    SESSION_FILE_DIR = '/tmp/beakmask_sessions'


class ProductionConfig(BaseConfig):
    """Production configuration with strict security."""

    DEBUG = False
    TESTING = False

    # Enforce secure cookies
    SESSION_COOKIE_SECURE = True

    # Stricter session lifetime
    PERMANENT_SESSION_LIFETIME = timedelta(hours=4)


class TestingConfig(BaseConfig):
    """Testing configuration."""

    TESTING = True
    DEBUG = True

    SECRET_KEY = 'test-secret-key-for-testing-only'  # nosemgrep: beakmask-hardcoded-secret

    # Use DATABASE_URL from environment if available (CI uses PostgreSQL)
    # Fall back to SQLite for local quick tests (may not support all features like JSONB)
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', 'sqlite:///:memory:')

    # SQLite doesn't support pool options; PostgreSQL does
    _db_url = os.getenv('DATABASE_URL', '')
    if 'sqlite' in _db_url or not _db_url:
        SQLALCHEMY_ENGINE_OPTIONS = {}
    # else: inherit from BaseConfig

    # Use filesystem session for testing (no Redis dependency)
    SESSION_TYPE = 'filesystem'
    SESSION_FILE_DIR = '/tmp/beakmask_test_sessions'

    # Disable CSRF for testing
    WTF_CSRF_ENABLED = False

    # Disable rate limiting for tests
    RATELIMIT_ENABLED = False
