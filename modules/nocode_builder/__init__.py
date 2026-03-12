"""
NoCode Builder Module - 子系統開發模組
無碼子系統開發平台：視圖管理、頁面管理、子系統開發、選項清單
"""

MODULE_INFO = {
    'name': 'nocode_builder',
    'display_name': '子系統開發模組',
    'version': '2.0.0',
    'description': '無碼子系統開發平台：視圖管理、頁面管理、子系統開發、選項清單',
    'author': 'BeakPlatform Team',
    'dependencies': [],
    'platform_version': '>=1.0.0',
    'enabled': True,

    'menu_items': [
        {
            'code': 'nocode_builder',
            'name': '子系統開發模組',
            'icon': 'database-2',
            'parent': None,
            'sort_order': 200,
            'user_types': ['ORG_ADMIN'],
            'children': [
                {
                    'code': 'nocode_builder.sub_systems',
                    'name': '子系統開發',
                    'url': '/nocode-builder/sub-systems',
                    'sort_order': 1
                },
                {
                    'code': 'nocode_builder.views',
                    'name': '視圖管理',
                    'url': '/nocode-builder/',
                    'sort_order': 2
                },
                {
                    'code': 'nocode_builder.lab',
                    'name': '頁面管理',
                    'url': '/nocode-builder/lab',
                    'sort_order': 3
                },
                {
                    'code': 'nocode_builder.lookup',
                    'name': '選項清單',
                    'url': '/nocode-builder/lookup',
                    'sort_order': 4
                },
            ]
        }
    ],

    'permissions': [
        {
            'code': 'nocode_builder.view',
            'name': '檢視子系統開發模組',
            'description': '允許檢視子系統開發模組的內容',
            'level': 'MODULE',
        },
        {
            'code': 'nocode_builder.manage',
            'name': '管理子系統開發模組',
            'description': '允許管理視圖配置和資料操作',
            'level': 'MODULE',
        },
    ],
}
