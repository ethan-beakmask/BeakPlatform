"""
BeakMask Menu Management Web Routes
選單管理頁面路由
"""
from datetime import datetime
from flask import Blueprint, render_template, request, flash, redirect, url_for, abort
from flask_login import current_user

from sqlalchemy import func
from ..security.decorators import admin_required
from ..models.menu_item import MenuItem
from ..models.menu_permission import MenuPermission
from ..models.user import UserType
from ..services.menu_service import MenuService
from ..services.code_generator import get_code_generator
from .. import db

menu_web_bp = Blueprint('menu', __name__)

# 用戶類型顯示名稱
USER_TYPE_LABELS = {
    UserType.SYSTEM_ADMIN: '系統管理員',
    UserType.ORG_ADMIN: '企業管理員',
    UserType.EMPLOYEE: '員工',
    UserType.EXTERNAL: '非公司成員',
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
@admin_required
def list_menu():
    """選單管理頁面"""
    root_items, _ = get_menu_tree()
    flat_items = flatten_menu_tree(root_items)

    # 取得所有顯示選單項目的權限矩陣
    # 不能只用 current_user.org_secure_code，因為可能顯示多企業選單
    all_menu_codes = [entry['item'].secure_code for entry in flat_items]
    permission_matrix = _get_full_permission_matrix(all_menu_codes)

    # 識別模組選單 (code 前綴匹配 INSTALLED_MODULES)
    module_menu_codes = _get_module_menu_code_set(flat_items)

    return render_template(
        'pages/menu/list.html',
        menu_items=flat_items,
        permission_matrix=permission_matrix,
        module_menu_codes=module_menu_codes,
        user_types=MenuService.USER_TYPES,
        user_type_labels=USER_TYPE_LABELS
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


@menu_web_bp.route('/create', methods=['GET', 'POST'])
@admin_required
def create_menu():
    """新增選單項目頁面"""
    root_items, _ = get_menu_tree()
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
                flash('無法自動產生代碼，請手動輸入', 'error')

        if not code or not title:
            flash('標題為必填', 'error')
        elif not allowed_user_types:
            flash('請至少選擇一種用戶類型', 'error')
        else:
            # 檢查代碼是否重複 (case-insensitive)
            existing = MenuItem.query.filter(
                func.upper(MenuItem.code) == code.upper(),
                MenuItem.is_deleted == False
            ).first()
            if existing:
                flash(f'選單代碼 {code} 已存在', 'error')
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

                    flash(f'已建立選單項目 {title}', 'success')
                    return redirect(url_for('menu.list_menu'))
                except Exception as e:
                    db.session.rollback()
                    flash(f'建立失敗: {str(e)}', 'error')

    return render_template(
        'pages/menu/create.html',
        parent_options=parent_options,
        user_types=MenuService.USER_TYPES,
        user_type_labels=USER_TYPE_LABELS
    )


@menu_web_bp.route('/<secure_code>/edit', methods=['GET', 'POST'])
@admin_required
def edit_menu(secure_code: str):
    """編輯選單項目頁面"""
    item = MenuItem.query.filter_by(
        secure_code=secure_code,
        is_deleted=False
    ).first()

    if not item:
        abort(404)

    root_items, _ = get_menu_tree()
    parent_options = flatten_menu_tree(root_items)
    # 排除自己及子孫作為可選的父項目
    descendants = item.get_descendants()
    descendant_codes = {d.secure_code for d in descendants}
    descendant_codes.add(item.secure_code)
    parent_options = [p for p in parent_options if p['item'].secure_code not in descendant_codes]

    # 取得當前權限
    current_permissions = MenuService.get_menu_permissions(item.secure_code)
    is_module = _is_module_menu(item.code)

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

        if not title:
            flash('標題為必填', 'error')
        elif not is_module and not allowed_user_types:
            flash('請至少選擇一種用戶類型', 'error')
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

                # 模組選單不透過 MenuPermission 控制，跳過權限寫入
                if not is_module:
                    MenuService.set_menu_permissions(item.secure_code, allowed_user_types)

                db.session.commit()
                flash('已更新選單項目', 'success')
                return redirect(url_for('menu.list_menu'))
            except Exception as e:
                db.session.rollback()
                flash(f'更新失敗: {str(e)}', 'error')

    return render_template(
        'pages/menu/edit.html',
        item=item,
        parent_options=parent_options,
        current_permissions=current_permissions,
        is_module_menu=is_module,
        user_types=MenuService.USER_TYPES,
        user_type_labels=USER_TYPE_LABELS
    )


@menu_web_bp.route('/<secure_code>/delete', methods=['POST'])
@admin_required
def delete_menu(secure_code: str):
    """刪除選單項目"""
    item = MenuItem.query.filter_by(
        secure_code=secure_code,
        is_deleted=False
    ).first()

    if not item:
        abort(404)

    try:
        # 同時刪除所有子項目
        descendants = item.get_descendants()
        for d in descendants:
            d.is_deleted = True
            d.deleted_at = datetime.utcnow()

        item.is_deleted = True
        item.deleted_at = datetime.utcnow()
        db.session.commit()
        flash(f'已刪除選單項目 {item.title}', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'刪除失敗: {str(e)}', 'error')

    return redirect(url_for('menu.list_menu'))
