"""
BeakPlatform Permission Central Service
權限中央管理服務

整合查詢五層權限設定，提供角色視角、功能視角、衝突偵測。
RBAC 出廠預設值管理（儲存、匯出、匯入、恢復）。

安全設計：
- SYSTEM_ADMIN: 可看全部角色/選單/權限，可操作全部
- ORG_ADMIN: 只能看到自己企業 + system.local 共用角色，
  只能看到授權給 ORG_ADMIN/EMPLOYEE/EXTERNAL 的選單，
  不能操作 SYSTEM 級權限
"""
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from flask import g
from flask_login import current_user
from sqlalchemy import func, or_

from ..models import (
    MenuItem, MenuPermission, MenuRoleRequirement,
    Role, RolePermission, Permission, UserRoleAssignment,
    User, UserType, RbacDefault
)
from ..constants import SYSTEM_ORG_CODE
from .. import db

logger = logging.getLogger(__name__)

# ORG_ADMIN 可見的 user_types（排除 SYSTEM_ADMIN 專屬）
_ORG_VISIBLE_USER_TYPES = {'ORG_ADMIN', 'EMPLOYEE', 'EXTERNAL'}


class PermissionCentralService:
    """
    權限中央管理服務

    整合五層權限：
    1. MenuPermission -- user_type 選單可見性
    2. MenuRoleRequirement -- 角色存取需求
    3. RolePermission -- 角色 RBAC 權限
    4. required_permission -- 選單最低權限門檻
    5. UserRoleAssignment -- 用戶角色指派
    """

    # ==================================================================
    # 角色視角
    # ==================================================================

    @classmethod
    def get_role_view(
        cls, role_secure_code: str, org_secure_code: str,
        is_system_admin: bool = False
    ) -> Dict[str, Any]:
        """
        角色視角：選定角色，看到它在各層的完整授權

        Args:
            role_secure_code: 角色 secure_code
            org_secure_code: 企業 secure_code
            is_system_admin: 是否為系統管理員

        Returns:
            角色在各層的完整授權資訊
        """
        # 查詢角色並驗證存取權
        role_query = Role.query.filter_by(
            secure_code=role_secure_code,
            is_deleted=False
        )
        if not is_system_admin:
            role_query = role_query.filter(Role.org_secure_code == org_secure_code)
        role = role_query.first()
        if not role:
            return {'error': '角色不存在或無權限存取'}

        # 角色所屬企業名稱
        role_org_label = cls._get_org_label(role.org_secure_code)

        # 哪些選單指定了此角色為存取需求 (MenuRoleRequirement)
        menu_role_reqs = MenuRoleRequirement.query.filter_by(
            role_secure_code=role_secure_code,
            org_secure_code=org_secure_code,
            is_deleted=False
        ).all()

        guarded_menus = []
        for mrr in menu_role_reqs:
            menu = MenuItem.query.filter_by(
                secure_code=mrr.menu_secure_code,
                is_deleted=False
            ).first()
            if menu:
                guarded_menus.append({
                    'secure_code': menu.secure_code,
                    'code': menu.code,
                    'title': menu.title,
                    'link_target': menu.link_target,
                    'required_permission': menu.required_permission,
                })

        # 此角色持有的 RBAC 權限 (RolePermission)
        role_perms = RolePermission.query.filter_by(
            role_secure_code=role_secure_code,
            is_deleted=False,
            is_active=True
        ).all()

        rbac_permissions = []
        for rp in role_perms:
            perm = rp.permission
            if perm:
                rbac_permissions.append({
                    'secure_code': rp.secure_code,
                    'permission_secure_code': perm.secure_code,
                    'permission_code': perm.code,
                    'permission_name': perm.name,
                    'permission_level': perm.permission_level,
                    'has_conditions': rp.has_conditions,
                    'is_active': rp.is_active,
                })

        # 持有此角色的用戶數（限定企業）
        user_count_query = db.session.query(
            func.count(UserRoleAssignment.id)
        ).join(
            User, User.secure_code == UserRoleAssignment.user_secure_code
        ).filter(
            UserRoleAssignment.role_secure_code == role_secure_code,
            UserRoleAssignment.is_deleted == False,
            User.is_deleted == False,
            User.is_active == True
        )
        if not is_system_admin:
            user_count_query = user_count_query.filter(
                User.org_secure_code == org_secure_code
            )
        user_count = user_count_query.scalar() or 0

        # 角色繼承的權限
        inherited_permissions = []
        if role.inherits_from_secure_code:
            parent_perms = RolePermission.query.filter_by(
                role_secure_code=role.inherits_from_secure_code,
                is_deleted=False,
                is_active=True
            ).all()
            for rp in parent_perms:
                perm = rp.permission
                if perm:
                    inherited_permissions.append({
                        'permission_code': perm.code,
                        'permission_name': perm.name,
                        'permission_level': perm.permission_level,
                        'from_role': role.inherits_from_secure_code,
                    })

        return {
            'role': {
                'secure_code': role.secure_code,
                'code': role.code,
                'name': role.name,
                'role_level': role.role_level,
                'is_system_role': role.is_system_role,
                'inherits_from': role.inherits_from_secure_code,
                'org_secure_code': role.org_secure_code,
                'org_label': role_org_label,
            },
            'guarded_menus': guarded_menus,
            'rbac_permissions': rbac_permissions,
            'inherited_permissions': inherited_permissions,
            'user_count': user_count,
        }

    # ==================================================================
    # 功能視角
    # ==================================================================

    @classmethod
    def get_menu_view(
        cls, menu_secure_code: str, org_secure_code: str,
        is_system_admin: bool = False
    ) -> Dict[str, Any]:
        """
        功能視角：選定選單，看到完整的權限授權狀態

        ORG_ADMIN 只能查看授權給 ORG_ADMIN/EMPLOYEE/EXTERNAL 的選單
        """
        menu = MenuItem.query.filter_by(
            secure_code=menu_secure_code,
            is_deleted=False
        ).first()
        if not menu:
            return {'error': '選單不存在'}

        # ORG_ADMIN 存取控制: 檢查此選單是否對 ORG_ADMIN 可見
        if not is_system_admin:
            visible_perms = MenuPermission.query.filter(
                MenuPermission.menu_secure_code == menu_secure_code,
                MenuPermission.user_type.in_(_ORG_VISIBLE_USER_TYPES),
                MenuPermission.is_deleted == False
            ).first()
            if not visible_perms:
                return {'error': '無權限存取此選單'}

        # user_type 矩陣 (MenuPermission)
        menu_perms = MenuPermission.query.filter_by(
            menu_secure_code=menu_secure_code,
            is_deleted=False
        ).all()
        user_types = {mp.user_type: True for mp in menu_perms}

        # 角色需求 (MenuRoleRequirement)
        role_reqs = MenuRoleRequirement.query.filter_by(
            menu_secure_code=menu_secure_code,
            org_secure_code=org_secure_code,
            is_deleted=False
        ).all()
        required_roles = []
        for rr in role_reqs:
            if rr.role and not rr.role.is_deleted:
                holder_count = db.session.query(
                    func.count(UserRoleAssignment.id)
                ).join(
                    User, User.secure_code == UserRoleAssignment.user_secure_code
                ).filter(
                    UserRoleAssignment.role_secure_code == rr.role_secure_code,
                    UserRoleAssignment.is_deleted == False,
                    User.is_deleted == False,
                    User.is_active == True,
                    User.org_secure_code == org_secure_code
                ).scalar() or 0

                required_roles.append({
                    'secure_code': rr.role.secure_code,
                    'code': rr.role.code,
                    'name': rr.role.name,
                    'holder_count': holder_count,
                })

        # required_permission
        rbac_info = None
        if menu.required_permission:
            perm = Permission.query.filter_by(
                code=menu.required_permission,
                is_deleted=False
            ).first()

            if perm:
                rps = RolePermission.query.filter_by(
                    permission_secure_code=perm.secure_code,
                    is_deleted=False,
                    is_active=True
                ).all()
                holding_roles = []
                for rp in rps:
                    if rp.role and not rp.role.is_deleted:
                        holding_roles.append({
                            'secure_code': rp.role.secure_code,
                            'code': rp.role.code,
                            'name': rp.role.name,
                            'org_secure_code': rp.role.org_secure_code,
                            'org_label': cls._get_org_label(rp.role.org_secure_code),
                        })

                rbac_info = {
                    'permission_code': perm.code,
                    'permission_name': perm.name,
                    'permission_level': perm.permission_level,
                    'holding_roles': holding_roles,
                }

        # 選單所屬企業
        menu_org_label = cls._get_org_label(menu.org_secure_code)

        return {
            'menu': {
                'secure_code': menu.secure_code,
                'code': menu.code,
                'title': menu.title,
                'link_target': menu.link_target,
                'required_permission': menu.required_permission,
                'is_active': menu.is_active,
                'parent_secure_code': menu.parent_secure_code,
                'org_secure_code': menu.org_secure_code,
                'org_label': menu_org_label,
            },
            'user_types': {
                'SYSTEM_ADMIN': user_types.get('SYSTEM_ADMIN', False),
                'ORG_ADMIN': user_types.get('ORG_ADMIN', False),
                'EMPLOYEE': user_types.get('EMPLOYEE', False),
                'EXTERNAL': user_types.get('EXTERNAL', False),
            },
            'required_roles': required_roles,
            'rbac_info': rbac_info,
        }

    # ==================================================================
    # 衝突偵測
    # ==================================================================

    @classmethod
    def detect_conflicts(
        cls, org_secure_code: str,
        is_system_admin: bool = False
    ) -> Dict[str, Any]:
        """
        偵測權限配置中的衝突與缺失

        ORG_ADMIN 只偵測與自己企業相關的衝突
        """
        conflicts = []

        # --- 類型 1: 有 MenuPermission 但缺 RBAC 權限 ---
        menus_with_rbac = MenuItem.query.filter(
            MenuItem.required_permission.isnot(None),
            MenuItem.required_permission != '',
            MenuItem.is_deleted == False,
            MenuItem.is_active == True
        ).all()

        for menu in menus_with_rbac:
            menu_perms = MenuPermission.query.filter_by(
                menu_secure_code=menu.secure_code,
                is_deleted=False
            ).all()

            if not menu_perms:
                continue

            user_types_granted = [mp.user_type for mp in menu_perms]

            # ORG_ADMIN: 只關心與自己相關的 user_types
            if not is_system_admin:
                relevant = [ut for ut in user_types_granted if ut in _ORG_VISIBLE_USER_TYPES]
                if not relevant:
                    continue
                user_types_granted = relevant

            perm = Permission.query.filter_by(
                code=menu.required_permission,
                is_deleted=False,
                is_active=True
            ).first()

            if not perm:
                conflicts.append({
                    'type': 'MISSING_PERMISSION_DEF',
                    'severity': 'error',
                    'menu_code': menu.code,
                    'menu_title': menu.title,
                    'menu_secure_code': menu.secure_code,
                    'message': f'選單 "{menu.title}" 要求權限 {menu.required_permission}，但該權限代碼不存在',
                })
                continue

            # ORG_ADMIN 天生持有所有非 SYSTEM 級權限，不需角色分配
            need_role_check = [
                ut for ut in user_types_granted
                if ut != 'ORG_ADMIN' or perm.permission_level == 'SYSTEM'
            ]

            if not need_role_check:
                continue

            holding_role_codes = db.session.query(
                RolePermission.role_secure_code
            ).filter_by(
                permission_secure_code=perm.secure_code,
                is_deleted=False,
                is_active=True
            ).all()
            holding_role_codes = {r[0] for r in holding_role_codes}

            if not holding_role_codes:
                conflicts.append({
                    'type': 'MENU_PERM_NO_RBAC',
                    'severity': 'warning',
                    'menu_code': menu.code,
                    'menu_title': menu.title,
                    'menu_secure_code': menu.secure_code,
                    'required_permission': menu.required_permission,
                    'user_types': need_role_check,
                    'message': f'選單 "{menu.title}" 授權給 {", ".join(need_role_check)}，'
                               f'但沒有任何角色持有權限 {menu.required_permission}',
                })

        # --- 類型 2: 有 MenuRoleRequirement 但該角色無人持有 ---
        role_reqs = MenuRoleRequirement.query.filter_by(
            org_secure_code=org_secure_code,
            is_deleted=False
        ).all()

        for rr in role_reqs:
            menu = MenuItem.query.filter_by(
                secure_code=rr.menu_secure_code,
                is_deleted=False
            ).first()
            if not menu:
                continue

            role = Role.query.filter_by(
                secure_code=rr.role_secure_code,
                is_deleted=False
            ).first()
            if not role:
                continue

            holder_count = db.session.query(
                func.count(UserRoleAssignment.id)
            ).join(
                User, User.secure_code == UserRoleAssignment.user_secure_code
            ).filter(
                UserRoleAssignment.role_secure_code == rr.role_secure_code,
                UserRoleAssignment.is_deleted == False,
                User.is_deleted == False,
                User.is_active == True,
                User.org_secure_code == org_secure_code
            ).scalar() or 0

            if holder_count == 0:
                conflicts.append({
                    'type': 'ROLE_REQ_NO_HOLDER',
                    'severity': 'warning',
                    'menu_code': menu.code,
                    'menu_title': menu.title,
                    'menu_secure_code': menu.secure_code,
                    'role_code': role.code,
                    'role_name': role.name,
                    'role_secure_code': role.secure_code,
                    'message': f'選單 "{menu.title}" 要求角色 "{role.name}"，'
                               f'但該企業無人持有此角色',
                })

        return {
            'conflicts': conflicts,
            'summary': {
                'total': len(conflicts),
                'errors': len([c for c in conflicts if c['severity'] == 'error']),
                'warnings': len([c for c in conflicts if c['severity'] == 'warning']),
            },
        }

    # ==================================================================
    # 角色 RBAC 權限管理
    # ==================================================================

    @classmethod
    def set_role_permissions(
        cls,
        role_secure_code: str,
        permission_secure_codes: List[str],
        org_secure_code: str,
        is_system_admin: bool = False,
        operator_user: Any = None
    ) -> Dict[str, Any]:
        """
        批量設定角色的 RBAC 權限（全量替換）

        安全限制：
        - ORG_ADMIN 只能操作自己企業的角色
        - ORG_ADMIN 不能授予 SYSTEM 級權限
        """
        # 驗證角色存取權
        role_query = Role.query.filter_by(
            secure_code=role_secure_code,
            is_deleted=False
        )
        if not is_system_admin:
            role_query = role_query.filter(Role.org_secure_code == org_secure_code)
        role = role_query.first()
        if not role:
            return {'error': '角色不存在或無權限操作'}

        # 驗證所有權限存在
        valid_perms = Permission.query.filter(
            Permission.secure_code.in_(permission_secure_codes),
            Permission.is_deleted == False,
            Permission.is_active == True
        ).all()
        valid_codes = {p.secure_code for p in valid_perms}
        invalid_codes = set(permission_secure_codes) - valid_codes
        if invalid_codes:
            return {'error': f'無效的權限代碼: {invalid_codes}'}

        # ORG_ADMIN 不能授予 SYSTEM 級權限
        if not is_system_admin:
            system_perms = [p for p in valid_perms if p.permission_level == 'SYSTEM']
            if system_perms:
                codes = [p.code for p in system_perms]
                return {'error': f'企業管理員不能授予系統級權限: {", ".join(codes)}'}

        try:
            existing = RolePermission.query.filter_by(
                role_secure_code=role_secure_code,
                is_deleted=False
            ).all()
            existing_perm_codes = {rp.permission_secure_code for rp in existing}

            to_add = valid_codes - existing_perm_codes
            to_remove = existing_perm_codes - valid_codes

            removed_count = 0
            for rp in existing:
                if rp.permission_secure_code in to_remove:
                    rp.is_deleted = True
                    removed_count += 1

            added_count = 0
            for perm_code in to_add:
                deleted_rp = RolePermission.query.filter_by(
                    role_secure_code=role_secure_code,
                    permission_secure_code=perm_code,
                    is_deleted=True
                ).first()

                if deleted_rp:
                    deleted_rp.is_deleted = False
                    deleted_rp.is_active = True
                else:
                    new_rp = RolePermission(
                        role_secure_code=role_secure_code,
                        permission_secure_code=perm_code,
                        is_active=True
                    )
                    db.session.add(new_rp)
                added_count += 1

            db.session.commit()

            logger.info(
                f"Role {role.code} permissions updated: "
                f"+{added_count} -{removed_count} by {getattr(operator_user, 'username', 'unknown')}"
            )

            return {
                'message': '權限更新成功',
                'added': added_count,
                'removed': removed_count,
                'total': len(valid_codes),
            }

        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to update role permissions: {e}")
            return {'error': f'更新失敗: {str(e)}'}

    # ==================================================================
    # 輔助查詢
    # ==================================================================

    @classmethod
    def get_all_roles(
        cls, org_secure_code: str,
        is_system_admin: bool = False,
        filter_org_code: str = ''
    ) -> List[Dict[str, Any]]:
        """
        取得角色列表

        SYSTEM_ADMIN + filter_org_code: 只看指定企業的角色
        SYSTEM_ADMIN 無 filter: 全部角色
        ORG_ADMIN: 只有自己企業的角色
        """
        query = Role.query.filter_by(
            is_deleted=False,
            is_active=True
        )
        if not is_system_admin:
            query = query.filter(Role.org_secure_code == org_secure_code)
        elif filter_org_code:
            query = query.filter(Role.org_secure_code == filter_org_code)

        roles = query.order_by(Role.sort_order).all()

        return [
            {
                'secure_code': r.secure_code,
                'code': r.code,
                'name': r.name,
                'role_level': r.role_level,
                'is_system_role': r.is_system_role,
                'org_secure_code': r.org_secure_code,
                'org_label': cls._get_org_label(r.org_secure_code),
            }
            for r in roles
        ]

    @classmethod
    def get_all_permissions(
        cls, is_system_admin: bool = False
    ) -> List[Dict[str, Any]]:
        """
        取得權限定義

        SYSTEM_ADMIN: 全部
        ORG_ADMIN: 非 SYSTEM 級
        """
        query = Permission.query.filter_by(
            is_deleted=False,
            is_active=True
        )
        if not is_system_admin:
            query = query.filter(Permission.permission_level != 'SYSTEM')

        perms = query.order_by(Permission.resource_type, Permission.action).all()

        return [
            {
                'secure_code': p.secure_code,
                'code': p.code,
                'name': p.name,
                'resource_type': p.resource_type,
                'action': p.action,
                'permission_level': p.permission_level,
            }
            for p in perms
        ]

    @classmethod
    def get_menu_tree_flat(
        cls, org_secure_code: str,
        is_system_admin: bool = False
    ) -> List[Dict[str, Any]]:
        """
        取得選單列表

        SYSTEM_ADMIN: 全部選單
        ORG_ADMIN: 只有授權給 ORG_ADMIN/EMPLOYEE/EXTERNAL 的選單
        """
        if is_system_admin:
            items = MenuItem.query.filter_by(
                is_deleted=False
            ).order_by(MenuItem.display_order).all()
        else:
            # 找出 ORG_ADMIN 可見的選單 secure_codes
            visible_codes = db.session.query(
                MenuPermission.menu_secure_code
            ).filter(
                MenuPermission.user_type.in_(_ORG_VISIBLE_USER_TYPES),
                MenuPermission.is_deleted == False
            ).distinct().all()
            visible_code_set = {r[0] for r in visible_codes}

            items = MenuItem.query.filter(
                MenuItem.is_deleted == False,
                MenuItem.secure_code.in_(visible_code_set)
            ).order_by(MenuItem.display_order).all()

        return [
            {
                'secure_code': m.secure_code,
                'code': m.code,
                'title': m.title,
                'parent_secure_code': m.parent_secure_code,
                'link_target': m.link_target,
                'icon': m.icon,
                'depth': m.depth,
                'is_active': m.is_active,
                'required_permission': m.required_permission,
                'org_secure_code': m.org_secure_code,
                'org_label': cls._get_org_label(m.org_secure_code),
            }
            for m in items
        ]

    # ==================================================================
    # 內部工具
    # ==================================================================

    @classmethod
    def _get_org_label(cls, org_secure_code: str) -> str:
        """取得企業顯示標籤"""
        if not org_secure_code:
            return '-'
        if org_secure_code == SYSTEM_ORG_CODE:
            return f'系統 ({SYSTEM_ORG_CODE})'
        from ..models import Organization
        org = Organization.query.filter_by(
            secure_code=org_secure_code,
            is_deleted=False
        ).first()
        if org:
            return org.display_name or org.name
        return org_secure_code

    # ==================================================================
    # RBAC 出廠預設值管理 (DB-based)
    # ==================================================================

    # --- 路徑常數（僅供 export_factory_sql 產出安裝用 SQL）---
    _PROJECT_ROOT = os.path.abspath(
        os.path.join(os.path.dirname(__file__), '..', '..', '..')
    )
    _DEFAULTS_JSON = os.path.join(
        _PROJECT_ROOT, 'backend', 'app', 'defaults', 'rbac_defaults.json'
    )

    @classmethod
    def _read_defaults_json(cls) -> Optional[Dict]:
        """讀取 rbac_defaults.json（fallback 用），不存在回傳 None"""
        if not os.path.isfile(cls._DEFAULTS_JSON):
            return None
        try:
            with open(cls._DEFAULTS_JSON, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return None

    @classmethod
    def _snapshot_system_roles(cls, org_secure_code: str) -> Dict[str, List[str]]:
        """
        快照指定企業的系統角色 RBAC 權限。

        Returns:
            { role_code: [perm_code, ...], ... }
        """
        roles = Role.query.filter_by(
            org_secure_code=org_secure_code,
            is_system_role=True,
            is_deleted=False,
            is_active=True
        ).all()

        snapshot = {}
        for role in roles:
            rps = RolePermission.query.filter_by(
                role_secure_code=role.secure_code,
                is_deleted=False,
                is_active=True
            ).all()
            perm_codes = []
            for rp in rps:
                if rp.permission and not rp.permission.is_deleted:
                    perm_codes.append(rp.permission.code)
            if perm_codes:
                snapshot[role.code] = sorted(perm_codes)
        return snapshot

    @classmethod
    def _load_defaults_from_db(cls) -> Optional[Dict[str, List[str]]]:
        """
        從 rbac_defaults 表載入預設值。

        Returns:
            {role_code: [perm_code, ...], ...}
            表為空回傳 None（觸發 fallback）
        """
        rows = RbacDefault.query.all()
        if not rows:
            return None

        snapshot = {}
        for row in rows:
            snapshot.setdefault(row.role_code, []).append(row.permission_code)
        # 排序
        for role_code in snapshot:
            snapshot[role_code] = sorted(snapshot[role_code])
        return snapshot

    @classmethod
    def save_factory_defaults(
        cls, org_secure_code: str, operator_username: str
    ) -> Dict[str, Any]:
        """
        設定目前組態成出廠值（系統管理員專用）。

        快照指定企業的系統角色 RBAC 權限，寫入 rbac_defaults 表（全量替換）。
        """
        try:
            snapshot = cls._snapshot_system_roles(org_secure_code)
            if not snapshot:
                return {'error': '該企業沒有系統角色或系統角色無權限配置'}

            # 清空 rbac_defaults 表，全量寫入
            RbacDefault.query.delete()

            now = datetime.utcnow()
            count = 0
            for role_code, perm_codes in snapshot.items():
                for perm_code in perm_codes:
                    row = RbacDefault(
                        role_code=role_code,
                        permission_code=perm_code,
                        saved_by=operator_username,
                        saved_at=now,
                    )
                    db.session.add(row)
                    count += 1

            db.session.commit()

            total_perms = sum(len(v) for v in snapshot.values())
            logger.info(
                f"RBAC factory defaults saved to DB: {len(snapshot)} roles, "
                f"{total_perms} permissions by {operator_username}"
            )

            return {
                'message': '出廠預設值已儲存',
                'roles_count': len(snapshot),
                'permissions_count': total_perms,
            }

        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to save factory defaults: {e}")
            return {'error': f'儲存失敗: {str(e)}'}

    @classmethod
    def export_factory_sql(cls) -> Dict[str, Any]:
        """
        從 rbac_defaults 表匯出安裝用 SQL（原廠專用）。

        生成冪等 SQL，只在角色完全沒有 role_permissions 時才插入，
        upgrade 不覆蓋用戶已儲存的設定。
        """
        snapshot = cls._load_defaults_from_db()
        if not snapshot:
            return {'error': 'rbac_defaults 表為空，請先儲存出廠預設值'}

        now_str = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
        lines = [
            '-- BeakPlatform RBAC Factory Defaults (install-only)',
            f'-- Generated: {now_str}',
            '-- ',
            '-- 安全機制: 只在 rbac_defaults 表為空時才插入',
            '-- (upgrade 不會覆蓋用戶已儲存的預設值)',
            '',
            '-- 條件: 僅當 rbac_defaults 表為空時執行',
            'DO $$',
            'BEGIN',
            '    IF NOT EXISTS (SELECT 1 FROM rbac_defaults LIMIT 1) THEN',
            '',
        ]

        for role_code, perm_codes in sorted(snapshot.items()):
            lines.append(
                f'        -- Role: {role_code} '
                f'({len(perm_codes)} permissions)'
            )
            for perm_code in perm_codes:
                sql = (
                    f"        INSERT INTO rbac_defaults "
                    f"(role_code, permission_code, saved_by, saved_at) "
                    f"VALUES ('{role_code}', '{perm_code}', "
                    f"'factory_install', NOW());"
                )
                lines.append(sql)
            lines.append('')

        lines.extend([
            '    END IF;',
            'END $$;',
        ])

        sql_content = '\n'.join(lines)

        sql_path = os.path.join(
            cls._PROJECT_ROOT, 'scripts', 'migrations',
            '060_seed_rbac_defaults.sql'
        )
        os.makedirs(os.path.dirname(sql_path), exist_ok=True)
        with open(sql_path, 'w', encoding='utf-8') as f:
            f.write(sql_content)

        total_perms = sum(len(v) for v in snapshot.values())
        logger.info(
            f"RBAC factory SQL exported: {len(snapshot)} roles, "
            f"{total_perms} permissions -> 060_seed_rbac_defaults.sql"
        )

        return {
            'message': '安裝用 SQL 已產出',
            'roles_count': len(snapshot),
            'permissions_count': total_perms,
            'sql_file': '060_seed_rbac_defaults.sql',
        }

    @classmethod
    def export_rbac(
        cls, org_secure_code: str, is_system_admin: bool
    ) -> Dict[str, Any]:
        """
        匯出 RBAC 權限（JSON 格式）。

        系統管理員: 匯出出廠預設值（rbac_defaults 表的內容）
        企業管理員: 匯出該企業所有角色的當前權限配置
        """
        if is_system_admin:
            # 系統級: 匯出出廠預設值（優先 DB，fallback JSON）
            snapshot = cls._load_defaults_from_db()
            if not snapshot:
                defaults = cls._read_defaults_json()
                if defaults:
                    snapshot = defaults.get('roles', {})
            if not snapshot:
                return {'error': '尚未設定出廠預設值，請先使用「設定目前組態成出廠值」'}

            return {
                'data': {
                    'version': '1.0',
                    'type': 'factory_defaults',
                    'exported_at': datetime.now(timezone.utc).isoformat(),
                    'source': 'system_factory_defaults',
                    'roles': snapshot,
                },
                'filename': 'rbac_factory_defaults.json',
            }
        else:
            # 企業級: 匯出當前企業所有角色的權限
            roles = Role.query.filter_by(
                org_secure_code=org_secure_code,
                is_deleted=False,
                is_active=True
            ).all()

            export_roles = {}
            for role in roles:
                rps = RolePermission.query.filter_by(
                    role_secure_code=role.secure_code,
                    is_deleted=False,
                    is_active=True
                ).all()
                perm_codes = []
                for rp in rps:
                    if rp.permission and not rp.permission.is_deleted:
                        perm_codes.append(rp.permission.code)
                export_roles[role.code] = sorted(perm_codes)

            org_label = cls._get_org_label(org_secure_code)
            return {
                'data': {
                    'version': '1.0',
                    'type': 'org_export',
                    'exported_at': datetime.now(timezone.utc).isoformat(),
                    'source': org_label,
                    'org_secure_code': org_secure_code,
                    'roles': export_roles,
                },
                'filename': f'rbac_export_{org_secure_code[:8]}.json',
            }

    @classmethod
    def import_rbac(
        cls, org_secure_code: str, is_system_admin: bool,
        import_data: Dict, operator_username: str
    ) -> Dict[str, Any]:
        """
        匯入 RBAC 權限。

        系統管理員: 匯入為新的出廠預設值（覆蓋 rbac_defaults.json + SQL）
        企業管理員: 匯入覆蓋該企業的角色權限
        """
        if not import_data or 'roles' not in import_data:
            return {'error': '匯入資料格式無效，缺少 roles 欄位'}

        roles_data = import_data['roles']
        if not isinstance(roles_data, dict):
            return {'error': '匯入資料格式無效，roles 必須是物件'}

        if is_system_admin:
            # 系統級: 覆蓋出廠預設值
            return cls._import_as_factory_defaults(roles_data, operator_username)
        else:
            # 企業級: 覆蓋企業設定
            return cls._import_to_org(
                org_secure_code, roles_data, operator_username
            )

    @classmethod
    def _import_as_factory_defaults(
        cls, roles_data: Dict, operator_username: str
    ) -> Dict[str, Any]:
        """匯入為出廠預設值（寫入 rbac_defaults 表）"""
        try:
            # 驗證權限代碼存在
            all_perm_codes = set()
            for codes in roles_data.values():
                if isinstance(codes, list):
                    all_perm_codes.update(codes)

            existing_perms = Permission.query.filter(
                Permission.code.in_(list(all_perm_codes)),
                Permission.is_deleted == False
            ).all()
            existing_codes = {p.code for p in existing_perms}
            missing = all_perm_codes - existing_codes
            if missing:
                return {'error': f'以下權限代碼不存在: {", ".join(sorted(missing))}'}

            # 寫入 DB（全量替換）
            RbacDefault.query.delete()
            now = datetime.utcnow()
            count = 0
            roles_count = 0

            for role_code, perm_codes in roles_data.items():
                if not isinstance(perm_codes, list):
                    continue
                roles_count += 1
                for perm_code in sorted(perm_codes):
                    if perm_code in existing_codes:
                        row = RbacDefault(
                            role_code=role_code,
                            permission_code=perm_code,
                            saved_by=operator_username,
                            saved_at=now,
                        )
                        db.session.add(row)
                        count += 1

            db.session.commit()

            logger.info(
                f"RBAC factory defaults imported to DB: "
                f"{roles_count} roles, {count} permissions "
                f"by {operator_username}"
            )

            return {
                'message': '出廠預設值已匯入',
                'roles_count': roles_count,
                'permissions_count': count,
            }

        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to import factory defaults: {e}")
            return {'error': f'匯入失敗: {str(e)}'}

    @classmethod
    def _import_to_org(
        cls, org_secure_code: str, roles_data: Dict,
        operator_username: str
    ) -> Dict[str, Any]:
        """匯入覆蓋企業的角色權限"""
        try:
            # 查詢企業角色
            roles = Role.query.filter_by(
                org_secure_code=org_secure_code,
                is_deleted=False
            ).all()
            role_by_code = {r.code: r for r in roles}

            # 查詢所有權限
            all_perm_codes = set()
            for codes in roles_data.values():
                if isinstance(codes, list):
                    all_perm_codes.update(codes)

            perms = Permission.query.filter(
                Permission.code.in_(list(all_perm_codes)),
                Permission.is_deleted == False,
                Permission.is_active == True
            ).all()
            perm_by_code = {p.code: p for p in perms}

            missing_perms = all_perm_codes - set(perm_by_code.keys())
            if missing_perms:
                return {
                    'error': f'以下權限代碼不存在: '
                             f'{", ".join(sorted(missing_perms))}'
                }

            total_added = 0
            total_removed = 0
            roles_updated = 0

            for role_code, perm_codes in roles_data.items():
                if not isinstance(perm_codes, list):
                    continue
                role = role_by_code.get(role_code)
                if not role:
                    continue

                # 取得現有權限
                existing_rps = RolePermission.query.filter_by(
                    role_secure_code=role.secure_code,
                    is_deleted=False
                ).all()
                existing_perm_scs = {
                    rp.permission_secure_code for rp in existing_rps
                }

                # 目標權限
                target_perm_scs = set()
                for pc in perm_codes:
                    p = perm_by_code.get(pc)
                    if p:
                        target_perm_scs.add(p.secure_code)

                to_add = target_perm_scs - existing_perm_scs
                to_remove = existing_perm_scs - target_perm_scs

                # 移除
                for rp in existing_rps:
                    if rp.permission_secure_code in to_remove:
                        rp.is_deleted = True
                        total_removed += 1

                # 新增
                for psc in to_add:
                    deleted_rp = RolePermission.query.filter_by(
                        role_secure_code=role.secure_code,
                        permission_secure_code=psc,
                        is_deleted=True
                    ).first()
                    if deleted_rp:
                        deleted_rp.is_deleted = False
                        deleted_rp.is_active = True
                    else:
                        new_rp = RolePermission(
                            role_secure_code=role.secure_code,
                            permission_secure_code=psc,
                            is_active=True
                        )
                        db.session.add(new_rp)
                    total_added += 1

                if to_add or to_remove:
                    roles_updated += 1

            db.session.commit()

            logger.info(
                f"RBAC imported to org {org_secure_code}: "
                f"+{total_added} -{total_removed} in {roles_updated} roles "
                f"by {operator_username}"
            )

            return {
                'message': 'RBAC 權限已匯入',
                'roles_updated': roles_updated,
                'added': total_added,
                'removed': total_removed,
            }

        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to import RBAC to org: {e}")
            return {'error': f'匯入失敗: {str(e)}'}

    @classmethod
    def restore_defaults(
        cls, org_secure_code: str, operator_username: str
    ) -> Dict[str, Any]:
        """
        恢復 RBAC 預設權限（企業管理員專用）。

        資料來源優先順序：
        1. rbac_defaults 表（系統管理員儲存的快照）
        2. rbac_defaults.json（fallback，向後相容）
        """
        # 優先從 DB 讀
        roles_data = cls._load_defaults_from_db()

        # fallback 到 JSON
        if not roles_data:
            defaults = cls._read_defaults_json()
            if defaults and 'roles' in defaults:
                roles_data = defaults['roles']

        if not roles_data:
            return {'error': '尚未設定出廠預設值，無法恢復'}

        # 只處理系統角色
        system_roles = Role.query.filter_by(
            org_secure_code=org_secure_code,
            is_system_role=True,
            is_deleted=False
        ).all()
        role_by_code = {r.code: r for r in system_roles}

        # 查詢所有需要的權限
        all_perm_codes = set()
        for codes in roles_data.values():
            all_perm_codes.update(codes)

        perms = Permission.query.filter(
            Permission.code.in_(list(all_perm_codes)),
            Permission.is_deleted == False,
            Permission.is_active == True
        ).all()
        perm_by_code = {p.code: p for p in perms}

        try:
            total_added = 0
            total_removed = 0
            roles_restored = 0

            for role_code, default_perm_codes in roles_data.items():
                role = role_by_code.get(role_code)
                if not role:
                    continue

                # 取得現有
                existing_rps = RolePermission.query.filter_by(
                    role_secure_code=role.secure_code,
                    is_deleted=False
                ).all()
                existing_perm_scs = {
                    rp.permission_secure_code for rp in existing_rps
                }

                # 目標
                target_perm_scs = set()
                for pc in default_perm_codes:
                    p = perm_by_code.get(pc)
                    if p:
                        target_perm_scs.add(p.secure_code)

                to_add = target_perm_scs - existing_perm_scs
                to_remove = existing_perm_scs - target_perm_scs

                for rp in existing_rps:
                    if rp.permission_secure_code in to_remove:
                        rp.is_deleted = True
                        total_removed += 1

                for psc in to_add:
                    deleted_rp = RolePermission.query.filter_by(
                        role_secure_code=role.secure_code,
                        permission_secure_code=psc,
                        is_deleted=True
                    ).first()
                    if deleted_rp:
                        deleted_rp.is_deleted = False
                        deleted_rp.is_active = True
                    else:
                        new_rp = RolePermission(
                            role_secure_code=role.secure_code,
                            permission_secure_code=psc,
                            is_active=True
                        )
                        db.session.add(new_rp)
                    total_added += 1

                if to_add or to_remove:
                    roles_restored += 1

            db.session.commit()

            logger.info(
                f"RBAC defaults restored for org {org_secure_code}: "
                f"+{total_added} -{total_removed} in {roles_restored} roles "
                f"by {operator_username}"
            )

            return {
                'message': 'RBAC 預設權限已恢復',
                'roles_restored': roles_restored,
                'added': total_added,
                'removed': total_removed,
            }

        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to restore defaults: {e}")
            return {'error': f'恢復失敗: {str(e)}'}
