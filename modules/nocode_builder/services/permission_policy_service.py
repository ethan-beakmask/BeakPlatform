"""
NoCode Builder - Permission Policy Service
權限政策組服務

每個子系統可建立多個權限政策組，每組包含多條 grant-based 准入規則。
網站地圖節點透過 permission_mode 選擇 inherit/policy/custom。
"""
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any

from app import db
from ..models.permission_policy import DcPermissionPolicyGroup, DcPermissionPolicyRule
from ..models.site_map_node import DcSiteMapNode
from ..models.site_map_permission import DcSiteMapPermission

logger = logging.getLogger(__name__)


class PermissionPolicyService:
    """權限政策組 CRUD + 節點權限解析"""

    # ======================================================================
    # 政策組 CRUD
    # ======================================================================

    @staticmethod
    def list_groups(sub_system_sc: str, org_sc: str) -> List[Dict[str, Any]]:
        """列出子系統的所有權限政策組（含規則摘要）"""
        groups = DcPermissionPolicyGroup.query.filter(
            DcPermissionPolicyGroup.sub_system_secure_code == sub_system_sc,
            DcPermissionPolicyGroup.org_secure_code == org_sc,
            DcPermissionPolicyGroup.is_deleted == False,
        ).order_by(DcPermissionPolicyGroup.created_at).all()

        if not groups:
            return []

        group_scs = [g.secure_code for g in groups]

        # 批量取得所有規則
        rules = DcPermissionPolicyRule.query.filter(
            DcPermissionPolicyRule.policy_group_secure_code.in_(group_scs),
            DcPermissionPolicyRule.org_secure_code == org_sc,
            DcPermissionPolicyRule.is_deleted == False,
        ).all()

        rules_by_group = {}
        for r in rules:
            rules_by_group.setdefault(r.policy_group_secure_code, []).append(r.to_dict())

        # 統計使用此政策組的節點數
        usage_counts = {}
        if group_scs:
            from sqlalchemy import func
            rows = db.session.query(
                DcSiteMapNode.permission_policy_secure_code,
                func.count(DcSiteMapNode.id),
            ).filter(
                DcSiteMapNode.permission_policy_secure_code.in_(group_scs),
                DcSiteMapNode.permission_mode == 'policy',
                DcSiteMapNode.org_secure_code == org_sc,
                DcSiteMapNode.is_deleted == False,
            ).group_by(DcSiteMapNode.permission_policy_secure_code).all()
            usage_counts = {sc: cnt for sc, cnt in rows}

        result = []
        for g in groups:
            d = g.to_dict()
            d['rules'] = rules_by_group.get(g.secure_code, [])
            d['usage_count'] = usage_counts.get(g.secure_code, 0)
            result.append(d)

        return result

    @staticmethod
    def get_group(group_sc: str, org_sc: str) -> Optional[DcPermissionPolicyGroup]:
        """取得單一政策組"""
        return DcPermissionPolicyGroup.query.filter(
            DcPermissionPolicyGroup.secure_code == group_sc,
            DcPermissionPolicyGroup.org_secure_code == org_sc,
            DcPermissionPolicyGroup.is_deleted == False,
        ).first()

    @staticmethod
    def create_group(sub_system_sc: str, org_sc: str,
                     name: str, description: str = '') -> DcPermissionPolicyGroup:
        """建立政策組"""
        group = DcPermissionPolicyGroup(
            sub_system_secure_code=sub_system_sc,
            org_secure_code=org_sc,
            name=name.strip(),
            description=description.strip() if description else '',
        )
        db.session.add(group)
        db.session.flush()
        return group

    @staticmethod
    def update_group(group: DcPermissionPolicyGroup, **kwargs) -> DcPermissionPolicyGroup:
        """更新政策組"""
        for field in ('name', 'description'):
            if field in kwargs:
                val = kwargs[field]
                if field == 'name':
                    val = val.strip()
                setattr(group, field, val)
        group.updated_at = datetime.utcnow()
        return group

    @staticmethod
    def delete_group(group: DcPermissionPolicyGroup) -> Dict[str, Any]:
        """
        刪除政策組

        會將引用此政策組的節點 permission_mode 改為 NULL（禁止狀態）。
        """
        now = datetime.utcnow()
        org_sc = group.org_secure_code
        group_sc = group.secure_code

        # 軟刪除政策組
        group.is_deleted = True
        group.deleted_at = now

        # 軟刪除關聯規則
        DcPermissionPolicyRule.query.filter(
            DcPermissionPolicyRule.policy_group_secure_code == group_sc,
            DcPermissionPolicyRule.org_secure_code == org_sc,
            DcPermissionPolicyRule.is_deleted == False,
        ).update({
            DcPermissionPolicyRule.is_deleted: True,
            DcPermissionPolicyRule.deleted_at: now,
        }, synchronize_session=False)

        # 將引用此政策組的節點重設為 NULL（禁止）
        affected = DcSiteMapNode.query.filter(
            DcSiteMapNode.permission_policy_secure_code == group_sc,
            DcSiteMapNode.permission_mode == 'policy',
            DcSiteMapNode.org_secure_code == org_sc,
            DcSiteMapNode.is_deleted == False,
        ).update({
            DcSiteMapNode.permission_mode: None,
            DcSiteMapNode.permission_policy_secure_code: None,
            DcSiteMapNode.updated_at: now,
        }, synchronize_session=False)

        return {'affected_nodes': affected}

    # ======================================================================
    # 規則 CRUD
    # ======================================================================

    @staticmethod
    def list_rules(group_sc: str, org_sc: str) -> List[Dict[str, Any]]:
        """列出政策組的所有規則"""
        rules = DcPermissionPolicyRule.query.filter(
            DcPermissionPolicyRule.policy_group_secure_code == group_sc,
            DcPermissionPolicyRule.org_secure_code == org_sc,
            DcPermissionPolicyRule.is_deleted == False,
        ).order_by(DcPermissionPolicyRule.created_at).all()
        return [r.to_dict() for r in rules]

    @staticmethod
    def add_rule(group_sc: str, org_sc: str,
                 grant_type: str, grant_target: str,
                 grant_target_name: str = '',
                 include_children: bool = False) -> DcPermissionPolicyRule:
        """新增規則到政策組"""
        if grant_type not in ('department', 'group', 'user'):
            raise ValueError(f'Invalid grant_type: {grant_type}')

        rule = DcPermissionPolicyRule(
            policy_group_secure_code=group_sc,
            org_secure_code=org_sc,
            grant_type=grant_type,
            grant_target=grant_target,
            grant_target_name=grant_target_name,
            include_children=include_children,
        )
        db.session.add(rule)
        db.session.flush()
        return rule

    @staticmethod
    def delete_rule(rule_sc: str, org_sc: str) -> bool:
        """刪除單一規則"""
        rule = DcPermissionPolicyRule.query.filter(
            DcPermissionPolicyRule.secure_code == rule_sc,
            DcPermissionPolicyRule.org_secure_code == org_sc,
            DcPermissionPolicyRule.is_deleted == False,
        ).first()
        if not rule:
            return False
        rule.is_deleted = True
        rule.deleted_at = datetime.utcnow()
        return True

    # ======================================================================
    # 節點權限解析
    # ======================================================================

    @staticmethod
    def resolve_node_permissions(node: DcSiteMapNode, org_sc: str) -> List:
        """
        解析節點的有效准入規則

        根據 permission_mode 回傳對應的 DcSiteMapPermission 或
        DcPermissionPolicyRule 記錄（統一轉為 dict 格式）。

        Returns:
            grant permission list (格式與 DcSiteMapPermission 相容)
            空 list = 無規則（根據 mode 決定語義）
        """
        mode = node.permission_mode

        if mode == 'custom':
            # 沿用自訂的 DcSiteMapPermission
            perms = DcSiteMapPermission.query.filter(
                DcSiteMapPermission.node_secure_code == node.secure_code,
                DcSiteMapPermission.org_secure_code == org_sc,
                DcSiteMapPermission.grant_type.isnot(None),
                DcSiteMapPermission.is_deleted == False,
            ).all()
            return perms

        if mode == 'policy':
            policy_sc = node.permission_policy_secure_code
            if not policy_sc:
                return []
            # 從政策組取規則
            rules = DcPermissionPolicyRule.query.filter(
                DcPermissionPolicyRule.policy_group_secure_code == policy_sc,
                DcPermissionPolicyRule.org_secure_code == org_sc,
                DcPermissionPolicyRule.is_deleted == False,
            ).all()
            return rules

        if mode == 'inherit':
            # 向上找父節點
            parent_sc = node.parent_secure_code
            if not parent_sc:
                # 根節點的 inherit = 無規則（開放給社群成員）
                return []
            parent = DcSiteMapNode.query.filter(
                DcSiteMapNode.secure_code == parent_sc,
                DcSiteMapNode.org_secure_code == org_sc,
                DcSiteMapNode.is_deleted == False,
            ).first()
            if not parent:
                return []
            return PermissionPolicyService.resolve_node_permissions(parent, org_sc)

        # mode=NULL or unknown → 禁止（回傳特殊標記）
        return None

    @staticmethod
    def apply_down(node: DcSiteMapNode, org_sc: str,
                   skip_custom: bool = True) -> int:
        """
        向下套用：把此節點的權限推送給所有子節點

        Args:
            node: 來源節點
            org_sc: 企業 secure_code
            skip_custom: True=保留 custom 節點不覆蓋 (預設)

        Returns:
            受影響的節點數
        """
        source_mode = node.permission_mode
        source_policy_sc = node.permission_policy_secure_code

        # 取得所有子孫節點（遞迴）
        descendants = PermissionPolicyService._get_descendants(
            node.secure_code, node.sub_system_secure_code, org_sc
        )

        if not descendants:
            return 0

        now = datetime.utcnow()
        affected = 0

        for child in descendants:
            if skip_custom and child.permission_mode == 'custom':
                continue
            child.permission_mode = source_mode
            child.permission_policy_secure_code = source_policy_sc
            child.updated_at = now
            affected += 1

        return affected

    @staticmethod
    def _get_descendants(node_sc: str, sub_system_sc: str,
                         org_sc: str) -> List[DcSiteMapNode]:
        """遞迴取得所有子孫節點"""
        all_nodes = DcSiteMapNode.query.filter(
            DcSiteMapNode.sub_system_secure_code == sub_system_sc,
            DcSiteMapNode.org_secure_code == org_sc,
            DcSiteMapNode.is_deleted == False,
        ).all()

        children_map = {}
        for n in all_nodes:
            if n.parent_secure_code:
                children_map.setdefault(n.parent_secure_code, []).append(n)

        result = []
        stack = list(children_map.get(node_sc, []))
        while stack:
            current = stack.pop()
            result.append(current)
            stack.extend(children_map.get(current.secure_code, []))

        return result
