#!/usr/bin/env python3
"""
BeakPlatform 權限初始化腳本
用於在新安裝的環境中建立系統預設權限和 ABAC 條件

注意：
- 冪等設計：已存在的權限和條件不會重複建立
- 使用 --force 可強制重建所有權限
"""

import sys
import os

# 加入 backend 路徑
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from app import create_app, db
from app.models.permission import Permission, DEFAULT_PERMISSIONS
from app.models.permission_condition import PermissionCondition, DEFAULT_CONDITIONS
import json


def init_permissions(force=False):
    """初始化系統預設權限

    Args:
        force: 若為 True，會先清除現有權限再建立
    """
    app = create_app()

    with app.app_context():
        # === 權限 ===
        existing_perm_count = Permission.query.filter_by(
            is_system_permission=True, is_deleted=False
        ).count()

        if existing_perm_count > 0 and not force and '--force' not in sys.argv:
            print(f"已存在 {existing_perm_count} 個系統權限，跳過")
        else:
            if force or '--force' in sys.argv:
                print(f"清除現有 {existing_perm_count} 個系統權限...")
                Permission.query.filter_by(is_system_permission=True).delete(
                    synchronize_session=False
                )
                db.session.commit()

            created = 0
            for perm_data in DEFAULT_PERMISSIONS:
                code = Permission.generate_code(
                    perm_data['resource_type'],
                    perm_data['action']
                )

                # 冪等：跳過已存在的
                if Permission.query.filter_by(code=code).first():
                    continue

                perm = Permission(
                    resource_type=perm_data['resource_type'],
                    action=perm_data['action'],
                    code=code,
                    name=perm_data['name'],
                    description=perm_data.get('description'),
                    permission_level=perm_data['level'],
                    is_system_permission=True,
                    is_active=True
                )
                db.session.add(perm)
                created += 1

            db.session.commit()
            print(f"建立 {created} 個系統權限 (共 {len(DEFAULT_PERMISSIONS)} 個定義)")

        # === ABAC 條件 ===
        existing_cond_count = PermissionCondition.query.filter_by(
            is_system_condition=True, is_deleted=False
        ).count()

        if existing_cond_count > 0 and not force and '--force' not in sys.argv:
            print(f"已存在 {existing_cond_count} 個 ABAC 條件，跳過")
        else:
            if force or '--force' in sys.argv:
                PermissionCondition.query.filter_by(
                    is_system_condition=True
                ).delete(synchronize_session=False)
                db.session.commit()

            created = 0
            for cond_data in DEFAULT_CONDITIONS:
                code = cond_data['code']

                if PermissionCondition.query.filter_by(code=code).first():
                    continue

                cond = PermissionCondition(
                    code=code,
                    name=cond_data['name'],
                    description=cond_data.get('description'),
                    condition_type=cond_data['condition_type'],
                    expression=json.dumps(
                        cond_data['expression'], ensure_ascii=False
                    ) if cond_data.get('expression') else None,
                    requires_param=cond_data.get('requires_param', False),
                    param_description=cond_data.get('param_description'),
                    is_system_condition=True,
                    is_active=True
                )
                db.session.add(cond)
                created += 1

            db.session.commit()
            print(f"建立 {created} 個 ABAC 條件 (共 {len(DEFAULT_CONDITIONS)} 個定義)")

        return True


if __name__ == '__main__':
    success = init_permissions()
    sys.exit(0 if success else 1)
