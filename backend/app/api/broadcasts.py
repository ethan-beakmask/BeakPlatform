"""
廣播系統 API

[標準 AUTH-02] 統一認證 decorator
[標準 TENANT-01] 強制企業隔離

端點：
- GET  /api/broadcasts/active           取得當前用戶可見的 active 廣播
- POST /api/broadcasts/<sc>/acknowledge  確認已讀（AlertBroadcast）
"""
from datetime import datetime
from flask import Blueprint, jsonify, request
from flask_login import current_user

from .. import db, limiter
from ..models import LookupItem, BroadcastAcknowledgment, User
from ..models.organizational_unit import OrganizationalUnit
from ..security.decorators import login_required

broadcasts_bp = Blueprint(
    'api_broadcasts',
    __name__,
    url_prefix='/api/broadcasts'
)


@broadcasts_bp.route('/active', methods=['GET'])
@login_required
@limiter.exempt
def get_active_broadcasts():
    """
    取得當前用戶可見的 active 廣播

    前端定時 polling 此 API。同時回傳 navbar 和 alert 兩種類型。
    alert 類型會檢查 target 並排除已確認的。
    自動將過期的 navbar 廣播標記為 inactive。
    """
    org_code = current_user.org_secure_code
    now = datetime.utcnow()

    # 設定 RLS context，讓 lookup_items SELECT policy 通過
    db.session.execute(
        db.text("SELECT set_config('app.current_org', :org, true)"),
        {'org': org_code}
    )

    # 查詢所有 active 廣播
    items = LookupItem.query.filter_by(
        org_secure_code=org_code,
        category_code='broadcast',
        is_active=True,
        is_deleted=False,
    ).all()

    # 取得用戶已確認的廣播
    acked_codes = set()
    ack_rows = BroadcastAcknowledgment.query.filter_by(
        user_secure_code=current_user.secure_code,
        is_deleted=False,
    ).all()
    for ack in ack_rows:
        acked_codes.add(ack.broadcast_secure_code)

    navbar_broadcasts = []
    alert_broadcasts = []

    for item in items:
        value = item.value or {}
        btype = value.get('type', '')

        if btype == 'navbar':
            # 檢查過期
            expires_at_str = value.get('expires_at')
            if expires_at_str:
                try:
                    expires_at = datetime.fromisoformat(expires_at_str)
                    if now >= expires_at:
                        item.is_active = False
                        db.session.commit()
                        continue
                except (ValueError, TypeError):
                    pass

            navbar_broadcasts.append({
                'secure_code': item.secure_code,
                'code': item.code,
                'message': value.get('message', ''),
                'text_color': value.get('text_color', '#000000'),
                'bg_color': value.get('bg_color', '#FDE047'),
                'display_seconds': value.get('display_seconds', 5),
            })

        elif btype == 'alert':
            # 已確認的不再推送
            if item.secure_code in acked_codes:
                continue

            # 目標過濾
            if not _user_in_target(current_user, value.get('target', {})):
                continue

            alert_broadcasts.append({
                'secure_code': item.secure_code,
                'code': item.code,
                'title': value.get('title', ''),
                'message': value.get('message', ''),
                'require_ack': value.get('require_ack', True),
            })

    return jsonify({
        'success': True,
        'navbar': navbar_broadcasts,
        'alerts': alert_broadcasts,
    })


@broadcasts_bp.route('/<secure_code>/acknowledge', methods=['POST'])
@login_required
def acknowledge_broadcast(secure_code):
    """
    確認已讀廣播

    幂等操作 - 重複確認不會報錯。
    """
    org_code = current_user.org_secure_code

    # 設定 RLS context
    db.session.execute(
        db.text("SELECT set_config('app.current_org', :org, true)"),
        {'org': org_code}
    )

    # 確認廣播存在
    item = LookupItem.query.filter_by(
        secure_code=secure_code,
        org_secure_code=org_code,
        category_code='broadcast',
        is_deleted=False,
    ).first()

    if not item:
        return jsonify({'success': False, 'message': '找不到廣播'}), 404

    # 檢查是否已確認（幂等）
    existing = BroadcastAcknowledgment.query.filter_by(
        broadcast_secure_code=secure_code,
        user_secure_code=current_user.secure_code,
        is_deleted=False,
    ).first()

    if existing:
        return jsonify({'success': True, 'message': '已確認'})

    from ..utils.security import generate_secure_code

    ack = BroadcastAcknowledgment(
        secure_code=generate_secure_code(),
        broadcast_secure_code=secure_code,
        user_secure_code=current_user.secure_code,
        org_secure_code=org_code,
        acknowledged_at=datetime.utcnow(),
    )
    db.session.add(ack)
    db.session.commit()

    return jsonify({'success': True, 'message': '確認成功'})


def _user_in_target(user, target: dict) -> bool:
    """
    檢查用戶是否在廣播目標範圍內

    target 格式：
    - {"type": "all"} -- 全企業
    - {"type": "specific", "roles": [...], "departments": [...], "include_children": true}
    """
    target_type = target.get('type', 'all')

    if target_type == 'all':
        return True

    if target_type != 'specific':
        return True

    target_roles = target.get('roles', [])
    target_depts = target.get('departments', [])
    include_children = target.get('include_children', True)

    # 檢查角色
    if target_roles:
        user_role_codes = set()
        if hasattr(user, 'roles'):
            for role in user.roles:
                if hasattr(role, 'code'):
                    user_role_codes.add(role.code)
                if hasattr(role, 'secure_code'):
                    user_role_codes.add(role.secure_code)
        if user_role_codes & set(target_roles):
            return True

    # 檢查部門
    if target_depts:
        user_dept_codes = set()
        if hasattr(user, 'unit_memberships'):
            for membership in user.unit_memberships:
                unit = membership.unit if hasattr(membership, 'unit') else None
                if unit:
                    user_dept_codes.add(unit.secure_code)
                    if include_children and hasattr(unit, 'full_path') and unit.full_path:
                        # full_path 包含所有上層 code，展開後任一匹配即可
                        pass  # secure_code 已加入

        # 如果 include_children，檢查目標部門的子部門
        if include_children:
            expanded_depts = set(target_depts)
            for dept_code in target_depts:
                children = OrganizationalUnit.query.filter(
                    OrganizationalUnit.org_secure_code == user.org_secure_code,
                    OrganizationalUnit.full_path.like(f'%{dept_code}%'),
                    OrganizationalUnit.is_active == True,
                    OrganizationalUnit.is_deleted == False,
                ).all()
                for child in children:
                    expanded_depts.add(child.secure_code)
            if user_dept_codes & expanded_depts:
                return True
        else:
            if user_dept_codes & set(target_depts):
                return True

    return False
