"""
用戶編號規則 API

提供編號規則的 CRUD 操作和編號產生功能。
"""
from flask import Blueprint, request, jsonify
from flask_login import current_user

from ..security.decorators import admin_required, login_required
from ..security.resource_gateway import ResourceGateway
from ..models import UserNumberingRule, UsedUserNumber
from ..models.user_numbering_rule import NumberingDefaultFor, NumberingUsageScope
from ..services.numbering_service import NumberingService
from .. import db

api_numbering_bp = Blueprint('api_numbering', __name__)


# ============================================================
# 管理員端點 - 規則 CRUD
# ============================================================

@api_numbering_bp.route('/admin/numbering-rules', methods=['GET'])
@admin_required
def list_rules():
    """列出所有編號規則"""
    rules = UserNumberingRule.query.filter_by(
        org_secure_code=current_user.org_secure_code,
        is_deleted=False
    ).order_by(
        UserNumberingRule.default_for.desc().nullslast(),
        UserNumberingRule.name
    ).all()

    # 為每個規則產生預覽
    result = []
    for rule in rules:
        data = rule.to_dict()
        try:
            data['preview'] = NumberingService.preview_numbers(rule, count=1)[0]
        except Exception:
            data['preview'] = '(無法預覽)'
        result.append(data)

    return jsonify({
        'success': True,
        'data': result
    })


@api_numbering_bp.route('/admin/numbering-rules', methods=['POST'])
@admin_required
def create_rule():
    """新增編號規則"""
    data = request.get_json()

    if not data:
        return jsonify({'success': False, 'error': '無效的請求資料'}), 400

    name = data.get('name', '').strip()
    description = data.get('description', '').strip()
    elements = data.get('elements', {})
    default_for = data.get('default_for', '').strip() or None
    usage_scope = data.get('usage_scope', NumberingUsageScope.INTERNAL_ONLY)

    # 向後相容：舊版前端可能只傳 is_default
    if not default_for and data.get('is_default'):
        default_for = NumberingDefaultFor.EMPLOYEE

    # 驗證
    if not name:
        return jsonify({'success': False, 'error': '規則名稱為必填'}), 400

    # 驗證元素配置
    valid, error = NumberingService.validate_elements(elements)
    if not valid:
        return jsonify({'success': False, 'error': error}), 400

    # 檢查名稱重複
    existing = UserNumberingRule.query.filter_by(
        org_secure_code=current_user.org_secure_code,
        name=name,
        is_deleted=False
    ).first()
    if existing:
        return jsonify({'success': False, 'error': f'規則名稱「{name}」已存在'}), 400

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
        elements=elements,
        usage_scope=usage_scope,
        default_for=default_for,
        is_active=True
    )
    db.session.add(rule)
    db.session.commit()

    result = rule.to_dict()
    try:
        result['preview'] = NumberingService.preview_numbers(rule, count=1)[0]
    except Exception:
        result['preview'] = '(無法預覽)'

    return jsonify({
        'success': True,
        'data': result,
        'message': '編號規則已建立'
    }), 201


@api_numbering_bp.route('/admin/numbering-rules/<secure_code>', methods=['GET'])
@admin_required
def get_rule(secure_code):
    """取得編號規則詳情"""
    rule = ResourceGateway.get(UserNumberingRule, secure_code)
    if not rule:
        return jsonify({'success': False, 'error': '找不到此規則'}), 404

    result = rule.to_dict()
    try:
        result['preview'] = NumberingService.preview_numbers(rule, count=10)
    except Exception:
        result['preview'] = []

    return jsonify({
        'success': True,
        'data': result
    })


@api_numbering_bp.route('/admin/numbering-rules/<secure_code>', methods=['PUT'])
@admin_required
def update_rule(secure_code):
    """更新編號規則"""
    rule = ResourceGateway.get(UserNumberingRule, secure_code)
    if not rule:
        return jsonify({'success': False, 'error': '找不到此規則'}), 404

    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': '無效的請求資料'}), 400

    # 更新欄位
    if 'name' in data:
        name = data['name'].strip()
        if not name:
            return jsonify({'success': False, 'error': '規則名稱為必填'}), 400

        # 檢查名稱重複
        existing = UserNumberingRule.query.filter(
            UserNumberingRule.org_secure_code == current_user.org_secure_code,
            UserNumberingRule.name == name,
            UserNumberingRule.secure_code != secure_code,
            UserNumberingRule.is_deleted == False
        ).first()
        if existing:
            return jsonify({'success': False, 'error': f'規則名稱「{name}」已存在'}), 400

        rule.name = name

    if 'description' in data:
        rule.description = data['description'].strip()

    if 'elements' in data:
        elements = data['elements']
        valid, error = NumberingService.validate_elements(elements)
        if not valid:
            return jsonify({'success': False, 'error': error}), 400
        rule.elements = elements

    if 'is_active' in data:
        rule.is_active = bool(data['is_active'])

    db.session.commit()

    result = rule.to_dict()
    try:
        result['preview'] = NumberingService.preview_numbers(rule, count=1)[0]
    except Exception:
        result['preview'] = '(無法預覽)'

    return jsonify({
        'success': True,
        'data': result,
        'message': '編號規則已更新'
    })


@api_numbering_bp.route('/admin/numbering-rules/<secure_code>', methods=['DELETE'])
@admin_required
def delete_rule(secure_code):
    """刪除編號規則"""
    rule = ResourceGateway.get(UserNumberingRule, secure_code)
    if not rule:
        return jsonify({'success': False, 'error': '找不到此規則'}), 404

    if rule.default_for:
        return jsonify({'success': False, 'error': '無法刪除預設規則，請先取消預設設定'}), 400

    # 軟刪除
    rule.is_deleted = True
    rule.deleted_at = db.func.now()
    db.session.commit()

    return jsonify({
        'success': True,
        'message': '編號規則已刪除'
    })


@api_numbering_bp.route('/admin/numbering-rules/<secure_code>/set-default', methods=['PUT'])
@admin_required
def set_default_rule(secure_code):
    """設定為預設規則"""
    rule = ResourceGateway.get(UserNumberingRule, secure_code)
    if not rule:
        return jsonify({'success': False, 'error': '找不到此規則'}), 404

    if not rule.is_active:
        return jsonify({'success': False, 'error': '無法將停用的規則設為預設'}), 400

    # 從請求取得預設用途，預設為 EMPLOYEE
    data = request.get_json(silent=True) or {}
    default_for = data.get('default_for', NumberingDefaultFor.EMPLOYEE)

    # 取消同類型的其他預設
    UserNumberingRule.query.filter_by(
        org_secure_code=current_user.org_secure_code,
        default_for=default_for,
        is_deleted=False
    ).update({'default_for': None})

    # 設定新預設
    rule.default_for = default_for
    db.session.commit()

    return jsonify({
        'success': True,
        'message': f'已將「{rule.name}」設為預設規則'
    })


@api_numbering_bp.route('/admin/numbering-rules/preview', methods=['POST'])
@admin_required
def preview_from_config():
    """從配置預覽編號（用於設計器即時預覽）"""
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': '無效的請求資料'}), 400

    elements = data.get('elements', {})
    count = min(data.get('count', 10), 20)  # 最多 20 個

    # 驗證配置
    valid, error = NumberingService.validate_elements(elements)
    if not valid:
        return jsonify({'success': False, 'error': error}), 400

    try:
        preview = NumberingService.preview_from_config(elements, count)
        return jsonify({
            'success': True,
            'data': preview
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'預覽失敗: {str(e)}'
        }), 500


# ============================================================
# 一般用戶端點 - 取得編號
# ============================================================

@api_numbering_bp.route('/numbering/rules', methods=['GET'])
@login_required
def get_available_rules():
    """
    取得可用的編號規則（用於新增用戶頁面）

    可選參數：
    - scope: 使用範圍過濾 (INTERNAL_ONLY, EXTERNAL_ONLY, INTERNAL_UNIVERSAL)
    """
    scope = request.args.get('scope')
    rules = NumberingService.get_active_rules(current_user.org_secure_code)

    # 如果有指定 scope，過濾規則（支援逗號分隔多值）
    if scope:
        scopes = [s.strip() for s in scope.split(',')]
        rules = [r for r in rules if r.usage_scope in scopes]

    result = []
    for rule in rules:
        data = {
            'secure_code': rule.secure_code,
            'name': rule.name,
            'default_for': rule.default_for,
            'is_default': rule.is_default  # 向後兼容
        }
        try:
            data['preview'] = NumberingService.get_next_number(rule, consume=False)
        except Exception:
            data['preview'] = '(無法取得)'
        result.append(data)

    return jsonify({
        'success': True,
        'data': result
    })


@api_numbering_bp.route('/numbering/next', methods=['GET'])
@login_required
def get_next_number():
    """取得下一個編號（預覽，不消耗）"""
    rule_code = request.args.get('rule')

    if rule_code:
        rule = ResourceGateway.get(UserNumberingRule, rule_code)
        if not rule or not rule.is_active:
            return jsonify({'success': False, 'error': '找不到此規則或規則已停用'}), 404
    else:
        rule = NumberingService.get_default_rule(current_user.org_secure_code)
        if not rule:
            return jsonify({'success': False, 'error': '尚未設定預設編號規則'}), 404

    try:
        number = NumberingService.get_next_number(rule, consume=False)
        return jsonify({
            'success': True,
            'data': {
                'number': number,
                'rule_name': rule.name,
                'rule_secure_code': rule.secure_code
            }
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'無法產生編號: {str(e)}'
        }), 500


@api_numbering_bp.route('/numbering/consume', methods=['POST'])
@login_required
def consume_number():
    """消耗編號（實際使用時呼叫）"""
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': '無效的請求資料'}), 400

    rule_code = data.get('rule')
    manual_number = data.get('number')  # 手動輸入的編號

    if manual_number:
        # 手動輸入的編號，只記錄不走規則
        manual_number = manual_number.strip()

        # 檢查是否已使用
        if UsedUserNumber.is_number_used(current_user.org_secure_code, manual_number):
            return jsonify({
                'success': False,
                'error': f'編號「{manual_number}」已被使用'
            }), 400

        # 記錄
        UsedUserNumber.record_number(
            org_secure_code=current_user.org_secure_code,
            number=manual_number
        )
        db.session.commit()

        return jsonify({
            'success': True,
            'data': {'number': manual_number}
        })

    # 使用規則產生
    if rule_code:
        rule = ResourceGateway.get(UserNumberingRule, rule_code)
        if not rule or not rule.is_active:
            return jsonify({'success': False, 'error': '找不到此規則或規則已停用'}), 404
    else:
        rule = NumberingService.get_default_rule(current_user.org_secure_code)
        if not rule:
            return jsonify({'success': False, 'error': '尚未設定預設編號規則'}), 404

    try:
        number = NumberingService.get_next_number(rule, consume=True)
        return jsonify({
            'success': True,
            'data': {
                'number': number,
                'rule_name': rule.name
            }
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': f'無法產生編號: {str(e)}'
        }), 500


@api_numbering_bp.route('/numbering/check', methods=['GET'])
@login_required
def check_number_available():
    """檢查編號是否可用"""
    number = request.args.get('number', '').strip()
    if not number:
        return jsonify({'success': False, 'error': '請提供編號'}), 400

    available = NumberingService.is_number_available(
        current_user.org_secure_code,
        number
    )

    return jsonify({
        'success': True,
        'data': {
            'number': number,
            'available': available
        }
    })
