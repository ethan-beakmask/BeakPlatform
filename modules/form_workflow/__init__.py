"""
FormWorkflow Module - 表單流程系統模組

移轉自 FormFlow A6，提供：
- 表單設計與管理
- 工作流設計與執行
- 簽核流程
- 流程節點處理器

使用方式：
    將此模組放置於 BeakPlatform/modules/ 目錄下，
    平台啟動時會自動載入。
"""

MODULE_INFO = {
    'name': 'form_workflow',
    'display_name': '表單流程系統',
    'version': '1.0.0',
    'description': '提供表單設計、工作流程設計、簽核流程等功能',
    'author': 'BeakPlatform Team',
    'dependencies': [],  # 無依賴其他模組
    'platform_version': '>=1.0.0',
    'enabled': True,

    # 模組選單項目
    'menu_items': [
        {
            'code': 'form_workflow',
            'name': '表單流程',
            'icon': 'F',
            'parent': None,
            'sort_order': 100,
            'children': [
                {
                    'code': 'form_workflow.dashboard',
                    'name': '儀表板',
                    'url': '/forms/',
                    'sort_order': 1
                },
                {
                    'code': 'form_workflow.center',
                    'name': '表單中心',
                    'url': '/forms/center',
                    'sort_order': 2
                },
                {
                    'code': 'form_workflow.my_forms',
                    'name': '我的表單',
                    'url': '/forms/my/',
                    'sort_order': 3
                },
                {
                    'code': 'form_workflow.pending',
                    'name': '待簽核',
                    'url': '/forms/pending/',
                    'sort_order': 4
                },
                {
                    'code': 'form_workflow.templates',
                    'name': '表單範本',
                    'url': '/forms/templates/',
                    'sort_order': 10,
                    'required_permission': 'form_workflow.template.manage'
                },
                {
                    'code': 'form_workflow.workflows',
                    'name': '流程設計',
                    'url': '/forms/workflows/',
                    'sort_order': 11,
                    'required_permission': 'form_workflow.workflow.manage'
                },
                {
                    'code': 'form_workflow.mappings',
                    'name': '配對管理',
                    'url': '/forms/mappings',
                    'sort_order': 12,
                    'required_permission': 'form_workflow.workflow.manage'
                },
                {
                    'code': 'form_workflow.data_specs',
                    'name': '資料表規格',
                    'url': '/forms/data-specs',
                    'sort_order': 13,
                    'required_permission': 'form_workflow.template.manage'
                },
                {
                    'code': 'form_workflow.form_themes',
                    'name': '表單風格管理',
                    'url': '/forms/form-themes',
                    'sort_order': 15,
                    'required_permission': 'form_workflow.admin'
                },
                {
                    'code': 'form_workflow.categories',
                    'name': '分類管理',
                    'url': '/forms/categories',
                    'sort_order': 20,
                    'required_permission': 'form_workflow.admin'
                },
            ]
        }
    ],

    # 模組權限定義
    'permissions': [
        # 表單填寫權限
        {
            'code': 'form_workflow.form.create',
            'name': '填寫表單',
            'description': '允許填寫並提交表單',
            'level': 'MODULE',
        },
        {
            'code': 'form_workflow.form.view',
            'name': '檢視表單',
            'description': '允許檢視自己的表單',
            'level': 'MODULE',
        },
        {
            'code': 'form_workflow.form.view_all',
            'name': '檢視所有表單',
            'description': '允許檢視企業內所有表單',
            'level': 'ORG',
        },

        # 簽核權限
        {
            'code': 'form_workflow.approval.approve',
            'name': '簽核表單',
            'description': '允許簽核/退回表單',
            'level': 'MODULE',
        },
        {
            'code': 'form_workflow.approval.transfer',
            'name': '轉交簽核',
            'description': '允許將簽核轉交他人',
            'level': 'MODULE',
        },

        # 表單範本管理權限
        {
            'code': 'form_workflow.template.view',
            'name': '檢視表單範本',
            'description': '允許檢視表單範本',
            'level': 'MODULE',
        },
        {
            'code': 'form_workflow.template.manage',
            'name': '管理表單範本',
            'description': '允許新增、編輯、刪除表單範本',
            'level': 'ORG',
        },
        {
            'code': 'form_workflow.template.publish',
            'name': '發布表單範本',
            'description': '允許發布表單範本供填寫',
            'level': 'ORG',
        },

        # 工作流程管理權限
        {
            'code': 'form_workflow.workflow.view',
            'name': '檢視工作流程',
            'description': '允許檢視工作流程定義',
            'level': 'MODULE',
        },
        {
            'code': 'form_workflow.workflow.manage',
            'name': '管理工作流程',
            'description': '允許新增、編輯、刪除工作流程',
            'level': 'ORG',
        },

        # 系統管理權限
        {
            'code': 'form_workflow.admin',
            'name': '模組管理員',
            'description': '表單流程模組的完整管理權限',
            'level': 'ORG',
        },
    ],
}


def init_runtime(app):
    """
    模組運行時初始化 hook

    在應用啟動時被 module_loader 調用，用於啟動背景服務。
    """
    import os
    import logging
    logger = logging.getLogger(__name__)

    # 僅在非測試環境且未使用獨立 executor 進程時啟動
    # Flask debug reloader 會產生父+子兩個進程，只在子進程（WERKZEUG_RUN_MAIN=true）啟動
    is_reloader_parent = (
        app.debug and
        os.environ.get('WERKZEUG_RUN_MAIN') != 'true'
    )

    if is_reloader_parent:
        logger.info('FormWorkflow: Reloader 父進程，跳過啟動執行器')
    elif not app.config.get('TESTING', False) and not os.environ.get('EXECUTOR_STANDALONE'):
        try:
            from .services.workflow_executor import start_executor
            start_executor(app=app)
            logger.info('FormWorkflow: 工作流執行器已啟動（Flask 內建模式）')
        except Exception as e:
            logger.error(f'FormWorkflow: 啟動工作流執行器失敗: {str(e)}')
    else:
        logger.info('FormWorkflow: 工作流執行器由獨立進程管理')

    # SQL Sync: per-org 架構，不需全域連線池（連線由 Worker 按需建立）
    logger.info('FormWorkflow: SQL Sync 使用 per-org 佇列模式（Worker 獨立處理）')
