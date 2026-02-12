"""
FormWorkflow Module - FieldRead Handler
讀取表單欄位節點處理器

負責讀取發動流程的表單欄位值，存入流程全域變數。
變數命名格式：{表單代碼}_{欄位key}
"""
import logging
from typing import Dict, Any

from .base import BaseNodeHandler

logger = logging.getLogger(__name__)


class FieldReadHandler(BaseNodeHandler):
    """OP_FIELDREAD 節點處理器"""

    def validate(self) -> bool:
        """驗證節點配置"""
        # 此節點通常不需要額外配置
        return True

    def handle(self) -> Dict[str, Any]:
        """處理 OpFieldRead 節點"""
        self.report_running()

        try:
            # 取得表單實例
            form_instance = self.form_instance
            if not form_instance:
                return {
                    'status': 'error',
                    'message': '找不到表單實例'
                }

            # 使用表單實例中的快照資訊（不依賴 relationship）
            form_code = form_instance.form_template_secure_code or form_instance.form_code
            form_name = form_instance.form_name or '未知表單'

            if not form_code:
                return {
                    'status': 'error',
                    'message': '找不到表單模板代碼'
                }

            self.log_info('開始讀取表單欄位', {
                'form_code': form_code,
                'form_name': form_name
            })

            # 讀取表單資料
            form_data = form_instance.form_data or {}

            # 取得要讀取的欄位列表
            fields_to_read = self.get_config_value('fields', [])

            # 如果沒有配置欄位，嘗試從流程模板的 fieldReadConfig 取得
            if not fields_to_read and form_instance.form_template_id:
                fields_to_read = self._get_fields_from_workflow_config(form_instance.form_template_id)

            # 如果還是沒有，自動讀取所有表單欄位（排除系統欄位）
            if not fields_to_read and form_data:
                fields_to_read = [
                    key for key in form_data.keys()
                    if not key.startswith('_') and key not in ('submit', 'data')
                ]
                self.log_info(f'自動偵測到 {len(fields_to_read)} 個表單欄位')

            # 讀取指定欄位並設定全域變數
            read_results = {}
            for field_key in fields_to_read:
                # 從表單資料取得欄位值
                field_value = self._get_nested_value(form_data, field_key)

                # 建立變數名稱（兩種格式）
                var_name_prefixed = f'{form_code}_{field_key}'
                var_name_simple = field_key

                # 設定全域變數
                self.set_global_var(var_name_prefixed, field_value)
                self.set_global_var(var_name_simple, field_value)

                read_results[var_name_prefixed] = field_value

                self.log_info(f'讀取欄位: {field_key} = {field_value}', {
                    'field_key': field_key,
                    'var_name': var_name_prefixed,
                    'value_type': type(field_value).__name__
                })

            self.log_info('欄位讀取完成', {
                'form_name': form_name,
                'read_count': len(read_results)
            })

            return {
                'status': 'success',
                'message': f'已讀取「{form_name}」的 {len(read_results)} 個欄位',
                'data': {
                    'form_code': form_code,
                    'form_name': form_name,
                    'read_count': len(read_results),
                    'variables': read_results
                }
            }

        except Exception as e:
            self.log_error(f'讀取表單欄位失敗: {str(e)}')
            return {
                'status': 'error',
                'message': f'讀取表單欄位失敗: {str(e)}'
            }

    def _get_fields_from_workflow_config(self, form_template_id: int) -> list:
        """從流程模板配置取得要讀取的欄位列表"""
        if not self.workflow_instance:
            return []

        from ..workflow_engine import WorkflowEngine
        graph = WorkflowEngine.get_effective_graph(self.workflow_instance)
        if not graph:
            return []

        field_read_config = graph.get('fieldReadConfig', {})
        if field_read_config:
            form_key = f'formId_{form_template_id}'
            form_field_config = field_read_config.get(form_key, {})
            return form_field_config.get('fields', [])

        return []
