"""
Data CRUD Module - Project Service
開發案管理服務

負責開發案生命週期: 建立/更新/刪除/上線/下線 + 開發者名單管理
"""
import copy
import logging
from datetime import datetime
from typing import Dict, List, Any

from flask_login import current_user
from sqlalchemy.orm.attributes import flag_modified

from app import db
from app.models.menu_item import MenuItem
from app.models.module_access_control import ModuleAccessControl
from app.models.user import User
from app.services.module_access_service import ModuleAccessService
from app.security.resource_gateway import ResourceGateway
from app.platform.data import get_current_org

from ..models.sub_system import DcSubSystem

logger = logging.getLogger(__name__)

_WEB_BUILDER_MODULE = 'nocode_builder'


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
        建立開發案（手動建立，非流程觸發）

        自動將建立者加入 developers 名單
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

        ss = ResourceGateway.create(
            DcSubSystem,
            check_permission=False,
            name=name,
            description=data.get('description', ''),
            icon=data.get('icon', ''),
            status='draft',
            developers=[user.secure_code],
            layout_mode=layout_mode,
            is_active=True,
        )

        ResourceGateway.commit()

        return {'success': True, 'data': ss.to_dict()}

    @staticmethod
    def update_project(secure_code: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        更新開發案基本資訊

        name 為 Single Source of Truth，同步更新關聯選單標題
        """
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

        # name 改變時同步選單標題
        if 'name' in update_fields and ss.menu_item_secure_code:
            org = get_current_org()
            if org:
                menu_item = MenuItem.query.filter_by(
                    secure_code=ss.menu_item_secure_code,
                    org_secure_code=org.secure_code,
                    is_deleted=False,
                ).first()
                if menu_item:
                    menu_item.title = update_fields['name']

        ResourceGateway.commit()

        return {'success': True, 'data': ss.to_dict()}

    @staticmethod
    def delete_project(secure_code: str) -> Dict[str, Any]:
        """
        軟刪除開發案

        同時：停用選單 + 撤銷無其他開發案的開發者 nocode_builder 權限
        """
        ss = ResourceGateway.get(
            DcSubSystem, secure_code,
            raise_on_not_found=False,
            check_permission=False,
        )
        if not ss or ss.is_deleted:
            return {'success': False, 'error': '開發案不存在'}

        org = get_current_org()
        org_sc = org.secure_code if org else ss.org_secure_code

        # 停用關聯選單
        if ss.menu_item_secure_code:
            menu_item = MenuItem.query.filter_by(
                secure_code=ss.menu_item_secure_code,
                org_secure_code=org_sc,
                is_deleted=False,
            ).first()
            if menu_item:
                menu_item.is_active = False

        # 刪除公開 Portal 路徑記錄
        from .portal_path_service import delete_portal_path
        delete_portal_path(ss.secure_code)

        # 撤銷開發者 nocode_builder 權限（無其他開發案時才撤銷）
        for dev_sc in (ss.developers or []):
            _revoke_if_no_other_projects(org_sc, dev_sc, ss.secure_code)

        ResourceGateway.delete(ss, check_permission=False, soft=True)
        ResourceGateway.commit()

        # 清理子系統 SQLite 檔案
        from .data_source_manager import cleanup_portal_sqlite
        try:
            cleanup_portal_sqlite(ss.secure_code)
        except Exception as e:
            logger.warning(
                'SQLite cleanup failed for project=%s: %s (non-fatal)',
                secure_code, e,
            )

        return {'success': True}

    @staticmethod
    def publish(secure_code: str) -> Dict[str, Any]:
        """上線開發案 -- 同時啟用關聯選單 + 啟用公開路徑"""
        ss = ResourceGateway.get(
            DcSubSystem, secure_code,
            raise_on_not_found=False,
            check_permission=False,
        )
        if not ss or ss.is_deleted:
            return {'success': False, 'error': '開發案不存在'}

        ResourceGateway.update(ss, check_permission=False, status='published')

        # 連動: 啟用關聯選單項（加 org_secure_code 過濾）
        if ss.menu_item_secure_code:
            menu_item = MenuItem.query.filter_by(
                secure_code=ss.menu_item_secure_code,
                org_secure_code=ss.org_secure_code,
                is_deleted=False,
            ).first()
            if menu_item:
                menu_item.is_active = True

        # 連動: 啟用公開 Portal 路徑
        from .portal_path_service import set_active
        set_active(secure_code, True)

        ResourceGateway.commit()

        return {'success': True, 'data': ss.to_dict()}

    @staticmethod
    def unpublish(secure_code: str) -> Dict[str, Any]:
        """下線開發案 -- 同時停用關聯選單 + 停用公開路徑"""
        ss = ResourceGateway.get(
            DcSubSystem, secure_code,
            raise_on_not_found=False,
            check_permission=False,
        )
        if not ss or ss.is_deleted:
            return {'success': False, 'error': '開發案不存在'}

        ResourceGateway.update(ss, check_permission=False, status='draft')

        # 連動: 停用關聯選單項（加 org_secure_code 過濾）
        if ss.menu_item_secure_code:
            menu_item = MenuItem.query.filter_by(
                secure_code=ss.menu_item_secure_code,
                org_secure_code=ss.org_secure_code,
                is_deleted=False,
            ).first()
            if menu_item:
                menu_item.is_active = False

        # 連動: 停用公開 Portal 路徑
        from .portal_path_service import set_active
        set_active(secure_code, False)

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
        """
        新增開發者

        同時授予 nocode_builder 模組使用權
        """
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

        # 授予 nocode_builder 模組使用權
        org = get_current_org()
        if org:
            ModuleAccessService.add_access(
                org_sc=org.secure_code,
                module_code=_WEB_BUILDER_MODULE,
                target_type='ACCOUNT',
                target_sc=user_sc,
            )

        db.session.commit()

        return {'success': True}

    @staticmethod
    def remove_developer(secure_code: str, user_sc: str) -> Dict[str, Any]:
        """
        移除開發者

        同時撤銷 nocode_builder 權限（若無其他開發案）+ 移除社群 membership
        """
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

        org = get_current_org()
        org_sc = org.secure_code if org else ss.org_secure_code

        # 撤銷 nocode_builder 權限（若無其他開發案）
        _revoke_if_no_other_projects(org_sc, user_sc, ss.secure_code)

        # 移除社群 membership（如有關聯社群）
        if ss.group_unit_secure_code:
            from app.models.user_unit_membership import UserUnitMembership
            membership = UserUnitMembership.query.filter_by(
                user_secure_code=user_sc,
                unit_secure_code=ss.group_unit_secure_code,
                is_deleted=False,
            ).first()
            if membership:
                membership.is_deleted = True
                membership.deleted_at = datetime.utcnow()

        db.session.commit()

        return {'success': True}

    @staticmethod
    def is_developer(user, sub_system: DcSubSystem) -> bool:
        """檢查用戶是否為開發者 (或管理員)"""
        if getattr(user, 'is_system_admin', False) or getattr(user, 'is_org_admin', False):
            return True
        developers = sub_system.developers or []
        return user.secure_code in developers


def _revoke_if_no_other_projects(org_sc: str, user_sc: str, exclude_ss_sc: str):
    """撤銷 nocode_builder 權限 -- 用戶沒有其他開發案時才撤銷"""
    other_count = DcSubSystem.query.filter(
        DcSubSystem.org_secure_code == org_sc,
        DcSubSystem.is_deleted == False,
        DcSubSystem.secure_code != exclude_ss_sc,
        DcSubSystem.developers.op('?')(user_sc),
    ).count()

    if other_count > 0:
        return

    record = ModuleAccessControl.query.filter(
        ModuleAccessControl.org_secure_code == org_sc,
        ModuleAccessControl.module_code == _WEB_BUILDER_MODULE,
        ModuleAccessControl.target_type == 'ACCOUNT',
        ModuleAccessControl.target_secure_code == user_sc,
        ModuleAccessControl.is_deleted == False,
    ).first()
    if record:
        record.is_deleted = True
        record.deleted_at = datetime.utcnow()
