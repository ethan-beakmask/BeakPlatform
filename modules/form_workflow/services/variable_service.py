"""
FormWorkflow Module - Variable Service
變數服務層

提供統一的變數存取介面，採用混合儲存模式（記憶體快取 + 資料庫持久化）。

Scope 定義 (見 dev-notes/VARIABLE_SYSTEM_SPEC.md):
- TREE: 跨流程共享，隔離鍵 = root_instance_code
- FLOW: 單一流程實例，隔離鍵 = workflow_instance_secure_code
- NODE: 節點級，節點完成後自動清除

讀取優先序: NODE > FLOW > TREE
"""
import logging
import secrets
from typing import Any, Dict, Optional

from sqlalchemy.exc import IntegrityError

from app import db
from ..models import FwWorkflowVariable

logger = logging.getLogger(__name__)


class VariableService:
    """
    變數服務

    採用混合儲存策略：
    - 記憶體快取：提升讀取效能（流程執行期間頻繁存取）
    - 資料庫持久化：支援長時間流程、系統重啟恢復、審計追蹤
    """

    # 記憶體快取 {scope_key:var_type:var_name -> value}
    _cache: Dict[str, Any] = {}

    @staticmethod
    def _cache_key(scope_key: str, var_name: str, var_type: str = 'FLOW') -> str:
        """產生快取鍵"""
        return f"{scope_key}:{var_type}:{var_name}"

    # ========================================
    # TREE scope（跨流程共享）
    # ========================================

    @staticmethod
    def get_tree_var(root_code: str, var_name: str, default: Any = None) -> Any:
        """
        取得跨流程變數（TREE scope）

        Args:
            root_code: 根流程實例 secure_code (root_instance_code)
            var_name: 變數名稱
            default: 預設值
        """
        if not root_code:
            return default

        cache_key = VariableService._cache_key(root_code, var_name, 'TREE')

        if cache_key in VariableService._cache:
            return VariableService._cache[cache_key]

        var = FwWorkflowVariable.query.filter_by(
            root_instance_code=root_code,
            var_name=var_name,
            var_type='TREE'
        ).first()

        if var:
            VariableService._cache[cache_key] = var.var_value
            return var.var_value

        return default

    @staticmethod
    def set_tree_var(root_code: str, var_name: str, value: Any,
                     instance_code: str = None, org_code: str = None,
                     source_node_id: str = None) -> FwWorkflowVariable:
        """
        設定跨流程變數（TREE scope）

        Args:
            root_code: 根流程實例 secure_code
            var_name: 變數名稱
            value: 變數值
            instance_code: 當前流程實例 code（用於 workflow_instance_secure_code 欄位）
            org_code: 組織代碼
            source_node_id: 來源節點 ID
        """
        return VariableService._set_var(
            instance_code=instance_code or root_code,
            var_name=var_name,
            value=value,
            var_type='TREE',
            org_code=org_code,
            source_node_id=source_node_id,
            root_code=root_code
        )

    # ========================================
    # FLOW scope（單一流程實例）
    # ========================================

    @staticmethod
    def get_flow_var(instance_code: str, var_name: str, default: Any = None) -> Any:
        """
        取得流程級變數（FLOW scope）

        Args:
            instance_code: 流程實例 secure_code
            var_name: 變數名稱
            default: 預設值
        """
        cache_key = VariableService._cache_key(instance_code, var_name, 'FLOW')

        if cache_key in VariableService._cache:
            return VariableService._cache[cache_key]

        var = FwWorkflowVariable.query.filter_by(
            workflow_instance_secure_code=instance_code,
            var_name=var_name,
            var_type='FLOW'
        ).first()

        if var:
            VariableService._cache[cache_key] = var.var_value
            return var.var_value

        return default

    @staticmethod
    def set_flow_var(instance_code: str, var_name: str, value: Any,
                     org_code: str = None, source_node_id: str = None) -> FwWorkflowVariable:
        """
        設定流程級變數（FLOW scope）

        Args:
            instance_code: 流程實例 secure_code
            var_name: 變數名稱
            value: 變數值
            org_code: 組織代碼
            source_node_id: 來源節點 ID
        """
        return VariableService._set_var(
            instance_code, var_name, value, 'FLOW', org_code, source_node_id
        )

    # ========================================
    # NODE scope（節點級）
    # ========================================

    @staticmethod
    def get_node_var(instance_code: str, var_name: str, default: Any = None) -> Any:
        """
        取得節點級變數（NODE scope）

        Args:
            instance_code: 流程實例 secure_code
            var_name: 變數名稱
            default: 預設值
        """
        cache_key = VariableService._cache_key(instance_code, var_name, 'NODE')

        if cache_key in VariableService._cache:
            return VariableService._cache[cache_key]

        var = FwWorkflowVariable.query.filter_by(
            workflow_instance_secure_code=instance_code,
            var_name=var_name,
            var_type='NODE'
        ).first()

        if var:
            VariableService._cache[cache_key] = var.var_value
            return var.var_value

        return default

    @staticmethod
    def set_node_var(instance_code: str, var_name: str, value: Any,
                     org_code: str = None, source_node_id: str = None) -> FwWorkflowVariable:
        """
        設定節點級變數（NODE scope）

        Args:
            instance_code: 流程實例 secure_code
            var_name: 變數名稱
            value: 變數值
            org_code: 組織代碼
            source_node_id: 來源節點 ID
        """
        return VariableService._set_var(
            instance_code, var_name, value, 'NODE', org_code, source_node_id
        )

    @staticmethod
    def cleanup_node_vars(instance_code: str, node_id: str) -> int:
        """
        清除指定節點的 NODE scope 變數（節點完成後呼叫）

        Args:
            instance_code: 流程實例 secure_code
            node_id: 節點 ID

        Returns:
            刪除的變數數量
        """
        vars_to_delete = FwWorkflowVariable.query.filter_by(
            workflow_instance_secure_code=instance_code,
            var_type='NODE',
            source_node_id=node_id
        ).all()

        count = len(vars_to_delete)
        for var in vars_to_delete:
            cache_key = VariableService._cache_key(instance_code, var.var_name, 'NODE')
            VariableService._cache.pop(cache_key, None)
            db.session.delete(var)

        if count > 0:
            db.session.commit()
            logger.info(f'[VariableService] 清除節點 {node_id} 的 {count} 個 NODE 變數')

        return count

    # ========================================
    # 統一讀取（優先序: NODE > FLOW > TREE）
    # ========================================

    @staticmethod
    def get_var(instance_code: str, root_code: str, var_name: str, default: Any = None) -> Any:
        """
        統一取得變數（優先序: NODE > FLOW > TREE）

        Args:
            instance_code: 流程實例 secure_code
            root_code: 根流程實例 secure_code（用於 TREE scope）
            var_name: 變數名稱
            default: 預設值
        """
        # 1. NODE
        value = VariableService.get_node_var(instance_code, var_name)
        if value is not None:
            return value

        # 2. FLOW
        value = VariableService.get_flow_var(instance_code, var_name)
        if value is not None:
            return value

        # 3. TREE
        if root_code:
            value = VariableService.get_tree_var(root_code, var_name)
            if value is not None:
                return value

        return default

    @staticmethod
    def get_all_vars(instance_code: str, root_code: str = None) -> Dict[str, Any]:
        """
        取得所有可見變數（TREE + FLOW + NODE）

        優先順序：NODE > FLOW > TREE（同名變數時，高優先覆蓋低優先）

        Args:
            instance_code: 流程實例 secure_code
            root_code: 根流程實例 secure_code（用於 TREE scope，可選）

        Returns:
            變數字典 {var_name: value}
        """
        result = {}

        # 1. 先取 TREE 變數（最低優先）
        if root_code:
            tree_vars = FwWorkflowVariable.query.filter_by(
                root_instance_code=root_code,
                var_type='TREE'
            ).all()
            for var in tree_vars:
                result[var.var_name] = var.var_value
                cache_key = VariableService._cache_key(root_code, var.var_name, 'TREE')
                VariableService._cache[cache_key] = var.var_value

        # 2. 再取 FLOW 變數（覆蓋同名 TREE）
        flow_vars = FwWorkflowVariable.query.filter_by(
            workflow_instance_secure_code=instance_code,
            var_type='FLOW'
        ).all()
        for var in flow_vars:
            result[var.var_name] = var.var_value
            cache_key = VariableService._cache_key(instance_code, var.var_name, 'FLOW')
            VariableService._cache[cache_key] = var.var_value

        # 3. 最後取 NODE 變數（覆蓋同名 FLOW/TREE）
        node_vars = FwWorkflowVariable.query.filter_by(
            workflow_instance_secure_code=instance_code,
            var_type='NODE'
        ).all()
        for var in node_vars:
            result[var.var_name] = var.var_value
            cache_key = VariableService._cache_key(instance_code, var.var_name, 'NODE')
            VariableService._cache[cache_key] = var.var_value

        return result

    # ========================================
    # 內部共用方法
    # ========================================

    @staticmethod
    def _set_var(instance_code: str, var_name: str, value: Any, var_type: str,
                 org_code: str = None, source_node_id: str = None,
                 root_code: str = None) -> FwWorkflowVariable:
        """
        內部共用：設定變數，處理並行寫入的 race condition

        採用 "先查後插，衝突時 rollback 改 update" 的模式。
        """
        type_label = FwWorkflowVariable.SCOPE_LABELS.get(var_type, var_type)

        # TREE scope 用 root_instance_code 查詢
        if var_type == 'TREE' and root_code:
            var = FwWorkflowVariable.query.filter_by(
                root_instance_code=root_code,
                var_name=var_name,
                var_type='TREE'
            ).first()
        else:
            var = FwWorkflowVariable.query.filter_by(
                workflow_instance_secure_code=instance_code,
                var_name=var_name,
                var_type=var_type
            ).first()

        if var:
            var.var_value = value
            if source_node_id:
                var.source_node_id = source_node_id
            db.session.commit()
        else:
            if not org_code:
                from ..models import FwWorkflowInstance
                instance = FwWorkflowInstance.query.filter_by(secure_code=instance_code).first()
                if instance:
                    org_code = instance.org_secure_code

            var = FwWorkflowVariable(
                secure_code=secrets.token_urlsafe(16),
                workflow_instance_secure_code=instance_code,
                root_instance_code=root_code,
                org_secure_code=org_code,
                var_name=var_name,
                var_value=value,
                var_type=var_type,
                source_node_id=source_node_id
            )
            db.session.add(var)

            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                if var_type == 'TREE' and root_code:
                    var = FwWorkflowVariable.query.filter_by(
                        root_instance_code=root_code,
                        var_name=var_name,
                        var_type='TREE'
                    ).first()
                else:
                    var = FwWorkflowVariable.query.filter_by(
                        workflow_instance_secure_code=instance_code,
                        var_name=var_name,
                        var_type=var_type
                    ).first()
                if var:
                    var.var_value = value
                    if source_node_id:
                        var.source_node_id = source_node_id
                    db.session.commit()
                else:
                    logger.error(f'[VariableService] 無法設定{type_label}變數 {var_name}：'
                                 f'IntegrityError 後仍找不到記錄')
                    return None

        # 更新快取
        scope_key = root_code if var_type == 'TREE' else instance_code
        cache_key = VariableService._cache_key(scope_key, var_name, var_type)
        VariableService._cache[cache_key] = value

        logger.info(f'[VariableService] 設定{type_label}變數: {var_name}={value} (instance={instance_code})')
        return var

    # ========================================
    # 舊 API 別名（deprecated，過渡期保留）
    # ========================================

    @staticmethod
    def get_global_var(instance_code: str, var_name: str, default: Any = None) -> Any:
        """deprecated: 用 get_flow_var"""
        return VariableService.get_flow_var(instance_code, var_name, default)

    @staticmethod
    def set_global_var(instance_code: str, var_name: str, value: Any,
                       org_code: str = None, source_node_id: str = None) -> FwWorkflowVariable:
        """deprecated: 用 set_flow_var"""
        return VariableService.set_flow_var(instance_code, var_name, value, org_code, source_node_id)

    @staticmethod
    def get_local_var(instance_code: str, var_name: str, default: Any = None) -> Any:
        """deprecated: 用 get_node_var"""
        return VariableService.get_node_var(instance_code, var_name, default)

    @staticmethod
    def set_local_var(instance_code: str, var_name: str, value: Any,
                      org_code: str = None, source_node_id: str = None) -> FwWorkflowVariable:
        """deprecated: 用 set_node_var"""
        return VariableService.set_node_var(instance_code, var_name, value, org_code, source_node_id)

    # ========================================
    # 快取管理
    # ========================================

    @staticmethod
    def delete_var(instance_code: str, var_name: str, var_type: str = 'FLOW') -> bool:
        """
        刪除變數

        Args:
            instance_code: 流程實例 secure_code
            var_name: 變數名稱
            var_type: 變數 scope（TREE/FLOW/NODE）
        """
        var = FwWorkflowVariable.query.filter_by(
            workflow_instance_secure_code=instance_code,
            var_name=var_name,
            var_type=var_type
        ).first()

        if var:
            db.session.delete(var)
            db.session.commit()

            cache_key = VariableService._cache_key(instance_code, var_name, var_type)
            VariableService._cache.pop(cache_key, None)

            return True

        return False

    @staticmethod
    def clear_cache(instance_code: Optional[str] = None):
        """
        清除快取

        Args:
            instance_code: 流程實例 secure_code（若指定，只清除該實例；否則清除全部）
        """
        if instance_code is None:
            VariableService._cache.clear()
        else:
            keys_to_remove = [
                key for key in VariableService._cache.keys()
                if key.startswith(f"{instance_code}:")
            ]
            for key in keys_to_remove:
                del VariableService._cache[key]

    @staticmethod
    def get_cache_stats() -> Dict[str, Any]:
        """取得快取統計資訊（用於除錯）"""
        return {
            'total_keys': len(VariableService._cache),
            'keys': list(VariableService._cache.keys())
        }
