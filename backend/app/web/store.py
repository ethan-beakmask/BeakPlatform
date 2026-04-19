"""
BeakPlatform Store Web Routes
內部商場頁面
"""
from flask import Blueprint, render_template
from ..security.decorators import login_required

store_web_bp = Blueprint('store', __name__)


@store_web_bp.route('/')
@login_required
def index():
    """內部商場首頁"""
    return render_template('pages/store/index.html')
