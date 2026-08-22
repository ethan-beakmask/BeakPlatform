"""
BeakPlatform System Settings API
系統設定 API - 僅系統管理員可用

[標準 AUTH-02] 使用 @system_admin_required 裝飾器

端點：
選單配色:
- GET    /api/system-settings/menu-colors             取得選單配色
- PUT    /api/system-settings/menu-colors             更新選單配色
- POST   /api/system-settings/menu-colors/reset       重置為預設值

E-MailRelay:
- GET    /api/system-settings/emailrelay              取得設定
- PUT    /api/system-settings/emailrelay              更新設定
- GET    /api/system-settings/emailrelay/auth         取得認證
- PUT    /api/system-settings/emailrelay/auth         更新認證
- POST   /api/system-settings/emailrelay/test         測試發送
- POST   /api/system-settings/emailrelay/service/<action>  服務控制

SMTP 設定 (系統級):
- GET    /api/system-settings/smtp                    列出 SMTP 設定
- POST   /api/system-settings/smtp                    新增 SMTP 設定
- GET    /api/system-settings/smtp/<id>               取得設定詳情
- PUT    /api/system-settings/smtp/<id>               更新 SMTP 設定
- DELETE /api/system-settings/smtp/<id>               刪除 SMTP 設定
- POST   /api/system-settings/smtp/test               測試連線
- POST   /api/system-settings/smtp/<id>/test          測試已儲存設定

Telegram 設定 (系統級):
- GET    /api/system-settings/telegram                列出 Telegram 設定
- POST   /api/system-settings/telegram                新增 Telegram 設定
- GET    /api/system-settings/telegram/<id>           取得設定詳情
- PUT    /api/system-settings/telegram/<id>           更新 Telegram 設定
- DELETE /api/system-settings/telegram/<id>           刪除 Telegram 設定
- POST   /api/system-settings/telegram/test           測試連線
- POST   /api/system-settings/telegram/<id>/test      測試已儲存設定

收件人群組 (系統級):
- GET    /api/system-settings/recipient-groups        列出群組
- POST   /api/system-settings/recipient-groups        新增群組
- GET    /api/system-settings/recipient-groups/<id>   取得群組詳情
- PUT    /api/system-settings/recipient-groups/<id>   更新群組
- DELETE /api/system-settings/recipient-groups/<id>   刪除群組
- GET    /api/system-settings/recipient-groups/<id>/resolve  解析收件人

套件版本:
- GET    /api/system-settings/package-versions        查詢套件版本

系統對外網址:
- GET    /api/system-settings/base-url                取得系統對外網址
- PUT    /api/system-settings/base-url                更新系統對外網址

稽核設定:
- GET    /api/system-settings/audit                   取得稽核設定
- PUT    /api/system-settings/audit                   更新稽核設定

檔案儲存:
- GET    /api/system-settings/file-storage            取得檔案儲存設定
- PUT    /api/system-settings/file-storage            更新檔案儲存設定
"""
from flask import Blueprint

from . import _ss_emailrelay
from . import _ss_smtp
from . import _ss_telegram
from . import _ss_recipient_groups
from . import _ss_packages
from . import _ss_audit
from . import _ss_base_url
from . import _ss_login_security

api_system_settings = Blueprint('api_system_settings', __name__, url_prefix='/api/system-settings')

# 掛載子模組路由
_ss_emailrelay.register(api_system_settings)
_ss_smtp.register(api_system_settings)
_ss_telegram.register(api_system_settings)
_ss_recipient_groups.register(api_system_settings)
_ss_packages.register(api_system_settings)
_ss_base_url.register(api_system_settings)
_ss_audit.register(api_system_settings)
_ss_login_security.register(api_system_settings)
