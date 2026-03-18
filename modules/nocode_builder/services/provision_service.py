"""
Data CRUD Module - SubSystem Provision Service
子系統配置服務

供 SubSystemProvisionHandler (workflow node) 呼叫的三合一服務：
  create_sub_system  - 建立子系統 + 選單 + 授予開發者權限
  suspend_sub_system - 停用子系統 + 停用選單
  delete_sub_system  - 軟刪除 + 停用選單 + 撤銷全部開發者權限
"""
import logging
from typing import Dict, Any

from sqlalchemy import func

from app import db
from app.models.menu_item import MenuItem
from app.models.user import User
from app.models.module_access_control import ModuleAccessControl
from app.services.module_access_service import ModuleAccessService
from app.services.code_generator import get_code_generator
from app.security.resource_gateway import ResourceGateway
from app.security.tenant_isolation import TenantContext

from ..models.sub_system import DcSubSystem

logger = logging.getLogger(__name__)

# 子系統選單的 parent code
_SUB_SYSTEM_MENU_PARENT = 'sub_system'

# 模組代碼
_WEB_BUILDER_MODULE = 'nocode_builder'


class SubSystemProvisionService:
    """子系統配置服務（三合一）"""

    # ========================================
    # create
    # ========================================
    @classmethod
    def create_sub_system(
        cls,
        org_sc: str,
        name: str,
        icon: str = '',
        developer_sc: str = '',
    ) -> Dict[str, Any]:
        """
        建立子系統 + 選單 + 授予開發者權限

        Args:
            org_sc: 企業 secure_code
            name: 子系統名稱 (Single Source of Truth)
            icon: 圖示 class (optional)
            developer_sc: 開發者 user secure_code

        Returns:
            {'success': bool, 'error'?: str, 'data'?: dict}
        """
        try:
            if not name:
                return {'success': False, 'error': '子系統名稱為空'}
            if not developer_sc:
                return {'success': False, 'error': '開發者未指定'}

            with TenantContext(org_sc):
                # 驗證開發者帳號
                developer = User.query.filter_by(
                    secure_code=developer_sc,
                    is_deleted=False,
                    is_active=True,
                ).first()
                if not developer:
                    return {'success': False, 'error': '開發者帳號不存在或已停用'}

                # 產生 code（冪等：同名不同 code）
                ss_code = cls._generate_code(org_sc, name)

                # 產生選單 code
                menu_code = f'{_WEB_BUILDER_MODULE}.{ss_code}'

                # Step 1: 建立子系統
                ss = ResourceGateway.create(
                    DcSubSystem,
                    check_permission=False,
                    code=ss_code,
                    name=name,
                    icon=icon,
                    status='draft',
                    developers=[developer_sc],
                    layout_mode='grid',
                    is_active=True,
                )

                # Step 2: 嘗試建立選單項（父選單不存在時跳過）
                menu_item_sc = None
                menu_result = cls._create_menu_item(
                    org_sc=org_sc,
                    code=menu_code,
                    title=name,
                    icon=icon,
                    sub_system_sc=ss.secure_code,
                )
                if menu_result.get('success'):
                    menu_item = menu_result['menu_item']
                    ss.menu_item_secure_code = menu_item.secure_code
                    menu_item_sc = menu_item.secure_code
                    db.session.flush()
                else:
                    logger.warning(
                        'SubSystem menu skipped: %s (sub_system=%s)',
                        menu_result.get('error'), ss_code,
                    )

                # Step 3: 授予開發者 nocode_builder 模組使用權
                cls._grant_module_access(org_sc, developer_sc)

                db.session.commit()

            logger.info(
                'SubSystem created: code=%s, name=%s, developer=%s',
                ss_code, name, developer_sc,
            )

            return {
                'success': True,
                'data': {
                    'sub_system_secure_code': ss.secure_code,
                    'sub_system_code': ss_code,
                    'menu_code': menu_code,
                    'menu_item_secure_code': menu_item_sc,
                },
            }

        except Exception as e:
            logger.error('SubSystem create failed: %s', e, exc_info=True)
            db.session.rollback()
            return {'success': False, 'error': str(e)}

    # ========================================
    # suspend
    # ========================================
    @classmethod
    def suspend_sub_system(
        cls,
        org_sc: str,
        sub_system_code: str,
    ) -> Dict[str, Any]:
        """
        停用子系統 + 停用選單

        Args:
            org_sc: 企業 secure_code
            sub_system_code: 子系統 code
        """
        try:
            with TenantContext(org_sc):
                ss = cls._find_by_code(org_sc, sub_system_code)
                if not ss:
                    return {'success': False, 'error': f'子系統 {sub_system_code} 不存在'}

                ss.is_active = False
                ss.status = 'draft'

                # 停用選單
                cls._set_menu_active(ss.menu_item_secure_code, org_sc, False)

                db.session.commit()

            logger.info('SubSystem suspended: code=%s', sub_system_code)
            return {'success': True}

        except Exception as e:
            logger.error('SubSystem suspend failed: %s', e, exc_info=True)
            db.session.rollback()
            return {'success': False, 'error': str(e)}

    # ========================================
    # delete
    # ========================================
    @classmethod
    def delete_sub_system(
        cls,
        org_sc: str,
        sub_system_code: str,
    ) -> Dict[str, Any]:
        """
        軟刪除子系統 + 停用選單 + 撤銷全部開發者權限

        Args:
            org_sc: 企業 secure_code
            sub_system_code: 子系統 code
        """
        try:
            with TenantContext(org_sc):
                ss = cls._find_by_code(org_sc, sub_system_code)
                if not ss:
                    return {'success': False, 'error': f'子系統 {sub_system_code} 不存在'}

                # 停用選單
                cls._set_menu_active(ss.menu_item_secure_code, org_sc, False)

                # 撤銷全部開發者 nocode_builder 權限
                for dev_sc in (ss.developers or []):
                    cls._revoke_module_access_if_no_other_projects(org_sc, dev_sc, ss.secure_code)

                # 軟刪除子系統
                ResourceGateway.delete(ss, check_permission=False, soft=True)

                db.session.commit()

            logger.info('SubSystem deleted: code=%s', sub_system_code)
            return {'success': True}

        except Exception as e:
            logger.error('SubSystem delete failed: %s', e, exc_info=True)
            db.session.rollback()
            return {'success': False, 'error': str(e)}

    # ========================================
    # 內部輔助
    # ========================================
    @classmethod
    def _generate_code(cls, org_sc: str, name: str) -> str:
        """用 code generator 產生子系統代碼（含衝突處理）"""
        generator = get_code_generator()

        def exists_checker(code):
            return DcSubSystem.query.filter(
                func.upper(DcSubSystem.code) == code.upper(),
                DcSubSystem.org_secure_code == org_sc,
                DcSubSystem.is_deleted == False,
            ).first() is not None

        return generator.generate(name, exists_checker=exists_checker)

    @classmethod
    def _find_by_code(cls, org_sc: str, code: str):
        """依 code + org 查找子系統"""
        return DcSubSystem.query.filter(
            func.upper(DcSubSystem.code) == code.upper(),
            DcSubSystem.org_secure_code == org_sc,
            DcSubSystem.is_deleted == False,
        ).first()

    @classmethod
    def _create_menu_item(
        cls,
        org_sc: str,
        code: str,
        title: str,
        icon: str,
        sub_system_sc: str,
    ) -> Dict[str, Any]:
        """在子系統 header 下建立選單項"""
        parent = MenuItem.query.filter_by(
            code=_SUB_SYSTEM_MENU_PARENT,
            org_secure_code=org_sc,
            is_deleted=False,
        ).first()
        if not parent:
            return {'success': False, 'error': f'找不到子系統父選單 (code={_SUB_SYSTEM_MENU_PARENT})'}

        # 冪等：已存在就跳過
        existing = MenuItem.query.filter_by(
            code=code,
            org_secure_code=org_sc,
            is_deleted=False,
        ).first()
        if existing:
            return {'success': True, 'menu_item': existing}

        max_order = db.session.query(
            db.func.coalesce(db.func.max(MenuItem.display_order), 0)
        ).filter(
            MenuItem.parent_secure_code == parent.secure_code,
            MenuItem.org_secure_code == org_sc,
            MenuItem.is_deleted == False,
        ).scalar()

        menu_item = MenuItem(
            org_secure_code=org_sc,
            parent_secure_code=parent.secure_code,
            code=code,
            title=title,
            icon=icon or '',
            link_type='route',
            link_target=f'/nocode-builder/sub-systems/{sub_system_sc}/portal',
            open_in_new_tab=False,
            display_order=(max_order or 0) + 10,
            depth=parent.depth + 1,
            is_expanded=False,
            is_active=False,
            required_level=2,
            is_shared=False,
        )
        db.session.add(menu_item)
        db.session.flush()

        return {'success': True, 'menu_item': menu_item}

    @classmethod
    def _set_menu_active(cls, menu_item_sc: str, org_sc: str, active: bool):
        """設定選單項啟用狀態"""
        if not menu_item_sc:
            return
        menu_item = MenuItem.query.filter_by(
            secure_code=menu_item_sc,
            org_secure_code=org_sc,
            is_deleted=False,
        ).first()
        if menu_item:
            menu_item.is_active = active

    @classmethod
    def _grant_module_access(cls, org_sc: str, user_sc: str):
        """授予用戶 nocode_builder 模組使用權"""
        ModuleAccessService.add_access(
            org_sc=org_sc,
            module_code=_WEB_BUILDER_MODULE,
            target_type='ACCOUNT',
            target_sc=user_sc,
        )

    @classmethod
    def _revoke_module_access_if_no_other_projects(
        cls, org_sc: str, user_sc: str, exclude_ss_sc: str
    ):
        """
        撤銷 nocode_builder 權限 -- 但只在用戶沒有其他開發案時才撤銷

        避免誤撤：用戶可能同時是多個子系統的開發者
        """
        other_count = DcSubSystem.query.filter(
            DcSubSystem.org_secure_code == org_sc,
            DcSubSystem.is_deleted == False,
            DcSubSystem.secure_code != exclude_ss_sc,
            DcSubSystem.developers.op('?')(user_sc),
        ).count()

        if other_count > 0:
            return

        # 找到並軟刪除 ACL
        record = ModuleAccessControl.query.filter(
            ModuleAccessControl.org_secure_code == org_sc,
            ModuleAccessControl.module_code == _WEB_BUILDER_MODULE,
            ModuleAccessControl.target_type == 'ACCOUNT',
            ModuleAccessControl.target_secure_code == user_sc,
            ModuleAccessControl.is_deleted == False,
        ).first()
        if record:
            from datetime import datetime
            record.is_deleted = True
            record.deleted_at = datetime.utcnow()
