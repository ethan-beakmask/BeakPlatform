"""
FormWorkflow Module - Variable Service
變數服務層

提供統一的變數存取介面，採用混合儲存模式（記憶體快取 + 資料庫持久化）。
"""
import logging
from typing import Any, Dict, Optional

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

    # 記憶體快取 {instance_id:var_name -> value}
    _cache: Dict[str, Any] = {}

    @staticmethod
    def _cache_key(instance_id: int, var_name: str, scope: str = 'GLOBAL', node_id: Optional[str] = None) -> str:
        """產生快取鍵"""
        if scope == 'LOCAL' and node_id:
            return f"{instance_id}:{node_id}:{var_name}"
        return f"{instance_id}:{var_name}"

    @staticmethod
    def get_global_var(instance_id: int, var_name: str, default: Any = None) -> Any:
        """
        取得全域變數

        Args:
            instance_id: 流程實例 ID
            var_name: 變數名稱
            default: 預設值

        Returns:
            變數值，若不存在則返回 default
        """
        cache_key = VariableService._cache_key(instance_id, var_name, 'GLOBAL')

        # 1. 先查快取
        if cache_key in VariableService._cache:
            return VariableService._cache[cache_key]

        # 2. 快取未命中，查資料庫
        var = FwWorkflowVariable.query.filter_by(
            workflow_instance_id=instance_id,
            var_name=var_name,
            scope='GLOBAL',
            node_id=None
        ).first()

        if var:
            # 3. 寫入快取
            VariableService._cache[cache_key] = var.var_value
            return var.var_value

        return default

    @staticmethod
    def set_global_var(instance_id: int, var_name: str, value: Any, org_code: str = None) -> FwWorkflowVariable:
        """
        設定全域變數

        Args:
            instance_id: 流程實例 ID
            var_name: 變數名稱
            value: 變數值
            org_code: 組織代碼（新增變數時需要）

        Returns:
            FwWorkflowVariable 物件
        """
        import secrets

        # 1. 查詢是否已存在
        var = FwWorkflowVariable.query.filter_by(
            workflow_instance_id=instance_id,
            var_name=var_name,
            scope='GLOBAL',
            node_id=None
        ).first()

        if var:
            # 更新現有變數
            var.var_value = value
        else:
            # 新增變數
            if not org_code:
                # 嘗試從 workflow_instance 取得 org_code
                from ..models import FwWorkflowInstance
                instance = FwWorkflowInstance.query.filter_by(id=instance_id).first()
                if instance:
                    org_code = instance.org_secure_code

            var = FwWorkflowVariable(
                secure_code=secrets.token_urlsafe(16),
                workflow_instance_id=instance_id,
                org_secure_code=org_code,
                var_name=var_name,
                var_value=value,
                scope='GLOBAL',
                node_id=None
            )
            db.session.add(var)

        # 2. 立即寫入資料庫（持久化）
        db.session.commit()

        # 3. 更新快取
        cache_key = VariableService._cache_key(instance_id, var_name, 'GLOBAL')
        VariableService._cache[cache_key] = value

        return var

    @staticmethod
    def get_local_var(instance_id: int, node_id: str, var_name: str, default: Any = None) -> Any:
        """
        取得節點級變數（LOCAL）

        Args:
            instance_id: 流程實例 ID
            node_id: 節點 ID
            var_name: 變數名稱
            default: 預設值

        Returns:
            變數值，若不存在則返回 default
        """
        cache_key = VariableService._cache_key(instance_id, var_name, 'LOCAL', node_id)

        # 1. 先查快取
        if cache_key in VariableService._cache:
            return VariableService._cache[cache_key]

        # 2. 快取未命中，查資料庫
        var = FwWorkflowVariable.query.filter_by(
            workflow_instance_id=instance_id,
            var_name=var_name,
            scope='LOCAL',
            node_id=node_id
        ).first()

        if var:
            # 3. 寫入快取
            VariableService._cache[cache_key] = var.var_value
            return var.var_value

        return default

    @staticmethod
    def set_local_var(instance_id: int, node_id: str, var_name: str, value: Any, org_code: str = None) -> FwWorkflowVariable:
        """
        設定節點級變數（LOCAL）

        Args:
            instance_id: 流程實例 ID
            node_id: 節點 ID
            var_name: 變數名稱
            value: 變數值
            org_code: 組織代碼（新增變數時需要）

        Returns:
            FwWorkflowVariable 物件
        """
        import secrets

        # 1. 查詢是否已存在
        var = FwWorkflowVariable.query.filter_by(
            workflow_instance_id=instance_id,
            var_name=var_name,
            scope='LOCAL',
            node_id=node_id
        ).first()

        if var:
            # 更新現有變數
            var.var_value = value
        else:
            # 新增變數
            if not org_code:
                # 嘗試從 workflow_instance 取得 org_code
                from ..models import FwWorkflowInstance
                instance = FwWorkflowInstance.query.filter_by(id=instance_id).first()
                if instance:
                    org_code = instance.org_secure_code

            var = FwWorkflowVariable(
                secure_code=secrets.token_urlsafe(16),
                workflow_instance_id=instance_id,
                org_secure_code=org_code,
                var_name=var_name,
                var_value=value,
                scope='LOCAL',
                node_id=node_id
            )
            db.session.add(var)

        # 2. 立即寫入資料庫（持久化）
        db.session.commit()

        # 3. 更新快取
        cache_key = VariableService._cache_key(instance_id, var_name, 'LOCAL', node_id)
        VariableService._cache[cache_key] = value

        return var

    @staticmethod
    def get_all_vars(instance_id: int, node_id: Optional[str] = None) -> Dict[str, Any]:
        """
        取得所有變數（GLOBAL + LOCAL）

        優先順序：LOCAL > GLOBAL（同名變數時，LOCAL 會覆蓋 GLOBAL）

        Args:
            instance_id: 流程實例 ID
            node_id: 節點 ID（若指定，則包含該節點的 LOCAL 變數）

        Returns:
            變數字典 {var_name: value}
        """
        result = {}

        # 1. 先取得所有 GLOBAL 變數
        global_vars = FwWorkflowVariable.query.filter_by(
            workflow_instance_id=instance_id,
            scope='GLOBAL',
            node_id=None
        ).all()

        for var in global_vars:
            result[var.var_name] = var.var_value
            # 更新快取
            cache_key = VariableService._cache_key(instance_id, var.var_name, 'GLOBAL')
            VariableService._cache[cache_key] = var.var_value

        # 2. 如果有指定 node_id，再取得 LOCAL 變數（會覆蓋同名 GLOBAL）
        if node_id:
            local_vars = FwWorkflowVariable.query.filter_by(
                workflow_instance_id=instance_id,
                scope='LOCAL',
                node_id=node_id
            ).all()

            for var in local_vars:
                result[var.var_name] = var.var_value
                # 更新快取
                cache_key = VariableService._cache_key(instance_id, var.var_name, 'LOCAL', node_id)
                VariableService._cache[cache_key] = var.var_value

        return result

    @staticmethod
    def delete_var(instance_id: int, var_name: str, scope: str = 'GLOBAL', node_id: Optional[str] = None) -> bool:
        """
        刪除變數

        Args:
            instance_id: 流程實例 ID
            var_name: 變數名稱
            scope: 作用域（GLOBAL/LOCAL）
            node_id: 節點 ID（LOCAL 變數時需要）

        Returns:
            是否刪除成功
        """
        query = FwWorkflowVariable.query.filter_by(
            workflow_instance_id=instance_id,
            var_name=var_name,
            scope=scope
        )

        if scope == 'LOCAL' and node_id:
            query = query.filter_by(node_id=node_id)
        else:
            query = query.filter_by(node_id=None)

        var = query.first()

        if var:
            # 從資料庫刪除
            db.session.delete(var)
            db.session.commit()

            # 從快取刪除
            cache_key = VariableService._cache_key(instance_id, var_name, scope, node_id)
            VariableService._cache.pop(cache_key, None)

            return True

        return False

    @staticmethod
    def clear_cache(instance_id: Optional[int] = None):
        """
        清除快取

        Args:
            instance_id: 流程實例 ID（若指定，只清除該實例的快取；否則清除所有快取）
        """
        if instance_id is None:
            # 清除所有快取
            VariableService._cache.clear()
        else:
            # 清除特定實例的快取
            keys_to_remove = [
                key for key in VariableService._cache.keys()
                if key.startswith(f"{instance_id}:")
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
