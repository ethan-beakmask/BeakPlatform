"""Shared scope resolution for API Key form triggers."""
from dataclasses import dataclass


@dataclass(frozen=True)
class ScopeFilter:
    category_scs: set
    form_scs: set
    template_scs: set


def resolve_scope_filter(api_key):
    """取出 key 的表單授權範圍。"""
    scopes = api_key.scopes or {}
    category_scs = set(scopes.get('form_category') or [])
    form_scs = set(scopes.get('form') or [])
    template_scs = set(scopes.get('form_template') or [])
    return ScopeFilter(
        category_scs=category_scs,
        form_scs=form_scs,
        template_scs=template_scs,
    )


def published_in_scope(published, scope_filter):
    """判斷 published 表單是否在 key 的授權範圍內(父分類含子分類)"""
    if published.secure_code in scope_filter.form_scs:
        return True
    if (published.source_form_template_secure_code
            in scope_filter.template_scs):
        return True
    if not scope_filter.category_scs:
        return False

    from ..models import FwFormTemplate, FwCategory
    form_template = FwFormTemplate.query.filter_by(
        secure_code=published.source_form_template_secure_code,
        is_deleted=False
    ).first()
    if not form_template or not form_template.category_secure_code:
        return False

    cat_sc = form_template.category_secure_code
    if cat_sc in scope_filter.category_scs:
        return True

    # 父分類授權涵蓋子分類
    category = FwCategory.query.filter_by(
        secure_code=cat_sc, is_deleted=False
    ).first()
    if category and category.parent_secure_code:
        return category.parent_secure_code in scope_filter.category_scs
    return False


def template_in_scope(template, scope_filter):
    """未發行時靠 template 或分類判 scope(父分類含子分類)。"""
    if template.secure_code in scope_filter.template_scs:
        return True

    from ..models import FwCategory

    cat_sc = template.category_secure_code
    if not cat_sc or not scope_filter.category_scs:
        return False
    if cat_sc in scope_filter.category_scs:
        return True
    category = FwCategory.query.filter_by(
        secure_code=cat_sc, is_deleted=False
    ).first()
    return bool(category and category.parent_secure_code
                and category.parent_secure_code in scope_filter.category_scs)


def list_triggerable_forms(api_key, org_secure_code) -> list[dict]:
    """列出這把 key 能發動的 published 表單（含 field_keys）。"""
    from ..models import FwPublishedFormWorkflow
    from ..services.form_submit_service import extract_schema_field_keys

    scope_filter = resolve_scope_filter(api_key)

    published_list = FwPublishedFormWorkflow.query.filter_by(
        org_secure_code=org_secure_code,
        status='Published',
        is_deleted=False,
    ).all()

    items = []
    for pub in published_list:
        if not published_in_scope(pub, scope_filter):
            continue
        form_snapshot = pub.form_snapshot or {}
        items.append({
            'published_secure_code': pub.secure_code,
            'name': form_snapshot.get('name'),
            'code': form_snapshot.get('code'),
            'form_code': form_snapshot.get('code'),
            'version': pub.source_form_version,
            'field_keys': sorted(extract_schema_field_keys(
                form_snapshot.get('schema'))),
        })

    return items
