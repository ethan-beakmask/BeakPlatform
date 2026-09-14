"""
FormWorkflow Module - FieldWrite Handler
寫入表單欄位節點處理器

負責將設計時輸入的字串或變數值寫入表單的特定欄位。
"""
import logging
from typing import Dict, Any

from app import db
from sqlalchemy.orm.attributes import flag_modified

from .base import BaseNodeHandler

logger = logging.getLogger(__name__)


class FieldWriteHandler(BaseNodeHandler):
    """OP_FIELDWRITE 節點處理器"""

    def validate(self) -> bool:
        """驗證節點配置（允許空配置，執行時跳過）"""
        return True

    def handle(self) -> Dict[str, Any]:
        """處理 OpFieldWrite 節點"""
        self.report_running()

        try:
            # 取得配置
            target_field = self.get_config_value('target_field')
            content = self.get_config_value('content')

            # 如果沒有配置，跳過執行
            if not target_field or content is None:
                self.log_info('OpFieldWrite 節點未配置，跳過執行')
                return {
                    'status': 'success',
                    'message': '節點未配置，已跳過',
                    'data': {'skipped': True}
                }

            # 取得表單實例
            form_instance = self.form_instance
            if not form_instance:
                return {
                    'status': 'error',
                    'message': '找不到表單實例'
                }

            content_type = self.get_config_value('content_type', 'text')  # text 或 html

            # 解析 target_field：如果是變數語法格式 ${...}，提取實際欄位名稱
            target_field = self._parse_target_field(target_field)

            self.log_info('開始寫入表單欄位', {
                'target_field': target_field,
                'content_type': content_type,
                'content_length': len(content)
            })

            # 處理內容（變數替換）
            processed_content = self.replace_variables(
                content,
                include_form=True,
                include_workflow=True
            )

            # 處理換行符號
            if content_type == 'text':
                processed_content = processed_content.replace('\\n', '\n')
            elif content_type == 'html':
                processed_content = processed_content.replace('\\n', '<br>')

            # 寫入表單欄位
            form_data = form_instance.form_data or {}
            old_value = self._get_nested_value(form_data, target_field)

            # 寫入值
            self._set_nested_value(form_data, target_field, processed_content)

            # 更新表單實例
            form_instance.form_data = form_data
            flag_modified(form_instance, 'form_data')
            db.session.commit()

            # 同步更新流程變數 (FLOW scope)
            form_code = form_instance.form_template_secure_code or form_instance.form_code
            if form_code:
                var_name_prefixed = f'{form_code}_{target_field}'
                self.set_flow_var(var_name_prefixed, processed_content)
                self.set_flow_var(target_field, processed_content)
                self.log_info('已同步更新工作流變數', {
                    'var_name': var_name_prefixed
                })

            self.log_info('欄位寫入完成', {
                'target_field': target_field,
                'old_value': str(old_value)[:100] if old_value else None,
                'new_value': processed_content[:100] if len(processed_content) > 100 else processed_content
            })

            return {
                'status': 'success',
                'message': f'已寫入欄位「{target_field}」',
                'data': {
                    'target_field': target_field,
                    'content_type': content_type,
                    'content_length': len(processed_content)
                }
            }

        except Exception as e:
            self.log_error(f'寫入表單欄位失敗: {str(e)}')
            return {
                'status': 'error',
                'message': f'寫入表單欄位失敗: {str(e)}'
            }

    def _parse_target_field(self, target_field: str) -> str:
        """解析目標欄位名稱"""
        if not target_field:
            return target_field

        # 如果是變數語法格式 ${...}，提取實際欄位名稱
        if target_field.startswith('${') and target_field.endswith('}'):
            inner = target_field[2:-1]  # 移除 ${ 和 }
            if inner.startswith('form.'):
                # ${form.fieldKey} 格式
                return inner[5:]
            elif '_' in inner:
                # ${FORMCODE_fieldKey} 格式，取最後一個 _ 後面的部分
                return inner.split('_')[-1]
            else:
                return inner

        return target_field
