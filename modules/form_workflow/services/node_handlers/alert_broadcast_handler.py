"""
FormWorkflow Module - AlertBroadcast Handler
緊急廣播節點處理器

觸發全頁強制彈窗，用戶必須捲到底部勾選 [已知道] 才能關閉。
支援目標指定（全企業 / 特定角色 / 特定部門）。
"""
import logging
from datetime import datetime
from typing import Dict, Any

from .base import BaseNodeHandler

logger = logging.getLogger(__name__)


class AlertBroadcastHandler(BaseNodeHandler):
    """緊急廣播節點處理器"""

    def handle(self) -> Dict[str, Any]:
        self.report_running()

        broadcast_code = self.get_config_value('broadcast_code', '')
        if not broadcast_code:
            self.log_error('未設定 broadcast_code')
            return {
                'status': 'error',
                'message': '未設定廣播代碼 (broadcast_code)',
            }

        return self._create_alert(broadcast_code)

    def _set_rls_context(self, org_code: str):
        """設定 RLS session variable，讓背景 executor 能通過 lookup_items RLS policy"""
        from app import db
        db.session.execute(
            db.text("SELECT set_config('app.current_org', :org, true)"),
            {'org': org_code}
        )

    def _create_alert(self, broadcast_code: str) -> Dict[str, Any]:
        """建立緊急廣播"""
        from app import db
        from app.models import LookupItem
        from app.utils.security import generate_secure_code

        title = self.get_config_value('title', '')
        message = self.get_config_value('message', '')
        require_ack = self.get_config_value('require_ack', True)

        # 支援變數替換
        if title:
            title = self.replace_variables(title)
        if message:
            message = self.replace_variables(message)

        if not title:
            self.log_error('未設定標題')
            return {'status': 'error', 'message': '未設定廣播標題'}

        # 目標設定
        target_type = self.get_config_value('target_type', 'all')
        target_roles = self.get_config_value('target_roles', [])
        target_departments = self.get_config_value('target_departments', [])
        include_children = self.get_config_value('include_children', True)

        target = {'type': target_type}
        if target_type == 'specific':
            target['roles'] = target_roles
            target['departments'] = target_departments
            target['include_children'] = include_children

        org_code = self.queue_item.org_secure_code
        self._set_rls_context(org_code)

        value_data = {
            'type': 'alert',
            'title': title,
            'message': message,
            'target': target,
            'require_ack': require_ack,
            'created_by_instance': self.queue_item.workflow_instance_secure_code,
            'created_at': datetime.utcnow().isoformat(),
        }

        # 檢查是否已有相同 code 的 active 廣播
        existing = LookupItem.query.filter_by(
            org_secure_code=org_code,
            category_code='broadcast',
            code=broadcast_code,
            is_deleted=False,
        ).first()

        if existing:
            existing.label = title[:200]
            existing.value = value_data
            existing.is_active = True

            # 清除舊的已讀確認（重新發動 = 全新警報，所有人需重新確認）
            from app.models import BroadcastAcknowledgment
            BroadcastAcknowledgment.query.filter_by(
                broadcast_secure_code=existing.secure_code,
            ).delete()

            self.log_info(f'更新既有緊急廣播（已清除舊確認記錄）: {broadcast_code}')
        else:
            item = LookupItem(
                secure_code=generate_secure_code(),
                org_secure_code=org_code,
                category_code='broadcast',
                code=broadcast_code,
                label=title[:200],
                value=value_data,
                sort_order=0,
                is_active=True,
            )
            db.session.add(item)
            self.log_info(f'建立緊急廣播: {broadcast_code}')

        db.session.commit()

        return {
            'status': 'success',
            'message': f'緊急廣播已發送: {broadcast_code}',
            'data': {
                'broadcast_code': broadcast_code,
                'target': target,
                'require_ack': require_ack,
            }
        }
