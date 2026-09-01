"""平台選單出廠預設值 seeding。"""
import logging
import secrets

from app import db
from app.defaults.menu_defaults import CORE_MENUS, get_allowed_user_types
from app.models import MenuItem, MenuPermission, Organization

logger = logging.getLogger(__name__)


def generate_secure_code(length=22):
    """產生安全的隨機碼"""
    alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-'
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def set_menu_permissions(menu_secure_code, user_types):
    """設定選單的用戶類型權限"""
    for user_type in user_types:
        permission = MenuPermission(
            menu_secure_code=menu_secure_code,
            user_type=user_type
        )
        db.session.add(permission)


def seed_platform_menus(force=False) -> dict:
    """初始化核心平台選單。"""
    from app.constants import SYSTEM_ORG_CODE

    org = Organization.query.filter_by(secure_code=SYSTEM_ORG_CODE).first()
    if not org:
        raise ValueError(
            f"{SYSTEM_ORG_CODE} 企業不存在，請先執行 scripts/bootstrap_db.py --fresh")

    result = {
        'skipped': False,
        'existing': 0,
        'created': 0,
        'mrr_created': 0,
    }

    existing_count = MenuItem.query.filter_by(
        org_secure_code=SYSTEM_ORG_CODE,
        is_deleted=False
    ).count()
    result['existing'] = existing_count

    if existing_count > 0:
        if force:
            logger.info("清除現有的 %s 個選單項目...", existing_count)
            menu_codes = [m.secure_code for m in MenuItem.query.filter(
                MenuItem.org_secure_code == SYSTEM_ORG_CODE
            ).all()]
            if menu_codes:
                MenuPermission.query.filter(
                    MenuPermission.menu_secure_code.in_(menu_codes)
                ).delete(synchronize_session=False)
            MenuItem.query.filter(
                MenuItem.org_secure_code == SYSTEM_ORG_CODE,
                MenuItem.parent_secure_code.isnot(None)
            ).delete(synchronize_session=False)
            MenuItem.query.filter(
                MenuItem.org_secure_code == SYSTEM_ORG_CODE
            ).delete(synchronize_session=False)
            db.session.commit()
            logger.info("選單已清除")
        else:
            logger.info("已存在 %s 個選單項目，跳過", existing_count)
            result['skipped'] = True
            return result

    code_to_secure_code = {}
    created_count = 0

    logger.info("建立根選單...")
    for menu_def in CORE_MENUS:
        if menu_def.get('depth', 0) != 0:
            continue

        secure_code = generate_secure_code()
        menu = MenuItem(
            secure_code=secure_code,
            org_secure_code=SYSTEM_ORG_CODE,
            code=menu_def['code'],
            title=menu_def['title'],
            title_i18n=menu_def.get('title_i18n') or {},
            icon=menu_def.get('icon'),
            link_type=menu_def['link_type'],
            link_target=menu_def.get('link_target'),
            open_in_new_tab=menu_def.get('open_in_new_tab', False),
            display_order=menu_def['display_order'],
            depth=0,
            is_expanded=menu_def.get('is_expanded', False),
            is_active=True,
            required_level=menu_def['required_level'],
            is_shared=menu_def.get('is_shared', False),
            required_permission=menu_def.get('required_permission'),
        )
        db.session.add(menu)
        code_to_secure_code[menu_def['code']] = secure_code

        if '_user_types_override' in menu_def:
            user_types = menu_def['_user_types_override']
        else:
            user_types = get_allowed_user_types(
                menu_def['required_level'],
                menu_def.get('is_shared', False)
            )
        set_menu_permissions(secure_code, user_types)
        created_count += 1

    db.session.flush()

    logger.info("建立子選單...")
    for menu_def in CORE_MENUS:
        if menu_def.get('depth', 0) != 1:
            continue

        parent_code = menu_def.get('parent_code')
        parent_secure_code = code_to_secure_code.get(parent_code)

        if not parent_secure_code:
            logger.warning("找不到父選單 %s，跳過 %s", parent_code, menu_def['code'])
            continue

        secure_code = generate_secure_code()
        menu = MenuItem(
            secure_code=secure_code,
            org_secure_code=SYSTEM_ORG_CODE,
            parent_secure_code=parent_secure_code,
            code=menu_def['code'],
            title=menu_def['title'],
            title_i18n=menu_def.get('title_i18n') or {},
            icon=menu_def.get('icon'),
            link_type=menu_def['link_type'],
            link_target=menu_def.get('link_target'),
            open_in_new_tab=menu_def.get('open_in_new_tab', False),
            display_order=menu_def['display_order'],
            depth=1,
            is_expanded=menu_def.get('is_expanded', False),
            is_active=True,
            required_level=menu_def['required_level'],
            is_shared=menu_def.get('is_shared', False),
            required_permission=menu_def.get('required_permission'),
        )
        db.session.add(menu)
        code_to_secure_code[menu_def['code']] = secure_code

        if '_user_types_override' in menu_def:
            user_types = menu_def['_user_types_override']
        else:
            user_types = get_allowed_user_types(
                menu_def['required_level'],
                menu_def.get('is_shared', False)
            )
        set_menu_permissions(secure_code, user_types)
        created_count += 1

    db.session.commit()
    result['created'] = created_count
    logger.info("成功建立 %s 個選單項目", created_count)

    from app.services.menu_service import MenuService
    items = MenuItem.query.filter_by(is_deleted=False).all()
    code_to_item = {item.code: item for item in items}
    result['mrr_created'] = MenuService.seed_all_orgs_role_requirements(
        code_to_item)
    db.session.commit()
    logger.info("建立 %s 筆選單角色需求", result['mrr_created'])

    return result
