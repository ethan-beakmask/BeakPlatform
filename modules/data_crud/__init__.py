"""
Data CRUD Module - 無碼 CRUD 工具
從既有的資料庫表自動產生 CRUD 頁面
"""

MODULE_INFO = {
    'name': 'data_crud',
    'display_name': '資料表工具',
    'version': '1.0.0',
    'description': '從既有資料庫表自動產生增刪改查介面',
    'author': 'BeakPlatform Team',
    'dependencies': [],
    'platform_version': '>=1.0.0',
    'enabled': True,

    'menu_items': [
        {
            'code': 'data_crud',
            'name': '資料表工具',
            'icon': 'database-2',
            'parent': None,
            'sort_order': 200,
            'children': [
                {
                    'code': 'data_crud.views',
                    'name': '視圖管理',
                    'url': '/data-crud/',
                    'sort_order': 1
                },
            ]
        }
    ],

    'permissions': [
        {
            'code': 'data_crud.view',
            'name': '檢視資料表工具',
            'description': '允許檢視資料表工具的內容',
            'level': 'MODULE',
        },
        {
            'code': 'data_crud.manage',
            'name': '管理資料表工具',
            'description': '允許管理視圖配置和資料操作',
            'level': 'MODULE',
        },
    ],
}
