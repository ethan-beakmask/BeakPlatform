#!/usr/bin/env python3
"""
急難救助物資捐贈教學實例 -- 端對端驗收

驗收項目
    1. 外部民眾可用 e-mail 自助註冊、登入
    2. 主細表送出：建立基本資料（master）+ 多筆物資（detail）
    3. 列級隔離：甲看不到乙的基本資料與物資
    4. 公佈欄：不具名、可匿名瀏覽、數量為所有人累積值
    5. 公佈欄唯讀：對公佈欄 widget 寫入應被拒（404）

執行
    ./venv/bin/python scripts/examples/verify_relief_donation_demo.py \\
        --path-id 8AMAUAh9 --donate-page <sc> --bulletin-page <sc>
"""
from __future__ import annotations

import argparse
import json
import re
import sys

import requests

BASE = 'http://192.168.0.16:7000/beakplatform'

RESULTS: list[tuple[bool, str]] = []


def check(ok: bool, label: str, detail: str = '') -> None:
    RESULTS.append((ok, label))
    mark = 'PASS' if ok else 'FAIL'
    print(f'[{mark}] {label}' + (f'  -- {detail}' if detail else ''))


class Portal:
    """一個 portal 訪客的瀏覽器 session。"""

    def __init__(self, base: str, path_id: str):
        self.base = base.rstrip('/')
        self.root = f'{self.base}/public/portal/{path_id}'
        self.s = requests.Session()
        self.token = ''

    def register(self, email: str, password: str, display_name: str) -> requests.Response:
        return self.s.post(f'{self.root}/register', data={
            'username': email,
            'password': password,
            'password_confirm': password,
            'display_name': display_name,
            'email': email,
        }, timeout=20, allow_redirects=False)

    def login(self, email: str, password: str) -> requests.Response:
        return self.s.post(f'{self.root}/login',
                           data={'username': email, 'password': password},
                           timeout=20, allow_redirects=False)

    def open_page(self, page_sc: str) -> requests.Response:
        r = self.s.get(f'{self.root}/p/{page_sc}', timeout=20)
        m = re.search(r'name="csrf-token"\s+content="([^"]+)"', r.text)
        if m:
            self.token = m.group(1)
        return r

    def rows(self, page_sc: str, widget_id: str, **params) -> requests.Response:
        return self.s.get(f'{self.root}/api/pages/{page_sc}/widgets/{widget_id}/rows',
                          params=params, timeout=20)

    def master_detail(self, page_sc: str, widget_id: str, payload: dict) -> requests.Response:
        return self.s.post(
            f'{self.root}/api/pages/{page_sc}/widgets/{widget_id}/master-detail',
            json=payload, headers={'X-CSRFToken': self.token}, timeout=30)

    def create_row(self, page_sc: str, widget_id: str, data: dict) -> requests.Response:
        return self.s.post(f'{self.root}/api/pages/{page_sc}/widgets/{widget_id}/rows',
                           json={'data': data},
                           headers={'X-CSRFToken': self.token}, timeout=20)


def main() -> int:
    ap = argparse.ArgumentParser(description='急難救助物資捐贈教學實例端對端驗收')
    ap.add_argument('--base-url', default=BASE, help='平台網址')
    ap.add_argument('--path-id', required=True, help='公開 portal 的 path_id')
    ap.add_argument('--donate-page', required=True, help='「我的捐贈登記」頁 secure_code')
    ap.add_argument('--bulletin-page', required=True, help='「物資公佈欄」頁 secure_code')
    ap.add_argument('--suffix', default='t1', help='測試帳號後綴，重跑時換一個')
    args = ap.parse_args()

    donate, bulletin = args.donate_page, args.bulletin_page
    pw = 'relief123456'

    # ── 1. 兩位民眾各自以 e-mail 註冊 ──────────────────────────
    people = {}
    for key, name, items in (
        ('a', '陳志明', [
            {'item_name': '礦泉水', 'quantity': 120, 'unit': '箱', 'note': '可自送'},
            {'item_name': '睡袋', 'quantity': 30, 'unit': '個', 'note': ''},
        ]),
        ('b', '林淑芬', [
            {'item_name': '礦泉水', 'quantity': 80, 'unit': '箱', 'note': '需協助運送'},
            {'item_name': '嬰兒尿布', 'quantity': 45, 'unit': '包', 'note': 'M 號'},
        ]),
    ):
        email = f'donor_{key}_{args.suffix}@example.com'
        p = Portal(args.base_url, args.path_id)
        r = p.register(email, pw, name)
        ok = r.status_code in (200, 302)
        check(ok, f'{name} 以 e-mail 註冊', f'HTTP {r.status_code}')
        if not ok:
            return 1
        p.open_page(donate)
        people[key] = {'portal': p, 'name': name, 'items': items, 'email': email}

    # ── 2. 主細表送出（基本資料 + 物資） ───────────────────────
    for key, person in people.items():
        p = person['portal']
        r = p.master_detail(donate, 'donation', {
            'master': {'sc': None, 'data': {
                'full_name': person['name'],
                'phone': f'09{key.encode().hex()}0000'[:10],
            }},
            'details': person['items'],
        })
        body = r.json() if r.headers.get('content-type', '').startswith('application/json') else {}
        ok = r.status_code in (200, 201) and body.get('success') is True
        check(ok, f'{person["name"]} 送出基本資料與 {len(person["items"])} 筆物資',
              f'HTTP {r.status_code} {json.dumps(body, ensure_ascii=False)[:160]}')
        if not ok:
            return 1
        person['master_sc'] = (body.get('data') or {}).get('master_sc')

    # ── 3. 列級隔離：各自只看得到自己的基本資料 ────────────────
    for key, person in people.items():
        r = person['portal'].rows(donate, 'my-profile')
        rows = r.json().get('rows', [])
        names = [row.get('full_name') for row in rows]
        ok = names == [person['name']]
        check(ok, f'{person["name"]} 的基本資料清單只有自己', f'看到 {names}')

    # ── 4. 列級隔離：物資明細也不互相外洩 ─────────────────────
    a, b = people['a'], people['b']
    r = a['portal'].s.get(f"{a['portal'].root}/p/{donate}",
                          params={'donation__sc': b['master_sc']}, timeout=20)
    ok = r.status_code == 200 and b['name'] not in r.text and '需協助運送' not in r.text
    check(ok, '甲帶乙的 master id 開頁面也看不到乙的資料', f'HTTP {r.status_code}')

    # ── 5. 公佈欄：匿名可讀、數值為累積值、不含捐贈者欄位 ──────
    anon = Portal(args.base_url, args.path_id)
    anon.open_page(bulletin)
    r = anon.rows(bulletin, 'bulletin', page=1)
    payload = r.json() if r.status_code == 200 else {}
    rows = payload.get('rows', [])
    board = {row.get('item_name'): row for row in rows}
    check(r.status_code == 200 and bool(rows), '匿名訪客可讀公佈欄',
          f'HTTP {r.status_code} 共 {len(rows)} 列')

    water = board.get('礦泉水') or {}
    check(water.get('total_quantity') == 200 and water.get('donor_count') == 2,
          '礦泉水累積 120+80=200、提供人數 2',
          json.dumps(water, ensure_ascii=False))

    leaked = {k for row in rows for k in row
              if k in {'full_name', 'phone', 'portal_user_ref', 'donor_id', 'note'}}
    check(not leaked, '公佈欄不含任何捐贈者識別欄位', f'外洩欄位 {leaked}')

    # ── 6. 公佈欄唯讀：寫入必須被拒 ────────────────────────────
    r = a['portal'].create_row(bulletin, 'bulletin',
                              {'item_name': '偽造項目', 'total_quantity': 99999})
    check(r.status_code == 404, '對公佈欄寫入被拒（fail-closed）', f'HTTP {r.status_code}')

    failed = [label for ok, label in RESULTS if not ok]
    print(f'\n=== {len(RESULTS) - len(failed)}/{len(RESULTS)} 通過 ===')
    if failed:
        for label in failed:
            print(f'  未通過: {label}')
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
