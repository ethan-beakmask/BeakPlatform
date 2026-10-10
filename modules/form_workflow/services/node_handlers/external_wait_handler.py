"""ExternalWait node handler."""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any, Dict

from flask_babel import gettext as _

from app import db
from modules.form_workflow.services.external_wait_service import (
    NO_TIMEOUT_SENTINEL,
    build_callback_url,
    meta_var_name,
    payload_var_name,
)
from modules.form_workflow.services.variable_service import VariableService

from .base import BaseNodeHandler

VAR_NAME_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ('1', 'true', 'yes', 'y', 'on')
    return bool(value)


class ExternalWaitHandler(BaseNodeHandler):
    """Wait for a signed external callback or an optional timeout."""

    def validate(self) -> bool:
        result_var = self.get_config_value('result_var')
        if not isinstance(result_var, str) or not VAR_NAME_RE.match(result_var.strip()):
            raise ValueError(_('result_var 格式不合法'))

        if _coerce_bool(self.get_config_value('timeout_enabled', False)):
            try:
                minutes = int(self.get_config_value('timeout_minutes'))
            except (TypeError, ValueError):
                minutes = 0
            if minutes < 1 or minutes > 14400:
                raise ValueError(_('timeout_minutes 必須介於 1 到 14400'))
        return True

    def handle(self) -> Dict[str, Any]:
        self.report_running()
        existing = ((self.queue_item.result or {}).get('data') or {})
        result_var = str(self.get_config_value('result_var') or '').strip()
        instance_code = self.queue_item.workflow_instance_secure_code
        node_id = self.queue_item.node_id

        meta = VariableService.get_flow_var(instance_code, meta_var_name(node_id))
        payload = VariableService.get_flow_var(instance_code, payload_var_name(node_id))
        if isinstance(meta, dict) and not meta.get('consumed'):
            return self._finish_received(result_var, existing, meta, payload)

        now = datetime.utcnow()
        timeout_at_raw = existing.get('timeout_at')
        if timeout_at_raw:
            timeout_at = self._parse_datetime(timeout_at_raw)
            if timeout_at and now >= timeout_at:
                return self._finish_timeout(result_var, existing)
            if timeout_at:
                self.queue_item.scheduled_at = timeout_at
                db.session.commit()
            return {
                'status': 'waiting',
                'message': '等待外部回呼',
                'data': existing,
            }

        callback_url = build_callback_url(instance_code, node_id)
        if not callback_url:
            self.log_warning('ExternalWait 缺少 system_base_url', {'node_id': node_id})

        timeout_at = None
        if _coerce_bool(self.get_config_value('timeout_enabled', False)):
            timeout_at = now + timedelta(minutes=int(self.get_config_value('timeout_minutes')))
            self.queue_item.scheduled_at = timeout_at
        else:
            # 欄位 NOT NULL；遠期哨兵值讓執行器永遠不會把它當成到期，只有回呼端點改 scheduled_at 才會喚醒
            self.queue_item.scheduled_at = NO_TIMEOUT_SENTINEL
        db.session.commit()

        data = {
            'timeout_at': timeout_at.isoformat() if timeout_at else None,
            'callback_url': callback_url,
            'waiting_since': now.isoformat(),
        }

        # commit 之後再查一次：回呼若在「上面讀變數」與「這裡」之間到達，端點只會把 scheduled_at
        # 推到現在、不會再被上面的 commit 覆蓋；而回呼若更早到，這一查就能直接收下，不必再等一輪
        meta = VariableService.get_flow_var(instance_code, meta_var_name(node_id))
        if isinstance(meta, dict) and not meta.get('consumed'):
            payload = VariableService.get_flow_var(instance_code, payload_var_name(node_id))
            return self._finish_received(result_var, data, meta, payload)

        return {
            'status': 'waiting',
            'message': '等待外部回呼',
            'data': data,
        }

    def _finish_received(self, result_var: str, existing: Dict[str, Any], meta: Dict[str, Any], payload: Any) -> Dict[str, Any]:
        callback_url = existing.get('callback_url') or build_callback_url(
            self.queue_item.workflow_instance_secure_code,
            self.queue_item.node_id,
        )
        waiting_since = existing.get('waiting_since')
        waited_seconds = self._waited_seconds(waiting_since)
        self._set_result_vars(result_var, {
            'result': 'received',
            'payload': payload,
            'received_at': meta.get('received_at'),
            'source_ip': meta.get('source_ip'),
            'callback_url': callback_url,
            'waited_seconds': waited_seconds,
        })
        meta = dict(meta)
        meta['consumed'] = True
        VariableService.set_flow_var(
            self.queue_item.workflow_instance_secure_code,
            meta_var_name(self.queue_item.node_id),
            meta,
            self.queue_item.org_secure_code,
            self.queue_item.node_id,
        )
        return {
            'status': 'success',
            'message': '已收到外部回呼',
            'data': {'result': 'received', 'waited_seconds': waited_seconds},
        }

    def _finish_timeout(self, result_var: str, existing: Dict[str, Any]) -> Dict[str, Any]:
        waited_seconds = self._waited_seconds(existing.get('waiting_since'))
        self._set_result_vars(result_var, {
            'result': 'timeout',
            'payload': None,
            'received_at': None,
            'source_ip': None,
            'callback_url': existing.get('callback_url'),
            'waited_seconds': waited_seconds,
        })
        return {
            'status': 'success',
            'message': '等待外部回呼逾時',
            'data': {'result': 'timeout', 'waited_seconds': waited_seconds},
        }

    def _set_result_vars(self, result_var: str, values: Dict[str, Any]) -> None:
        if not VAR_NAME_RE.match(result_var or ''):
            return
        for suffix, value in values.items():
            self.set_flow_var(f'{result_var}_{suffix}', value)

    @staticmethod
    def _parse_datetime(value: str):
        try:
            return datetime.fromisoformat(str(value).replace('Z', '+00:00')).replace(tzinfo=None)
        except ValueError:
            return None

    @staticmethod
    def _waited_seconds(waiting_since: str | None) -> int:
        if not waiting_since:
            return 0
        try:
            start = datetime.fromisoformat(str(waiting_since).replace('Z', '+00:00')).replace(tzinfo=None)
        except ValueError:
            return 0
        return max(0, int((datetime.utcnow() - start).total_seconds()))
