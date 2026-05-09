"""
FormWorkflow Module - DecisionWriter Handler

寫入一筆 OdDefenseDecision,等同企業版「寫 PA EDL」的開源等價物 -- 廠牌中性。
任何外部執行端(CrowdSec / nftables / Cloudflare 等)透過 enforcement_points 篩選後拉取執行。

org_secure_code 嚴格繼承自 queue_item(workflow instance),
即使 form 欄位被竄改也不會跨租戶污染決策表。
"""
import logging
from typing import Dict, Any

from .base import BaseNodeHandler

logger = logging.getLogger(__name__)


class DecisionWriterHandler(BaseNodeHandler):
    """寫入防禦決策的節點處理器"""

    def handle(self) -> Dict[str, Any]:
        self.report_running()

        action = (self.get_config_value('action', '') or '').strip()
        target_type = (self.get_config_value('target_type', '') or '').strip()
        target_value_raw = self.get_config_value('target_value', '') or ''
        enforcement_points = self.get_config_value('enforcement_points', []) or []
        severity = self.get_config_value('severity') or None
        ttl_seconds = self.get_config_value('ttl_seconds')
        reason_template = self.get_config_value('reason_template', '') or ''

        if not action:
            self.log_error('DecisionWriter 未設定 action')
            return {'status': 'error', 'message': '未設定 action'}
        if not target_type:
            self.log_error('DecisionWriter 未設定 target_type')
            return {'status': 'error', 'message': '未設定 target_type'}

        # 變數替換 - target_value / reason 通常引用表單欄位
        target_value = self.replace_variables(target_value_raw)
        if not target_value or not target_value.strip():
            self.log_error('DecisionWriter target_value 替換後為空', {
                'template': target_value_raw,
            })
            return {
                'status': 'error',
                'message': f'target_value 替換失敗或為空: {target_value_raw!r}',
            }

        reason = self.replace_variables(reason_template) if reason_template else None

        # ttl_seconds 容錯
        ttl_int = None
        if ttl_seconds not in (None, '', 0, '0'):
            try:
                ttl_int = int(ttl_seconds)
                if ttl_int <= 0:
                    ttl_int = None
            except (TypeError, ValueError):
                self.log_error('ttl_seconds 不可解析為整數', {'value': ttl_seconds})
                return {'status': 'error', 'message': f'ttl_seconds 不合法: {ttl_seconds!r}'}

        # enforcement_points 標準化
        if isinstance(enforcement_points, str):
            enforcement_points = [
                ep.strip() for ep in enforcement_points.split(',') if ep.strip()
            ]
        if not isinstance(enforcement_points, list):
            enforcement_points = []

        # 嚴格從 queue_item 取 org_secure_code,禁止從 form 欄位推斷
        org_secure_code = self.queue_item.org_secure_code
        if not org_secure_code:
            self.log_error('queue_item 缺 org_secure_code,拒絕寫決策')
            return {'status': 'error', 'message': 'queue_item 缺 org_secure_code'}

        decided_via = self._infer_decided_via()
        decided_by = self._infer_decided_by()

        try:
            from modules.open_defense.services.decision_service import (
                create_decision, DecisionValidationError,
            )
        except Exception as exc:
            self.log_error(f'載入 decision_service 失敗: {exc}')
            return {'status': 'error', 'message': '無法載入 decision_service'}

        try:
            decision = create_decision(
                org_secure_code=org_secure_code,
                action=action,
                target_type=target_type,
                target_value=target_value,
                decided_via=decided_via,
                decided_by_secure_code=decided_by,
                enforcement_points=enforcement_points,
                severity=severity,
                ttl_seconds=ttl_int,
                reason=reason,
                case_secure_code=self.queue_item.workflow_instance_secure_code,
                workflow_node_id=self.queue_item.node_id,
                intake_event_secure_code=self._lookup_source_event(),
                commit=True,
            )
        except DecisionValidationError as exc:
            self.log_error(f'DecisionWriter 驗證失敗: {exc}')
            return {'status': 'error', 'message': str(exc)}
        except Exception as exc:
            logger.exception('DecisionWriter 寫入失敗')
            self.log_error(f'DecisionWriter 寫入失敗: {exc}')
            return {'status': 'error', 'message': f'寫入失敗: {exc}'}

        self.log_info('DecisionWriter 已寫入決策', {
            'decision_secure_code': decision.secure_code,
            'action': action,
            'target_type': target_type,
            'target_value': target_value,
            'enforcement_points': enforcement_points,
            'ttl_seconds': ttl_int,
        })

        return {
            'status': 'success',
            'message': f'決策已寫入: {action} {target_type}={target_value}',
            'data': {
                'decision_secure_code': decision.secure_code,
                'action': action,
                'target_type': target_type,
                'target_value': target_value,
                'enforcement_points': enforcement_points,
                'ttl_seconds': ttl_int,
                'expires_at': decision.expires_at.isoformat() if decision.expires_at else None,
            },
        }

    # ------------------------------------------------------------------
    # 內部輔助
    # ------------------------------------------------------------------
    def _infer_decided_via(self) -> str:
        """
        推斷此決策的決策來源:
        - human:節點配置明確標註 decided_via='human',或工作流上一個節點是 FormAdapter(人簽)
        - ai:節點配置明確標註 decided_via='ai'
        - auto:其餘(自動分支判斷後直達此節點)
        """
        explicit = self.get_config_value('decided_via')
        if explicit in ('human', 'auto', 'ai'):
            return explicit

        # 簡化推斷:檢查 workflow instance 上一個完成的節點
        # 若為 FormAdapter,視為 human;否則 auto
        try:
            wi = self.workflow_instance
            if wi and getattr(wi, 'last_completed_node_type', None) == 'FormAdapter':
                return 'human'
        except Exception:
            pass
        return 'auto'

    def _infer_decided_by(self):
        """若 decided_via=human,嘗試取最後簽核者 secure_code;否則 None"""
        try:
            fi = self.form_instance
            if fi:
                last_approver = getattr(fi, 'last_approver_secure_code', None)
                if last_approver:
                    return last_approver
        except Exception:
            pass
        return None

    def _lookup_source_event(self):
        """
        從 form_instance 中找對應的 OdIntakeEvent.secure_code。
        OdIntakeEvent 寫入時把 case_secure_code 指向 workflow instance,
        反查時用 case_secure_code 對應即可。
        """
        try:
            from modules.open_defense.models import OdIntakeEvent
            wi_sc = self.queue_item.workflow_instance_secure_code
            if not wi_sc:
                return None
            row = OdIntakeEvent.query.filter_by(
                case_secure_code=wi_sc,
                org_secure_code=self.queue_item.org_secure_code,
                is_deleted=False,
            ).first()
            return row.secure_code if row else None
        except Exception:
            return None
