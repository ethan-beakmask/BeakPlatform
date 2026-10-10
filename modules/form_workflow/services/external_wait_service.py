"""Shared helpers for the ExternalWait workflow node."""
from __future__ import annotations

import hmac
import hashlib
import json
import logging
import os
import re
from datetime import datetime
from typing import Any, Tuple

from flask import current_app

from app import db
from app.models import SystemSetting
from modules.form_workflow.models import FwNodeExecutionQueue, FwWorkflowInstance
from modules.form_workflow.services.variable_service import VariableService
from modules.form_workflow.services.workflow_log_service import WorkflowLogService

logger = logging.getLogger(__name__)

MAX_PAYLOAD_BYTES = 65536
# 「不設逾時」時 scheduled_at 放的哨兵值：欄位 NOT NULL，而且遠期時間永遠不會被執行器當成到期
NO_TIMEOUT_SENTINEL = datetime(9999, 12, 31)
MAX_JSON_DEPTH = 10
TOKEN_RE = re.compile(r'^[0-9a-f]{32}$')
NODE_ID_RE = re.compile(r'^[A-Za-z0-9_-]{1,100}$')
INSTANCE_CODE_RE = re.compile(r'^[A-Za-z0-9_-]{16,40}$')

_HMAC_CONTEXT = b'external-wait-callback-v1'


def _hmac_key() -> bytes:
    secret = current_app.config.get('SECRET_KEY') or ''
    if isinstance(secret, str):
        secret = secret.encode('utf-8')
    return hmac.new(secret, _HMAC_CONTEXT, hashlib.sha256).digest()


def callback_token(instance_code: str, node_id: str) -> str:
    msg = f'{instance_code}|{node_id}'.encode('utf-8')
    return hmac.new(_hmac_key(), msg, hashlib.sha256).hexdigest()[:32]


def verify_token(instance_code: str, node_id: str, token: str) -> bool:
    if not TOKEN_RE.match(token or ''):
        return False
    expected = callback_token(instance_code, node_id)
    return hmac.compare_digest(expected, token)


def build_callback_url(instance_code: str, node_id: str) -> str | None:
    base = (SystemSetting.get('system_base_url', '') or '').strip().rstrip('/')
    if not base:
        return None
    prefix = (os.environ.get('APP_PREFIX', '/beakplatform') or '').strip()
    if prefix and not prefix.startswith('/'):
        prefix = '/' + prefix
    prefix = prefix.rstrip('/')
    token = callback_token(instance_code, node_id)
    return f'{base}{prefix}/api/external-wait/callback/{instance_code}/{node_id}/{token}'


def payload_var_name(node_id: str) -> str:
    return f'_extwait_{node_id}_payload'


def meta_var_name(node_id: str) -> str:
    return f'_extwait_{node_id}_meta'


def json_depth(obj: Any) -> int:
    if isinstance(obj, dict):
        if not obj:
            return 1
        return 1 + max(json_depth(v) for v in obj.values())
    if isinstance(obj, list):
        if not obj:
            return 1
        return 1 + max(json_depth(v) for v in obj)
    return 1


def _latest_queue_item(instance_code: str, node_id: str) -> FwNodeExecutionQueue | None:
    return FwNodeExecutionQueue.query.filter_by(
        workflow_instance_secure_code=instance_code,
        node_id=node_id,
        node_type='ExternalWait',
    ).order_by(FwNodeExecutionQueue.id.desc()).first()


def _not_found() -> Tuple[int, dict]:
    return 404, {'error': 'not_found'}


def receive_callback(
    instance_code: str,
    node_id: str,
    token: str,
    raw_body: bytes,
    source_ip: str | None,
) -> Tuple[int, dict]:
    if (
        not INSTANCE_CODE_RE.match(instance_code or '')
        or not NODE_ID_RE.match(node_id or '')
        or not TOKEN_RE.match(token or '')
    ):
        return _not_found()

    instance = FwWorkflowInstance.query.filter_by(secure_code=instance_code).first()
    if not instance or not verify_token(instance_code, node_id, token):
        return _not_found()

    if VariableService.get_flow_var(instance_code, meta_var_name(node_id)) is not None:
        return 409, {'error': 'already_received'}

    if instance.status != 'RUNNING':
        return 409, {'error': 'workflow_not_running'}

    queue_item = _latest_queue_item(instance_code, node_id)
    if queue_item and queue_item.status in ('SUCCESS', 'FAILED', 'CANCELLED'):
        return 409, {'error': 'already_completed'}

    if len(raw_body or b'') > MAX_PAYLOAD_BYTES:
        return 413, {'error': 'payload_too_large'}

    if raw_body:
        try:
            payload = json.loads(raw_body.decode('utf-8'))
        except (UnicodeDecodeError, ValueError):
            return 400, {'error': 'invalid_json'}
    else:
        payload = {}

    if json_depth(payload) > MAX_JSON_DEPTH:
        return 400, {'error': 'payload_too_deep'}

    now = datetime.utcnow()
    meta = {
        'received_at': now.isoformat(),
        'source_ip': source_ip,
        'consumed': False,
    }
    VariableService.set_flow_var(
        instance_code,
        payload_var_name(node_id),
        payload,
        instance.org_secure_code,
        node_id,
    )
    VariableService.set_flow_var(
        instance_code,
        meta_var_name(node_id),
        meta,
        instance.org_secure_code,
        node_id,
    )

    state = 'buffered'
    if queue_item:
        WorkflowLogService.log(
            workflow_instance_id=instance.id,
            node_queue_id=queue_item.id,
            node_id=queue_item.node_id,
            node_type=queue_item.node_type,
            status=queue_item.status,
            node_instance_id=queue_item.secure_code,
            org_secure_code=queue_item.org_secure_code,
            level='INFO',
            message='收到外部回呼',
            data={'source_ip': source_ip},
        )
        # WAITING：叫執行器下一輪撿起來。RUNNING／PENDING：處理器可能剛讀過變數、正要寫回
        # waiting，這裡先把 scheduled_at 推到現在，處理器那邊 commit 完會再查一次變數；
        # 兩邊各讓一步，回呼在任何時序到達都不會卡死（見 docs/develop/custom_node_wait.md 第一節）
        if queue_item.status in ('WAITING', 'RUNNING', 'PENDING'):
            queue_item.scheduled_at = now
            db.session.commit()
            state = 'woken'

    return 202, {'accepted': True, 'state': state}
