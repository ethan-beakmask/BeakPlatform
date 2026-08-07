"""
NoCode Builder Module - 子系統開發模組
無碼子系統開發平台：視圖管理、頁面管理、子系統開發、選項清單

選單隱藏開關（2026-08-07 起）：
環境變數 NOCODE_BUILDER_MENU 不等於 'on' 時，本模組不註冊任何平台選單。
模組本身照常載入 —— 路由、API、portal 公開頁全部可用，只是介面上看不到入口。
復原步驟見 docs/NOCODE_MENU_HIDE.md（.env 加一行 + 一句 SQL + 重啟）。
"""
import os

# 平台選單定義。是否註冊由 NOCODE_BUILDER_MENU 決定，見檔頭說明。
_MENU_ITEMS = [
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
]

_MENU_ENABLED = os.getenv('NOCODE_BUILDER_MENU', '').strip().lower() == 'on'

MODULE_INFO = {
    'name': 'nocode_builder',
    'display_name': '子系統開發模組',
    'version': '2.0.0',
    'description': '無碼子系統開發平台：視圖管理、頁面管理、子系統開發、選項清單',
    'author': 'BeakPlatform Team',
    'dependencies': [],
    'platform_version': '>=1.0.0',
    'enabled': True,

    'menu_items': _MENU_ITEMS if _MENU_ENABLED else [],

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
        from .services.pageir_portal_menu import init_portal_pageir_menu
        init_portal_pageir_menu()
    except Exception as e:
        logger.error(f'NocodeBuilder: 註冊 Page IR portal menu 失敗: {str(e)}')

    try:
        from .services.pageir_shared_component import init_portal_shared_components
        init_portal_shared_components()
    except Exception as e:
        logger.error(f'NocodeBuilder: 註冊 Page IR shared components 失敗: {str(e)}')

    try:
        from .services.pageir_formflow_resources import init_formflow_pageir_resources
        init_formflow_pageir_resources()
    except Exception as e:
        logger.error(f'NocodeBuilder: 註冊 Page IR formflow resources 失敗: {str(e)}')

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

    try:
        from app.pageir.registry import register_portal_action
        from .services.pageir_formflow_resources import resolve_submission_state

        register_portal_action('portal.form.submit', {
            'endpoint': 'nocode_public_portal.portal_widget_submit',
            'update_endpoint': 'nocode_public_portal.portal_widget_update_submission',
            'state_resolver': resolve_submission_state,
        })
        register_portal_action('portal.form.cancel', {
            'endpoint': 'nocode_public_portal.portal_widget_cancel_submission',
            'method': 'POST',
            'requires_record': True,
            'row_flag': '_can_cancel',
            'confirm': True,
        })
    except Exception as e:
        logger.error(f'NocodeBuilder: 註冊 Page IR portal action 失敗: {str(e)}')
