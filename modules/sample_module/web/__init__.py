"""
Sample Module - Web Routes
"""
from flask import Blueprint, render_template_string
from app.security.decorators import login_required as security_login_required

# 建立 Web Blueprint
web_bp = Blueprint(
    'sample_module_web',
    __name__,
    url_prefix='/sample'
)

# 簡單的內嵌模板（正式模組應使用 templates/ 目錄）
DEMO_TEMPLATE = """
{% extends 'layouts/base.html' %}

{% block title %}範例模組 - BeakPlatform{% endblock %}

{% block content %}
<h1>範例模組</h1>
<p>這是一個用於驗證模組化機制的範例模組。</p>

<h2>模組資訊</h2>
<table border="1" cellpadding="8" cellspacing="0">
    <tr><td>模組名稱</td><td>{{ module_info.display_name }}</td></tr>
    <tr><td>版本</td><td>{{ module_info.version }}</td></tr>
    <tr><td>描述</td><td>{{ module_info.description }}</td></tr>
</table>

<h2>平台 API 測試</h2>
<table border="1" cellpadding="8" cellspacing="0">
    <tr><td>當前用戶</td><td>{{ user_info.display_name }}</td></tr>
    <tr><td>所屬企業</td><td>{{ org_info.name if org_info else '無' }}</td></tr>
    <tr><td>權限檢查 (sample_module.view)</td><td>{{ '有' if has_view else '無' }}</td></tr>
</table>

<h2>API 端點</h2>
<ul>
    <li><a href="/api/sample-module/info" target="_blank">/api/sample-module/info</a> - 模組資訊</li>
    <li><a href="/api/sample-module/demo" target="_blank">/api/sample-module/demo</a> - 展示 API</li>
</ul>

<p style="margin-top: 20px; color: #666;">
    <em>此模組僅供測試，可在正式環境中移除。</em>
</p>
{% endblock %}
"""


@web_bp.route('/')
@security_login_required
def index():
    """範例模組首頁"""
    from .. import MODULE_INFO
    from app.platform.auth import current_user, has_permission
    from app.platform.data import get_current_org

    return render_template_string(
        DEMO_TEMPLATE,
        module_info=MODULE_INFO,
        user_info=current_user,
        org_info=get_current_org(),
        has_view=has_permission('sample_module.view')
    )
