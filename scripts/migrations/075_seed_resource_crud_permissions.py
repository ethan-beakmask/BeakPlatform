#!/usr/bin/env python3
"""
075 - 資源 CRUD 權限代碼權威清單（冪等）

背景：ResourceGateway 階段 B 在 dev 以工具腳本
（scripts/seed_resource_permissions.py）分批建立 {type}:{action} 權限代碼，
但工具腳本需要參數、不會被 migration runner 重播，導致 prod 部署時
權限代碼缺漏、LIST_RBAC_ENFORCED_MODELS 內的 model 全面拒絕存取。

本 migration 內嵌 dev 環境的權威清單（含逐碼 permission_level，
如 module:read 是 MODULE 而其餘 module:* 是 ORG），已存在的代碼一律跳過，
可重複執行。之後每批新增 resource type 時，直接新增編號 migration，
不要只跑工具腳本。
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'backend'))

# (code, permission_level, name, is_system_permission)
# 來源：dev DB 2026-07-07 快照
PERMISSIONS = [
    ('approval_category:create', 'ORG', 'approval_category create', False),
    ('approval_category:delete', 'ORG', 'approval_category delete', False),
    ('approval_category:read', 'ORG', 'approval_category read', False),
    ('approval_category:update', 'ORG', 'approval_category update', False),
    ('audit_log:read', 'ORG', '檢視稽核日誌', True),
    ('contract:create', 'SYSTEM', '新增合約', True),
    ('contract:delete', 'SYSTEM', '刪除合約', True),
    ('contract:read', 'SYSTEM', '檢視合約', True),
    ('contract:update', 'SYSTEM', '編輯合約', True),
    ('dc_page_template:create', 'ORG', 'dc_page_template create', False),
    ('dc_page_template:delete', 'ORG', 'dc_page_template delete', False),
    ('dc_page_template:read', 'ORG', 'dc_page_template read', False),
    ('dc_page_template:update', 'ORG', 'dc_page_template update', False),
    ('dc_site_map_node:create', 'ORG', 'dc_site_map_node create', False),
    ('dc_site_map_node:delete', 'ORG', 'dc_site_map_node delete', False),
    ('dc_site_map_node:read', 'ORG', 'dc_site_map_node read', False),
    ('dc_site_map_node:update', 'ORG', 'dc_site_map_node update', False),
    ('delegation:create', 'ORG', 'delegation create', False),
    ('delegation:delete', 'ORG', 'delegation delete', False),
    ('delegation:read', 'ORG', 'delegation read', False),
    ('delegation:update', 'ORG', 'delegation update', False),
    ('department:create', 'ORG', '新增部門', True),
    ('department:delete', 'ORG', '刪除部門', True),
    ('department:read', 'ORG', '檢視部門', True),
    ('department:update', 'ORG', '編輯部門', True),
    ('duty:create', 'ORG', 'duty create', False),
    ('duty:delete', 'ORG', 'duty delete', False),
    ('duty:read', 'ORG', 'duty read', False),
    ('duty:update', 'ORG', 'duty update', False),
    ('duty_category:create', 'ORG', 'duty_category create', False),
    ('duty_category:delete', 'ORG', 'duty_category delete', False),
    ('duty_category:read', 'ORG', 'duty_category read', False),
    ('duty_category:update', 'ORG', 'duty_category update', False),
    ('employee_position:create', 'ORG', 'employee_position create', False),
    ('employee_position:delete', 'ORG', 'employee_position delete', False),
    ('employee_position:read', 'ORG', 'employee_position read', False),
    ('employee_position:update', 'ORG', 'employee_position update', False),
    ('flow_definition:create', 'ORG', '新增流程定義', True),
    ('flow_definition:delete', 'ORG', '刪除流程定義', True),
    ('flow_definition:read', 'ORG', '檢視流程定義', True),
    ('flow_definition:update', 'ORG', '編輯流程定義', True),
    ('flow_instance:read', 'MODULE', '檢視流程實例', True),
    ('form_instance:create', 'MODULE', '填寫表單', True),
    ('form_instance:delete', 'MODULE', '刪除表單填報', True),
    ('form_instance:read', 'MODULE', '檢視表單填報', True),
    ('form_instance:update', 'MODULE', '編輯表單填報', True),
    ('form_template:create', 'ORG', '新增表單範本', True),
    ('form_template:delete', 'ORG', '刪除表單範本', True),
    ('form_template:read', 'ORG', '檢視表單範本', True),
    ('form_template:update', 'ORG', '編輯表單範本', True),
    ('job_family:create', 'ORG', 'job_family create', False),
    ('job_family:delete', 'ORG', 'job_family delete', False),
    ('job_family:read', 'ORG', 'job_family read', False),
    ('job_family:update', 'ORG', 'job_family update', False),
    ('job_level:create', 'ORG', 'job_level create', False),
    ('job_level:delete', 'ORG', 'job_level delete', False),
    ('job_level:read', 'ORG', 'job_level read', False),
    ('job_level:update', 'ORG', 'job_level update', False),
    ('job_level_approval_limit:create', 'ORG', 'job_level_approval_limit create', False),
    ('job_level_approval_limit:delete', 'ORG', 'job_level_approval_limit delete', False),
    ('job_level_approval_limit:read', 'ORG', 'job_level_approval_limit read', False),
    ('job_level_approval_limit:update', 'ORG', 'job_level_approval_limit update', False),
    ('job_title:create', 'ORG', 'job_title create', False),
    ('job_title:delete', 'ORG', 'job_title delete', False),
    ('job_title:read', 'ORG', 'job_title read', False),
    ('job_title:update', 'ORG', 'job_title update', False),
    ('module:create', 'ORG', '新增模組', True),
    ('module:delete', 'ORG', '刪除模組', True),
    ('module:read', 'MODULE', '檢視模組', True),
    ('module:update', 'ORG', '編輯模組', True),
    ('module_content:create', 'MODULE', '新增內容', True),
    ('module_content:delete', 'MODULE', '刪除內容', True),
    ('module_content:read', 'MODULE', '檢視內容', True),
    ('module_content:update', 'MODULE', '編輯內容', True),
    ('organization:create', 'SYSTEM', '新增企業', True),
    ('organization:delete', 'SYSTEM', '刪除企業', True),
    ('organization:read', 'SYSTEM', '檢視企業', True),
    ('organization:update', 'SYSTEM', '編輯企業', True),
    ('recipient_group:create', 'ORG', 'recipient_group create', False),
    ('recipient_group:delete', 'ORG', 'recipient_group delete', False),
    ('recipient_group:read', 'ORG', 'recipient_group read', False),
    ('recipient_group:update', 'ORG', 'recipient_group update', False),
    ('report:read', 'ORG', '檢視報表', True),
    ('role:create', 'ORG', '新增角色', True),
    ('role:delete', 'ORG', '刪除角色', True),
    ('role:read', 'ORG', '檢視角色', True),
    ('role:update', 'ORG', '編輯角色', True),
    ('smtp_config:create', 'ORG', 'smtp_config create', False),
    ('smtp_config:delete', 'ORG', 'smtp_config delete', False),
    ('smtp_config:read', 'ORG', 'smtp_config read', False),
    ('smtp_config:update', 'ORG', 'smtp_config update', False),
    ('store_template:create', 'ORG', '上傳商店模板', True),
    ('store_template:delete', 'SYSTEM', '下架商店模板', True),
    ('store_template:read', 'ORG', '瀏覽商店模板', True),
    ('system_setting:read', 'SYSTEM', '檢視系統設定', True),
    ('system_setting:update', 'SYSTEM', '編輯系統設定', True),
    ('telegram_config:create', 'ORG', 'telegram_config create', False),
    ('telegram_config:delete', 'ORG', 'telegram_config delete', False),
    ('telegram_config:read', 'ORG', 'telegram_config read', False),
    ('telegram_config:update', 'ORG', 'telegram_config update', False),
    ('user:create', 'ORG', '新增用戶', True),
    ('user:delete', 'ORG', '刪除用戶', True),
    ('user:read', 'ORG', '檢視用戶', True),
    ('user:update', 'ORG', '編輯用戶', True),
    ('user_numbering_rule:create', 'ORG', 'user_numbering_rule create', False),
    ('user_numbering_rule:delete', 'ORG', 'user_numbering_rule delete', False),
    ('user_numbering_rule:read', 'ORG', 'user_numbering_rule read', False),
    ('user_numbering_rule:update', 'ORG', 'user_numbering_rule update', False),
    ('user_role_assignment:create', 'ORG', 'user_role_assignment create', False),
    ('user_role_assignment:delete', 'ORG', 'user_role_assignment delete', False),
    ('user_role_assignment:read', 'ORG', 'user_role_assignment read', False),
    ('user_role_assignment:update', 'ORG', 'user_role_assignment update', False),
    ('work_schedule:create', 'ORG', 'work_schedule create', False),
    ('work_schedule:delete', 'ORG', 'work_schedule delete', False),
    ('work_schedule:read', 'ORG', 'work_schedule read', False),
    ('work_schedule:update', 'ORG', 'work_schedule update', False),
]


def main():
    from app import create_app, db
    from app.models import Permission
    from app.utils.security import generate_secure_code

    app = create_app()
    with app.app_context():
        created, skipped = 0, 0
        for code, level, name, is_sys in PERMISSIONS:
            if Permission.query.filter_by(code=code).first():
                skipped += 1
                continue
            rtype, action = code.split(':', 1)
            db.session.add(Permission(
                secure_code=generate_secure_code(),
                resource_type=rtype,
                action=action,
                code=code,
                name=name,
                description=f'資源權限：{rtype} 的 {action}',
                permission_level=level,
                is_system_permission=is_sys,
                is_active=True,
            ))
            created += 1
        db.session.commit()
        print(f'建立 {created} 筆，跳過 {skipped} 筆（已存在）')


if __name__ == '__main__':
    main()
