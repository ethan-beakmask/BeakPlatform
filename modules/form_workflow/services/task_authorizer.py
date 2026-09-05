"""
FormWorkflow task action authorization helpers.

簽核授權判定的唯一實作。判定來源有四層，任一成立即放行：

1. **快照**：節點啟動當下解析出的 `assignees`（原始行為，永不縮減）
2. **當前角色@單位**：`ROLE` 即時比對使用者現在持有的 `(role, unit)`，
   ROLE 型角色可由後代單位往祖先單位套圈，POSITION 型角色不套圈
3. **主管缺席順位**：目標為 POSITION 且允許 fallback 時，依副主管、代理人一、
   代理人二判定；DEPARTMENT 已退役為 `DEPT_MEMBER@unit` 的別名
4. **代理授權**：使用者是某個「原本可簽的人」的生效中代理人

呼叫端一律用 `build_actor()` 先把身分資訊算好再進迴圈，避免清單 API 的 N+1。
"""
from datetime import date

from app.models.associations import UserRoleAssignment
from app.models.role import Role, RoleType
from app.models.user import User
from app.services.unit_resolver import get_unit_ancestor_codes, org_local_today


FALLBACK_ROLE_CODES = {
    'DEPT_MANAGER': ('DEPT_DEPUTY', 'DEPT_PROXY1', 'DEPT_PROXY2'),
}
ALWAYS_ALLOWED_FALLBACK_CODES = frozenset({'DEPT_DEPUTY'})


def get_actor_role_units(
    user_secure_code: str,
    org_secure_code: str,
    today: date | None = None,
) -> set[tuple[str, str | None]]:
    """取得使用者在指定企業當前有效的 (role, unit) 集合。"""
    if today is None:
        today = org_local_today(org_secure_code)

    assignments = UserRoleAssignment.query.filter(
        UserRoleAssignment.user_secure_code == user_secure_code,
        UserRoleAssignment.org_secure_code == org_secure_code,
        UserRoleAssignment.is_deleted == False,  # noqa: E712
    ).all()
    return {
        (a.role_secure_code, a.unit_secure_code or None)
        for a in assignments
        if a.is_valid_on(today)
    }


def get_actor_role_codes(user_secure_code: str, org_secure_code: str) -> set:
    """取得使用者在指定企業當前有效的角色 secure_code 集合。

    平台另有 `UserRoleAssignment.get_active_role_secure_codes()`，但它不帶
    org 條件，本模組一律自行查詢並補上（TENANT-01）。
    """
    return {
        role_sc
        for role_sc, _ in get_actor_role_units(user_secure_code, org_secure_code)
    }


def _build_identity(user_secure_code: str, org_secure_code: str, today: date) -> dict:
    role_units = get_actor_role_units(user_secure_code, org_secure_code, today)
    return {
        'user_sc': user_secure_code,
        'role_units': role_units,
        'role_codes': {role_sc for role_sc, _ in role_units},
    }


def _merge_delegation_scope(current, incoming):
    """合併同一授權人的代理範圍；None 表示不限表單。"""
    if current is None or incoming is None:
        return None
    return set(current) | set(incoming)


def _get_delegated_identity_data(
    user_secure_code: str,
    org_secure_code: str,
    today: date | None = None,
) -> tuple[dict, dict]:
    """取得代理身分與表單 scope，供公開舊 API 與 build_actor 共用。"""
    from app.models.delegation import Delegation, DelegationType

    if today is None:
        today = org_local_today(org_secure_code)

    rows = Delegation.query.filter(
        Delegation.delegate_secure_code == user_secure_code,
        Delegation.org_secure_code == org_secure_code,
        Delegation.is_deleted == False,  # noqa: E712
    ).all()

    identities_by_delegator = {}
    scopes_by_delegator = {}
    for d in rows:
        if not d.is_effective_on(today):
            continue

        scope = None
        if d.delegation_type == DelegationType.APPROVAL and d.approval_limit is not None:
            continue
        if d.delegation_type == DelegationType.SPECIFIC:
            allowed = set(d.get_allowed_form_templates())
            if not allowed:
                continue
            scope = allowed
        elif d.delegation_type not in (DelegationType.FULL, DelegationType.APPROVAL):
            continue

        delegator_sc = d.delegator_secure_code
        if delegator_sc not in identities_by_delegator:
            identities_by_delegator[delegator_sc] = _build_identity(
                delegator_sc, org_secure_code, today)
            scopes_by_delegator[delegator_sc] = scope
        else:
            scopes_by_delegator[delegator_sc] = _merge_delegation_scope(
                scopes_by_delegator[delegator_sc], scope)

    return identities_by_delegator, scopes_by_delegator


def get_delegated_identities(user_secure_code: str, org_secure_code: str) -> dict:
    """取得「這個人目前代理了誰」，回傳 {授權人 secure_code: 授權人的角色集合}。

    只採計對簽核任務有意義且判得準的代理型別：

    | 型別 | 是否採計 | 理由 |
    |------|---------|------|
    | FULL     | 是 | 全權代理 |
    | APPROVAL | 僅 `approval_limit` 為空時 | 有金額上限時，佇列項層拿不到單據金額，放行等於忽略上限 |
    | SPECIFIC | 有選表單模板時 | 僅限任務所屬表單模板在 `allowed_process_types` JSON 陣列內 |

    不採計者一律不放行（fail-closed）。代理筆數在實務上極少（通常 0），
    因此逐筆查授權人角色不會造成效能問題。
    """
    identities_by_delegator, _ = _get_delegated_identity_data(
        user_secure_code, org_secure_code)
    return {
        delegator_sc: identity['role_codes']
        for delegator_sc, identity in identities_by_delegator.items()
    }


def build_actor(user_secure_code: str, org_secure_code: str) -> dict:
    """一次算好授權判定需要的身分資訊，供迴圈重複使用。"""
    today = org_local_today(org_secure_code)
    identity = _build_identity(user_secure_code, org_secure_code, today)
    delegations, delegation_scopes = _get_delegated_identity_data(
        user_secure_code, org_secure_code, today)
    return {
        **identity,
        'delegations': delegations,
        'delegation_scopes': delegation_scopes,
        '_form_template_cache': {},
        '_org_sc': org_secure_code,
        '_today': today,
        '_role_meta': {},
        '_role_sc_by_code': {},
        '_unit_ancestors': {},
        '_unit_manager_present': {},
    }


def _actor_org_sc(actor: dict, org_secure_code: str | None = None) -> str | None:
    if org_secure_code is not None:
        actor['_org_sc'] = org_secure_code
    return actor.get('_org_sc')


def _actor_today(actor: dict, org_secure_code: str) -> date:
    if '_today' not in actor:
        actor['_today'] = org_local_today(org_secure_code)
    return actor['_today']


def _identity_role_units(identity) -> set[tuple[str, str | None]]:
    if isinstance(identity, set):
        return {(role_sc, None) for role_sc in identity}
    if not identity:
        return set()
    if 'role_units' in identity:
        return set(identity.get('role_units') or set())
    return {(role_sc, None) for role_sc in (identity.get('role_codes') or set())}


def _role_meta(actor: dict, role_secure_code: str) -> dict | None:
    cache = actor.setdefault('_role_meta', {})
    if role_secure_code not in cache:
        org_secure_code = actor.get('_org_sc')
        role = Role.query.filter(
            Role.org_secure_code == org_secure_code,
            Role.secure_code == role_secure_code,
            Role.is_deleted == False,  # noqa: E712
        ).first()
        cache[role_secure_code] = (
            {'code': role.code, 'role_type': role.role_type}
            if role else None
        )
    return cache[role_secure_code]


def _role_sc_by_code(actor: dict, code: str) -> str | None:
    cache = actor.setdefault('_role_sc_by_code', {})
    if code not in cache:
        org_secure_code = actor.get('_org_sc')
        role = Role.query.filter(
            Role.org_secure_code == org_secure_code,
            Role.code == code,
            Role.is_active == True,  # noqa: E712
            Role.is_deleted == False,  # noqa: E712
        ).first()
        cache[code] = role.secure_code if role else None
    return cache[code]


def _unit_ancestors(actor: dict, unit_secure_code: str) -> list[str]:
    cache = actor.setdefault('_unit_ancestors', {})
    if unit_secure_code not in cache:
        cache[unit_secure_code] = get_unit_ancestor_codes(
            unit_secure_code, actor.get('_org_sc'))
    return cache[unit_secure_code]


def _spec_from(task_result_data: dict, actor: dict) -> tuple[str, str | None] | None:
    assignee_type = task_result_data.get('assignee_type')
    assignee_value = task_result_data.get('assignee_value')
    if not assignee_value:
        return None

    if assignee_type == 'ROLE':
        if _role_meta(actor, assignee_value) is None:
            return None
        return assignee_value, task_result_data.get('assignee_unit_secure_code') or None

    if assignee_type == 'DEPARTMENT':
        role_sc = _role_sc_by_code(actor, 'DEPT_MEMBER')
        if not role_sc:
            return None
        return role_sc, assignee_value

    return None


def _holds(actor: dict, identity, role_secure_code: str, unit_secure_code: str | None) -> bool:
    role_units = _identity_role_units(identity)
    if (role_secure_code, unit_secure_code) in role_units:
        return True
    if (role_secure_code, None) in role_units:
        return True
    if unit_secure_code is None:
        return any(role_sc == role_secure_code for role_sc, _ in role_units)

    meta = _role_meta(actor, role_secure_code)
    if not meta or meta.get('role_type') == RoleType.POSITION:
        return False

    return any(
        role_sc == role_secure_code
        and held_unit_sc
        and unit_secure_code in _unit_ancestors(actor, held_unit_sc)
        for role_sc, held_unit_sc in role_units
    )


def _unit_manager_present(actor: dict, manager_role_sc: str, unit_secure_code: str) -> bool:
    cache = actor.setdefault('_unit_manager_present', {})
    key = (manager_role_sc, unit_secure_code)
    if key in cache:
        return cache[key]

    org_secure_code = actor.get('_org_sc')
    today = actor.get('_today') or org_local_today(org_secure_code)
    rows = UserRoleAssignment.query.join(
        User,
        UserRoleAssignment.user_secure_code == User.secure_code,
    ).filter(
        UserRoleAssignment.org_secure_code == org_secure_code,
        UserRoleAssignment.role_secure_code == manager_role_sc,
        UserRoleAssignment.is_deleted == False,  # noqa: E712
        (UserRoleAssignment.unit_secure_code == unit_secure_code)
        | (UserRoleAssignment.unit_secure_code == None),  # noqa: E711
        User.org_secure_code == org_secure_code,
        User.is_active == True,  # noqa: E712
        User.is_deleted == False,  # noqa: E712
    ).all()
    cache[key] = any(row.is_valid_on(today) for row in rows)
    return cache[key]


def _match_identity(task_result_data: dict, user_secure_code: str, identity, actor: dict) -> dict | None:
    """單一身分是否符合這個佇列項的指派條件。"""
    assignee_type = task_result_data.get('assignee_type')
    if not assignee_type:
        return {'acted_as_role_code': None}

    if user_secure_code in (task_result_data.get('assignees') or []):
        return {'acted_as_role_code': None}

    if assignee_type in ('ROLE', 'DEPARTMENT'):
        spec = _spec_from(task_result_data, actor)
        if not spec:
            return None
        role_sc, unit_sc = spec
        if _holds(actor, identity, role_sc, unit_sc):
            return {'acted_as_role_code': None}

        if (
            assignee_type == 'ROLE'
            and task_result_data.get('assignee_role_type') == RoleType.POSITION
            and task_result_data.get('absence_fallback', True)
            and unit_sc is not None
        ):
            meta = _role_meta(actor, role_sc)
            target_code = meta.get('code') if meta else None
            for fallback_code in FALLBACK_ROLE_CODES.get(target_code, ()):
                fallback_sc = _role_sc_by_code(actor, fallback_code)
                if not fallback_sc or not _holds(actor, identity, fallback_sc, unit_sc):
                    continue
                if (
                    fallback_code in ALWAYS_ALLOWED_FALLBACK_CODES
                    or not _unit_manager_present(actor, role_sc, unit_sc)
                ):
                    return {'acted_as_role_code': fallback_code}

    return None


def _task_form_template_secure_code(task, org_secure_code: str, actor: dict) -> str | None:
    """取得佇列項所屬表單模板 secure_code；結果快取在 actor 內。"""
    form_instance_sc = getattr(task, 'form_instance_secure_code', None)
    if not form_instance_sc:
        return None

    cache = actor.setdefault('_form_template_cache', {})
    if form_instance_sc in cache:
        return cache[form_instance_sc]

    from modules.form_workflow.models import FwFormInstance

    instance = FwFormInstance.query.filter(
        FwFormInstance.org_secure_code == org_secure_code,
        FwFormInstance.secure_code == form_instance_sc,
        FwFormInstance.is_deleted == False,  # noqa: E712
    ).first()
    cache[form_instance_sc] = instance.form_template_secure_code if instance else None
    return cache[form_instance_sc]


def _delegation_scope_allows_task(scope, task, org_secure_code: str, actor: dict) -> bool:
    """檢查代理 scope 是否允許處理該任務。"""
    if scope is None:
        return True
    form_template_sc = _task_form_template_secure_code(task, org_secure_code, actor)
    return bool(form_template_sc and form_template_sc in scope)


def resolve_acting_identity(
    task,
    user_secure_code: str,
    org_secure_code: str,
    actor: dict = None,
) -> dict | None:
    """回傳這次放行憑的是哪個身分；不能簽回 None。

    回傳值：
    - {'via': 'self', 'delegator_secure_code': None, 'acted_as_role_code': ...}
    - {'via': 'delegation', 'delegator_secure_code': '<授權人 sc>', 'acted_as_role_code': ...}

    `acted_as_role_code` 是走主管缺席順位時放行的那個角色 code
    （`DEPT_DEPUTY` / `DEPT_PROXY1` / `DEPT_PROXY2`），直接持有或快照命中時為 None。
    """
    if not task:
        return None

    task_result_data = (task.result or {}).get('data', {})
    if actor is None:
        actor = build_actor(user_secure_code, org_secure_code)
    else:
        _actor_org_sc(actor, org_secure_code)
        _actor_today(actor, org_secure_code)

    self_match = _match_identity(task_result_data, user_secure_code, actor, actor)
    if self_match:
        return {
            'via': 'self',
            'delegator_secure_code': None,
            'acted_as_role_code': self_match.get('acted_as_role_code'),
        }

    # 代理授權：排序後取第一個符合者，避免 dict 順序影響記錄結果。
    delegations = actor.get('delegations') or {}
    # 舊形狀 actor 沒有 delegation_scopes 時，維持既有語意：所有授權人不限表單。
    delegation_scopes = actor.get('delegation_scopes')
    for delegator_sc in sorted(delegations):
        match = _match_identity(
            task_result_data, delegator_sc, delegations[delegator_sc], actor)
        if match:
            scope = None if delegation_scopes is None else delegation_scopes.get(delegator_sc)
            if _delegation_scope_allows_task(scope, task, org_secure_code, actor):
                return {
                    'via': 'delegation',
                    'delegator_secure_code': delegator_sc,
                    'acted_as_role_code': match.get('acted_as_role_code'),
                }

    return None


def delegate_from_fields(identity, org_secure_code) -> dict:
    """換成 FwApprovalRecord 的 delegate_from_* 欄位值。

    本人簽核回 {}。代理簽核會記錄授權人的 secure_code 與顯示名稱。
    這裡刻意不加 User.is_active 條件：本函式只負責寫歷史記錄，不做授權判定；
    授權是否成立已由 resolve_acting_identity() 判斷，即使授權人事後停用也要保留姓名。
    """
    if not identity or identity.get('via') != 'delegation':
        return {}

    delegator_sc = identity.get('delegator_secure_code')
    if not delegator_sc:
        return {}

    user = User.query.filter(
        User.org_secure_code == org_secure_code,
        User.secure_code == delegator_sc,
        User.is_deleted == False,  # noqa: E712
    ).first()
    name = (user.display_name or user.username) if user else delegator_sc
    return {
        'delegate_from_secure_code': delegator_sc,
        'delegate_from_name': name,
    }


def can_act_on_task(
    task,
    user_secure_code: str,
    org_secure_code: str,
    actor: dict = None,
) -> bool:
    """判斷使用者能否對這個簽核佇列項採取行動。

    actor 可由呼叫端以 `build_actor()` 預先算好傳入（清單／批次 API 用，
    避免迴圈內重複查詢）；不傳則自行計算。
    """
    return resolve_acting_identity(
        task, user_secure_code, org_secure_code, actor
    ) is not None


def is_pending_assignee(
    task,
    user_secure_code: str,
    org_secure_code: str,
    actor: dict = None,
) -> bool:
    """是否為此佇列項的「當前待簽者」。

    與 can_act_on_task 的差別：**沒有 assignee_type 一律回 False**。
    can_act_on_task 對無 assignee_type 回 True 的語意是「這一關沒有限定簽核人」，
    用在簽核端是對的；但用在「他是不是參與者」這種正向判定上會過寬——
    呼叫端（如檔案授權）取的 WAITING 佇列項不限 node_type，
    非簽核類節點本來就沒有 assignee_type，會變成全企業放行。
    """
    if not task:
        return False
    if not ((task.result or {}).get('data') or {}).get('assignee_type'):
        return False
    return can_act_on_task(task, user_secure_code, org_secure_code, actor)
