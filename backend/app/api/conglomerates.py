"""
BeakMask Conglomerate API
集團管理 API

僅限系統管理員存取
"""
from flask import Blueprint, jsonify, request
from flask_babel import gettext as _
from flask_login import current_user

from ..security.decorators import system_admin_required
from ..services.conglomerate_service import ConglomerateService
from ..models.organization import Organization
from .. import db

conglomerate_bp = Blueprint('api_conglomerates', __name__)


@conglomerate_bp.route('', methods=['GET'])
@system_admin_required
def list_conglomerates():
    """
    取得所有集團

    Query params:
        include_inactive: 是否包含停用的集團 (default: false)

    Returns:
        {conglomerates: [...]}
    """
    include_inactive = request.args.get('include_inactive', 'false') == 'true'
    conglomerates = ConglomerateService.list_conglomerates(include_inactive)

    return jsonify({
        'conglomerates': [c.to_dict() for c in conglomerates]
    })


@conglomerate_bp.route('', methods=['POST'])
@system_admin_required
def create_conglomerate():
    """
    建立集團

    Body:
        name: str (required)
        org_secure_codes: [str] (required, 至少 2 個)
        description: str

    Returns:
        {conglomerate: {...}, organizations: [...]}
    """
    data = request.get_json()

    name = data.get('name', '').strip()
    org_secure_codes = data.get('org_secure_codes', [])
    description = data.get('description', '').strip() or None

    if not name:
        return jsonify({'error': _('集團名稱為必填')}), 400

    if len(org_secure_codes) < 2:
        return jsonify({'error': _('至少需要選擇兩家企業')}), 400

    try:
        conglomerate, orgs = ConglomerateService.create_conglomerate(
            name=name,
            org_secure_codes=org_secure_codes,
            operator_email=current_user.email,
            description=description
        )
        db.session.commit()

        return jsonify({
            'conglomerate': conglomerate.to_dict(),
            'organizations': [o.to_dict() for o in orgs]
        }), 201

    except ValueError as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': _('建立失敗: %(error)s', error=str(e))}), 500


@conglomerate_bp.route('/<secure_code>', methods=['GET'])
@system_admin_required
def get_conglomerate(secure_code: str):
    """
    取得單一集團

    Returns:
        {conglomerate: {...}, organizations: [...]}
    """
    conglomerate = ConglomerateService.get_conglomerate(secure_code)
    if not conglomerate:
        return jsonify({'error': _('集團不存在')}), 404

    orgs = Organization.query.filter_by(
        conglomerate_secure_code=secure_code,
        is_deleted=False
    ).order_by(Organization.name).all()

    cg_dict = conglomerate.to_dict()

    # 補上共享 DB 名稱（來自 FwConglomerateDatabase）
    if conglomerate.has_shared_db:
        from modules.form_workflow.services.sql_sync.cg_db_manager import (
            get_conglomerate_database,
        )
        cg_db = get_conglomerate_database(secure_code)
        if cg_db:
            cg_dict['shared_db_name'] = cg_db.db_name

    return jsonify({
        'conglomerate': cg_dict,
        'organizations': [o.to_dict() for o in orgs]
    })


@conglomerate_bp.route('/<secure_code>', methods=['PUT'])
@system_admin_required
def update_conglomerate(secure_code: str):
    """
    更新集團

    Body:
        name: str
        description: str
        is_active: bool

    Returns:
        {conglomerate: {...}}
    """
    data = request.get_json()

    conglomerate = ConglomerateService.update_conglomerate(
        secure_code=secure_code,
        name=data.get('name'),
        description=data.get('description'),
        is_active=data.get('is_active')
    )

    if not conglomerate:
        return jsonify({'error': _('集團不存在')}), 404

    db.session.commit()

    return jsonify({
        'conglomerate': conglomerate.to_dict()
    })


@conglomerate_bp.route('/<secure_code>', methods=['DELETE'])
@system_admin_required
def delete_conglomerate(secure_code: str):
    """
    刪除（解散）集團

    Returns:
        204 No Content
    """
    success = ConglomerateService.delete_conglomerate(
        secure_code=secure_code,
        operator_email=current_user.email
    )

    if not success:
        return jsonify({'error': _('集團不存在')}), 404

    db.session.commit()

    return '', 204


@conglomerate_bp.route('/<secure_code>/members', methods=['PUT'])
@system_admin_required
def update_members(secure_code: str):
    """
    更新集團成員

    Body:
        org_secure_codes: [str] (至少 2 個)

    Returns:
        {added: [...], removed: [...], dissolved: bool}
    """
    data = request.get_json()
    org_secure_codes = data.get('org_secure_codes', [])

    if len(org_secure_codes) < 2:
        return jsonify({'error': _('集團至少需要兩家企業')}), 400

    try:
        result = ConglomerateService.update_organization_memberships(
            conglomerate_secure_code=secure_code,
            new_org_secure_codes=org_secure_codes,
            operator_email=current_user.email
        )
        db.session.commit()

        return jsonify({
            'added': [o.to_dict() for o in result['added']],
            'removed': [o.to_dict() for o in result['removed']],
            'dissolved': result['dissolved']
        })

    except ValueError as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': _('更新失敗: %(error)s', error=str(e))}), 500


@conglomerate_bp.route('/<secure_code>/logs', methods=['GET'])
@system_admin_required
def get_logs(secure_code: str):
    """
    取得集團操作日誌

    Query params:
        limit: int (default: 100)

    Returns:
        {logs: [...]}
    """
    limit = request.args.get('limit', 100, type=int)
    logs = ConglomerateService.get_logs(
        conglomerate_secure_code=secure_code,
        limit=limit
    )

    return jsonify({
        'logs': [log.to_dict() for log in logs]
    })


@conglomerate_bp.route('/<secure_code>/provision-db', methods=['POST'])
@system_admin_required
def provision_shared_db(secure_code: str):
    """
    為集團建立共享資料庫

    Returns:
        {db_name, admin_user, member_user, is_ready}
    """
    from ..models.conglomerate import Conglomerate

    conglomerate = Conglomerate.query.filter_by(
        secure_code=secure_code,
        is_deleted=False,
    ).first()
    if not conglomerate:
        return jsonify({'error': _('集團不存在')}), 404

    if conglomerate.has_shared_db:
        return jsonify({'error': _('此集團已有共享資料庫')}), 400

    try:
        from modules.spec_formulate.services.schema.pg_table_manager import (
            ensure_conglomerate_database,
        )
        cg_db = ensure_conglomerate_database(conglomerate)
        db.session.commit()

        return jsonify({
            'db_name': cg_db.db_name,
            'admin_user': cg_db.admin_user,
            'member_user': cg_db.member_user,
            'is_ready': cg_db.is_ready,
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': _('建立失敗: %(error)s', error=str(e))}), 500
