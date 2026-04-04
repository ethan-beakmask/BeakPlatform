"""
工作站篩選邏輯

提供共用的篩選函式，讓 form-center API 的各端點
根據工作站的 filter_rules 過濾結果。
"""
import logging
from flask import request
from flask_login import current_user

from app import db
from app.platform.data import get_current_org

logger = logging.getLogger(__name__)


def get_active_workstation(org_secure_code):
    """
    從 request args 取得工作站設定。

    若 ?workstation=<code> 存在且有效，回傳 FwWorkstation 物件。
    否則回傳 None（表示全局視角）。
    """
    ws_code = request.args.get('workstation', '').strip().upper()
    if not ws_code:
        return None

    from ..models import FwWorkstation
    ws = FwWorkstation.query.filter_by(
        code=ws_code,
        org_secure_code=org_secure_code,
        is_active=True,
        is_deleted=False
    ).first()

    return ws


def load_tag_map(org_secure_code):
    """
    預載 form_template_secure_code → {tag_code, ...} 的映射。
    用於工作站的 tags 篩選。
    """
    from ..models import FwFormTemplateTag, FwFormTag

    links = FwFormTemplateTag.query.filter_by(
        org_secure_code=org_secure_code,
        is_deleted=False
    ).all()

    if not links:
        return {}

    tag_scs = list(set(link.tag_secure_code for link in links))
    tags = FwFormTag.query.filter(
        FwFormTag.secure_code.in_(tag_scs),
        FwFormTag.org_secure_code == org_secure_code,
        FwFormTag.is_deleted == False,
        FwFormTag.is_active == True
    ).all()
    tag_sc_to_code = {t.secure_code: t.code for t in tags}

    # form_template_sc → set of tag codes
    result = {}
    for link in links:
        code = tag_sc_to_code.get(link.tag_secure_code)
        if code:
            result.setdefault(link.form_template_secure_code, set()).add(code)

    return result


def filter_available_forms(items, workstation, tag_map):
    """
    根據工作站 filter_rules 過濾 available-forms 結果。

    items: list of dicts（available-forms 的回傳格式）
    workstation: FwWorkstation 物件
    tag_map: form_template_sc → set of tag codes

    回傳過濾後的 list。
    """
    if not workstation:
        return items

    rules = workstation.filter_rules or {}
    categories = set(rules.get('categories') or [])
    tags = set(rules.get('tags') or [])
    form_templates = set(rules.get('form_templates') or [])
    match_mode = rules.get('match_mode', 'all')

    if not categories and not tags and not form_templates:
        return items

    result = []
    for item in items:
        matches = []

        if categories:
            item_cats = set()
            if item.get('category_secure_code'):
                item_cats.add(item['category_secure_code'])
            if item.get('parent_category_secure_code'):
                item_cats.add(item['parent_category_secure_code'])
            matches.append(bool(item_cats & categories))

        if tags:
            item_sc = item.get('secure_code', '')
            item_tags = tag_map.get(item_sc, set())
            matches.append(bool(item_tags & tags))

        if form_templates:
            matches.append(item.get('secure_code', '') in form_templates)

        if match_mode == 'any':
            if any(matches):
                result.append(item)
        else:
            if all(matches):
                result.append(item)

    return result


def filter_pending_tasks(items, workstation, tag_map, fi_map=None):
    """
    根據工作站 filter_rules 過濾 pending-tasks 結果。

    items: list of dicts（pending-tasks 的回傳格式）
    workstation: FwWorkstation 物件
    tag_map: form_template_sc → set of tag codes
    fi_map: form_instance_sc → FwFormInstance（用於 source_type 過濾）
    """
    if not workstation:
        return items

    rules = workstation.filter_rules or {}
    categories = set(rules.get('categories') or [])
    tags = set(rules.get('tags') or [])
    source_types = set(rules.get('source_types') or [])
    form_templates = set(rules.get('form_templates') or [])
    match_mode = rules.get('match_mode', 'all')

    if not categories and not tags and not source_types and not form_templates:
        return items

    result = []
    for item in items:
        matches = []

        if categories:
            item_cat_sc = item.get('category_secure_code', '')
            matches.append(item_cat_sc in categories)

        if tags:
            fi_sc = item.get('form_instance_secure_code', '')
            fi = fi_map.get(fi_sc) if fi_map else None
            ft_sc = fi.form_template_secure_code if fi else ''
            item_tags = tag_map.get(ft_sc, set())
            matches.append(bool(item_tags & tags))

        if source_types:
            fi_sc = item.get('form_instance_secure_code', '')
            fi = fi_map.get(fi_sc) if fi_map else None
            item_source = fi.source_type if fi else 'WEB'
            matches.append(item_source in source_types)

        if form_templates:
            fi_sc = item.get('form_instance_secure_code', '')
            fi = fi_map.get(fi_sc) if fi_map else None
            ft_sc = fi.form_template_secure_code if fi else ''
            matches.append(ft_sc in form_templates)

        if match_mode == 'any':
            if any(matches):
                result.append(item)
        else:
            if all(matches):
                result.append(item)

    return result


def filter_my_forms(rows, workstation, tag_map):
    """
    根據工作站 filter_rules 過濾 my-forms 的查詢結果。

    rows: list of tuples (FwFormInstance, FwWorkflowInstance, category, category_sc, publish_version)
    workstation: FwWorkstation 物件
    tag_map: form_template_sc → set of tag codes

    回傳過濾後的 list。
    """
    if not workstation:
        return rows

    rules = workstation.filter_rules or {}
    categories = set(rules.get('categories') or [])
    tags = set(rules.get('tags') or [])
    source_types = set(rules.get('source_types') or [])
    form_templates = set(rules.get('form_templates') or [])
    match_mode = rules.get('match_mode', 'all')

    if not categories and not tags and not source_types and not form_templates:
        return rows

    result = []
    for row in rows:
        fi = row[0]  # FwFormInstance
        cat_sc = row[3]  # category_secure_code

        matches = []

        if categories:
            matches.append((cat_sc or '') in categories)

        if tags:
            item_tags = tag_map.get(fi.form_template_secure_code, set())
            matches.append(bool(item_tags & tags))

        if source_types:
            matches.append((fi.source_type or 'WEB') in source_types)

        if form_templates:
            matches.append(fi.form_template_secure_code in form_templates)

        if match_mode == 'any':
            if any(matches):
                result.append(row)
        else:
            if all(matches):
                result.append(row)

    return result
