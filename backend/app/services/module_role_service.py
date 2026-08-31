"""
BeakPlatform - Module Role Service
模組預設角色服務

模組可在 MODULE_INFO 宣告一套「模組預設角色」，採購（合約含）該模組的企業
自動獲得這套企業內角色，解決模組功能無適當角色可配發的缺口。

MODULE_INFO 宣告格式:
    'default_roles': [
        {
            'code': 'SECURITY_STAFF',          # 角色代碼（企業內唯一）
            'name': '資安人員',                 # 角色名稱
            'description': '...',              # 描述（選填）
            'permissions': ['open_defense.view'],  # 模組 permission codes（選填）
        },
    ],
    'default_menu_role_requirements': {        # 雙鑰匙 Key2（選填）
        'open_defense.security_cases': ['SECURITY_STAFF'],
    },
    'default_acl_roles': ['SECURITY_STAFF'],   # 模組預設 ACL（選填，
        # fail-closed 配套：僅在該企業該模組零筆 ACL 時種入 ROLE 型記錄）

Seeding 時機:
1. 企業新增合約時（OrganizationService.create_contract 依 modules_config 觸發）
2. `flask module sync` 對所有持有效合約的企業補種（解決既存合約）

碰撞政策: 企業已有同 code 角色時跳過不覆蓋（保護企業自訂角色），
但 Key2 需求仍會綁到該既有角色上。
"""
import json
import logging
from datetime import date
from typing import Any, Dict, List

from sqlalchemy import text

from .. import db
from ..constants import SYSTEM_ORG_CODE
from ..models import MenuItem
from ..models.role import Role, RoleType, ScopeType, RoleLevel

logger = logging.getLogger(__name__)


class ModuleRoleService:
    """模組預設角色服務"""

    @classmethod
    def seed_org_module_roles(
        cls,
        org_secure_code: str,
        module: Any,
    ) -> Dict[str, int]:
        """
        為單一企業種入單一模組的預設角色與 Key2 需求

        Args:
            org_secure_code: 目標企業 secure_code
            module: ModuleInfo（需有 name / default_roles /
                    default_menu_role_requirements 屬性）

        Returns:
            {'roles_created': n, 'roles_skipped': n,
             'perms_assigned': n, 'mrr_created': n}
        """
        from ..models.menu_role_requirement import MenuRoleRequirement
        from ..models.permission import Permission
        from ..models.role_permission import RolePermission

        result = {
            'roles_created': 0, 'roles_skipped': 0,
            'perms_assigned': 0, 'mrr_created': 0,
            'acl_created': 0, 'acl_skipped': 0,
        }

        role_defs: List[Dict] = getattr(module, 'default_roles', []) or []
        menu_reqs: Dict[str, List[str]] = getattr(
            module, 'default_menu_role_requirements', {}) or {}
        acl_roles: List[str] = getattr(module, 'default_acl_roles', []) or []

        if not role_defs and not menu_reqs and not acl_roles:
            return result

        # 系統企業不受合約限制，也不需要模組角色
        if org_secure_code == SYSTEM_ORG_CODE:
            return result

        # 繞過 RLS（seeding 屬系統層操作）
        db.session.execute(text("SET LOCAL app.is_system_admin = 'true'"))

        # 企業既有角色 code → secure_code（含企業自訂角色，碰撞檢查用）
        org_roles = Role.query.filter(
            Role.org_secure_code == org_secure_code,
            Role.is_deleted == False,
        ).all()
        role_code_to_sc = {r.code: r.secure_code for r in org_roles}

        # ---- 1. 種角色 ----
        for role_def in role_defs:
            code = role_def.get('code')
            name = role_def.get('name')
            if not code or not name:
                logger.warning(
                    f"Module {module.name}: invalid default_role definition "
                    f"(missing code or name): {role_def}"
                )
                continue

            if code in role_code_to_sc:
                # 碰撞政策：不覆蓋企業既有同 code 角色
                result['roles_skipped'] += 1
                continue

            role = Role(
                org_secure_code=org_secure_code,
                role_type=RoleType.ROLE,
                scope_type=ScopeType.GLOBAL,
                role_level=RoleLevel.MODULE,
                code=code,
                name=name,
                description=role_def.get('description'),
                is_manager=False,
                is_system_role=True,
                is_active=True,
            )
            role.update_full_path()
            db.session.add(role)
            db.session.flush()  # 取得 secure_code
            role_code_to_sc[code] = role.secure_code
            result['roles_created'] += 1

            # 角色權限（僅新建角色才種，跳過的角色維持企業自行配置）
            perm_codes = role_def.get('permissions') or []
            if perm_codes:
                perms = Permission.query.filter(
                    Permission.code.in_(perm_codes),
                    Permission.is_deleted == False,
                    Permission.is_active == True,
                ).all()
                for perm in perms:
                    db.session.add(RolePermission(
                        role_secure_code=role.secure_code,
                        permission_secure_code=perm.secure_code,
                        is_active=True,
                    ))
                    result['perms_assigned'] += 1

        # ---- 2. 種選單角色需求（雙鑰匙 Key2）----
        if menu_reqs:
            menu_items = MenuItem.query.filter(
                MenuItem.code.in_(list(menu_reqs.keys())),
                MenuItem.is_deleted == False,
            ).all()
            menu_code_to_item = {m.code: m for m in menu_items}

            existing_mrrs = MenuRoleRequirement.query.filter(
                MenuRoleRequirement.org_secure_code == org_secure_code,
                MenuRoleRequirement.is_deleted == False,
            ).all()
            existing_keys = {
                (m.menu_secure_code, m.role_secure_code)
                for m in existing_mrrs
            }

            for menu_code, role_codes in menu_reqs.items():
                item = menu_code_to_item.get(menu_code)
                if not item:
                    logger.warning(
                        f"Module {module.name}: menu '{menu_code}' not found, "
                        f"skipping Key2 seed for org {org_secure_code}"
                    )
                    continue

                # header/divider 不吃鑰匙2（結構元素，可見性由可見子項決定），
                # 種了只會產生死資料
                if item.link_type in ('header', 'divider'):
                    logger.warning(
                        f"Module {module.name}: menu '{menu_code}' is a "
                        f"structural element ({item.link_type}), Key2 does "
                        f"not apply — skipping"
                    )
                    continue

                for role_code in role_codes:
                    role_sc = role_code_to_sc.get(role_code)
                    if not role_sc:
                        continue

                    key = (item.secure_code, role_sc)
                    if key in existing_keys:
                        continue

                    db.session.add(MenuRoleRequirement(
                        menu_secure_code=item.secure_code,
                        role_secure_code=role_sc,
                        org_secure_code=org_secure_code,
                    ))
                    existing_keys.add(key)
                    result['mrr_created'] += 1

        # ---- 3. 種模組預設 ACL（fail-closed 配套，PF-145 階段三之一）----
        if acl_roles:
            from .module_access_service import ModuleAccessService
            acl_result = ModuleAccessService.seed_org_module_acl(
                org_secure_code, module)
            result['acl_created'] = acl_result['acl_created']
            result['acl_skipped'] = acl_result['acl_skipped']

        if result['roles_created'] or result['mrr_created']:
            logger.info(
                f"Module {module.name}: seeded default roles for org "
                f"{org_secure_code}: {result}"
            )

        return result

    @classmethod
    def seed_contract_module_roles(
        cls,
        org_secure_code: str,
        module_codes: List[str],
    ) -> Dict[str, Dict[str, int]]:
        """
        依合約的模組清單為企業種入各模組的預設角色

        由 OrganizationService.create_contract 在新增合約時呼叫。
        不 commit，交由呼叫端統一處理。

        Returns:
            {module_name: seed result}
        """
        from ..module_loader import module_loader

        results = {}
        for code in module_codes or []:
            module = module_loader.get_module(code)
            if not module or not module.enabled:
                continue
            results[code] = cls.seed_org_module_roles(org_secure_code, module)
        return results

    @classmethod
    def sync_all_module_roles(
        cls,
        module_loader,
    ) -> Dict[str, Dict[str, int]]:
        """
        為所有持有效合約的企業補種模組預設角色（冪等）

        由 `flask module sync` 呼叫，解決機制上線前已存在的合約。

        Returns:
            {module_name: 彙總 seed result}
        """
        from ..models.contract import Contract, ContractStatus

        db.session.execute(text("SET LOCAL app.is_system_admin = 'true'"))

        # 建立 org → 已授權模組集合（ACTIVE 且在效期內的合約聯集）
        today = date.today()
        contracts = Contract.query.filter(
            Contract.status == ContractStatus.ACTIVE,
            Contract.start_date <= today,
            Contract.end_date >= today,
            Contract.is_deleted == False,
        ).all()

        org_modules: Dict[str, set] = {}
        for contract in contracts:
            if not contract.modules_config:
                continue
            try:
                modules = json.loads(contract.modules_config)
            except (json.JSONDecodeError, TypeError):
                logger.warning(
                    f"Invalid modules_config in contract "
                    f"{contract.contract_number}"
                )
                continue
            if isinstance(modules, list):
                org_modules.setdefault(
                    contract.org_secure_code, set()).update(modules)

        # 逐模組彙總
        results: Dict[str, Dict[str, int]] = {}
        for module in module_loader.get_loaded_modules():
            role_defs = getattr(module, 'default_roles', []) or []
            menu_reqs = getattr(
                module, 'default_menu_role_requirements', {}) or {}
            acl_roles = getattr(module, 'default_acl_roles', []) or []
            if not role_defs and not menu_reqs and not acl_roles:
                continue

            total = {
                'roles_created': 0, 'roles_skipped': 0,
                'perms_assigned': 0, 'mrr_created': 0,
                'acl_created': 0, 'acl_skipped': 0,
            }
            for org_sc, modules in org_modules.items():
                if module.name not in modules:
                    continue
                try:
                    sub = cls.seed_org_module_roles(org_sc, module)
                    for k in total:
                        total[k] += sub[k]
                except Exception as e:
                    logger.error(
                        f"Failed to seed roles of {module.name} "
                        f"for org {org_sc}: {e}"
                    )
                    raise
            results[module.name] = total

        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to commit module role sync: {e}")
            raise

        return results
