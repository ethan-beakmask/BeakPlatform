#!/usr/bin/env python3
"""
清理既有 NoCode 孤兒頁面關聯。

背景：
    舊版刪除 NoCode 子系統時，只軟刪子系統本身，沒有同步軟刪該子系統底下的
    site map 節點與頁面掛載，導致平台側仍可能透過 /p/<sc> 或設計器開啟孤兒頁。

行為：
    依序清理仍存活但所屬子系統已軟刪或不存在的 dc_site_map_nodes、
    dc_sub_system_pages，flush 後再檢查候選頁面。頁面是否仍屬於存活子系統一律
    透過 page_ownership_service 的雙路徑 OR 判定；若候選頁在清掉孤兒關聯後不再
    可達，才軟刪 dc_page_layouts。所有刪除皆走 ResourceGateway，腳本可重複執行。
"""
import argparse
import os
import sys

_script_dir = os.path.dirname(os.path.abspath(__file__))
_project_dir = os.path.dirname(_script_dir)
sys.path.insert(0, _project_dir)
sys.path.insert(0, os.path.join(_project_dir, 'backend'))


def _display_item(category, secure_code, name):
    print(f'{category}: secure_code={secure_code} name={name or ""}')


def _live_sub_system_codes(DcSubSystem):
    rows = DcSubSystem.query.filter(
        DcSubSystem.is_deleted == False,  # noqa: E712
    ).all()
    return {row.secure_code for row in rows if row.secure_code}


def _find_orphan_nodes(DcSiteMapNode, live_codes):
    rows = DcSiteMapNode.query.filter(
        DcSiteMapNode.is_deleted == False,  # noqa: E712
    ).all()
    return [
        row for row in rows
        if row.sub_system_secure_code not in live_codes
    ]


def _find_orphan_mounts(DcSubSystemPage, live_codes):
    rows = DcSubSystemPage.query.filter(
        DcSubSystemPage.is_deleted == False,  # noqa: E712
    ).all()
    return [
        row for row in rows
        if row.sub_system_secure_code not in live_codes
    ]


def _candidate_page_codes(orphan_nodes, orphan_mounts):
    codes = set()
    for node in orphan_nodes:
        page_sc = (node.page_layout_secure_code or '').strip()
        if page_sc:
            codes.add(page_sc)
    for mounted_page in orphan_mounts:
        page_sc = (mounted_page.page_layout_secure_code or '').strip()
        if page_sc:
            codes.add(page_sc)
    return codes


def _load_cleanup_pages(DcPageLayout, candidate_codes, post_cleanup):
    from modules.nocode_builder.services.page_ownership_service import (
        get_owner_sub_system_codes,
        is_page_reachable,
    )

    pages = []
    for page_sc in sorted(candidate_codes):
        owner_codes = get_owner_sub_system_codes(page_sc)
        should_delete = (
            not is_page_reachable(page_sc)
            or (post_cleanup and not owner_codes)
        )
        if not should_delete:
            continue
        page = DcPageLayout.query.filter(
            DcPageLayout.secure_code == page_sc,
            DcPageLayout.is_deleted == False,  # noqa: E712
        ).first()
        if page:
            pages.append(page)
    return pages


def run_cleanup(apply_changes):
    from app import create_app, db
    from app.security.resource_gateway import ResourceGateway
    from modules.nocode_builder.models import (
        DcPageLayout,
        DcSiteMapNode,
        DcSubSystem,
        DcSubSystemPage,
    )

    app = create_app()
    with app.app_context():
        live_codes = _live_sub_system_codes(DcSubSystem)
        orphan_nodes = _find_orphan_nodes(DcSiteMapNode, live_codes)
        orphan_mounts = _find_orphan_mounts(DcSubSystemPage, live_codes)
        candidate_codes = _candidate_page_codes(orphan_nodes, orphan_mounts)

        if apply_changes:
            for node in orphan_nodes:
                ResourceGateway.delete(node, check_permission=False, soft=True)
            for mounted_page in orphan_mounts:
                ResourceGateway.delete(
                    mounted_page,
                    check_permission=False,
                    soft=True,
                )
            db.session.flush()
            orphan_pages = _load_cleanup_pages(
                DcPageLayout,
                candidate_codes,
                post_cleanup=True,
            )
            for page in orphan_pages:
                ResourceGateway.delete(page, check_permission=False, soft=True)
            ResourceGateway.commit()
        else:
            orphan_pages = _load_cleanup_pages(
                DcPageLayout,
                candidate_codes,
                post_cleanup=False,
            )
            for node in orphan_nodes:
                _display_item('A 孤兒節點', node.secure_code, node.name)
            for mounted_page in orphan_mounts:
                _display_item(
                    'B 孤兒掛載',
                    mounted_page.secure_code,
                    mounted_page.display_name,
                )
            for page in orphan_pages:
                _display_item('C 孤兒頁面', page.secure_code, page.name)

        mode = '實際寫入' if apply_changes else '試跑（未寫入）'
        print(
            f'--- 完成（{mode}）：孤兒節點 {len(orphan_nodes)} 筆，'
            f'孤兒掛載 {len(orphan_mounts)} 筆，孤兒頁面 {len(orphan_pages)} 筆'
        )


def main():
    parser = argparse.ArgumentParser(
        description='清理既有 NoCode 孤兒頁面關聯',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            '範例：\n'
            '  先看會刪什麼（不寫入）：\n'
            '    ./cleanup_orphan_nocode_pages.py --dry-run\n'
            '  實際軟刪孤兒資料：\n'
            '    ./cleanup_orphan_nocode_pages.py --apply\n'
        ),
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='只列出會軟刪的項目，不實際寫入',
    )
    parser.add_argument(
        '--apply',
        action='store_true',
        help='實際執行軟刪（與 --dry-run 二者必須指定其一）',
    )

    if len(sys.argv) == 1:
        parser.print_help()
        return 0

    args = parser.parse_args()
    if args.dry_run == args.apply:
        print('錯誤：--dry-run 與 --apply 必須指定其中一個（且不可同時指定）')
        return 2

    run_cleanup(args.apply)
    return 0


if __name__ == '__main__':
    sys.exit(main())
