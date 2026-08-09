"""
OpenDefense Module - 對外安全事件接收 + 決策廣播表

對外接收 OCSF 標準的安全事件(透過 HMAC 簽章 webhook),
經由表單流程處理後,將決策結果寫入 od_defense_decisions 表,
供外部執行端(CrowdSec / nftables / Cloudflare 等)以 Service Account JWT 拉取後落地實施。

對外整合契約: docs/integrations/open_defense_contract.md (v1.0)
Manifest: docs/manifests/mod-open-defense.yaml
"""

MODULE_INFO = {
    'name': 'open_defense',
    'display_name': '開放防禦',
    'version': '0.1.0',
    'description': '對外接收安全事件(OCSF),經表單流程後產生防禦決策,供外部執行端拉取實施',
    'author': 'BeakPlatform Team',
    'dependencies': ['form_workflow'],
    'platform_version': '>=1.0.0',
    'enabled': True,

    'menu_items': [
        {
            'code': 'open_defense',
            'name': '開放防禦',
            'icon': 'ri-shield-keyhole-line',
            'parent': None,
            'sort_order': 5,
            # header 含 EMPLOYEE：資安案件處置中心開放給持 SOC 角色的企業成員
            # （員工無可見子項時，header 由 _prune_empty_parents 自動裁剪）
            'user_types': ['ORG_ADMIN', 'EMPLOYEE'],
            'children': [
                {
                    'code': 'open_defense.dashboard',
                    'name': '儀表板',
                    'url': 'open_defense_web.dashboard',
                    'sort_order': 0,
                    # PERM-01 試點：Key1 開到 EMPLOYEE 層，是否真的開放由各企業
                    # 的 Key2（角色需求）決定——預設不種員工角色，fail-closed
                    'user_types': ['ORG_ADMIN', 'EMPLOYEE'],
                    'required_permission': 'open_defense.view',
                },
                {
                    'code': 'open_defense.decisions',
                    'name': '決策列表',
                    'url': 'open_defense_web.decisions',
                    'sort_order': 1,
                    'user_types': ['ORG_ADMIN'],
                    'required_permission': 'open_defense.decision.view',
                },
                {
                    'code': 'open_defense.security_cases',
                    'name': '資安案件處置中心',
                    'url': 'open_defense_web.security_cases',
                    'sort_order': 2,
                    # SOC 值班人員（企業成員）為主要使用者；實際可見誰由各企業
                    # 的 MenuRoleRequirement（雙鑰匙 Key2）決定
                    'user_types': ['ORG_ADMIN', 'EMPLOYEE'],
                },
                {
                    'code': 'open_defense.intake_keys',
                    'name': '事件接收金鑰',
                    'url': 'open_defense_web.intake_keys',
                    'sort_order': 3,
                    'user_types': ['ORG_ADMIN'],
                    'required_permission': 'open_defense.admin',
                },
                {
                    'code': 'open_defense.service_accounts',
                    'name': '執行端帳號',
                    'url': 'open_defense_web.service_accounts',
                    'sort_order': 4,
                    'user_types': ['ORG_ADMIN'],
                    'required_permission': 'open_defense.admin',
                },
                {
                    'code': 'open_defense.event_routing',
                    'name': '事件路由設定',
                    'url': 'open_defense_web.event_routing',
                    'sort_order': 5,
                    'user_types': ['ORG_ADMIN'],
                    'required_permission': 'open_defense.admin',
                },
            ],
        },
    ],

    # 模組預設角色：採購本模組的企業自動獲得（碰撞跳過，冪等）
    # 僅提供最小集合「資安人員」，SOC_L1/主管等分工角色由企業依
    # docs/guides/SOC_ROLE_DESIGN_GUIDE.md 自行設計
    'default_roles': [
        {
            'code': 'SECURITY_STAFF',
            'name': '資安人員',
            'description': '資安案件處置中心值班與案件簽核人員（開放防禦模組預設角色）',
        },
    ],

    # 模組預設選單角色需求（雙鑰匙 Key2）：menu code → [role codes]
    'default_menu_role_requirements': {
        'open_defense.security_cases': ['SECURITY_STAFF'],
    },

    'permissions': [
        {
            'code': 'open_defense.view',
            'name': '檢視開放防禦',
            'description': '允許檢視 OpenDefense 儀表板',
            'level': 'MODULE',
        },
        {
            'code': 'open_defense.decision.view',
            'name': '檢視防禦決策',
            'description': '允許檢視決策列表',
            'level': 'MODULE',
        },
        {
            'code': 'open_defense.decision.write',
            'name': '簽發防禦決策',
            'description': '允許在工作流中放置 decision_writer 節點 / 手動撤銷決策',
            'level': 'ORG',
        },
        {
            'code': 'open_defense.admin',
            'name': '管理開放防禦',
            'description': 'OpenDefense 完整管理權限(intake key / service account 建立與撤銷)',
            'level': 'ORG',
        },
    ],
}
