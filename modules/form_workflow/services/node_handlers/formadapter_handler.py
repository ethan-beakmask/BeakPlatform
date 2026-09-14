"""
FormWorkflow Module - FormAdapter Handler
FormAdapter 節點處理器

負責簽核流程：等待指定人員選擇後續路徑。
"""
import logging
import secrets
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from .base import BaseNodeHandler

from app import db

logger = logging.getLogger(__name__)

TIMEOUT_MODES = ('ABSOLUTE', 'WORKING')
UNIT_SCOPES = ('GLOBAL', 'UNIT', 'APPLICANT_UNIT', 'APPLICANT_ANCESTOR')
SELF_TARGET_ACTIONS = ('escalate_or_return', 'escalate_or_self', 'self')
TIMEOUT_MAX_MINUTES = 14400          # 10 天，與 ParallelJoin 一致
TIMEOUT_ACTION = 'timeout'           # fw_approval_records.action（機器碼，不翻譯）
TIMEOUT_APPROVER_NAME = '系統（逾時自動處理）'
NO_ASSIGNEE_ACTION = 'no_assignee'   # fw_approval_records.action（機器碼，不翻譯）
NO_ASSIGNEE_APPROVER_NAME = '系統（找不到簽核人）'


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat(timespec='seconds')


def _parse_iso(value) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)).replace(tzinfo=None)
    except ValueError:
        return None


def compute_timeout_deadline(user, now_utc: datetime, minutes: int, mode: str, tz_name: str):
    """回 (效果模式, 期限 naive UTC)。

    WORKING：只在簽核者班表內倒數（`ScheduleService.estimate_working_end_time()`，已含時段級請假）；
    `user` 為 None 或沒有班表 → 退回 ABSOLUTE（2026-09-03 Q4 定案，否則 `calculate_working_seconds()` 恆 0 永不逾時）。
    schedule_service 吃 naive 當地時間、queue 存 UTC，換算只走 calendar_time。
    """
    from app.services.schedule_service import ScheduleService
    from app.utils.calendar_time import local_naive_to_utc, utc_to_local

    seconds = int(minutes) * 60
    if mode == 'WORKING' and user is not None and ScheduleService.get_user_schedule(user) is not None:
        local_now = utc_to_local(tz_name, now_utc).replace(tzinfo=None)
        local_end = ScheduleService.estimate_working_end_time(user, local_now, seconds)
        deadline = local_naive_to_utc(tz_name, local_end)
        if deadline > now_utc:
            return 'WORKING', deadline
    return 'ABSOLUTE', now_utc + timedelta(seconds=seconds)


def recompute_working_deadline(user, started_utc: datetime, now_utc: datetime, minutes: int, tz_name: str):
    """WORKING 模式被喚醒時重算：回 (剩餘工作秒數, 新期限 naive UTC 或 None)。

    剩餘 <= 0 表示真的逾時；> 0 表示班表／請假在等待期間變了（例如中途請假），往後推再等。
    """
    from app.services.schedule_service import ScheduleService
    from app.utils.calendar_time import local_naive_to_utc, utc_to_local

    local_started = utc_to_local(tz_name, started_utc).replace(tzinfo=None)
    local_now = utc_to_local(tz_name, now_utc).replace(tzinfo=None)
    elapsed = ScheduleService.calculate_working_seconds(user, local_started, local_now)
    remaining = int(minutes) * 60 - int(elapsed)
    if remaining <= 0:
        return remaining, None
    local_end = ScheduleService.estimate_working_end_time(user, local_now, remaining)
    deadline = local_naive_to_utc(tz_name, local_end)
    if deadline <= now_utc:
        deadline = now_utc + timedelta(seconds=60)
    return remaining, deadline


class FormAdapterHandler(BaseNodeHandler):
    """FormAdapter 簽核節點處理器"""

    def validate(self) -> bool:
        """
        驗證節點配置

        必要配置：
        - assignee_type: 簽核者類型 (ROLE/USER/DEPARTMENT/INITIATOR/DYNAMIC)
        - selection_mode: 選擇模式 (single/multiple)

        Returns:
            bool: 是否通過驗證
        """
        assignee_type = self.get_config_value('assignee_type')
        if not assignee_type:
            # 預設為 INITIATOR（發起人自己簽核）
            self.node_config['assignee_type'] = 'INITIATOR'

        selection_mode = self.get_config_value('selection_mode')
        if selection_mode not in [None, 'single', 'multiple']:
            raise ValueError(f'selection_mode 必須是 single 或 multiple，而非 {selection_mode}')

        if not selection_mode:
            self.node_config['selection_mode'] = 'single'

        if self.get_config_value('timeout_enabled', False):
            try:
                minutes = int(self.get_config_value('timeout_minutes', 0) or 0)
            except (TypeError, ValueError):
                raise ValueError('timeout_minutes 必須是整數')
            if minutes <= 0 or minutes > TIMEOUT_MAX_MINUTES:
                raise ValueError(f'timeout_minutes 必須介於 1 與 {TIMEOUT_MAX_MINUTES}，而非 {minutes}')
            mode = str(self.get_config_value('timeout_mode', 'ABSOLUTE') or 'ABSOLUTE').upper()
            if mode not in TIMEOUT_MODES:
                raise ValueError(f'timeout_mode 必須是 ABSOLUTE 或 WORKING，而非 {mode}')
            self.node_config['timeout_mode'] = mode
            if not str(self.get_config_value('timeout_path_id', '') or '').strip():
                raise ValueError('啟用簽核逾時時必須指定逾時去向 (timeout_path_id)')

        no_assignee_action = self.get_config_value('no_assignee_action', 'return')
        if no_assignee_action not in ('return', 'fallback_role'):
            no_assignee_action = 'return'
        self.node_config['no_assignee_action'] = no_assignee_action
        if no_assignee_action == 'fallback_role':
            role_sc = str(self.get_config_value('no_assignee_role_secure_code', '') or '').strip()
            if not role_sc:
                raise ValueError('改派給角色時必須指定角色 (no_assignee_role_secure_code)')

        assignee_type = self.get_config_value('assignee_type')
        if assignee_type == 'ROLE':
            raw_scope = self.get_config_value('unit_scope', 'GLOBAL')
            unit_scope = str(raw_scope or 'GLOBAL').strip().upper()
            if unit_scope not in UNIT_SCOPES:
                raise ValueError(f'unit_scope 必須是 GLOBAL、UNIT、APPLICANT_UNIT 或 APPLICANT_ANCESTOR，而非 {unit_scope}')
            self.node_config['unit_scope'] = unit_scope

            if unit_scope == 'UNIT':
                unit_sc = str(self.get_config_value('unit_secure_code', '') or '').strip()
                if not unit_sc:
                    raise ValueError('單位範圍為指定單位時必須指定單位 (unit_secure_code)')
                self.node_config['unit_secure_code'] = unit_sc

            if unit_scope == 'APPLICANT_ANCESTOR':
                raw_levels = self.get_config_value('unit_levels_up', 1)
                try:
                    levels = int(raw_levels)
                except (TypeError, ValueError):
                    raise ValueError('unit_levels_up 必須是整數')
                if levels < 1:
                    raise ValueError(f'unit_levels_up 必須 >= 1，而非 {levels}')
                self.node_config['unit_levels_up'] = levels

            raw_self_target_action = self.get_config_value('self_target_action', 'escalate_or_return')
            self_target_action = str(raw_self_target_action or 'escalate_or_return').strip().lower()
            if self_target_action not in SELF_TARGET_ACTIONS:
                raise ValueError(
                    f'self_target_action 必須是 escalate_or_return、escalate_or_self 或 self，而非 {raw_self_target_action}'
                )
            self.node_config['self_target_action'] = self_target_action

        return True

    def handle(self) -> Dict[str, Any]:
        """
        處理 FormAdapter 節點

        1. 讀取此節點的所有出線
        2. 產生可選路徑列表（支援自定義決策選項）
        3. 評估來向變數控制（input_variables）
        4. 設定狀態為等待簽核
        5. 等待簽核者透過 API 提交選擇

        Returns:
            dict: 執行結果
        """
        self.report_running()

        # 逾時喚醒（executor 依 result.data.timeout_at 把 WAITING 設回 PENDING 重跑本 handler）：
        # 不重新解析簽核者、不重設 waiting_since，只判斷是不是真的逾時
        existing = ((self.queue_item.result or {}).get('data') or {})
        if existing.get('timeout_at'):
            return self._handle_timeout_reentry(existing)

        # 取得配置
        assignee_type = self.get_config_value('assignee_type', 'INITIATOR')
        assignee_value = self.get_config_value('assignee_value', '')
        selection_mode = self.get_config_value('selection_mode', 'single')
        allow_comment = self.get_config_value('allow_comment', True)
        require_comment = self.get_config_value('require_comment', False)
        min_comment_length = int(self.get_config_value('min_comment_length', 0))
        use_custom_decisions = self.get_config_value('use_custom_decisions', False)
        output_variable = self.get_config_value('output_variable', '')

        # 根據模式取得決策選項
        if use_custom_decisions:
            available_paths = self._get_custom_decision_options()
        else:
            available_paths = self._get_available_paths()

        if not available_paths:
            self.log_error('FormAdapter 節點沒有出線，無法繼續')
            return {
                'status': 'error',
                'message': 'FormAdapter 節點沒有出線'
            }

        # 評估來向變數控制
        input_variable_results = self._resolve_input_variables()

        data = {
            'assignee_type': assignee_type,
            'assignee_value': assignee_value,
            'selection_mode': selection_mode,
            'allow_comment': allow_comment,
            'require_comment': require_comment,
            'min_comment_length': min_comment_length,
            'use_custom_decisions': use_custom_decisions,
            'output_variable': output_variable,
            'available_paths': available_paths,
            'input_variable_results': input_variable_results,
            'waiting_since': datetime.utcnow().isoformat()
        }

        if assignee_type in ('ROLE', 'DEPARTMENT'):
            spec_data, failure_reason = self._resolve_assignee_spec(assignee_type, assignee_value)
            if failure_reason:
                if spec_data:
                    data.update(spec_data)
                data['assignees'] = []
                no_assignee_result = self._handle_no_assignee(data, reason=failure_reason)
                if no_assignee_result:
                    return no_assignee_result
            else:
                data.update(spec_data)
        else:
            data['assignees'] = self._resolve_assignees(assignee_type, assignee_value)

        assignees = data['assignees']
        if assignees == [] and assignee_type not in ('ROLE', 'DEPARTMENT'):
            no_assignee_result = self._handle_no_assignee(data)
            if no_assignee_result:
                return no_assignee_result
            assignees = data['assignees']

        timeout_info = self._build_timeout_info(assignees, available_paths)
        if timeout_info:
            data.update(timeout_info)
            self.log_info('簽核逾時倒數開始', {
                k: timeout_info[k] for k in ('timeout_mode', 'timeout_mode_effective', 'timeout_minutes',
                                             'timeout_at', 'timeout_path_id', 'timeout_reference_user')
            })

        self.log_info('FormAdapter 節點等待簽核', {
            'node_id': self.queue_item.node_id,
            'assignee_type': data['assignee_type'],
            'assignee_value': data['assignee_value'],
            'assignees': data['assignees'],
            'selection_mode': selection_mode,
            'use_custom_decisions': use_custom_decisions,
            'available_paths': available_paths
        })

        # 返回等待簽核狀態
        return {
            'status': 'waiting_form_action',
            'message': '等待簽核',
            'data': data
        }

    # ------------------------------------------------------------------
    # 簽核逾時（PF-229 第三期第 2 項）
    # ------------------------------------------------------------------

    def _no_assignee_reason(self, assignee_type: str, assignee_value: str) -> str:
        if assignee_type == 'DYNAMIC':
            return f'變數 {assignee_value} 為空'
        if assignee_type == 'USER':
            return '指定用戶為空'
        if assignee_type == 'INITIATOR':
            return '表單沒有申請人'
        return f'{assignee_type} 簽核者為空'

    def _no_assignee_return_result(self, data: Dict[str, Any], reason: str) -> Dict[str, Any]:
        comment = f'找不到簽核人（{reason}），退回申請人重送'
        self._write_system_record(NO_ASSIGNEE_ACTION, NO_ASSIGNEE_APPROVER_NAME, comment)
        self.log_error('FormAdapter 簽核者解析為空，退回申請人重送', {
            'assignee_type': data.get('assignee_type'),
            'assignee_value': data.get('assignee_value'),
            'reason': reason,
        })
        return {
            'status': 'complete_workflow',
            'message': comment,
            'data': {
                **data,
                'decision': NO_ASSIGNEE_ACTION,
                'no_assignee': True,
                'no_assignee_reason': reason,
                'workflow_status': 'REJECTED',
                'finish_mode': 'detach',
            },
        }

    def _handle_no_assignee(self, data: Dict[str, Any], reason: str | None = None) -> Optional[Dict[str, Any]]:
        assignee_type = data.get('assignee_type')
        assignee_value = data.get('assignee_value') or ''
        if reason is None:
            reason = self._no_assignee_reason(assignee_type, assignee_value)
        action = self.get_config_value('no_assignee_action', 'return')
        if action != 'fallback_role':
            return self._no_assignee_return_result(data, reason)

        role_sc = str(self.get_config_value('no_assignee_role_secure_code', '') or '').strip()
        from app.models.role import Role
        role = Role.query.filter(
            Role.secure_code == role_sc,
            Role.org_secure_code == self.queue_item.org_secure_code,
            Role.is_deleted == False,  # noqa: E712
            Role.is_active == True,  # noqa: E712
        ).first()
        if role is None:
            self.log_error('FormAdapter 改派角色不存在或不可用', {
                'no_assignee_role_secure_code': role_sc,
                'reason': reason,
            })
            return self._no_assignee_return_result(data, reason)

        data.update(self._role_spec_data(role, None, 'GLOBAL'))
        data.update({
            'no_assignee_fallback_applied': True,
            'original_assignee_type': assignee_type,
            'original_assignee_value': assignee_value,
            'no_assignee_reason': reason,
        })
        self.log_warning('FormAdapter 簽核者解析為空，改派給角色', {
            'original_assignee_type': assignee_type,
            'original_assignee_value': assignee_value,
            'no_assignee_role_secure_code': role_sc,
            'assignees': data['assignees'],
            'reason': reason,
        })
        return None

    def _role_by_secure_code(self, role_sc: str):
        from app.models.role import Role
        return Role.query.filter(
            Role.secure_code == role_sc,
            Role.org_secure_code == self.queue_item.org_secure_code,
            Role.is_deleted == False,  # noqa: E712
        ).first()

    def _active_role_by_code(self, code: str):
        from app.models.role import Role
        return Role.query.filter(
            Role.code == code,
            Role.org_secure_code == self.queue_item.org_secure_code,
            Role.is_deleted == False,  # noqa: E712
            Role.is_active == True,  # noqa: E712
        ).first()

    def _role_spec_data(self, role, unit, unit_scope: str) -> Dict[str, Any]:
        from app.services.role_holding_service import effective_holders

        org_sc = self.queue_item.org_secure_code
        role_sc = role.secure_code
        unit_sc = unit.secure_code if unit else None
        local_now = self._local_now()
        assignees = effective_holders(
            role.secure_code,
            org_sc,
            unit_sc,
            include_descendant_units=unit is not None,
            today=local_now.date(),
            local_now=local_now,
        )

        return {
            'assignee_type': 'ROLE',
            'assignee_value': role_sc,
            'assignee_role_code': role.code,
            'assignee_role_name': role.name,
            'assignee_role_type': role.role_type,
            'assignee_unit_scope': unit_scope,
            'assignee_unit_secure_code': unit_sc,
            'assignee_unit_name': unit.name if unit else None,
            'assignees': assignees,
        }

    @staticmethod
    def _dedupe_preserve_order(values: List[str]) -> List[str]:
        result = []
        seen = set()
        for value in values:
            if value in seen:
                continue
            seen.add(value)
            result.append(value)
        return result

    def _local_now(self) -> datetime:
        from app.utils.calendar_time import utc_to_local

        return utc_to_local(self._org_tz_name(), datetime.utcnow()).replace(tzinfo=None)

    def _resolve_applicant_unit(self):
        from app.services.unit_resolver import get_unit, resolve_user_unit

        if not self.form_instance or not self.form_instance.applicant_secure_code:
            return None, '表單沒有申請人'
        org_sc = self.queue_item.org_secure_code
        unit_sc = resolve_user_unit(self.form_instance.applicant_secure_code, org_sc)
        if not unit_sc:
            return None, '申請人沒有所屬單位'
        unit = get_unit(unit_sc, org_sc)
        if not unit:
            return None, f'單位 {unit_sc} 不存在或已刪除'
        return unit, None

    def _resolve_role_unit(self, unit_scope: str):
        from app.services.unit_resolver import get_unit, get_unit_ancestor_codes

        org_sc = self.queue_item.org_secure_code
        if unit_scope == 'GLOBAL':
            return None, None
        if unit_scope == 'UNIT':
            unit_sc = str(self.get_config_value('unit_secure_code', '') or '').strip()
            unit = get_unit(unit_sc, org_sc)
            if not unit:
                return None, f'單位 {unit_sc} 不存在或已刪除'
            return unit, None
        if unit_scope == 'APPLICANT_UNIT':
            return self._resolve_applicant_unit()
        if unit_scope != 'APPLICANT_ANCESTOR':
            return None, f'unit_scope 必須是 GLOBAL、UNIT、APPLICANT_UNIT 或 APPLICANT_ANCESTOR，而非 {unit_scope}'

        applicant_unit, failure = self._resolve_applicant_unit()
        if failure:
            return None, failure
        ancestors = get_unit_ancestor_codes(applicant_unit.secure_code, org_sc)
        if not ancestors:
            return applicant_unit, None
        levels = int(self.get_config_value('unit_levels_up', 1) or 1)
        target_sc = ancestors[min(levels, len(ancestors)) - 1]
        unit = get_unit(target_sc, org_sc)
        if not unit:
            return None, f'單位 {target_sc} 不存在或已刪除'
        return unit, None

    def _resolve_assignee_spec(self, assignee_type: str, assignee_value: str) -> tuple[Dict[str, Any], str | None]:
        from app.services.unit_resolver import get_unit

        org_sc = self.queue_item.org_secure_code
        if assignee_type == 'DEPARTMENT':
            role = self._active_role_by_code('DEPT_MEMBER')
            if role is None:
                return {}, '企業沒有部門成員角色（DEPT_MEMBER）'
            unit = get_unit(assignee_value, org_sc)
            if unit is None:
                return {}, f'部門 {assignee_value} 不存在或已刪除'
            data = self._role_spec_data(role, unit, 'DEPARTMENT')
            data.update({
                'original_assignee_type': 'DEPARTMENT',
                'original_assignee_value': assignee_value,
            })
            return data, None

        role_sc = str(assignee_value or '').strip()
        if not role_sc:
            return {}, '未指定角色'
        role = self._role_by_secure_code(role_sc)
        if role is None:
            return {}, f'角色 {role_sc} 不存在或已刪除'
        unit_scope = str(self.get_config_value('unit_scope', 'GLOBAL') or 'GLOBAL').strip().upper()
        unit, failure = self._resolve_role_unit(unit_scope)
        if failure:
            return {}, failure
        data = self._role_spec_data(role, unit, unit_scope)
        if unit_scope in ('APPLICANT_UNIT', 'APPLICANT_ANCESTOR'):
            return self._apply_self_target(data, unit, unit_scope, role)
        return data, None

    def _normalized_self_target_action(self) -> str:
        value = str(self.get_config_value('self_target_action', 'escalate_or_return') or 'escalate_or_return').strip().lower()
        if value not in SELF_TARGET_ACTIONS:
            return 'escalate_or_return'
        return value

    def _apply_self_target(self, spec_data: Dict[str, Any], unit, unit_scope: str,
                           role) -> tuple[Dict[str, Any], str | None]:
        from app.models.role import RoleType
        from app.services.unit_resolver import get_unit, get_unit_ancestor_codes

        action = self._normalized_self_target_action()
        spec_data['self_target_action'] = action
        spec_data['self_target_escalated_levels'] = 0

        applicant = self.form_instance.applicant_secure_code
        if role.role_type != RoleType.POSITION or applicant not in (spec_data.get('assignees') or []):
            return spec_data, None
        if action == 'self':
            return spec_data, None

        org_sc = self.queue_item.org_secure_code
        ancestors = get_unit_ancestor_codes(unit.secure_code, org_sc) if unit else []
        for level, ancestor_sc in enumerate(ancestors, start=1):
            ancestor_unit = get_unit(ancestor_sc, org_sc)
            if not ancestor_unit:
                continue
            candidate = self._role_spec_data(role, ancestor_unit, unit_scope)
            candidate_assignees = candidate.get('assignees') or []
            if candidate_assignees and applicant not in candidate_assignees:
                candidate['self_target_action'] = action
                candidate['self_target_escalated_levels'] = level
                return candidate, None

        if action == 'escalate_or_self':
            return spec_data, None
        return spec_data, f'申請人本人為簽核者，往上 {len(ancestors)} 層仍無其他簽核人'

    def _org_tz_name(self) -> str:
        from app.models.organization import Organization
        org = Organization.query.filter_by(secure_code=self.queue_item.org_secure_code).first()
        return org.get_setting('timezone', 'Asia/Taipei') if org else 'Asia/Taipei'

    def _load_member(self, secure_code):
        from app.models.user import User
        if not secure_code:
            return None
        return User.query.filter(
            User.org_secure_code == self.queue_item.org_secure_code,
            User.secure_code == secure_code,
            User.is_deleted == False,  # noqa: E712
            User.is_active == True,  # noqa: E712
        ).first()

    def _working_reference_user(self, assignees: List[str]):
        """WORKING 模式拿哪個人的班表倒數：依簽核者順序取第一個有共用班表的人。"""
        from app.services.schedule_service import ScheduleService
        for sc in assignees or []:
            user = self._load_member(sc)
            if user is not None and ScheduleService.get_user_schedule(user) is not None:
                return user
        return None

    @staticmethod
    def _find_timeout_path(available_paths, path_id):
        for path in available_paths or []:
            if path_id and path_id in (path.get('id'), path.get('edge_id')):
                return path
        return None

    def _build_timeout_info(self, assignees: List[str], available_paths: List[Dict]) -> Optional[Dict[str, Any]]:
        if not self.get_config_value('timeout_enabled', False):
            return None
        minutes = int(self.get_config_value('timeout_minutes', 0) or 0)
        mode = str(self.get_config_value('timeout_mode', 'ABSOLUTE') or 'ABSOLUTE').upper()
        path_id = str(self.get_config_value('timeout_path_id', '') or '').strip()
        if self._find_timeout_path(available_paths, path_id) is None:
            # validate() 只能檢查有沒有填；去向存不存在要等 available_paths 算出來才知道。
            # fail-closed：不啟動一個逾時後走不出去的倒數，但也不擋簽核本身
            self.log_error('逾時去向不在可選路徑內，本關卡不啟用逾時', {'timeout_path_id': path_id})
            return None
        now = datetime.utcnow().replace(microsecond=0)
        tz_name = self._org_tz_name()
        ref_user = self._working_reference_user(assignees) if mode == 'WORKING' else None
        effective, deadline = compute_timeout_deadline(ref_user, now, minutes, mode, tz_name)
        return {
            'timeout_enabled': True,
            'timeout_minutes': minutes,
            'timeout_mode': mode,
            'timeout_mode_effective': effective,
            'timeout_reference_user': ref_user.secure_code if ref_user else None,
            'timeout_path_id': path_id,
            'timeout_started_at': _iso(now),
            'timeout_at': _iso(deadline),
        }

    def _handle_timeout_reentry(self, data: Dict[str, Any]) -> Dict[str, Any]:
        now = datetime.utcnow().replace(microsecond=0)
        timeout_at = _parse_iso(data.get('timeout_at'))
        if timeout_at is None or now < timeout_at:
            self.log_info('簽核節點被喚醒但尚未逾時，繼續等待', {'timeout_at': data.get('timeout_at')})
            return {'status': 'waiting_form_action', 'message': '等待簽核', 'data': data}

        minutes = int(data.get('timeout_minutes') or 0)
        if data.get('timeout_mode_effective') == 'WORKING':
            ref_user = self._load_member(data.get('timeout_reference_user'))
            started = _parse_iso(data.get('timeout_started_at'))
            if ref_user is not None and started is not None:
                remaining, new_deadline = recompute_working_deadline(
                    ref_user, started, now, minutes, self._org_tz_name())
                if remaining > 0 and new_deadline is not None:
                    self.log_info('工作時間逾時重算：仍有剩餘工作秒數，往後推', {
                        'remaining_seconds': remaining, 'timeout_at': _iso(new_deadline)})
                    return {
                        'status': 'waiting_form_action',
                        'message': '等待簽核',
                        'data': {**data, 'timeout_at': _iso(new_deadline), 'timeout_recomputed_at': _iso(now)},
                    }

        path = self._find_timeout_path(data.get('available_paths'), data.get('timeout_path_id'))
        if path is None:
            self.log_error('簽核逾時，但逾時去向不存在', {'timeout_path_id': data.get('timeout_path_id')})
            return {'status': 'error', 'message': '簽核逾時，但逾時去向不存在'}

        label = path.get('label') or path.get('id') or path.get('edge_id') or ''
        target_edges = list(path.get('target_edges') or [])
        if not target_edges and path.get('edge_id'):
            target_edges = [path['edge_id']]
        mode_label = '工作時間' if data.get('timeout_mode_effective') == 'WORKING' else '絕對時間'
        comment = f'簽核逾時（{mode_label} {minutes} 分鐘），系統自動採用「{label}」'

        self._write_system_record(TIMEOUT_ACTION, TIMEOUT_APPROVER_NAME, comment)

        output_variable = data.get('output_variable')
        if output_variable and path.get('value') is not None:
            self.set_flow_var(output_variable, path.get('value'))

        base = {
            **data,
            'decision': TIMEOUT_ACTION,
            'timed_out': True,
            'timeout_triggered_at': _iso(now),
            'timeout_path_label': label,
            'selected_option_value': path.get('value'),
        }
        self.log_info('簽核逾時，自動採用逾時去向', {
            'timeout_path_id': data.get('timeout_path_id'), 'label': label, 'target_edges': target_edges})

        if not target_edges:
            # 未配對出線的決策＝REJECTED 終態（與人工簽核「駁回」同一語意）
            return {
                'status': 'complete_workflow',
                'message': comment,
                'data': {**base, 'workflow_status': 'REJECTED', 'finish_mode': 'detach'},
            }
        return {
            'status': 'success',
            'message': comment,
            'data': {**base, 'selected_edges': target_edges},
        }

    def _write_system_record(self, action: str, approver_name: str, comment: str) -> None:
        from ...models import FwApprovalRecord
        db.session.add(FwApprovalRecord(
            secure_code=secrets.token_urlsafe(16),
            org_secure_code=self.queue_item.org_secure_code,
            workflow_instance_secure_code=self.queue_item.workflow_instance_secure_code,
            form_instance_secure_code=self.queue_item.form_instance_secure_code or '',
            node_id=self.queue_item.node_id,
            node_name=self.queue_item.node_name,
            node_queue_secure_code=self.queue_item.secure_code,
            approver_secure_code=None,
            approver_name=approver_name,
            action=action,
            comment=comment,
            acted_at=datetime.utcnow(),
        ))

    def _get_custom_decision_options(self) -> List[Dict[str, Any]]:
        """
        從 config.decision_options 產生自定義決策選項列表

        Returns:
            list: 決策選項列表，每個選項包含 id, label, value, target_edges, style, visible_when
        """
        decision_options = self.get_config_value('decision_options', [])
        if not decision_options:
            return []

        # 取得合法 edge IDs 用於驗證
        graph = self._get_workflow_graph()
        valid_edge_ids = set()
        if graph:
            edges = graph.get('edges', [])
            current_node_id = self.queue_item.node_id
            for edge in edges:
                edge_data = edge.get('data', edge)
                if edge_data.get('source') == current_node_id:
                    eid = edge_data.get('id', edge.get('id'))
                    if eid:
                        valid_edge_ids.add(eid)

        result = []
        for opt in decision_options:
            opt_id = opt.get('id', '')
            target_edges = opt.get('target_edges', [])

            # 驗證 target_edges 合法性（空 target_edges 表示終態）
            validated_edges = []
            for eid in target_edges:
                if eid in valid_edge_ids:
                    validated_edges.append(eid)
                else:
                    self.log_warning(f'決策選項 {opt_id} 引用了無效的 edge: {eid}')

            result.append({
                'id': opt_id,
                'label': opt.get('label', ''),
                'value': opt.get('value', ''),
                'target_edges': validated_edges,
                'style': opt.get('style', 'default'),
                'visible_when': opt.get('visible_when')
            })

        return result

    def _resolve_input_variables(self) -> Dict[str, Any]:
        """
        評估 config.input_variables 中定義的來向變數控制規則

        Returns:
            dict: 評估結果
            {
                'hidden_option_ids': ['opt-uuid1', ...],    # 應隱藏的決策選項 ID
                'field_permission_overrides': {              # 動態欄位權限覆蓋
                    'amount': 'editable',
                    'reason': 'hidden'
                }
            }
        """
        input_variables = self.get_config_value('input_variables', [])
        if not input_variables:
            return {}

        hidden_option_ids = set()
        visible_option_ids = set()
        field_permission_overrides = {}
        has_visibility_rules = False

        for var_def in input_variables:
            var_name = var_def.get('var_name', '')
            if not var_name:
                continue

            actual_value = self.get_var(var_name, '')
            controls = var_def.get('controls', [])

            for ctrl in controls:
                ctrl_type = ctrl.get('type', '')
                condition = ctrl.get('condition', {})

                # 評估條件
                if not self._evaluate_input_condition(actual_value, condition):
                    continue

                if ctrl_type == 'decision_visibility':
                    has_visibility_rules = True
                    target_ids = ctrl.get('target_option_ids', [])
                    visible_option_ids.update(target_ids)

                elif ctrl_type == 'field_permission':
                    field_key = ctrl.get('field_key', '')
                    permission = ctrl.get('permission', 'readonly')
                    if field_key:
                        field_permission_overrides[field_key] = permission

        result = {}

        # 計算 hidden_option_ids：如果有 visibility 規則，不在 visible 集合中的都隱藏
        if has_visibility_rules:
            all_option_ids = set()
            decision_options = self.get_config_value('decision_options', [])
            for opt in decision_options:
                all_option_ids.add(opt.get('id', ''))
            hidden_option_ids = all_option_ids - visible_option_ids
            result['hidden_option_ids'] = list(hidden_option_ids)

        if field_permission_overrides:
            result['field_permission_overrides'] = field_permission_overrides

        return result

    @staticmethod
    def _evaluate_input_condition(actual_value: Any, condition: Dict) -> bool:
        """
        評估單一條件

        Args:
            actual_value: 實際變數值
            condition: {'operator': '==', 'value': 'high'}

        Returns:
            bool: 條件是否成立
        """
        operator = condition.get('operator', '==')
        expected = condition.get('value', '')

        try:
            actual_str = str(actual_value) if actual_value is not None else ''
            expected_str = str(expected)

            if operator == '==':
                return actual_str == expected_str
            elif operator == '!=':
                return actual_str != expected_str
            elif operator == '>':
                return float(actual_str) > float(expected_str)
            elif operator == '>=':
                return float(actual_str) >= float(expected_str)
            elif operator == '<':
                return float(actual_str) < float(expected_str)
            elif operator == '<=':
                return float(actual_str) <= float(expected_str)
            elif operator == 'contains':
                return expected_str in actual_str
            elif operator == 'not_empty':
                return actual_str.strip() != ''
            elif operator == 'empty':
                return actual_str.strip() == ''
            else:
                return False
        except (ValueError, TypeError):
            return False

    def _get_available_paths(self) -> List[Dict[str, Any]]:
        """
        取得此節點的所有出線選項

        Returns:
            list: 可選路徑列表
        """
        if not self.workflow_instance:
            return []

        # 取得流程定義
        graph = self._get_workflow_graph()
        if not graph:
            return []

        edges = graph.get('edges', [])
        nodes = graph.get('nodes', [])

        # 建立 node id -> node data 的映射
        node_map = {}
        for node in nodes:
            node_id = node.get('id')
            if node_id:
                node_map[node_id] = node

        # 找出從此節點出發的所有 edge
        current_node_id = self.queue_item.node_id
        available_paths = []

        for edge in edges:
            edge_data = edge.get('data', edge)
            source = edge_data.get('source')

            if source == current_node_id:
                target_node_id = edge_data.get('target')
                edge_id = edge_data.get('id', edge.get('id'))
                edge_label = edge_data.get('label', edge.get('label', ''))

                # 取得目標節點資訊
                target_node = node_map.get(target_node_id, {})
                target_node_type = target_node.get('type', 'UNKNOWN')
                target_node_label = target_node.get('label', target_node_type)

                # 決定顯示名稱：優先用 edge label，否則用目標節點 label
                display_label = edge_label if edge_label else target_node_label

                available_paths.append({
                    'edge_id': edge_id,
                    'target_node_id': target_node_id,
                    'target_node_type': target_node_type,
                    'target_node_label': target_node_label,
                    'label': display_label
                })

        return available_paths

    def _get_workflow_graph(self) -> Dict:
        """取得工作流圖形定義（快照優先，設計圖 fallback）"""
        if not self.workflow_instance:
            return {}
        from ..workflow_engine import WorkflowEngine
        return WorkflowEngine.get_effective_graph(self.workflow_instance)

    def _resolve_assignees(self, assignee_type: str, assignee_value: str) -> List[str]:
        """
        解析簽核者

        Args:
            assignee_type: 簽核者類型
            assignee_value: 簽核者值

        Returns:
            list: 簽核者 ID 列表
        """
        if assignee_type == 'INITIATOR':
            # 表單發起人
            if self.form_instance and self.form_instance.applicant_secure_code:
                return [self.form_instance.applicant_secure_code]
            return []

        elif assignee_type == 'USER':
            # 指定用戶（支援多用戶，以逗號分隔）
            if assignee_value:
                return [v.strip() for v in assignee_value.split(',') if v.strip()]
            return []

        elif assignee_type == 'DYNAMIC':
            # 從變數取得
            if assignee_value:
                value = self.get_var(assignee_value)
                if value:
                    if isinstance(value, list):
                        return [str(v) for v in value]
                    return [str(value)]
            return []

        return []


def complete_form_action(queue_item_secure_code: str, selected_edges: List[str],
                         user_secure_code: str, comment: str = None) -> Dict[str, Any]:
    """
    完成 FormAdapter 簽核動作

    此函數由簽核 API 呼叫，用於：
    1. 驗證用戶權限
    2. 記錄簽核結果
    3. 更新節點狀態為 SUCCESS
    4. 根據選擇的路徑建立後續節點

    Args:
        queue_item_secure_code: FwNodeExecutionQueue secure_code
        selected_edges: 選擇的 edge ID 列表
        user_secure_code: 簽核者 secure_code
        comment: 簽核備註

    Returns:
        dict: 執行結果
    """
    from ...models import FwNodeExecutionQueue, FwWorkflowInstance
    from ..workflow_log_service import WorkflowLogService

    # 取得 queue_item
    queue_item = FwNodeExecutionQueue.query.filter_by(
        secure_code=queue_item_secure_code
    ).first()

    if not queue_item:
        return {'success': False, 'error': '找不到簽核項目'}

    if queue_item.node_type != 'FormAdapter':
        return {'success': False, 'error': '此節點不是 FormAdapter 類型'}

    # 檢查狀態
    if queue_item.status == 'SUCCESS':
        return {'success': False, 'error': '此節點已完成簽核'}

    # 取得之前儲存的可選路徑
    result_data = queue_item.result or {}
    available_paths = result_data.get('data', {}).get('available_paths', [])
    selection_mode = result_data.get('data', {}).get('selection_mode', 'single')

    # 驗證選擇的 edge 是否有效
    valid_edge_ids = [p['edge_id'] for p in available_paths]
    for edge_id in selected_edges:
        if edge_id not in valid_edge_ids:
            return {'success': False, 'error': f'無效的選擇: {edge_id}'}

    # 單選模式只能選一個
    if selection_mode == 'single' and len(selected_edges) != 1:
        return {'success': False, 'error': '單選模式只能選擇一個選項'}

    # 複選模式至少選一個
    if selection_mode == 'multiple' and len(selected_edges) < 1:
        return {'success': False, 'error': '請至少選擇一個選項'}

    # 記錄簽核結果
    action_result = {
        'selected_edges': selected_edges,
        'selected_by': user_secure_code,
        'selected_at': datetime.utcnow().isoformat(),
        'comment': comment,
        'selection_mode': selection_mode
    }

    # 更新狀態
    queue_item.status = 'SUCCESS'
    queue_item.completed_at = datetime.utcnow()
    queue_item.result = {
        'status': 'success',
        'message': '簽核完成',
        'data': {
            **result_data.get('data', {}),
            'action_result': action_result
        }
    }

    db.session.commit()

    # 記錄日誌
    workflow_instance = FwWorkflowInstance.query.filter_by(
        secure_code=queue_item.workflow_instance_secure_code
    ).first()

    WorkflowLogService.log(
        workflow_instance_id=workflow_instance.id if workflow_instance else None,
        node_queue_id=queue_item.id,
        node_type=queue_item.node_type,
        node_instance_id=queue_item.secure_code,
        org_secure_code=queue_item.org_secure_code,
        status=queue_item.status,
        level='INFO',
        message='FormAdapter 簽核完成',
        data=action_result
    )

    # 建立選擇的後續節點
    _create_next_nodes(queue_item, selected_edges, available_paths)

    return {'success': True, 'message': '簽核完成'}


def _create_next_nodes(queue_item, selected_edges: List[str], available_paths: List[Dict]):
    """
    根據選擇的路徑建立後續節點

    Args:
        queue_item: FwNodeExecutionQueue 實例
        selected_edges: 選擇的 edge ID 列表
        available_paths: 可選路徑列表
    """
    import secrets
    from ...models import FwNodeExecutionQueue, FwWorkflowInstance
    from ..workflow_log_service import WorkflowLogService

    workflow_instance = FwWorkflowInstance.query.filter_by(
        secure_code=queue_item.workflow_instance_secure_code
    ).first()

    if not workflow_instance:
        return

    # 取得有效流程圖（快照優先，設計圖 fallback）
    from ..workflow_engine import WorkflowEngine
    graph = WorkflowEngine.get_effective_graph(workflow_instance)
    if not graph:
        return

    graph_nodes = graph.get('nodes', [])

    # 建立 node id -> node data 的映射
    node_map = {}
    for node in graph_nodes:
        node_id = node.get('id')
        if node_id:
            node_map[node_id] = node

    # 為每個選擇的 edge 建立對應的後續節點
    for edge_id in selected_edges:
        # 找到對應的路徑資訊
        path_info = None
        for p in available_paths:
            if p['edge_id'] == edge_id:
                path_info = p
                break

        if not path_info:
            continue

        target_node_id = path_info['target_node_id']
        target_node_type = path_info['target_node_type']

        # 從 graph 取得完整節點配置
        target_node_data = node_map.get(target_node_id, {})
        node_config = target_node_data.get('config', {})
        display_name = target_node_data.get('label') or target_node_data.get('data', {}).get('label') or ''

        # 檢查節點是否已存在且未完成
        existing = FwNodeExecutionQueue.query.filter(
            FwNodeExecutionQueue.workflow_instance_secure_code == workflow_instance.secure_code,
            FwNodeExecutionQueue.node_id == target_node_id,
            FwNodeExecutionQueue.calling_instance_code == queue_item.calling_instance_code,
            FwNodeExecutionQueue.status.in_(['PENDING', 'RUNNING', 'WAITING'])
        ).first()

        if existing:
            logger.info(f'節點執行中或等待中，跳過: {target_node_type} ({target_node_id}) status={existing.status}')
            continue

        logger.info(f'建立後續節點: {target_node_type} ({target_node_id})')

        new_queue_item = FwNodeExecutionQueue(
            secure_code=secrets.token_urlsafe(16),
            org_secure_code=workflow_instance.org_secure_code,
            workflow_instance_secure_code=workflow_instance.secure_code,
            form_instance_secure_code=getattr(workflow_instance, 'form_instance_secure_code', None),
            node_id=target_node_id,
            node_type=target_node_type,
            node_name=display_name,
            node_config=node_config,
            parent_node_id=queue_item.parent_node_id,
            calling_instance_code=queue_item.calling_instance_code,
            status='PENDING',
            priority=queue_item.priority
        )

        db.session.add(new_queue_item)

        WorkflowLogService.log(
            workflow_instance_id=workflow_instance.id,
            node_queue_id=None,
            node_id=queue_item.node_id,
            node_type=queue_item.node_type,
            node_instance_id=queue_item.secure_code,
            org_secure_code=queue_item.org_secure_code,
            status=queue_item.status,
            level='INFO',
            message=f'FormAdapter 建立後續節點: {target_node_type}',
            data={
                'from_node': queue_item.node_id,
                'edge_id': edge_id,
                'target_node_id': target_node_id,
                'target_node_type': target_node_type
            }
        )

    db.session.commit()
