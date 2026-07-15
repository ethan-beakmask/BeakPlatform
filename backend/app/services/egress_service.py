"""
Egress Service - 資料出口政策引擎

伺服器統一決定哪些資料離開伺服器：
  1. 欄位投影/遮罩（clear/masked/hidden，語境感知）
  2. 逐格揭示（masked 欄位唯一取值通道）
  3. 三水表計量（list_rows/reveal/export）與警戒告警

規格：docs/EGRESS_POLICY_SPEC.md

接入方式（API 序列化處，to_dict 之後）：
    from app.services import egress_service
    items = egress_service.apply('user', 'list', items)
"""
import logging
import time
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

from flask import g, request, has_request_context

from .. import db
from ..models.egress_policy import (
    EgressFieldPolicy, EgressTierThreshold, EgressAuditLog,
    VISIBILITY_CLEAR, VISIBILITY_MASKED, VISIBILITY_HIDDEN, VISIBILITY_ORDER,
)
from ..utils.security import generate_secure_code

logger = logging.getLogger(__name__)

# 政策快取 TTL（秒）：政策異動最遲此秒數後生效
_POLICY_CACHE_TTL = 60
# {(org, resource_code): {'ts': float, 'by_context': {context: [policy_dict]}}}
_policy_cache: Dict[tuple, Dict] = {}

# 揭示值取用註冊表：resource_code -> accessor(record_sc, field_name) -> value
# 平台資源用 register_model_resource 註冊；JSON 資料（如 form_data）
# 由模組載入時 register_accessor 自訂取值函式。
_RESOURCE_ACCESSORS: Dict[str, Callable[[str, str], Any]] = {}


# =============================================================================
# 註冊
# =============================================================================

def register_accessor(resource_code: str, accessor: Callable[[str, str], Any]) -> None:
    """註冊揭示取值函式。accessor(record_sc, field_name) 需自行做租戶隔離。"""
    _RESOURCE_ACCESSORS[resource_code] = accessor


def register_model_resource(resource_code: str, model_class) -> None:
    """以 ResourceGateway 為取值通道註冊 ORM 資源（自帶租戶隔離與權限檢查）。"""
    def _accessor(record_sc: str, field_name: str):
        from ..security.resource_gateway import ResourceGateway
        resource = ResourceGateway.get(model_class, record_sc)
        if not hasattr(resource, field_name):
            raise KeyError(field_name)
        return getattr(resource, field_name)
    register_accessor(resource_code, _accessor)


def invalidate_cache(org_secure_code: str = None) -> None:
    """政策異動後呼叫；不呼叫最遲 TTL 後自然失效。"""
    if org_secure_code is None:
        _policy_cache.clear()
        return
    for key in [k for k in _policy_cache if k[0] == org_secure_code]:
        _policy_cache.pop(key, None)


# =============================================================================
# 政策解析
# =============================================================================

def _load_policies(org: str, resource_code: str) -> Dict[str, List[dict]]:
    """讀取（快取）某資源的全部有效政策，依 context 分組。"""
    cache_key = (org, resource_code)
    cached = _policy_cache.get(cache_key)
    if cached and time.time() - cached['ts'] < _POLICY_CACHE_TTL:
        return cached['by_context']

    rows = EgressFieldPolicy.query.filter_by(
        org_secure_code=org,
        resource_code=resource_code,
        is_deleted=False,
        is_active=True,
    ).all()

    by_context: Dict[str, List[dict]] = {}
    for p in rows:
        by_context.setdefault(p.context, []).append({
            'field_name': p.field_name,
            'role_secure_code': p.role_secure_code,
            'department_secure_code': p.department_secure_code,
            'node_key': p.node_key,
            'visibility': p.visibility,
            'tier': p.tier,
        })

    _policy_cache[cache_key] = {'ts': time.time(), 'by_context': by_context}
    return by_context


def _current_user():
    from flask_login import current_user
    if current_user and getattr(current_user, 'is_authenticated', False):
        return current_user
    return None


def _user_scopes(user) -> tuple:
    """回傳 (role_sc_set, dept_sc_set)。"""
    role_scs = set()
    for role in getattr(user, 'roles', []) or []:
        sc = getattr(role, 'secure_code', None)
        if sc:
            role_scs.add(sc)
    dept_scs = set()
    for membership in getattr(user, 'unit_memberships', []) or []:
        unit = getattr(membership, 'unit', None)
        if unit and getattr(unit, 'secure_code', None):
            dept_scs.add(unit.secure_code)
    return role_scs, dept_scs


def _resolve_field_policies(
    policies: List[dict],
    role_scs: set,
    dept_scs: set,
    node_key: str = None,
) -> Dict[str, dict]:
    """
    解析每個欄位的生效政策。

    優先序（先命中先用，同級取最嚴格）：
      1. 角色+部門都相符
      2. 角色相符且政策部門為 NULL
      3. 資源預設（政策角色為 NULL）
    form_node 語境時，帶 node_key 的政策只在 node_key 相符時參與比對；
    node_key 為 NULL 的政策視為該語境通用。
    """
    # field -> level -> policy（同級保留最嚴格）
    candidates: Dict[str, Dict[int, dict]] = {}

    for p in policies:
        if p['node_key'] and p['node_key'] != node_key:
            continue

        if p['role_secure_code']:
            if p['role_secure_code'] not in role_scs:
                continue
            if p['department_secure_code']:
                if p['department_secure_code'] not in dept_scs:
                    continue
                level = 1
            else:
                level = 2
        else:
            level = 3

        field = p['field_name']
        existing = candidates.setdefault(field, {}).get(level)
        if (existing is None or
                VISIBILITY_ORDER[p['visibility']] > VISIBILITY_ORDER[existing['visibility']]):
            candidates[field][level] = p

    effective = {}
    for field, by_level in candidates.items():
        best_level = min(by_level.keys())
        effective[field] = by_level[best_level]
    return effective


# =============================================================================
# 出口過濾
# =============================================================================

def apply(
    resource_code: str,
    context: str,
    items: List[Dict[str, Any]],
    *,
    record_sc_key: str = 'secure_code',
    node_key: str = None,
    meter: bool = True,
) -> List[Dict[str, Any]]:
    """
    對序列化後的 dict 清單套用出口政策。

    - hidden 欄位剔除；masked 欄位換哨兵（真值不出手）
    - 未設任何政策的資源為 no-op（不過濾、不計量、不稽核）
    - 需要 request context；無用戶上下文（背景任務）不過濾

    Args:
        resource_code: 資源代碼（揭示端點以此對應 accessor）
        context: list / detail / form_node / export
        items: to_dict() 後的 dict 清單（就地修改並回傳）
        record_sc_key: 記錄識別欄位名（哨兵與稽核用）
        node_key: form_node 語境的節點鍵
        meter: 是否計量（背景匯出可關）
    """
    if not items or not has_request_context():
        return items

    user = _current_user()
    if user is None:
        return items

    org = getattr(user, 'org_secure_code', None) or getattr(g, 'tenant', None)
    if not org:
        return items

    by_context = _load_policies(org, resource_code)
    if not any(by_context.values()):
        return items  # 未設政策：no-op，不記稽核噪音

    policies = by_context.get(context, [])
    role_scs, dept_scs = _user_scopes(user)
    effective = _resolve_field_policies(policies, role_scs, dept_scs, node_key)

    max_tier = 'normal'
    for item in items:
        record_sc = item.get(record_sc_key)
        for field, policy in effective.items():
            if field not in item:
                continue
            if policy['visibility'] == VISIBILITY_HIDDEN:
                item.pop(field, None)
            elif policy['visibility'] == VISIBILITY_MASKED:
                item[field] = {
                    '__masked': True,
                    'resource': resource_code,
                    'record_sc': record_sc,
                    'field': field,
                }
            if policy['tier'] != 'normal':
                max_tier = policy['tier']

    if meter:
        _record_and_meter(
            user=user, org=org, resource_code=resource_code,
            context=context,
            action='export' if context == 'export' else
                   ('detail' if context == 'detail' else 'list'),
            record_scs=[i.get(record_sc_key) for i in items if i.get(record_sc_key)],
            row_count=len(items),
            tier=max_tier,
        )

    return items


# =============================================================================
# 伺服端渲染（Jinja）輔助
# =============================================================================

def field_visibility(resource_code: str, context: str, field_name: str) -> str:
    """單一欄位對當前用戶的能見度（Jinja 模板用）。無政策/無用戶 → clear。"""
    if not has_request_context():
        return VISIBILITY_CLEAR
    user = _current_user()
    if user is None:
        return VISIBILITY_CLEAR
    org = getattr(user, 'org_secure_code', None)
    if not org:
        return VISIBILITY_CLEAR
    policies = _load_policies(org, resource_code).get(context, [])
    if not policies:
        return VISIBILITY_CLEAR
    role_scs, dept_scs = _user_scopes(user)
    effective = _resolve_field_policies(policies, role_scs, dept_scs)
    policy = effective.get(field_name)
    return policy['visibility'] if policy else VISIBILITY_CLEAR


def meter_view(resource_code: str, context: str, record_scs: List[str]) -> None:
    """伺服端渲染頁的出口計量（web route 於 render_template 前呼叫）。"""
    if not has_request_context():
        return
    user = _current_user()
    if user is None:
        return
    org = getattr(user, 'org_secure_code', None)
    if not org:
        return
    by_context = _load_policies(org, resource_code)
    if not any(by_context.values()):
        return  # 未設政策不記稽核噪音
    role_scs, dept_scs = _user_scopes(user)
    effective = _resolve_field_policies(
        by_context.get(context, []), role_scs, dept_scs)
    max_tier = 'normal'
    for policy in effective.values():
        if policy['tier'] != 'normal':
            max_tier = policy['tier']
    _record_and_meter(
        user=user, org=org, resource_code=resource_code,
        context=context,
        action='detail' if context == 'detail' else 'list',
        record_scs=record_scs, row_count=len(record_scs), tier=max_tier,
    )


# =============================================================================
# 揭示
# =============================================================================

class RevealDenied(Exception):
    pass


def reveal(resource_code: str, record_sc: str, field_name: str) -> Any:
    """
    揭示單一 masked 格的真值。masked 欄位唯一的取值通道。

    政策檢查：欄位在 list 或 detail 任一語境對該用戶為 masked 才可揭示；
    兩語境皆 hidden 則拒絕。
    """
    user = _current_user()
    if user is None:
        raise RevealDenied('未登入')

    org = getattr(user, 'org_secure_code', None)
    by_context = _load_policies(org, resource_code)
    role_scs, dept_scs = _user_scopes(user)

    allowed = False
    tier = 'normal'
    seen_policy = False
    for context in ('list', 'detail', 'form_node'):
        effective = _resolve_field_policies(
            by_context.get(context, []), role_scs, dept_scs)
        policy = effective.get(field_name)
        if policy is None:
            continue
        seen_policy = True
        if policy['visibility'] == VISIBILITY_MASKED:
            allowed = True
            tier = policy['tier']
    if not seen_policy:
        raise RevealDenied('欄位未設遮罩政策')
    if not allowed:
        raise RevealDenied('無揭示權限')

    accessor = _RESOURCE_ACCESSORS.get(resource_code)
    if accessor is None:
        raise RevealDenied(f'資源 {resource_code} 未註冊揭示通道')

    value = accessor(record_sc, field_name)

    _record_and_meter(
        user=user, org=org, resource_code=resource_code,
        context='reveal', action='reveal',
        record_scs=[record_sc], row_count=1,
        tier=tier, field_name=field_name,
    )
    return value


# =============================================================================
# 計量與警戒
# =============================================================================

_METER_BY_ACTION = {
    'list': 'list_rows',
    'detail': 'list_rows',
    'reveal': 'reveal',
    'export': 'export',
}


def _record_and_meter(*, user, org, resource_code, context, action,
                      record_scs, row_count, tier, field_name=None) -> None:
    """寫出口稽核 + 檢查水表閾值。稽核失敗不阻斷主流程。"""
    try:
        log = EgressAuditLog(
            secure_code=generate_secure_code(),
            org_secure_code=org,
            user_secure_code=user.secure_code,
            resource_code=resource_code,
            context=context,
            action=action,
            record_scs=record_scs,
            field_name=field_name,
            row_count=row_count,
            tier=tier,
            ip_address=request.remote_addr if request else None,
        )
        db.session.add(log)
        _check_threshold(user=user, org=org, tier=tier,
                         meter=_METER_BY_ACTION[action])
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.exception(
            f'Egress 稽核寫入失敗 resource={resource_code} '
            f'user={user.secure_code}'
        )


def _check_threshold(*, user, org, tier, meter) -> None:
    """滑動時間窗檢查水表；達閾值插 alert 廣播（同窗冷卻不重複）。"""
    threshold_row = EgressTierThreshold.query.filter_by(
        org_secure_code=org, tier=tier, meter=meter,
        is_active=True, is_deleted=False,
    ).first()
    if threshold_row is None:
        return

    window_start = datetime.utcnow() - timedelta(
        minutes=threshold_row.window_minutes)

    actions = [a for a, m in _METER_BY_ACTION.items() if m == meter]
    total = db.session.query(
        db.func.coalesce(db.func.sum(EgressAuditLog.row_count), 0)
    ).filter(
        EgressAuditLog.org_secure_code == org,
        EgressAuditLog.user_secure_code == user.secure_code,
        EgressAuditLog.tier == tier,
        EgressAuditLog.action.in_(actions),
        EgressAuditLog.created_at >= window_start,
    ).scalar()

    if total < threshold_row.threshold:
        return

    # 冷卻：同窗內已告警過就不重複
    recent_alert = EgressAuditLog.query.filter(
        EgressAuditLog.org_secure_code == org,
        EgressAuditLog.user_secure_code == user.secure_code,
        EgressAuditLog.action == 'alert',
        EgressAuditLog.meter == meter,
        EgressAuditLog.created_at >= window_start,
    ).first()
    if recent_alert:
        return

    db.session.add(EgressAuditLog(
        secure_code=generate_secure_code(),
        org_secure_code=org,
        user_secure_code=user.secure_code,
        resource_code='-',
        context='-',
        action='alert',
        row_count=int(total),
        tier=tier,
        meter=meter,
    ))
    _create_alert_broadcast(user=user, org=org, tier=tier,
                            meter=meter, total=int(total),
                            window_minutes=threshold_row.window_minutes)
    logger.warning(
        f'Egress 水表警戒: user={user.secure_code} tier={tier} '
        f'meter={meter} total={total} window={threshold_row.window_minutes}m'
    )


def _create_alert_broadcast(*, user, org, tier, meter, total, window_minutes) -> None:
    """插入 alert 廣播（既有 /api/broadcasts/active 管道），目標為企業管理員。"""
    from ..models.lookup_item import LookupItem

    meter_labels = {
        'list_rows': '資料瀏覽筆數',
        'reveal': '敏感欄位揭示次數',
        'export': '資料匯出筆數',
    }
    username = getattr(user, 'username', user.secure_code)
    title = '資料出口警戒'
    message = (
        f'用戶 {username} 於 {window_minutes} 分鐘內的'
        f'{meter_labels.get(meter, meter)}達 {total}，'
        f'超過敏感度分級 {tier} 的警戒值，請查核是否為異常存取。'
    )
    db.session.add(LookupItem(
        secure_code=generate_secure_code(),
        org_secure_code=org,
        category_code='broadcast',
        code=f'EGRESS-ALERT-{generate_secure_code()[:8]}',
        label=title,
        value={
            'type': 'alert',
            'title': title,
            'message': message,
            'require_ack': True,
            # 只推給管理層：靠角色 code 過濾（_user_in_target 支援 role code）
            'target': {'type': 'specific', 'roles': ['ORG_ADMIN']},
        },
        sort_order=0,
        is_active=True,
    ))
