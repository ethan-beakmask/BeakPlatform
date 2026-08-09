"""
FormWorkflow task action authorization helpers.
"""
from app.models.associations import UserRoleAssignment


def get_actor_role_codes(user_secure_code: str, org_secure_code: str) -> set:
    """取得使用者在指定企業當前有效的角色 secure_code 集合。"""
    assignments = UserRoleAssignment.query.filter(
        UserRoleAssignment.user_secure_code == user_secure_code,
        UserRoleAssignment.org_secure_code == org_secure_code,
        UserRoleAssignment.is_deleted == False,  # noqa: E712
    ).all()
    return {a.role_secure_code for a in assignments if a.is_valid}


def can_act_on_task(
    task,
    user_secure_code: str,
    org_secure_code: str,
    role_codes: set = None,
) -> bool:
    """判斷使用者能否對這個簽核佇列項採取行動。

    role_codes 可由呼叫端預先算好傳入（清單/批次 API 用，避免迴圈內重複查詢）。
    """
    if not task:
        return False

    task_result_data = (task.result or {}).get('data', {})
    assignee_type = task_result_data.get('assignee_type')
    assignee_value = task_result_data.get('assignee_value')
    assignees = task_result_data.get('assignees') or []

    if not assignee_type:
        return True

    if user_secure_code in assignees:
        return True

    if assignee_type == 'ROLE':
        if not assignee_value:
            return False
        if role_codes is None:
            role_codes = get_actor_role_codes(user_secure_code, org_secure_code)
        return assignee_value in role_codes

    # DEPARTMENT is intentionally snapshot-only in L1; INITIATOR/USER/DYNAMIC
    # also keep their original fixed-person semantics.
    return False


def is_pending_assignee(
    task,
    user_secure_code: str,
    org_secure_code: str,
    role_codes: set = None,
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
    return can_act_on_task(task, user_secure_code, org_secure_code, role_codes)
