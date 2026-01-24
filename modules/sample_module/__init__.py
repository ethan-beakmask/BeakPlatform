"""
Sample Module - 範例模組
用於驗證模組化機制是否正常運作
"""

MODULE_INFO = {
    'name': 'sample_module',
    'display_name': '範例模組',
    'version': '1.0.0',
    'description': '用於驗證模組化機制的範例模組',
    'author': 'BeakPlatform Team',
    'dependencies': [],
    'platform_version': '>=1.0.0',
    'enabled': True,

    # 模組選單項目
    'menu_items': [
        {
            'code': 'sample_module',
            'name': '範例模組',
            'icon': 'box',
            'parent': None,
            'sort_order': 900,
            'children': [
                {
                    'code': 'sample_module.demo',
                    'name': '功能展示',
                    'url': '/sample/',
                    'sort_order': 1
                },
            ]
        }
    ],

    # 模組權限定義
    # 權限代碼格式：{module_name}.{action} 或 {module_name}.{resource}.{action}
    # 權限層級：SYSTEM（系統級）, ORG（企業級）, MODULE（模組級，預設）
    'permissions': [
        {
            'code': 'sample_module.view',
            'name': '檢視範例模組',
            'description': '允許檢視範例模組的內容',
            'level': 'MODULE',
        },
        {
            'code': 'sample_module.manage',
            'name': '管理範例模組',
            'description': '允許管理範例模組的設定和內容',
            'level': 'MODULE',
        },
    ],
}
