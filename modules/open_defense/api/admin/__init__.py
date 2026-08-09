"""
OpenDefense Module - Admin API

供 UI 呼叫的內部 API,**不是**對外契約 API(那組在 ../intake.py / decisions.py /
service_accounts.py,鎖 webhook_hmac / SA JWT)。

這組鎖 admin_required(企業管理員 session),回傳 JSON 給 Alpine.js 用。
"""
from flask import Blueprint

admin_bp = Blueprint(
    'open_defense_admin_api',
    __name__,
    url_prefix='/api/open_defense/admin',
)

from . import dashboard      # noqa: E402,F401
from . import intake_keys    # noqa: E402,F401
from . import service_accounts  # noqa: E402,F401
from . import decisions      # noqa: E402,F401
from . import routing_rules  # noqa: E402,F401
