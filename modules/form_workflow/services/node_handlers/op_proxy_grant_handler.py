"""
FormWorkflow Module - OpProxyGrant Handler

Creates proxy role assignments after the named delegate accepts the request.
"""
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from flask_babel import gettext as _

from .base import BaseNodeHandler

logger = logging.getLogger(__name__)


class OpProxyGrantHandler(BaseNodeHandler):
    """代理指定授出節點處理器"""

    def handle(self) -> Dict[str, Any]:
        self.report_running()

        try:
            form_data = self.form_instance.form_data if self.form_instance else {}
            if not isinstance(form_data, dict):
                msg = _('代理指定失敗：表單資料格式錯誤')
                self.log_error('OpProxyGrant invalid form_data')
                return {'status': 'error', 'message': msg}

            roles_field = self.get_config_value('roles_field') or 'proxy_roles'
            delegate_field = self.get_config_value('delegate_field') or 'delegate'
            from_field = self.get_config_value('from_field') or 'effective_from'
            until_field = self.get_config_value('until_field') or 'effective_until'
            forms_field = self.get_config_value('forms_field') or 'authorized_forms'
            reason_field = self.get_config_value('reason_field') or 'reason'
            result_var = self.get_config_value('result_var') or 'proxy'

            applicant_sc = (
                self.form_instance.applicant_secure_code if self.form_instance else ''
            )
            applicant_sc = str(applicant_sc or '').strip()
            if not applicant_sc:
                msg = _('代理指定失敗：找不到申請人')
                self.log_error('OpProxyGrant missing applicant')
                return {'status': 'error', 'message': msg}

            org_code = self.queue_item.org_secure_code
            self._set_rls_context(org_code)

            applicant_user = self._get_active_org_user(applicant_sc, org_code)
            if not applicant_user:
                msg = _('代理指定失敗：申請人不是本企業有效帳號')
                self.log_error('OpProxyGrant applicant not active in org', {
                    'applicant': applicant_sc, 'org': org_code,
                })
                return {'status': 'error', 'message': msg}

            delegate_sc = str(form_data.get(delegate_field) or '').strip()
            delegate_user = self._get_active_org_user(delegate_sc, org_code)
            if not delegate_user:
                msg = _('代理指定失敗：代理人不是本企業有效帳號')
                self.log_error('OpProxyGrant delegate not active in org', {
                    'delegate': delegate_sc, 'org': org_code,
                })
                return {'status': 'error', 'message': msg}
            if delegate_sc == applicant_sc:
                msg = _('代理指定失敗：代理人不可以是申請人本人')
                self.log_error('OpProxyGrant delegate equals applicant', {
                    'delegate': delegate_sc,
                })
                return {'status': 'error', 'message': msg}

            valid_from = self._parse_date(form_data.get(from_field))
            valid_until = self._parse_date(form_data.get(until_field))
            if not valid_from or not valid_until:
                msg = _('代理指定失敗：起迄日期格式錯誤')
                self.log_error('OpProxyGrant invalid date range')
                return {'status': 'error', 'message': msg}
            if valid_from > valid_until:
                msg = _('代理指定失敗：生效開始日期不能晚於結束日期')
                self.log_error('OpProxyGrant from after until', {
                    'valid_from': valid_from.isoformat(),
                    'valid_until': valid_until.isoformat(),
                })
                return {'status': 'error', 'message': msg}

            reason = str(form_data.get(reason_field) or '').strip()
            if not reason:
                msg = _('代理指定失敗：請填寫事由')
                self.log_error('OpProxyGrant missing reason')
                return {'status': 'error', 'message': msg}

            requested_roles = self._normalize_roles(form_data.get(roles_field))
            if not requested_roles:
                msg = _('代理指定失敗：未選擇要委任的角色')
                self.log_error('OpProxyGrant missing roles')
                return {'status': 'error', 'message': msg}

            forms = self._normalize_forms(form_data.get(forms_field))
            today = self._org_today(org_code)
            allowed_rows = self._proxyable_rows(org_code, applicant_sc, today)
            allowed_keys = {(row.role_secure_code, row.unit_secure_code) for row in allowed_rows}

            # form_data 由送單人控制，且送單到簽核完成之間申請人的角色可能已被撤銷；
            # 前端 myRolePicker 的過濾不是防線，授出前必須用執行當下的 regular
            # 持有狀態 fail-closed 重驗。
            out_of_scope = [
                {'role_secure_code': role_sc, 'unit_secure_code': unit_sc}
                for role_sc, unit_sc in requested_roles
                if (role_sc, unit_sc) not in allowed_keys
            ]
            if out_of_scope:
                msg = _('代理指定失敗：申請的角色已不在你目前持有的範圍內')
                self.log_error('OpProxyGrant requested roles out of scope', {
                    'applicant': applicant_sc,
                    'out_of_scope': out_of_scope,
                })
                return {'status': 'error', 'message': msg}

            from app import db
            from app.services import role_assignment_service

            execution_code = (
                getattr(self.workflow_instance, 'execution_code', None)
                or self.queue_item.workflow_instance_secure_code
            )
            role_labels = self._role_labels(allowed_rows, requested_roles)
            created = 0
            try:
                for role_sc, unit_sc in requested_roles:
                    role_assignment_service.assign_role(
                        org_code,
                        delegate_sc,
                        role_sc,
                        unit_sc,
                        kind='proxy',
                        acting_for_sc=applicant_sc,
                        valid_from=valid_from,
                        valid_until=valid_until,
                        allowed_form_templates=forms or None,
                        grant_reason=reason,
                        operator=applicant_user,
                        source_ref=f'flow:{execution_code}',
                        commit=False,
                    )
                    created += 1
                db.session.commit()
            except ValueError as exc:
                db.session.rollback()
                msg = str(exc)
                self.log_error('OpProxyGrant assign_role rejected', {'error': msg})
                return {'status': 'error', 'message': msg}
            except Exception as exc:
                db.session.rollback()
                self.log_error(f'OpProxyGrant assign_role failed: {exc}')
                return {'status': 'error', 'message': _('代理指定失敗')}

            self.set_flow_var(f'{result_var}_count', created)
            self.set_flow_var(f'{result_var}_delegate', delegate_sc)
            self.set_flow_var(f'{result_var}_delegate_name', self._display_name(delegate_user))
            self.set_flow_var(f'{result_var}_roles', '、'.join(role_labels))
            self.set_flow_var(f'{result_var}_from', valid_from.isoformat())
            self.set_flow_var(f'{result_var}_until', valid_until.isoformat())

            self.log_info('OpProxyGrant completed', {
                'delegate': delegate_sc,
                'applicant': applicant_sc,
                'count': created,
                'roles': [
                    {'role_secure_code': role_sc, 'unit_secure_code': unit_sc}
                    for role_sc, unit_sc in requested_roles
                ],
            })
            return {'status': 'success', 'message': _('代理指定完成')}
        except Exception as exc:
            self.log_error(f'OpProxyGrant failed: {exc}')
            return {'status': 'error', 'message': _('代理指定失敗')}

    def _set_rls_context(self, org_code: str):
        """設定 RLS session variable（背景 executor 無 request context）"""
        from app import db
        db.session.execute(
            db.text("SELECT set_config('app.current_org', :org, true)"),
            {'org': org_code},
        )

    def _get_active_org_user(self, user_secure_code: str, org_code: str):
        from app.models import User

        return User.query.filter_by(
            secure_code=user_secure_code,
            org_secure_code=org_code,
            is_deleted=False,
            is_active=True,
        ).first()

    def _org_today(self, org_code: str):
        from app.models import Organization

        org = Organization.query.filter_by(
            secure_code=org_code,
            is_deleted=False,
        ).first()
        if not org:
            raise ValueError(_('企業不存在'))
        return org.local_today()

    def _proxyable_rows(self, org_code: str, applicant_sc: str, today):
        from app.services import proxy_assignment_service

        return proxy_assignment_service.proxyable_regular_assignments(
            org_code, applicant_sc, today)

    def _parse_date(self, raw: Any):
        value = str(raw or '').strip()
        if not value:
            return None
        date_part = value.split('T')[0].strip()
        for fmt in ('%Y-%m-%d', '%Y/%m/%d'):
            try:
                return datetime.strptime(date_part, fmt).date()
            except ValueError:
                continue
        return None

    def _normalize_roles(self, raw: Any) -> List[Tuple[str, Optional[str]]]:
        if not isinstance(raw, list):
            return []
        roles = []
        seen = set()
        for item in raw:
            if not isinstance(item, dict):
                continue
            role_sc = str(item.get('role_secure_code') or '').strip()
            unit_raw = item.get('unit_secure_code')
            unit_sc = None if unit_raw is None else str(unit_raw or '').strip() or None
            if not role_sc:
                continue
            key = (role_sc, unit_sc)
            if key in seen:
                continue
            seen.add(key)
            roles.append(key)
        return roles

    def _normalize_forms(self, raw: Any) -> Optional[List[str]]:
        if not isinstance(raw, list):
            return None
        forms = []
        for item in raw:
            sc = str(item or '').strip()
            if sc and sc not in forms:
                forms.append(sc)
        return forms or None

    def _role_labels(self, rows, requested_roles) -> List[str]:
        labels = {}
        for row in rows:
            role_name = row.role.name if row.role else row.role_secure_code
            unit_name = row.unit.name if row.unit else ''
            labels[(row.role_secure_code, row.unit_secure_code)] = (
                role_name + (f'@{unit_name}' if unit_name else '')
            )
        return [
            labels.get((role_sc, unit_sc), role_sc)
            for role_sc, unit_sc in requested_roles
        ]

    def _display_name(self, user) -> str:
        return (getattr(user, 'display_name', None)
                or getattr(user, 'username', None)
                or getattr(user, 'email', None)
                or getattr(user, 'secure_code', ''))
