#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Node showcase provisioning helpers."""
from __future__ import annotations

import importlib
import traceback
from typing import Iterable

SHOWCASE_CATEGORY_NAME = 'node展覽館'

SHOWCASE_ITEMS = [
    ('B0 hr_demo', 'scripts.examples.provision_system_org_hr_demo', {}, {
        'node_types': [], 'requires_modules': [], 'depends_on': [],
    }),
    ('B1 vars', 'scripts.examples.provision_nodedemo_vars', {}, {
        'node_types': ['Start', 'OpSet', 'OpFieldRead', 'OpFieldWrite', 'FormAdapter', 'End'],
        'requires_modules': [], 'depends_on': [],
    }),
    ('B2 control', 'scripts.examples.provision_nodedemo_control', {}, {
        'node_types': ['Start', 'Branch', 'OpSet', 'Delay', 'FormAdapter', 'End'],
        'requires_modules': [], 'depends_on': [],
    }),
    ('B3 startend', 'scripts.examples.provision_nodedemo_startend', {}, {
        'node_types': ['Start', 'OpSet', 'Delay', 'FormAdapter', 'End'],
        'requires_modules': [], 'depends_on': [],
    }),
    ('B4 parallel_subflow', 'scripts.examples.provision_nodedemo_parallel_subflow', {}, {
        'node_types': ['Start', 'Delay', 'OpSet', 'ParallelJoin', 'FormAdapter', 'Branch', 'SubFlow', 'End'],
        'requires_modules': [], 'depends_on': [],
    }),
    ('B5a approval_assignee', 'scripts.examples.provision_nodedemo_approval_assignee', {}, {
        'node_types': ['Start', 'FormAdapter', 'Branch', 'End'],
        'requires_modules': [], 'depends_on': ['B0'],
    }),
    ('B5b approval_decision', 'scripts.examples.provision_nodedemo_approval_decision', {}, {
        'node_types': ['Start', 'FormAdapter', 'Branch', 'OpFieldWrite', 'End'],
        'requires_modules': [], 'depends_on': [],
    }),
    ('B6 osexecutor', 'scripts.examples.provision_nodedemo_osexecutor', {}, {
        'node_types': ['Start', 'OpSet', 'OsExecutor', 'OpFieldWrite', 'FormAdapter', 'End'],
        'requires_modules': [], 'depends_on': [],
    }),
    ('B7 osfile', 'scripts.examples.provision_nodedemo_osfile', {}, {
        'node_types': ['Start', 'OsFileRead', 'OsFileWrite', 'OpFieldWrite', 'FormAdapter', 'End'],
        'requires_modules': [], 'depends_on': [],
    }),
    ('B8 sqlexecutor', 'scripts.examples.provision_nodedemo_sqlexecutor', {}, {
        'node_types': ['Start', 'OpSet', 'SysSqlExecutor', 'OpFieldWrite', 'FormAdapter', 'End'],
        'requires_modules': [], 'depends_on': [],
    }),
    ('B9 aiagent', 'scripts.examples.provision_nodedemo_aiagent', {}, {
        'node_types': ['Start', 'AiAgent', 'OpFieldWrite', 'FormAdapter', 'Branch', 'End'],
        'requires_modules': [], 'depends_on': [],
    }),
    ('B10 broadcast', 'scripts.examples.provision_nodedemo_broadcast', {}, {
        'node_types': ['Start', 'AlertBroadcast', 'NavbarBroadcast', 'Delay', 'OpFieldWrite', 'FormAdapter', 'End'],
        'requires_modules': [], 'depends_on': [],
    }),
    ('B11 telegram', 'scripts.examples.provision_nodedemo_telegram', {}, {
        'node_types': ['Start', 'Telegram', 'SysTelegram', 'OpFieldWrite', 'FormAdapter', 'End'],
        'requires_modules': [], 'depends_on': [],
    }),
    ('B12 email', 'scripts.examples.provision_nodedemo_email', {}, {
        'node_types': ['Start', 'EmailAdapter', 'SysEmailRelay', 'OpFieldWrite', 'FormAdapter', 'End'],
        'requires_modules': [], 'depends_on': ['B0'],
    }),
    ('B13 apikey', 'scripts.examples.provision_nodedemo_apikey', {}, {
        'node_types': ['Start', 'FormAdapter', 'ApiKeyIssue', 'ApiKeyAction', 'OpFieldWrite', 'End'],
        'requires_modules': [], 'depends_on': [],
    }),
    ('B14 decisionwriter', 'scripts.examples.provision_nodedemo_decisionwriter', {}, {
        'node_types': ['Start', 'FormAdapter', 'DecisionWriter', 'OpFieldWrite', 'Branch', 'End'],
        'requires_modules': [], 'depends_on': [],
    }),
    ('B15 hrlookup', 'scripts.examples.provision_nodedemo_hrlookup', {}, {
        'node_types': ['Start', 'OpHrLookup', 'OpFieldWrite', 'FormAdapter', 'End'],
        'requires_modules': [], 'depends_on': ['B0'],
    }),
    ('B16 subsystem', 'scripts.examples.provision_nodedemo_subsystem', {}, {
        'node_types': ['Start', 'FormAdapter', 'SubSystemProvision', 'OpFieldWrite', 'Branch', 'End'],
        'requires_modules': ['nocode_builder'], 'depends_on': [],
    }),
    ('waf_failover', 'scripts.examples.provision_nodedemo_waf_failover', {}, {
        'node_types': ['Start', 'FormAdapter', 'OsExecutor', 'OpFieldWrite', 'Branch', 'End'],
        'requires_modules': [], 'depends_on': [],
    }),
    ('waf_monitor', 'scripts.examples.provision_nodedemo_waf_monitor', {}, {
        'node_types': ['Start', 'OpSet', 'Delay', 'OsExecutor', 'Branch', 'SysTelegram', 'FormAdapter', 'OpFieldWrite', 'End'],
        'requires_modules': [], 'depends_on': [],
    }),
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
        category.is_system = bool(getattr(org, 'is_system_org', False))
        category.show_in_form_design = True
        category.show_in_workflow_design = True
        category.show_in_form_center = True
        return category

    category = FwCategory(
        org_secure_code=org.secure_code,
        name=SHOWCASE_CATEGORY_NAME,
        description='節點示範表單與流程',
        display_order=900,
        is_system=bool(getattr(org, 'is_system_org', False)),
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


def _item_code(name: str) -> str:
    return name.split()[0]


def _item_simple_name(name: str) -> str:
    return name.split()[-1]


def _item_matches(name: str, selected: set[str] | None) -> bool:
    if not selected:
        return True
    return (
        name in selected
        or _item_code(name) in selected
        or _item_simple_name(name) in selected
    )


def resolve_showcase_org(identifier=None):
    """Resolve a showcase target organization by code, domain, or secure_code."""
    from app.models import Organization

    if identifier is None or not str(identifier).strip():
        return Organization.query.filter_by(
            is_system_org=True,
            is_deleted=False,
        ).first()

    value = str(identifier).strip()
    for column in (Organization.code, Organization.domain_name, Organization.secure_code):
        org = Organization.query.filter(
            column == value,
            Organization.is_deleted.is_(False),
        ).first()
        if org:
            return org
    return None


def _restricted_node_types() -> set[str]:
    from modules.form_workflow.models import WorkflowNodeDefinition

    rows = WorkflowNodeDefinition.query.with_entities(
        WorkflowNodeDefinition.node_type
    ).filter(
        WorkflowNodeDefinition.org_restricted.is_(True),
        WorkflowNodeDefinition.is_deleted.is_(False),
    ).all()
    return {row[0] for row in rows if row[0]}


def _has_module_contract(org, module_code: str) -> bool:
    if getattr(org, 'is_system_org', False):
        return True

    from types import SimpleNamespace
    from app.services.module_access_service import ModuleAccessService

    user_like = SimpleNamespace(
        org_secure_code=org.secure_code,
        organization=org,
    )
    return ModuleAccessService.check_module_contract(user_like, module_code)


def _workflow_codes_for_module(module_name: str) -> list[str]:
    module = importlib.import_module(module_name)
    codes = []
    for attr in ('DEMOS', 'FULL_DEMOS', 'FULL_DEMOS_STATIC', 'WORKFLOW_ONLY_DEMOS'):
        demos = getattr(module, attr, None)
        if not isinstance(demos, list):
            continue
        for demo in demos:
            if isinstance(demo, dict) and demo.get('workflow_code'):
                codes.append(demo['workflow_code'])
    return codes


def _item_exists(org, module_name: str) -> bool:
    from modules.form_workflow.models import FwCategory, FwWorkflowTemplate

    try:
        codes = _workflow_codes_for_module(module_name)
    except Exception:
        return False
    if not codes:
        return False
    category = FwCategory.query.filter_by(
        org_secure_code=org.secure_code,
        name=SHOWCASE_CATEGORY_NAME,
        is_deleted=False,
    ).first()
    if not category:
        return False
    return FwWorkflowTemplate.query.filter(
        FwWorkflowTemplate.org_secure_code == org.secure_code,
        FwWorkflowTemplate.category_secure_code == category.secure_code,
        FwWorkflowTemplate.code.in_(codes),
        FwWorkflowTemplate.is_deleted.is_(False),
    ).first() is not None


def plan_showcase_items(org, only=None) -> list[dict]:
    """Return a per-item installation plan for the target organization."""
    from modules.form_workflow.services.node_grant_service import is_node_allowed

    selected = _selected_names(only)
    restricted_types = _restricted_node_types()
    plan = []

    for name, module_name, _defaults, metadata in SHOWCASE_ITEMS:
        if not _item_matches(name, selected):
            continue

        node_types = list(metadata.get('node_types') or [])
        item_restricted = [node_type for node_type in node_types if node_type in restricted_types]
        tier = 'base' if _item_code(name) == 'B0' else ('system' if item_restricted else 'enterprise')
        action = 'run'
        reason = None

        unauthorized = [
            node_type for node_type in item_restricted
            if not is_node_allowed(node_type, org.secure_code)
        ]
        if unauthorized:
            action = 'skip'
            reason = '本企業未獲授權節點：' + ', '.join(unauthorized)

        if action == 'run':
            for module_code in metadata.get('requires_modules') or []:
                if not _has_module_contract(org, module_code):
                    action = 'skip'
                    reason = f'本企業無 {module_code} 模組合約'
                    break

        plan.append({
            'name': name,
            'code': _item_code(name),
            'tier': tier,
            'node_types': node_types,
            'action': action,
            'reason': reason,
            'exists': _item_exists(org, module_name),
            'depends_on': list(metadata.get('depends_on') or []),
            'requires_modules': list(metadata.get('requires_modules') or []),
        })
    return plan


def seed_node_showcase(org, apply=True, password=None, only=None, **opts) -> dict:
    """Provision every showcase item, keeping failures isolated per item."""
    category = ensure_showcase_category(org)
    plan = plan_showcase_items(org, only=only)
    run_codes = {item['code'] for item in plan if item['action'] == 'run'}
    if 'B0' in run_codes and not password:
        raise ValueError('B0 示範帳號需要密碼')

    done = []
    failed = []
    skipped = [(item['name'], item['reason']) for item in plan if item['action'] == 'skip']

    for name, module_name, defaults, _metadata in SHOWCASE_ITEMS:
        code_name = _item_code(name)
        if code_name not in run_codes:
            continue
        item_opts = dict(defaults)
        item_opts.update(opts)
        if module_name.endswith('provision_system_org_hr_demo'):
            item_opts['password'] = password
        try:
            module = importlib.import_module(module_name)
            result = module.provision(org, apply=apply, **item_opts)
            done.append((name, result))
        except ModuleNotFoundError as exc:
            failed.append((name, f'模組載入失敗：{exc}'))
            traceback.print_exc()
        except Exception as exc:
            failed.append((name, f'{exc.__class__.__name__}: {exc}'))
            traceback.print_exc()

    return {
        'ok': not failed,
        'done': done,
        'failed': failed,
        'skipped': skipped,
        'plan': plan,
        'category_secure_code': category.secure_code,
    }
