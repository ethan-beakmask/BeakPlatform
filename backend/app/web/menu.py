"""
BeakMask Menu Management Web Routes
選單管理頁面路由
"""
import json
from datetime import datetime
from flask import Blueprint, render_template, request, flash, redirect, url_for, abort
from flask_babel import gettext as _
from flask_login import current_user
from markupsafe import Markup

from sqlalchemy import func
from ..security.decorators import system_admin_required
from ..models.menu_item import MenuItem
from ..models.menu_permission import MenuPermission
from ..models.user import UserType
from ..services.menu_service import MenuService
from ..services.code_generator import get_code_generator
from ..constants import SYSTEM_ORG_CODE
from .. import db

menu_web_bp = Blueprint('menu', __name__)

# 用戶類型顯示名稱
USER_TYPE_LABELS = {
    UserType.SYSTEM_ADMIN: '系統管理員',
    UserType.ORG_ADMIN: '企業管理員',
    UserType.EMPLOYEE: '企業成員',
    UserType.EXTERNAL: '外部廠商',
}


def get_menu_tree():
    """取得選單樹狀結構，用於模板渲染"""
    items = MenuItem.query.filter(
        MenuItem.is_deleted == False
    ).order_by(MenuItem.display_order).all()

    # 建立樹狀結構
    root_items = []
    item_map = {item.secure_code: item for item in items}

    for item in items:
        if not item.parent_secure_code:
            root_items.append(item)

    return root_items, item_map


def flatten_menu_tree(items, depth=0):
    """將選單樹扁平化成列表，帶有縮排資訊"""
    result = []
    for item in items:
        result.append({
            'item': item,
            'depth': depth,
            'indent': '--' * depth + (' ' if depth > 0 else '')
        })
        children = [c for c in item.children if not c.is_deleted]
        children.sort(key=lambda x: x.display_order)
        result.extend(flatten_menu_tree(children, depth + 1))
    return result


@menu_web_bp.route('/')
@system_admin_required
def list_menu():
    """選單管理頁面"""
    root_items, _unused = get_menu_tree()
    flat_items = flatten_menu_tree(root_items)

    # 取得所有顯示選單項目的權限矩陣
    # 不能只用 current_user.org_secure_code，因為可能顯示多企業選單
    all_menu_codes = [entry['item'].secure_code for entry in flat_items]
    permission_matrix = _get_full_permission_matrix(all_menu_codes)

    # 識別模組選單 (code 前綴匹配 INSTALLED_MODULES)
    module_menu_codes = _get_module_menu_code_set(flat_items)

    # 建構 BeakTrellis 用的樹狀資料
    trellis_data = _build_trellis_data(root_items, permission_matrix, module_menu_codes)

    return render_template(
        'pages/menu/list.html',
        menu_items=flat_items,
        permission_matrix=permission_matrix,
        module_menu_codes=module_menu_codes,
        user_types=MenuService.USER_TYPES,
        user_type_labels=USER_TYPE_LABELS,
        trellis_data_json=Markup(json.dumps(trellis_data, ensure_ascii=False))
    )


def _get_module_menu_code_set(flat_items):
    """取得模組選單的 code 集合，用於模板判斷"""
    from ..services.lookup_service import LookupService
    try:
        installed_items = LookupService.get_items('INSTALLED_MODULES')
        installed_module_codes = {item['code'] for item in installed_items}
    except Exception:
        return set()

    if not installed_module_codes:
        return set()

    result = set()
    for entry in flat_items:
        code = entry['item'].code
        if MenuService._get_module_code_for_menu(code, installed_module_codes) is not None:
            result.add(code)
    return result


def _is_module_menu(menu_code: str) -> bool:
    """判斷指定 menu code 是否為模組選單"""
    from ..services.lookup_service import LookupService
    try:
        installed_items = LookupService.get_items('INSTALLED_MODULES')
        installed_module_codes = {item['code'] for item in installed_items}
    except Exception:
        return False
    return MenuService._get_module_code_for_menu(menu_code, installed_module_codes) is not None


def _get_full_permission_matrix(menu_secure_codes):
    """
    取得指定選單項目的權限矩陣

    Args:
        menu_secure_codes: 選單 secure_code 列表

    Returns:
        {menu_secure_code: {user_type: True/False, ...}, ...}
    """
    if not menu_secure_codes:
        return {}

    # 取得所有相關的權限記錄
    permissions = MenuPermission.query.filter(
        MenuPermission.menu_secure_code.in_(menu_secure_codes),
        MenuPermission.is_deleted == False
    ).all()

    # 建立權限集合
    perm_set = {(p.menu_secure_code, p.user_type) for p in permissions}

    # 建立交叉矩陣
    matrix = {}
    for code in menu_secure_codes:
        matrix[code] = {
            user_type: (code, user_type) in perm_set
            for user_type in MenuService.USER_TYPES
        }

    return matrix


def _compute_row_class(perms, title, is_module):
    """計算選單列的 CSS class（依權限等級著色）

    優先級：模組 > 跨階層基本選單(3+types) > 階層專屬
    """
    has_sys = perms.get('SYSTEM_ADMIN', False)
    has_org = perms.get('ORG_ADMIN', False)
    has_emp = perms.get('EMPLOYEE', False)
    has_ext = perms.get('EXTERNAL', False)

    if is_module:
        return 'menu-module'

    # 計算擁有幾種 user_type
    type_count = sum([has_sys, has_org, has_emp, has_ext])

    # 3+ types = 跨階層基本選單（所有人/幾乎所有人都能看的）
    if type_count >= 3:
        return 'menu-common'

    # 1-2 types = 階層專屬
    if has_sys:
        return 'menu-sys-cross' if (has_org or has_emp or has_ext) else 'menu-sys-only'
    if has_org:
        return 'menu-org-cross' if (has_emp or has_ext) else 'menu-org-only'
    if has_emp:
        return 'menu-user-cross' if has_ext else 'menu-user-only'
    if has_ext:
        return 'menu-ext-only'
    return ''


def _build_trellis_data(root_items, permission_matrix, module_menu_codes):
    """建構 BeakTrellis 用的巢狀樹狀資料"""
    def build_node(item):
        perms = permission_matrix.get(item.secure_code, {})
        is_module = item.code in module_menu_codes
        row_class = _compute_row_class(perms, item.title, is_module)

        # 將 UserType enum key 轉為字串 key 供前端讀取
        perms_str = {}
        for ut, val in perms.items():
            key = ut if isinstance(ut, str) else ut.name if hasattr(ut, 'name') else str(ut)
            perms_str[key] = val

        children = [c for c in item.children if not c.is_deleted]
        children.sort(key=lambda x: x.display_order)

        return {
            'id': item.secure_code,
            'label': item.title,
            'expanded': True,
            'data': {
                'code': item.code,
                'icon': item.icon or '',
                'link_type': item.link_type or '',
                'link_target': item.link_target or '',
                'display_order': item.display_order,
                'is_active': item.is_active,
                'is_user_created': item.is_user_created,
                'row_class': row_class,
                'perms': perms_str,
            },
            'children': [build_node(c) for c in children]
        }

    return [build_node(item) for item in root_items]


@menu_web_bp.route('/create', methods=['GET', 'POST'])
@system_admin_required
def create_menu():
    """新增選單項目頁面"""
    root_items, _unused = get_menu_tree()
    parent_options = flatten_menu_tree(root_items)

    if request.method == 'POST':
        code = request.form.get('code', '').strip()
        title = request.form.get('title', '').strip()
        title_en = request.form.get('title_en', '').strip() or None
        title_zh_cn = request.form.get('title_zh_cn', '').strip() or None
        icon = request.form.get('icon', '').strip() or None
        parent_secure_code = request.form.get('parent_secure_code', '').strip() or None
        link_type = request.form.get('link_type', 'route').strip()
        link_target = request.form.get('link_target', '').strip() or None
        display_order = int(request.form.get('display_order', 0))
        is_expanded = request.form.get('is_expanded') == 'on'
        allowed_user_types = request.form.getlist('allowed_user_types')

        # 組裝 title_i18n JSONB
        title_i18n = {}
        for lang_code in ('en', 'zh-CN', 'ja'):
            val = request.form.get(f'title_{lang_code}', '').strip()
            if val:
                title_i18n[lang_code] = val
        # 向下相容：也從舊欄位名讀取
        if title_en and 'en' not in title_i18n:
            title_i18n['en'] = title_en
        if title_zh_cn and 'zh-CN' not in title_i18n:
            title_i18n['zh-CN'] = title_zh_cn

        # code 空白時自動產生
        if not code and title:
            generator = get_code_generator()
            def _exists(c):
                return MenuItem.query.filter(
                    func.upper(MenuItem.code) == c.upper(),
                    MenuItem.is_deleted == False
                ).first() is not None
            try:
                code = generator.generate(title, exists_checker=_exists)
            except ValueError:
                flash(_('無法自動產生代碼，請手動輸入'), 'error')

        if not code or not title:
            flash(_('標題為必填'), 'error')
        elif not allowed_user_types:
            flash(_('請至少選擇一種用戶類型'), 'error')
        else:
            # 檢查代碼是否重複 (case-insensitive)
            existing = MenuItem.query.filter(
                func.upper(MenuItem.code) == code.upper(),
                MenuItem.is_deleted == False
            ).first()
            if existing:
                flash(_('選單代碼 %(code)s 已存在', code=code), 'error')
            else:
                try:
                    # 計算深度
                    depth = 0
                    if parent_secure_code:
                        parent = MenuItem.query.filter_by(
                            secure_code=parent_secure_code,
                            is_deleted=False
                        ).first()
                        if parent:
                            depth = parent.depth + 1

                    item = MenuItem(
                        org_secure_code=current_user.org_secure_code,
                        code=code,
                        title=title,
                        title_i18n=title_i18n,
                        title_en=title_en,
                        title_zh_cn=title_zh_cn,
                        icon=icon,
                        parent_secure_code=parent_secure_code,
                        link_type=link_type,
                        link_target=link_target,
                        display_order=display_order,
                        is_expanded=is_expanded,
                        depth=depth,
                        is_active=True
                    )
                    db.session.add(item)
                    db.session.flush()  # 取得 secure_code

                    # 設定權限
                    MenuService.set_menu_permissions(item.secure_code, allowed_user_types)

                    db.session.commit()

                    flash(_('已建立選單項目 %(title)s', title=title), 'success')
                    return redirect(url_for('menu.list_menu'))
                except Exception as e:
                    db.session.rollback()
                    flash(_('建立失敗: %(error)s', error=str(e)), 'error')

    return render_template(
        'pages/menu/create.html',
        parent_options=parent_options,
        user_types=MenuService.USER_TYPES,
        user_type_labels=USER_TYPE_LABELS
    )


@menu_web_bp.route('/create-root-header', methods=['POST'])
@system_admin_required
def create_root_header():
    """快速建立根層級 header 項目（系統管理員分類用）"""
    title = request.form.get('title', '').strip()
    if not title:
        flash(_('標題為必填'), 'error')
        return redirect(url_for('menu.list_menu'))

    # 自動產生 code
    generator = get_code_generator()

    def _exists(c):
        return MenuItem.query.filter(
            func.upper(MenuItem.code) == c.upper(),
            MenuItem.is_deleted == False
        ).first() is not None

    try:
        code = generator.generate(title, exists_checker=_exists)
    except ValueError:
        flash(_('無法自動產生代碼，請手動輸入'), 'error')
        return redirect(url_for('menu.list_menu'))

    # display_order: 排到最前面（現有最小值 - 1）
    min_order = db.session.query(func.min(MenuItem.display_order)).filter(
        MenuItem.parent_secure_code.is_(None),
        MenuItem.is_deleted == False
    ).scalar()
    display_order = (min_order - 1) if min_order is not None else 0

    try:
        item = MenuItem(
            org_secure_code=SYSTEM_ORG_CODE,
            code=code,
            title=title,
            title_i18n={},
            icon=None,
            parent_secure_code=None,
            link_type='header',
            link_target=None,
            display_order=display_order,
            is_expanded=False,
            depth=0,
            is_active=True,
            is_user_created=True
        )
        db.session.add(item)
        db.session.flush()

        # 權限只開 SYSTEM_ADMIN
        MenuService.set_menu_permissions(item.secure_code, ['SYSTEM_ADMIN'])

        db.session.commit()
        flash(_('已建立根項目「%(title)s」', title=title), 'success')
    except Exception as e:
        db.session.rollback()
        flash(_('建立失敗: %(error)s', error=str(e)), 'error')

    return redirect(url_for('menu.list_menu'))


@menu_web_bp.route('/<secure_code>/edit', methods=['GET', 'POST'])
@system_admin_required
def edit_menu(secure_code: str):
    """編輯選單項目頁面"""
    item = MenuItem.query.filter_by(
        secure_code=secure_code,
        is_deleted=False
    ).first()

    if not item:
        abort(404)

    root_items, _unused = get_menu_tree()
    parent_options = flatten_menu_tree(root_items)
    # 排除自己及子孫作為可選的父項目
    descendants = item.get_descendants()
    descendant_codes = {d.secure_code for d in descendants}
    descendant_codes.add(item.secure_code)
    parent_options = [p for p in parent_options if p['item'].secure_code not in descendant_codes]

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        title_en = request.form.get('title_en', '').strip() or None
        title_zh_cn = request.form.get('title_zh_cn', '').strip() or None
        icon = request.form.get('icon', '').strip() or None
        new_parent_code = request.form.get('parent_secure_code', '').strip() or None
        link_type = request.form.get('link_type', 'route').strip()
        link_target = request.form.get('link_target', '').strip() or None
        display_order = int(request.form.get('display_order', 0))
        is_expanded = request.form.get('is_expanded') == 'on'
        is_active = request.form.get('is_active') == 'on'

        # 組裝 title_i18n JSONB
        title_i18n = {}
        for lang_code in ('en', 'zh-CN', 'ja'):
            val = request.form.get(f'title_{lang_code}', '').strip()
            if val:
                title_i18n[lang_code] = val
        # 向下相容：也從舊欄位名讀取
        if title_en and 'en' not in title_i18n:
            title_i18n['en'] = title_en
        if title_zh_cn and 'zh-CN' not in title_i18n:
            title_i18n['zh-CN'] = title_zh_cn

        if not title:
            flash(_('標題為必填'), 'error')
        else:
            try:
                item.title = title
                item.title_i18n = title_i18n
                item.title_en = title_en
                item.title_zh_cn = title_zh_cn
                item.icon = icon
                item.link_type = link_type
                item.link_target = link_target
                item.display_order = display_order
                item.is_expanded = is_expanded
                item.is_active = is_active

                # 處理父選單變更
                if new_parent_code != item.parent_secure_code:
                    item.parent_secure_code = new_parent_code

                    # 重新計算深度
                    if new_parent_code:
                        new_parent = MenuItem.query.filter_by(
                            secure_code=new_parent_code,
                            is_deleted=False
                        ).first()
                        item.depth = (new_parent.depth + 1) if new_parent else 0
                    else:
                        item.depth = 0

                    # 遞迴更新所有子孫的深度
                    def update_children_depth(parent_item):
                        for child in parent_item.children:
                            if not child.is_deleted:
                                child.depth = parent_item.depth + 1
                                update_children_depth(child)

                    update_children_depth(item)

                db.session.commit()
                flash(_('已更新選單項目'), 'success')
                return redirect(url_for('menu.list_menu'))
            except Exception as e:
                db.session.rollback()
                flash(_('更新失敗: %(error)s', error=str(e)), 'error')

    # 計算子孫中的預設項目（用於刪除區塊提示）
    protected_children = []
    if item.is_user_created:
        descendants = item.get_descendants()
        protected_children = [d.title for d in descendants if not d.is_user_created]

    return render_template(
        'pages/menu/edit.html',
        item=item,
        parent_options=parent_options,
        protected_children=protected_children
    )


@menu_web_bp.route('/<secure_code>/delete', methods=['POST'])
@system_admin_required
def delete_menu(secure_code: str):
    """刪除選單項目"""
    item = MenuItem.query.filter_by(
        secure_code=secure_code,
        is_deleted=False
    ).first()

    if not item:
        abort(404)

    if not item.is_user_created:
        flash(_('預設選單項目禁止刪除'), 'error')
        return redirect(url_for('menu.list_menu'))

    # 檢查子孫是否包含預設項目
    descendants = item.get_descendants()
    protected = [d for d in descendants if not d.is_user_created]
    if protected:
        names = '、'.join(d.title for d in protected[:5])
        if len(protected) > 5:
            names += _(' 等共 %(count)s 項', count=len(protected))
        flash(_('無法刪除：子項目中包含預設選單（%(names)s），請先將其移出', names=names), 'error')
        return redirect(url_for('menu.list_menu'))

    try:
        # 同時刪除所有子項目
        for d in descendants:
            d.is_deleted = True
            d.deleted_at = datetime.utcnow()

        item.is_deleted = True
        item.deleted_at = datetime.utcnow()
        db.session.commit()
        flash(_('已刪除選單項目 %(title)s', title=item.title), 'success')
    except Exception as e:
        db.session.rollback()
        flash(_('刪除失敗: %(error)s', error=str(e)), 'error')

    return redirect(url_for('menu.list_menu'))
