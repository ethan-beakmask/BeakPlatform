"""System-administrator OIDC client management page."""
from flask import Blueprint, render_template

from app.security.decorators import system_admin_required


oidc_clients_bp = Blueprint('oidc_clients', __name__)


@oidc_clients_bp.route('/')
@system_admin_required
def index():
    return render_template('pages/oidc_clients/index.html')
