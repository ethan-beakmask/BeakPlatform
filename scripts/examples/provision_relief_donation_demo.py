#!/usr/bin/env python3
"""
NoCode 教學實例：急難救助物資捐贈系統（公開 Portal）

用途
    以 NoCode Builder 的公開 API 完整搭出一個給「外人」使用的公開子系統，
    作為設計者學習 NoCode 平台的參考實例。全程不改任何平台程式碼。

系統長什麼樣
    1. 外部民眾用 e-mail 自助註冊（帳號欄即填 e-mail），登入後
    2. 建立自己的基本資料（姓名、電話）= master
    3. 在同一頁登錄自己能提供的物資 = detail（可多筆）
    4. 每個人只看得見自己的資料（列級擁有權 row_owner_scope=own）
    5. 另有一個不具名公佈欄，只顯示「物資項目 + 累積數量」，任何人都看得到

執行
    ./venv/bin/python scripts/examples/provision_relief_donation_demo.py [--force]

    --force  已存在同名子系統時，仍建立一個新的（預設會中止）

參數說明
    --base-url   平台網址，預設 http://192.168.0.16:7000/beakplatform
    --user-sc    以開發機的免密碼快速登入 (/dev/quick-login) 取得管理員 session
    --account    平台管理員帳號（有指定時改走正式密碼登入）
    --password   平台管理員密碼
"""
from __future__ import annotations

import argparse
import re
import json
import sqlite3
import sys
from pathlib import Path

import requests

DEFAULT_BASE = 'http://192.168.0.16:7000/beakplatform'
# 開發機專用的免密碼快速登入；正式環境請改用 --account/--password
DEFAULT_USER_SC = 'jIYEQ-_lZMZNBkVy-hijal'   # admin-ethanyu@beluga.com (ORG_ADMIN)

SUB_SYSTEM_NAME = '急難救助物資捐贈'
PORTAL_ROOT = Path('/opt/BeakPlatform-dev/data/nocode_portals')

# ── 資料表設計 ────────────────────────────────────────────────
# 建表 API 一律自動附加系統欄位 id / created_at / portal_user_ref，
# 這三欄不可自行宣告（reserved_column_name）。
TABLES = [
    {
        'table_name': 'donor_profile',          # master：一位捐贈者一列
        'columns': [
            {'name': 'full_name', 'type': 'TEXT', 'required': True},
            {'name': 'phone', 'type': 'TEXT', 'required': True},
        ],
    },
    {
        'table_name': 'relief_offer',           # detail：可提供的物資
        'columns': [
            {'name': 'donor_id', 'type': 'INTEGER', 'required': True,
             'references': {'table': 'donor_profile', 'column': 'id'}},
            {'name': 'item_name', 'type': 'TEXT', 'required': True},
            {'name': 'quantity', 'type': 'INTEGER', 'required': True},
            {'name': 'unit', 'type': 'TEXT'},
            {'name': 'available_until', 'type': 'DATE'},
            {'name': 'note', 'type': 'TEXT'},
        ],
    },
    {
        'table_name': 'bulletin_board',         # 公佈欄：由 trigger 自動彙總
        'columns': [
            {'name': 'item_name', 'type': 'TEXT', 'required': True},
            {'name': 'unit', 'type': 'TEXT'},
            {'name': 'total_quantity', 'type': 'INTEGER'},
            {'name': 'offer_count', 'type': 'INTEGER'},
            {'name': 'donor_count', 'type': 'INTEGER'},
        ],
    },
]

# ── 彙總 trigger ──────────────────────────────────────────────
# NoCode 目前沒有「聚合視圖」能力（DcCrudView 只會 SELECT 單表、無 GROUP BY），
# 因此公佈欄用一張實體彙總表 + SQLite trigger 維護。
# 重算採「整組刪除後重建」，天生冪等，也不怕 UPDATE 改掉 item_name。
_RECALC = """
    DELETE FROM bulletin_board WHERE item_name = {name} AND ifnull(unit,'') = ifnull({unit},'');
    INSERT INTO bulletin_board (item_name, unit, total_quantity, offer_count, donor_count)
    SELECT item_name, unit, SUM(quantity), COUNT(*), COUNT(DISTINCT donor_id)
      FROM relief_offer
     WHERE item_name = {name} AND ifnull(unit,'') = ifnull({unit},'')
     GROUP BY item_name, unit;
"""

TRIGGER_SQL = f"""
DROP TRIGGER IF EXISTS trg_offer_ai;
DROP TRIGGER IF EXISTS trg_offer_au;
DROP TRIGGER IF EXISTS trg_offer_ad;

CREATE TRIGGER trg_offer_ai AFTER INSERT ON relief_offer BEGIN
{_RECALC.format(name='NEW.item_name', unit='NEW.unit')}
END;

CREATE TRIGGER trg_offer_au AFTER UPDATE ON relief_offer BEGIN
{_RECALC.format(name='OLD.item_name', unit='OLD.unit')}
{_RECALC.format(name='NEW.item_name', unit='NEW.unit')}
END;

CREATE TRIGGER trg_offer_ad AFTER DELETE ON relief_offer BEGIN
{_RECALC.format(name='OLD.item_name', unit='OLD.unit')}
END;
"""


def i18n(text: str) -> dict:
    return {'zh-TW': text}


class Client:
    """平台 API 薄封裝；任何非 2xx 或 success=false 一律中止，不吞錯。"""

    def __init__(self, base: str, user_sc: str = '', account: str = '', password: str = ''):
        self.base = base.rstrip('/')
        self.s = requests.Session()
        if account:
            r = self.s.post(f'{self.base}/auth/login',
                            json={'account': account, 'password': password}, timeout=20)
        else:
            r = self.s.post(f'{self.base}/dev/quick-login',
                            json={'user_id': user_sc}, timeout=20)
        if r.status_code != 200 or not r.json().get('success', True):
            raise SystemExit(f'登入失敗: {r.status_code} {r.text[:300]}')
        # 部分 API 未豁免 CSRF，token 只能從登入後的頁面 meta 取得
        page = self.s.get(f'{self.base}/dashboard', timeout=20).text
        m = re.search(r'name="csrf-token"\s+content="([^"]+)"', page)
        if not m:
            raise SystemExit('取不到 CSRF token')
        self.s.headers['X-CSRFToken'] = m.group(1)

    def call(self, method: str, path: str, payload: dict | None = None) -> dict:
        url = f'{self.base}/api/nocode-builder{path}'
        r = self.s.request(method, url, json=payload, timeout=60)
        try:
            data = r.json()
        except ValueError:
            raise SystemExit(f'{method} {path} 非 JSON 回應 ({r.status_code}): {r.text[:300]}')
        if r.status_code >= 400 or data.get('success') is False:
            raise SystemExit(f'{method} {path} 失敗 ({r.status_code}): '
                             f'{json.dumps(data, ensure_ascii=False)[:600]}')
        return data


def build_page_ir(view_sc: dict) -> tuple[dict, dict]:
    """回傳 (我的捐贈登記 IR, 物資公佈欄 IR)。"""

    # 註冊後的預設身分是 group=GENERAL / level=MEMBER（rank 10）。
    member_rule = {'groups': ['GENERAL'], 'min_level': 'MEMBER'}
    guest_rule = {'groups': None, 'min_level': 'GUEST'}

    donate_page = {
        'ir_version': 3,
        'page': {
            'id': 'relief-donate',
            'title_i18n': i18n('我的捐贈登記'),
            'widgets': [
                {
                    'id': 'intro',
                    'type': 'text',
                    'level': 'p',
                    'content_i18n': i18n(
                        '請先填寫您的聯絡資料並送出，之後從下方清單點選自己的資料，'
                        '即可繼續新增可提供的物資。此頁只看得到您自己登錄的內容。'
                    ),
                },
                {
                    # 自己的基本資料清單：own scope 只會列出自己建的那列，
                    # 點擊後透過 row_link_ref 帶 ?donation__sc=<id> 載入下方主細表。
                    'id': 'my-profile',
                    'type': 'table',
                    'binding': {
                        'resource': f'portal:{view_sc["donor_profile"]}',
                        'view': 'list',
                        'fields': ['full_name', 'phone'],
                    },
                    'columns': [
                        {'field': 'full_name', 'label_i18n': i18n('姓名'), 'sortable': True},
                        {'field': 'phone', 'label_i18n': i18n('聯絡電話')},
                    ],
                    'page_size': 5,
                    'row_link_ref': 'donation',
                    'access_matrix': {'read': member_rule},
                },
                {
                    'id': 'donation',
                    'type': 'master_detail',
                    'master': {
                        'binding': {
                            'resource': f'portal:{view_sc["donor_profile"]}',
                            'view': 'detail',
                            'fields': ['full_name', 'phone'],
                        },
                        'fields': [
                            {'field': 'full_name', 'label_i18n': i18n('姓名')},
                            {'field': 'phone', 'label_i18n': i18n('聯絡電話')},
                        ],
                        'layout_columns': 2,
                        'editable': True,
                    },
                    'detail': {
                        'binding': {
                            'resource': f'portal:{view_sc["relief_offer"]}',
                            'view': 'list',
                            'fields': ['donor_id', 'item_name', 'quantity', 'unit',
                                       'available_until', 'note'],
                        },
                        'foreign_key': 'donor_id',
                        'columns': [
                            {'field': 'item_name', 'label_i18n': i18n('物資項目')},
                            {'field': 'quantity', 'label_i18n': i18n('數量')},
                            {'field': 'unit', 'label_i18n': i18n('單位')},
                            {'field': 'available_until', 'label_i18n': i18n('可提供至')},
                            {'field': 'note', 'label_i18n': i18n('備註')},
                        ],
                        'page_size': 20,
                    },
                    'history': {
                        'enabled': True,
                        'page_size': 20,
                        'default_sort': {'field': 'item_name', 'dir': 'asc'},
                    },
                    # 寫入權限必須明確宣告（fail-closed：沒宣告就是沒人能寫）
                    'access_matrix': {
                        'read': member_rule,
                        'create': member_rule,
                        'update': member_rule,
                    },
                },
            ],
        },
    }

    bulletin_page = {
        'ir_version': 3,
        'page': {
            'id': 'relief-bulletin',
            'title_i18n': i18n('物資公佈欄'),
            'widgets': [
                {
                    'id': 'bulletin-note',
                    'type': 'text',
                    'level': 'p',
                    'content_i18n': i18n(
                        '本公佈欄僅彙總各界目前可提供的物資總量，不顯示任何捐贈者資訊。'
                    ),
                },
                {
                    'id': 'bulletin',
                    'type': 'table',
                    'binding': {
                        'resource': f'portal:{view_sc["bulletin_board"]}',
                        'view': 'list',
                        'fields': ['item_name', 'unit', 'total_quantity', 'donor_count'],
                    },
                    'columns': [
                        {'field': 'item_name', 'label_i18n': i18n('物資項目'), 'sortable': True},
                        {'field': 'total_quantity', 'label_i18n': i18n('累積數量'), 'sortable': True},
                        {'field': 'unit', 'label_i18n': i18n('單位')},
                        {'field': 'donor_count', 'label_i18n': i18n('提供人數')},
                    ],
                    'page_size': 50,
                    'default_sort': {'field': 'total_quantity', 'dir': 'desc'},
                    # 只宣告 read，寫入一律拒絕（公佈欄是唯讀的）
                    'access_matrix': {'read': guest_rule},
                },
            ],
        },
    }
    return donate_page, bulletin_page


def main() -> int:
    ap = argparse.ArgumentParser(
        description='建立 NoCode 教學實例：急難救助物資捐贈系統',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument('--base-url', default=DEFAULT_BASE, help='平台網址')
    ap.add_argument('--user-sc', default=DEFAULT_USER_SC,
                    help='開發機免密碼快速登入的管理員 secure_code')
    ap.add_argument('--account', default='', help='平台管理員帳號（指定時改走密碼登入）')
    ap.add_argument('--password', default='', help='平台管理員密碼')
    ap.add_argument('--force', action='store_true', help='已有同名子系統時仍建立新的')
    args = ap.parse_args()

    api = Client(args.base_url, args.user_sc, args.account, args.password)

    # 0. 檢查同名子系統
    existing = [
        s for s in api.call('GET', '/sub-systems')['data']
        if s.get('name') == SUB_SYSTEM_NAME
    ]
    if existing and not args.force:
        print(f'已存在同名子系統 {existing[0]["secure_code"]}，如要重建請加 --force')
        return 1

    # 1. 建立子系統（連帶自動建立 portal 路徑、SQLite、welcome 首頁）
    ss = api.call('POST', '/sub-systems', {
        'name': SUB_SYSTEM_NAME,
        'description': '公開的急難救助物資捐贈登記系統（NoCode 教學實例）',
    })['data']
    ss_sc = ss['sub_system_secure_code']
    print(f'[1/9] 子系統 {ss_sc}')

    # 2. 建立三張業務表（portal_data.db）
    for spec in TABLES:
        api.call('POST', f'/sub-systems/{ss_sc}/tables',
                 {'data_source': 'portal_data', **spec})
    print(f'[2/9] 資料表 {", ".join(t["table_name"] for t in TABLES)}')

    # 3. 建立彙總 trigger（NoCode 無聚合能力，這步必須直接下 SQL）
    db_path = PORTAL_ROOT / ss_sc / 'portal_data.db'
    with sqlite3.connect(db_path) as conn:
        conn.executescript(TRIGGER_SQL)
    print(f'[3/9] 彙總 trigger 已建立於 {db_path}')

    # 4. 為每張表產生 CRUD View
    view_sc = {}
    for spec in TABLES:
        v = api.call('POST', f'/sub-systems/{ss_sc}/resolve-view',
                     {'data_source': 'portal_data', 'table_name': spec['table_name']})['data']
        view_sc[spec['table_name']] = v['secure_code']

    # 5. 調整 View：擁有權範圍與 CRUD 開關
    api.call('PUT', f'/views/{view_sc["donor_profile"]}', {
        'name': '捐贈者基本資料', 'row_owner_scope': 'own',
        'allow_create': True, 'allow_edit': True, 'allow_delete': False,
    })
    api.call('PUT', f'/views/{view_sc["relief_offer"]}', {
        'name': '可提供物資', 'row_owner_scope': 'own',
        'allow_create': True, 'allow_edit': True, 'allow_delete': True,
    })
    api.call('PUT', f'/views/{view_sc["bulletin_board"]}', {
        'name': '物資公佈欄（彙總）', 'row_owner_scope': 'all',
        'allow_create': False, 'allow_edit': False, 'allow_delete': False,
        'page_size': 50,
    })
    print(f'[4-5/9] View: {json.dumps(view_sc, ensure_ascii=False)}')

    # 6. 建立兩個 Page IR v3 頁面並發布
    donate_ir, bulletin_ir = build_page_ir(view_sc)
    pages = {}
    for key, name, ir in (
        ('donate', '我的捐贈登記', donate_ir),
        ('bulletin', '物資公佈欄', bulletin_ir),
    ):
        p = api.call('POST', '/pages', {'name': name, 'layout_json': ir})['data']
        api.call('PATCH', f'/pages/{p["secure_code"]}/publish')
        pages[key] = p['secure_code']
    print(f'[6/9] 頁面 {json.dumps(pages, ensure_ascii=False)}')

    # 7. 掛載到子系統 + 建立 site map 節點
    for key, name, order in (('donate', '我的捐贈登記', 1), ('bulletin', '物資公佈欄', 2)):
        api.call('POST', f'/sub-systems/{ss_sc}/pages', {
            'page_layout_secure_code': pages[key],
            'display_name': name,
            'display_order': order,
            'visible_roles': ['*'],
        })
    root = next(
        n for n in api.call('GET', f'/sub-systems/{ss_sc}/site-map')['data']
        if n.get('parent_secure_code') in (None, '')
    )
    nodes = {}
    for key, name, order in (('donate', '我的捐贈登記', 1), ('bulletin', '物資公佈欄', 2)):
        n = api.call('POST', f'/sub-systems/{ss_sc}/site-map/nodes', {
            'name': name,
            'node_type': 'page',
            'parent_secure_code': root['secure_code'],
            'page_layout_secure_code': pages[key],
            'display_order': order,
        })['data']
        nodes[key] = n['secure_code']
    print(f'[7/9] Site map 節點 {json.dumps(nodes, ensure_ascii=False)}')

    # 8. 頁面級准入矩陣 + 開放自助註冊
    api.call('POST', f'/sub-systems/{ss_sc}/site-map/access-matrix/batch', {
        'node_secure_codes': [nodes['donate']],
        'access_matrix': {'read': {'groups': ['GENERAL'], 'min_level': 'MEMBER'}},
    })
    api.call('POST', f'/sub-systems/{ss_sc}/site-map/access-matrix/batch', {
        'node_secure_codes': [nodes['bulletin']],
        'access_matrix': {'read': {'groups': None, 'min_level': 'GUEST'}},
    })

    portal_db = PORTAL_ROOT / ss_sc / 'portal.db'
    with sqlite3.connect(portal_db) as conn:
        for key, value in (('allow_registration', 'true'), ('allow_anonymous', 'true')):
            conn.execute(
                'INSERT INTO portal_settings (key, value) VALUES (?, ?) '
                'ON CONFLICT(key) DO UPDATE SET value = excluded.value',
                (key, value),
            )
    print('[8/9] 准入矩陣與自助註冊設定完成')

    # 9. 上線：子系統 status 必須是 published，公開 portal 才對外開放
    api.call('POST', f'/projects/{ss_sc}/publish')
    print('[9/9] 子系統已上線')

    # 收尾：印出對外網址
    path_id = ss.get('portal_path_id')
    print('\n=== 完成 ===')
    print(f'子系統 secure_code : {ss_sc}')
    print(f'頁面 secure_code   : {json.dumps(pages, ensure_ascii=False)}')
    print(f'View secure_code   : {json.dumps(view_sc, ensure_ascii=False)}')
    print(f'portal_path_id     : {path_id}')
    print(f'公開入口           : {api.base}/public/portal/{path_id}/')
    return 0


if __name__ == '__main__':
    sys.exit(main())
