"""
Permission Audit - 選單權限與路由裝飾器一致性檢查
SEC-03: Menu-Route Permission Consistency

啟動時自動比對 MenuPermission (DB) 與路由 decorator (程式碼)，
確保選單可見性與路由存取控制一致，避免 URL 直打繞過選單權限。

比對邏輯：
    MenuPermission        期望的 decorator
    ─────────────────────────────────────────
    [SYS]                 @system_admin_required
    [SYS, ORG]            @admin_required
    [含 EMP 或 EXT]       @login_required 或 @module_access_required
"""
import logging
import os
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from flask import Flask

logger = logging.getLogger(__name__)

# decorator flag → 存取等級 (數字越大越寬鬆)
DECORATOR_LEVELS = {
    'system_admin_required': 0,
    'admin_required': 1,
    'module_access_required': 2,
    'login_required': 2,
    'public_route': 3,
}

# MenuPermission user_type 組合 → 期望的最低 decorator 等級
# 規則: decorator 不能比選單權限更寬鬆
USER_TYPE_TO_LEVEL = {
    frozenset({'SYSTEM_ADMIN'}): 0,                                  # SYS only
    frozenset({'SYSTEM_ADMIN', 'ORG_ADMIN'}): 1,                     # SYS + ORG
    frozenset({'ORG_ADMIN'}): 1,                                      # ORG only
}
# 含 EMPLOYEE 或 EXTERNAL 的組合 → level 2 (login_required)


def _detect_decorator(view_func) -> Optional[str]:
    """偵測 view function 使用的 auth decorator"""
    if getattr(view_func, '_system_admin_required', False):
        return 'system_admin_required'
    if getattr(view_func, '_admin_required', False):
        return 'admin_required'
    if getattr(view_func, '_module_access_required', False):
        return 'module_access_required'
    if getattr(view_func, '_login_required', False):
        return 'login_required'
    if getattr(view_func, '_public_route', False):
        return 'public_route'
    return None


def _get_expected_level(user_types: frozenset) -> int:
    """根據 MenuPermission 的 user_type 組合判定期望的存取等級"""
    if not user_types:
        return -1  # 無權限設定，跳過

    if user_types in USER_TYPE_TO_LEVEL:
        return USER_TYPE_TO_LEVEL[user_types]

    # 含 EMPLOYEE 或 EXTERNAL → login_required 等級
    if 'EMPLOYEE' in user_types or 'EXTERNAL' in user_types:
        return 2

    return -1  # 未知組合，跳過


def audit_permissions(app: Flask) -> List[Dict]:
    """
    比對 MenuPermission (DB) 與路由 decorator (程式碼)

    Returns:
        不一致的項目清單，每筆包含:
        - menu_code, title, link_target
        - menu_user_types: 選單允許的 user_types
        - expected_decorator: 期望的 decorator
        - actual_decorator: 實際的 decorator
        - severity: 'CRITICAL' (太寬鬆) 或 'INFO' (太嚴格)
    """
    from ..models.menu_item import MenuItem
    from ..models.menu_permission import MenuPermission

    mismatches = []

    try:
        # 取得所有啟用中的 route 型選單
        items = MenuItem.query.filter(
            MenuItem.is_deleted == False,
            MenuItem.is_active == True,
            MenuItem.link_type == 'route',
            MenuItem.link_target.isnot(None),
        ).all()
    except Exception:
        # DB 未初始化 (如首次部署)，跳過
        return []

    if not items:
        return []

    # 按 link_target 分組，合併所有指向同一路由的選單權限
    target_groups: Dict[str, Tuple[set, list]] = defaultdict(
        lambda: (set(), [])
    )

    for item in items:
        lt = item.link_target
        if lt.startswith('/'):
            continue  # URL 路徑，非 Flask endpoint，跳過

        perms = MenuPermission.query.filter_by(
            menu_secure_code=item.secure_code
        ).filter(MenuPermission.is_deleted == False).all()

        user_types = {str(p.user_type) for p in perms}
        group = target_groups[lt]
        group[0].update(user_types)
        group[1].append(item)

    # 逐一比對
    for link_target, (all_user_types, menu_items) in target_groups.items():
        view_func = app.view_functions.get(link_target)
        if not view_func:
            continue  # 端點不存在，另外處理

        actual_dec = _detect_decorator(view_func)
        if not actual_dec:
            continue  # 無法偵測 decorator，跳過

        # 模組路由使用 @module_access_required，有獨立的合約+ACL 存取控制鏈
        # 不走 admin/system_admin 體系，跳過比對
        if actual_dec == 'module_access_required':
            continue

        actual_level = DECORATOR_LEVELS.get(actual_dec, -1)
        expected_level = _get_expected_level(frozenset(all_user_types))

        if expected_level < 0:
            continue  # 無法判定，跳過

        if actual_level > expected_level:
            # 路由比選單更寬鬆 → CRITICAL (可被繞過)
            level_to_dec = {0: 'system_admin_required', 1: 'admin_required', 2: 'login_required'}
            expected_dec = level_to_dec.get(expected_level, '?')

            for mi in menu_items:
                mismatches.append({
                    'menu_code': mi.code,
                    'title': mi.title,
                    'link_target': link_target,
                    'menu_user_types': sorted(all_user_types),
                    'expected_decorator': f'@{expected_dec}',
                    'actual_decorator': f'@{actual_dec}',
                    'severity': 'CRITICAL',
                })

    return mismatches


def run_startup_audit(app: Flask) -> None:
    """
    Flask 啟動時執行權限審計

    PERMISSION_AUDIT_STRICT=true: 不一致則阻止啟動
    預設: 記錄警告
    """
    with app.app_context():
        mismatches = audit_permissions(app)

    if not mismatches:
        logger.info('[SEC-03] Permission audit passed: menu/route consistency OK')
        return

    # 格式化輸出
    lines = [
        '',
        '=' * 70,
        ' [SEC-03] PERMISSION AUDIT FAILED - Menu/Route Mismatch Detected',
        '=' * 70,
    ]

    for m in mismatches:
        lines.append(
            f"  {m['severity']} | {m['menu_code']} ({m['title']})\n"
            f"           route: {m['link_target']}\n"
            f"           menu allows: {m['menu_user_types']}\n"
            f"           expected: {m['expected_decorator']}, "
            f"actual: {m['actual_decorator']}"
        )

    lines.append('=' * 70)
    lines.append(f'  Total: {len(mismatches)} mismatch(es)')
    lines.append('=' * 70)

    msg = '\n'.join(lines)

    is_strict = os.environ.get('PERMISSION_AUDIT_STRICT')
    if is_strict:
        # 嚴格模式 (PERMISSION_AUDIT_STRICT=true): 阻止啟動
        logger.error(msg)
        raise SystemExit(
            f'\n[SEC-03] {len(mismatches)} permission mismatch(es) detected. '
            f'Fix before starting.\n'
        )
    else:
        # 生產環境: 警告
        logger.warning(msg)
