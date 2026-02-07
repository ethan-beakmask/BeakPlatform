"""
BeakPlatform Security Headers
安全 HTTP 標頭設定
"""
from flask import Flask, Response


def register_security_headers(app: Flask) -> None:
    """
    註冊安全 HTTP 標頭。
    在每個回應中加入安全相關的 HTTP 標頭。
    """

    @app.after_request
    def add_security_headers(response: Response) -> Response:
        """
        添加安全 HTTP 標頭。

        Headers:
        - X-Frame-Options: 防止 Clickjacking
        - X-Content-Type-Options: 防止 MIME sniffing
        - X-XSS-Protection: XSS 保護 (legacy browsers)
        - Referrer-Policy: 控制 Referer 資訊
        - Content-Security-Policy: 內容安全政策
        - Strict-Transport-Security: 強制 HTTPS
        - Permissions-Policy: 控制瀏覽器功能
        """
        # Prevent Clickjacking
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'

        # Prevent MIME sniffing
        response.headers['X-Content-Type-Options'] = 'nosniff'

        # XSS Protection (for legacy browsers)
        response.headers['X-XSS-Protection'] = '1; mode=block'

        # Referrer Policy
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'

        # Content Security Policy
        # Note: Adjust based on your frontend requirements
        csp_directives = [
            "default-src 'self'",
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'",  # Adjust for frontend framework
            "style-src 'self' 'unsafe-inline'",
            "img-src 'self' data: https:",
            "font-src 'self'",
            "connect-src 'self'",
            "worker-src 'self' blob:",  # ACE editor Web Worker 需要 blob:
            "frame-ancestors 'self'",
            "form-action 'self'",
            "base-uri 'self'",
        ]
        response.headers['Content-Security-Policy'] = '; '.join(csp_directives)

        # HSTS - only in production with HTTPS
        if not app.debug:
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'

        # Permissions Policy (formerly Feature-Policy)
        permissions = [
            'geolocation=()',
            'microphone=()',
            'camera=()',
            'payment=()',
            'usb=()',
        ]
        response.headers['Permissions-Policy'] = ', '.join(permissions)

        # Remove Server header (if possible)
        response.headers.pop('Server', None)

        return response
