"""
FormWorkflow Module - ApiKeyIssue Handler

Issues a platform API Key after approval and creates a one-time claim ticket.
The plaintext secret returned by create_api_key() is intentionally discarded:
only the beneficiary may retrieve it later through api_key_claim_service.claim_once().
"""
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from flask_babel import gettext as _

from .base import BaseNodeHandler

logger = logging.getLogger(__name__)


class ApiKeyIssueHandler(BaseNodeHandler):
    """API Key 核發節點處理器"""

    def handle(self) -> Dict[str, Any]:
        self.report_running()

        try:
            form_data = self.form_instance.form_data if self.form_instance else {}
            if not isinstance(form_data, dict):
                form_data = {}

            beneficiary_field = self.get_config_value(
                'beneficiary_field') or 'beneficiary'
            forms_field = self.get_config_value(
                'forms_field') or 'authorized_forms'
            purpose_field = self.get_config_value('purpose_field') or 'purpose'
            expires_field = self.get_config_value('expires_field') or 'expires_at'
            allowed_ips_field = self.get_config_value(
                'allowed_ips_field') or 'allowed_ips'
            claim_ttl_hours = int(self.get_config_value('claim_ttl_hours') or 72)
            result_var = self.get_config_value('result_var') or 'apikey'

            beneficiary = str(form_data.get(beneficiary_field) or '').strip()
            forms = form_data.get(forms_field)
            purpose = str(form_data.get(purpose_field) or '').strip()
            expires_raw = str(form_data.get(expires_field) or '').strip()
            allowed_ips = self._normalize_allowed_ips(form_data.get(allowed_ips_field))

            if not beneficiary:
                msg = _('API Key 核發失敗：未指定領取人')
                self.log_error('ApiKeyIssue missing beneficiary')
                return {'status': 'error', 'message': msg}
            if not isinstance(forms, list) or not [f for f in forms if f]:
                msg = _('API Key 核發失敗：未指定授權表單')
                self.log_error('ApiKeyIssue missing authorized forms')
                return {'status': 'error', 'message': msg}

            expires_at = self._parse_expires_at(
                expires_raw, self.queue_item.org_secure_code)
            if expires_at is None:
                msg = _('API Key 核發失敗：有效期限格式錯誤')
                self.log_error('ApiKeyIssue invalid expires_at')
                return {'status': 'error', 'message': msg}

            org_code = self.queue_item.org_secure_code
            self._set_rls_context(org_code)

            beneficiary_user = self._get_active_org_user(beneficiary, org_code)
            if not beneficiary_user:
                msg = _('API Key 核發失敗：領取人不是本企業有效帳號')
                self.log_error(
                    'ApiKeyIssue beneficiary not active in org',
                    {'beneficiary': beneficiary, 'org': org_code},
                )
                return {'status': 'error', 'message': msg}

            requested_forms = []
            for item in forms:
                sc = str(item).strip()
                if sc and sc not in requested_forms:
                    requested_forms.append(sc)

            # 授權表單必須落在「領取人自己填得到」的範圍內。前端選擇器的過濾
            # 不是防線 -- form_data 由送單人控制，F12 就能塞進任意 template SC，
            # 核發前不重驗等於任何人都能替他人取得原本沒有的能力（提權）。
            out_of_scope = self._forms_out_of_scope(
                requested_forms, beneficiary_user, org_code)
            if out_of_scope:
                msg = _('API Key 核發失敗：授權表單超出領取人可填寫的範圍')
                self.log_error(
                    'ApiKeyIssue forms out of beneficiary scope',
                    {'beneficiary': beneficiary, 'out_of_scope': out_of_scope},
                )
                return {'status': 'error', 'message': msg}

            from app.services import api_key_claim_service, api_key_service

            form_sc = self.form_instance.secure_code if self.form_instance else None
            subject = (self.form_instance.subject or '').strip() if self.form_instance else ''
            name = subject or _('API Key 申請')
            description = self._build_description(purpose, form_sc)

            api_key_record, _plaintext_secret_b64 = api_key_service.create_api_key(
                org_secure_code=org_code,
                name=name,
                description=description,
                scopes={'form_template': requested_forms},
                applicant_user_secure_code=beneficiary,
                allowed_ips=allowed_ips,
                expires_at=expires_at,
                created_by_secure_code=f'wf:{self.queue_item.workflow_instance_secure_code}',
            )

            claim = api_key_claim_service.create_claim(
                api_key_secure_code=api_key_record.secure_code,
                org_secure_code=org_code,
                beneficiary_user_secure_code=beneficiary,
                form_instance_secure_code=form_sc,
                ttl_hours=claim_ttl_hours,
            )

            self.set_flow_var(f'{result_var}_key_id', api_key_record.key_id)
            self.set_flow_var(f'{result_var}_claim_code', claim.secure_code)
            self.set_flow_var(f'{result_var}_beneficiary', beneficiary)

            self.log_info(
                'ApiKeyIssue completed',
                {
                    'api_key_sc': api_key_record.secure_code,
                    'key_id': api_key_record.key_id,
                    'claim_sc': claim.secure_code,
                    'beneficiary': beneficiary,
                },
            )
            return {'status': 'success', 'message': _('API Key 核發完成')}
        except Exception as exc:
            self.log_error(f'ApiKeyIssue failed: {exc}')
            return {'status': 'error', 'message': _('API Key 核發失敗')}

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

    def _forms_out_of_scope(self, requested_forms: List[str], beneficiary_user,
                            org_code: str) -> List[str]:
        """回傳領取人填不到的表單模板 SC（唯一判定：fill_permission_service）。"""
        from ..fill_permission_service import list_fillable_published_templates

        allowed = {
            item['secure_code']
            for item in list_fillable_published_templates(
                beneficiary_user, org_code)
        }
        return [sc for sc in requested_forms if sc not in allowed]

    def _parse_expires_at(self, value: str,
                          org_code: str) -> Optional[datetime]:
        """把「有效期限」日期解讀成「該日在企業時區的結束」的 naive UTC。

        TZ-01:DB 存 naive UTC,但使用者填的是當地日曆日。直接
        strptime 會得到當日 00:00 UTC —— 台北時區等於當天早上 8 點就失效,
        比使用者預期的「用到當天結束」早了整整一天。
        """
        if not value:
            return None
        # flatpickr 缺失時（PF-207）datetime 元件退化成純文字輸入，
        # 使用者手打的常見變體（斜線、含時間的 ISO 字串）也要能解讀。
        date_part = value.split('T')[0].strip()
        day = None
        for fmt in ('%Y-%m-%d', '%Y/%m/%d'):
            try:
                day = datetime.strptime(date_part, fmt)
                break
            except ValueError:
                continue
        if day is None:
            return None

        try:
            local_tz = ZoneInfo(self._org_timezone(org_code))
        except Exception:
            local_tz = ZoneInfo('Asia/Taipei')
        end_local = (day + timedelta(days=1)).replace(tzinfo=local_tz)
        return end_local.astimezone(ZoneInfo('UTC')).replace(tzinfo=None)

    def _org_timezone(self, org_code: str) -> str:
        from app.models import Organization

        org = Organization.query.filter_by(
            secure_code=org_code, is_deleted=False).first()
        if not org:
            return 'Asia/Taipei'
        return org.get_setting('timezone', 'Asia/Taipei') or 'Asia/Taipei'

    def _normalize_allowed_ips(self, raw: Any) -> Optional[List[str]]:
        if not raw:
            return None
        if isinstance(raw, list):
            cleaned = [str(item).strip() for item in raw if str(item).strip()]
            return cleaned or None
        if isinstance(raw, str):
            parts = raw.replace('\n', ',').split(',')
            cleaned = [part.strip() for part in parts if part.strip()]
            return cleaned or None
        return None

    def _build_description(self, purpose: str, form_sc: Optional[str]) -> str:
        parts = []
        if purpose:
            parts.append(purpose)
        if form_sc:
            parts.append(f'來源申請單: {form_sc}')
        return '\n'.join(parts)[:500]
