"""
Data CRUD Module - SiteMap Service
網站地圖服務

管理樹狀節點結構和節點准入控制。

准入模型 (grant-based permission):
  - 節點無任何 DcSiteMapPermission 記錄 → 開放給所有社群成員
  - 節點有 permission 記錄 → 白名單匹配（部門/社群/個人）

  grant_type: department / group / user
  include_children: 部門含子部門 / 社群含下層群組

舊 access_roles 仍保留在 DB 欄位，但准入檢查已改用 permission 記錄。
"""
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any, Set, Tuple

from app import db
from ..models.site_map_node import DcSiteMapNode
from ..models.site_map_permission import DcSiteMapPermission
from ..models.page_layout import DcPageLayout
from .sub_system_service import SubSystemService

logger = logging.getLogger(__name__)


class SiteMapService:
    """網站地圖服務"""

    # ==========================================================================
    # 查詢
    # ==========================================================================

    @staticmethod
    def has_site_map(sub_system_sc: str, org_sc: str) -> bool:
        """判斷子系統是否有 site map 節點"""
        count = DcSiteMapNode.query.filter(
            DcSiteMapNode.sub_system_secure_code == sub_system_sc,
            DcSiteMapNode.org_secure_code == org_sc,
            DcSiteMapNode.is_deleted == False,
        ).count()
        return count > 0

    @staticmethod
    def get_tree(sub_system_sc: str, org_sc: str) -> List[Dict[str, Any]]:
        """
        Admin 用: 取得完整巢狀樹 (含停用節點)

        Returns:
            [{ ...node_dict, children: [...] }]
        """
        nodes = DcSiteMapNode.query.filter(
            DcSiteMapNode.sub_system_secure_code == sub_system_sc,
            DcSiteMapNode.org_secure_code == org_sc,
            DcSiteMapNode.is_deleted == False,
        ).order_by(DcSiteMapNode.display_order).all()

        # 補充 page_layout 名稱
        layout_scs = {n.page_layout_secure_code for n in nodes if n.page_layout_secure_code}
        layout_names = {}
        if layout_scs:
            layouts = DcPageLayout.query.filter(
                DcPageLayout.secure_code.in_(layout_scs),
                DcPageLayout.is_deleted == False,
            ).all()
            layout_names = {l.secure_code: l.name for l in layouts}

        # 批量取得每個節點的 grant permission 數量
        node_scs = [n.secure_code for n in nodes]
        perm_counts = {}
        if node_scs:
            from sqlalchemy import func
            rows = db.session.query(
                DcSiteMapPermission.node_secure_code,
                func.count(DcSiteMapPermission.id),
            ).filter(
                DcSiteMapPermission.node_secure_code.in_(node_scs),
                DcSiteMapPermission.org_secure_code == org_sc,
                DcSiteMapPermission.grant_type.isnot(None),
                DcSiteMapPermission.is_deleted == False,
            ).group_by(DcSiteMapPermission.node_secure_code).all()
            perm_counts = {r[0]: r[1] for r in rows}

        # 組裝樹
        node_map = {}
        for n in nodes:
            d = n.to_dict()
            d['children'] = []
            d['page_layout_name'] = layout_names.get(n.page_layout_secure_code, '')
            d['_perm_count'] = perm_counts.get(n.secure_code, 0)
            node_map[n.secure_code] = d

        roots = []
        for n in nodes:
            d = node_map[n.secure_code]
            parent_sc = n.parent_secure_code
            if parent_sc and parent_sc in node_map:
                node_map[parent_sc]['children'].append(d)
            else:
                roots.append(d)

        return roots

    @staticmethod
    def get_user_tree(user, sub_system) -> Dict[str, Any]:
        """
        Portal 用: 取得用戶可見的樹 (grant-based permission 過濾)

        非成員 role_type='GUEST'。
        管理層角色不做過濾（全部可見）。

        Returns:
            { role_type, is_admin, tree: [...] }
            tree 為空表示無可見節點。
        """
        role_type = SubSystemService.get_user_role_type(user, sub_system)
        is_admin = False

        if role_type is None:
            role_type = 'GUEST'
        else:
            is_admin = SubSystemService.is_admin_role(role_type)

        nodes = DcSiteMapNode.query.filter(
            DcSiteMapNode.sub_system_secure_code == sub_system.secure_code,
            DcSiteMapNode.org_secure_code == sub_system.org_secure_code,
            DcSiteMapNode.is_deleted == False,
            DcSiteMapNode.is_active == True,
        ).order_by(DcSiteMapNode.display_order).all()

        if not nodes:
            return {'role_type': role_type, 'is_admin': is_admin, 'tree': []}

        # 管理層不做過濾
        if is_admin:
            visible_scs = {n.secure_code for n in nodes}
        else:
            visible_scs = SiteMapService._filter_by_grant_permissions(
                nodes, role_type, user, sub_system.org_secure_code
            )

        # 補充 page_layout 名稱
        layout_scs = {n.page_layout_secure_code for n in nodes if n.page_layout_secure_code}
        layout_names = {}
        if layout_scs:
            layouts = DcPageLayout.query.filter(
                DcPageLayout.secure_code.in_(layout_scs),
                DcPageLayout.is_deleted == False,
            ).all()
            layout_names = {l.secure_code: l.name for l in layouts}

        # 組裝樹 (僅可見節點)
        node_map = {}
        for n in nodes:
            if n.secure_code not in visible_scs:
                continue
            d = n.to_dict()
            d['children'] = []
            d['page_layout_name'] = layout_names.get(n.page_layout_secure_code, '')
            node_map[n.secure_code] = d

        roots = []
        for n in nodes:
            if n.secure_code not in visible_scs:
                continue
            d = node_map[n.secure_code]
            parent_sc = n.parent_secure_code
            if parent_sc and parent_sc in node_map:
                node_map[parent_sc]['children'].append(d)
            else:
                roots.append(d)

        return {'role_type': role_type, 'is_admin': is_admin, 'tree': roots}

    @staticmethod
    def get_node(node_sc: str, org_sc: str) -> Optional[DcSiteMapNode]:
        """取得單一節點"""
        return DcSiteMapNode.query.filter(
            DcSiteMapNode.secure_code == node_sc,
            DcSiteMapNode.org_secure_code == org_sc,
            DcSiteMapNode.is_deleted == False,
        ).first()

    @staticmethod
    def get_root_node(sub_system_sc: str, org_sc: str) -> Optional[DcSiteMapNode]:
        """取得 site map 的根節點 (welcome)"""
        return DcSiteMapNode.query.filter(
            DcSiteMapNode.sub_system_secure_code == sub_system_sc,
            DcSiteMapNode.org_secure_code == org_sc,
            DcSiteMapNode.parent_secure_code == None,
            DcSiteMapNode.is_deleted == False,
        ).first()

    @staticmethod
    def get_node_context(node: DcSiteMapNode, role_type: str) -> Dict[str, Any]:
        """
        取得節點的權限 context (CRUD + data_filters)

        暫時保留，Phase 3 將 CRUD 權限移至 widget 層級。
        """
        crud_overrides = node.crud_overrides or {}
        data_filters_map = node.data_filters or {}

        crud = crud_overrides.get(role_type)
        if crud is None:
            if SubSystemService.is_admin_role(role_type):
                crud = {'create': True, 'edit': True, 'delete': True}
            else:
                crud = {'create': False, 'edit': False, 'delete': False}

        data_filters = data_filters_map.get(role_type, {})

        return {
            'crud': crud,
            'data_filters': data_filters,
        }

    @staticmethod
    def check_page_access(role_type: Optional[str], node: DcSiteMapNode,
                          user=None) -> bool:
        """
        檢查用戶是否有權進入此頁面（grant-based permission）

        邏輯:
          1. 節點無任何 grant permission → 開放（所有社群成員可進入）
          2. 節點有 grant permission → 白名單匹配（部門/社群/個人）

        管理層角色（MANAGER/DEPUTY/PROXY1/PROXY2）在上層已跳過此檢查。

        Args:
            role_type: 用戶角色（None/'GUEST' 表示非成員）
            node: 目標節點
            user: 當前用戶物件（用於 grant-based 匹配）

        Returns:
            True = 允許, False = 拒絕
        """
        org_sc = node.org_secure_code

        # 取得此節點的 grant permission 記錄
        grant_perms = DcSiteMapPermission.query.filter(
            DcSiteMapPermission.node_secure_code == node.secure_code,
            DcSiteMapPermission.org_secure_code == org_sc,
            DcSiteMapPermission.grant_type.isnot(None),
            DcSiteMapPermission.is_deleted == False,
        ).all()

        # 無 grant permission → 開放給社群成員
        if not grant_perms:
            # 非成員（GUEST）無法進入
            effective_role = role_type or 'GUEST'
            return effective_role != 'GUEST'

        # 有 grant permission → 白名單匹配
        if not user:
            return False

        return SiteMapService._match_grant_permissions(user, grant_perms, org_sc)

    # ==========================================================================
    # 節點 CRUD
    # ==========================================================================

    @staticmethod
    def create_node(
        sub_system_sc: str,
        org_sc: str,
        name: str,
        node_type: str = 'page',
        parent_sc: str = None,
        icon: str = None,
        page_layout_sc: str = None,
        display_order: int = 0,
    ) -> DcSiteMapNode:
        """
        建立節點

        page 類型若未指定 page_layout_sc，自動建立空白 DcPageLayout。
        """
        if node_type != 'page':
            raise ValueError(f'Invalid node_type: {node_type}，僅支援 page')

        # 限制只能有一個根頁面，且名稱必須為 welcome
        if not parent_sc:
            existing_root = DcSiteMapNode.query.filter(
                DcSiteMapNode.sub_system_secure_code == sub_system_sc,
                DcSiteMapNode.org_secure_code == org_sc,
                DcSiteMapNode.parent_secure_code == None,
                DcSiteMapNode.is_deleted == False,
            ).first()
            if existing_root:
                raise ValueError(
                    'Site Map 只能有一個根頁面 (welcome)，'
                    '請將新網頁建立在根頁面下'
                )
            if name.lower() != 'welcome':
                raise ValueError(
                    '根頁面名稱必須為 welcome'
                )

        # page 類型自動建立空白佈局
        if node_type == 'page' and not page_layout_sc:
            layout = DcPageLayout(
                org_secure_code=org_sc,
                name=name,
                layout_json={'version': 2, 'widgets': []},
                status='draft',
            )
            db.session.add(layout)
            db.session.flush()
            page_layout_sc = layout.secure_code

        node = DcSiteMapNode(
            sub_system_secure_code=sub_system_sc,
            org_secure_code=org_sc,
            parent_secure_code=parent_sc,
            name=name,
            icon=icon,
            node_type=node_type,
            page_layout_secure_code=page_layout_sc,
            display_order=display_order,
        )
        db.session.add(node)
        db.session.flush()

        return node

    @staticmethod
    def update_node(
        node: DcSiteMapNode,
        **kwargs
    ) -> DcSiteMapNode:
        """更新節點屬性"""
        allowed = {
            'name', 'icon', 'page_layout_secure_code',
            'display_order', 'access_roles', 'redirect_to',
            'crud_overrides', 'data_filters', 'is_active',
        }
        for key, value in kwargs.items():
            if key in allowed:
                setattr(node, key, value)
        node.updated_at = datetime.utcnow()
        db.session.flush()
        return node

    @staticmethod
    def delete_node(node_sc: str, org_sc: str) -> int:
        """
        軟刪除節點 (含子節點遞迴)

        Returns:
            刪除的節點數
        """
        # 根節點不可刪除
        root_check = DcSiteMapNode.query.filter(
            DcSiteMapNode.secure_code == node_sc,
            DcSiteMapNode.org_secure_code == org_sc,
            DcSiteMapNode.parent_secure_code == None,
            DcSiteMapNode.is_deleted == False,
        ).first()
        if root_check:
            raise ValueError('根頁面 (welcome) 不可刪除')

        now = datetime.utcnow()
        count = 0

        def _delete_recursive(sc):
            nonlocal count
            node = DcSiteMapNode.query.filter(
                DcSiteMapNode.secure_code == sc,
                DcSiteMapNode.org_secure_code == org_sc,
                DcSiteMapNode.is_deleted == False,
            ).first()
            if not node:
                return

            # 先刪子節點
            children = DcSiteMapNode.query.filter(
                DcSiteMapNode.parent_secure_code == sc,
                DcSiteMapNode.org_secure_code == org_sc,
                DcSiteMapNode.is_deleted == False,
            ).all()
            for child in children:
                _delete_recursive(child.secure_code)

            node.is_deleted = True
            node.deleted_at = now
            node.updated_at = now
            count += 1

            # 刪除節點的權限記錄
            perms = DcSiteMapPermission.query.filter(
                DcSiteMapPermission.node_secure_code == sc,
                DcSiteMapPermission.org_secure_code == org_sc,
                DcSiteMapPermission.is_deleted == False,
            ).all()
            for perm in perms:
                perm.is_deleted = True
                perm.deleted_at = now

        _delete_recursive(node_sc)
        db.session.flush()
        return count

    @staticmethod
    def reorder_nodes(
        nodes_order: List[Dict[str, Any]],
        org_sc: str
    ) -> int:
        """
        批量更新 parent + display_order (拖曳後)

        Args:
            nodes_order: [{ secure_code, parent_secure_code, display_order }]

        Returns:
            更新的節點數
        """
        now = datetime.utcnow()
        count = 0
        for item in nodes_order:
            node = DcSiteMapNode.query.filter(
                DcSiteMapNode.secure_code == item['secure_code'],
                DcSiteMapNode.org_secure_code == org_sc,
                DcSiteMapNode.is_deleted == False,
            ).first()
            if not node:
                continue
            node.parent_secure_code = item.get('parent_secure_code') or None
            node.display_order = item.get('display_order', 0)
            node.updated_at = now
            count += 1
        db.session.flush()
        return count

    # ==========================================================================
    # 權限管理
    # ==========================================================================

    @staticmethod
    def get_node_permissions(
        node_sc: str, org_sc: str
    ) -> List[Dict[str, Any]]:
        """取得節點的權限列表 (含 target 名稱解析)"""
        from app.services.module_access_service import ModuleAccessService

        perms = DcSiteMapPermission.query.filter(
            DcSiteMapPermission.node_secure_code == node_sc,
            DcSiteMapPermission.org_secure_code == org_sc,
            DcSiteMapPermission.is_deleted == False,
        ).order_by(
            DcSiteMapPermission.target_type,
            DcSiteMapPermission.created_at,
        ).all()

        result = []
        for p in perms:
            item = p.to_dict()
            item['target_name'] = ModuleAccessService._resolve_target_name(
                p.target_type, p.target_secure_code
            )
            result.append(item)
        return result

    @staticmethod
    def add_permission(
        node_sc: str,
        org_sc: str,
        target_type: str,
        target_sc: str,
    ) -> Optional[DcSiteMapPermission]:
        """
        新增節點權限

        Returns:
            DcSiteMapPermission 或 None (重複)
        """
        valid_types = ('ROLE', 'DEPARTMENT', 'GROUP', 'ACCOUNT')
        if target_type not in valid_types:
            raise ValueError(f'Invalid target_type: {target_type}')

        existing = DcSiteMapPermission.query.filter(
            DcSiteMapPermission.node_secure_code == node_sc,
            DcSiteMapPermission.org_secure_code == org_sc,
            DcSiteMapPermission.target_type == target_type,
            DcSiteMapPermission.target_secure_code == target_sc,
            DcSiteMapPermission.is_deleted == False,
        ).first()
        if existing:
            return None

        perm = DcSiteMapPermission(
            node_secure_code=node_sc,
            org_secure_code=org_sc,
            target_type=target_type,
            target_secure_code=target_sc,
        )
        db.session.add(perm)
        db.session.flush()
        return perm

    @staticmethod
    def add_grant_permission(
        node_sc: str,
        org_sc: str,
        grant_type: str,
        grant_target: str,
        grant_target_name: str = '',
        include_children: bool = False,
    ) -> Optional[DcSiteMapPermission]:
        """
        新增 grant-based 准入權限

        Returns:
            DcSiteMapPermission 或 None (重複)
        """
        if grant_type not in ('department', 'group', 'user'):
            raise ValueError(f'Invalid grant_type: {grant_type}')

        # 檢查重複
        existing = DcSiteMapPermission.query.filter(
            DcSiteMapPermission.node_secure_code == node_sc,
            DcSiteMapPermission.org_secure_code == org_sc,
            DcSiteMapPermission.grant_type == grant_type,
            DcSiteMapPermission.grant_target == grant_target,
            DcSiteMapPermission.is_deleted == False,
        ).first()
        if existing:
            return None

        perm = DcSiteMapPermission(
            node_secure_code=node_sc,
            org_secure_code=org_sc,
            grant_type=grant_type,
            grant_target=grant_target,
            grant_target_name=grant_target_name,
            include_children=include_children,
        )
        db.session.add(perm)
        db.session.flush()
        return perm

    @staticmethod
    def get_grant_permissions(
        node_sc: str, org_sc: str
    ) -> List[Dict[str, Any]]:
        """取得節點的 grant-based 准入權限列表"""
        perms = DcSiteMapPermission.query.filter(
            DcSiteMapPermission.node_secure_code == node_sc,
            DcSiteMapPermission.org_secure_code == org_sc,
            DcSiteMapPermission.grant_type.isnot(None),
            DcSiteMapPermission.is_deleted == False,
        ).order_by(
            DcSiteMapPermission.grant_type,
            DcSiteMapPermission.created_at,
        ).all()
        return [p.to_dict() for p in perms]

    @staticmethod
    def remove_permission(perm_sc: str, org_sc: str) -> bool:
        """軟刪除權限記錄"""
        perm = DcSiteMapPermission.query.filter(
            DcSiteMapPermission.secure_code == perm_sc,
            DcSiteMapPermission.org_secure_code == org_sc,
            DcSiteMapPermission.is_deleted == False,
        ).first()
        if not perm:
            return False
        perm.is_deleted = True
        perm.deleted_at = datetime.utcnow()
        return True

    # ==========================================================================
    # SITEMENU Widget 用
    # ==========================================================================

    @staticmethod
    def get_menu_tree(user, sub_system) -> Dict[str, Any]:
        """
        SITEMENU Widget 用: 取得用戶可見的 menu tree

        過濾邏輯 (grant-based permission):
          - 節點無 grant permission 記錄 → 社群成員可見
          - 節點有 grant permission 記錄 → 白名單匹配（部門/社群/個人）
          - 管理層角色: 全部可見

        Returns:
            { role_type, is_admin, tree: [...] }
        """
        role_type = SubSystemService.get_user_role_type(user, sub_system)
        is_admin = False

        if role_type is None:
            role_type = 'GUEST'
        else:
            is_admin = SubSystemService.is_admin_role(role_type)

        org_sc = sub_system.org_secure_code
        ss_sc = sub_system.secure_code

        # 取得所有啟用節點
        nodes = DcSiteMapNode.query.filter(
            DcSiteMapNode.sub_system_secure_code == ss_sc,
            DcSiteMapNode.org_secure_code == org_sc,
            DcSiteMapNode.is_deleted == False,
            DcSiteMapNode.is_active == True,
        ).order_by(DcSiteMapNode.display_order).all()

        if not nodes:
            return {'role_type': role_type, 'is_admin': is_admin, 'tree': []}

        # 管理層: 全部可見
        if is_admin:
            visible_scs = {n.secure_code for n in nodes}
        else:
            visible_scs = SiteMapService._filter_by_grant_permissions(
                nodes, role_type, user, org_sc
            )

        # 補充 page_layout 名稱
        layout_scs = {n.page_layout_secure_code for n in nodes if n.page_layout_secure_code}
        layout_names = {}
        if layout_scs:
            layouts = DcPageLayout.query.filter(
                DcPageLayout.secure_code.in_(layout_scs),
                DcPageLayout.is_deleted == False,
            ).all()
            layout_names = {l.secure_code: l.name for l in layouts}

        # 組裝樹 (僅可見節點)
        node_map = {}
        for n in nodes:
            if n.secure_code not in visible_scs:
                continue
            d = n.to_dict()
            d['children'] = []
            d['page_layout_name'] = layout_names.get(n.page_layout_secure_code, '')
            node_map[n.secure_code] = d

        roots = []
        for n in nodes:
            if n.secure_code not in visible_scs:
                continue
            d = node_map[n.secure_code]
            parent_sc = n.parent_secure_code
            if parent_sc and parent_sc in node_map:
                node_map[parent_sc]['children'].append(d)
            else:
                roots.append(d)

        return {'role_type': role_type, 'is_admin': is_admin, 'tree': roots}

    # ==========================================================================
    # 內部方法
    # ==========================================================================

    @staticmethod
    def _filter_by_grant_permissions(
        nodes: List[DcSiteMapNode],
        role_type: str,
        user,
        org_sc: str,
    ) -> Set[str]:
        """
        grant-based permission 過濾演算法

        邏輯:
          - 節點無 grant permission → 社群成員可見（非成員不可見）
          - 節點有 grant permission → 匹配部門/社群/個人

        Args:
            nodes: 所有啟用節點
            role_type: 用戶角色（'GUEST' 表示非成員）
            user: 當前用戶物件
            org_sc: 企業 secure_code

        Returns:
            可見節點的 secure_code 集合
        """
        if not nodes:
            return set()

        node_scs = [n.secure_code for n in nodes]

        # 批量取得所有 grant permissions
        all_grant_perms = DcSiteMapPermission.query.filter(
            DcSiteMapPermission.node_secure_code.in_(node_scs),
            DcSiteMapPermission.org_secure_code == org_sc,
            DcSiteMapPermission.grant_type.isnot(None),
            DcSiteMapPermission.is_deleted == False,
        ).all()

        # 按 node_sc 分組
        perms_by_node = {}
        for p in all_grant_perms:
            perms_by_node.setdefault(p.node_secure_code, []).append(p)

        visible = set()
        is_member = (role_type != 'GUEST')

        for n in nodes:
            node_perms = perms_by_node.get(n.secure_code)

            if not node_perms:
                # 無 grant permission → 社群成員可見
                if is_member:
                    visible.add(n.secure_code)
                continue

            # 有 grant permission → 匹配
            if user and SiteMapService._match_grant_permissions(user, node_perms, org_sc):
                visible.add(n.secure_code)

        return visible

    @staticmethod
    def _match_grant_permissions(
        user, perms: List[DcSiteMapPermission], org_sc: str
    ) -> bool:
        """
        檢查用戶是否匹配任一 grant permission

        Args:
            user: 當前用戶
            perms: 節點的 grant permission 記錄
            org_sc: 企業 secure_code

        Returns:
            True = 匹配
        """
        from app.models.user_unit_membership import UserUnitMembership, MembershipType
        from app.models.organizational_unit import OrganizationalUnit

        user_sc = user.secure_code

        # 快取用戶的部門/群組身份
        memberships = UserUnitMembership.query.filter_by(
            user_secure_code=user_sc,
            is_deleted=False,
        ).filter(UserUnitMembership.is_active == True).all()

        user_dept_scs = set()
        user_group_scs = set()
        for m in memberships:
            if m.membership_type in (MembershipType.SOLID, MembershipType.DOTTED):
                user_dept_scs.add(m.unit_secure_code)
            elif m.membership_type == MembershipType.MEMBER:
                user_group_scs.add(m.unit_secure_code)

        # 建立祖先鏈（延遲，需要時才建）
        dept_ancestors = None
        group_ancestors = None

        for p in perms:
            if p.grant_type == 'user':
                if p.grant_target == user_sc:
                    return True

            elif p.grant_type == 'department':
                if not user_dept_scs:
                    continue
                if p.include_children:
                    if dept_ancestors is None:
                        dept_ancestors = set()
                        for dsc in user_dept_scs:
                            _build_ancestors(dsc, dept_ancestors, org_sc)
                    if p.grant_target in dept_ancestors:
                        return True
                else:
                    if p.grant_target in user_dept_scs:
                        return True

            elif p.grant_type == 'group':
                if not user_group_scs:
                    continue
                if p.include_children:
                    if group_ancestors is None:
                        group_ancestors = set()
                        for gsc in user_group_scs:
                            _build_ancestors(gsc, group_ancestors, org_sc)
                    if p.grant_target in group_ancestors:
                        return True
                else:
                    if p.grant_target == '__ORG_ROOT__':
                        # 虛擬企業根（不含下層）→ 有任一群組身份即匹配
                        return True
                    if p.grant_target in user_group_scs:
                        return True

        return False

    @staticmethod
    def _filter_by_access_roles(
        nodes: List[DcSiteMapNode],
        role_type: str,
    ) -> Set[str]:
        """
        (舊) access_roles 過濾演算法 -- 保留供向下相容

        檢查每個節點的 access_roles 是否允許此角色。
        """
        visible = set()

        for n in nodes:
            access_roles = n.access_roles or []

            if not access_roles:
                continue

            if 'GUEST' in access_roles:
                visible.add(n.secure_code)
            elif role_type != 'GUEST' and role_type in access_roles:
                visible.add(n.secure_code)

        return visible


def _build_ancestors(unit_sc: str, ancestors: Set[str], org_sc: str):
    """遞迴建立單位祖先鏈（含自身 + 虛擬企業根），用於 include_children 判斷"""
    from app.models.organizational_unit import OrganizationalUnit

    visited = set()
    current = unit_sc
    while current and current not in visited:
        visited.add(current)
        ancestors.add(current)
        unit = OrganizationalUnit.query.filter_by(
            secure_code=current,
            org_secure_code=org_sc,
            is_deleted=False,
        ).first()
        if not unit or not unit.parent_secure_code:
            break
        current = unit.parent_secure_code
    if current and current not in ancestors:
        ancestors.add(current)
    # 虛擬企業根 -- 讓 grant_target='__ORG_ROOT__' + include_children 匹配所有
    ancestors.add('__ORG_ROOT__')
