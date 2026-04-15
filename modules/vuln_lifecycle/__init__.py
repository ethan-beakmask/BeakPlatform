"""
VulnLifecycle Module - 弱點生命週期管理模組

整合 BeakRisk 弱點管理系統，提供：
- 弱點儀表板（severity 分布、掃描器狀態）
- 資產清冊瀏覽
- 弱點時間軸追蹤（NEW/OPEN/FIXED/RECURRED）
- 風險調整簽核流程（透過 form_workflow 模組）
- 稽核紀錄（ISO 合規）

資料來源：外部 vulnmgmt PostgreSQL 資料庫（由 BeakRisk core 管理）
"""

MODULE_INFO = {
    'name': 'vuln_lifecycle',
    'display_name': 'Vulnerability Lifecycle',
    'version': '0.1.0',
    'description': 'Vulnerability lifecycle management with risk adjustment workflow',
    'author': 'BeakPlatform Team',
    'dependencies': [],  # form_workflow 為選配，非硬依賴
    'platform_version': '>=1.0.0',
    'enabled': True,

    # 模組選單項目
    'menu_items': [
        {
            'code': 'vuln_lifecycle',
            'name': 'Vuln Lifecycle',
            'icon': 'ri-shield-check-line',
            'parent': None,
            'sort_order': 8,
            'user_types': ['ORG_ADMIN'],
            'children': [
                {
                    'code': 'vuln_lifecycle.dashboard',
                    'name': 'Dashboard',
                    'url': 'vuln_lifecycle_web.dashboard',
                    'sort_order': 0,
                    'required_permission': 'vuln_lifecycle.dashboard.view',
                },
                {
                    'code': 'vuln_lifecycle.assets',
                    'name': 'Assets',
                    'url': 'vuln_lifecycle_web.assets',
                    'sort_order': 1,
                    'required_permission': 'vuln_lifecycle.asset.view',
                },
                {
                    'code': 'vuln_lifecycle.risk',
                    'name': 'Risk Adjustments',
                    'url': 'vuln_lifecycle_web.risk_list',
                    'sort_order': 2,
                    'required_permission': 'vuln_lifecycle.risk.view',
                },
            ]
        }
    ],

    # 模組權限定義
    'permissions': [
        # 檢視權限
        {
            'code': 'vuln_lifecycle.dashboard.view',
            'name': 'View Dashboard',
            'description': 'View vulnerability dashboard and statistics',
            'level': 'MODULE',
        },
        {
            'code': 'vuln_lifecycle.asset.view',
            'name': 'View Assets',
            'description': 'View asset inventory and vulnerability timeline',
            'level': 'MODULE',
        },
        {
            'code': 'vuln_lifecycle.finding.view',
            'name': 'View Findings',
            'description': 'View vulnerability findings detail',
            'level': 'MODULE',
        },
        {
            'code': 'vuln_lifecycle.risk.view',
            'name': 'View Risk Adjustments',
            'description': 'View risk adjustment records',
            'level': 'MODULE',
        },
        # 操作權限
        {
            'code': 'vuln_lifecycle.risk.adjust',
            'name': 'Submit Risk Adjustment',
            'description': 'Submit risk adjustment request (initiates workflow)',
            'level': 'MODULE',
        },
        {
            'code': 'vuln_lifecycle.risk.approve',
            'name': 'Approve Risk Adjustment',
            'description': 'Approve or reject risk adjustment requests',
            'level': 'ORG',
        },
        # 管理權限
        {
            'code': 'vuln_lifecycle.admin',
            'name': 'Module Admin',
            'description': 'Full management of vulnerability lifecycle module',
            'level': 'ORG',
        },
    ],
}


def init_runtime(app):
    """模組運行時初始化"""
    import logging
    logger = logging.getLogger(__name__)
    logger.info('VulnLifecycle: module initialized')
