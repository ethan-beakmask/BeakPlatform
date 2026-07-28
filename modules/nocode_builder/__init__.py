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
            'icon': 'ri-database-2-line',
            'parent': None,
            'sort_order': 5,
            'user_types': ['ORG_ADMIN'],
            'children': [
                {
                    'code': 'nocode_builder.sub_systems',
                    'name': '子系統開發',
                    'url': 'nocode_builder_web.sub_system_list',
                    'sort_order': 0
                },
                {
                    'code': 'nocode_builder.lookup',
                    'name': '選項-清單-資料樹',
                    'url': 'nocode_builder_web.lookup_manager',
                    'sort_order': 1
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


def init_runtime(app):
    """
    模組運行時初始化 hook

    在應用啟動時被 module_loader 調用。
    """
    import logging
    logger = logging.getLogger(__name__)

    # 註冊 subsystem_file 的檔案物件級授權判定
    try:
        from app.services import file_service
        from .services.file_authorizer import register
        register(file_service)
    except Exception as e:
        logger.error(f'NocodeBuilder: 註冊檔案 authorizer 失敗: {str(e)}')

    try:
        from .services.pageir_portal_resources import init_portal_pageir_resources
        init_portal_pageir_resources()
    except Exception as e:
        logger.error(f'NocodeBuilder: 註冊 Page IR portal resources 失敗: {str(e)}')

    try:
        from app.pageir.registry import register_access_evaluator
        from .services import portal_access_service

        def _portal_widget_evaluator(matrix, action, ctx):
            if action == 'read':
                return portal_access_service.check_widget_access(matrix, action, ctx)
            return portal_access_service.check_widget_write_access(matrix, action, ctx)

        register_access_evaluator('portal', _portal_widget_evaluator)
    except Exception as e:
        logger.error(f'NocodeBuilder: 註冊 Page IR portal access evaluator 失敗: {str(e)}')
