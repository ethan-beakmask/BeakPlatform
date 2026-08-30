"""
流程節點企業授權管理頁。

提供系統管理員管理「受限流程節點型別 × 企業」授權矩陣的 HTML 頁面。
"""
from flask import Blueprint, render_template

from app.security.decorators import system_admin_required


node_grants_bp = Blueprint('node_grants', __name__)


@node_grants_bp.route('/')
@system_admin_required
def index():
    return render_template('pages/node_grants/index.html')
