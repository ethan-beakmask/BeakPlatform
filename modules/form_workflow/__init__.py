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
                    'code': 'form_workflow.my_forms',
                    'name': '我的表單',
                    'url': '/forms/my/',
                    'sort_order': 2
                },
                {
                    'code': 'form_workflow.pending',
                    'name': '待簽核',
                    'url': '/forms/pending/',
                    'sort_order': 3
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
