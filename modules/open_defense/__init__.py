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
            'user_types': ['ORG_ADMIN'],
            'children': [
                {
                    'code': 'open_defense.dashboard',
                    'name': '儀表板',
                    'url': 'open_defense_web.dashboard',
                    'sort_order': 0,
                    'required_permission': 'open_defense.view',
                },
                {
                    'code': 'open_defense.decisions',
                    'name': '決策列表',
                    'url': 'open_defense_web.decisions',
                    'sort_order': 1,
                    'required_permission': 'open_defense.decision.view',
                },
                {
                    'code': 'open_defense.intake_keys',
                    'name': '事件接收金鑰',
                    'url': 'open_defense_web.intake_keys',
                    'sort_order': 2,
                    'required_permission': 'open_defense.admin',
                },
                {
                    'code': 'open_defense.service_accounts',
                    'name': '執行端帳號',
                    'url': 'open_defense_web.service_accounts',
                    'sort_order': 3,
                    'required_permission': 'open_defense.admin',
                },
            ],
        },
    ],

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
