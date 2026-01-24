"""
FormWorkflow Module - Base Node Handler
節點處理器基礎類別

定義所有節點處理器的標準介面。
適配 BeakPlatform 模組化架構。
"""
import logging
import os
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class BaseNodeHandler(ABC):
    """節點處理器基礎類別"""

    def __init__(self, queue_item):
        """
        初始化處理器

        Args:
            queue_item: FwNodeExecutionQueue 實例
        """
        self.queue_item = queue_item
        self.node_config = queue_item.node_config or {}

        # 延遲載入關聯物件
        self._workflow_instance = None
        self._form_instance = None

    @property
    def workflow_instance(self):
        """取得工作流實例"""
        if self._workflow_instance is None:
            from ...models import FwWorkflowInstance
            self._workflow_instance = FwWorkflowInstance.query.filter_by(
                secure_code=self.queue_item.workflow_instance_secure_code
            ).first()
        return self._workflow_instance

    @property
    def form_instance(self):
        """取得表單實例"""
        if self._form_instance is None and self.workflow_instance:
            from ...models import FwFormInstance
            self._form_instance = FwFormInstance.query.filter_by(
                secure_code=self.workflow_instance.form_instance_secure_code
            ).first()
        return self._form_instance

    @abstractmethod
    def handle(self) -> Dict[str, Any]:
        """
        處理節點

        Returns:
            dict: 執行結果
                {
                    'status': 'success' | 'error' | 'waiting' | 'complete_workflow',
                    'message': str,
                    'data': dict (optional)
                }
        """
        pass

    def validate(self) -> bool:
        """
        驗證節點配置

        Returns:
            bool: 是否通過驗證
        """
        return True

    def get_config_value(self, key: str, default: Any = None) -> Any:
        """
        取得節點配置值

        Args:
            key: 配置鍵
            default: 預設值

        Returns:
            Any: 配置值
        """
        return self.node_config.get(key, default)

    def log_info(self, message: str, details: Dict = None):
        """記錄資訊日誌"""
        logger.info(f'[{self.queue_item.node_type}] {message}')
        if details:
            logger.info(f'  Details: {details}')

    def log_warning(self, message: str, details: Dict = None):
        """記錄警告日誌"""
        logger.warning(f'[{self.queue_item.node_type}] {message}')
        if details:
            logger.warning(f'  Details: {details}')

    def log_error(self, message: str, details: Dict = None):
        """記錄錯誤日誌"""
        logger.error(f'[{self.queue_item.node_type}] {message}')
        if details:
            logger.error(f'  Details: {details}')

    def get_form_field(self, field_name: str, default: Any = None) -> Any:
        """
        取得表單欄位值

        Args:
            field_name: 欄位名稱
            default: 預設值

        Returns:
            欄位值
        """
        if not self.form_instance or not self.form_instance.form_data:
            return default

        return self._get_nested_value(self.form_instance.form_data, field_name, default)

    def set_form_field(self, field_name: str, value: Any) -> bool:
        """
        設定表單欄位值

        Args:
            field_name: 欄位名稱
            value: 欄位值

        Returns:
            是否成功
        """
        if not self.form_instance:
            return False

        if not self.form_instance.form_data:
            self.form_instance.form_data = {}

        return self._set_nested_value(self.form_instance.form_data, field_name, value)

    def _get_nested_value(self, data: Dict, key: str, default: Any = None) -> Any:
        """
        取得巢狀資料中的值

        支援格式：
        - simple_key
        - nested.key
        - array[0]
        """
        if not data or not key:
            return default

        try:
            if '.' not in key and '[' not in key:
                return data.get(key, default)

            current = data
            parts = key.replace('[', '.').replace(']', '').split('.')

            for part in parts:
                if not part:
                    continue

                if isinstance(current, dict):
                    current = current.get(part)
                elif isinstance(current, list):
                    try:
                        idx = int(part)
                        current = current[idx] if 0 <= idx < len(current) else None
                    except (ValueError, IndexError):
                        return default
                else:
                    return default

                if current is None:
                    return default

            return current
        except Exception:
            return default

    def _set_nested_value(self, data: Dict, key: str, value: Any) -> bool:
        """
        設定巢狀資料中的值
        """
        if not data or not key:
            return False

        try:
            if '.' not in key and '[' not in key:
                data[key] = value
                return True

            parts = key.replace('[', '.').replace(']', '').split('.')
            parts = [p for p in parts if p]

            if len(parts) == 0:
                return False

            current = data
            for part in parts[:-1]:
                if isinstance(current, dict):
                    if part not in current:
                        current[part] = {}
                    current = current[part]
                elif isinstance(current, list):
                    try:
                        idx = int(part)
                        if 0 <= idx < len(current):
                            current = current[idx]
                        else:
                            return False
                    except (ValueError, IndexError):
                        return False
                else:
                    return False

            last_part = parts[-1]
            if isinstance(current, dict):
                current[last_part] = value
                return True
            elif isinstance(current, list):
                try:
                    idx = int(last_part)
                    if 0 <= idx < len(current):
                        current[idx] = value
                        return True
                except (ValueError, IndexError):
                    pass
            return False
        except Exception:
            return False

    def replace_variables(self, text: str) -> str:
        """
        替換文字中的變數

        支援格式：
        - ${var_name}
        - ${form.field_name}
        - ${workflow.instance_id}

        Args:
            text: 要處理的文字

        Returns:
            替換後的文字
        """
        import re

        if not text:
            return ''

        def replace_var(match):
            var_name = match.group(1)

            # workflow.* 變數
            if var_name.startswith('workflow.'):
                if var_name == 'workflow.instance_code':
                    return self.queue_item.workflow_instance_secure_code
                elif var_name == 'workflow.execution_code':
                    return self.workflow_instance.execution_code if self.workflow_instance else ''
                return ''

            # form.* 變數
            if var_name.startswith('form.'):
                field_name = var_name[5:]
                value = self.get_form_field(field_name)
                return str(value) if value is not None else ''

            # 一般變數
            return ''

        result = re.sub(r'\$\{([^}]+)\}', replace_var, text)
        return result
