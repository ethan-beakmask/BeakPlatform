"""Approval history serialization helpers."""


def _role_names_by_code(org_secure_code: str, role_codes: set[str]) -> dict[str, str]:
    if not role_codes:
        return {}

    from app.models.role import Role

    roles = Role.query.filter(
        Role.org_secure_code == org_secure_code,
        Role.code.in_(role_codes),
        Role.is_deleted == False,  # noqa: E712
    ).all()
    return {role.code: role.name for role in roles}


def serialize_approval_history(approval_records, org_secure_code: str) -> list[dict]:
    """Serialize approval records and resolve acted_as role names once per request."""
    role_codes = {
        approval.acted_as_role_code
        for approval in approval_records
        if approval.acted_as_role_code
    }
    role_names = _role_names_by_code(org_secure_code, role_codes)

    return [
        {
            'node_id': approval.node_id,
            'node_name': approval.node_name,
            'approver_name': approval.approver_name,
            'delegate_from_name': approval.delegate_from_name,
            'acted_as_role_code': approval.acted_as_role_code,
            'acted_as_kind': approval.acted_as_kind,
            'acted_as_role_name': role_names.get(approval.acted_as_role_code),
            'action': approval.action,
            'comment': approval.comment,
            'acted_at': approval.acted_at.isoformat() if approval.acted_at else None,
        }
        for approval in approval_records
    ]
