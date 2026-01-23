"""
BeakMask Email Service
郵件發送服務

TODO: 整合實際的郵件服務 (SMTP, SendGrid, etc.)
目前為 placeholder 實作，只記錄日誌
"""
import logging

logger = logging.getLogger(__name__)


class EmailService:
    """郵件發送服務"""

    @staticmethod
    def send_password_reset_verification(
        to_email: str,
        verification_url: str,
        verification_code: str,
        org_name: str
    ) -> bool:
        """
        發送密碼重設驗證信

        郵件內容包含:
        - 驗證 URL
        - 6 碼驗證碼
        - 10 分鐘有效期限提醒

        Args:
            to_email: 收件人 email
            verification_url: 驗證 URL
            verification_code: 6 碼驗證碼
            org_name: 企業名稱

        Returns:
            bool: 是否成功發送
        """
        # TODO: 實際發送郵件
        logger.info(f"[EMAIL] Password Reset Verification")
        logger.info(f"  To: {to_email}")
        logger.info(f"  Org: {org_name}")
        logger.info(f"  URL: {verification_url}")
        logger.info(f"  Code: {verification_code}")
        logger.info(f"  ------ Email Content ------")
        logger.info(f"  您好，")
        logger.info(f"  ")
        logger.info(f"  您已申請 {org_name} 系統的密碼重設。")
        logger.info(f"  請點擊以下連結並輸入 6 碼驗證碼完成驗證：")
        logger.info(f"  ")
        logger.info(f"  驗證連結：{verification_url}")
        logger.info(f"  驗證碼：{verification_code}")
        logger.info(f"  ")
        logger.info(f"  此驗證碼將於 10 分鐘後失效。")
        logger.info(f"  如果您沒有申請密碼重設，請忽略此郵件。")
        logger.info(f"  ------ End of Email ------")

        return True

    @staticmethod
    def send_temp_password(
        to_email: str,
        temp_password: str,
        org_name: str
    ) -> bool:
        """
        發送暫時密碼

        Args:
            to_email: 收件人 email
            temp_password: 暫時密碼
            org_name: 企業名稱

        Returns:
            bool: 是否成功發送
        """
        # TODO: 實際發送郵件
        logger.info(f"[EMAIL] Temporary Password")
        logger.info(f"  To: {to_email}")
        logger.info(f"  Org: {org_name}")
        logger.info(f"  ------ Email Content ------")
        logger.info(f"  您好，")
        logger.info(f"  ")
        logger.info(f"  您的 {org_name} 系統暫時密碼如下：")
        logger.info(f"  ")
        logger.info(f"  暫時密碼：{temp_password}")
        logger.info(f"  ")
        logger.info(f"  請使用此暫時密碼登入，登入後系統將要求您立即變更密碼。")
        logger.info(f"  此暫時密碼僅供一次性使用。")
        logger.info(f"  ------ End of Email ------")

        return True

    @staticmethod
    def send_welcome_email(
        to_email: str,
        username: str,
        org_name: str,
        login_url: str
    ) -> bool:
        """
        發送歡迎郵件 (新用戶建立時)

        Args:
            to_email: 收件人 email
            username: 用戶名
            org_name: 企業名稱
            login_url: 登入 URL

        Returns:
            bool: 是否成功發送
        """
        # TODO: 實際發送郵件
        logger.info(f"[EMAIL] Welcome Email")
        logger.info(f"  To: {to_email}")
        logger.info(f"  Username: {username}")
        logger.info(f"  Org: {org_name}")
        logger.info(f"  Login URL: {login_url}")

        return True

    @staticmethod
    def send_admin_password_reset_notification(
        to_emails: list,
        target_admin_name: str,
        target_admin_email: str,
        operator_name: str,
        operator_email: str,
        org_name: str,
        reset_time: str
    ) -> bool:
        """
        發送企業管理員密碼被重設的通知

        當企業管理員的密碼被其他管理員重設時，通知該企業所有企業管理員
        （包含停用中的帳號，作為防弊措施）

        Args:
            to_emails: 收件人 email 列表
            target_admin_name: 被重設密碼的管理員姓名
            target_admin_email: 被重設密碼的管理員 email
            operator_name: 操作者姓名
            operator_email: 操作者 email
            org_name: 企業名稱
            reset_time: 重設時間

        Returns:
            bool: 是否成功發送
        """
        # TODO: 實際發送郵件
        logger.info(f"[EMAIL] Admin Password Reset Notification")
        logger.info(f"  To: {', '.join(to_emails)}")
        logger.info(f"  Org: {org_name}")
        logger.info(f"  ------ Email Content ------")
        logger.info(f"  企業管理員密碼重設通知")
        logger.info(f"  ")
        logger.info(f"  您好，")
        logger.info(f"  ")
        logger.info(f"  這是一封自動發送的安全通知郵件。")
        logger.info(f"  ")
        logger.info(f"  以下企業管理員的密碼已被重設：")
        logger.info(f"  ")
        logger.info(f"  被重設帳號：{target_admin_name} ({target_admin_email})")
        logger.info(f"  操作者：{operator_name} ({operator_email})")
        logger.info(f"  重設時間：{reset_time}")
        logger.info(f"  ")
        logger.info(f"  如果這不是您或授權人員的操作，請立即聯繫系統管理員。")
        logger.info(f"  ")
        logger.info(f"  此郵件發送給 {org_name} 的所有企業管理員（包含停用帳號）。")
        logger.info(f"  ------ End of Email ------")

        return True
