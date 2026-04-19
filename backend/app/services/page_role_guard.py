"""
BeakPlatform Page Role Guard
網頁角色守衛 - 在 before_request 中強制執行角色權限檢查

雙鑰匙安全模型：
  鑰匙 1: MenuPermission (user_type 四階層) → 選單可見性
  鑰匙 2: MenuRoleRequirement (角色) → 頁面存取權

執行流程：
1. SYSTEM_ADMIN → 直接放行（程式控制，不走角色系統）
2. URL → 比對 MenuItem（支援 endpoint 名稱 / url path / page code）
3. 比對成功 → 查 MenuRoleRequirement（按用戶所屬企業）
4. 無角色設定 → 擋下（雙鑰匙：必須同時通過 user_type + 角色）
5. 有角色設定 → 比對 UserRoleAssignment
   - 匹配 → 放行
   - 不匹配 → 強制登出 + 稽核日誌
"""
import logging
from datetime import date
from typing import List, Optional, Set, Tuple

from flask import request, url_for
from flask_login import logout_user

from sqlalchemy import text

from ..models.menu_item import MenuItem
from ..models.menu_permission import MenuPermission
from ..models.menu_role_requirement import MenuRoleRequirement
from ..models.associations import UserRoleAssignment
from ..services.audit_service import AuditService, get_real_ip
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

        # SYSTEM_ADMIN bypass: 系統管理員走程式控制（decorator），不走角色系統
        if getattr(user, 'is_system_admin', False):
            return None

        # ORG_ADMIN bypass: 企業管理員負責設定角色與權限，已由 MenuPermission 管控可見範圍
        if getattr(user, 'is_org_admin', False):
            return None

        # 原始管理員 bypass: 初始設定階段尚無角色，由 auth_interceptor AUTH-03 管控
        if getattr(user, 'is_original_admin', False):
            return None

        # RLS context: 選單項目屬於系統企業 (SYSTEM_ORG_CODE)，角色需求跨企業
        # 需要 system_admin 權限才能查詢所有企業的資料
        try:
            db.session.execute(text("SET LOCAL app.is_system_admin = 'true'"))
        except Exception:
            pass

        # 查找匹配當前 URL 的選單項目（可能有多筆，如同 URL 分屬不同 user_type）
        matching_items = cls._find_matching_menu_items(path)
        if not matching_items:
            return None  # 無對應選單 → 沿用現有裝飾器

        # 過濾出該用戶 user_type 有權限的選單項目
        user_type = str(user.user_type)
        permitted_items = cls._filter_by_user_type(matching_items, user_type)

        if not permitted_items:
            # 有對應選單但用戶類型不匹配 → 沿用裝飾器處理
            # （MenuPermission 不符的情況交由 sidebar 隱藏 + 裝飾器擋）
            return None

        # 雙鑰匙檢查：用戶類型匹配的選單中，檢查角色需求
        org_sc = user.org_secure_code
        user_role_scs = None  # lazy load

        for item in permitted_items:
            required_role_scs = cls._get_required_roles(
                item.secure_code, org_sc
            )

            if not required_role_scs:
                # 雙鑰匙：無角色設定 → 擋下
                return (
                    f"User {user.username} (sc={user.secure_code}) "
                    f"denied access to {path} "
                    f"(menu={item.code}, "
                    f"NO role requirements configured for org={org_sc})"
                )

            # Lazy load 用戶角色（只在需要時查一次）
            if user_role_scs is None:
                user_role_scs = cls._get_user_roles(user.secure_code)

            # 比對：用戶持有的角色 ∩ 所需角色
            if user_role_scs & required_role_scs:
                return None  # 匹配 → 放行

        # 所有匹配的選單都未通過角色檢查
        if user_role_scs is None:
            user_role_scs = set()

        return (
            f"User {user.username} (sc={user.secure_code}) "
            f"denied access to {path} "
            f"(matched_menus={[i.code for i in permitted_items]}, "
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
                ip_address=get_real_ip(),
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

        return '/bp/auth/login', 302

    # =========================================================================
    # URL 匹配
    # =========================================================================

    @classmethod
    def _find_matching_menu_items(cls, path: str) -> List[MenuItem]:
        """
        根據 URL 路徑找到所有對應的 MenuItem。

        三階段匹配策略：
        1. Flask endpoint 精確匹配（link_type='route' + endpoint 名稱）
        2. URL path 匹配（link_type='url' 或 link_type='route' + path）
        3. Page code 匹配（link_type='page' + /p/ 前綴）

        Returns:
            匹配的 MenuItem 列表（可能多筆，同 URL 分屬不同 user_type）
        """
        results = []
        matched_scs = set()  # 避免重複

        # 策略 1: Flask endpoint 精確匹配
        endpoint = request.endpoint
        if endpoint:
            matches = MenuItem.query.filter(
                MenuItem.link_type == 'route',
                MenuItem.link_target == endpoint,
                MenuItem.is_deleted == False,
                MenuItem.is_active == True,
            ).all()
            for m in matches:
                if m.secure_code not in matched_scs:
                    results.append(m)
                    matched_scs.add(m.secure_code)

        # 策略 2: URL path 匹配（link_type='url' 或 link_type='route' 以 / 開頭）
        path_candidates = MenuItem.query.filter(
            MenuItem.link_type.in_(['url', 'route']),
            MenuItem.link_target.isnot(None),
            MenuItem.link_target.like('/%'),
            MenuItem.is_deleted == False,
            MenuItem.is_active == True,
        ).all()

        path_normalized = path.rstrip('/')

        # 精確匹配優先收集，前綴匹配記錄最佳
        prefix_matches = []  # (match_len, item)

        for item in path_candidates:
            if item.secure_code in matched_scs:
                continue

            target = item.link_target
            if not target:
                continue

            target_normalized = target.rstrip('/')

            # 精確匹配
            if path_normalized == target_normalized:
                results.append(item)
                matched_scs.add(item.secure_code)
                continue

            # 前綴匹配
            if path.startswith(target_normalized + '/'):
                prefix_matches.append((len(target_normalized), item))

        # 從前綴匹配中取最長匹配
        if prefix_matches:
            max_len = max(length for length, _ in prefix_matches)
            for length, item in prefix_matches:
                if length == max_len and item.secure_code not in matched_scs:
                    results.append(item)
                    matched_scs.add(item.secure_code)

        # 策略 3: Page code 匹配 (/p/{secure_code})
        if path.startswith('/p/') and not results:
            page_code = path[3:].split('/')[0]  # 取第一段
            if page_code:
                matches = MenuItem.query.filter(
                    MenuItem.link_type == 'page',
                    MenuItem.link_target == page_code,
                    MenuItem.is_deleted == False,
                    MenuItem.is_active == True,
                ).all()
                for m in matches:
                    if m.secure_code not in matched_scs:
                        results.append(m)
                        matched_scs.add(m.secure_code)

        return results

    @classmethod
    def _filter_by_user_type(
        cls,
        items: List[MenuItem],
        user_type: str
    ) -> List[MenuItem]:
        """
        過濾出用戶 user_type 有 MenuPermission 的選單項目。

        同一 URL 可能有多個選單項目（如 login_fail_monitor 給 SYSTEM_ADMIN，
        login_fail_monitor_org 給 ORG_ADMIN），只保留匹配用戶類型的。
        """
        if not items:
            return []

        item_scs = [i.secure_code for i in items]
        permissions = MenuPermission.query.filter(
            MenuPermission.menu_secure_code.in_(item_scs),
            MenuPermission.user_type == user_type,
            MenuPermission.is_deleted == False,
        ).all()

        permitted_scs = {p.menu_secure_code for p in permissions}
        return [i for i in items if i.secure_code in permitted_scs]

    # =========================================================================
    # 角色查詢
    # =========================================================================

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
