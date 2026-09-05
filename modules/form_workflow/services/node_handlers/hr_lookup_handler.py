"""
FormWorkflow Module - HR Lookup Handler
人事資料取值節點處理器
"""
import re
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Optional, Tuple

from sqlalchemy import case

from app.models import (
    ApprovalCategory,
    EmployeePosition,
    JobFamily,
    JobLevelApprovalLimit,
    Organization,
    PositionType,
    User,
)
from app.services.unit_resolver import get_unit, iter_manager_chain, resolve_direct_manager

from .base import BaseNodeHandler


class HrLookupHandler(BaseNodeHandler):
    """讀取成員職位與核決資料，寫入流程變數。"""

    _PREFIX_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')

    _BASE_SUFFIXES = [
        'found',
        'user_code',
        'user_name',
        'position_type',
        'job_title',
        'job_title_code',
        'job_title_short',
        'is_supervisor',
        'job_level_code',
        'job_level_name',
        'job_level_order',
        'job_level_is_manager',
        'job_family_code',
        'job_family_name',
        'job_family_type',
        'job_family_root_code',
        'unit_code',
        'unit_name',
        'is_unit_head',
        'direct_manager',
        'direct_manager_name',
        'direct_manager_unit',
        'direct_manager_unit_name',
    ]

    _APPROVAL_SUFFIX = 'approval_limit'
    _APPROVER_SUFFIXES = [
        'approver',
        'approver_name',
        'approver_level_code',
        'approver_unit',
        'approver_unit_name',
        'approver_found',
    ]

    def validate(self) -> bool:
        return True

    def handle(self) -> Dict[str, Any]:
        self.report_running()

        prefix = self._normalized_prefix()
        category_code = (self.get_config_value('approval_category_code', '') or '').strip().upper()
        approver_mode = self._coerce_bool(self.get_config_value('approver_mode', False))
        today = self._local_today()

        target_code = self._resolve_target_code()
        user = self._get_active_user(target_code) if target_code else None
        position = self._get_effective_position(target_code, today) if user else None

        if not user or not position:
            self._write_empty_result(prefix, category_code, approver_mode)
            self.log_warning('人事資料取值找不到有效職位', {
                'target_code': target_code,
                'has_user': bool(user),
                'org_secure_code': self.queue_item.org_secure_code,
            })
            return {
                'status': 'success',
                'message': '人事資料取值完成：找不到有效職位',
                'data': {'found': False, 'prefix': prefix}
            }

        variables = self._build_position_variables(prefix, user, position, today)
        for name, value in variables.items():
            self.set_flow_var(name, value)

        category = None
        if category_code:
            category = self._get_approval_category(category_code)
            approval_limit = self._approval_limit_for_position(position, category) if category else ''
            if category is None:
                self.log_warning('人事資料取值找不到啟用中的核決類別', {
                    'approval_category_code': category_code,
                })
            self.set_flow_var(f'{prefix}_{self._APPROVAL_SUFFIX}', approval_limit)

        if approver_mode:
            approver_vars = self._resolve_approver_variables(
                prefix, user, category_code, category, today)
            for name, value in approver_vars.items():
                self.set_flow_var(name, value)

        self.log_info('人事資料取值完成', {
            'target_code': user.secure_code,
            'position_type': position.position_type,
            'prefix': prefix,
            'approval_category_code': category_code,
            'approver_mode': approver_mode,
        })

        return {
            'status': 'success',
            'message': '人事資料取值完成',
            'data': {'found': True, 'prefix': prefix}
        }

    def _normalized_prefix(self) -> str:
        raw = (self.get_config_value('var_prefix', 'hr') or 'hr').strip()
        if self._PREFIX_RE.match(raw):
            return raw
        self.log_warning('人事資料取值變數前綴不合法，已改用 hr', {'var_prefix': raw})
        return 'hr'

    @staticmethod
    def _coerce_bool(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in ('1', 'true', 'yes', 'on')
        return bool(value)

    def _resolve_target_code(self) -> str:
        target_source = self.get_config_value('target_source', 'applicant') or 'applicant'
        if target_source == 'variable':
            expr = self.get_config_value('target_expr', '') or ''
            return self.replace_variables(expr).strip()

        if self.form_instance and self.form_instance.applicant_secure_code:
            return self.form_instance.applicant_secure_code
        return ''

    def _local_today(self):
        org = Organization.query.filter(
            Organization.secure_code == self.queue_item.org_secure_code,
            Organization.is_deleted == False,
        ).first()
        if org:
            return org.local_today()
        self.log_warning('人事資料取值找不到企業，改用 UTC 參考日', {
            'org_secure_code': self.queue_item.org_secure_code,
        })
        from app.utils.timezone import local_today
        return local_today('Asia/Taipei')

    def _get_active_user(self, user_secure_code: str) -> Optional[User]:
        if not user_secure_code:
            return None
        return User.query.filter(
            User.secure_code == user_secure_code,
            User.org_secure_code == self.queue_item.org_secure_code,
            User.is_active == True,
            User.is_deleted == False,
        ).first()

    def _get_effective_position(
        self,
        user_secure_code: str,
        today=None,
    ) -> Optional[EmployeePosition]:
        if today is None:
            today = self._local_today()
        return EmployeePosition.query.filter(
            EmployeePosition.user_secure_code == user_secure_code,
            EmployeePosition.org_secure_code == self.queue_item.org_secure_code,
            EmployeePosition.is_deleted == False,
            EmployeePosition.is_active == True,
            EmployeePosition.effective_from <= today,
            (EmployeePosition.effective_until.is_(None)) | (EmployeePosition.effective_until >= today),
        ).order_by(
            case((EmployeePosition.position_type == PositionType.PRIMARY, 0), else_=1),
            EmployeePosition.effective_from.asc(),
            EmployeePosition.id.asc(),
        ).first()

    def _build_position_variables(
        self,
        prefix: str,
        user: User,
        position: EmployeePosition,
        today,
    ) -> Dict[str, Any]:
        job_title = position.job_title
        job_level = job_title.job_level if job_title else None
        job_family = job_title.job_family if job_title else None
        root_family = self._get_root_family(job_family)
        unit = position.unit
        org = self.queue_item.org_secure_code
        station = resolve_direct_manager(user.secure_code, org, today)
        manager = self._get_active_user(station['manager_secure_code']) if station else None
        manager_unit = get_unit(station['unit_secure_code'], org) if station else None

        return {
            f'{prefix}_found': 'true',
            f'{prefix}_user_code': user.secure_code,
            f'{prefix}_user_name': user.display_name or '',
            f'{prefix}_position_type': position.position_type or '',
            f'{prefix}_job_title': job_title.name if job_title else '',
            f'{prefix}_job_title_code': job_title.code if job_title else '',
            f'{prefix}_job_title_short': job_title.short_name if job_title and job_title.short_name else '',
            f'{prefix}_is_supervisor': self._bool_string(job_title.is_supervisor if job_title else False),
            f'{prefix}_job_level_code': job_level.code if job_level else '',
            f'{prefix}_job_level_name': job_level.name if job_level else '',
            f'{prefix}_job_level_order': int(job_level.level_order) if job_level else '',
            f'{prefix}_job_level_is_manager': self._bool_string(job_level.is_manager_level if job_level else False),
            f'{prefix}_job_family_code': job_family.code if job_family else '',
            f'{prefix}_job_family_name': job_family.name if job_family else '',
            f'{prefix}_job_family_type': job_family.family_type if job_family else '',
            f'{prefix}_job_family_root_code': root_family.code if root_family else '',
            f'{prefix}_unit_code': unit.code if unit else '',
            f'{prefix}_unit_name': unit.name if unit else '',
            f'{prefix}_is_unit_head': self._bool_string(position.is_unit_head),
            f'{prefix}_direct_manager': manager.secure_code if manager else '',
            f'{prefix}_direct_manager_name': manager.display_name if manager else '',
            f'{prefix}_direct_manager_unit': manager_unit.code if manager_unit else '',
            f'{prefix}_direct_manager_unit_name': station['unit_name'] if station else '',
        }

    def _get_root_family(self, family: Optional[JobFamily]) -> Optional[JobFamily]:
        if not family:
            return None
        if not family.parent_secure_code:
            return family
        parent = JobFamily.query.filter(
            JobFamily.secure_code == family.parent_secure_code,
            JobFamily.org_secure_code == self.queue_item.org_secure_code,
            JobFamily.is_deleted == False,
            JobFamily.is_active == True,
        ).first()
        return parent or family

    @staticmethod
    def _bool_string(value: Any) -> str:
        return 'true' if bool(value) else 'false'

    def _get_approval_category(self, category_code: str) -> Optional[ApprovalCategory]:
        return ApprovalCategory.query.filter(
            ApprovalCategory.org_secure_code == self.queue_item.org_secure_code,
            ApprovalCategory.code == category_code,
            ApprovalCategory.is_deleted == False,
            ApprovalCategory.is_active == True,
        ).first()

    def _approval_limit_for_position(
        self,
        position: EmployeePosition,
        category: Optional[ApprovalCategory],
    ) -> Any:
        job_title = position.job_title
        job_level = job_title.job_level if job_title else None
        if not job_level or not category:
            return 0
        row = JobLevelApprovalLimit.query.filter(
            JobLevelApprovalLimit.org_secure_code == self.queue_item.org_secure_code,
            JobLevelApprovalLimit.job_level_secure_code == job_level.secure_code,
            JobLevelApprovalLimit.category_secure_code == category.secure_code,
            JobLevelApprovalLimit.is_deleted == False,
        ).first()
        if not row or row.approval_limit is None:
            return 0
        return int(row.approval_limit)

    def _resolve_approver_variables(
        self,
        prefix: str,
        user: User,
        category_code: str,
        category: Optional[ApprovalCategory],
        today,
    ) -> Dict[str, Any]:
        empty = self._empty_approver_vars(prefix)
        amount_expr = self.get_config_value('amount_expr', '') or ''
        if not category_code or not amount_expr:
            self.log_warning('人事資料取值核決人模式缺少核決類別或金額表達式', {
                'approval_category_code': category_code,
                'has_amount_expr': bool(amount_expr),
            })
            return empty
        if category is None:
            self.log_warning('人事資料取值核決人模式找不到核決類別', {
                'approval_category_code': category_code,
            })
            return empty

        amount = self._parse_amount(amount_expr)
        if amount is None:
            self.log_warning('人事資料取值核決人模式金額解析失敗', {'amount_expr': amount_expr})
            return empty

        org = self.queue_item.org_secure_code
        for steps, station in enumerate(iter_manager_chain(user.secure_code, org, today), start=1):
            if steps > 20:
                self.log_warning('人事資料取值核決人模式超過 20 站', {
                    'target_code': user.secure_code,
                })
                break
            manager = self._get_active_user(station['manager_secure_code'])
            if not manager:
                continue
            manager_position = self._get_effective_position(manager.secure_code, today)

            limit = Decimal(str(
                self._approval_limit_for_position(manager_position, category)
                if manager_position else 0
            ))
            if limit >= amount:
                level = manager_position.job_title.job_level if manager_position and manager_position.job_title else None
                unit = get_unit(station['unit_secure_code'], org)
                return {
                    f'{prefix}_approver': manager.secure_code,
                    f'{prefix}_approver_name': manager.display_name or '',
                    f'{prefix}_approver_level_code': level.code if level else '',
                    f'{prefix}_approver_unit': unit.code if unit else '',
                    f'{prefix}_approver_unit_name': station['unit_name'],
                    f'{prefix}_approver_found': 'true',
                }

        return empty

    def _parse_amount(self, amount_expr: str) -> Optional[Decimal]:
        raw = self.replace_variables(amount_expr)
        normalized = re.sub(r'[\s,]+', '', raw or '')
        if not normalized:
            return None
        try:
            return Decimal(normalized)
        except (InvalidOperation, ValueError):
            return None

    def _write_empty_result(self, prefix: str, category_code: str, approver_mode: bool) -> None:
        for suffix in self._BASE_SUFFIXES:
            self.set_flow_var(f'{prefix}_{suffix}', 'false' if suffix == 'found' else '')
        if category_code:
            self.set_flow_var(f'{prefix}_{self._APPROVAL_SUFFIX}', '')
        if approver_mode:
            for name, value in self._empty_approver_vars(prefix).items():
                self.set_flow_var(name, value)

    def _empty_approver_vars(self, prefix: str) -> Dict[str, str]:
        return {
            f'{prefix}_approver': '',
            f'{prefix}_approver_name': '',
            f'{prefix}_approver_level_code': '',
            f'{prefix}_approver_unit': '',
            f'{prefix}_approver_unit_name': '',
            f'{prefix}_approver_found': 'false',
        }
