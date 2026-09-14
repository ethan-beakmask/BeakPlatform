#!/usr/bin/env python3
"""
種入平台內建 Page IR 版面樣板。

可重複執行；以固定 secure_code 判定新增或更新。scope='system' 的樣板
不屬於任何企業或子系統，因此 org_secure_code / sub_system_secure_code 皆為 NULL。
"""
from __future__ import annotations

import argparse
import copy
import os
import sys
from datetime import datetime

_script_dir = os.path.dirname(os.path.abspath(__file__))
_project_dir = os.path.dirname(_script_dir)
sys.path.insert(0, _project_dir)
sys.path.insert(0, os.path.join(_project_dir, "backend"))


SYSTEM_TEMPLATES = [
    {
        "secure_code": "sys_tpl_top_left_main",
        "name": "上選單＋左選單＋內容",
        "description": "頁首橫向選單、左側縱向選單，右側為內容區。",
        "category": "版面",
        "layout_json": {
            "ir_version": 3,
            "page": {
                "id": "template-top-left-main",
                "title_i18n": {"zh-TW": "上選單＋左選單＋內容"},
                "engine": "grid",
                "canvas": {
                    "min_width": 1280,
                    "gap": 8,
                    "col_widths": [1, 4],
                    "row_heights": [80, 600],
                    "zones": [
                        {
                            "id": "zone-top",
                            "row": 1,
                            "col": 1,
                            "row_span": 1,
                            "col_span": 2,
                            "widget_ids": ["menu-top"],
                        },
                        {
                            "id": "zone-left",
                            "row": 2,
                            "col": 1,
                            "row_span": 1,
                            "col_span": 1,
                            "widget_ids": ["menu-left"],
                        },
                        {
                            "id": "zone-main",
                            "row": 2,
                            "col": 2,
                            "row_span": 1,
                            "col_span": 1,
                            "widget_ids": ["main-text"],
                        },
                    ],
                },
                "widgets": [
                    {
                        "id": "menu-top",
                        "type": "menu",
                        "items": [],
                        "orientation": "horizontal",
                        "title_i18n": {"zh-TW": "主選單"},
                    },
                    {
                        "id": "menu-left",
                        "type": "menu",
                        "items": [],
                        "orientation": "vertical",
                        "title_i18n": {"zh-TW": "側選單"},
                    },
                    {
                        "id": "main-text",
                        "type": "text",
                        "level": "p",
                        "content_i18n": {"zh-TW": "在此放置內容元件。"},
                    },
                ],
            },
        },
    },
    {
        "secure_code": "sys_tpl_top_main",
        "name": "上選單＋內容",
        "description": "頁首橫向選單，下方為單一內容區。",
        "category": "版面",
        "layout_json": {
            "ir_version": 3,
            "page": {
                "id": "template-top-main",
                "title_i18n": {"zh-TW": "上選單＋內容"},
                "engine": "grid",
                "canvas": {
                    "min_width": 1280,
                    "gap": 8,
                    "col_widths": [1],
                    "row_heights": [80, 600],
                    "zones": [
                        {
                            "id": "zone-top",
                            "row": 1,
                            "col": 1,
                            "row_span": 1,
                            "col_span": 1,
                            "widget_ids": ["menu-top"],
                        },
                        {
                            "id": "zone-main",
                            "row": 2,
                            "col": 1,
                            "row_span": 1,
                            "col_span": 1,
                            "widget_ids": ["main-text"],
                        },
                    ],
                },
                "widgets": [
                    {
                        "id": "menu-top",
                        "type": "menu",
                        "items": [],
                        "orientation": "horizontal",
                        "title_i18n": {"zh-TW": "主選單"},
                    },
                    {
                        "id": "main-text",
                        "type": "text",
                        "level": "p",
                        "content_i18n": {"zh-TW": "在此放置內容元件。"},
                    },
                ],
            },
        },
    },
    {
        "secure_code": "sys_tpl_left_main",
        "name": "左選單＋內容",
        "description": "左側縱向選單，右側為主要內容區。",
        "category": "版面",
        "layout_json": {
            "ir_version": 3,
            "page": {
                "id": "template-left-main",
                "title_i18n": {"zh-TW": "左選單＋內容"},
                "engine": "grid",
                "canvas": {
                    "min_width": 1280,
                    "gap": 8,
                    "col_widths": [1, 4],
                    "row_heights": [600],
                    "zones": [
                        {
                            "id": "zone-left",
                            "row": 1,
                            "col": 1,
                            "row_span": 1,
                            "col_span": 1,
                            "widget_ids": ["menu-left"],
                        },
                        {
                            "id": "zone-main",
                            "row": 1,
                            "col": 2,
                            "row_span": 1,
                            "col_span": 1,
                            "widget_ids": ["main-text"],
                        },
                    ],
                },
                "widgets": [
                    {
                        "id": "menu-left",
                        "type": "menu",
                        "items": [],
                        "orientation": "vertical",
                        "title_i18n": {"zh-TW": "側選單"},
                    },
                    {
                        "id": "main-text",
                        "type": "text",
                        "level": "p",
                        "content_i18n": {"zh-TW": "在此放置內容元件。"},
                    },
                ],
            },
        },
    },
    {
        "secure_code": "sys_tpl_single",
        "name": "單欄內容",
        "description": "適合簡單說明頁或單一主題內容頁。",
        "category": "版面",
        "layout_json": {
            "ir_version": 3,
            "page": {
                "id": "template-single",
                "title_i18n": {"zh-TW": "單欄內容"},
                "engine": "flow",
                "widgets": [
                    {
                        "id": "title-text",
                        "type": "text",
                        "level": "h2",
                        "content_i18n": {"zh-TW": "頁面標題"},
                    },
                    {
                        "id": "body-text",
                        "type": "text",
                        "level": "p",
                        "content_i18n": {"zh-TW": "在此撰寫頁面內容。"},
                    },
                ],
            },
        },
    },
    {
        "secure_code": "sys_tpl_dashboard",
        "name": "儀表板四格",
        "description": "適合放置四個摘要區塊的儀表板骨架。",
        "category": "版面",
        "layout_json": {
            "ir_version": 3,
            "page": {
                "id": "template-dashboard",
                "title_i18n": {"zh-TW": "儀表板四格"},
                "engine": "grid",
                "canvas": {
                    "min_width": 1280,
                    "gap": 8,
                    "col_widths": [1, 1],
                    "row_heights": [300, 300],
                    "zones": [
                        {
                            "id": "zone-summary",
                            "row": 1,
                            "col": 1,
                            "row_span": 1,
                            "col_span": 1,
                            "widget_ids": ["summary-text"],
                        },
                        {
                            "id": "zone-trend",
                            "row": 1,
                            "col": 2,
                            "row_span": 1,
                            "col_span": 1,
                            "widget_ids": ["trend-text"],
                        },
                        {
                            "id": "zone-status",
                            "row": 2,
                            "col": 1,
                            "row_span": 1,
                            "col_span": 1,
                            "widget_ids": ["status-text"],
                        },
                        {
                            "id": "zone-notes",
                            "row": 2,
                            "col": 2,
                            "row_span": 1,
                            "col_span": 1,
                            "widget_ids": ["notes-text"],
                        },
                    ],
                },
                "widgets": [
                    {
                        "id": "summary-text",
                        "type": "text",
                        "level": "p",
                        "content_i18n": {"zh-TW": "摘要區塊"},
                    },
                    {
                        "id": "trend-text",
                        "type": "text",
                        "level": "p",
                        "content_i18n": {"zh-TW": "趨勢區塊"},
                    },
                    {
                        "id": "status-text",
                        "type": "text",
                        "level": "p",
                        "content_i18n": {"zh-TW": "狀態區塊"},
                    },
                    {
                        "id": "notes-text",
                        "type": "text",
                        "level": "p",
                        "content_i18n": {"zh-TW": "備註區塊"},
                    },
                ],
            },
        },
    },
    {
        "secure_code": "sys_tpl_free_blank",
        "name": "自由版面空白",
        "description": "適合從自由定位畫布開始安排內容。",
        "category": "版面",
        "layout_json": {
            "ir_version": 3,
            "page": {
                "id": "template-free-blank",
                "title_i18n": {"zh-TW": "自由版面空白"},
                "engine": "free",
                "canvas": {
                    "min_width": 1280,
                    "gap": 8,
                    "columns": 12,
                    "row_unit": 40,
                    "frames": [
                        {
                            "id": "frame-main",
                            "x": 0,
                            "y": 0,
                            "w": 12,
                            "h": 8,
                            "widget_ids": ["main-text"],
                        }
                    ],
                },
                "widgets": [
                    {
                        "id": "main-text",
                        "type": "text",
                        "level": "p",
                        "content_i18n": {"zh-TW": "在此放置自由版面內容。"},
                    }
                ],
            },
        },
    },
]


def _validate_templates():
    from app.pageir import validate_page_ir

    for template in SYSTEM_TEMPLATES:
        ok, errors = validate_page_ir(template["layout_json"])
        if not ok:
            print(f'錯誤：樣板 {template["secure_code"]} 的 Page IR 不合法')
            for error in errors:
                path = error.get("path") or "<root>"
                print(f'  - {path}: {error.get("message")} ({error.get("code")})')
            return False
    return True


def _same_template(row, template):
    return (
        row.name == template["name"]
        and row.description == template["description"]
        and row.category == template["category"]
        and row.layout_json == template["layout_json"]
        and row.scope == "system"
        and row.org_secure_code is None
        and row.sub_system_secure_code is None
        and row.source_sub_system_sc is None
        and row.is_active is True
        and row.is_deleted is False
        and (row.thumbnail_svg or "") == ""
    )


def _apply_template_fields(row, template):
    row.secure_code = template["secure_code"]
    row.org_secure_code = None
    row.scope = "system"
    row.sub_system_secure_code = None
    row.source_sub_system_sc = None
    row.name = template["name"]
    row.description = template["description"]
    row.category = template["category"]
    row.layout_json = copy.deepcopy(template["layout_json"])
    row.style_config = {}
    row.thumbnail_svg = ""
    row.created_by_sc = None
    row.is_active = True
    row.is_deleted = False
    row.deleted_at = None


def _legacy_templates(DcPageTemplate):
    rows = DcPageTemplate.query.filter(
        DcPageTemplate.is_deleted == False,  # noqa: E712
    ).all()
    return [
        row for row in rows
        if isinstance(row.layout_json, dict) and "ir_version" not in row.layout_json
    ]


def run_seed(apply_changes, purge_legacy=False):
    if not _validate_templates():
        return 1

    from app import create_app, db
    from modules.nocode_builder.models.page_template import DcPageTemplate

    app = create_app()
    created = []
    updated = []
    skipped = []
    purged = []

    with app.app_context():
        for template in SYSTEM_TEMPLATES:
            row = DcPageTemplate.query.filter(
                DcPageTemplate.secure_code == template["secure_code"],
            ).first()
            if row is None:
                created.append(template)
                if apply_changes:
                    row = DcPageTemplate()
                    _apply_template_fields(row, template)
                    db.session.add(row)
            elif _same_template(row, template):
                skipped.append(template)
            else:
                updated.append(template)
                if apply_changes:
                    _apply_template_fields(row, template)

        if purge_legacy:
            legacy_rows = _legacy_templates(DcPageTemplate)
            purged = list(legacy_rows)
            if apply_changes:
                now = datetime.utcnow()
                for row in legacy_rows:
                    row.is_deleted = True
                    row.deleted_at = now

        mode = "實際寫入" if apply_changes else "試跑（未寫入）"
        print(f"--- {mode}：內建版面樣板")
        for item in created:
            print(f'建立：{item["secure_code"]} {item["name"]}')
        for item in updated:
            print(f'更新：{item["secure_code"]} {item["name"]}')
        for item in skipped:
            print(f'略過：{item["secure_code"]} {item["name"]}')
        if purge_legacy:
            for row in purged:
                print(f"軟刪舊樣板：{row.secure_code} {row.name}")

        if apply_changes:
            db.session.commit()
        else:
            db.session.rollback()

    print(
        f"--- 摘要：建立 {len(created)}、更新 {len(updated)}、"
        f"略過 {len(skipped)}、軟刪 {len(purged)}"
    )
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="種入平台內建 Page IR 版面樣板",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "範例：\n"
            "  先看會建立或更新什麼（不寫入）：\n"
            "    ./seed_system_page_templates.py --dry-run\n"
            "  實際寫入內建樣板：\n"
            "    ./seed_system_page_templates.py --apply\n"
            "  實際寫入並軟刪舊 v2 樣板：\n"
            "    ./seed_system_page_templates.py --apply --purge-legacy\n"
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只列出將建立、更新或略過的樣板，不實際寫入",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="實際建立或更新內建樣板（與 --dry-run 二者必須指定其一）",
    )
    parser.add_argument(
        "--purge-legacy",
        action="store_true",
        help="軟刪 layout_json 沒有 ir_version 欄位的舊樣板",
    )

    if len(sys.argv) == 1:
        parser.print_help()
        return 0

    args = parser.parse_args()
    if args.dry_run == args.apply:
        print("錯誤：--dry-run 與 --apply 必須指定其中一個（且不可同時指定）")
        return 2

    return run_seed(args.apply, purge_legacy=args.purge_legacy)


if __name__ == "__main__":
    sys.exit(main())
