"""
FormWorkflow Module - SubSystem Provision Handler
子系統配置節點處理器

三合一動作：
  create  - 建立子系統 + 選單 + 授予開發者權限
  suspend - 停用子系統 + 停用選單
  delete  - 軟刪除子系統 + 停用選單 + 撤銷所有開發者權限
"""
import logging
import re
from typing import Dict, Any

from app import db
from .base import BaseNodeHandler

logger = logging.getLogger(__name__)

# 選單父節點 code
_SUB_SYSTEM_MENU_PARENT = 'sub_system'

# 模組代碼
_WEB_BUILDER_MODULE = 'nocode_builder'

# code 格式驗證
_CODE_PATTERN = re.compile(r'^[A-Za-z][A-Za-z0-9_]{0,58}$')


class SubSystemProvisionHandler(BaseNodeHandler):
    """子系統配置處理器"""

    def validate(self) -> bool:
        action = self.get_config_value('action')
        if not action:
            raise ValueError('缺少必要配置: action')
        if action not in ('create', 'suspend', 'delete'):
            raise ValueError(f'不支援的 action: {action}，須為 create/suspend/delete')
        return True

    def handle(self) -> Dict[str, Any]:
        self.report_running()

        action = self.get_config_value('action')

        if action == 'create':
            return self._handle_create()
        elif action == 'suspend':
            return self._handle_suspend()
        elif action == 'delete':
            return self._handle_delete()
        else:
            return {'status': 'error', 'message': f'未知 action: {action}'}

    # ========================================
    # create
    # ========================================
    def _handle_create(self) -> Dict[str, Any]:
        from modules.nocode_builder.services.provision_service import SubSystemProvisionService

        # 讀取配置（支援變數替換）
        raw_name = self.get_config_value('sub_system_name', '')
        name = self.replace_variables(raw_name).strip() if raw_name else ''

        raw_icon = self.get_config_value('sub_system_icon', '')
        icon = self.replace_variables(raw_icon).strip() if raw_icon else ''

        raw_developer = self.get_config_value('sub_system_developer', '')
        developer_sc = self.replace_variables(raw_developer).strip() if raw_developer else ''

        if not name:
            return {'status': 'error', 'message': '子系統名稱為空'}

        # 取得企業 context
        org_sc = self._get_org_secure_code()
        if not org_sc:
            return {'status': 'error', 'message': '無法取得企業資訊'}

        # 若未指定開發者，使用申請者
        if not developer_sc:
            developer_sc = self._get_applicant_secure_code()
        if not developer_sc:
            return {'status': 'error', 'message': '無法取得開發者資訊'}

        result = SubSystemProvisionService.create_sub_system(
            org_sc=org_sc,
            name=name,
            icon=icon,
            developer_sc=developer_sc,
        )

        if not result['success']:
            return {'status': 'error', 'message': result['error']}

        data = result['data']

        # 寫入流程變數，供後續節點使用
        self.set_flow_var('sub_system_secure_code', data['sub_system_secure_code'])
        self.set_flow_var('sub_system_code', data['sub_system_code'])
        self.set_flow_var('sub_system_menu_code', data['menu_code'])

        self.log_info('子系統建立成功', {
            'sub_system_code': data['sub_system_code'],
            'developer': developer_sc,
        })

        return {
            'status': 'success',
            'message': f'子系統「{name}」建立成功 (code={data["sub_system_code"]})',
            'data': data,
        }

    # ========================================
    # suspend
    # ========================================
    def _handle_suspend(self) -> Dict[str, Any]:
        from modules.nocode_builder.services.provision_service import SubSystemProvisionService

        sub_system_code = self._resolve_sub_system_code()
        if not sub_system_code:
            return {'status': 'error', 'message': '無法取得目標子系統 code'}

        org_sc = self._get_org_secure_code()
        if not org_sc:
            return {'status': 'error', 'message': '無法取得企業資訊'}

        result = SubSystemProvisionService.suspend_sub_system(
            org_sc=org_sc,
            sub_system_code=sub_system_code,
        )

        if not result['success']:
            return {'status': 'error', 'message': result['error']}

        self.log_info('子系統已停用', {'sub_system_code': sub_system_code})
        return {
            'status': 'success',
            'message': f'子系統 {sub_system_code} 已停用',
        }

    # ========================================
    # delete
    # ========================================
    def _handle_delete(self) -> Dict[str, Any]:
        from modules.nocode_builder.services.provision_service import SubSystemProvisionService

        sub_system_code = self._resolve_sub_system_code()
        if not sub_system_code:
            return {'status': 'error', 'message': '無法取得目標子系統 code'}

        org_sc = self._get_org_secure_code()
        if not org_sc:
            return {'status': 'error', 'message': '無法取得企業資訊'}

        result = SubSystemProvisionService.delete_sub_system(
            org_sc=org_sc,
            sub_system_code=sub_system_code,
        )

        if not result['success']:
            return {'status': 'error', 'message': result['error']}

        self.log_info('子系統已刪除', {'sub_system_code': sub_system_code})
        return {
            'status': 'success',
            'message': f'子系統 {sub_system_code} 已刪除',
        }

    # ========================================
    # 內部輔助
    # ========================================
    def _get_org_secure_code(self) -> str:
        """從表單實例取得 org_secure_code"""
        if self.form_instance:
            return self.form_instance.org_secure_code
        return ''

    def _get_applicant_secure_code(self) -> str:
        """從表單實例取得申請者 secure_code"""
        if self.form_instance:
            return self.form_instance.applicant_secure_code
        return ''

    def _resolve_sub_system_code(self) -> str:
        """取得目標子系統 code（從配置或流程變數）"""
        raw = self.get_config_value('sub_system_code', '')
        if raw:
            return self.replace_variables(raw).strip()
        # fallback: 讀取流程變數
        return self.get_var('sub_system_code', '')
