"""
BeakPlatform Page Role Guard
網頁角色守衛 - 在 before_request 中強制執行角色權限檢查

執行流程：
1. URL → 比對 MenuItem.link_target（精確 + 前綴）
2. 比對成功 → 查 MenuRoleRequirement（按用戶所屬企業）
3. 無角色設定 → 放行（沿用現有 user_type 檢查）
4. 有角色設定 → 比對 UserRoleAssignment
   - 匹配 → 放行
   - 不匹配 → 強制登出 + 稽核日誌

SYSTEM_ADMIN 不享有特權，必須持有所需角色。
"""
import logging
from datetime import date
from typing import Optional, Set, Tuple

from flask import request
from flask_login import logout_user

from ..models.menu_item import MenuItem
from ..models.menu_role_requirement import MenuRoleRequirement
from ..models.associations import UserRoleAssignment
from ..services.audit_service import AuditService
from .. import db

logger = logging.getLogger(__name__)


class PageRoleGuard:
    """網頁角色守衛"""

    # 不檢查的路徑前綴（API、靜態資源等已有其他機制保護）
    SKIP_PREFIXES = (
        '/api/',
        '/static/',
        '/auth/',
        '/public/',
        '/dev/',
        '/health',
        '/favicon.ico',
    )

    @classmethod
    def check_access(cls, user) -> Optional[str]:
        """
        檢查用戶是否有權限存取當前頁面。

        Args:
            user: 當前登入用戶

        Returns:
            None = 放行
            str = 被擋下的原因訊息（呼叫端負責登出+重導向）
        """
        path = request.path

        # 跳過不需要檢查的路徑
        if path.startswith(cls.SKIP_PREFIXES):
            return None

        # 查找匹配的選單項目
        menu_item = cls._find_matching_menu_item(path)
        if not menu_item:
            return None  # 無對應選單 → 沿用現有裝飾器

        # 查詢該選單在用戶企業的角色需求
        org_sc = user.org_secure_code
        required_role_scs = cls._get_required_roles(
            menu_item.secure_code, org_sc
        )

        if not required_role_scs:
            # 無角色設定 → 擋下（雙鑰匙：四階層+角色都必須通過）
            return (
                f"User {user.username} (sc={user.secure_code}) "
                f"denied access to {path} "
                f"(menu={menu_item.code}, "
                f"NO role requirements configured for org={org_sc})"
            )

        # 取得用戶當前持有的角色
        user_role_scs = cls._get_user_roles(user.secure_code)

        # 比對：用戶持有的角色 ∩ 所需角色
        if user_role_scs & required_role_scs:
            return None  # 匹配 → 放行

        # 不匹配 → 阻擋
        return (
            f"User {user.username} (sc={user.secure_code}) "
            f"denied access to {path} "
            f"(menu={menu_item.code}, "
            f"required_roles={required_role_scs}, "
            f"user_roles={user_role_scs})"
        )

    @classmethod
    def enforce(cls, user) -> Optional[Tuple[str, int]]:
        """
        強制執行角色檢查。被擋時自動登出+寫稽核日誌。

        Args:
            user: 當前登入用戶

        Returns:
            None = 放行
            Tuple[redirect_url, status_code] = 需要重導向
        """
        denial_reason = cls.check_access(user)
        if denial_reason is None:
            return None

        # 寫稽核日誌
        logger.warning(f"Page role guard DENIED: {denial_reason}")
        try:
            AuditService.log(
                action='ACCESS_DENIED',
                resource_type='PAGE_ROLE_GUARD',
                org_secure_code=user.org_secure_code,
                user_secure_code=user.secure_code,
                details=denial_reason,
                request_method=request.method,
                request_path=request.path,
                status_code=403,
                ip_address=request.remote_addr,
                user_agent=request.headers.get('User-Agent', '')[:500],
            )
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to write page role guard audit log: {e}")

        # 強制登出
        try:
            logout_user()
        except Exception as e:
            logger.error(f"Failed to logout user: {e}")

        return '/auth/login', 302

    @classmethod
    def _find_matching_menu_item(cls, path: str) -> Optional[MenuItem]:
        """
        根據 URL 路徑找到對應的 MenuItem。

        匹配規則：
        1. link_target 精確匹配 path
        2. link_target 前綴匹配（path 以 link_target 開頭，
           且 link_target 以 / 結尾或 path 在 link_target 後接 /）

        僅查詢 link_type='route' 且 link_target 以 '/' 開頭的選單。
        """
        # 取得所有 route 類型且 link_target 以 / 開頭的選單
        candidates = MenuItem.query.filter(
            MenuItem.link_type == 'route',
            MenuItem.link_target.isnot(None),
            MenuItem.link_target.like('/%'),
            MenuItem.is_deleted == False,
            MenuItem.is_active == True,
        ).all()

        # 精確匹配優先
        best_match = None
        best_match_len = 0

        for item in candidates:
            target = item.link_target
            if not target:
                continue

            # 精確匹配
            if path == target or path == target.rstrip('/'):
                return item

            # 前綴匹配（最長匹配優先）
            normalized = target.rstrip('/')
            if path.startswith(normalized + '/') and len(normalized) > best_match_len:
                best_match = item
                best_match_len = len(normalized)

        return best_match

    @classmethod
    def _get_required_roles(
        cls, menu_secure_code: str, org_secure_code: str
    ) -> Set[str]:
        """
        取得選單在指定企業的角色需求。

        Returns:
            所需角色的 secure_code 集合（空集合 = 無角色需求）
        """
        requirements = MenuRoleRequirement.query.filter(
            MenuRoleRequirement.menu_secure_code == menu_secure_code,
            MenuRoleRequirement.org_secure_code == org_secure_code,
            MenuRoleRequirement.is_deleted == False,
        ).all()

        return {r.role_secure_code for r in requirements}

    @classmethod
    def _get_user_roles(cls, user_secure_code: str) -> Set[str]:
        """
        取得用戶當前有效的角色 secure_code 集合。

        過濾條件：
        - 未刪除
        - 在有效期限內
        """
        today = date.today()

        assignments = UserRoleAssignment.query.filter(
            UserRoleAssignment.user_secure_code == user_secure_code,
            UserRoleAssignment.is_deleted == False,
        ).all()

        result = set()
        for a in assignments:
            # 檢查有效期限
            if a.valid_from and today < a.valid_from:
                continue
            if a.valid_until and today > a.valid_until:
                continue
            result.add(a.role_secure_code)

        return result

    # ==========================================================================
    # 管理 API 用的方法
    # ==========================================================================

    @classmethod
    def get_menu_roles(
        cls, menu_secure_code: str, org_secure_code: str
    ):
        """取得選單的角色需求列表"""
        return MenuRoleRequirement.query.filter(
            MenuRoleRequirement.menu_secure_code == menu_secure_code,
            MenuRoleRequirement.org_secure_code == org_secure_code,
            MenuRoleRequirement.is_deleted == False,
        ).all()

    @classmethod
    def set_menu_roles(
        cls,
        menu_secure_code: str,
        org_secure_code: str,
        role_secure_codes: list
    ) -> int:
        """
        設定選單的角色需求（全量替換）。

        Args:
            menu_secure_code: 選單 secure_code
            org_secure_code: 企業 secure_code
            role_secure_codes: 角色 secure_code 列表

        Returns:
            設定的角色數量
        """
        # 硬刪除現有記錄（關聯表不需軟刪除，且 unique constraint 不含 is_deleted）
        MenuRoleRequirement.query.filter(
            MenuRoleRequirement.menu_secure_code == menu_secure_code,
            MenuRoleRequirement.org_secure_code == org_secure_code,
            MenuRoleRequirement.is_deleted == False,
        ).delete(synchronize_session='fetch')

        # 建立新記錄
        count = 0
        for role_sc in role_secure_codes:
            req = MenuRoleRequirement(
                menu_secure_code=menu_secure_code,
                role_secure_code=role_sc,
                org_secure_code=org_secure_code,
            )
            db.session.add(req)
            count += 1

        return count

    @classmethod
    def remove_menu_role(
        cls,
        menu_secure_code: str,
        role_secure_code: str,
        org_secure_code: str,
    ) -> bool:
        """移除單一角色需求"""
        count = MenuRoleRequirement.query.filter(
            MenuRoleRequirement.menu_secure_code == menu_secure_code,
            MenuRoleRequirement.role_secure_code == role_secure_code,
            MenuRoleRequirement.org_secure_code == org_secure_code,
            MenuRoleRequirement.is_deleted == False,
        ).delete(synchronize_session='fetch')

        return count > 0
