"""
FormWorkflow Module - Variable Service
變數服務層

提供統一的變數存取介面，採用混合儲存模式（記憶體快取 + 資料庫持久化）。
注意：此服務使用 workflow_instance_secure_code 作為關聯鍵。
"""
import logging
import secrets
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

    注意：使用 workflow_instance_secure_code（而非 workflow_instance_id）作為關聯鍵
    """

    # 記憶體快取 {instance_code:var_name -> value}
    _cache: Dict[str, Any] = {}

    @staticmethod
    def _cache_key(instance_code: str, var_name: str, var_type: str = 'GLOBAL') -> str:
        """產生快取鍵"""
        return f"{instance_code}:{var_type}:{var_name}"

    @staticmethod
    def get_global_var(instance_code: str, var_name: str, default: Any = None) -> Any:
        """
        取得全域變數

        Args:
            instance_code: 流程實例 secure_code
            var_name: 變數名稱
            default: 預設值

        Returns:
            變數值，若不存在則返回 default
        """
        cache_key = VariableService._cache_key(instance_code, var_name, 'GLOBAL')

        # 1. 先查快取
        if cache_key in VariableService._cache:
            return VariableService._cache[cache_key]

        # 2. 快取未命中，查資料庫
        var = FwWorkflowVariable.query.filter_by(
            workflow_instance_secure_code=instance_code,
            var_name=var_name,
            var_type='GLOBAL'
        ).first()

        if var:
            # 3. 寫入快取
            VariableService._cache[cache_key] = var.var_value
            return var.var_value

        return default

    @staticmethod
    def set_global_var(instance_code: str, var_name: str, value: Any, org_code: str = None, source_node_id: str = None) -> FwWorkflowVariable:
        """
        設定全域變數

        Args:
            instance_code: 流程實例 secure_code
            var_name: 變數名稱
            value: 變數值
            org_code: 組織代碼（新增變數時需要）
            source_node_id: 來源節點 ID

        Returns:
            FwWorkflowVariable 物件
        """
        # 1. 查詢是否已存在
        var = FwWorkflowVariable.query.filter_by(
            workflow_instance_secure_code=instance_code,
            var_name=var_name,
            var_type='GLOBAL'
        ).first()

        if var:
            # 更新現有變數
            var.var_value = value
            if source_node_id:
                var.source_node_id = source_node_id
        else:
            # 新增變數
            if not org_code:
                # 嘗試從 workflow_instance 取得 org_code
                from ..models import FwWorkflowInstance
                instance = FwWorkflowInstance.query.filter_by(secure_code=instance_code).first()
                if instance:
                    org_code = instance.org_secure_code

            var = FwWorkflowVariable(
                secure_code=secrets.token_urlsafe(16),
                workflow_instance_secure_code=instance_code,
                org_secure_code=org_code,
                var_name=var_name,
                var_value=value,
                var_type='GLOBAL',
                source_node_id=source_node_id
            )
            db.session.add(var)

        # 2. 立即寫入資料庫（持久化）
        db.session.commit()

        # 3. 更新快取
        cache_key = VariableService._cache_key(instance_code, var_name, 'GLOBAL')
        VariableService._cache[cache_key] = value

        logger.info(f'[VariableService] 設定全域變數: {var_name}={value} (instance={instance_code})')
        return var

    @staticmethod
    def get_local_var(instance_code: str, var_name: str, default: Any = None) -> Any:
        """
        取得節點級變數（LOCAL）

        Args:
            instance_code: 流程實例 secure_code
            var_name: 變數名稱
            default: 預設值

        Returns:
            變數值，若不存在則返回 default
        """
        cache_key = VariableService._cache_key(instance_code, var_name, 'LOCAL')

        # 1. 先查快取
        if cache_key in VariableService._cache:
            return VariableService._cache[cache_key]

        # 2. 快取未命中，查資料庫
        var = FwWorkflowVariable.query.filter_by(
            workflow_instance_secure_code=instance_code,
            var_name=var_name,
            var_type='LOCAL'
        ).first()

        if var:
            # 3. 寫入快取
            VariableService._cache[cache_key] = var.var_value
            return var.var_value

        return default

    @staticmethod
    def set_local_var(instance_code: str, var_name: str, value: Any, org_code: str = None, source_node_id: str = None) -> FwWorkflowVariable:
        """
        設定節點級變數（LOCAL）

        Args:
            instance_code: 流程實例 secure_code
            var_name: 變數名稱
            value: 變數值
            org_code: 組織代碼（新增變數時需要）
            source_node_id: 來源節點 ID

        Returns:
            FwWorkflowVariable 物件
        """
        # 1. 查詢是否已存在
        var = FwWorkflowVariable.query.filter_by(
            workflow_instance_secure_code=instance_code,
            var_name=var_name,
            var_type='LOCAL'
        ).first()

        if var:
            # 更新現有變數
            var.var_value = value
            if source_node_id:
                var.source_node_id = source_node_id
        else:
            # 新增變數
            if not org_code:
                # 嘗試從 workflow_instance 取得 org_code
                from ..models import FwWorkflowInstance
                instance = FwWorkflowInstance.query.filter_by(secure_code=instance_code).first()
                if instance:
                    org_code = instance.org_secure_code

            var = FwWorkflowVariable(
                secure_code=secrets.token_urlsafe(16),
                workflow_instance_secure_code=instance_code,
                org_secure_code=org_code,
                var_name=var_name,
                var_value=value,
                var_type='LOCAL',
                source_node_id=source_node_id
            )
            db.session.add(var)

        # 2. 立即寫入資料庫（持久化）
        db.session.commit()

        # 3. 更新快取
        cache_key = VariableService._cache_key(instance_code, var_name, 'LOCAL')
        VariableService._cache[cache_key] = value

        logger.info(f'[VariableService] 設定區域變數: {var_name}={value} (instance={instance_code})')
        return var

    @staticmethod
    def get_all_vars(instance_code: str) -> Dict[str, Any]:
        """
        取得所有變數（GLOBAL + LOCAL）

        優先順序：LOCAL > GLOBAL（同名變數時，LOCAL 會覆蓋 GLOBAL）

        Args:
            instance_code: 流程實例 secure_code

        Returns:
            變數字典 {var_name: value}
        """
        result = {}

        # 1. 先取得所有 GLOBAL 變數
        global_vars = FwWorkflowVariable.query.filter_by(
            workflow_instance_secure_code=instance_code,
            var_type='GLOBAL'
        ).all()

        for var in global_vars:
            result[var.var_name] = var.var_value
            # 更新快取
            cache_key = VariableService._cache_key(instance_code, var.var_name, 'GLOBAL')
            VariableService._cache[cache_key] = var.var_value

        # 2. 再取得 LOCAL 變數（會覆蓋同名 GLOBAL）
        local_vars = FwWorkflowVariable.query.filter_by(
            workflow_instance_secure_code=instance_code,
            var_type='LOCAL'
        ).all()

        for var in local_vars:
            result[var.var_name] = var.var_value
            # 更新快取
            cache_key = VariableService._cache_key(instance_code, var.var_name, 'LOCAL')
            VariableService._cache[cache_key] = var.var_value

        return result

    @staticmethod
    def delete_var(instance_code: str, var_name: str, var_type: str = 'GLOBAL') -> bool:
        """
        刪除變數

        Args:
            instance_code: 流程實例 secure_code
            var_name: 變數名稱
            var_type: 變數類型（GLOBAL/LOCAL）

        Returns:
            是否刪除成功
        """
        var = FwWorkflowVariable.query.filter_by(
            workflow_instance_secure_code=instance_code,
            var_name=var_name,
            var_type=var_type
        ).first()

        if var:
            # 從資料庫刪除
            db.session.delete(var)
            db.session.commit()

            # 從快取刪除
            cache_key = VariableService._cache_key(instance_code, var_name, var_type)
            VariableService._cache.pop(cache_key, None)

            return True

        return False

    @staticmethod
    def clear_cache(instance_code: Optional[str] = None):
        """
        清除快取

        Args:
            instance_code: 流程實例 secure_code（若指定，只清除該實例的快取；否則清除所有快取）
        """
        if instance_code is None:
            # 清除所有快取
            VariableService._cache.clear()
        else:
            # 清除特定實例的快取
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
