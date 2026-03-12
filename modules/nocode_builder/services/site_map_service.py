"""
Data CRUD Module - SiteMap Service
網站地圖服務

管理樹狀節點結構和節點權限。
權限規則: 節點無任何權限記錄 = 所有人可見; 有記錄 = 白名單匹配。
"""
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any, Set, Tuple

from app import db
from app.models.associations import UserRoleAssignment
from app.models.user_unit_membership import UserUnitMembership, MembershipType
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
    def get_user_tree(user, sub_system) -> Optional[Dict[str, Any]]:
        """
        Portal 用: 取得用戶可見的樹 (權限過濾)

        Returns:
            { role_type, is_admin, tree: [...] } 或 None (非成員)
        """
        role_type = SubSystemService.get_user_role_type(user, sub_system)
        if role_type is None:
            return None

        is_admin = SubSystemService.is_admin_role(role_type)

        nodes = DcSiteMapNode.query.filter(
            DcSiteMapNode.sub_system_secure_code == sub_system.secure_code,
            DcSiteMapNode.org_secure_code == sub_system.org_secure_code,
            DcSiteMapNode.is_deleted == False,
            DcSiteMapNode.is_active == True,
        ).order_by(DcSiteMapNode.display_order).all()

        if not nodes:
            return {'role_type': role_type, 'is_admin': is_admin, 'tree': []}

        # Admin 不做權限過濾
        if is_admin:
            visible_scs = {n.secure_code for n in nodes}
        else:
            visible_scs = SiteMapService._filter_by_permissions(
                nodes, user, sub_system.org_secure_code
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
    def get_node_context(node: DcSiteMapNode, role_type: str) -> Dict[str, Any]:
        """
        取得節點的權限 context (CRUD + data_filters)

        類似 SubSystemService.get_page_context 但讀取節點自身的 overrides。
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
            'display_order', 'crud_overrides', 'data_filters', 'is_active',
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

    @staticmethod
    def check_node_access(user, node: DcSiteMapNode) -> bool:
        """檢查用戶是否有權限存取此節點"""
        perms = DcSiteMapPermission.query.filter(
            DcSiteMapPermission.node_secure_code == node.secure_code,
            DcSiteMapPermission.org_secure_code == node.org_secure_code,
            DcSiteMapPermission.is_deleted == False,
        ).all()

        if not perms:
            return True  # 無權限記錄 = 所有人可見

        user_ids = SiteMapService._get_user_identifiers(user)
        for p in perms:
            if (p.target_type, p.target_secure_code) in user_ids:
                return True
        return False

    # ==========================================================================
    # 內部方法
    # ==========================================================================

    @staticmethod
    def _get_user_identifiers(user) -> Set[Tuple[str, str]]:
        """
        取得使用者的所有身份標識 (target_type, target_secure_code) 集合

        復用 ModuleAccessService._get_user_identifiers 的邏輯模式。
        """
        identifiers = set()

        # ACCOUNT
        identifiers.add(('ACCOUNT', user.secure_code))

        # ROLE
        role_assignments = UserRoleAssignment.query.filter(
            UserRoleAssignment.user_secure_code == user.secure_code,
            UserRoleAssignment.is_deleted == False,
        ).all()
        for ra in role_assignments:
            if ra.is_valid:
                identifiers.add(('ROLE', ra.role_secure_code))

        # DEPARTMENT + GROUP (via UserUnitMembership)
        memberships = UserUnitMembership.query.filter(
            UserUnitMembership.user_secure_code == user.secure_code,
            UserUnitMembership.is_deleted == False,
        ).all()
        for m in memberships:
            if not m.is_active:
                continue
            if m.membership_type in (MembershipType.SOLID, MembershipType.DOTTED):
                identifiers.add(('DEPARTMENT', m.unit_secure_code))
            elif m.membership_type == MembershipType.MEMBER:
                identifiers.add(('GROUP', m.unit_secure_code))

        return identifiers

    @staticmethod
    def _filter_by_permissions(
        nodes: List[DcSiteMapNode],
        user,
        org_sc: str,
    ) -> Set[str]:
        """
        權限過濾演算法

        1. 一次查詢所有 node 的 permissions，按 node_secure_code 分組
        2. 每個 node: 無 perms = 可見，有 perms = 白名單匹配
        3. folder: 子節點全不可見時，folder 也隱藏

        Returns:
            可見節點的 secure_code 集合
        """
        node_scs = [n.secure_code for n in nodes]
        if not node_scs:
            return set()

        # 一次查詢所有權限
        all_perms = DcSiteMapPermission.query.filter(
            DcSiteMapPermission.node_secure_code.in_(node_scs),
            DcSiteMapPermission.org_secure_code == org_sc,
            DcSiteMapPermission.is_deleted == False,
        ).all()

        # 按 node 分組
        perm_by_node: Dict[str, List[DcSiteMapPermission]] = {}
        for p in all_perms:
            perm_by_node.setdefault(p.node_secure_code, []).append(p)

        user_ids = SiteMapService._get_user_identifiers(user)

        # 先判定 page 節點可見性
        visible = set()
        node_type_map = {n.secure_code: n.node_type for n in nodes}
        parent_map = {n.secure_code: n.parent_secure_code for n in nodes}

        for n in nodes:
            perms = perm_by_node.get(n.secure_code, [])
            if not perms:
                # 無權限記錄 = 可見
                visible.add(n.secure_code)
            else:
                # 白名單匹配
                for p in perms:
                    if (p.target_type, p.target_secure_code) in user_ids:
                        visible.add(n.secure_code)
                        break

        # folder: 若子節點全不可見則隱藏
        # 反覆迭代直到穩定
        changed = True
        while changed:
            changed = False
            for n in nodes:
                if n.secure_code not in visible:
                    continue
                if n.node_type != 'folder':
                    continue
                # 檢查此 folder 是否有任何可見子節點
                has_visible_child = False
                for other in nodes:
                    if other.parent_secure_code == n.secure_code and other.secure_code in visible:
                        has_visible_child = True
                        break
                if not has_visible_child:
                    visible.discard(n.secure_code)
                    changed = True

        return visible
