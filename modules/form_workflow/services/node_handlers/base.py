"""
FormWorkflow Module - Base Node Handler
節點處理器基礎類別

定義所有節點處理器的標準介面。
變數系統 v2: 前綴制 (f./fi./v./wi./n./t.)，見 dev-notes/VARIABLE_SYSTEM_SPEC.md
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

    # 新式變數分隔符（設計器 UI 顯示用，過渡期引擎仍支援）
    DISPLAY_VAR_SEPARATOR = '::'

    # fi. 前綴對應的 FwFormInstance model 欄位
    _FI_FIELD_MAP = {
        'fi.applicant':       'applicant_name',
        'fi.applicant_dept':  'applicant_dept',
        'fi.applicant_email': 'applicant_email',
        'fi.applicant_code':  'applicant_secure_code',
        'fi.serial':          'serial_number',
        'fi.name':            'form_name',
        'fi.subject':         'subject',
        'fi.code':            'secure_code',
        'fi.status':          'status',
    }

    # wi. 前綴對應的解析方式（在 _resolve_wi 中處理）
    _WI_FIELDS = {'wi.code', 'wi.exec_code', 'wi.name', 'wi.status', 'wi.depth'}

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

    def _get_root_instance_code(self) -> Optional[str]:
        """取得 root_instance_code（用於 TREE scope）"""
        if self.workflow_instance:
            return self.workflow_instance.root_instance_code or self.workflow_instance.secure_code
        return None

    # ========================================
    # 變數 API (v2: TREE / FLOW / NODE)
    # ========================================
    def get_var(self, var_name: str, default: Any = None) -> Any:
        """
        取得變數（優先序: NODE > FLOW > TREE）

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

        root_code = self._get_root_instance_code()
        return VariableService.get_var(instance_code, root_code, var_name, default)

    def set_tree_var(self, var_name: str, value: Any):
        """設定跨流程變數（TREE scope）"""
        from ..variable_service import VariableService

        instance_code = self._get_workflow_instance_code()
        root_code = self._get_root_instance_code()
        if not instance_code or not root_code:
            logger.warning("Cannot set tree var: instance_code or root_code is None")
            return None

        return VariableService.set_tree_var(
            root_code, var_name, value,
            instance_code=instance_code,
            org_code=self.queue_item.org_secure_code,
            source_node_id=self.queue_item.node_id
        )

    def set_flow_var(self, var_name: str, value: Any):
        """設定流程級變數（FLOW scope）"""
        from ..variable_service import VariableService

        instance_code = self._get_workflow_instance_code()
        if not instance_code:
            logger.warning("Cannot set flow var: workflow_instance_code is None")
            return None

        return VariableService.set_flow_var(
            instance_code, var_name, value,
            self.queue_item.org_secure_code,
            self.queue_item.node_id
        )

    def set_node_var(self, var_name: str, value: Any):
        """設定節點級變數（NODE scope）"""
        from ..variable_service import VariableService

        instance_code = self._get_workflow_instance_code()
        if not instance_code:
            logger.warning("Cannot set node var: workflow_instance_code is None")
            return None

        return VariableService.set_node_var(
            instance_code, var_name, value,
            self.queue_item.org_secure_code,
            self.queue_item.node_id
        )

    # deprecated aliases
    def set_global_var(self, var_name: str, value: Any):
        """deprecated: 用 set_flow_var"""
        return self.set_flow_var(var_name, value)

    def set_local_var(self, var_name: str, value: Any):
        """deprecated: 用 set_node_var"""
        return self.set_node_var(var_name, value)

    def get_all_vars(self) -> Dict[str, Any]:
        """
        取得所有可見變數（TREE + FLOW + NODE）

        Returns:
            變數字典
        """
        from ..variable_service import VariableService

        instance_code = self._get_workflow_instance_code()
        if not instance_code:
            return {}

        root_code = self._get_root_instance_code()
        return VariableService.get_all_vars(instance_code, root_code)

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
    # 統一變數替換 API (v2: 前綴制)
    # ========================================
    def replace_variables(self, text: str, **kwargs) -> str:
        """
        通用變數替換方法 (v2)

        前綴制語法 (見 dev-notes/VARIABLE_SYSTEM_SPEC.md):
        - ${f.field_key}       表單欄位值 (form_data JSON)
        - ${fi.applicant}      表單資訊 (form_instance model 欄位)
        - ${v.var_name}        流程變數 (NODE > FLOW > TREE)
        - ${wi.code}           流程資訊 (workflow_instance model 欄位)
        - ${n.name}            節點上下文
        - ${t.now}             時間

        過渡期支援:
        - ${form.xxx}          → 舊語法 fallback
        - ${workflow.xxx}      → 舊語法 fallback
        - ${timestamp.xxx}     → 舊語法 fallback
        - ${node.xxx}          → 舊語法 fallback
        - ${bare_name}         → 無前綴裸名 fallback (查 v. scope + 警告)
        - ${表單名::欄位}       → 顯示格式 fallback

        Args:
            text: 要處理的文字

        Returns:
            替換後的文字
        """
        if not text:
            return ''

        all_vars = self.get_all_vars()
        now = datetime.utcnow()

        def replace_var(match):
            var_expr = match.group(1)

            # --- v2 前綴制 ---

            # f. 表單欄位
            if var_expr.startswith('f.') and not var_expr.startswith('fi.'):
                field_name = var_expr[2:]
                value = self.get_form_field(field_name)
                return str(value) if value is not None else ''

            # fi. 表單資訊
            if var_expr.startswith('fi.'):
                return self._resolve_fi(var_expr)

            # v. 流程變數
            if var_expr.startswith('v.'):
                var_name = var_expr[2:]
                value = all_vars.get(var_name)
                return str(value) if value is not None else ''

            # wi. 流程資訊
            if var_expr.startswith('wi.'):
                return self._resolve_wi(var_expr)

            # n. 節點上下文
            if var_expr.startswith('n.'):
                return self._resolve_n(var_expr)

            # t. 時間
            if var_expr.startswith('t.'):
                return self._resolve_t(var_expr, now)

            # --- 過渡期: 舊語法 fallback ---

            # form.* (舊 → fi. 或 f.)
            if var_expr.startswith('form.'):
                return self._legacy_resolve_form(var_expr)

            # workflow.* (舊 → wi.)
            if var_expr.startswith('workflow.'):
                return self._legacy_resolve_workflow(var_expr)

            # timestamp* (舊 → t.)
            if var_expr.startswith('timestamp'):
                return self._legacy_resolve_timestamp(var_expr, now)

            # node.* (舊 → n.)
            if var_expr.startswith('node.'):
                return self._legacy_resolve_node(var_expr)

            # 新式顯示變數（表單名::欄位標籤）
            if self.DISPLAY_VAR_SEPARATOR in var_expr:
                internal_var = self._resolve_display_variable(var_expr)
                if internal_var:
                    value = all_vars.get(internal_var)
                    if value is not None:
                        return str(value)

            # 無前綴裸名 → fallback 查 all_vars (過渡期)
            value = all_vars.get(var_expr)
            if value is not None:
                logger.warning(f"[VarReplace] 無前綴裸名 '${{{var_expr}}}'，"
                               f"請改用 '${{v.{var_expr}}}'")
                return str(value)

            return ''

        result = re.sub(r'\$\{([^}]+)\}', replace_var, text)
        return result

    # ========================================
    # v2 前綴解析器
    # ========================================

    def _resolve_fi(self, var_expr: str) -> str:
        """解析 fi.* 表單資訊"""
        if not self.form_instance:
            return ''

        attr_name = self._FI_FIELD_MAP.get(var_expr)
        if attr_name:
            value = getattr(self.form_instance, attr_name, None)
            return str(value) if value is not None else ''

        return ''

    def _resolve_wi(self, var_expr: str) -> str:
        """解析 wi.* 流程資訊"""
        if var_expr == 'wi.code':
            return self.queue_item.workflow_instance_secure_code or ''
        elif var_expr == 'wi.exec_code':
            if self.workflow_instance:
                return getattr(self.workflow_instance, 'execution_code', '') or ''
            return ''
        elif var_expr == 'wi.name':
            if self.workflow_instance:
                return getattr(self.workflow_instance, 'workflow_name', '') or ''
            return ''
        elif var_expr == 'wi.status':
            if self.workflow_instance:
                return getattr(self.workflow_instance, 'status', '') or ''
            return ''
        elif var_expr == 'wi.depth':
            if self.workflow_instance:
                return str(getattr(self.workflow_instance, 'workflow_depth', 0) or 0)
            return '0'
        return ''

    def _resolve_n(self, var_expr: str) -> str:
        """解析 n.* 節點上下文"""
        if var_expr == 'n.name':
            return self.queue_item.node_name or ''
        elif var_expr == 'n.id':
            return self.queue_item.node_id or ''
        elif var_expr == 'n.type':
            return self.queue_item.node_type or ''
        return ''

    def _resolve_t(self, var_expr: str, now: datetime) -> str:
        """解析 t.* 時間"""
        if var_expr == 't.now':
            return now.strftime('%Y-%m-%d %H:%M:%S')
        elif var_expr == 't.date':
            return now.strftime('%Y-%m-%d')
        elif var_expr == 't.time':
            return now.strftime('%H:%M:%S')
        return ''

    # ========================================
    # 過渡期: 舊語法 fallback
    # ========================================

    def _legacy_resolve_form(self, var_expr: str) -> str:
        """舊 form.* → fi. 或 f. fallback"""
        if not self.form_instance:
            return ''

        if var_expr == 'form.instance_id':
            return str(self.form_instance.id) if self.form_instance else ''
        elif var_expr == 'form.instance_code':
            return self.form_instance.secure_code if self.form_instance else ''
        elif var_expr == 'form.serial_number':
            return getattr(self.form_instance, 'serial_number', '') or ''
        elif var_expr == 'form.display_name':
            return self.form_instance.form_name or ''
        elif var_expr == 'form.applicant_name':
            return getattr(self.form_instance, 'applicant_name', '') or ''
        elif var_expr == 'form.applicant_dept':
            return getattr(self.form_instance, 'applicant_dept', '') or ''
        elif var_expr == 'form.applicant_email':
            return getattr(self.form_instance, 'applicant_email', '') or ''
        else:
            field_name = var_expr[5:]  # 移除 "form." 前綴
            value = self.get_form_field(field_name)
            return str(value) if value is not None else ''

    def _legacy_resolve_workflow(self, var_expr: str) -> str:
        """舊 workflow.* → wi. fallback"""
        if var_expr == 'workflow.instance_id':
            return str(self._get_workflow_instance_id() or '')
        elif var_expr == 'workflow.instance_code':
            return self.queue_item.workflow_instance_secure_code or ''
        elif var_expr == 'workflow.name':
            if self.workflow_instance:
                return getattr(self.workflow_instance, 'workflow_name', '') or ''
            return ''
        elif var_expr == 'workflow.execution_code':
            if self.workflow_instance:
                return getattr(self.workflow_instance, 'execution_code', '') or ''
            return ''
        return ''

    def _legacy_resolve_timestamp(self, var_expr: str, now: datetime) -> str:
        """舊 timestamp* → t. fallback"""
        if var_expr == 'timestamp':
            return now.strftime('%Y-%m-%d %H:%M:%S')
        elif var_expr == 'timestamp.date':
            return now.strftime('%Y-%m-%d')
        elif var_expr == 'timestamp.time':
            return now.strftime('%H:%M:%S')
        return ''

    def _legacy_resolve_node(self, var_expr: str) -> str:
        """舊 node.* → n. fallback"""
        if var_expr == 'node.display_name':
            return self.queue_item.node_name or ''
        return ''

    # ========================================
    # 新式顯示變數（過渡期保留）
    # ========================================

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

        parts = display_var.split(self.DISPLAY_VAR_SEPARATOR)
        if len(parts) != 2:
            return None

        field_label_part = parts[1].strip()

        # 處理可能的 key 後綴：姓名(applicant_name) -> 姓名, applicant_name
        field_label = field_label_part
        explicit_key = None
        if '(' in field_label_part and field_label_part.endswith(')'):
            idx = field_label_part.rfind('(')
            field_label = field_label_part[:idx]
            explicit_key = field_label_part[idx+1:-1]

        if not self.form_instance:
            logger.warning(f"[DisplayVar] form_instance 為 None，無法解析 '{display_var}'")
            return None

        schema = None
        form_secure_code = self.form_instance.form_template_secure_code

        if self.form_instance.schema_snapshot:
            schema = self.form_instance.schema_snapshot
        else:
            from ...models import FwFormTemplate
            form_template = FwFormTemplate.query.filter_by(
                secure_code=form_secure_code
            ).first()
            if form_template:
                schema = form_template.schema

        if not schema:
            logger.warning(f"[DisplayVar] schema 為 None，無法解析 '{display_var}'")
            return None

        def normalize(s):
            return s.replace(' ', '').replace('\u3000', '') if s else ''

        def find_field_by_label(components, target_label, target_key=None):
            for comp in (components or []):
                comp_key = comp.get('key', '')
                comp_label = comp.get('label', '')
                comp_type = comp.get('type', '')

                if comp.get('input', False) and comp_type not in ('button', 'submit'):
                    if target_key and comp_key == target_key:
                        return comp_key
                    if normalize(comp_label) == normalize(target_label):
                        return comp_key

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

        field_key = find_field_by_label(schema.get('components', []), field_label, explicit_key)

        if field_key:
            internal_var = f"{form_secure_code}_{field_key}"
            logger.info(f"[DisplayVar] 解析成功: '{display_var}' -> '{internal_var}' (透過標籤 '{field_label}')")
            return internal_var
        else:
            form_name = self.form_instance.form_name or form_secure_code
            logger.warning(f"[DisplayVar] 解析失敗: '{display_var}' - 在表單 '{form_name}' 中找不到標籤 '{field_label}'")
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
