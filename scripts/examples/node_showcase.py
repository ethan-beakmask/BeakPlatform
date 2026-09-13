#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""System-level node showcase provisioning helpers."""
from __future__ import annotations

import importlib
import traceback
from typing import Iterable

SHOWCASE_CATEGORY_NAME = 'node展覽館'

SHOWCASE_ITEMS = [
    ('B0 hr_demo', 'scripts.examples.provision_system_org_hr_demo', {}),
    ('B1 vars', 'scripts.examples.provision_nodedemo_vars', {}),
    ('B2 control', 'scripts.examples.provision_nodedemo_control', {}),
    ('B3 startend', 'scripts.examples.provision_nodedemo_startend', {}),
    ('B4 parallel_subflow', 'scripts.examples.provision_nodedemo_parallel_subflow', {}),
    ('B5a approval_assignee', 'scripts.examples.provision_nodedemo_approval_assignee', {}),
    ('B5b approval_decision', 'scripts.examples.provision_nodedemo_approval_decision', {}),
    ('B6 osexecutor', 'scripts.examples.provision_nodedemo_osexecutor', {}),
    ('B7 osfile', 'scripts.examples.provision_nodedemo_osfile', {}),
    ('B8 sqlexecutor', 'scripts.examples.provision_nodedemo_sqlexecutor', {}),
    ('B9 aiagent', 'scripts.examples.provision_nodedemo_aiagent', {}),
    ('B10 broadcast', 'scripts.examples.provision_nodedemo_broadcast', {}),
    ('B11 telegram', 'scripts.examples.provision_nodedemo_telegram', {}),
    ('B12 email', 'scripts.examples.provision_nodedemo_email', {}),
    ('B13 apikey', 'scripts.examples.provision_nodedemo_apikey', {}),
    ('B14 decisionwriter', 'scripts.examples.provision_nodedemo_decisionwriter', {}),
    ('B15 hrlookup', 'scripts.examples.provision_nodedemo_hrlookup', {}),
    ('B16 subsystem', 'scripts.examples.provision_nodedemo_subsystem', {}),
    ('waf_failover', 'scripts.examples.provision_nodedemo_waf_failover', {}),
    ('waf_monitor', 'scripts.examples.provision_nodedemo_waf_monitor', {}),
]


def ensure_showcase_category(org):
    """Return the org-local node showcase category, creating it when missing."""
    from app import db
    from modules.form_workflow.models import FwCategory

    category = FwCategory.query.filter_by(
        org_secure_code=org.secure_code,
        name=SHOWCASE_CATEGORY_NAME,
        is_deleted=False,
    ).first()
    if category:
        category.show_in_form_design = True
        category.show_in_workflow_design = True
        category.show_in_form_center = True
        return category

    category = FwCategory(
        org_secure_code=org.secure_code,
        name=SHOWCASE_CATEGORY_NAME,
        description='系統級節點示範表單與流程',
        display_order=900,
        is_system=True,
        show_in_form_design=True,
        show_in_workflow_design=True,
        show_in_form_center=True,
    )
    db.session.add(category)
    db.session.flush()
    return category


def _selected_names(only: Iterable[str] | None) -> set[str] | None:
    if not only:
        return None
    return {name.strip() for name in only if name and name.strip()}


def seed_node_showcase(org, apply=True, password=None, only=None, **opts) -> dict:
    """Provision every showcase item, keeping failures isolated per item."""
    category = ensure_showcase_category(org)
    selected = _selected_names(only)
    done = []
    failed = []

    for name, module_name, defaults in SHOWCASE_ITEMS:
        code_name = name.split()[0]
        simple_name = name.split()[-1]
        if selected and name not in selected and simple_name not in selected and code_name not in selected:
            continue
        item_opts = dict(defaults)
        item_opts.update(opts)
        if module_name.endswith('provision_system_org_hr_demo'):
            item_opts['password'] = password
        try:
            module = importlib.import_module(module_name)
            result = module.provision(org, apply=apply, **item_opts)
            done.append((name, result))
        except Exception as exc:
            failed.append((name, f'{exc.__class__.__name__}: {exc}'))
            traceback.print_exc()

    return {
        'ok': not failed,
        'done': done,
        'failed': failed,
        'category_secure_code': category.secure_code,
    }
