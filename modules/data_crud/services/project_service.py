"""
Data CRUD Module - Project Service
開發案管理服務

負責開發案生命週期: 建立/更新/刪除/上線/下線 + 開發者名單管理
"""
import copy
import logging
from typing import Dict, List, Optional, Any

from flask_login import current_user
from sqlalchemy.orm.attributes import flag_modified

from app import db
from app.models.menu_item import MenuItem
from app.models.organizational_unit import OrganizationalUnit, UnitType
from app.models.user_unit_membership import (
    UserUnitMembership, MembershipType, MembershipRole,
)
from app.models.user import User
from app.security.resource_gateway import ResourceGateway
from app.platform.data import get_current_org

from ..models.sub_system import DcSubSystem

logger = logging.getLogger(__name__)


class ProjectService:
    """開發案管理服務"""

    @staticmethod
    def list_projects(user) -> List[Dict[str, Any]]:
        """
        列出用戶可見的開發案

        系統管理員/企業管理員看全部，一般用戶只看 developers 名單包含自己的
        """
        org = get_current_org()
        if not org:
            return []

        all_projects = ResourceGateway.filter(
            DcSubSystem,
            is_deleted=False,
            order_by='-updated_at',
        )

        is_admin = (
            getattr(user, 'is_system_admin', False)
            or getattr(user, 'is_org_admin', False)
        )

        result = []
        for ss in all_projects:
            if not is_admin:
                developers = ss.developers or []
                if user.secure_code not in developers:
                    continue
            d = ss.to_dict()
            d['developer_count'] = len(ss.developers or [])
            result.append(d)

        return result

    @staticmethod
    def create_project(user, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        建立開發案

        自動:
        1. 建立社群 (OrganizationalUnit type=GROUP)
        2. 將建立者加入 developers 名單
        3. 建立者成為社群 MANAGER
        """
        org = get_current_org()
        if not org:
            return {'success': False, 'error': 'Organization not found'}

        name = data.get('name', '').strip()
        if not name:
            return {'success': False, 'error': '名稱為必填'}

        layout_mode = data.get('layout_mode', 'grid')
        if layout_mode not in ('grid', 'free'):
            layout_mode = 'grid'

        # 自動建立社群
        group_code = 'PRJ_' + name.upper().replace(' ', '_')[:30]
        group = OrganizationalUnit(
            org_secure_code=org.secure_code,
            unit_type=UnitType.GROUP,
            code=group_code,
            name=name,
            description=f'開發案「{name}」社群',
            is_active=True,
        )
        group.update_full_path()
        db.session.add(group)
        db.session.flush()  # 取得 secure_code

        # 建立子系統
        ss = ResourceGateway.create(
            DcSubSystem,
            check_permission=False,
            name=name,
            description=data.get('description', ''),
            icon=data.get('icon', ''),
            group_unit_secure_code=group.secure_code,
            status='draft',
            developers=[user.secure_code],
            layout_mode=layout_mode,
            is_active=True,
        )

        # 建立者成為社群 MANAGER
        membership = UserUnitMembership(
            org_secure_code=org.secure_code,
            user_secure_code=user.secure_code,
            unit_secure_code=group.secure_code,
            membership_type=MembershipType.MEMBER,
            role_type=MembershipRole.MANAGER,
        )
        db.session.add(membership)

        ResourceGateway.commit()

        return {'success': True, 'data': ss.to_dict()}

    @staticmethod
    def update_project(secure_code: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """更新開發案基本資訊"""
        ss = ResourceGateway.get(
            DcSubSystem, secure_code,
            raise_on_not_found=False,
            check_permission=False,
        )
        if not ss or ss.is_deleted:
            return {'success': False, 'error': '開發案不存在'}

        update_fields = {}
        for field in ('name', 'description', 'icon'):
            if field in data:
                update_fields[field] = data[field]

        if 'name' in update_fields and not update_fields['name'].strip():
            return {'success': False, 'error': '名稱不可為空'}

        ResourceGateway.update(ss, check_permission=False, **update_fields)
        ResourceGateway.commit()

        return {'success': True, 'data': ss.to_dict()}

    @staticmethod
    def delete_project(secure_code: str) -> Dict[str, Any]:
        """軟刪除開發案"""
        ss = ResourceGateway.get(
            DcSubSystem, secure_code,
            raise_on_not_found=False,
            check_permission=False,
        )
        if not ss or ss.is_deleted:
            return {'success': False, 'error': '開發案不存在'}

        ResourceGateway.delete(ss, check_permission=False, soft=True)
        ResourceGateway.commit()

        return {'success': True}

    @staticmethod
    def publish(secure_code: str) -> Dict[str, Any]:
        """上線開發案 -- 同時啟用關聯選單"""
        ss = ResourceGateway.get(
            DcSubSystem, secure_code,
            raise_on_not_found=False,
            check_permission=False,
        )
        if not ss or ss.is_deleted:
            return {'success': False, 'error': '開發案不存在'}

        ResourceGateway.update(ss, check_permission=False, status='published')

        # 連動: 啟用關聯選單項
        if ss.menu_item_secure_code:
            menu_item = MenuItem.query.filter_by(
                secure_code=ss.menu_item_secure_code,
                is_deleted=False,
            ).first()
            if menu_item:
                menu_item.is_active = True

        ResourceGateway.commit()

        return {'success': True, 'data': ss.to_dict()}

    @staticmethod
    def unpublish(secure_code: str) -> Dict[str, Any]:
        """下線開發案 -- 同時停用關聯選單"""
        ss = ResourceGateway.get(
            DcSubSystem, secure_code,
            raise_on_not_found=False,
            check_permission=False,
        )
        if not ss or ss.is_deleted:
            return {'success': False, 'error': '開發案不存在'}

        ResourceGateway.update(ss, check_permission=False, status='draft')

        # 連動: 停用關聯選單項
        if ss.menu_item_secure_code:
            menu_item = MenuItem.query.filter_by(
                secure_code=ss.menu_item_secure_code,
                is_deleted=False,
            ).first()
            if menu_item:
                menu_item.is_active = False

        ResourceGateway.commit()

        return {'success': True, 'data': ss.to_dict()}

    @staticmethod
    def get_developers(secure_code: str) -> Dict[str, Any]:
        """取得開發者名單 (附帶用戶資訊)"""
        ss = ResourceGateway.get(
            DcSubSystem, secure_code,
            raise_on_not_found=False,
            check_permission=False,
        )
        if not ss or ss.is_deleted:
            return {'success': False, 'error': '開發案不存在'}

        developer_scs = ss.developers or []
        developers = []
        for sc in developer_scs:
            user = User.query.filter_by(
                secure_code=sc,
                is_deleted=False,
                is_active=True,
            ).first()
            if user:
                developers.append({
                    'secure_code': user.secure_code,
                    'display_name': user.display_name,
                    'employee_id': user.employee_id,
                })

        return {'success': True, 'data': developers}

    @staticmethod
    def add_developer(secure_code: str, user_sc: str) -> Dict[str, Any]:
        """新增開發者"""
        ss = ResourceGateway.get(
            DcSubSystem, secure_code,
            raise_on_not_found=False,
            check_permission=False,
        )
        if not ss or ss.is_deleted:
            return {'success': False, 'error': '開發案不存在'}

        user = User.query.filter_by(
            secure_code=user_sc,
            is_deleted=False,
            is_active=True,
        ).first()
        if not user:
            return {'success': False, 'error': '用戶不存在'}

        developers = copy.deepcopy(ss.developers or [])
        if user_sc in developers:
            return {'success': False, 'error': '該用戶已是開發者'}

        developers.append(user_sc)
        ss.developers = developers
        flag_modified(ss, 'developers')

        # 同時加入社群 (如果尚未加入)
        org = get_current_org()
        existing_membership = UserUnitMembership.query.filter_by(
            user_secure_code=user_sc,
            unit_secure_code=ss.group_unit_secure_code,
            is_deleted=False,
        ).first()
        if not existing_membership and org:
            membership = UserUnitMembership(
                org_secure_code=org.secure_code,
                user_secure_code=user_sc,
                unit_secure_code=ss.group_unit_secure_code,
                membership_type=MembershipType.MEMBER,
                role_type=MembershipRole.MEMBER,
            )
            db.session.add(membership)

        db.session.commit()

        return {'success': True}

    @staticmethod
    def remove_developer(secure_code: str, user_sc: str) -> Dict[str, Any]:
        """移除開發者"""
        ss = ResourceGateway.get(
            DcSubSystem, secure_code,
            raise_on_not_found=False,
            check_permission=False,
        )
        if not ss or ss.is_deleted:
            return {'success': False, 'error': '開發案不存在'}

        developers = copy.deepcopy(ss.developers or [])
        if user_sc not in developers:
            return {'success': False, 'error': '該用戶不是開發者'}

        if len(developers) <= 1:
            return {'success': False, 'error': '至少需要保留一位開發者'}

        developers.remove(user_sc)
        ss.developers = developers
        flag_modified(ss, 'developers')
        db.session.commit()

        return {'success': True}

    @staticmethod
    def is_developer(user, sub_system: DcSubSystem) -> bool:
        """檢查用戶是否為開發者 (或管理員)"""
        if getattr(user, 'is_system_admin', False) or getattr(user, 'is_org_admin', False):
            return True
        developers = sub_system.developers or []
        return user.secure_code in developers
