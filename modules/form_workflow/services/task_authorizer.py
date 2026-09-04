"""
FormWorkflow task action authorization helpers.

簽核授權判定的唯一實作。判定來源有三層，任一成立即放行：

1. **快照**：節點啟動當下解析出的 `assignees`（原始行為，永不縮減）
2. **當前角色**：`assignee_type == 'ROLE'` 時即時比對使用者現在持有的角色，
   讓「新進/輪替/調職」對已經停在關卡上的單立即生效（L1，2026-08-09）
3. **代理授權**：使用者是某個「原本可簽的人」的生效中代理人（2026-08-09）

呼叫端一律用 `build_actor()` 先把身分資訊算好再進迴圈，避免清單 API 的 N+1。
"""
from app.models.associations import UserRoleAssignment


def get_actor_role_codes(user_secure_code: str, org_secure_code: str) -> set:
    """取得使用者在指定企業當前有效的角色 secure_code 集合。

    平台另有 `UserRoleAssignment.get_active_role_secure_codes()`，但它不帶
    org 條件，本模組一律自行查詢並補上（TENANT-01）。
    """
    assignments = UserRoleAssignment.query.filter(
        UserRoleAssignment.user_secure_code == user_secure_code,
        UserRoleAssignment.org_secure_code == org_secure_code,
        UserRoleAssignment.is_deleted == False,  # noqa: E712
    ).all()
    return {a.role_secure_code for a in assignments if a.is_valid}


def _merge_delegation_scope(current, incoming):
    """合併同一授權人的代理範圍；None 表示不限表單。"""
    if current is None or incoming is None:
        return None
    return set(current) | set(incoming)


def _get_delegated_identity_data(user_secure_code: str, org_secure_code: str) -> tuple[dict, dict]:
    """取得代理身分與表單 scope，供公開舊 API 與 build_actor 共用。"""
    from app.models.delegation import Delegation, DelegationType

    rows = Delegation.query.filter(
        Delegation.delegate_secure_code == user_secure_code,
        Delegation.org_secure_code == org_secure_code,
        Delegation.is_deleted == False,  # noqa: E712
    ).all()

    role_codes_by_delegator = {}
    scopes_by_delegator = {}
    for d in rows:
        if not d.is_active:          # status == ACTIVE 且今日在生效期間內
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
        if delegator_sc not in role_codes_by_delegator:
            role_codes_by_delegator[delegator_sc] = get_actor_role_codes(
                delegator_sc, org_secure_code)
            scopes_by_delegator[delegator_sc] = scope
        else:
            scopes_by_delegator[delegator_sc] = _merge_delegation_scope(
                scopes_by_delegator[delegator_sc], scope)

    return role_codes_by_delegator, scopes_by_delegator


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
    role_codes_by_delegator, _ = _get_delegated_identity_data(
        user_secure_code, org_secure_code)
    return role_codes_by_delegator


def build_actor(user_secure_code: str, org_secure_code: str) -> dict:
    """一次算好授權判定需要的身分資訊，供迴圈重複使用。"""
    delegations, delegation_scopes = _get_delegated_identity_data(
        user_secure_code, org_secure_code)
    return {
        'user_sc': user_secure_code,
        'role_codes': get_actor_role_codes(user_secure_code, org_secure_code),
        'delegations': delegations,
        'delegation_scopes': delegation_scopes,
        '_form_template_cache': {},
    }


def _identity_matches(task_result_data: dict, user_secure_code: str,
                      role_codes: set) -> bool:
    """單一身分是否符合這個佇列項的指派條件。"""
    assignee_type = task_result_data.get('assignee_type')
    if not assignee_type:
        return True

    if user_secure_code in (task_result_data.get('assignees') or []):
        return True

    if assignee_type == 'ROLE':
        assignee_value = task_result_data.get('assignee_value')
        if not assignee_value:
            return False
        return assignee_value in (role_codes or set())

    # DEPARTMENT 刻意維持 snapshot-only（部門調動不即時生效，範圍決定不是遺漏）；
    # INITIATOR / USER / DYNAMIC 的語意本來就是「指定的那個人」，不適用角色比對。
    return False


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
    - {'via': 'self', 'delegator_secure_code': None}
    - {'via': 'delegation', 'delegator_secure_code': '<授權人 sc>'}
    """
    if not task:
        return None

    task_result_data = (task.result or {}).get('data', {})
    if actor is None:
        actor = build_actor(user_secure_code, org_secure_code)

    if _identity_matches(task_result_data, user_secure_code, actor.get('role_codes')):
        return {'via': 'self', 'delegator_secure_code': None}

    # 代理授權：排序後取第一個符合者，避免 dict 順序影響記錄結果。
    delegations = actor.get('delegations') or {}
    # 舊形狀 actor 沒有 delegation_scopes 時，維持既有語意：所有授權人不限表單。
    delegation_scopes = actor.get('delegation_scopes')
    for delegator_sc in sorted(delegations):
        if _identity_matches(task_result_data, delegator_sc, delegations[delegator_sc]):
            scope = None if delegation_scopes is None else delegation_scopes.get(delegator_sc)
            if _delegation_scope_allows_task(scope, task, org_secure_code, actor):
                return {'via': 'delegation', 'delegator_secure_code': delegator_sc}

    return None


def delegate_from_fields(identity, org_secure_code) -> dict:
    """換成 FwApprovalRecord 的 delegate_from_* 欄位值。

    本人簽核回 {}。代理簽核會記錄授權人的 secure_code 與顯示名稱。
    這裡刻意不加 User.is_active 條件：本函式只負責寫歷史記錄，不做授權判定；
    授權是否成立已由 get_delegated_identities() 判斷，即使授權人事後停用也要保留姓名。
    """
    if not identity or identity.get('via') != 'delegation':
        return {}

    delegator_sc = identity.get('delegator_secure_code')
    if not delegator_sc:
        return {}

    from app.models.user import User

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
