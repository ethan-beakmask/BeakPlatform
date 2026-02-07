"""
BeakPlatform Public Routes
對外公開區域 - 無需登入即可存取
"""
from flask import Blueprint, render_template

from ..security.decorators import public_route

public_bp = Blueprint('public', __name__)


@public_bp.route('/')
@public_route
def index():
    """公開區首頁"""
    return render_template('pages/public/index.html')


@public_bp.route('/about')
@public_route
def about():
    """關於我們"""
    return render_template('pages/public/about.html')
