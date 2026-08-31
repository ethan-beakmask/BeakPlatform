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
    'display_name': 'BeakRisk 弱點管理系統',
    'version': '0.1.0',
    'description': '弱點生命週期管理，含風險調整簽核流程',
    'author': 'BeakPlatform Team',
    'dependencies': [],  # form_workflow 為選配，非硬依賴
    'platform_version': '>=1.0.0',
    'enabled': True,

    # 模組選單項目
    'menu_items': [
        {
            'code': 'vuln_lifecycle',
            'name': '弱點管理',
            'icon': 'ri-shield-check-line',
            'parent': None,
            'sort_order': 8,
            # PF-145：RISK_CONTROLLER 角色（EMPLOYEE 型）握有全部 vuln_lifecycle
            # permission，卻因為 Key1 只開 ORG_ADMIN 而看不到選單——API 打得到、
            # 選單看不到。開放 EMPLOYEE 讓兩者一致；實際守門交給 Key2
            # （MENU_ROLE_DEFAULTS 的 vuln_lifecycle.* -> RISK_CONTROLLER）。
            'user_types': ['ORG_ADMIN', 'EMPLOYEE'],
            'children': [
                {
                    'code': 'vuln_lifecycle.dashboard',
                    'name': '弱點儀表板',
                    'url': 'vuln_lifecycle_web.dashboard',
                    'sort_order': 0,
                    'required_permission': 'vuln_lifecycle.dashboard.view',
                },
                {
                    'code': 'vuln_lifecycle.assets',
                    'name': '資產清冊',
                    'url': 'vuln_lifecycle_web.assets',
                    'sort_order': 1,
                    'required_permission': 'vuln_lifecycle.asset.view',
                },
                {
                    'code': 'vuln_lifecycle.risk',
                    'name': '風險調整',
                    'url': 'vuln_lifecycle_web.risk_list',
                    'sort_order': 2,
                    'required_permission': 'vuln_lifecycle.risk.view',
                },
                {
                    'code': 'vuln_lifecycle.kynd',
                    'name': 'KYND',
                    'url': 'vuln_lifecycle_web.kynd',
                    'sort_order': 3,
                    'required_permission': 'vuln_lifecycle.kynd.view',
                },
            ]
        }
    ],

    # 模組預設 ACL（fail-closed 配套）：與各頁 Key2（RISK_CONTROLLER）一致
    'default_acl_roles': ['RISK_CONTROLLER'],

    # 模組權限定義
    'permissions': [
        # 檢視權限
        {
            'code': 'vuln_lifecycle.dashboard.view',
            'name': '檢視儀表板',
            'description': '檢視弱點儀表板與統計數據',
            'level': 'MODULE',
        },
        {
            'code': 'vuln_lifecycle.asset.view',
            'name': '檢視資產',
            'description': '檢視資產清冊與弱點時間軸',
            'level': 'MODULE',
        },
        {
            'code': 'vuln_lifecycle.finding.view',
            'name': '檢視弱點',
            'description': '檢視弱點發現詳情',
            'level': 'MODULE',
        },
        {
            'code': 'vuln_lifecycle.risk.view',
            'name': '檢視風險調整',
            'description': '檢視風險調整紀錄',
            'level': 'MODULE',
        },
        {
            'code': 'vuln_lifecycle.kynd.view',
            'name': '檢視 KYND',
            'description': '檢視 KYND 外部風險監控資料',
            'level': 'MODULE',
        },
        # 操作權限
        {
            'code': 'vuln_lifecycle.risk.adjust',
            'name': '提交風險調整',
            'description': '提交風險調整申請（啟動簽核流程）',
            'level': 'MODULE',
        },
        {
            'code': 'vuln_lifecycle.risk.approve',
            'name': '審核風險調整',
            'description': '核准或駁回風險調整申請',
            'level': 'ORG',
        },
        # 管理權限
        {
            'code': 'vuln_lifecycle.admin',
            'name': '模組管理',
            'description': '弱點生命週期模組完整管理權限',
            'level': 'ORG',
        },
    ],
}


def init_runtime(app):
    """模組運行時初始化"""
    import logging
    logger = logging.getLogger(__name__)
    logger.info('VulnLifecycle: module initialized')
