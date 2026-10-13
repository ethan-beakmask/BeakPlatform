#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
產生出廠表單／流程的縮圖，寫進資料庫並更新縮圖包（scripts/examples/thumbnails/）。

這是開發機用的產生器，不是安裝步驟：安裝時只讀縮圖包（見 thumbnail_pack.py）。
表單用 Playwright 把 form.io schema 渲染成圖（與設計器儲存時的 html2image 路徑共用同一份
HTML 與後處理）；流程則開啟實際的流程設計器頁面，用 cytoscape 匯出畫布（與設計器儲存時
wf-save.js 的做法相同），所以需要一個跑著的平台與可登入的帳號。

用法：
  set -a && source .env && set +a
  venv/bin/python scripts/examples/build_showcase_thumbnails.py --org SYSTEM \\
      --base-url http://<平台主機>/beakplatform --quick-login <user secure_code>
  venv/bin/python scripts/examples/build_showcase_thumbnails.py --org DEMOSOC \\
      --base-url http://<平台主機>/beakplatform --login admin@example.com --password-env BP_PASSWORD \\
      --only PROXY_REQUEST --only PROXY_REQUEST_FLOW

參數：
  --org            目標企業（code／domain／secure_code），預設系統企業
  --base-url       平台網址（含 nginx 前綴），流程縮圖需要
  --quick-login    開發機 /dev/quick-login 的 user secure_code（與 --login 二選一）
  --login          帳密登入的帳號（密碼從 --password-env 指定的環境變數讀，不走命令列）
  --forms / --workflows  只做其中一類；都不給＝兩類都做
  --only CODE      只處理指定 code，可重複
  --all            企業內全部模板都處理；預設只處理「會進縮圖包」的模板
                   （node展覽館分類 ＋ API_KEY_REQUEST／PROXY_REQUEST 鏈路）
  --no-pack        只寫資料庫、不更新縮圖包檔案
  --no-db          只更新縮圖包檔案、不寫資料庫
  --headed         以有頭瀏覽器執行（除錯用）

依賴：venv 內要有 playwright（`venv/bin/pip install playwright`）與它的 chromium
（`venv/bin/playwright install chromium`）；這兩個不在 requirements.txt，因為安裝版用不到。
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
import time
from pathlib import Path

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
BACKEND_DIR = os.path.join(REPO_ROOT, 'backend')
sys.path.insert(0, BACKEND_DIR)
sys.path.insert(0, REPO_ROOT)

PACK_EXTRA_CODES = {
    'form': {'API_KEY_REQUEST', 'PROXY_REQUEST'},
    'workflow': {'API_KEY_REQUEST_FLOW', 'PROXY_REQUEST_FLOW'},
}

# 與 wf-save.js generateAndSaveThumbnail() 相同的 600x400、內縮 24px 白邊
WORKFLOW_THUMBNAIL_JS = """
async () => {
    const cy = window.cy;
    if (!cy || cy.nodes().length === 0) return null;
    const raw = cy.png({ output: 'base64', bg: 'white', full: true, scale: 2 });
    const src = 'data:image/png;base64,' + raw;
    return await new Promise((resolve) => {
        const img = new Image();
        img.onload = () => {
            const canvas = document.createElement('canvas');
            canvas.width = 600;
            canvas.height = 400;
            const ctx = canvas.getContext('2d');
            ctx.fillStyle = 'white';
            ctx.fillRect(0, 0, 600, 400);
            const pad = 24;
            const drawW = 600 - pad * 2;
            const drawH = 400 - pad * 2;
            const scale = Math.min(drawW / img.width, drawH / img.height);
            const w = img.width * scale;
            const h = img.height * scale;
            ctx.drawImage(img, pad + (drawW - w) / 2, pad + (drawH - h) / 2, w, h);
            resolve(canvas.toDataURL('image/png'));
        };
        img.onerror = () => resolve(null);
        img.src = src;
    });
}
"""


def parse_args(argv):
    if not argv:
        print(__doc__)
        sys.exit(1)
    parser = argparse.ArgumentParser(
        description='產生出廠表單／流程縮圖並更新縮圖包',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument('--org', help='目標企業 code／domain／secure_code；預設系統企業')
    parser.add_argument('--base-url', help='平台網址（含前綴），流程縮圖需要')
    parser.add_argument('--quick-login', help='開發機 quick-login 的 user secure_code')
    parser.add_argument('--login', help='帳密登入的帳號')
    parser.add_argument('--password-env', default='BP_PASSWORD',
                        help='存放登入密碼的環境變數名（預設 BP_PASSWORD）')
    parser.add_argument('--forms', action='store_true', help='只做表單')
    parser.add_argument('--workflows', action='store_true', help='只做流程')
    parser.add_argument('--only', action='append', default=[], help='只處理指定 code，可重複')
    parser.add_argument('--all', action='store_true', help='企業內全部模板都處理')
    parser.add_argument('--no-pack', action='store_true', help='不更新縮圖包檔案')
    parser.add_argument('--no-db', action='store_true', help='不寫資料庫')
    parser.add_argument('--headed', action='store_true', help='有頭瀏覽器（除錯用）')
    return parser.parse_args(argv)


def _in_pack_scope(template, kind, showcase_category_sc):
    if template.code in PACK_EXTRA_CODES[kind]:
        return True
    return bool(showcase_category_sc) and template.category_secure_code == showcase_category_sc


def _select_templates(org, kind, only, include_all):
    from modules.form_workflow.models import FwCategory, FwFormTemplate, FwWorkflowTemplate
    from scripts.examples.node_showcase import SHOWCASE_CATEGORY_NAME

    model = FwFormTemplate if kind == 'form' else FwWorkflowTemplate
    category = FwCategory.query.filter_by(
        org_secure_code=org.secure_code, name=SHOWCASE_CATEGORY_NAME, is_deleted=False,
    ).first()
    category_sc = category.secure_code if category else None

    query = model.query.filter_by(org_secure_code=org.secure_code, is_deleted=False)
    if only:
        query = query.filter(model.code.in_(only))
    rows = query.order_by(model.code).all()
    selected = []
    for row in rows:
        in_pack = _in_pack_scope(row, kind, category_sc)
        if not include_all and not only and not in_pack:
            continue
        selected.append((row, in_pack))
    return selected


def _login(context, base_url, args):
    """用 quick-login 或帳密在 Playwright context 建立 session。"""
    api = context.request
    if args.quick_login:
        resp = api.post(f'{base_url}/dev/quick-login',
                        data={'user_id': args.quick_login},
                        headers={'Content-Type': 'application/json'})
        if not resp.ok:
            raise RuntimeError(f'quick-login 失敗：HTTP {resp.status} {resp.text()[:200]}')
        return
    if args.login:
        password = os.environ.get(args.password_env, '')
        if not password:
            raise RuntimeError(f'環境變數 {args.password_env} 沒有密碼')
        resp = api.post(f'{base_url}/auth/login',
                        data={'account': args.login, 'password': password},
                        headers={'Content-Type': 'application/json'})
        if not resp.ok:
            raise RuntimeError(f'登入失敗：HTTP {resp.status} {resp.text()[:200]}')
        return
    raise RuntimeError('流程縮圖需要 --quick-login 或 --login 其中之一')


def _render_form(page, schema, tmpdir):
    from modules.form_workflow.services.thumbnail_service import (
        FORM_RENDER_VIEWPORT, build_form_render_html, screenshot_to_thumbnail,
    )

    html_path = Path(tmpdir) / 'form.html'
    html_path.write_text(build_form_render_html(schema), encoding='utf-8')
    page.set_viewport_size({'width': FORM_RENDER_VIEWPORT[0], 'height': FORM_RENDER_VIEWPORT[1]})
    page.goto(html_path.as_uri(), wait_until='load')
    try:
        page.wait_for_function('window.__formRendered === true', timeout=15000)
    except Exception:
        print('    警告：表單渲染逾時，以當下畫面截圖')
    page.wait_for_timeout(400)
    shot = Path(tmpdir) / 'screenshot.png'
    page.screenshot(path=str(shot), full_page=False)
    return screenshot_to_thumbnail(shot)


def _render_workflow(page, base_url, secure_code):
    page.set_viewport_size({'width': 1600, 'height': 1000})
    page.goto(f'{base_url}/forms/workflows/{secure_code}', wait_until='load')
    page.wait_for_function('window.cy && window.cy.nodes().length > 0', timeout=30000)
    # 節點圖示是 background-image，等它們載完再匯出，否則縮圖上只有空框
    page.wait_for_timeout(1500)
    return page.evaluate(WORKFLOW_THUMBNAIL_JS)


def main():
    args = parse_args(sys.argv[1:])
    do_forms = args.forms or not args.workflows
    do_workflows = args.workflows or not args.forms
    if do_workflows and not args.base_url:
        print('錯誤：流程縮圖需要 --base-url', file=sys.stderr)
        return 1
    base_url = (args.base_url or '').rstrip('/')

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print('錯誤：venv 內沒有 playwright（venv/bin/pip install playwright && venv/bin/playwright install chromium）',
              file=sys.stderr)
        return 1

    from app import create_app, db
    from scripts.examples.node_showcase import resolve_showcase_org
    from scripts.examples.thumbnail_pack import save_pack_file

    app = create_app('development')
    with app.app_context():
        org = resolve_showcase_org(args.org)
        if not org:
            print(f'錯誤：找不到企業 {args.org or "（系統企業）"}', file=sys.stderr)
            return 1
        print(f'企業：{org.code}（{org.secure_code}）')

        work = []
        if do_forms:
            work.extend(('form', row, in_pack) for row, in_pack in _select_templates(org, 'form', args.only, args.all))
        if do_workflows:
            work.extend(('workflow', row, in_pack) for row, in_pack in _select_templates(org, 'workflow', args.only, args.all))
        if not work:
            print('沒有符合條件的模板')
            return 0
        print(f'待處理：表單 {sum(1 for k, _, _ in work if k == "form")} 張、'
              f'流程 {sum(1 for k, _, _ in work if k == "workflow")} 張')

        done = 0
        failed = []
        packed = 0
        with sync_playwright() as pw, tempfile.TemporaryDirectory() as tmpdir:
            browser = pw.chromium.launch(headless=not args.headed)
            context = browser.new_context()
            if do_workflows:
                _login(context, base_url, args)
            page = context.new_page()
            for kind, row, in_pack in work:
                started = time.time()
                try:
                    if kind == 'form':
                        data_uri = _render_form(page, row.schema or {}, tmpdir)
                    else:
                        data_uri = _render_workflow(page, base_url, row.secure_code)
                except Exception as exc:
                    failed.append((kind, row.code, f'{exc.__class__.__name__}: {str(exc)[:160]}'))
                    print(f'  FAIL {kind} {row.code}: {exc.__class__.__name__}')
                    continue
                if not data_uri:
                    failed.append((kind, row.code, '沒有產出縮圖'))
                    print(f'  FAIL {kind} {row.code}: 沒有產出縮圖')
                    continue
                if not args.no_db:
                    row.thumbnail_2x1 = data_uri
                    db.session.commit()
                if not args.no_pack and in_pack:
                    save_pack_file(kind, row.code, data_uri)
                    packed += 1
                done += 1
                print(f'  OK   {kind} {row.code} ({len(data_uri) // 1024} KB, {time.time() - started:.1f}s)'
                      + ('' if in_pack else ' [不進縮圖包]'))
            if do_workflows:
                try:
                    context.request.get(f'{base_url}/auth/logout')
                except Exception:
                    pass
            browser.close()

    print(f'總結：done={done} packed={packed} failed={len(failed)}')
    for kind, code, reason in failed:
        print(f'FAILED {kind} {code}: {reason}')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
