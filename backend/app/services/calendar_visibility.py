"""行事曆事件可見性規則。"""

MASKED_TITLE_KEY = 'BUSY'


def _strip_audience(event: dict) -> dict:
    result = dict(event)
    result.pop('audience', None)
    return result


def apply_visibility(event: dict, viewer) -> dict | None:
    """依 viewer 回傳完整事件、遮罩事件，或 None。"""
    audience = event.get('audience')
    if audience:
        users = set(audience.get('users') or [])
        allowed = (
            viewer.secure_code in users
            or (audience.get('org_admin') is True and viewer.is_org_admin)
            or audience.get('everyone') is True
        )
        if not allowed:
            return None
        result = _strip_audience(event)
        result['masked'] = False
        return result

    if event.get('calendar_kind') == 'ORG':
        result = _strip_audience(event)
        result['masked'] = False
        return result

    if event.get('calendar_kind') != 'PERSONAL':
        return None

    if event.get('owner_user_secure_code') == viewer.secure_code:
        result = _strip_audience(event)
        result['masked'] = False
        return result

    visibility = event.get('visibility')
    if visibility == 'PUBLIC':
        result = _strip_audience(event)
        result['masked'] = False
        return result

    if visibility == 'BUSY':
        result = _strip_audience(event)
        result.update({
            'masked': True,
            'title': None,
            'note': None,
            'link': None,
            'event_type': MASKED_TITLE_KEY,
            'editable': False,
        })
        return result

    return None
