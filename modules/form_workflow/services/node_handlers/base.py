"""
FormWorkflow Module - Base Node Handler
節點處理器基礎類別

定義所有節點處理器的標準介面。
適配 BeakPlatform 模組化架構，包含 A6 所有功能。
"""
import logging
import os
import re
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

from app import db

logger = logging.getLogger(__name__)


class BaseNodeHandler(ABC):
    """節點處理器基礎類別"""

    # 新式變數分隔符
    DISPLAY_VAR_SEPARATOR = '::'

    def __init__(self, queue_item):
        """
        初始化處理器

        Args:
            queue_item: FwNodeExecutionQueue 實例
        """
        self.queue_item = queue_item
        self.node_config = queue_item.node_config or {}
        self._display_var_cache = None  # 新式變數映射表快取

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
            if self.workflow_instance.form_instance_secure_code:
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

        Raises:
            Exception: 處理失敗時拋出異常
        """
        pass

    def validate(self) -> bool:
        """
        驗證節點配置是否正確

        Returns:
            bool: 是否通過驗證

        Raises:
            ValueError: 驗證失敗時拋出異常
        """
        return True

    def report_running(self):
        """
        回報程式開始執行

        handler 在 handle() 開頭呼叫此方法，更新：
        - status = RUNNING
        - started_at = 現在時間（僅第一次）
        - process_id = 當前程序 PID
        - retry_count += 1（僅第一次）
        """
        if self.queue_item.status == 'RUNNING':
            # 已在執行中，不重複設定
            return

        now = datetime.utcnow()
        self.queue_item.status = 'RUNNING'
        self.queue_item.started_at = now
        self.queue_item.process_id = os.getpid()
        self.queue_item.retry_count = (self.queue_item.retry_count or 0) + 1

        db.session.commit()

        self.log_info('節點開始執行', {
            'node_id': self.queue_item.node_id,
            'process_id': self.queue_item.process_id,
            'retry_count': self.queue_item.retry_count
        })

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

    # ========================================
    # 日誌 API
    # ========================================
    def log_info(self, message: str, details: Dict = None):
        """記錄資訊日誌"""
        from ..workflow_log_service import WorkflowLogService
        WorkflowLogService.log(
            workflow_instance_id=self._get_workflow_instance_id(),
            node_queue_id=self.queue_item.id,
            node_id=self.queue_item.node_id,
            level='INFO',
            message=message,
            data=details
        )

    def log_warning(self, message: str, details: Dict = None):
        """記錄警告日誌"""
        from ..workflow_log_service import WorkflowLogService
        WorkflowLogService.log(
            workflow_instance_id=self._get_workflow_instance_id(),
            node_queue_id=self.queue_item.id,
            node_id=self.queue_item.node_id,
            level='WARNING',
            message=message,
            data=details
        )

    def log_error(self, message: str, details: Dict = None):
        """記錄錯誤日誌"""
        from ..workflow_log_service import WorkflowLogService
        WorkflowLogService.log(
            workflow_instance_id=self._get_workflow_instance_id(),
            node_queue_id=self.queue_item.id,
            node_id=self.queue_item.node_id,
            level='ERROR',
            message=message,
            data=details
        )

    def _get_workflow_instance_id(self) -> Optional[int]:
        """取得 workflow_instance_id (數字)"""
        if self.workflow_instance:
            return self.workflow_instance.id
        return None

    def _get_workflow_instance_code(self) -> Optional[str]:
        """取得 workflow_instance_secure_code (用於 VariableService)"""
        return self.queue_item.workflow_instance_secure_code

    # ========================================
    # 新版變數 API（推薦使用）
    # ========================================
    def get_var(self, var_name: str, default: Any = None) -> Any:
        """
        取得變數（優先 LOCAL，再找 GLOBAL）

        Args:
            var_name: 變數名稱
            default: 預設值

        Returns:
            變數值
        """
        from ..variable_service import VariableService

        instance_code = self._get_workflow_instance_code()
        if not instance_code:
            return default

        # 先嘗試 LOCAL
        value = VariableService.get_local_var(instance_code, var_name)
        if value is not None:
            return value

        # 再嘗試 GLOBAL
        return VariableService.get_global_var(instance_code, var_name, default)

    def set_global_var(self, var_name: str, value: Any):
        """
        設定全域變數

        Args:
            var_name: 變數名稱
            value: 變數值
        """
        from ..variable_service import VariableService

        instance_code = self._get_workflow_instance_code()
        if not instance_code:
            logger.warning(f"Cannot set global var: workflow_instance_code is None")
            return None

        return VariableService.set_global_var(
            instance_code,
            var_name,
            value,
            self.queue_item.org_secure_code,
            self.queue_item.node_id
        )

    def set_local_var(self, var_name: str, value: Any):
        """
        設定節點級變數

        Args:
            var_name: 變數名稱
            value: 變數值
        """
        from ..variable_service import VariableService

        instance_code = self._get_workflow_instance_code()
        if not instance_code:
            logger.warning(f"Cannot set local var: workflow_instance_code is None")
            return None

        return VariableService.set_local_var(
            instance_code,
            var_name,
            value,
            self.queue_item.org_secure_code,
            self.queue_item.node_id
        )

    def get_all_vars(self) -> Dict[str, Any]:
        """
        取得所有可見變數（GLOBAL + LOCAL）

        Returns:
            變數字典
        """
        from ..variable_service import VariableService

        instance_code = self._get_workflow_instance_code()
        if not instance_code:
            return {}

        return VariableService.get_all_vars(instance_code)

    # ========================================
    # 表單欄位存取 API
    # ========================================
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

        success = self._set_nested_value(self.form_instance.form_data, field_name, value)
        if success:
            db.session.commit()
        return success

    # ========================================
    # 統一變數替換 API
    # ========================================
    def replace_variables(self, text: str,
                          include_form: bool = True,
                          include_workflow: bool = True,
                          include_timestamp: bool = False,
                          include_node: bool = False) -> str:
        """
        通用變數替換方法

        支援的變數格式：
        - ${var_name} - 流程變數（總是支援）
        - ${form.field_name} - 表單欄位（include_form=True 時）
        - ${form.instance_id} - 表單實例 ID
        - ${form.serial_number} - 表單編號
        - ${form.display_name} - 表單模板名稱
        - ${workflow.instance_id} - 流程實例 ID（include_workflow=True 時）
        - ${workflow.name} - 流程模板名稱
        - ${workflow.execution_code} - 流程執行代碼
        - ${timestamp} - 完整時間戳記（include_timestamp=True 時）
        - ${timestamp.date} - 日期
        - ${timestamp.time} - 時間
        - ${node.display_name} - 節點顯示名稱（include_node=True 時）

        Args:
            text: 要處理的文字
            include_form: 是否支援 form.* 變數
            include_workflow: 是否支援 workflow.* 變數
            include_timestamp: 是否支援 timestamp* 變數
            include_node: 是否支援 node.* 變數

        Returns:
            替換後的文字
        """
        if not text:
            return ''

        all_vars = self.get_all_vars()
        now = datetime.utcnow()

        def replace_var(match):
            var_name = match.group(1)

            # workflow.* 變數
            if var_name.startswith('workflow.'):
                if not include_workflow:
                    return match.group(0)  # 不替換，保留原樣
                if var_name == 'workflow.instance_id':
                    return str(self._get_workflow_instance_id() or '')
                elif var_name == 'workflow.instance_code':
                    return self.queue_item.workflow_instance_secure_code or ''
                elif var_name == 'workflow.name':
                    if self.workflow_instance and hasattr(self.workflow_instance, 'workflow_template'):
                        template = self.workflow_instance.workflow_template
                        return template.name if template else ''
                    return ''
                elif var_name == 'workflow.execution_code':
                    if self.workflow_instance:
                        return getattr(self.workflow_instance, 'execution_code', '') or ''
                    return ''
                return ''

            # form.* 變數
            if var_name.startswith('form.'):
                if not include_form:
                    return match.group(0)  # 不替換，保留原樣
                if var_name == 'form.instance_id':
                    return str(self.form_instance.id) if self.form_instance else ''
                elif var_name == 'form.instance_code':
                    return self.form_instance.secure_code if self.form_instance else ''
                elif var_name == 'form.serial_number':
                    if self.form_instance:
                        return getattr(self.form_instance, 'serial_number', '') or ''
                    return ''
                elif var_name == 'form.display_name':
                    if self.form_instance and hasattr(self.form_instance, 'form_template'):
                        template = self.form_instance.form_template
                        return template.name if template else ''
                    return ''
                else:
                    # form.field_name - 支援巢狀欄位
                    field_name = var_name[5:]  # 移除 "form." 前綴
                    value = self.get_form_field(field_name)
                    return str(value) if value is not None else ''

            # timestamp* 變數
            if var_name.startswith('timestamp'):
                if not include_timestamp:
                    return match.group(0)  # 不替換，保留原樣
                if var_name == 'timestamp':
                    return now.strftime('%Y-%m-%d %H:%M:%S')
                elif var_name == 'timestamp.date':
                    return now.strftime('%Y-%m-%d')
                elif var_name == 'timestamp.time':
                    return now.strftime('%H:%M:%S')
                return ''

            # node.* 變數
            if var_name.startswith('node.'):
                if not include_node:
                    return match.group(0)  # 不替換，保留原樣
                if var_name == 'node.display_name':
                    return self.queue_item.node_name or ''
                return ''

            # 新式變數格式（表單名稱::欄位標籤）
            if self.DISPLAY_VAR_SEPARATOR in var_name:
                internal_var = self._resolve_display_variable(var_name)
                if internal_var:
                    value = all_vars.get(internal_var)
                    if value is not None:
                        return str(value)
                # 如果找不到對應的內部變數，繼續嘗試一般查找

            # 一般流程變數
            value = all_vars.get(var_name)
            return str(value) if value is not None else ''

        result = re.sub(r'\$\{([^}]+)\}', replace_var, text)
        return result

    def _resolve_display_variable(self, display_var: str) -> Optional[str]:
        """
        解析新式變數格式，返回對應的內部變數名稱

        新式變數格式：表單名稱::欄位標籤
        可能有衝突標記：表單名稱::欄位標籤(key)

        Args:
            display_var: 新式變數名稱，如 "流程記錄單::姓名"

        Returns:
            內部變數名稱，找不到則返回 None
        """
        if self.DISPLAY_VAR_SEPARATOR not in display_var:
            return None

        # 解析顯示變數：表單名稱::欄位標籤
        parts = display_var.split(self.DISPLAY_VAR_SEPARATOR)
        if len(parts) != 2:
            return None

        field_label_part = parts[1].strip()

        # 處理可能的 key 後綴：姓名(applicant_name) -> 姓名, applicant_name
        field_label = field_label_part
        explicit_key = None
        if '(' in field_label_part and field_label_part.endswith(')'):
            # 有明確指定 key
            idx = field_label_part.rfind('(')
            field_label = field_label_part[:idx]
            explicit_key = field_label_part[idx+1:-1]

        # 使用實際表單實例來解析
        if not self.form_instance:
            logger.warning(f"[DisplayVar] form_instance 為 None，無法解析 '{display_var}'")
            return None

        if not hasattr(self.form_instance, 'form_template') or not self.form_instance.form_template:
            logger.warning(f"[DisplayVar] form_template 為 None，無法解析 '{display_var}'")
            return None

        form_template = self.form_instance.form_template
        if not form_template.schema:
            logger.warning(f"[DisplayVar] schema 為 None，無法解析 '{display_var}'")
            return None

        # 從 schema 中尋找符合標籤的欄位
        def normalize(s):
            """正規化名稱：移除空格"""
            return s.replace(' ', '').replace('\u3000', '') if s else ''

        def find_field_by_label(components, target_label, target_key=None):
            """遞迴搜尋符合標籤的欄位"""
            for comp in (components or []):
                comp_key = comp.get('key', '')
                comp_label = comp.get('label', '')
                comp_type = comp.get('type', '')

                # 只處理輸入型元件
                if comp.get('input', False) and comp_type not in ('button', 'submit'):
                    # 如果有明確指定 key，優先匹配 key
                    if target_key and comp_key == target_key:
                        return comp_key
                    # 否則匹配標籤
                    if normalize(comp_label) == normalize(target_label):
                        return comp_key

                # 遞迴處理巢狀結構
                for nested_key in ('components', ):
                    if nested_key in comp:
                        result = find_field_by_label(comp[nested_key], target_label, target_key)
                        if result:
                            return result
                if 'columns' in comp:
                    for col in comp['columns']:
                        result = find_field_by_label(col.get('components', []), target_label, target_key)
                        if result:
                            return result
                if 'rows' in comp:
                    for row in comp['rows']:
                        for cell in row:
                            result = find_field_by_label(cell.get('components', []), target_label, target_key)
                            if result:
                                return result
                if 'tabs' in comp:
                    for tab in comp['tabs']:
                        result = find_field_by_label(tab.get('components', []), target_label, target_key)
                        if result:
                            return result

            return None

        # 查找欄位
        schema = form_template.schema
        field_key = find_field_by_label(schema.get('components', []), field_label, explicit_key)

        if field_key:
            # 建立內部變數名稱
            internal_var = f"{form_template.secure_code}_{field_key}"
            logger.info(f"[DisplayVar] 解析成功: '{display_var}' -> '{internal_var}' (透過標籤 '{field_label}')")
            return internal_var
        else:
            logger.warning(f"[DisplayVar] 解析失敗: '{display_var}' - 在表單 '{form_template.name}' 中找不到標籤 '{field_label}'")
            return None

    # ========================================
    # 工具方法
    # ========================================
    def _get_nested_value(self, data: Dict, key: str, default: Any = None) -> Any:
        """
        取得巢狀資料中的值

        支援格式：
        - simple_key
        - nested.key
        - array[0]
        - nested.array[0].field
        """
        if not data or not key:
            return default

        try:
            # 簡單鍵：直接取值
            if '.' not in key and '[' not in key:
                return data.get(key, default)

            # 複雜鍵：逐層解析
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
