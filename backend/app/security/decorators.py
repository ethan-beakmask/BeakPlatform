"""
BeakMask Security Decorators
統一認證裝飾器 - 所有路由必須使用

[標準 AUTH-02] 統一認證 Decorator
所有路由必須使用以下裝飾器之一：
- @public_route: 公開路由，不需登入
- @login_required: 需要登入
- @admin_required: 需要企業管理員權限
- @system_admin_required: 需要系統管理員權限
- @webhook_hmac_required: 外部 webhook(HMAC 簽章驗證)
"""
import logging
from functools import wraps
from flask import abort, g, request, jsonify
from flask_login import current_user

logger = logging.getLogger(__name__)


def public_route(f):
    """
    標記為公開路由，不需要登入。
    此路由會被加入白名單，跳過全域認證檢查。
    """
    f._public_route = True

    @wraps(f)
    def decorated_function(*args, **kwargs):
        return f(*args, **kwargs)

    return decorated_function


def login_required(f):
    """
    需要登入的路由。
    檢查：
    1. 用戶已登入
    2. 用戶帳號未被停用
    """
    f._login_required = True

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            abort(401, description="Authentication required")

        if not current_user.is_active:
            abort(403, description="Account is disabled")

        # Set tenant context
        g.current_org_secure_code = current_user.org_secure_code

        return f(*args, **kwargs)

    return decorated_function


def admin_required(f):
    """
    需要企業管理員權限的路由。
    檢查：
    1. 用戶已登入
    2. 用戶帳號未被停用
    3. 用戶具有企業管理員角色
    """
    f._admin_required = True

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            abort(401, description="Authentication required")

        if not current_user.is_active:
            abort(403, description="Account is disabled")

        if not (current_user.is_org_admin or current_user.is_system_admin):
            abort(403, description="Admin privileges required")

        # Set tenant context
        g.current_org_secure_code = current_user.org_secure_code

        return f(*args, **kwargs)

    return decorated_function


def system_admin_required(f):
    """
    需要系統管理員權限的路由。
    檢查：
    1. 用戶已登入
    2. 用戶帳號未被停用
    3. 用戶具有系統管理員角色
    """
    f._system_admin_required = True

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            abort(401, description="Authentication required")

        if not current_user.is_active:
            abort(403, description="Account is disabled")

        if not current_user.is_system_admin:
            abort(403, description="System admin privileges required")

        # System admin can access all tenants
        # But still set context for audit logging
        g.current_org_secure_code = getattr(current_user, 'org_secure_code', None)

        return f(*args, **kwargs)

    return decorated_function


def page_keys_required(menu_code: str):
    """
    頁面資料 API 與所屬頁面共用雙鑰匙（選單即授權，PERM-01 試點 2026-07-16）。

    用途：web 頁面本身由 PageRoleGuard（before_request）依雙鑰匙把關，
    但頁面消費的 /api/ 路徑在 PageRoleGuard 的 SKIP_PREFIXES 內——
    掛此裝飾器讓資料 API 與所屬選單頁吃同一組鑰匙，
    避免「選單看得見、頁面開得了、資料卻 403」的不同步。

    檢查語意與 PageRoleGuard.check_access 一致：
    1. 登入 + 帳號啟用
    2. SYSTEM_ADMIN / ORG_ADMIN / 原始管理員 → bypass（同 PageRoleGuard）
    3. 其餘（EMPLOYEE/EXTERNAL）：
       鑰匙1 = 該選單對用戶 user_type 有 MenuPermission
       鑰匙2 = 用戶持有該選單在其企業的任一所需角色
    4. 失敗回 403（API 語境，不做 PageRoleGuard 的強制登出）

    Usage:
        @admin_bp.route('/dashboard/stats')
        @page_keys_required('open_defense.dashboard')
        def dashboard_stats(): ...
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                abort(401, description="Authentication required")

            if not current_user.is_active:
                abort(403, description="Account is disabled")

            # Set tenant context
            g.current_org_secure_code = current_user.org_secure_code

            if (current_user.is_system_admin or current_user.is_org_admin
                    or getattr(current_user, 'is_original_admin', False)):
                return f(*args, **kwargs)

            # 延遲 import 避免循環相依
            from sqlalchemy import text
            from .. import db
            from ..models.menu_item import MenuItem
            from ..services.page_role_guard import PageRoleGuard

            # RLS context: 選單項目屬系統企業
            try:
                db.session.execute(
                    text("SET LOCAL app.is_system_admin = 'true'"))
            except Exception:
                pass

            item = MenuItem.query.filter_by(
                code=menu_code, is_deleted=False, is_active=True
            ).first()
            if not item:
                # fail-closed：宣告的選單不存在視為設定錯誤，一律擋下
                logger.error(
                    f"page_keys_required: menu '{menu_code}' not found "
                    f"(route={request.path})"
                )
                abort(403, description="Access denied")

            # 鑰匙1: user_type
            permitted = PageRoleGuard._filter_by_user_type(
                [item], str(current_user.user_type))
            if not permitted:
                abort(403, description="Access denied")

            # 鑰匙2: 角色（無角色設定 = fail-closed）
            required = PageRoleGuard._get_required_roles(
                item.secure_code, current_user.org_secure_code)
            if not required:
                abort(403, description="Access denied")

            user_roles = PageRoleGuard._get_user_roles(
                current_user.secure_code)
            if not (user_roles & required):
                abort(403, description="Access denied")

            return f(*args, **kwargs)

        return decorated_function
    return decorator


def module_access_required(module_code: str, check_acl: bool = True):
    """
    模組使用權路由檢查裝飾器。

    檢查順序：
    1. 登入 + 帳號啟用
    2. 合約驗證 → 企業須有該模組的有效合約
    3. 企業管理員 → 放行（通過合約驗證後）
    4. 模組 ACL 檢查（check_acl=True 時）

    注意：SYSTEM_ADMIN 不享有特權，與其他用戶相同流程。

    Args:
        module_code: 模組代碼 (如 'form_workflow', 'nocode_builder')
        check_acl: 是否檢查模組 ACL（終端用戶頁面可設 False，僅驗合約）

    Usage:
        @module_access_required('nocode_builder')           # 合約 + ACL
        @module_access_required('form_workflow', False)      # 僅合約
    """
    def decorator(f):
        f._module_access_required = module_code

        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                abort(401, description="Authentication required")

            if not current_user.is_active:
                abort(403, description="Account is disabled")

            # [SEC-02] SYSTEM_ADMIN 不享有特權，與其他用戶相同流程
            # 已移除: 系統管理員自動放行

            # 合約驗證（所有用戶皆須通過）
            from ..services.module_access_service import ModuleAccessService
            if not ModuleAccessService.check_module_contract(current_user, module_code):
                abort(403, description=f"No contract for module: {module_code}")

            # 企業管理員放行（已通過合約驗證）
            if getattr(current_user, 'is_org_admin', False):
                g.current_org_secure_code = current_user.org_secure_code
                return f(*args, **kwargs)

            # 一般用戶: 檢查模組 ACL（若啟用）
            if check_acl:
                if not ModuleAccessService.check_user_access(current_user, module_code):
                    abort(403, description=f"No access to module: {module_code}")

            g.current_org_secure_code = current_user.org_secure_code
            return f(*args, **kwargs)

        return decorated_function

    return decorator


# =============================================================================
# Webhook HMAC 驗證(外部安全堆疊事件 webhook 用)
# =============================================================================

def _webhook_error(code: str, status: int = 401):
    """webhook 統一錯誤回應格式"""
    return jsonify({'error': code}), status


def _verify_platform_api_key(key_id: str, timestamp: str,
                             signature_header: str, tag: str):
    """
    平台 ApiKey HMAC 驗證核心(供 @api_key_hmac_required 與
    @webhook_hmac_required 共用)。

    驗證順序(先快後慢,失敗早返回):
      1. headers 存在
      2. timestamp 在容忍範圍(±300 sec)
      3. key_id 對應 active(未暫停/撤銷/過期) ApiKey
      4. allowed_ips 白名單(有設定才檢查)
      5. 解密 secret -> compare_digest 驗章

    Returns:
        ApiKey record;失敗回 None(呼叫端一律回 401 auth_failed)
    """
    if not key_id or not timestamp or not signature_header:
        logger.warning('%s: missing headers path=%s ip=%s',
                       tag, request.path, request.remote_addr)
        return None

    from .hmac_verifier import is_timestamp_valid, verify_signature
    if not is_timestamp_valid(timestamp):
        logger.warning('%s: timestamp out of range key_id=%s ts=%s',
                       tag, key_id, timestamp)
        return None

    from ..services import api_key_service
    key_record = api_key_service.lookup_active_key(key_id)
    if key_record is None:
        logger.warning('%s: key not found/inactive key_id=%s ip=%s',
                       tag, key_id, request.remote_addr)
        return None

    if not api_key_service.check_source_ip(key_record, request.remote_addr):
        logger.warning('%s: source ip not allowed key_id=%s ip=%s',
                       tag, key_id, request.remote_addr)
        return None

    try:
        secret = api_key_service.decrypt_secret(key_record)
    except Exception as exc:
        logger.error('%s: decrypt failed key_id=%s err=%s',
                     tag, key_id, exc)
        return None

    body = request.get_data(cache=True) or b''
    if not verify_signature(secret, timestamp, body, signature_header):
        logger.warning('%s: signature mismatch key_id=%s ip=%s',
                       tag, key_id, request.remote_addr)
        return None

    return key_record


def webhook_hmac_required(f):
    """
    HMAC 簽章驗證裝飾器(對外 webhook 入口用,P2 起改讀平台 ApiKey)。

    對外契約: docs/integrations/open_defense_contract.md §3.1, §4.2
    規格: docs/API_KEY_TRIGGER_SPEC.md(P2:OdIntakeKey 遷移平台 ApiKey)

    雙軌收頭(擇一,X-BP-* 優先):
      X-BP-Key-Id / X-BP-Timestamp / X-BP-Signature   (平台標準)
      X-OD-Key-Id / X-OD-Timestamp / X-OD-Signature   (相容舊契約,deprecated)

    簽章格式(兩組相同):
      sha256=<hex(HMAC-SHA256(key_secret, "{ts}\n{body}"))>

    驗證一律走平台 ApiKey(api_keys 表),舊 OdIntakeKey 已由
    migration 079 遷入。失敗一律 401 auth_failed(不區分原因)。

    成功時注入:
      g.api_key         = ApiKey 物件
      g.api_key_org     = org_secure_code

    被裝飾的 view function 自動視為 public_route(跳過全域認證攔截)。
    """
    f._public_route = True
    f._webhook_hmac_required = True

    @wraps(f)
    def decorated_function(*args, **kwargs):
        key_id = request.headers.get('X-BP-Key-Id', '').strip()
        if key_id:
            timestamp = request.headers.get('X-BP-Timestamp', '').strip()
            signature_header = request.headers.get('X-BP-Signature', '').strip()
        else:
            # 舊契約 headers(deprecated,保留相容)
            key_id = request.headers.get('X-OD-Key-Id', '').strip()
            timestamp = request.headers.get('X-OD-Timestamp', '').strip()
            signature_header = request.headers.get('X-OD-Signature', '').strip()

        key_record = _verify_platform_api_key(
            key_id, timestamp, signature_header, 'webhook_hmac')
        if key_record is None:
            return _webhook_error('auth_failed')

        g.api_key = key_record
        g.api_key_org = key_record.org_secure_code

        from ..services import api_key_service
        try:
            api_key_service.touch_last_used(key_record)
        except Exception as exc:
            logger.warning('webhook_hmac: touch_last_used failed: %s', exc)

        logger.info(
            'webhook_hmac: verified key_id=%s org=%s path=%s',
            key_id, key_record.org_secure_code, request.path,
        )
        return f(*args, **kwargs)

    # CSRF exempt:webhook 由外部系統呼叫,沒有 session,自然無法帶 CSRF token。
    # 安全性由 HMAC 簽章 + timestamp 防 replay 取代 CSRF。
    try:
        from .. import csrf
        decorated_function = csrf.exempt(decorated_function)
    except Exception as exc:
        logger.warning('webhook_hmac: csrf.exempt 註冊失敗: %s', exc)

    return decorated_function


def api_key_hmac_required(f):
    """
    平台級 API Key HMAC 簽章驗證裝飾器(外部發動閘道用)。

    規格: docs/API_KEY_TRIGGER_SPEC.md §2

    必要 headers:
      X-BP-Key-Id     : api key 公開識別碼(ak_ 開頭)
      X-BP-Timestamp  : Unix 秒,±300 秒內有效
      X-BP-Signature  : sha256=<hex(HMAC-SHA256(key_secret, "{ts}\n{body}"))>

    驗證順序(先快後慢,失敗早返回):
      1. headers 存在
      2. timestamp 在容忍範圍(±300 sec)
      3. key_id 對應 active(未暫停/撤銷/過期) ApiKey
      4. allowed_ips 白名單(有設定才檢查)
      5. 解密 secret -> compare_digest 驗章

    失敗一律 401 auth_failed,不區分原因(避免探測)。

    成功時注入:
      g.api_key      = ApiKey 物件
      g.api_key_org  = org_secure_code

    被裝飾的 view function 自動視為 public_route(跳過全域認證攔截)。
    """
    f._public_route = True
    f._api_key_hmac_required = True

    @wraps(f)
    def decorated_function(*args, **kwargs):
        key_id = request.headers.get('X-BP-Key-Id', '').strip()
        timestamp = request.headers.get('X-BP-Timestamp', '').strip()
        signature_header = request.headers.get('X-BP-Signature', '').strip()

        key_record = _verify_platform_api_key(
            key_id, timestamp, signature_header, 'api_key_hmac')
        if key_record is None:
            return _webhook_error('auth_failed')

        g.api_key = key_record
        g.api_key_org = key_record.org_secure_code

        from ..services import api_key_service
        try:
            api_key_service.touch_last_used(key_record)
        except Exception as exc:
            logger.warning('api_key_hmac: touch_last_used failed: %s', exc)

        logger.info(
            'api_key_hmac: verified key_id=%s org=%s path=%s',
            key_id, key_record.org_secure_code, request.path,
        )
        return f(*args, **kwargs)

    # CSRF exempt:外部系統呼叫,沒有 session,安全性由 HMAC + timestamp 取代。
    try:
        from .. import csrf
        decorated_function = csrf.exempt(decorated_function)
    except Exception as exc:
        logger.warning('api_key_hmac: csrf.exempt 註冊失敗: %s', exc)

    return decorated_function


# =============================================================================
# Service Account JWT 驗證(OpenDefense 執行端用)
# =============================================================================

def service_account_required(f):
    """
    驗 Authorization: Bearer <jwt> 並注入 g.service_account。

    對外契約 §3.2:JWT HS256,15 分鐘有效,簽章 secret = OD_SA_JWT_SECRET。

    成功時注入:
      g.service_account       = OdServiceAccount 物件
      g.service_account_claims = JWT decoded claims dict

    被裝飾 view function 自動視為 public_route(JWT 自身就是憑證,無需 session)。
    """
    f._public_route = True
    f._service_account_required = True

    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth = request.headers.get('Authorization', '').strip()
        if not auth.startswith('Bearer '):
            return jsonify({'error': 'auth_failed',
                            'message': '缺 Authorization Bearer token'}), 401

        token = auth[len('Bearer '):].strip()

        from modules.open_defense.services.service_account_service import (
            decode_jwt, lookup_active_sa, ServiceAccountError,
        )
        try:
            claims = decode_jwt(token)
        except ServiceAccountError as exc:
            logger.warning('service_account: jwt decode fail code=%s ip=%s',
                           exc.code, request.remote_addr)
            return jsonify({'error': exc.code, 'message': str(exc)}), 401

        sa_id = claims.get('sub')
        record = lookup_active_sa(sa_id)
        if record is None:
            logger.warning('service_account: sa not found / inactive sa_id=%s',
                           sa_id)
            return jsonify({'error': 'sa_inactive',
                            'message': 'service account 已停用或不存在'}), 401

        # 防護:JWT claim 中的 org 必須與 DB 一致(SA 換 org 後舊 token 立即失效)
        if claims.get('org') != record.org_secure_code:
            logger.warning(
                'service_account: org mismatch claim=%s db=%s sa_id=%s',
                claims.get('org'), record.org_secure_code, sa_id,
            )
            return jsonify({'error': 'sa_changed',
                            'message': 'service account 已變更,請重新登入'}), 401

        g.service_account = record
        g.service_account_claims = claims
        return f(*args, **kwargs)

    # CSRF exempt:外部端點,以 JWT 為憑證
    try:
        from .. import csrf
        decorated_function = csrf.exempt(decorated_function)
    except Exception as exc:
        logger.warning('service_account_required: csrf.exempt 註冊失敗: %s', exc)

    return decorated_function
