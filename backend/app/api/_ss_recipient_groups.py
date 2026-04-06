"""
System Settings - 收件人群組子模組

端點：
- GET    /api/system-settings/recipient-groups        列出群組
- POST   /api/system-settings/recipient-groups        新增群組
- GET    /api/system-settings/recipient-groups/<id>   取得群組詳情
- PUT    /api/system-settings/recipient-groups/<id>   更新群組
- DELETE /api/system-settings/recipient-groups/<id>   刪除群組
- GET    /api/system-settings/recipient-groups/<id>/resolve  解析收件人
"""
from datetime import datetime
from flask import jsonify, request

from ..security.decorators import system_admin_required
from ..models import RecipientGroup
from ..constants import SYSTEM_ORG_CODE
from .. import db


def register(bp):
    """將收件人群組路由掛載到 Blueprint"""

    @bp.route('/recipient-groups', methods=['GET'])
    @system_admin_required
    def list_recipient_groups():
        """列出所有系統級收件人群組"""
        groups = RecipientGroup.query.filter_by(
            org_secure_code=SYSTEM_ORG_CODE,
            is_deleted=False
        ).order_by(RecipientGroup.priority).all()

        return jsonify({
            'success': True,
            'data': [g.to_dict() for g in groups]
        })

    @bp.route('/recipient-groups', methods=['POST'])
    @system_admin_required
    def create_recipient_group():
        """
        新增系統級收件人群組

        Body:
            name: 群組名稱 (必填)
            description: 描述
            priority: 優先順序 (預設 100)
            is_active: 是否啟用 (預設 true)
            included_units: [{"id": "xxx", "include_children": bool}, ...]
            included_users: ["user_id", ...]
            excluded_units: ["unit_id", ...]
            excluded_users: ["user_id", ...]
        """
        data = request.get_json()

        if not data:
            return jsonify({'success': False, 'message': '請提供資料'}), 400

        if not data.get('name'):
            return jsonify({'success': False, 'message': '請填寫群組名稱'}), 400

        # 建立群組
        group = RecipientGroup(
            org_secure_code=SYSTEM_ORG_CODE,
            name=data['name'],
            description=data.get('description'),
            priority=data.get('priority', 100),
            is_active=data.get('is_active', True)
        )

        # 設定收件人
        group.included_units = data.get('included_units', [])
        group.included_users = data.get('included_users', [])
        group.excluded_units = data.get('excluded_units', [])
        group.excluded_users = data.get('excluded_users', [])

        db.session.add(group)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': '收件人群組已建立',
            'data': group.to_dict()
        }), 201

    @bp.route('/recipient-groups/<secure_code>', methods=['GET'])
    @system_admin_required
    def get_recipient_group(secure_code):
        """取得收件人群組詳情"""
        group = RecipientGroup.query.filter_by(
            secure_code=secure_code,
            org_secure_code=SYSTEM_ORG_CODE,
            is_deleted=False
        ).first()

        if not group:
            return jsonify({'success': False, 'message': '群組不存在'}), 404

        return jsonify({
            'success': True,
            'data': group.to_dict()
        })

    @bp.route('/recipient-groups/<secure_code>', methods=['PUT'])
    @system_admin_required
    def update_recipient_group(secure_code):
        """更新收件人群組"""
        group = RecipientGroup.query.filter_by(
            secure_code=secure_code,
            org_secure_code=SYSTEM_ORG_CODE,
            is_deleted=False
        ).first()

        if not group:
            return jsonify({'success': False, 'message': '群組不存在'}), 404

        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': '請提供資料'}), 400

        # 更新基本欄位
        if 'name' in data:
            group.name = data['name']
        if 'description' in data:
            group.description = data['description']
        if 'priority' in data:
            group.priority = data['priority']
        if 'is_active' in data:
            group.is_active = data['is_active']

        # 更新收件人設定
        if 'included_units' in data:
            group.included_units = data['included_units']
        if 'included_users' in data:
            group.included_users = data['included_users']
        if 'excluded_units' in data:
            group.excluded_units = data['excluded_units']
        if 'excluded_users' in data:
            group.excluded_users = data['excluded_users']

        db.session.commit()

        return jsonify({
            'success': True,
            'message': '收件人群組已更新',
            'data': group.to_dict()
        })

    @bp.route('/recipient-groups/<secure_code>', methods=['DELETE'])
    @system_admin_required
    def delete_recipient_group(secure_code):
        """刪除收件人群組（軟刪除）"""
        group = RecipientGroup.query.filter_by(
            secure_code=secure_code,
            org_secure_code=SYSTEM_ORG_CODE,
            is_deleted=False
        ).first()

        if not group:
            return jsonify({'success': False, 'message': '群組不存在'}), 404

        group.is_deleted = True
        group.deleted_at = datetime.utcnow()
        db.session.commit()

        return jsonify({
            'success': True,
            'message': '收件人群組已刪除'
        })

    @bp.route('/recipient-groups/<secure_code>/resolve', methods=['GET'])
    @system_admin_required
    def resolve_recipient_group(secure_code):
        """
        解析收件人群組，取得最終收件人列表

        注意：系統級群組的 resolve 會嘗試解析所有企業的用戶
        """
        group = RecipientGroup.query.filter_by(
            secure_code=secure_code,
            org_secure_code=SYSTEM_ORG_CODE,
            is_deleted=False
        ).first()

        if not group:
            return jsonify({'success': False, 'message': '群組不存在'}), 404

        # 系統級群組目前不支援自動解析（跨企業邏輯複雜）
        # 返回設定內容讓前端顯示
        return jsonify({
            'success': True,
            'data': {
                'group_id': group.secure_code,
                'group_name': group.name,
                'included_units': group.included_units,
                'included_users': group.included_users,
                'excluded_units': group.excluded_units,
                'excluded_users': group.excluded_users,
                'message': '系統級群組需手動指定收件人'
            }
        })
