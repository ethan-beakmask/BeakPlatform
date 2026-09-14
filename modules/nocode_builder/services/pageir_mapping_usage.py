"""Page IR mapping usage lookup for NoCode pages."""
from __future__ import annotations

import logging

from sqlalchemy import Text, cast

from modules.nocode_builder.models.page_layout import DcPageLayout

logger = logging.getLogger(__name__)


def find_pages_using_mapping(org_secure_code: str, mapping_sc: str) -> list[dict]:
    """回傳引用指定 mapping 的頁面清單 [{'secure_code':..., 'name':...}]。"""
    try:
        pages = DcPageLayout.query.filter(
            DcPageLayout.org_secure_code == org_secure_code,
            DcPageLayout.is_deleted.is_(False),
            cast(DcPageLayout.layout_json, Text).like(f'%{mapping_sc}%'),
        ).all()

        found = []
        for page in pages:
            if _layout_uses_mapping(page.layout_json, mapping_sc):
                found.append({'secure_code': page.secure_code, 'name': page.name})
        return found
    except Exception:
        logger.exception('NoCode Page IR mapping usage lookup failed: mapping=%s', mapping_sc)
        return []


def _layout_uses_mapping(layout_json: dict, mapping_sc: str) -> bool:
    if not isinstance(layout_json, dict):
        return False
    page = layout_json.get('page') or {}
    return _widgets_use_mapping(page.get('widgets'), mapping_sc)


def _widgets_use_mapping(widgets, mapping_sc: str) -> bool:
    if not isinstance(widgets, list):
        return False
    for widget in widgets:
        if not isinstance(widget, dict):
            continue
        if widget.get('type') == 'form' and widget.get('mapping_ref') == mapping_sc:
            return True
        if widget.get('type') == 'layout' and _widgets_use_mapping(widget.get('children'), mapping_sc):
            return True
    return False
