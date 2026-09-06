"""FormWorkflow task action authorization helpers.

簽核授權判定的唯一實作。判定來源兩層：

1. 舊佇列項的快照相容。
2. 角色@單位即時持有：regular/proxy/standby 三種指派性質，核心規則在
   app.services.role_holding_service。

呼叫端一律用 build_actor() 先把身分資訊算好再進迴圈，避免清單 API 的 N+1。
"""
from datetime import date

from app.models.role import Role, RoleType
from app.models.user import User
from app.models.associations import AssignmentKind
from app.services.role_holding_service import (
    has_available_holder,
    holds as assignment_holds,
    load_actor_assignments,
)
from app.services.unit_resolver import (
    get_unit_ancestor_codes,
    org_local_now,
    org_local_today,
)




def _build_identity(user_secure_code: str, org_secure_code: str, today: date) -> dict:
    assignments = load_actor_assignments(user_secure_code, org_secure_code, today)
    holding_assignments = [
        row for row in assignments
        if row.get('kind') in AssignmentKind.HOLDING
    ]
    role_units = {
        (row.get('role_sc'), row.get('unit_sc'))
        for row in holding_assignments
    }
    return {
        'user_sc': user_secure_code,
        'assignments': assignments,
        'role_units': role_units,
        'role_codes': {row.get('role_sc') for row in holding_assignments},
    }


def build_actor(user_secure_code: str, org_secure_code: str) -> dict:
    """一次算好授權判定需要的身分資訊，供迴圈重複使用。"""
    today = org_local_today(org_secure_code)
    identity = _build_identity(user_secure_code, org_secure_code, today)
    return {
        **identity,
        '_form_template_cache': {},
        '_org_sc': org_secure_code,
        '_local_now': org_local_now(org_secure_code),
        '_today': today,
        '_role_meta': {},
        '_role_sc_by_code': {},
        '_unit_ancestors': {},
        '_available': {},
    }


def _actor_org_sc(actor: dict, org_secure_code: str | None = None) -> str | None:
    if org_secure_code is not None:
        actor['_org_sc'] = org_secure_code
    return actor.get('_org_sc')


def _actor_today(actor: dict, org_secure_code: str) -> date:
    if '_today' not in actor:
        actor['_today'] = org_local_today(org_secure_code)
    return actor['_today']


def _actor_local_now(actor: dict, org_secure_code: str):
    if '_local_now' not in actor:
        actor['_local_now'] = org_local_now(org_secure_code)
    return actor['_local_now']


def _identity_role_units(identity) -> set[tuple[str, str | None]]:
    if isinstance(identity, set):
        return {(role_sc, None) for role_sc in identity}
    if not identity:
        return set()
    if 'role_units' in identity:
        return set(identity.get('role_units') or set())
    return {(role_sc, None) for role_sc in (identity.get('role_codes') or set())}


def _identity_assignments(identity) -> list[dict]:
    """把新舊身分形狀都轉成 role_holding_service.holds() 可吃的列。"""
    if isinstance(identity, dict) and 'assignments' in identity:
        return list(identity.get('assignments') or [])
    return [
        {
            'role_sc': role_sc,
            'unit_sc': unit_sc,
            'kind': AssignmentKind.REGULAR,
            'scope': None,
            'acting_for': None,
        }
        for role_sc, unit_sc in _identity_role_units(identity)
    ]


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


def _available(actor: dict, role_secure_code: str, unit_secure_code: str | None) -> bool:
    """指定 R@U 是否有可用 regular/proxy 持有者。"""
    cache = actor.setdefault('_available', {})
    key = (role_secure_code, unit_secure_code)
    if key in cache:
        return cache[key]
    cache[key] = has_available_holder(
        role_secure_code,
        actor.get('_org_sc'),
        unit_secure_code,
        today=actor['_today'],
        local_now=actor['_local_now'],
    )
    return cache[key]


def _holds(
    actor: dict,
    identity,
    role_secure_code: str,
    unit_secure_code: str | None,
    task,
) -> tuple[str, str | None] | None:
    assignments = _identity_assignments(identity)
    meta = _role_meta(actor, role_secure_code)
    return assignment_holds(
        assignments,
        role_secure_code,
        unit_secure_code,
        is_position=bool(meta and meta.get('role_type') == RoleType.POSITION),
        ancestors_of=lambda u: _unit_ancestors(actor, u),
        is_available=lambda r, u: _available(actor, r, u),
        form_template_sc_of=lambda: _task_form_template_secure_code(
            task, actor['_org_sc'], actor),
    )


def _match_identity(task_result_data: dict, user_secure_code: str, identity, actor: dict, task) -> dict | None:
    """單一身分是否符合這個佇列項的指派條件。"""
    assignee_type = task_result_data.get('assignee_type')
    if not assignee_type:
        return {
            'acted_as_kind': None,
            'acting_for': None,
            'acted_as_role_code': None,
        }

    # ROLE／DEPARTMENT 若帶 assignee_unit_secure_code key，代表第 2 期後的角色@單位規格：
    # 角色與缺席順位用即時狀態判定，不再用進關卡快照放行。舊佇列項沒有這個 key 時，
    # 才維持快照相容行為。
    in_snapshot = user_secure_code in (task_result_data.get('assignees') or [])

    if assignee_type in ('ROLE', 'DEPARTMENT'):
        spec = _spec_from(task_result_data, actor)
        if spec:
            role_sc, unit_sc = spec
            hit = _holds(actor, identity, role_sc, unit_sc, task)
            if hit:
                kind, acting_for = hit
                meta = _role_meta(actor, role_sc)
                return {
                    'acted_as_kind': kind,
                    'acting_for': acting_for,
                    'acted_as_role_code': (
                        meta.get('code') if meta and kind != AssignmentKind.REGULAR else None
                    ),
                }

        if 'assignee_unit_secure_code' in task_result_data:
            return None

    if in_snapshot:
        return {
            'acted_as_kind': None,
            'acting_for': None,
            'acted_as_role_code': None,
        }
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


def resolve_acting_identity(
    task,
    user_secure_code: str,
    org_secure_code: str,
    actor: dict = None,
) -> dict | None:
    """回傳這次放行憑的是哪個身分；不能簽回 None。

    回傳值：
    - {'via': 'self', 'delegator_secure_code': None, 'acted_as_role_code': ..., 'acted_as_kind': ...}

    proxy/standby 命中時 acted_as_role_code 為被命中的角色 code；regular 或快照命中為 None。
    """
    if not task:
        return None

    task_result_data = (task.result or {}).get('data', {})
    if actor is None:
        actor = build_actor(user_secure_code, org_secure_code)
    else:
        _actor_org_sc(actor, org_secure_code)
        _actor_today(actor, org_secure_code)
        _actor_local_now(actor, org_secure_code)

    self_match = _match_identity(task_result_data, user_secure_code, actor, actor, task)
    if self_match:
        return {
            'via': 'self',
            'delegator_secure_code': self_match.get('acting_for'),
            'acted_as_role_code': self_match.get('acted_as_role_code'),
            'acted_as_kind': self_match.get('acted_as_kind'),
        }

    return None


def delegate_from_fields(identity, org_secure_code) -> dict:
    """換成 FwApprovalRecord 的 delegate_from_* 欄位值。

    本人簽核回 {}。delegator_secure_code 有值時會記錄授權人或被代理人的 secure_code 與顯示名稱。
    這裡刻意不加 User.is_active 條件：本函式只負責寫歷史記錄，不做授權判定；
    授權是否成立已由 resolve_acting_identity() 判斷，即使授權人事後停用也要保留姓名。
    """
    if not identity:
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
