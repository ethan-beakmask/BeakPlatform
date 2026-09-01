"""
BeakMask Module Access Service
模組使用權服務

控制企業內「誰能使用哪個模組」。
支援指派到角色 (ROLE)、部門 (DEPARTMENT)、群組 (GROUP)、帳號 (ACCOUNT)。

fail-closed（2026-09-01 PF-145 階段三之一起）:
某模組在某企業沒有任何 ACL 記錄 = 拒絕（僅 ORG_ADMIN 經 decorator 層放行）。
配套：模組於 MODULE_INFO 宣告 default_acl_roles，合約建立與
`flask module sync` 時由 ModuleRoleService 觸發 seed_org_module_acl 種入。
此前為 fail-open（無記錄 = 不限制），舊行為勿再引用。
"""
import json
import logging
from datetime import datetime
from typing import Set, Dict, Any, List, Tuple, Optional

from ..models.module_access_control import ModuleAccessControl, TargetType
from ..models.associations import UserRoleAssignment, UserUnitAssignment
from ..models.user_unit_membership import UserUnitMembership, MembershipType
from ..models.user import User, UserType
from ..models.role import Role
from ..models.organizational_unit import OrganizationalUnit, UnitType
from ..utils.timezone import local_today
from .. import db

logger = logging.getLogger(__name__)


class ModuleAccessService:
    """模組使用權服務"""

    @classmethod
    def get_accessible_modules(cls, user) -> Tuple[Set[str], Set[str]]:
        """
        取得使用者可存取的模組集合

        Returns:
            (accessible, controlled)
            - accessible: 使用者可用的模組代碼集合
            - controlled: 有設定 ACL 的模組代碼集合（用於選單過濾判斷）
        """
        org_sc = getattr(user, 'org_secure_code', None)
        if not org_sc:
            return set(), set()

        try:
            # 取得此企業所有未刪除的 ACL 記錄
            records = ModuleAccessControl.query.filter(
                ModuleAccessControl.org_secure_code == org_sc,
                ModuleAccessControl.is_deleted == False
            ).all()

            if not records:
                return set(), set()

            # 分組: module_code -> [records]
            module_records: Dict[str, List[ModuleAccessControl]] = {}
            for r in records:
                module_records.setdefault(r.module_code, []).append(r)

            controlled = set(module_records.keys())

            # 取得使用者的所有身份標識
            user_identifiers = cls._get_user_identifiers(user)

            accessible = set()
            for module_code, acl_list in module_records.items():
                for acl in acl_list:
                    key = (acl.target_type, acl.target_secure_code)
                    if key in user_identifiers:
                        accessible.add(module_code)
                        break

            return accessible, controlled

        except Exception as e:
            logger.warning('get_accessible_modules failed: %s', e)
            db.session.rollback()
            return set(), set()

    @classmethod
    def check_user_access(cls, user, module_code: str) -> bool:
        """
        檢查使用者是否有權存取指定模組

        fail-closed: 無 ACL 記錄 = 拒絕（PF-145 階段三之一）。
        正常情況合約建立時已種入 default_acl_roles，走到無記錄代表
        該企業 ACL 被清空，此時僅 ORG_ADMIN（decorator 層放行）可用。
        """
        org_sc = getattr(user, 'org_secure_code', None)
        if not org_sc:
            return False

        records = ModuleAccessControl.query.filter(
            ModuleAccessControl.org_secure_code == org_sc,
            ModuleAccessControl.module_code == module_code,
            ModuleAccessControl.is_deleted == False
        ).all()

        if not records:
            return False  # fail-closed：無 ACL 記錄 = 拒絕

        user_identifiers = cls._get_user_identifiers(user)
        for r in records:
            if (r.target_type, r.target_secure_code) in user_identifiers:
                return True

        return False

    @classmethod
    def get_access_list(
        cls,
        org_sc: str,
        module_code: str
    ) -> List[Dict[str, Any]]:
        """
        取得模組的 ACL 列表（含 target 名稱解析）
        """
        records = ModuleAccessControl.query.filter(
            ModuleAccessControl.org_secure_code == org_sc,
            ModuleAccessControl.module_code == module_code,
            ModuleAccessControl.is_deleted == False
        ).order_by(
            ModuleAccessControl.target_type,
            ModuleAccessControl.created_at
        ).all()

        result = []
        for r in records:
            item = r.to_dict()
            item['target_name'] = cls._resolve_target_name(
                r.target_type, r.target_secure_code
            )
            result.append(item)

        return result

    @classmethod
    def add_access(
        cls,
        org_sc: str,
        module_code: str,
        target_type: str,
        target_sc: str
    ) -> Optional[ModuleAccessControl]:
        """
        新增 ACL 記錄

        Returns:
            ModuleAccessControl 或 None (重複)
        """
        if target_type not in TargetType.ALL:
            raise ValueError(f'Invalid target_type: {target_type}')

        # 檢查是否已存在
        existing = ModuleAccessControl.query.filter(
            ModuleAccessControl.org_secure_code == org_sc,
            ModuleAccessControl.module_code == module_code,
            ModuleAccessControl.target_type == target_type,
            ModuleAccessControl.target_secure_code == target_sc,
            ModuleAccessControl.is_deleted == False
        ).first()

        if existing:
            return None

        record = ModuleAccessControl(
            org_secure_code=org_sc,
            module_code=module_code,
            target_type=target_type,
            target_secure_code=target_sc,
        )
        db.session.add(record)
        db.session.flush()

        return record

    @classmethod
    def remove_access(cls, secure_code: str, org_secure_code: str) -> bool:
        """
        軟刪除 ACL 記錄

        Args:
            secure_code: ACL 記錄識別碼
            org_secure_code: 企業識別碼（強制租戶隔離）

        Returns:
            是否成功刪除
        """
        record = ModuleAccessControl.query.filter(
            ModuleAccessControl.secure_code == secure_code,
            ModuleAccessControl.org_secure_code == org_secure_code,
            ModuleAccessControl.is_deleted == False
        ).first()

        if not record:
            return False

        record.is_deleted = True
        record.deleted_at = datetime.utcnow()
        return True

    # ========================================
    # 預設 ACL 種入（fail-closed 配套）
    # ========================================

    @classmethod
    def seed_org_module_acl(cls, org_secure_code: str, module) -> Dict[str, int]:
        """
        依模組宣告的 default_acl_roles 為單一企業種入 ROLE 型 ACL

        僅在該 (企業, 模組) 目前沒有任何未刪除 ACL 記錄時種入——
        已有記錄代表企業已自行設定，不覆蓋也不補充。
        角色以 code 在該企業內解析（出廠角色由 _create_default_roles 保證存在），
        解析不到記 warning 跳過。不 commit，交由呼叫端統一處理。

        Args:
            org_secure_code: 目標企業 secure_code
            module: ModuleInfo（需有 name / default_acl_roles 屬性）

        Returns:
            {'acl_created': n, 'acl_skipped': n（已設定或角色缺失）}
        """
        result = {'acl_created': 0, 'acl_skipped': 0}

        acl_roles: List[str] = getattr(module, 'default_acl_roles', []) or []
        if not acl_roles:
            return result

        existing = ModuleAccessControl.query.filter(
            ModuleAccessControl.org_secure_code == org_secure_code,
            ModuleAccessControl.module_code == module.name,
            ModuleAccessControl.is_deleted == False,
        ).count()
        if existing:
            result['acl_skipped'] = len(acl_roles)
            return result

        org_roles = Role.query.filter(
            Role.org_secure_code == org_secure_code,
            Role.code.in_(acl_roles),
            Role.is_deleted == False,
        ).all()
        role_code_to_sc = {r.code: r.secure_code for r in org_roles}

        for role_code in acl_roles:
            role_sc = role_code_to_sc.get(role_code)
            if not role_sc:
                logger.warning(
                    'seed_org_module_acl: role %s not found in org %s '
                    '(module %s), skipping', role_code, org_secure_code,
                    module.name)
                result['acl_skipped'] += 1
                continue
            db.session.add(ModuleAccessControl(
                org_secure_code=org_secure_code,
                module_code=module.name,
                target_type=TargetType.ROLE,
                target_secure_code=role_sc,
            ))
            result['acl_created'] += 1

        db.session.flush()
        return result

    # ========================================
    # 合約驗證
    # ========================================

    @classmethod
    def check_module_contract(cls, user, module_code: str) -> bool:
        """
        檢查用戶企業是否擁有指定模組的有效合約

        系統企業 (SYSTEM_ORG_CODE) 不受合約限制。

        Args:
            user: 當前用戶
            module_code: 模組代碼 (如 'form_workflow')

        Returns:
            True = 有合約授權, False = 無合約
        """
        from ..models.contract import Contract, ContractStatus
        from ..constants import SYSTEM_ORG_CODE

        org_sc = getattr(user, 'org_secure_code', None)
        if not org_sc:
            return False

        # 系統企業不受合約限制
        if org_sc == SYSTEM_ORG_CODE:
            return True

        org = getattr(user, 'organization', None)
        today = org.local_today() if org else local_today('Asia/Taipei')

        contracts = Contract.query.filter(
            Contract.org_secure_code == org_sc,
            Contract.status == ContractStatus.ACTIVE,
            Contract.start_date <= today,
            Contract.end_date >= today,
            Contract.is_deleted == False
        ).all()

        for contract in contracts:
            if contract.modules_config:
                try:
                    modules = json.loads(contract.modules_config)
                    if isinstance(modules, list) and module_code in modules:
                        return True
                except (json.JSONDecodeError, TypeError):
                    pass

        return False

    # ========================================
    # 內部方法
    # ========================================

    @classmethod
    def _get_user_identifiers(cls, user) -> Set[Tuple[str, str]]:
        """
        取得使用者的所有身份標識 (target_type, target_secure_code) 集合

        包含:
        - (ACCOUNT, user.secure_code)
        - (ROLE, role_sc) -- 來自 UserRoleAssignment
        - (DEPARTMENT, unit_sc) -- 來自 UserUnitMembership (SOLID/DOTTED)
        - (GROUP, unit_sc) -- 來自 UserUnitMembership (MEMBER)
        """
        identifiers = set()

        # ACCOUNT
        identifiers.add((TargetType.ACCOUNT, user.secure_code))

        # ROLE
        role_assignments = UserRoleAssignment.query.filter(
            UserRoleAssignment.user_secure_code == user.secure_code,
            UserRoleAssignment.is_deleted == False
        ).all()
        for ra in role_assignments:
            if ra.is_valid:
                identifiers.add((TargetType.ROLE, ra.role_secure_code))

        # DEPARTMENT + GROUP (via UserUnitMembership)
        memberships = UserUnitMembership.query.filter(
            UserUnitMembership.user_secure_code == user.secure_code,
            UserUnitMembership.is_deleted == False
        ).all()
        for m in memberships:
            if not m.is_active:
                continue
            if m.membership_type in (MembershipType.SOLID, MembershipType.DOTTED):
                identifiers.add((TargetType.DEPARTMENT, m.unit_secure_code))
            elif m.membership_type == MembershipType.MEMBER:
                identifiers.add((TargetType.GROUP, m.unit_secure_code))

        return identifiers

    @classmethod
    def _resolve_target_name(cls, target_type: str, target_sc: str) -> str:
        """解析 target 的顯示名稱"""
        try:
            if target_type == TargetType.ACCOUNT:
                user = User.query.filter(
                    User.secure_code == target_sc,
                    User.is_deleted == False
                ).first()
                return user.display_name if user else f'[unknown:{target_sc}]'

            elif target_type == TargetType.ROLE:
                role = Role.query.filter(
                    Role.secure_code == target_sc,
                    Role.is_deleted == False
                ).first()
                return role.name if role else f'[unknown:{target_sc}]'

            elif target_type in (TargetType.DEPARTMENT, TargetType.GROUP):
                unit = OrganizationalUnit.query.filter(
                    OrganizationalUnit.secure_code == target_sc,
                    OrganizationalUnit.is_deleted == False
                ).first()
                return unit.name if unit else f'[unknown:{target_sc}]'

        except Exception as e:
            logger.warning('Failed to resolve target name: %s', e)

        return f'[{target_type}:{target_sc}]'

    @classmethod
    def get_available_targets(
        cls,
        org_sc: str,
        target_type: str,
        query: str = ''
    ) -> List[Dict[str, Any]]:
        """
        取得可選的 target 清單（用於 UI 下拉選單）
        """
        results = []
        q = query.strip().lower()

        if target_type == TargetType.ACCOUNT:
            users = User.query.filter(
                User.org_secure_code == org_sc,
                User.is_deleted == False,
                User.is_active == True
            ).order_by(User.display_name).all()
            for u in users:
                if q and q not in u.display_name.lower() and q not in u.username.lower():
                    continue
                results.append({
                    'secure_code': u.secure_code,
                    'name': u.display_name,
                    'detail': u.username,
                })

        elif target_type == TargetType.ROLE:
            roles = Role.query.filter(
                Role.org_secure_code == org_sc,
                Role.is_deleted == False
            ).order_by(Role.name).all()
            for r in roles:
                if q and q not in r.name.lower() and q not in (r.code or '').lower():
                    continue
                results.append({
                    'secure_code': r.secure_code,
                    'name': r.name,
                    'detail': r.code or '',
                })

        elif target_type == TargetType.DEPARTMENT:
            units = OrganizationalUnit.query.filter(
                OrganizationalUnit.org_secure_code == org_sc,
                OrganizationalUnit.unit_type == UnitType.DEPARTMENT,
                OrganizationalUnit.is_deleted == False
            ).order_by(OrganizationalUnit.name).all()
            for u in units:
                if q and q not in u.name.lower() and q not in (u.code or '').lower():
                    continue
                results.append({
                    'secure_code': u.secure_code,
                    'name': u.name,
                    'detail': u.code or '',
                })

        elif target_type == TargetType.GROUP:
            units = OrganizationalUnit.query.filter(
                OrganizationalUnit.org_secure_code == org_sc,
                OrganizationalUnit.unit_type == UnitType.GROUP,
                OrganizationalUnit.is_deleted == False
            ).order_by(OrganizationalUnit.name).all()
            for u in units:
                if q and q not in u.name.lower() and q not in (u.code or '').lower():
                    continue
                results.append({
                    'secure_code': u.secure_code,
                    'name': u.name,
                    'detail': u.code or '',
                })

        return results
