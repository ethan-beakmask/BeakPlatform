"""Page IR BeakPlatform 平台資源註冊。"""
from __future__ import annotations

from app.pageir.registry import register_resource


USER_FIELDS = [
    "username",
    "display_name",
    "email",
    "user_type",
    "created_at",
    "backup_email_1",
    "mobile_phone_1",
]


def init_pageir_resources(app) -> None:
    """註冊 BeakPlatform Page IR pilot resources。"""
    del app
    register_resource(
        "user",
        {
            "fields": USER_FIELDS,
            "egress_resource": "user",
            "views": ["list", "detail"],
            "fetch_list": _fetch_user_list,
            "fetch_detail": _fetch_user_detail,
        },
    )


def _fetch_user_list(fields, page, page_size, sort_field, sort_dir):
    from app.models.user import User
    from app.security.resource_gateway import ResourceGateway

    order_by = None
    if sort_field in USER_FIELDS:
        order_by = f"-{sort_field}" if sort_dir == "desc" else sort_field

    result = ResourceGateway.list(
        User,
        page=page,
        per_page=page_size,
        order_by=order_by,
        is_deleted=False,
        is_active=True,
    )
    rows = [_user_row(user, fields) for user in result["items"]]
    return rows, result["total"]


def _fetch_user_detail(record_sc, fields):
    from app.models.user import User
    from app.security.resource_gateway import ResourceGateway

    user = ResourceGateway.get(
        User,
        record_sc,
        raise_on_not_found=False,
    )
    if not user or user.is_deleted or not user.is_active:
        return None
    return _user_row(user, fields)


def _user_row(user, fields):
    row = {field: getattr(user, field) for field in fields if field in USER_FIELDS}
    row["_sc"] = user.secure_code
    return row
