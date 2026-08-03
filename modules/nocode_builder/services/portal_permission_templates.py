"""Portal permission template definitions for PF-8."""

PERMISSION_TEMPLATES = {
    'PUBLIC_READONLY': {
        'name': '公開唯讀',
        'description': '任何訪客都能瀏覽的公開頁面',
        'permissions': [
            {
                'code': 'portal_page.view_public',
                'description': '瀏覽公開頁面',
                'risk_level': 'low',
            },
        ],
        'levels': {'GUEST': ['portal_page.view_public']},
        'roles': {},
    },
    'MEMBER_ONLY': {
        'name': '會員專屬',
        'description': '登入會員才能瀏覽與登錄自己的資料',
        'permissions': [
            {
                'code': 'portal_page.view_member',
                'description': '瀏覽會員頁面',
                'risk_level': 'normal',
            },
            {
                'code': 'portal_record.read_own',
                'description': '查看自己建立的資料',
                'risk_level': 'normal',
            },
            {
                'code': 'portal_record.create',
                'description': '建立資料',
                'risk_level': 'normal',
            },
        ],
        'levels': {
            'MEMBER': [
                'portal_page.view_member',
                'portal_record.read_own',
                'portal_record.create',
            ],
        },
        'roles': {},
    },
    'ADMIN_ONLY': {
        'name': '管理限定',
        'description': '管理者才能瀏覽的後台頁面與全域資料操作',
        'permissions': [
            {
                'code': 'portal_page.view_admin',
                'description': '瀏覽管理頁面',
                'risk_level': 'high',
            },
            {
                'code': 'portal_record.read_all',
                'description': '查看全部資料',
                'risk_level': 'high',
            },
            {
                'code': 'portal_record.update',
                'description': '修改資料',
                'risk_level': 'high',
            },
            {
                'code': 'portal_record.delete',
                'description': '刪除資料',
                'risk_level': 'critical',
            },
        ],
        'levels': {
            'ADMIN': [
                'portal_page.view_admin',
                'portal_record.read_all',
                'portal_record.update',
                'portal_record.delete',
            ],
        },
        'roles': {
            'SYSTEM_ADMIN': [
                'portal_page.view_admin',
                'portal_record.read_all',
                'portal_record.update',
                'portal_record.delete',
            ],
        },
    },
}

DEFAULT_ADMIN_ROLES = [
    ('MEMBER_MANAGER', '會員管理員'),
    ('MATERIAL_MANAGER', '資料管理員'),
    ('BULLETIN_MANAGER', '公告管理員'),
    ('REPORT_MANAGER', '報表管理員'),
    ('AUDITOR', '稽核員'),
    ('SYSTEM_ADMIN', '系統管理員'),
]


def list_templates() -> list[dict]:
    """回傳模板摘要（code / name / description / 權限碼數），供 UI 顯示。"""
    return [
        {
            'code': code,
            'name': item['name'],
            'description': item['description'],
            'permission_count': len(item.get('permissions') or []),
        }
        for code, item in PERMISSION_TEMPLATES.items()
    ]
