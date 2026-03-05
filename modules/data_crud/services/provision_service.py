"""
Data CRUD Module - SubSystem Provision Service
子系統開發申請配置服務

當「子系統開發申請」表單審批通過後，自動:
1. 建立開發案 (子系統 + 社群 + 開發者)
2. 建立選單項 (子系統 header 下)
3. 授予申請者 web_builder 模組使用權
4. 關聯子系統與選單項
"""
import logging
from typing import Dict, Any

from flask import g

from app import db
from app.models.menu_item import MenuItem
from app.models.user import User
from app.models.organizational_unit import OrganizationalUnit, UnitType
from app.models.user_unit_membership import (
    UserUnitMembership, MembershipType, MembershipRole,
)
from app.services.module_access_service import ModuleAccessService
from app.security.resource_gateway import ResourceGateway

from ..models.sub_system import DcSubSystem

logger = logging.getLogger(__name__)

# 表單識別: form_name 或 form_code
_TRIGGER_FORM_NAME = '子系統開發申請'
_TRIGGER_FORM_CODE = 'FORM_WF8AEB7774_EA31'

# 子系統選單的 parent code
_SUB_SYSTEM_MENU_CODE = 'sub_system'

# 模組代碼
_WEB_BUILDER_MODULE = 'web_builder'


class SubSystemProvisionService:
    """子系統開發申請配置服務"""

    @classmethod
    def should_provision(cls, form_instance) -> bool:
        """判斷此表單是否為子系統開發申請"""
        form_name = getattr(form_instance, 'form_name', '') or ''
        form_code = getattr(form_instance, 'form_code', '') or ''
        return (
            form_name == _TRIGGER_FORM_NAME
            or form_code == _TRIGGER_FORM_CODE
        )

    @classmethod
    def provision(cls, form_instance) -> Dict[str, Any]:
        """
        依據審批通過的申請單配置子系統

        不依賴 current_user/request context，直接用 form_instance 的資料。

        Args:
            form_instance: FwFormInstance (status=APPROVED)

        Returns:
            {'success': bool, 'error'?: str, 'data'?: dict}
        """
        try:
            form_data = form_instance.form_data or {}
            applicant_sc = form_instance.applicant_secure_code
            org_sc = form_instance.org_secure_code

            if not applicant_sc or not org_sc:
                return {'success': False, 'error': '申請者或企業資訊不完整'}

            # 設定 tenant context (ResourceGateway 需要)
            g.current_org_secure_code = org_sc

            # 解析表單欄位
            sub_system_name = form_data.get('dc_sub_systems_name', '').strip()
            menu_code = form_data.get('menu_items_code', '').strip()
            menu_title = form_data.get('menu_items_title', '').strip()
            menu_icon = form_data.get('menu_items_icon', '').strip()

            if not sub_system_name:
                return {'success': False, 'error': '子系統名稱為空'}
            if not menu_code:
                return {'success': False, 'error': '選單代碼為空'}
            if not menu_title:
                menu_title = sub_system_name

            # 取得申請者 User 物件
            applicant = User.query.filter_by(
                secure_code=applicant_sc,
                is_deleted=False,
                is_active=True,
            ).first()
            if not applicant:
                return {'success': False, 'error': '申請者帳號不存在或已停用'}

            # Step 1: 建立社群
            group_code = 'PRJ_' + sub_system_name.upper().replace(' ', '_')[:30]
            group = OrganizationalUnit(
                org_secure_code=org_sc,
                unit_type=UnitType.GROUP,
                code=group_code,
                name=sub_system_name,
                description=f'開發案「{sub_system_name}」社群 (申請單 {form_instance.serial_number})',
                is_active=True,
            )
            group.update_full_path()
            db.session.add(group)
            db.session.flush()

            # Step 2: 建立子系統
            ss = ResourceGateway.create(
                DcSubSystem,
                check_permission=False,
                name=sub_system_name,
                description=f'由申請單 {form_instance.serial_number} 自動建立',
                icon=menu_icon,
                group_unit_secure_code=group.secure_code,
                status='draft',
                developers=[applicant_sc],
                layout_mode='grid',
                is_active=True,
            )

            # Step 3: 申請者成為社群 MANAGER
            membership = UserUnitMembership(
                org_secure_code=org_sc,
                user_secure_code=applicant_sc,
                unit_secure_code=group.secure_code,
                membership_type=MembershipType.MEMBER,
                role_type=MembershipRole.MANAGER,
            )
            db.session.add(membership)
            db.session.flush()

            # Step 4: 建立選單項 (子系統 header 下)
            menu_result = cls._create_menu_item(
                org_sc=org_sc,
                code=menu_code,
                title=menu_title,
                icon=menu_icon,
                sub_system_sc=ss.secure_code,
            )
            if not menu_result.get('success'):
                db.session.rollback()
                return {
                    'success': False,
                    'error': f'建立選單失敗: {menu_result.get("error")}',
                }

            menu_item = menu_result['menu_item']

            # Step 5: 關聯子系統 → 選單項
            ss.menu_item_secure_code = menu_item.secure_code
            db.session.flush()

            # Step 6: 授予申請者 web_builder 模組使用權
            cls._grant_module_access(org_sc, applicant_sc)

            db.session.commit()

            logger.info(
                'SubSystem provisioned: serial=%s, sub_system=%s, menu=%s, applicant=%s',
                form_instance.serial_number, ss.secure_code, menu_item.secure_code, applicant_sc,
            )

            return {
                'success': True,
                'data': {
                    'sub_system_secure_code': ss.secure_code,
                    'menu_item_secure_code': menu_item.secure_code,
                    'serial_number': form_instance.serial_number,
                },
            }

        except Exception as e:
            logger.error('SubSystem provision failed: %s', e, exc_info=True)
            db.session.rollback()
            return {'success': False, 'error': str(e)}

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
        # 找到「子系統」父選單
        parent = MenuItem.query.filter_by(
            code=_SUB_SYSTEM_MENU_CODE,
            org_secure_code=org_sc,
            is_deleted=False,
        ).first()
        if not parent:
            return {'success': False, 'error': f'找不到子系統父選單 (code={_SUB_SYSTEM_MENU_CODE})'}

        # 檢查是否已有同 code 的選單 (避免重複)
        existing = MenuItem.query.filter_by(
            code=code,
            org_secure_code=org_sc,
            is_deleted=False,
        ).first()
        if existing:
            return {'success': False, 'error': f'選單代碼 {code} 已存在'}

        # 計算 display_order (取最大值 +10)
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
            link_target=f'/data-crud/sub-systems/{sub_system_sc}/portal',
            open_in_new_tab=False,
            display_order=(max_order or 0) + 10,
            depth=parent.depth + 1,
            is_expanded=False,
            is_active=False,  # 上線 (publish) 時才啟用
            required_level=2,
            is_shared=False,
        )
        db.session.add(menu_item)
        db.session.flush()

        return {'success': True, 'menu_item': menu_item}

    @classmethod
    def _grant_module_access(cls, org_sc: str, user_sc: str):
        """授予用戶 web_builder 模組使用權 (ACCOUNT 類型)"""
        ModuleAccessService.add_access(
            org_sc=org_sc,
            module_code=_WEB_BUILDER_MODULE,
            target_type='ACCOUNT',
            target_sc=user_sc,
        )
