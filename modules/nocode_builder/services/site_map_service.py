"""
Data CRUD Module - SiteMap Service
網站地圖服務

管理樹狀節點結構和節點准入控制。

准入模型 (access_roles):
  [] (空)     → NONE: 預設安全防呆，任何人都無法到此頁面
  ["GUEST"]   → 任何人都能到此頁面（含非成員）
  ["MANAGER", "MEMBER", ...] → 只有符合角色的成員才能到此頁面
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

        # 組裝樹
        node_map = {}
        for n in nodes:
            d = n.to_dict()
            d['children'] = []
            d['page_layout_name'] = layout_names.get(n.page_layout_secure_code, '')
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
        Portal 用: 取得用戶可見的樹 (access_roles 過濾)

        非成員 role_type='GUEST'，只能看到 access_roles 含 GUEST 的節點。
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
            visible_scs = SiteMapService._filter_by_access_roles(nodes, role_type)

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
    def check_page_access(role_type: Optional[str], node: DcSiteMapNode) -> bool:
        """
        檢查用戶是否有權進入此頁面

        Args:
            role_type: 用戶角色（None 表示非成員，視為 GUEST）
            node: 目標節點

        Returns:
            True = 允許, False = 拒絕（轉向 node.redirect_to）
        """
        access_roles = node.access_roles or []

        if not access_roles:
            return False  # NONE: 預設拒絕

        if 'GUEST' in access_roles:
            return True  # 任何人都能進入

        # 角色檢查: 非成員一律拒絕
        effective_role = role_type or 'GUEST'
        if effective_role == 'GUEST':
            return False

        return effective_role in access_roles

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
        if node_type not in ('folder', 'page'):
            raise ValueError(f'Invalid node_type: {node_type}')

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
    # 內部方法
    # ==========================================================================

    @staticmethod
    def _filter_by_access_roles(
        nodes: List[DcSiteMapNode],
        role_type: str,
    ) -> Set[str]:
        """
        access_roles 過濾演算法

        page 節點: 檢查 access_roles 是否允許此角色
        folder 節點: 子節點全不可見時，folder 也隱藏

        Args:
            nodes: 所有啟用節點
            role_type: 用戶角色（'GUEST' 表示非成員）

        Returns:
            可見節點的 secure_code 集合
        """
        visible = set()

        for n in nodes:
            access_roles = n.access_roles or []

            if n.node_type == 'folder':
                # folder 先暫時標記可見，後面再檢查子節點
                visible.add(n.secure_code)
                continue

            # page 節點: 檢查准入
            if not access_roles:
                continue  # NONE: 不可見

            if 'GUEST' in access_roles:
                visible.add(n.secure_code)
            elif role_type != 'GUEST' and role_type in access_roles:
                visible.add(n.secure_code)

        # folder: 若子節點全不可見則隱藏（反覆迭代直到穩定）
        changed = True
        while changed:
            changed = False
            for n in nodes:
                if n.secure_code not in visible:
                    continue
                if n.node_type != 'folder':
                    continue
                has_visible_child = any(
                    other.parent_secure_code == n.secure_code
                    and other.secure_code in visible
                    for other in nodes
                )
                if not has_visible_child:
                    visible.discard(n.secure_code)
                    changed = True

        return visible
