"""
Spec Formulate Module - 規格制定模組

資料表欄位規格定義與管理工具。
目前提供資料表三相工具（SQL / JSON / 規格），
未來將擴展至 APP、AI 開發規格化。
"""

MODULE_INFO = {
    'name': 'spec_formulate',
    'display_name': '規格制定模組',
    'version': '1.0.0',
    'description': '資料表欄位規格定義與管理',
    'author': 'BeakPlatform Team',
    'dependencies': ['form_workflow'],
    'platform_version': '>=1.0.0',
    'enabled': True,

    'menu_items': [
        {
            'code': 'spec_formulate',
            'name': '規格制定模組',
            'icon': 'S',
            'parent': None,
            'sort_order': 150,
            'user_types': ['ORG_ADMIN'],
            'children': [
                {
                    'code': 'spec_formulate.data_specs',
                    'name': '資料表規格',
                    'url': '/spec-formulate/',
                    'sort_order': 1,
                },
            ]
        }
    ],

    'permissions': [
        {
            'code': 'spec_formulate.view',
            'name': '檢視規格制定',
            'description': '允許檢視規格制定模組的內容',
            'level': 'MODULE',
        },
        {
            'code': 'spec_formulate.manage',
            'name': '管理規格制定',
            'description': '允許建立、編輯、刪除規格',
            'level': 'MODULE',
        },
    ],
}
