"""
BeakPlatform Store API
內部商場 API

提供商品列表、安裝(匯入)功能。
"""
import json
import logging
from datetime import datetime

from flask import Blueprint, jsonify, request
from flask_login import current_user

from .. import db
from ..models.store_item import StoreItem
from ..models.store_installation import StoreInstallation
from ..security.decorators import login_required, admin_required

logger = logging.getLogger(__name__)

store_bp = Blueprint('api_store', __name__, url_prefix='/api/store')


@store_bp.route('/items', methods=['GET'])
@login_required
def list_items():
    """
    取得商場商品列表

    所有登入用戶都能瀏覽，但 scope=platform 的商品僅系統企業可見。
    回傳包含該企業的安裝狀態。
    """
    org_sc = current_user.org_secure_code

    # 查詢可見商品
    query = StoreItem.query.filter(
        StoreItem.is_active == True,
        StoreItem.is_deleted == False,
    )

    # 非系統企業過濾掉 platform 商品
    from ..models.organization import Organization
    org = Organization.query.filter_by(secure_code=org_sc).first()
    if not org or not org.is_system_org:
        query = query.filter(StoreItem.scope == 'tenant')

    # 篩選條件
    item_type = request.args.get('type')
    if item_type:
        query = query.filter(StoreItem.item_type == item_type)

    category = request.args.get('category')
    if category:
        query = query.filter(StoreItem.category == category)

    items = query.order_by(StoreItem.category, StoreItem.name).all()

    # 查詢該企業的安裝記錄
    installed = StoreInstallation.query.filter(
        StoreInstallation.org_secure_code == org_sc,
        StoreInstallation.is_deleted == False,
    ).all()
    installed_map = {i.store_item_code: i for i in installed}

    result = []
    for item in items:
        d = item.to_dict()
        inst = installed_map.get(item.code)
        d['installed'] = inst is not None
        d['installed_version'] = inst.installed_version if inst else None
        d['installed_at'] = inst.installed_at.isoformat() if inst and inst.installed_at else None
        d['installed_by'] = inst.installed_by_name if inst else None
        d['upgradable'] = (
            inst is not None and inst.installed_version != item.version
        )
        result.append(d)

    return jsonify({'success': True, 'data': result})


@store_bp.route('/items/<item_sc>/install', methods=['POST'])
@admin_required
def install_item(item_sc):
    """
    安裝商品到當前企業

    僅企業管理員可執行。
    workflow_bundle: 複製表單+流程+配對到企業。
    """
    org_sc = current_user.org_secure_code

    item = StoreItem.query.filter(
        StoreItem.secure_code == item_sc,
        StoreItem.is_active == True,
        StoreItem.is_deleted == False,
    ).first()

    if not item:
        return jsonify({'success': False, 'message': '商品不存在'}), 404

    # 檢查 scope
    from ..models.organization import Organization
    org = Organization.query.filter_by(secure_code=org_sc).first()
    if item.scope == 'platform' and (not org or not org.is_system_org):
        return jsonify({'success': False, 'message': '此商品僅限系統企業安裝'}), 403

    # 檢查是否已安裝
    existing = StoreInstallation.query.filter(
        StoreInstallation.org_secure_code == org_sc,
        StoreInstallation.store_item_code == item.code,
        StoreInstallation.is_deleted == False,
    ).first()
    if existing:
        return jsonify({
            'success': False,
            'message': f'已安裝 (v{existing.installed_version})'
        }), 409

    # 執行安裝
    try:
        result_summary = _do_install(item, org_sc)

        installation = StoreInstallation(
            org_secure_code=org_sc,
            store_item_secure_code=item.secure_code,
            store_item_code=item.code,
            installed_version=item.version,
            installed_by_secure_code=current_user.secure_code,
            installed_by_name=current_user.display_name or current_user.username,
            installed_at=datetime.utcnow(),
            result_summary=result_summary,
        )
        db.session.add(installation)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': f'已安裝 {item.name} v{item.version}',
            'data': result_summary,
        })
    except Exception as e:
        db.session.rollback()
        logger.error(f'Store install failed: {item.code} -> {org_sc}: {e}')
        return jsonify({'success': False, 'message': f'安裝失敗: {str(e)}'}), 500


def _do_install(item: StoreItem, org_sc: str) -> dict:
    """
    執行商品安裝邏輯

    Returns:
        安裝結果摘要
    """
    if item.item_type == 'workflow_bundle':
        return _install_workflow_bundle(item, org_sc)
    elif item.item_type == 'form_template':
        return _install_form_template(item, org_sc)
    else:
        raise ValueError(f'Unsupported item_type: {item.item_type}')


def _install_workflow_bundle(item: StoreItem, org_sc: str) -> dict:
    """
    安裝表單+流程範本包

    payload 格式:
    {
        "form_template": { "code": "...", "name": "...", "schema": {...} },
        "workflow_template": { "code": "...", "name": "...", "graph": {...} },
        "mapping": { "priority": 0 }
    }
    """
    from modules.form_workflow.models.form_template import FwFormTemplate
    from modules.form_workflow.models.workflow_template import FwWorkflowTemplate
    from modules.form_workflow.models.form_workflow_mapping import FwFormWorkflowMapping

    payload = item.payload
    if not payload:
        raise ValueError('payload is empty')

    result = {'form_template': None, 'workflow_template': None, 'mapping': None}

    # 1. 建立表單
    ft_data = payload.get('form_template', {})
    ft = FwFormTemplate(
        org_secure_code=org_sc,
        code=ft_data.get('code', item.code + '_FORM'),
        name=ft_data.get('name', item.name + ' - 表單'),
        description=ft_data.get('description', ''),
        category=ft_data.get('category', item.category),
        schema=ft_data.get('schema', {'components': []}),
        version='AA',
        revision=1,
        is_published=True,
        is_active=True,
        is_protected=False,
        permission_type='org',
        created_by_name='內部商場',
    )
    db.session.add(ft)
    db.session.flush()
    result['form_template'] = {'code': ft.code, 'name': ft.name, 'secure_code': ft.secure_code}

    # 2. 建立流程
    wt_data = payload.get('workflow_template', {})
    wt = FwWorkflowTemplate(
        org_secure_code=org_sc,
        form_template_secure_code=ft.secure_code,
        code=wt_data.get('code', item.code + '_WF'),
        name=wt_data.get('name', item.name + ' - 流程'),
        description=wt_data.get('description', ''),
        graph=wt_data.get('graph', {'nodes': [], 'edges': []}),
        is_active=True,
        created_by_name='內部商場',
    )
    db.session.add(wt)
    db.session.flush()
    result['workflow_template'] = {'code': wt.code, 'name': wt.name, 'secure_code': wt.secure_code}

    # 3. 建立配對
    mapping_data = payload.get('mapping', {})
    mapping = FwFormWorkflowMapping(
        org_secure_code=org_sc,
        form_template_id=ft.id,
        form_template_secure_code=ft.secure_code,
        form_template_code=ft.code,
        form_template_version=ft.version,
        workflow_template_id=wt.id,
        workflow_template_secure_code=wt.secure_code,
        workflow_template_code=wt.code,
        workflow_template_version='1',
        is_active=True,
        priority=mapping_data.get('priority', 0),
    )
    db.session.add(mapping)
    db.session.flush()
    result['mapping'] = {'secure_code': mapping.secure_code}

    return result


def _install_form_template(item: StoreItem, org_sc: str) -> dict:
    """安裝單獨表單範本"""
    from modules.form_workflow.models.form_template import FwFormTemplate

    payload = item.payload
    if not payload:
        raise ValueError('payload is empty')

    ft_data = payload.get('form_template', payload)
    ft = FwFormTemplate(
        org_secure_code=org_sc,
        code=ft_data.get('code', item.code),
        name=ft_data.get('name', item.name),
        description=ft_data.get('description', ''),
        category=ft_data.get('category', item.category),
        schema=ft_data.get('schema', {'components': []}),
        version='AA',
        revision=1,
        is_published=True,
        is_active=True,
        is_protected=False,
        permission_type='org',
        created_by_name='內部商場',
    )
    db.session.add(ft)
    db.session.flush()

    return {'form_template': {'code': ft.code, 'name': ft.name, 'secure_code': ft.secure_code}}
