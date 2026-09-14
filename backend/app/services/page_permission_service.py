"""
BeakMask Page Permission Service
頁面權限服務 - 檢查用戶對頁面的存取權限
"""
from typing import Optional
from flask_login import current_user

from ..models.page import Page
from ..security.resource_gateway import ResourceGateway


class PagePermissionService:
    """
    頁面權限服務

    負責：
    1. 檢查用戶對頁面的存取權限
    2. 根據 URL 路徑檢查權限
    """

    # 權限結果
    ACCESS_FULL = 'full'
    ACCESS_READ_ONLY = 'read_only'
    ACCESS_DENIED = 'denied'

    @classmethod
    def check_page_access(cls, user, page_secure_code: str) -> str:
        """
        檢查用戶對頁面的存取權限

        Args:
            user: 當前用戶
            page_secure_code: 頁面識別碼

        Returns:
            'full': 完整存取
            'read_only': 只讀
            'denied': 禁止
        """
        # 1. 取得頁面
        page = ResourceGateway.get(
            Page,
            page_secure_code,
            raise_on_not_found=False,
            check_permission=False
        )

        if not page:
            return cls.ACCESS_DENIED

        return cls._check_page(user, page)

    @classmethod
    def _check_page(cls, user, page: Page) -> str:
        """
        檢查頁面權限 (內部方法)

        Args:
            user: 當前用戶
            page: Page 物件

        Returns:
            權限結果
        """
        # 1. 檢查頁面是否啟用
        if not page.is_active:
            return cls.ACCESS_DENIED

        # 2. 公開頁面
        if page.required_access == 'public':
            return cls.ACCESS_FULL

        # 3. 需要登入
        if not user or not user.is_authenticated:
            return cls.ACCESS_DENIED

        # [SEC-02] SYSTEM_ADMIN 不享有特權，走正常存取等級檢查
        # 已移除: 系統管理員特權

        # 4. 系統管理員等級頁面
        if page.required_access == 'system_admin':
            if user.is_system_admin:
                return cls.ACCESS_FULL
            return cls.ACCESS_DENIED

        # 5. 企業管理員特權
        if user.is_org_admin:
            # 企業管理員可存取 org_admin 和 authenticated 等級
            if page.required_access in ('org_admin', 'authenticated'):
                return cls.ACCESS_FULL
            # 系統管理員等級需要拒絕
            return cls.ACCESS_DENIED

        # 6. 一般用戶
        if page.required_access == 'authenticated':
            return cls.ACCESS_FULL

        # 7. 需要更高權限
        return cls.ACCESS_DENIED

    @classmethod
    def get_user_accessible_pages(cls, user, module_secure_code: Optional[str] = None):
        """
        取得用戶可存取的頁面列表

        Args:
            user: 當前用戶
            module_secure_code: 模組識別碼 (可選，用於過濾)

        Returns:
            Page 列表
        """
        if not user or not user.is_authenticated:
            # 未登入只能看公開頁面
            query = Page.query.filter(
                Page.required_access == 'public',
                Page.is_active == True,
                Page.is_deleted == False
            )
        else:
            # 建立基本查詢
            query = Page.query.filter(
                Page.org_secure_code == user.org_secure_code,
                Page.is_active == True,
                Page.is_deleted == False
            )

            # [SEC-02] 根據權限等級過濾（SYSTEM_ADMIN 不享有特權）
            if user.is_system_admin:
                # 系統管理員可見 system_admin + authenticated + public
                query = query.filter(
                    Page.required_access.in_(['system_admin', 'authenticated', 'public'])
                )
            elif user.is_org_admin:
                # 企業管理員可見 org_admin 和 authenticated
                query = query.filter(
                    Page.required_access.in_(['org_admin', 'authenticated', 'public'])
                )
            else:
                # 一般用戶只能見 authenticated 和 public
                query = query.filter(
                    Page.required_access.in_(['authenticated', 'public'])
                )

        # 模組過濾
        if module_secure_code:
            query = query.filter(Page.module_secure_code == module_secure_code)

        return query.order_by(Page.url_path).all()
