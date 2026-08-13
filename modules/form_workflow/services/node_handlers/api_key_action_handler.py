"""
FormWorkflow Module - ApiKeyAction Handler
API Key 處置節點處理器 (P3, dev-notes/API_KEY_TRIGGER_SPEC.md)

暫停 (suspend) 或復原 (resume) 平台級 API Key，供資安流程機器處置疑似盜用。
處置對象三種來源：
- trigger:  發動本流程的 API Key (form_instance.source_api_key)
- static:   設計時指定的 key_id
- variable: 由變數運算式解析 key_id，如 ${f.key_id}

租戶隔離：僅能處置本流程所屬企業的 key。
冪等：suspend 已暫停 / resume 已啟用的 key 視為成功，不中斷流程。
"""
import logging
from typing import Dict, Any, Optional

from .base import BaseNodeHandler

logger = logging.getLogger(__name__)

VALID_ACTIONS = ('suspend', 'resume')
VALID_KEY_SOURCES = ('trigger', 'static', 'variable')


class ApiKeyActionHandler(BaseNodeHandler):
    """API Key 處置節點處理器"""

    def handle(self) -> Dict[str, Any]:
        self.report_running()

        action = (self.get_config_value('action') or 'suspend').strip().lower()
        if action not in VALID_ACTIONS:
            self.log_error(f'無效的處置動作: {action}')
            return {'status': 'error',
                    'message': f'無效的處置動作: {action}（僅支援 suspend / resume）'}

        key_source = (self.get_config_value('key_source') or 'trigger').strip().lower()
        if key_source not in VALID_KEY_SOURCES:
            self.log_error(f'無效的 key 來源: {key_source}')
            return {'status': 'error',
                    'message': f'無效的 key 來源: {key_source}'}

        key_id = self._resolve_key_id(key_source)
        if not key_id:
            msg = ('此流程實例非由 API Key 發動，無法取得處置對象'
                   if key_source == 'trigger'
                   else '無法解析處置對象 key_id（設定為空或變數解析結果為空）')
            self.log_error(msg)
            return {'status': 'error', 'message': msg}

        return self._apply_action(action, key_id)

    def _resolve_key_id(self, key_source: str) -> Optional[str]:
        """依 key_source 解析處置對象的 key_id"""
        if key_source == 'trigger':
            fi = self.form_instance
            return (fi.source_api_key or '').strip() or None if fi else None

        raw = (self.get_config_value('key_id') or '').strip()
        if not raw:
            return None
        if key_source == 'variable':
            return self.replace_variables(raw).strip() or None
        return raw

    def _set_rls_context(self, org_code: str):
        """設定 RLS session variable（背景 executor 無 request context）"""
        from app import db
        db.session.execute(
            db.text("SELECT set_config('app.current_org', :org, true)"),
            {'org': org_code}
        )

    def _apply_action(self, action: str, key_id: str) -> Dict[str, Any]:
        from app.models.api_key import (
            ApiKey, STATUS_ACTIVE, STATUS_SUSPENDED,
        )
        from app.services import api_key_service

        org_code = self.queue_item.org_secure_code
        self._set_rls_context(org_code)

        # 租戶隔離：僅查本企業、未撤銷的 key
        record = ApiKey.query.filter_by(
            key_id=key_id,
            org_secure_code=org_code,
            is_deleted=False,
        ).first()
        if record is None:
            msg = f'找不到 API Key {key_id}（不存在、已撤銷或非本企業）'
            self.log_error(msg)
            return {'status': 'error', 'message': msg}

        previous_status = record.status
        operator = f'wf:{self.queue_item.workflow_instance_secure_code}'

        try:
            if action == 'suspend':
                if record.status == STATUS_SUSPENDED:
                    self.log_info(f'API Key {key_id} 已是暫停狀態，跳過（冪等）')
                else:
                    reason = self.replace_variables(
                        self.get_config_value('reason') or '流程自動處置'
                    ).strip()[:500]
                    api_key_service.suspend_key(
                        record, reason, operator_secure_code=operator)
                    self.log_info(f'API Key {key_id} 已暫停', {'reason': reason})
            else:  # resume
                if record.status == STATUS_ACTIVE:
                    self.log_info(f'API Key {key_id} 已是啟用狀態，跳過（冪等）')
                else:
                    api_key_service.resume_key(
                        record, operator_secure_code=operator)
                    self.log_info(f'API Key {key_id} 已復原')
        except api_key_service.ApiKeyError as exc:
            self.log_error(f'API Key 處置失敗: {exc}')
            return {'status': 'error', 'message': f'API Key 處置失敗: {exc}'}

        return {
            'status': 'success',
            'message': f'API Key {key_id} {action} 完成',
            'data': {
                'key_id': key_id,
                'action': action,
                'previous_status': previous_status,
                'current_status': record.status,
            }
        }
