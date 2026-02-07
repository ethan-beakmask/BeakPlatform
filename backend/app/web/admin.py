"""
BeakPlatform Admin Routes
企業管理員專區 - 各企業的管理功能

路徑：/admin/*
權限：admin_required (企業管理員)
"""
from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import current_user

from ..security.decorators import admin_required
from ..utils.timezone import get_timezone_choices
from .. import db

admin_bp = Blueprint('admin', __name__)


@admin_bp.route('/')
@admin_required
def index():
    """企業管理首頁"""
    return render_template('pages/admin/index.html')


@admin_bp.route('/settings')
@admin_required
def settings():
    """
    系統設定頁面 (企業級)

    企業管理員可設定：
    - 企業基本資訊
    - 選單配置
    - 通知設定
    - 整合設定
    """
    return render_template(
        'pages/admin/settings.html',
        timezone_choices=get_timezone_choices()
    )


@admin_bp.route('/settings/general', methods=['GET', 'POST'])
@admin_required
def settings_general():
    """
    一般設定頁面

    包含：
    - 允許用戶修改自己的資料
    """
    org = current_user.organization

    if request.method == 'POST':
        # 取得表單值
        allow_user_self_edit = request.form.get('allow_user_self_edit') == '1'

        # 儲存設定
        org.set_setting('allow_user_self_edit', allow_user_self_edit)
        db.session.commit()

        flash('設定已儲存', 'success')
        return redirect(url_for('admin.settings_general'))

    # 取得目前設定
    settings = org.get_settings()

    return render_template(
        'pages/admin/settings_general.html',
        settings=settings
    )
