"""
用戶編號規則 Web 路由

設定頁面路由，提供編號規則的管理介面。
"""
from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import current_user
from flask_babel import gettext as _

from ..security.decorators import admin_required
from ..security.resource_gateway import ResourceGateway
from ..models import UserNumberingRule, NumberingUsageScope
from ..services.numbering_service import NumberingService
from .. import db

numbering_bp = Blueprint('numbering', __name__)


@numbering_bp.route('/admin/numbering')
@admin_required
def list_rules():
    """編號規則列表頁面"""
    rules = UserNumberingRule.query.filter_by(
        org_secure_code=current_user.org_secure_code,
        is_deleted=False
    ).order_by(
        UserNumberingRule.default_for.desc().nullslast(),
        UserNumberingRule.name
    ).all()

    # 為每個規則產生預覽
    for rule in rules:
        try:
            rule.preview = NumberingService.preview_numbers(rule, count=1)[0]
        except Exception:
            rule.preview = '(無法預覽)'

    return render_template(
        'pages/admin/numbering/list.html',
        rules=rules
    )


@numbering_bp.route('/admin/numbering/create', methods=['GET', 'POST'])
@admin_required
def create_rule():
    """新增編號規則"""
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        usage_scope = request.form.get('usage_scope', NumberingUsageScope.INTERNAL_ONLY)
        default_for = request.form.get('default_for', '').strip() or None

        # 從表單建構 elements
        elements = _build_elements_from_form(request.form)

        # 驗證
        if not name:
            flash(_('規則名稱為必填'), 'error')
            return render_template('pages/admin/numbering/edit.html', rule=None)

        # 驗證 usage_scope
        if usage_scope not in [NumberingUsageScope.INTERNAL_ONLY,
                               NumberingUsageScope.EXTERNAL_ONLY,
                               NumberingUsageScope.INTERNAL_UNIVERSAL]:
            usage_scope = NumberingUsageScope.INTERNAL_ONLY

        valid, error = NumberingService.validate_elements(elements)
        if not valid:
            flash(error, 'error')
            return render_template('pages/admin/numbering/edit.html', rule=None)

        # 檢查名稱重複
        existing = UserNumberingRule.query.filter_by(
            org_secure_code=current_user.org_secure_code,
            name=name,
            is_deleted=False
        ).first()
        if existing:
            flash(_('規則名稱「%(name)s」已存在', name=name), 'error')
            return render_template('pages/admin/numbering/edit.html', rule=None)

        # 如果要設為預設，先取消同類型的其他預設
        if default_for:
            UserNumberingRule.query.filter_by(
                org_secure_code=current_user.org_secure_code,
                default_for=default_for,
                is_deleted=False
            ).update({'default_for': None})

        # 建立規則
        rule = UserNumberingRule(
            org_secure_code=current_user.org_secure_code,
            name=name,
            description=description,
            usage_scope=usage_scope,
            elements=elements,
            default_for=default_for,
            is_active=True
        )
        db.session.add(rule)
        db.session.commit()

        flash(_('編號規則已建立'), 'success')
        return redirect(url_for('numbering.list_rules'))

    return render_template('pages/admin/numbering/edit.html', rule=None)


@numbering_bp.route('/admin/numbering/<secure_code>/edit', methods=['GET', 'POST'])
@admin_required
def edit_rule(secure_code):
    """編輯編號規則"""
    rule = ResourceGateway.get(UserNumberingRule, secure_code)
    if not rule:
        flash(_('找不到此規則'), 'error')
        return redirect(url_for('numbering.list_rules'))

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        usage_scope = request.form.get('usage_scope', NumberingUsageScope.INTERNAL_ONLY)
        default_for = request.form.get('default_for', '').strip() or None
        is_active = request.form.get('is_active') == '1'

        # 從表單建構 elements
        elements = _build_elements_from_form(request.form)

        # 驗證
        if not name:
            flash(_('規則名稱為必填'), 'error')
            return render_template('pages/admin/numbering/edit.html', rule=rule)

        # 驗證 usage_scope
        if usage_scope not in [NumberingUsageScope.INTERNAL_ONLY,
                               NumberingUsageScope.EXTERNAL_ONLY,
                               NumberingUsageScope.INTERNAL_UNIVERSAL]:
            usage_scope = NumberingUsageScope.INTERNAL_ONLY

        valid, error = NumberingService.validate_elements(elements)
        if not valid:
            flash(error, 'error')
            return render_template('pages/admin/numbering/edit.html', rule=rule)

        # 檢查名稱重複
        existing = UserNumberingRule.query.filter(
            UserNumberingRule.org_secure_code == current_user.org_secure_code,
            UserNumberingRule.name == name,
            UserNumberingRule.secure_code != secure_code,
            UserNumberingRule.is_deleted == False
        ).first()
        if existing:
            flash(_('規則名稱「%(name)s」已存在', name=name), 'error')
            return render_template('pages/admin/numbering/edit.html', rule=rule)

        # 如果要設為預設，先取消同類型的其他預設
        if default_for and default_for != rule.default_for:
            UserNumberingRule.query.filter(
                UserNumberingRule.org_secure_code == current_user.org_secure_code,
                UserNumberingRule.default_for == default_for,
                UserNumberingRule.secure_code != secure_code,
                UserNumberingRule.is_deleted == False
            ).update({'default_for': None})

        # 更新
        rule.name = name
        rule.description = description
        rule.usage_scope = usage_scope
        rule.elements = elements
        rule.default_for = default_for
        rule.is_active = is_active
        db.session.commit()

        flash(_('編號規則已更新'), 'success')
        return redirect(url_for('numbering.list_rules'))

    # 產生預覽
    try:
        rule.preview_list = NumberingService.preview_numbers(rule, count=10)
    except Exception:
        rule.preview_list = []

    return render_template('pages/admin/numbering/edit.html', rule=rule)


@numbering_bp.route('/admin/numbering/<secure_code>/delete', methods=['POST'])
@admin_required
def delete_rule(secure_code):
    """刪除編號規則"""
    rule = ResourceGateway.get(UserNumberingRule, secure_code)
    if not rule:
        flash(_('找不到此規則'), 'error')
        return redirect(url_for('numbering.list_rules'))

    if rule.default_for:
        default_labels = {
            'EMPLOYEE': _('企業成員預設'),
            'EXTERNAL': _('外部預設'),
            'FORM': _('表單預設'),
        }
        default_label = default_labels.get(rule.default_for, _('預設'))
        flash(_('無法刪除%(label)s規則，請先在編輯頁面取消預設設定', label=default_label), 'error')
        return redirect(url_for('numbering.list_rules'))

    # 軟刪除
    rule.is_deleted = True
    rule.deleted_at = db.func.now()
    db.session.commit()

    flash(_('規則「%(name)s」已刪除', name=rule.name), 'success')
    return redirect(url_for('numbering.list_rules'))


def _build_elements_from_form(form) -> dict:
    """從表單資料建構 elements 配置"""
    total_length = int(form.get('total_length', 0) or 0)
    components = []

    # 處理各元素
    order = 1

    # 前綴
    if form.get('use_prefix'):
        prefix_values = form.get('prefix_values', '').strip()
        if prefix_values:
            components.append({
                'type': 'prefix',
                'order': int(form.get('prefix_order', order)),
                'values': [v.strip() for v in prefix_values.split(',') if v.strip()]
            })
            order += 1

    # 公元年碼
    if form.get('use_year'):
        components.append({
            'type': 'year',
            'order': int(form.get('year_order', order)),
            'format': form.get('year_format', 'yy')
        })
        order += 1

    # 年換算碼
    if form.get('use_year_offset'):
        components.append({
            'type': 'year_offset',
            'order': int(form.get('year_offset_order', order)),
            'offset': int(form.get('year_offset_value', 0) or 0),
            'format': form.get('year_offset_format', 'fff')
        })
        order += 1

    # 月碼
    if form.get('use_month'):
        components.append({
            'type': 'month',
            'order': int(form.get('month_order', order)),
            'format': form.get('month_format', 'mm')
        })
        order += 1

    # 序號（必要）
    seq_digits = int(form.get('seq_digits', 4) or 4)
    seq_start = int(form.get('seq_start', 1) or 1)
    seq_reset = form.get('seq_reset', 'never')
    components.append({
        'type': 'sequence',
        'order': int(form.get('seq_order', order)),
        'digits': seq_digits,
        'start': seq_start,
        'reset_period': seq_reset
    })
    order += 1

    # 後綴
    if form.get('use_suffix'):
        suffix_values = form.get('suffix_values', '').strip()
        if suffix_values:
            components.append({
                'type': 'suffix',
                'order': int(form.get('suffix_order', order)),
                'values': [v.strip() for v in suffix_values.split(',') if v.strip()]
            })

    return {
        'total_length': total_length,
        'components': components
    }
