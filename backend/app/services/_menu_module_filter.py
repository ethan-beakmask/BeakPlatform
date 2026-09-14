"""
選單模組過濾 Mixin - 負責模組/合約/ACL/社群相關的選單過濾

方法：
- _filter_by_sub_system_membership: 子系統社群成員過濾
- _get_authorized_modules: 取得企業已授權模組
- _filter_by_contract: 合約過濾
- _get_all_module_menu_codes: 取得所有模組選單 codes
- _get_module_access_menu_codes: ACL 模組選單 codes
- _filter_by_module_access: ACL 過濾
- _get_module_code_for_menu: 選單 → 模組代碼映射
"""
import json
import logging
from datetime import date
from typing import List, Set, Optional

from ..models.menu_item import MenuItem
from ..constants import SYSTEM_ORG_CODE

logger = logging.getLogger(__name__)


class MenuModuleFilterMixin:
    """模組/合約/ACL/社群選單過濾"""

    # 子系統父選單 code
    _SUB_SYSTEM_PARENT_CODE = 'sub_system'

    @classmethod
    def _filter_by_sub_system_membership(
        cls,
        items: List[MenuItem],
        user
    ) -> List[MenuItem]:
        """
        過濾子系統選單: 只有對應社群成員能看到

        透過 DcSubSystem.menu_item_secure_code 反查選單歸屬的子系統，
        再查社群成員身份決定可見性。admin 不經此過濾 (在呼叫端已判斷)。
        """
        try:
            # 找出「子系統」父選單
            sub_system_parent_sc = None
            for item in items:
                if item.code == cls._SUB_SYSTEM_PARENT_CODE:
                    sub_system_parent_sc = item.secure_code
                    break

            if not sub_system_parent_sc:
                return items

            # 收集「子系統」header 下的子選單
            sub_menu_scs = set()
            for item in items:
                if item.parent_secure_code == sub_system_parent_sc:
                    sub_menu_scs.add(item.secure_code)

            if not sub_menu_scs:
                return items

            # 透過 DB 關聯查詢：哪些子系統綁定了這些選單
            from modules.nocode_builder.models.sub_system import DcSubSystem
            sub_systems = DcSubSystem.query.filter(
                DcSubSystem.menu_item_secure_code.in_(sub_menu_scs),
                DcSubSystem.is_deleted == False,
            ).all()

            # menu_sc -> group_unit_sc 映射
            menu_group_map = {
                ss.menu_item_secure_code: ss.group_unit_secure_code
                for ss in sub_systems
                if ss.group_unit_secure_code
            }

            if not menu_group_map:
                # 無任何子系統綁定選單，移除所有子系統子選單
                return [i for i in items if i.secure_code not in sub_menu_scs]

            # 批量查詢用戶的社群成員身份
            from ..models.user_unit_membership import UserUnitMembership
            group_scs = set(menu_group_map.values())

            memberships = UserUnitMembership.query.filter(
                UserUnitMembership.user_secure_code == user.secure_code,
                UserUnitMembership.unit_secure_code.in_(group_scs),
                UserUnitMembership.is_deleted == False,
                UserUnitMembership.is_active == True,
            ).all()
            user_group_scs = {m.unit_secure_code for m in memberships}

            # 過濾
            result = []
            for item in items:
                if item.secure_code not in sub_menu_scs:
                    result.append(item)
                    continue
                # 子系統子選單：檢查社群成員身份
                group_sc = menu_group_map.get(item.secure_code)
                if not group_sc:
                    # 無 DB 關聯的子選單 (手動建立的)，保留
                    result.append(item)
                elif group_sc in user_group_scs:
                    result.append(item)
                # else: 非成員，移除

            return result

        except Exception as e:
            logger.warning('Sub system membership filter failed, skipping: %s', e)
            return items

    @classmethod
    def _get_authorized_modules(cls, user) -> Set[str]:
        """
        取得用戶企業的已授權模組代碼集合

        根據企業所有 ACTIVE 且在有效期限內的合約，
        聯集所有 modules_config 中的模組代碼。

        Args:
            user: 當前用戶

        Returns:
            已授權的模組代碼集合 (如 {'form_workflow', 'nocode_builder'})
        """
        from ..models.contract import Contract, ContractStatus

        org_sc = getattr(user, 'org_secure_code', None)
        if not org_sc:
            return set()

        # 系統企業不受合約限制，授權所有已安裝模組
        if org_sc == SYSTEM_ORG_CODE:
            from .lookup_service import LookupService
            installed_items = LookupService.get_items('INSTALLED_MODULES')
            return {item['code'] for item in installed_items}

        today = date.today()

        contracts = Contract.query.filter(
            Contract.org_secure_code == org_sc,
            Contract.status == ContractStatus.ACTIVE,
            Contract.start_date <= today,
            Contract.end_date >= today,
            Contract.is_deleted == False
        ).all()

        authorized = set()
        for contract in contracts:
            if contract.modules_config:
                try:
                    modules = json.loads(contract.modules_config)
                    if isinstance(modules, list):
                        authorized.update(modules)
                except (json.JSONDecodeError, TypeError):
                    logger.warning(
                        f"Invalid modules_config in contract {contract.contract_number}"
                    )

        return authorized

    @classmethod
    def _filter_by_contract(
        cls,
        items: List[MenuItem],
        authorized_modules: Set[str]
    ) -> List[MenuItem]:
        """
        根據合約授權過濾模組選單

        模組選單的判定方式：code 前綴匹配已安裝模組名稱。
        非模組選單（平台核心選單）不受影響。

        Args:
            items: 選單項目列表
            authorized_modules: 已授權的模組代碼集合

        Returns:
            過濾後的選單項目列表
        """
        from ..services.lookup_service import LookupService

        # 取得所有已安裝模組的代碼 (get_items 回傳 List[dict])
        installed_items = LookupService.get_items('INSTALLED_MODULES')
        installed_module_codes = {item['code'] for item in installed_items}

        if not installed_module_codes:
            return items

        filtered = []
        for item in items:
            # 判斷此選單是否屬於某個模組 (code 前綴匹配)
            module_code = cls._get_module_code_for_menu(item.code, installed_module_codes)

            if module_code is None:
                # 不是模組選單，直接保留
                filtered.append(item)
            elif module_code in authorized_modules:
                # 是模組選單且已授權
                filtered.append(item)
            # else: 模組選單但未授權，過濾掉

        return filtered

    @classmethod
    def _get_all_module_menu_codes(cls) -> Set[str]:
        """
        取得所有已安裝模組的選單 secure_codes

        供 SYSTEM_ADMIN / ORG_ADMIN 使用，讓管理員看到所有模組選單。
        合約過濾在後續 Step 6 處理。

        Returns:
            所有模組選單的 secure_code 集合
        """
        try:
            from .lookup_service import LookupService
            from sqlalchemy import or_

            installed_items = LookupService.get_items('INSTALLED_MODULES')
            installed_module_codes = {item['code'] for item in installed_items}

            if not installed_module_codes:
                return set()

            conditions = []
            for mc in installed_module_codes:
                conditions.append(MenuItem.code == mc)
                conditions.append(MenuItem.code.like(f'{mc}.%'))

            menus = MenuItem.query.filter(
                or_(*conditions),
                MenuItem.is_deleted == False,
                MenuItem.is_active == True
            ).all()

            return {m.secure_code for m in menus}

        except Exception as e:
            logger.warning('_get_all_module_menu_codes failed: %s', e)
            return set()

    @classmethod
    def _get_module_access_menu_codes(cls, user) -> Set[str]:
        """
        根據 module_access_control 取得用戶可見的模組選單 secure_codes

        當用戶透過 /admin/module-permissions 被指派模組使用權時，
        該模組的選單自動加入用戶的可見範圍，不需要 MenuPermission 預先設定。

        Args:
            user: 當前用戶

        Returns:
            模組選單的 secure_code 集合
        """
        try:
            from .module_access_service import ModuleAccessService
            from .lookup_service import LookupService
            from sqlalchemy import or_

            accessible, _controlled = ModuleAccessService.get_accessible_modules(user)
            if not accessible:
                return set()

            # 取得已安裝模組代碼
            installed_items = LookupService.get_items('INSTALLED_MODULES')
            installed_module_codes = {item['code'] for item in installed_items}

            # 交集：用戶可存取 且 已安裝的模組
            target_modules = accessible & installed_module_codes
            if not target_modules:
                return set()

            # 查詢這些模組的選單項目 (code == module_code 或 code LIKE 'module_code.%')
            conditions = []
            for mc in target_modules:
                conditions.append(MenuItem.code == mc)
                conditions.append(MenuItem.code.like(f'{mc}.%'))

            menus = MenuItem.query.filter(
                or_(*conditions),
                MenuItem.is_deleted == False,
                MenuItem.is_active == True
            ).all()

            return {m.secure_code for m in menus}

        except Exception as e:
            logger.warning('_get_module_access_menu_codes failed: %s', e)
            return set()

    @classmethod
    def _filter_by_module_access(
        cls,
        items: List[MenuItem],
        user
    ) -> List[MenuItem]:
        """
        根據模組使用權過濾選單

        有 ACL 記錄的模組才檢查；無 ACL 記錄的模組保留（向下相容）。
        非模組選單不受影響。

        Args:
            items: 選單項目列表
            user: 當前用戶

        Returns:
            過濾後的選單項目列表
        """
        try:
            from .module_access_service import ModuleAccessService
            from .lookup_service import LookupService

            # 取得使用者可存取的模組 + 有 ACL 設定的模組
            accessible, controlled = ModuleAccessService.get_accessible_modules(user)

            if not controlled:
                return items  # 沒有任何 ACL 記錄，全部保留

            # 取得已安裝模組代碼
            installed_items = LookupService.get_items('INSTALLED_MODULES')
            installed_module_codes = {item['code'] for item in installed_items}

            if not installed_module_codes:
                return items

            filtered = []
            for item in items:
                module_code = cls._get_module_code_for_menu(item.code, installed_module_codes)

                if module_code is None:
                    filtered.append(item)
                elif module_code not in controlled:
                    filtered.append(item)
                elif module_code in accessible:
                    filtered.append(item)

            return filtered

        except Exception as e:
            logger.warning('Module access filter failed, skipping: %s', e)
            return items

    @staticmethod
    def _get_module_code_for_menu(menu_code: str, installed_modules: Set[str]) -> Optional[str]:
        """
        判斷選單屬於哪個模組

        匹配規則：menu code == module_code 或 menu code 以 'module_code.' 開頭

        Args:
            menu_code: 選單代碼
            installed_modules: 已安裝模組代碼集合

        Returns:
            模組代碼，或 None（非模組選單）
        """
        for mc in installed_modules:
            if menu_code == mc or menu_code.startswith(f'{mc}.'):
                return mc
        return None
