"""
OpenDefense Module - API Routes

由 module_loader 自動掛載。對外契約: docs/integrations/open_defense_contract.md
"""
from flask import Blueprint

api_bp = Blueprint(
    'open_defense_api',
    __name__,
    url_prefix='/api/open_defense',
)

# 匯入 view 子模組,讓 route 註冊到 api_bp
from . import intake             # noqa: E402,F401
from . import service_accounts   # noqa: E402,F401
from . import decisions          # noqa: E402,F401
