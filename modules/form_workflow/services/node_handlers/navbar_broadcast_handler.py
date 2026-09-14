"""
FormWorkflow Module - NavbarBroadcast Handler
跑馬燈廣播節點處理器

兩種模式：
- StartBroadcast: 建立廣播記錄，開始在 Navbar 顯示跑馬燈
- EndBroadcast: 根據 broadcast_code 關閉廣播
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, Any

from .base import BaseNodeHandler

logger = logging.getLogger(__name__)


class NavbarBroadcastHandler(BaseNodeHandler):
    """跑馬燈廣播節點處理器"""

    def handle(self) -> Dict[str, Any]:
        self.report_running()

        mode = self.get_config_value('mode', 'start')
        broadcast_code = self.get_config_value('broadcast_code', '')

        if not broadcast_code:
            self.log_error('未設定 broadcast_code')
            return {
                'status': 'error',
                'message': '未設定廣播代碼 (broadcast_code)',
            }

        if mode == 'start':
            return self._handle_start(broadcast_code)
        elif mode == 'end':
            return self._handle_end(broadcast_code)
        else:
            self.log_error(f'未知模式: {mode}')
            return {
                'status': 'error',
                'message': f'未知模式: {mode}',
            }

    def _set_rls_context(self, org_code: str):
        """設定 RLS session variable，讓背景 executor 能通過 lookup_items RLS policy"""
        from app import db
        db.session.execute(
            db.text("SELECT set_config('app.current_org', :org, true)"),
            {'org': org_code}
        )

    def _handle_start(self, broadcast_code: str) -> Dict[str, Any]:
        """啟動跑馬燈廣播"""
        from app import db
        from app.models import LookupItem
        from app.utils.security import generate_secure_code

        message = self.get_config_value('message', '')
        if message:
            message = self.replace_variables(message)

        if not message:
            self.log_error('未設定訊息內容')
            return {'status': 'error', 'message': '未設定訊息內容'}

        text_color = self.get_config_value('text_color', '#000000')
        bg_color = self.get_config_value('bg_color', '#FDE047')
        display_seconds = self.get_config_value('display_seconds', 5)
        duration_minutes = self.get_config_value('duration_minutes', 0)

        # 計算過期時間
        expires_at = None
        if duration_minutes and duration_minutes > 0:
            expires_at = datetime.utcnow() + timedelta(minutes=duration_minutes)

        org_code = self.queue_item.org_secure_code
        self._set_rls_context(org_code)

        # 檢查是否已有相同 code 的 active 廣播，有則更新
        existing = LookupItem.query.filter_by(
            org_secure_code=org_code,
            category_code='broadcast',
            code=broadcast_code,
            is_deleted=False
        ).first()

        value_data = {
            'type': 'navbar',
            'message': message,
            'text_color': text_color,
            'bg_color': bg_color,
            'display_seconds': display_seconds,
            'expires_at': expires_at.isoformat() if expires_at else None,
            'created_by_instance': self.queue_item.workflow_instance_secure_code,
            'started_at': datetime.utcnow().isoformat(),
        }

        if existing:
            existing.label = message[:200]
            existing.value = value_data
            existing.is_active = True
            self.log_info(f'更新既有跑馬燈廣播: {broadcast_code}')
        else:
            item = LookupItem(
                secure_code=generate_secure_code(),
                org_secure_code=org_code,
                category_code='broadcast',
                code=broadcast_code,
                label=message[:200],
                value=value_data,
                sort_order=0,
                is_active=True,
            )
            db.session.add(item)
            self.log_info(f'建立跑馬燈廣播: {broadcast_code}')

        db.session.commit()

        return {
            'status': 'success',
            'message': f'跑馬燈廣播已啟動: {broadcast_code}',
            'data': {
                'broadcast_code': broadcast_code,
                'mode': 'start',
            }
        }

    def _handle_end(self, broadcast_code: str) -> Dict[str, Any]:
        """停止跑馬燈廣播"""
        from app import db
        from app.models import LookupItem

        org_code = self.queue_item.org_secure_code
        self._set_rls_context(org_code)

        item = LookupItem.query.filter_by(
            org_secure_code=org_code,
            category_code='broadcast',
            code=broadcast_code,
            is_deleted=False
        ).first()

        if item:
            item.is_active = False
            if item.value:
                item.value = {**item.value, 'stopped_at': datetime.utcnow().isoformat()}
            db.session.commit()
            self.log_info(f'跑馬燈廣播已停止: {broadcast_code}')
        else:
            self.log_warning(f'找不到廣播: {broadcast_code}')

        return {
            'status': 'success',
            'message': f'跑馬燈廣播已停止: {broadcast_code}',
            'data': {
                'broadcast_code': broadcast_code,
                'mode': 'end',
            }
        }
