"""
Data CRUD Module - SubSystem Service
子系統權限與准入邏輯

三層權限模型:
  Layer 1: 子系統准入 -- 社群成員才能進入
  Layer 2: 頁面可見性 -- 角色決定可見頁面
  Layer 3: 資料層控制 -- CRUD 覆蓋 + 資料篩選
"""
import logging
from typing import Dict, List, Optional, Any

from flask_login import current_user

from app.models.user_unit_membership import UserUnitMembership, MembershipRole
from app.models.organizational_unit import OrganizationalUnit
from ..models.sub_system import DcSubSystem
from ..models.sub_system_page import DcSubSystemPage
from ..models.page_layout import DcPageLayout

logger = logging.getLogger(__name__)

# 管理層角色 (團長/副團長/代理)
_ADMIN_ROLES = frozenset({
    MembershipRole.MANAGER,
    MembershipRole.DEPUTY,
    MembershipRole.PROXY1,
    MembershipRole.PROXY2,
})


class SubSystemService:
    """子系統權限服務"""

    @staticmethod
    def get_user_membership(user, sub_system: DcSubSystem) -> Optional[UserUnitMembership]:
        """
        查詢用戶在子系統綁定社群的成員資格

        Args:
            user: 當前用戶 (User model)
            sub_system: 子系統

        Returns:
            UserUnitMembership 或 None (非成員)
        """
        membership = UserUnitMembership.query.filter_by(
            user_secure_code=user.secure_code,
            unit_secure_code=sub_system.group_unit_secure_code,
            is_deleted=False,
        ).first()

        if membership and not membership.is_active:
            return None

        return membership

    @staticmethod
    def get_user_role_type(user, sub_system: DcSubSystem) -> Optional[str]:
        """
        取得用戶在子系統中的角色類型

        系統管理員和企業管理員自動視為 MANAGER。
        非成員回傳 None。

        Args:
            user: 當前用戶
            sub_system: 子系統

        Returns:
            role_type 字串或 None
        """
        # 系統管理員/企業管理員 → 自動 MANAGER
        if getattr(user, 'is_system_admin', False) or getattr(user, 'is_org_admin', False):
            return MembershipRole.MANAGER

        membership = SubSystemService.get_user_membership(user, sub_system)
        if not membership:
            return None

        return membership.role_type or MembershipRole.MEMBER

    @staticmethod
    def is_admin_role(role_type: str) -> bool:
        """判斷是否為管理層角色 (團長/副團長/代理)"""
        return role_type in _ADMIN_ROLES

    @staticmethod
    def get_visible_pages(
        user, sub_system: DcSubSystem
    ) -> List[Dict[str, Any]]:
        """
        取得用戶在子系統中可見的頁面清單

        依角色過濾 visible_roles，回傳可見頁面清單 (含頁面名稱)。

        Args:
            user: 當前用戶
            sub_system: 子系統

        Returns:
            [{ secure_code, display_name, page_layout_secure_code, ... }]
        """
        role_type = SubSystemService.get_user_role_type(user, sub_system)
        if role_type is None:
            return []

        pages = DcSubSystemPage.query.filter_by(
            sub_system_secure_code=sub_system.secure_code,
            org_secure_code=sub_system.org_secure_code,
            is_deleted=False,
            is_active=True,
        ).order_by(DcSubSystemPage.display_order).all()

        result = []
        for ssp in pages:
            if not SubSystemService._is_role_visible(role_type, ssp.visible_roles):
                continue

            # 取得頁面佈局名稱
            page_name = ssp.display_name
            if not page_name:
                layout = DcPageLayout.query.filter_by(
                    secure_code=ssp.page_layout_secure_code,
                    is_deleted=False,
                ).first()
                page_name = layout.name if layout else '未命名頁面'

            result.append({
                'secure_code': ssp.secure_code,
                'display_name': page_name,
                'page_layout_secure_code': ssp.page_layout_secure_code,
                'display_order': ssp.display_order,
            })

        return result

    @staticmethod
    def get_page_context(
        role_type: str, sub_system_page: DcSubSystemPage
    ) -> Dict[str, Any]:
        """
        取得頁面在指定角色下的權限 context

        Args:
            role_type: 用戶角色類型
            sub_system_page: 子系統頁面配置

        Returns:
            {
                'crud': {'create': bool, 'edit': bool, 'delete': bool},
                'data_filters': {col: val, ...}
            }
        """
        crud_overrides = sub_system_page.crud_overrides or {}
        data_filters_map = sub_system_page.data_filters or {}

        # CRUD: 先查角色覆蓋，無則依管理層/一般成員給予預設
        crud = crud_overrides.get(role_type)
        if crud is None:
            if SubSystemService.is_admin_role(role_type):
                crud = {'create': True, 'edit': True, 'delete': True}
            else:
                crud = {'create': False, 'edit': False, 'delete': False}

        # 資料篩選: 查角色對應的篩選條件
        data_filters = data_filters_map.get(role_type, {})

        return {
            'crud': crud,
            'data_filters': data_filters,
        }

    @staticmethod
    def _is_role_visible(role_type: str, visible_roles: list) -> bool:
        """判斷角色是否在可見名單中"""
        if not visible_roles:
            return True
        if '*' in visible_roles:
            return True
        return role_type in visible_roles
