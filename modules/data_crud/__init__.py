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
                {
                    'code': 'data_crud.lab',
                    'name': '頁面設計',
                    'url': '/data-crud/lab',
                    'sort_order': 2
                },
                {
                    'code': 'data_crud.sub_systems',
                    'name': '子系統管理',
                    'url': '/data-crud/sub-systems',
                    'sort_order': 3
                },
                {
                    'code': 'data_crud.lookup',
                    'name': '選項清單',
                    'url': '/data-crud/lookup',
                    'sort_order': 4
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
