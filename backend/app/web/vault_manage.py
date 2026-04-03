"""
BeakPlatform Vault Management UI
BeakSeal 加密保險庫管理頁面

路徑：/vault/*
權限：system_admin_required
"""
import logging

from flask import Blueprint, render_template

from ..security.decorators import system_admin_required

logger = logging.getLogger(__name__)

vault_manage_bp = Blueprint('vault_manage', __name__)


@vault_manage_bp.route('/')
@system_admin_required
def index():
    """BeakSeal 管理主頁"""
    return render_template('pages/vault/index.html')
