#!/usr/bin/env python3
"""
BeakPlatform 選單初始化腳本
用於在新安裝的環境中建立核心平台選單

注意：
- 只包含平台級選單，不包含模組選單（form_workflow, nocode_builder, spec_formulate 等）
- 模組選單由 ModuleMenuService.sync_all_module_menus() 在 Flask 啟動時自動建立
- 使用 --force 可強制重建所有平台選單
- 邏輯在 backend/app/defaults/platform_menu_defaults.py，本檔只是維運入口
"""

import os
import sys

os.environ['SKIP_MODULE_SYNC'] = '1'
os.environ['EXECUTOR_STANDALONE'] = '1'

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from app import create_app
from app.defaults.platform_menu_defaults import seed_platform_menus


def main():
    app = create_app()
    with app.app_context():
        try:
            result = seed_platform_menus(force='--force' in sys.argv)
        except ValueError as exc:
            print(f"錯誤: {exc}")
            return 1

    if result['skipped']:
        print(f"已存在 {result['existing']} 個選單項目")
        print("使用 --force 參數可強制重建選單")
    else:
        if result['existing']:
            print(f"清除現有的 {result['existing']} 個選單項目...")
            print("選單已清除")
        print(f"成功建立 {result['created']} 個選單項目")
        print(f"建立 {result['mrr_created']} 筆選單角色需求")
        print("模組選單（表單流程、資料表工具等）將在 Flask 啟動時自動同步")
    return 0


if __name__ == '__main__':
    sys.exit(main())
