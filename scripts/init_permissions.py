#!/usr/bin/env python3
"""
BeakPlatform 權限初始化腳本
用於在新安裝的環境中建立系統預設權限和 ABAC 條件

注意：
- 冪等設計：已存在的權限和條件不會重複建立
- 使用 --force 可強制重建所有權限
- 邏輯在 backend/app/defaults/permission_defaults.py，本檔只是維運入口
"""

import os
import sys

os.environ['SKIP_MODULE_SYNC'] = '1'
os.environ['EXECUTOR_STANDALONE'] = '1'

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from app import create_app
from app.defaults.permission_defaults import seed_system_permissions


def main():
    force = '--force' in sys.argv
    app = create_app()
    with app.app_context():
        result = seed_system_permissions(force=force)

    print(
        f"建立 {result['permissions_created']} 個系統權限 "
        f"(共 {result['permissions_total']} 個定義)")
    print(
        f"建立 {result['conditions_created']} 個 ABAC 條件 "
        f"(共 {result['conditions_total']} 個定義)")
    return 0


if __name__ == '__main__':
    sys.exit(main())
