"""Page IR form workflow submission resource resolver."""
from __future__ import annotations

import logging

from flask_babel import gettext as _

from app import db
from app.pageir.registry import register_resource_lister, register_resource_provider

from modules.form_workflow.models import (
    FwFormInstance,
    FwNodeExecutionQueue,
    FwWorkflowInstance,
    FwWorkflowVariable,
)

from ..models.sub_system import DcSubSystem
from .portal_auth_service import nocode_user_ref

logger = logging.getLogger(__name__)

RESOURCE_CODE = "formflow:submissions"
FIELDS = [
    "serial_number",
    "execution_code",
    "subject",
    "status_label",
    "current_step",
    "submitted_at",
]
_SORT_FIELDS = {
    "submitted_at": FwFormInstance.submitted_at,
    "serial_number": FwFormInstance.serial_number,
    "execution_code": FwWorkflowInstance.execution_code,
}
_REJECTED_STATUSES = {
    "FAILED",
    "ERROR",
    "CANCELLED",
    "CANCELED",
    "REJECTED",
    "TERMINATED",
    "ABORTED",
}


def init_formflow_pageir_resources() -> None:
    """Register formflow-prefixed Page IR resources."""
    register_resource_provider("formflow", _resolve_formflow_resource)
    register_resource_lister(_list_formflow_resources)


def _resolve_formflow_resource(code: str, ctx: dict) -> dict | None:
    if code != RESOURCE_CODE:
        return None

    sub_system_sc = (ctx or {}).get("sub_system_sc")
    portal_user = (ctx or {}).get("portal_user")
    if not sub_system_sc or not portal_user:
        return None

    sub_system = DcSubSystem.query.filter_by(
        secure_code=sub_system_sc,
        is_deleted=False,
    ).first()
    if not sub_system:
        return None

    try:
        user_ref = nocode_user_ref(sub_system_sc, portal_user)
    except Exception:
        logger.exception(
            "Failed to resolve portal nocode user ref: sub_system=%s",
            sub_system_sc,
        )
        return None

    def fetch_list(fields, page, page_size, sort_field, sort_dir):
        return _fetch_list(
            sub_system.org_secure_code,
            sub_system_sc,
            user_ref,
            fields,
            page,
            page_size,
            sort_field,
            sort_dir,
        )

    def fetch_detail(record_sc, fields):
        return _fetch_detail(
            sub_system.org_secure_code,
            sub_system_sc,
            user_ref,
            record_sc,
            fields,
        )

    return {
        "fields": FIELDS,
        "writable_fields": [],
        "crud": {"create": False, "update": False, "delete": False},
        "egress_resource": None,
        "views": ["list", "detail"],
        "fetch_list": fetch_list,
        "fetch_detail": fetch_detail,
        "create_row": lambda payload: (False, "readonly"),
        "update_row": lambda record_sc, payload: (False, "readonly"),
        "delete_row": lambda record_sc: (False, "readonly"),
    }


def _list_formflow_resources(sub_system_sc: str) -> list[dict]:
    if not sub_system_sc:
        return []
    return [{
        "code": RESOURCE_CODE,
        "name": _("我送出的表單"),
        "views": ["list", "detail"],
        "fields": FIELDS,
        "writable_fields": [],
        "crud": {"create": False, "update": False, "delete": False},
        "egress_resource": None,
    }]


def _base_query(org_secure_code: str, sub_system_sc: str, user_ref: str):
    return db.session.query(FwWorkflowInstance, FwFormInstance).join(
        FwFormInstance,
        FwFormInstance.secure_code == FwWorkflowInstance.form_instance_secure_code,
    ).filter(
        FwWorkflowInstance.org_secure_code == org_secure_code,
        FwWorkflowInstance.nocode_sub_system_sc == sub_system_sc,
        FwWorkflowInstance.nocode_user_ref == user_ref,
        FwWorkflowInstance.is_deleted.is_(False),
        FwFormInstance.org_secure_code == org_secure_code,
        FwFormInstance.is_deleted.is_(False),
    )


def _fetch_list(
    org_secure_code: str,
    sub_system_sc: str,
    user_ref: str,
    fields: list[str],
    page,
    page_size,
    sort_field,
    sort_dir,
):
    page = max(int(page or 1), 1)
    page_size = max(int(page_size or 20), 1)
    base_query = _base_query(org_secure_code, sub_system_sc, user_ref)
    total = base_query.count()

    sort_column = _SORT_FIELDS[sort_field] if sort_field in _SORT_FIELDS else FwFormInstance.submitted_at
    direction = (sort_dir or "desc").lower()
    if sort_field not in _SORT_FIELDS or direction not in {"asc", "desc"}:
        direction = "desc"
    order_by = sort_column.asc() if direction == "asc" else sort_column.desc()

    pairs = (
        base_query
        .order_by(order_by, FwFormInstance.secure_code.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    waiting = _waiting_steps([wi.secure_code for wi, _fi in pairs], org_secure_code)
    rows = [_submission_row(wi, fi, waiting, fields) for wi, fi in pairs]
    return rows, total


def _fetch_detail(
    org_secure_code: str,
    sub_system_sc: str,
    user_ref: str,
    record_sc: str,
    fields: list[str],
):
    if not record_sc:
        return None
    pair = _base_query(org_secure_code, sub_system_sc, user_ref).filter(
        FwFormInstance.secure_code == record_sc,
    ).first()
    if not pair:
        return None
    wi, fi = pair
    waiting = _waiting_steps([wi.secure_code], org_secure_code)
    return _submission_row(wi, fi, waiting, fields)


def is_submission_editable(workflow_instance_secure_code: str) -> bool:
    """流程變數 nocode_editable 是否開放外部用戶修改此筆送件。

    刻意**不走** `VariableService.get_flow_var()`：那層有一份類別層級、
    無 TTL 的進程內快取，多 worker 部署下流程把變數改成 false 之後，
    其他 worker 仍會讀到舊的 true。用過期值做顯示只是難看，
    用過期值做授權判定就是漏洞，所以這裡直接查 DB。

    未設定或任何無法明確判讀為真的值 → 一律唯讀（fail-closed）。
    """
    var = FwWorkflowVariable.query.filter_by(
        workflow_instance_secure_code=workflow_instance_secure_code,
        var_name="nocode_editable",
        var_type="FLOW",
    ).first()
    value = var.var_value if var else None
    if value is True or value == 1:
        return True
    if isinstance(value, str) and value in {"true", "True", "1"}:
        return True
    return False


def _owned_submission(record_sc: str, ctx: dict):
    """Return (workflow_instance, form_instance) owned by the current portal user.

    三重過濾（org / 子系統 / user_ref）全部在 SQL WHERE。
    任何呼叫端都必須經由本函式取得 form_instance，
    不可以自行再查一次 FwFormInstance —— 第二次查詢很容易漏掉 user_ref，
    那就是 IDOR。
    """
    if not record_sc:
        return None
    sub_system_sc = (ctx or {}).get("sub_system_sc")
    portal_user = (ctx or {}).get("portal_user")
    if not sub_system_sc or not portal_user:
        return None

    sub_system = DcSubSystem.query.filter_by(
        secure_code=sub_system_sc,
        is_deleted=False,
    ).first()
    if not sub_system:
        return None

    try:
        user_ref = nocode_user_ref(sub_system_sc, portal_user)
    except Exception:
        logger.exception(
            "Failed to resolve portal nocode user ref: sub_system=%s",
            sub_system_sc,
        )
        return None

    return _base_query(
        sub_system.org_secure_code,
        sub_system_sc,
        user_ref,
    ).filter(
        FwFormInstance.secure_code == record_sc,
    ).first()


def resolve_submission_state(record_sc: str, ctx: dict) -> dict | None:
    """Return form state for a portal-owned formflow submission."""
    pair = _owned_submission(record_sc, ctx)
    if not pair:
        return None
    wi, fi = pair
    return {
        "form_data": fi.form_data if isinstance(fi.form_data, dict) else {},
        "editable": is_submission_editable(wi.secure_code),
    }


def get_editable_submission(record_sc: str, ctx: dict):
    """Return the FwFormInstance the current portal user is allowed to edit.

    無權存取、查無此筆、或流程變數未開放修改時一律回 None。
    更新端點必須用這支取得 instance，不要自行再查一次。
    """
    pair = _owned_submission(record_sc, ctx)
    if not pair:
        return None
    wi, fi = pair
    if not is_submission_editable(wi.secure_code):
        return None
    return fi


def _waiting_steps(workflow_instance_codes: list[str], org_secure_code: str) -> dict[str, str]:
    if not workflow_instance_codes:
        return {}
    items = (
        FwNodeExecutionQueue.query
        .filter(
            FwNodeExecutionQueue.org_secure_code == org_secure_code,
            FwNodeExecutionQueue.workflow_instance_secure_code.in_(workflow_instance_codes),
            FwNodeExecutionQueue.status == "WAITING",
            FwNodeExecutionQueue.node_type.in_(["Approve", "FormAdapter", "FORMADAPTER"]),
            FwNodeExecutionQueue.is_deleted.is_(False),
        )
        .order_by(FwNodeExecutionQueue.scheduled_at.asc())
        .all()
    )
    steps: dict[str, str] = {}
    for item in items:
        steps.setdefault(item.workflow_instance_secure_code, item.node_name or "")
    return steps


def _submission_row(
    wi: FwWorkflowInstance,
    fi: FwFormInstance,
    waiting_steps: dict[str, str],
    fields: list[str],
) -> dict:
    requested = [field for field in fields if field in FIELDS]
    has_waiting = wi.secure_code in waiting_steps
    values = {
        "serial_number": fi.serial_number,
        "execution_code": wi.execution_code,
        "subject": fi.subject,
        "status_label": _status_label(wi.status, has_waiting),
        "current_step": waiting_steps.get(wi.secure_code, ""),
        "submitted_at": fi.submitted_at,
    }
    row = {field: values.get(field) for field in requested}
    row["_sc"] = fi.secure_code
    row["_can_cancel"] = (wi.status == "RUNNING")
    return row


def _status_label(status: str | None, has_waiting: bool) -> str:
    if status == "RUNNING":
        return _("審核中") if has_waiting else _("處理中")
    if status == "COMPLETED":
        return _("已完成")
    if status in _REJECTED_STATUSES:
        return _("已退回")
    return _("處理中")
