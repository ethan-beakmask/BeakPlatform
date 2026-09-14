"""
登入安全欄位服務

三欄位偽裝機制：前端送出 sv_1, sv_2, sv_3 三個外觀一致的欄位，
後端依設定決定哪個是密碼、地雷、救助欄位。

設定層級（高優先覆蓋低）：
  企業設定 (Organization.settings) → 系統設��� (SystemSetting) → 硬編碼預設

兩組獨立設定：
  - employee: 企業成員 + 共用登入頁
  - vendor: 外部廠商登入頁
"""
import logging
import time
from typing import Optional

from ..models.system_setting import SystemSetting

logger = logging.getLogger(__name__)

# 有效欄位名稱
VALID_FIELDS = ('sv_1', 'sv_2', 'sv_3')

# 硬編碼預設值（最低優先）
DEFAULT_CONFIG = {
    'password_field': 'sv_2',
    'mine_field': 'sv_1',
    'rescue_field': 'sv_3',
    'rescue_keyword': '',
}

# 登入回應固定延遲秒數
LOGIN_DELAY_SECONDS = 3.0


class LoginSecurityService:
    """登入安全欄位服務"""

    # ------------------------------------------------------------------
    # 設定解析
    # ------------------------------------------------------------------

    @staticmethod
    def get_config(org, context: str = 'employee') -> dict:
        """
        取得登入安全欄位設定

        Args:
            org: Organization 物件（可為 None，此時只查系統設定）
            context: 'employee' 或 'vendor'

        Returns:
            dict: { password_field, mine_field, rescue_field, rescue_keyword }
        """
        setting_key = f'login_security_{context}'

        # 1. 企業設定
        org_cfg = None
        if org:
            org_cfg = org.get_setting(setting_key)

        # 2. 系統設定
        sys_cfg = SystemSetting.get(setting_key, default=None)

        # 3. 合併：org > system > default
        result = dict(DEFAULT_CONFIG)
        if isinstance(sys_cfg, dict):
            result.update({k: v for k, v in sys_cfg.items() if k in DEFAULT_CONFIG})
        if isinstance(org_cfg, dict):
            result.update({k: v for k, v in org_cfg.items() if k in DEFAULT_CONFIG})

        return result

    @staticmethod
    def validate_config(config: dict) -> tuple:
        """
        驗證設定值合法性

        Args:
            config: { password_field, mine_field, rescue_field, rescue_keyword }

        Returns:
            (is_valid: bool, error_message: str or None)
        """
        pf = config.get('password_field')
        mf = config.get('mine_field')
        rf = config.get('rescue_field')

        # 必須是有效欄位
        for label, val in [('密碼欄位', pf), ('地雷欄位', mf), ('��助欄位', rf)]:
            if val not in VALID_FIELDS:
                return False, f'{label}無效，允許值: {", ".join(VALID_FIELDS)}'

        # 三個欄位不能重複
        if len({pf, mf, rf}) < 3:
            return False, '密碼、地雷��救助欄位不能重複指派'

        return True, None

    # ------------------------------------------------------------------
    # 登入欄位處理
    # ------------------------------------------------------------------

    @staticmethod
    def process_fields(form_data: dict, config: dict) -> dict:
        """
        從表單資料中依設定提取各欄位值

        Args:
            form_data: { 'sv_1': ..., 'sv_2': ..., 'sv_3': ... }
            config: get_config() 的回傳值

        Returns:
            {
                'password': str,        # 密碼欄位的值
                'mine_triggered': bool,  # 地雷欄位是否有值
                'mine_value': str,       # 地雷欄位原始值
                'rescue_triggered': bool,# 救助欄位是否命中關鍵字
                'rescue_value': str,     # 救助欄位原始值
            }
        """
        password_val = form_data.get(config['password_field'], '').strip()
        mine_val = form_data.get(config['mine_field'], '').strip()
        rescue_val = form_data.get(config['rescue_field'], '').strip()

        # 地雷：有值就觸發
        mine_triggered = bool(mine_val)

        # 救助：關鍵字非空且出現在欄位值中（忽略大��寫）
        rescue_keyword = config.get('rescue_keyword', '').strip()
        rescue_triggered = False
        if rescue_keyword and rescue_val:
            rescue_triggered = rescue_keyword.lower() in rescue_val.lower()

        return {
            'password': password_val,
            'mine_triggered': mine_triggered,
            'mine_value': mine_val,
            'rescue_triggered': rescue_triggered,
            'rescue_value': rescue_val,
        }

    # ------------------------------------------------------------------
    # 救助通知
    # ------------------------------------------------------------------

    @staticmethod
    def send_rescue_alert(
        org,
        account_hint: str,
        remote_ip: str,
        login_context: str = 'employee',
    ):
        """
        發送救助通知信給企業所有活躍的管理員

        Args:
            org: Organization 物件
            account_hint: 觸發帳號（username 或 email）
            remote_ip: 來源 IP
            login_context: 'employee' ��� 'vendor'
        """
        from ..models import User
        from ..models.user import UserType
        from ..services.email_service import EmailService
        from .. import db
        from datetime import datetime
        from zoneinfo import ZoneInfo

        # 取得活躍的企業管理員
        admins = User.query.filter(
            User.org_secure_code == org.secure_code,
            User.user_type == UserType.ORG_ADMIN,
            User.is_active == True,
            User.is_deleted == False,
        ).all()

        if not admins:
            logger.warning(
                f"[RESCUE] 企業 {org.name} 無活躍管理員可接收救助通知"
            )
            return

        # 收集通知信箱（優先 backup_email_1）
        notify_emails = []
        for a in admins:
            email = a.backup_email_1 or a.email
            if email and email not in notify_emails:
                notify_emails.append(email)

        if not notify_emails:
            logger.warning(
                f"[RESCUE] 企業 {org.name} 管理員均無可用信箱"
            )
            return

        # 時間格式化
        org_tz = ZoneInfo(org.get_setting('timezone', 'Asia/Taipei'))
        now_local = datetime.utcnow().replace(
            tzinfo=ZoneInfo('UTC')
        ).astimezone(org_tz)
        time_str = now_local.strftime('%Y-%m-%d %H:%M:%S %Z')

        context_label = '企業成員' if login_context == 'employee' else '外部廠商'

        subject = f'[{org.name}] 登入救助警報'

        body = f'''登入救助警報

以下登入嘗試觸發了救助機制，可能有人被迫進行操作：

企業：{org.name}
登入類型：{context_label}
觸發帳號：{account_hint}
來源 IP：{remote_ip}
觸發時間：{time_str}

請立即確認當事人是否安全。

---
{org.name} 系統自動發送
'''

        for email in notify_emails:
            if not EmailService.send_email(email, subject, body):
                logger.error(f"[RESCUE] 救助通知寄送失敗: {email}")

        logger.info(
            f"[RESCUE] 救助通知已發送: org={org.name}, "
            f"account={account_hint}, ip={remote_ip}, "
            f"recipients={notify_emails}"
        )

    # ------------------------------------------------------------------
    # 延遲控制
    # ------------------------------------------------------------------

    @staticmethod
    def enforce_delay(start_time: float):
        """
        確保登入回應至少延遲 LOGIN_DELAY_SECONDS 秒

        Args:
            start_time: time.monotonic() 的起始時間
        """
        elapsed = time.monotonic() - start_time
        remaining = LOGIN_DELAY_SECONDS - elapsed
        if remaining > 0:
            time.sleep(remaining)
