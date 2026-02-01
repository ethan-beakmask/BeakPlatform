"""
FormWorkflow Module - Workflows API
工作流程設計器 API

提供與 A6 相容的 API 端點，支援流程設計器前端。
"""
import secrets
from datetime import datetime
from flask import Blueprint, render_template, jsonify, request
from flask_login import current_user

from app.security.decorators import login_required
from app.platform.auth import (
    has_permission,
    require_permission,
)
from app.platform.data import get_current_org
from app import db, csrf

# 建立 API Blueprint - 使用與 A6 相同的路徑
workflows_bp = Blueprint(
    'form_workflow_workflows',
    __name__,
    url_prefix='/api/workflows'
)


# =============================================================================
# 輔助函數
# =============================================================================

def _get_default_graph():
    """
    取得預設流程圖（包含 Start 和 End 節點）
    """
    return {
        "nodes": [
            {
                "id": "node-Start",
                "label": "開始",
                "type": "Start",
                "icon": "/static/modules/form_workflow/icons/workflow/start.svg",
                "config": {},
                "description": "",
                "position": {"x": -175, "y": -50}
            },
            {
                "id": "node-End",
                "label": "結束",
                "type": "End",
                "icon": "/static/modules/form_workflow/icons/workflow/end.svg",
                "config": {},
                "description": "",
                "position": {"x": 875, "y": 350}
            }
        ],
        "edges": [],
        "relayPoints": []
    }


def _get_node_definitions():
    """
    取得節點定義列表

    每個節點包含 require_system_admin 欄位，用於 API 層權限過濾。
    """
    _ICON = "/static/modules/form_workflow/icons/workflow"
    return [
        # =================================================================
        # 基本
        # =================================================================
        {
            "node_type": "Start",
            "display_name": "開始",
            "description": "流程的起點",
            "icon": f"{_ICON}/start.svg",
            "category": "基本",
            "config_schema": {},
            "is_active": True,
            "require_system_admin": False,
        },
        {
            "node_type": "End",
            "display_name": "結束",
            "description": "流程的終點",
            "icon": f"{_ICON}/end.svg",
            "category": "基本",
            "config_schema": {},
            "is_active": True,
            "require_system_admin": False,
        },
        # =================================================================
        # 表單 / 簽核
        # =================================================================
        {
            "node_type": "FormAdapter",
            "display_name": "簽核",
            "description": "表單簽核節點",
            "icon": f"{_ICON}/formadapter.svg",
            "category": "表單",
            "config_schema": {
                "assigneeType": "string",
                "assigneeValue": "string",
                "approvalMode": "string"
            },
            "is_active": True,
            "require_system_admin": False,
        },
        # =================================================================
        # 流程控制
        # =================================================================
        {
            "node_type": "Delay",
            "display_name": "暫停",
            "description": "延遲執行指定時間",
            "icon": f"{_ICON}/delay.svg",
            "category": "控制",
            "config_schema": {
                "delay_seconds": "number"
            },
            "is_active": True,
            "require_system_admin": False,
        },
        {
            "node_type": "Branch",
            "display_name": "分支",
            "description": "根據條件選擇路徑",
            "icon": f"{_ICON}/branch.svg",
            "category": "控制",
            "config_schema": {},
            "is_active": True,
            "require_system_admin": False,
        },
        {
            "node_type": "Condition",
            "display_name": "條件判斷",
            "description": "條件判斷節點",
            "icon": f"{_ICON}/condition.svg",
            "category": "控制",
            "config_schema": {},
            "is_active": True,
            "require_system_admin": False,
        },
        {
            "node_type": "Switch",
            "display_name": "條件分支",
            "description": "多路條件判斷分支",
            "icon": f"{_ICON}/switch.svg",
            "category": "控制",
            "config_schema": {},
            "is_active": True,
            "require_system_admin": False,
        },
        {
            "node_type": "Converge",
            "display_name": "匯合",
            "description": "等待多條路徑匯合",
            "icon": f"{_ICON}/converge.svg",
            "category": "控制",
            "config_schema": {
                "mode": "string"
            },
            "is_active": True,
            "require_system_admin": False,
        },
        {
            "node_type": "ParallelFork",
            "display_name": "並行分支",
            "description": "並行執行多路分支",
            "icon": f"{_ICON}/parallelfork.svg",
            "category": "控制",
            "config_schema": {},
            "is_active": True,
            "require_system_admin": False,
        },
        {
            "node_type": "ParallelJoin",
            "display_name": "並行匯合",
            "description": "等待所有並行分支完成",
            "icon": f"{_ICON}/paralleljoin.svg",
            "category": "控制",
            "config_schema": {
                "mode": "string"
            },
            "is_active": True,
            "require_system_admin": False,
        },
        {
            "node_type": "SubFlow",
            "display_name": "子流程",
            "description": "呼叫其他工作流程",
            "icon": f"{_ICON}/subflow.svg",
            "category": "控制",
            "config_schema": {
                "childFlowId": "string"
            },
            "is_active": True,
            "require_system_admin": False,
        },
        # =================================================================
        # 通知
        # =================================================================
        {
            "node_type": "Notification",
            "display_name": "通知",
            "description": "系統內部通知",
            "icon": f"{_ICON}/notification.svg",
            "category": "通知",
            "config_schema": {
                "message": "string",
                "notifyType": "string"
            },
            "is_active": True,
            "require_system_admin": False,
        },
        {
            "node_type": "Telegram",
            "display_name": "Telegram 通知",
            "description": "發送 Telegram 訊息",
            "icon": f"{_ICON}/telegram.svg",
            "category": "通知",
            "config_schema": {
                "message": "string",
                "chat_id": "string"
            },
            "is_active": True,
            "require_system_admin": False,
        },
        {
            "node_type": "EmailAdapter",
            "display_name": "Email 通知",
            "description": "發送 Email",
            "icon": f"{_ICON}/emailadapter.svg",
            "category": "通知",
            "config_schema": {
                "to": "string",
                "subject": "string",
                "body": "string"
            },
            "is_active": True,
            "require_system_admin": False,
        },
        # =================================================================
        # 變數 / 資料操作
        # =================================================================
        {
            "node_type": "OpSet",
            "display_name": "設定變數",
            "description": "設定流程變數值",
            "icon": f"{_ICON}/opset.svg",
            "category": "變數",
            "config_schema": {
                "variables": "array"
            },
            "is_active": True,
            "require_system_admin": False,
        },
        {
            "node_type": "OpFieldRead",
            "display_name": "讀取欄位",
            "description": "從表單讀取欄位到變數",
            "icon": f"{_ICON}/opfieldread.svg",
            "category": "變數",
            "config_schema": {
                "mappings": "array"
            },
            "is_active": True,
            "require_system_admin": False,
        },
        {
            "node_type": "OpFieldWrite",
            "display_name": "寫入欄位",
            "description": "將變數寫入表單欄位",
            "icon": f"{_ICON}/opfieldwrite.svg",
            "category": "變數",
            "config_schema": {
                "mappings": "array"
            },
            "is_active": True,
            "require_system_admin": False,
        },
        {
            "node_type": "FormExp",
            "display_name": "表單匯出",
            "description": "將表單資料匯出",
            "icon": f"{_ICON}/formexp.svg",
            "category": "變數",
            "config_schema": {},
            "is_active": True,
            "require_system_admin": False,
        },
        # =================================================================
        # 外部整合
        # =================================================================
        {
            "node_type": "EmailRelay",
            "display_name": "Email 轉發",
            "description": "透過外部系統發送 Email",
            "icon": f"{_ICON}/emailrelay.svg",
            "category": "整合",
            "config_schema": {
                "to": "string",
                "subject": "string",
                "body": "string"
            },
            "is_active": True,
            "require_system_admin": False,
        },
        {
            "node_type": "SqlExecutor",
            "display_name": "SQL 執行",
            "description": "執行 SQL 查詢",
            "icon": f"{_ICON}/sqlexecutor.svg",
            "category": "整合",
            "config_schema": {
                "sql": "string",
                "connection": "string"
            },
            "is_active": True,
            "require_system_admin": False,
        },
        # =================================================================
        # 系統（部分僅系統管理員可見）
        # =================================================================
        {
            "node_type": "SysTelegram",
            "display_name": "系統 Telegram",
            "description": "系統級 Telegram 通知",
            "icon": f"{_ICON}/systelegram.svg",
            "category": "系統",
            "config_schema": {
                "message": "string"
            },
            "is_active": True,
            "require_system_admin": True,
        },
        {
            "node_type": "Abandon",
            "display_name": "中止",
            "description": "強制中止流程",
            "icon": f"{_ICON}/abandon.svg",
            "category": "系統",
            "config_schema": {},
            "is_active": True,
            "require_system_admin": False,
        },
    ]


# =============================================================================
# 頁面路由
# =============================================================================

@workflows_bp.route('/list')
@login_required
def list_page():
    """流程模板列表頁面"""
    return render_template(
        'modules/form_workflow/workflow_list.html',
        active_menu_code='form_workflow.workflows'
    )


@workflows_bp.route('/designer')
@workflows_bp.route('/designer/<secure_code>')
@login_required
def designer(secure_code=None):
    """流程設計器頁面"""
    from ..models import FwWorkflowTemplate

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    if secure_code:
        # 編輯模式
        template = FwWorkflowTemplate.query.filter_by(
            secure_code=secure_code,
            org_secure_code=org.secure_code,
            is_deleted=False
        ).first()

        if not template:
            return jsonify({'success': False, 'error': 'Workflow not found'}), 404
    else:
        template = None

    return render_template(
        'modules/form_workflow/workflow_designer.html',
        org_secure_code=org.secure_code,
        workflow_secure_code=secure_code,
        workflow=template.to_dict(include_graph=True) if template else None
    )


@workflows_bp.route('/designer/standalone')
@login_required
def designer_standalone():
    """流程設計器獨立頁面（用於 iframe 嵌入）"""
    from ..models import FwWorkflowTemplate

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    secure_code = request.args.get('id')
    template = None

    if secure_code:
        template = FwWorkflowTemplate.query.filter_by(
            secure_code=secure_code,
            org_secure_code=org.secure_code,
            is_deleted=False
        ).first()

    return render_template(
        'modules/form_workflow/workflow_designer.html',
        org_secure_code=org.secure_code,
        workflow_secure_code=secure_code,
        workflow=template.to_dict(include_graph=True) if template else None
    )


# =============================================================================
# 數據 API
# =============================================================================

@workflows_bp.route('/data/templates')
@login_required
def list_templates():
    """取得流程模板列表"""
    from ..models import FwWorkflowTemplate

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    query = FwWorkflowTemplate.query.filter_by(
        org_secure_code=org.secure_code,
        is_deleted=False
    )

    # 搜尋
    q = request.args.get('q', '').strip()
    if q:
        query = query.filter(
            FwWorkflowTemplate.name.ilike(f'%{q}%') |
            FwWorkflowTemplate.code.ilike(f'%{q}%')
        )

    # 排除子流程
    include_subprocess = request.args.get('include_subprocess', 'false').lower() == 'true'
    if not include_subprocess:
        query = query.filter(FwWorkflowTemplate.is_subprocess == False)

    templates = query.order_by(FwWorkflowTemplate.updated_at.desc()).all()

    return jsonify({
        'success': True,
        'templates': [t.to_dict(include_graph=False) for t in templates]
    })


@workflows_bp.route('/data/templates/<secure_code>')
@login_required
def get_template(secure_code):
    """取得單一流程模板"""
    from ..models import FwWorkflowTemplate

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    template = FwWorkflowTemplate.query.filter_by(
        secure_code=secure_code,
        org_secure_code=org.secure_code,
        is_deleted=False
    ).first()

    if not template:
        return jsonify({'success': False, 'error': 'Template not found'}), 404

    result = template.to_dict(include_graph=True)

    # 確保有預設的 graph
    if not result.get('graph') and not result.get('cytoscape_config'):
        result['cytoscape_config'] = _get_default_graph()

    return jsonify({
        'success': True,
        **result
    })


@workflows_bp.route('/data/templates', methods=['POST'])
@csrf.exempt
@login_required
def create_template():
    """建立流程模板"""
    from ..models import FwWorkflowTemplate

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    data = request.get_json() or {}
    name = data.get('name', '').strip()

    if not name:
        return jsonify({'success': False, 'error': 'Name is required'}), 400

    # 自動產生 code
    code = data.get('code', '').strip().upper()
    if not code:
        code = f'WF{secrets.token_hex(4).upper()}'

    # 檢查 code 是否重複
    existing = FwWorkflowTemplate.query.filter_by(
        code=code,
        org_secure_code=org.secure_code,
        is_deleted=False
    ).first()
    if existing:
        return jsonify({'success': False, 'error': f'Code {code} already exists'}), 400

    template = FwWorkflowTemplate(
        secure_code=secrets.token_urlsafe(16),
        org_secure_code=org.secure_code,
        name=name,
        code=code,
        description=data.get('description', ''),
        graph=data.get('graph') or _get_default_graph(),
        cytoscape_config=data.get('cytoscape_config') or _get_default_graph(),
        is_active=data.get('is_active', True),
        is_subprocess=data.get('is_subprocess', False),
        owner_secure_code=current_user.secure_code
    )

    db.session.add(template)
    db.session.commit()

    return jsonify({
        'success': True,
        'secure_code': template.secure_code,
        **template.to_dict(include_graph=True),
        'message': '流程模板已建立'
    })


@workflows_bp.route('/data/templates/<secure_code>', methods=['PUT'])
@csrf.exempt
@login_required
def update_template(secure_code):
    """更新流程模板"""
    from ..models import FwWorkflowTemplate, FwFormTemplate, FwFormWorkflowMapping

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    template = FwWorkflowTemplate.query.filter_by(
        secure_code=secure_code,
        org_secure_code=org.secure_code,
        is_deleted=False
    ).first()

    if not template:
        return jsonify({'success': False, 'error': 'Template not found'}), 404

    data = request.get_json() or {}

    # 記錄舊的 revision（用於判斷是否首次儲存）
    old_revision = template.revision or 0

    if 'name' in data:
        template.name = data['name'].strip()
    if 'description' in data:
        template.description = data['description']
    if 'graph' in data:
        template.graph = data['graph']
    if 'cytoscape_config' in data:
        template.cytoscape_config = data['cytoscape_config']
    if 'category' in data:
        template.category = data['category']
    if 'is_active' in data:
        template.is_active = data['is_active']

    # 縮圖
    if 'thumbnail_2x1' in data:
        template.thumbnail_2x1 = data['thumbnail_2x1']
    if 'thumbnail_1x1' in data:
        template.thumbnail_1x1 = data['thumbnail_1x1']
    if 'thumbnail_1x2' in data:
        template.thumbnail_1x2 = data['thumbnail_1x2']

    # 首次儲存時遞增 revision
    if old_revision == 0 and (data.get('graph') or data.get('cytoscape_config')):
        template.revision = 1

    template.updated_at = datetime.utcnow()

    # =========================================================================
    # 自動配對機制：首次儲存時（revision 0 → 1），自動建立同名表單並配對
    # =========================================================================
    auto_created_form = None
    auto_created_mapping = None

    if old_revision == 0 and template.revision == 1 and not template.is_subprocess:
        # 檢查是否已存在同名表單
        existing_form = FwFormTemplate.query.filter_by(
            org_secure_code=org.secure_code,
            name=template.name,
            is_deleted=False
        ).first()

        if not existing_form:
            # 建立空白表單（流程記錄單）
            form_code = f"FORM_{template.code}_{secrets.token_hex(2).upper()}"
            form_category = template.category if hasattr(template, 'category') and template.category else '流程記錄單'

            form_template = FwFormTemplate(
                secure_code=secrets.token_urlsafe(16),
                org_secure_code=org.secure_code,
                code=form_code,
                name=template.name,
                version='AA',
                description=f'{template.name} 流程記錄單',
                category=form_category,
                schema={
                    "components": [],
                    "display": "form"
                },
                is_active=True,
                is_published=False,
                owner_secure_code=current_user.secure_code
            )
            db.session.add(form_template)
            db.session.flush()  # 取得 form_template.id
            auto_created_form = form_template

            # 自動建立配對關係
            mapping = FwFormWorkflowMapping(
                secure_code=secrets.token_urlsafe(16),
                org_secure_code=org.secure_code,
                form_template_id=form_template.id,
                form_template_secure_code=form_template.secure_code,
                form_template_code=form_template.code,
                form_template_version=form_template.version,
                workflow_template_id=template.id,
                workflow_template_secure_code=template.secure_code,
                workflow_template_code=template.code,
                workflow_template_version=template.version or 'AA',
                is_active=True,
                is_published=False
            )
            db.session.add(mapping)
            auto_created_mapping = mapping

    db.session.commit()

    # 建立回應
    response_data = {
        'success': True,
        **template.to_dict(include_graph=True),
        'message': '流程模板已更新'
    }

    # 如果有自動建立表單和配對，加入額外資訊
    if auto_created_form:
        response_data['auto_created'] = {
            'form': {
                'secure_code': auto_created_form.secure_code,
                'name': auto_created_form.name,
                'code': auto_created_form.code
            },
            'mapping': {
                'secure_code': auto_created_mapping.secure_code
            } if auto_created_mapping else None
        }
        response_data['message'] = f'流程模板已更新，並自動建立表單「{auto_created_form.name}」及配對'

    return jsonify(response_data)


@workflows_bp.route('/data/templates/<secure_code>', methods=['DELETE'])
@csrf.exempt
@login_required
def delete_template(secure_code):
    """刪除流程模板（軟刪除）"""
    from ..models import FwWorkflowTemplate

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    template = FwWorkflowTemplate.query.filter_by(
        secure_code=secure_code,
        org_secure_code=org.secure_code,
        is_deleted=False
    ).first()

    if not template:
        return jsonify({'success': False, 'error': 'Template not found'}), 404

    template.is_deleted = True
    # template.updated_by = current_user.secure_code  # Model 沒有此欄位
    template.updated_at = datetime.utcnow()
    db.session.commit()

    return jsonify({
        'success': True,
        'message': '流程模板已刪除'
    })


@workflows_bp.route('/data/templates/<secure_code>/save-new-version', methods=['POST'])
@csrf.exempt
@login_required
def save_new_version(secure_code):
    """儲存新版本"""
    from ..models import FwWorkflowTemplate, FwFormTemplate, FwFormWorkflowMapping

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    template = FwWorkflowTemplate.query.filter_by(
        secure_code=secure_code,
        org_secure_code=org.secure_code,
        is_deleted=False
    ).first()

    if not template:
        return jsonify({'success': False, 'error': 'Template not found'}), 404

    data = request.get_json() or {}

    # 記錄舊的 revision（用於判斷是否首次儲存）
    old_revision = template.revision or 0

    # 更新版本號
    current_version = template.version or 'AA'
    # 簡單的版本遞增（AA -> AB -> ... -> AZ -> BA -> ...）
    if len(current_version) >= 2:
        first, second = current_version[0], current_version[1]
        if second == 'Z':
            new_version = chr(ord(first) + 1) + 'A'
        else:
            new_version = first + chr(ord(second) + 1)
    else:
        new_version = 'AA'

    template.version = new_version
    template.revision = old_revision + 1

    if 'graph' in data:
        template.graph = data['graph']
    if 'cytoscape_config' in data:
        template.cytoscape_config = data['cytoscape_config']

    template.updated_at = datetime.utcnow()

    # =========================================================================
    # 自動配對機制：首次儲存時（revision 0 → 1），自動建立同名表單並配對
    # =========================================================================
    auto_created_form = None
    auto_created_mapping = None

    if old_revision == 0 and not template.is_subprocess:
        # 檢查是否已存在同名表單
        existing_form = FwFormTemplate.query.filter_by(
            org_secure_code=org.secure_code,
            name=template.name,
            is_deleted=False
        ).first()

        if not existing_form:
            # 建立空白表單（流程記錄單）
            form_code = f"FORM_{template.code}_{secrets.token_hex(2).upper()}"
            form_category = template.category if hasattr(template, 'category') and template.category else '流程記錄單'

            form_template = FwFormTemplate(
                secure_code=secrets.token_urlsafe(16),
                org_secure_code=org.secure_code,
                code=form_code,
                name=template.name,
                version='AA',
                description=f'{template.name} 流程記錄單',
                category=form_category,
                schema={
                    "components": [],
                    "display": "form"
                },
                is_active=True,
                is_published=False,
                owner_secure_code=current_user.secure_code
            )
            db.session.add(form_template)
            db.session.flush()  # 取得 form_template.id
            auto_created_form = form_template

            # 自動建立配對關係
            mapping = FwFormWorkflowMapping(
                secure_code=secrets.token_urlsafe(16),
                org_secure_code=org.secure_code,
                form_template_id=form_template.id,
                form_template_secure_code=form_template.secure_code,
                form_template_code=form_template.code,
                form_template_version=form_template.version,
                workflow_template_id=template.id,
                workflow_template_secure_code=template.secure_code,
                workflow_template_code=template.code,
                workflow_template_version=template.version,
                is_active=True,
                is_published=False
            )
            db.session.add(mapping)
            auto_created_mapping = mapping

    db.session.commit()

    # 建立回應
    response_data = {
        'success': True,
        **template.to_dict(include_graph=True),
        'message': f'已儲存新版本 {new_version}'
    }

    # 如果有自動建立表單和配對，加入額外資訊
    if auto_created_form:
        response_data['auto_created'] = {
            'form': {
                'secure_code': auto_created_form.secure_code,
                'name': auto_created_form.name,
                'code': auto_created_form.code
            },
            'mapping': {
                'secure_code': auto_created_mapping.secure_code
            } if auto_created_mapping else None
        }
        response_data['message'] = f'已儲存新版本 {new_version}，並自動建立表單「{auto_created_form.name}」及配對'

    return jsonify(response_data)


# =============================================================================
# 節點定義 API
# =============================================================================

@workflows_bp.route('/data/node-definitions')
@login_required
def get_node_definitions():
    """
    取得節點定義列表（按分類分組）

    過濾邏輯：
    - Start 節點不出現在面板（由系統自動建立，一個流程只能有一個起點）
    - require_system_admin=True 的節點僅系統管理員可見
    """
    definitions = _get_node_definitions()
    is_sys_admin = getattr(current_user, 'is_system_admin', False)

    # 將節點按分類分組
    category_map = {
        '基本': 'basic',
        '表單': 'form',
        '通知': 'notification',
        '控制': 'flow_control',
        '變數': 'data',
        '操作': 'operation',
        '整合': 'integration',
        '系統': 'system',
    }

    grouped = {}
    for node_def in definitions:
        # 隱藏 Start 節點（由系統自動建立，避免用戶重複拖放）
        if node_def['node_type'] == 'Start':
            continue

        # 權限過濾：非系統管理員看不到 require_system_admin 的節點
        if node_def.get('require_system_admin') and not is_sys_admin:
            continue

        category_zh = node_def.get('category', '基本')
        category_key = category_map.get(category_zh, 'basic')

        if category_key not in grouped:
            grouped[category_key] = []

        grouped[category_key].append({
            'type': node_def['node_type'],
            'label': node_def['display_name'],
            'icon': node_def['icon'],
            'description': node_def.get('description', '')
        })

    return jsonify({
        'success': True,
        'data': grouped
    })


@workflows_bp.route('/nodes/<node_type>/schema')
@login_required
def get_node_schema(node_type):
    """取得節點的配置 schema"""
    definitions = _get_node_definitions()

    for node_def in definitions:
        if node_def['node_type'].lower() == node_type.lower():
            return jsonify({
                'success': True,
                'schema': node_def.get('config_schema', {})
            })

    return jsonify({
        'success': False,
        'error': f'Node type {node_type} not found'
    }), 404


# =============================================================================
# 子流程 API
# =============================================================================

@workflows_bp.route('/data/subflows/available')
@login_required
def list_available_subflows():
    """取得可用的子流程列表"""
    from ..models import FwWorkflowTemplate

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    parent_id = request.args.get('parent_id')

    # 查詢子流程
    query = FwWorkflowTemplate.query.filter_by(
        org_secure_code=org.secure_code,
        is_subprocess=True,
        is_deleted=False
    )

    subflows = query.order_by(FwWorkflowTemplate.name).all()

    return jsonify({
        'success': True,
        'subflows': [
            {
                'secure_code': sf.secure_code,
                'code': sf.code,
                'name': sf.name,
                'description': sf.description,
                'is_exclusive': sf.parent_workflow_id is not None
            }
            for sf in subflows
        ]
    })


@workflows_bp.route('/data/subflows/create', methods=['POST'])
@csrf.exempt
@login_required
def create_subflow():
    """建立子流程"""
    from ..models import FwWorkflowTemplate

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    data = request.get_json() or {}
    name = data.get('name', '').strip()
    parent_id = data.get('parent_id')

    if not name:
        return jsonify({'success': False, 'error': 'Name is required'}), 400

    code = f'SF{secrets.token_hex(4).upper()}'

    subflow = FwWorkflowTemplate(
        secure_code=secrets.token_urlsafe(16),
        org_secure_code=org.secure_code,
        name=name,
        code=code,
        description=data.get('description', ''),
        graph=data.get('graph') or _get_default_graph(),
        cytoscape_config=data.get('cytoscape_config') or _get_default_graph(),
        is_active=True,
        is_subprocess=True,
        parent_workflow_id=parent_id,
        owner_secure_code=current_user.secure_code
    )

    db.session.add(subflow)
    db.session.commit()

    return jsonify({
        'success': True,
        'secure_code': subflow.secure_code,
        'code': subflow.code,
        **subflow.to_dict(include_graph=True),
        'message': '子流程已建立'
    })


# =============================================================================
# 變數映射 API
# =============================================================================

@workflows_bp.route('/data/variable-mapping', methods=['GET', 'POST'])
@csrf.exempt
@login_required
def variable_mapping():
    """
    取得或建立變數映射

    POST: 根據配對表單建立 內部變數 <-> 顯示變數 的雙向映射表
        內部格式: ${SECURE_CODE_fieldKey}   (除錯用唯一識別碼)
        顯示格式: ${表單名稱::欄位標籤}       (人類可讀格式)
    """
    from ..models import FwFormTemplate

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    if request.method == 'GET':
        return jsonify({
            'success': True,
            'mapping': {
                'form_fields': [],
                'workflow_variables': [],
                'system_variables': [
                    {'name': 'applicant_name', 'type': 'string', 'description': '申請人姓名'},
                    {'name': 'applicant_department', 'type': 'string', 'description': '申請人部門'},
                    {'name': 'submit_date', 'type': 'datetime', 'description': '提交日期'},
                    {'name': 'serial_number', 'type': 'string', 'description': '表單序號'},
                ]
            }
        })

    # POST - 根據 form_ids 建立變數映射表
    data = request.get_json() or {}
    form_ids = data.get('form_ids', [])

    if not form_ids:
        return jsonify({'success': True, 'data': {'forward': {}, 'reverse': {}, 'form_info': {}}})

    try:
        forward = {}
        reverse = {}
        form_info = {}

        for form_secure_code in form_ids:
            form = FwFormTemplate.query.filter_by(
                secure_code=form_secure_code,
                org_secure_code=org.secure_code,
                is_deleted=False
            ).first()

            if not form or not form.schema:
                continue

            form_name = form.name or ''
            # 正規化表單名稱：移除半形和全形空格
            display_form_name = form_name.replace(' ', '').replace('\u3000', '')

            # 提取欄位
            fields = _extract_form_fields(form.schema.get('components', []))

            # 檢測同一表單內欄位標籤重複
            label_counts = {}
            for f in fields:
                norm_label = (f.get('label', '') or '').replace(' ', '').replace('\u3000', '')
                label_counts[norm_label] = label_counts.get(norm_label, 0) + 1

            # 建立映射
            field_info = {}
            for f in fields:
                key = f.get('key', '')
                if not key:
                    continue

                label = f.get('label', '') or key
                norm_label = label.replace(' ', '').replace('\u3000', '')

                # 同名標籤加上 key 後綴區分
                if label_counts.get(norm_label, 0) > 1:
                    display_label = f"{norm_label}({key})"
                else:
                    display_label = norm_label

                internal_var = f"{form_secure_code}_{key}"
                display_var = f"{display_form_name}::{display_label}"

                forward[internal_var] = display_var
                reverse[display_var] = internal_var

                field_info[key] = {
                    'label': label,
                    'display_label': display_label
                }

            form_info[form_secure_code] = {
                'name': form_name,
                'display_name': display_form_name,
                'fields': field_info
            }

        return jsonify({
            'success': True,
            'data': {
                'forward': forward,
                'reverse': reverse,
                'form_info': form_info
            }
        })

    except Exception as e:
        import traceback
        print(f"❌ VARIABLE_MAPPING ERROR: {str(e)}")
        print(f"📋 Traceback:\n{traceback.format_exc()}")
        return jsonify({'success': False, 'message': f'建立變數映射失敗: {str(e)}'}), 500


# =============================================================================
# 組織樹 API（用於選擇簽核人）
# =============================================================================

@workflows_bp.route('/data/org-tree')
@login_required
def get_org_tree():
    """取得組織架構樹（用於選擇簽核人）"""
    from app.models.organizational_unit import OrganizationalUnit, UnitType
    from app.models.user import User

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    # 取得部門（只取 DEPARTMENT 類型）
    departments = OrganizationalUnit.query.filter_by(
        org_secure_code=org.secure_code,
        unit_type=UnitType.DEPARTMENT,
        is_deleted=False,
        is_active=True
    ).order_by(OrganizationalUnit.sort_order.asc()).all()

    # 取得用戶（排除已刪除和停用的帳號）
    users = User.query.filter_by(
        org_secure_code=org.secure_code,
        is_active=True,
        is_deleted=False
    ).all()

    def build_tree(parent_code=None):
        result = []
        for dept in departments:
            if dept.parent_secure_code == parent_code:
                dept_name = dept.name
                node = {
                    'id': f'dept_{dept.secure_code}',
                    'name': dept_name,
                    'type': 'department',
                    'secure_code': dept.secure_code,
                    'children': build_tree(dept.secure_code)
                }
                # 添加該部門的用戶（透過 primary_unit_secure_code）
                dept_users = [u for u in users if u.primary_unit_secure_code == dept.secure_code]
                for user in dept_users:
                    node['children'].append({
                        'id': f'user_{user.secure_code}',
                        'label': user.display_name or user.username,
                        'type': 'user',
                        'secure_code': user.secure_code
                    })
                result.append(node)
        return result

    tree = build_tree(None)

    # 未歸屬部門的用戶
    dept_codes = {d.secure_code for d in departments}
    unassigned = [u for u in users if not u.primary_unit_secure_code or u.primary_unit_secure_code not in dept_codes]
    if unassigned:
        tree.append({
            'id': 'dept_unassigned',
            'name': '(未歸屬部門)',
            'type': 'department',
            'secure_code': '',
            'children': [{
                'id': f'user_{u.secure_code}',
                'label': u.display_name or u.username,
                'type': 'user',
                'secure_code': u.secure_code
            } for u in unassigned]
        })

    return jsonify({
        'success': True,
        'data': tree
    })


@workflows_bp.route('/data/roles')
@login_required
def get_roles_list():
    """取得角色列表（用於簽核人角色選擇）"""
    from app.models.role import Role

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    roles = Role.query.filter(
        Role.org_secure_code == org.secure_code,
        Role.is_deleted == False,
        Role.is_active == True
    ).order_by(Role.name).all()

    result = []
    for role in roles:
        result.append({
            'secure_code': role.secure_code,
            'code': role.code,
            'name': role.name,
        })

    return jsonify({
        'success': True,
        'data': result
    })


# =============================================================================
# 表單欄位 API（用於 OPSET 變數）
# =============================================================================

@workflows_bp.route('/data/templates/<template_id>/mapped-forms', methods=['GET'])
@login_required
def get_workflow_mapped_forms(template_id):
    """
    取得指定流程的已配對表單清單

    支援兩種版本來源：
    - 設計版：從 FwFormWorkflowMapping 取得
    - 發行版：從 FwPublishedFormWorkflow 取得

    Query Parameters:
        version_type: 'design' (設計版, 預設) 或 'published' (發行版)

    Returns:
        JSON: {
            "success": true,
            "data": {
                "forms": [
                    {
                        "form_secure_code": "...",
                        "form_name": "請假申請單",
                        "form_version": "AA",
                        "form_revision": 5,
                        "mapping_id": 1,
                        "source": "design" | "published",
                        "publish_version": null | 1
                    }
                ],
                "total": 2,
                "auto_select": true | false
            }
        }
    """
    from ..models import FwWorkflowTemplate, FwFormWorkflowMapping, FwPublishedFormWorkflow, FwFormTemplate

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    version_type = request.args.get('version_type', 'design')

    try:
        # 取得流程模板
        workflow = FwWorkflowTemplate.query.filter_by(
            secure_code=template_id,
            org_secure_code=org.secure_code,
            is_deleted=False
        ).first()

        if not workflow:
            return jsonify({'success': False, 'message': '流程不存在'}), 404

        forms = []

        if version_type == 'published':
            # 從發行版取得表單
            published_list = FwPublishedFormWorkflow.query.filter_by(
                source_workflow_template_id=workflow.id,
                org_secure_code=org.secure_code
            ).filter(
                FwPublishedFormWorkflow.status.in_(['Published', 'Suspended'])
            ).order_by(FwPublishedFormWorkflow.publish_version.desc()).all()

            # 去重：同一個表單只保留最新發行版
            seen_forms = set()
            for pub in published_list:
                form_id = pub.source_form_template_id
                if form_id not in seen_forms:
                    seen_forms.add(form_id)
                    form = FwFormTemplate.query.get(form_id)
                    if form and not form.is_deleted:
                        forms.append({
                            'form_id': form.secure_code,  # 前端使用此欄位呼叫 API
                            'form_secure_code': form.secure_code,
                            'form_name': form.name,
                            'form_version': pub.form_snapshot.get('version', 'AA') if pub.form_snapshot else form.version,
                            'form_revision': pub.form_snapshot.get('revision', 1) if pub.form_snapshot else form.revision,
                            'mapping_id': pub.source_mapping_id,
                            'source': 'published',
                            'publish_version': pub.publish_version,
                            'publish_status': pub.status
                        })
        else:
            # 從設計版 (Mapping) 取得表單
            mappings = FwFormWorkflowMapping.query.filter_by(
                workflow_template_id=workflow.id,
                org_secure_code=org.secure_code,
                is_active=True
            ).all()

            for mapping in mappings:
                # 直接查詢表單（避免關聯問題）
                form = FwFormTemplate.query.filter_by(
                    id=mapping.form_template_id,
                    org_secure_code=org.secure_code,
                    is_deleted=False
                ).first()

                if form:
                    form_data = {
                        'form_id': form.secure_code,  # 前端使用此欄位呼叫 API
                        'form_secure_code': form.secure_code,
                        'form_name': form.name,
                        'form_version': form.version,
                        'form_revision': form.revision,
                        'mapping_id': mapping.id,
                        'source': 'design',
                        'publish_version': None,
                        'publish_status': None
                    }
                    print(f"📋 Adding form: {form_data}")
                    forms.append(form_data)

        return jsonify({
            'success': True,
            'data': {
                'forms': forms,
                'total': len(forms),
                'auto_select': len(forms) == 1
            }
        })

    except Exception as e:
        import traceback
        print(f"❌ GET_WORKFLOW_MAPPED_FORMS ERROR: {str(e)}")
        print(f"📋 Traceback:\n{traceback.format_exc()}")
        return jsonify({'success': False, 'message': f'取得配對表單失敗: {str(e)}'}), 500


@workflows_bp.route('/data/forms/<form_id>/fields', methods=['GET'])
@login_required
def get_form_fields(form_id):
    """
    分析並取得指定表單的欄位清單

    Query Parameters:
        version_type: 'design' (設計版, 預設) 或 'published' (發行版)
        publish_version: 發行版號 (僅當 version_type=published 時使用)
        mapping_id: Mapping ID (用於取得特定配對的發行版)

    Returns:
        JSON: {
            "success": true,
            "data": {
                "form_info": {
                    "secure_code": "...",
                    "name": "請假申請單",
                    "version": "AA",
                    "revision": 5
                },
                "fields": [
                    {
                        "key": "applicant_name",
                        "label": "申請人姓名",
                        "type": "textfield",
                        "data_type": "string",
                        "default_value": null,
                        "options": null,
                        "required": true,
                        "path": "data.applicant_name",
                        "nested_level": 0
                    }
                ],
                "total": 10
            }
        }
    """
    from ..models import FwFormTemplate, FwPublishedFormWorkflow

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    version_type = request.args.get('version_type', 'design')
    publish_version = request.args.get('publish_version')
    mapping_id = request.args.get('mapping_id')

    try:
        # 取得表單
        form = FwFormTemplate.query.filter_by(
            secure_code=form_id,
            org_secure_code=org.secure_code,
            is_deleted=False
        ).first()

        if not form:
            return jsonify({'success': False, 'message': '表單不存在'}), 404

        # 取得 schema
        schema = None
        form_info = {
            'secure_code': form.secure_code,
            'name': form.name,
            'version': form.version,
            'revision': form.revision
        }

        if version_type == 'published' and mapping_id:
            # 從發行版取得 schema
            query = FwPublishedFormWorkflow.query.filter_by(
                source_mapping_id=int(mapping_id),
                org_secure_code=org.secure_code
            )
            if publish_version:
                query = query.filter_by(publish_version=int(publish_version))
            else:
                query = query.filter(FwPublishedFormWorkflow.status == 'Published')

            published = query.order_by(FwPublishedFormWorkflow.publish_version.desc()).first()

            if published and published.form_snapshot:
                schema = published.form_snapshot.get('schema', {})
                form_info['version'] = published.form_snapshot.get('version', form.version)
                form_info['revision'] = published.form_snapshot.get('revision', form.revision)
                form_info['source'] = 'published'
                form_info['publish_version'] = published.publish_version
        else:
            # 從設計版取得 schema
            schema = form.schema
            form_info['source'] = 'design'

        if not schema:
            schema = form.schema  # 回退到設計版

        # 分析欄位
        fields = _extract_form_fields(schema.get('components', []) if schema else [])

        return jsonify({
            'success': True,
            'data': {
                'form_info': form_info,
                'fields': fields,
                'total': len(fields)
            }
        })

    except Exception as e:
        import traceback
        print(f"❌ GET_FORM_FIELDS ERROR: {str(e)}")
        print(f"📋 Traceback:\n{traceback.format_exc()}")
        return jsonify({'success': False, 'message': f'分析表單欄位失敗: {str(e)}'}), 500


def _extract_form_fields(components, path_prefix='data', nested_level=0):
    """
    遞迴分析 Form.io schema 中的欄位

    Args:
        components: Form.io 元件陣列
        path_prefix: 欄位路徑前綴
        nested_level: 巢狀層級

    Returns:
        list: 欄位資訊列表
    """
    fields = []

    # Form.io 類型到資料類型的映射
    TYPE_MAPPING = {
        'textfield': 'string',
        'textarea': 'string',
        'number': 'number',
        'password': 'string',
        'email': 'string',
        'phoneNumber': 'string',
        'url': 'string',
        'currency': 'number',
        'checkbox': 'boolean',
        'selectboxes': 'object',
        'select': 'string',
        'radio': 'string',
        'datetime': 'datetime',
        'day': 'string',
        'time': 'string',
        'date': 'date',
        'hidden': 'string',
        'signature': 'string',
        'file': 'array',
        'tags': 'array',
        'address': 'object',
        'datagrid': 'array',
        'editgrid': 'array',
        'survey': 'object',
    }

    # 布局類型 (不產生資料欄位)
    LAYOUT_TYPES = {
        'button', 'htmlelement', 'content', 'well', 'fieldset',
        'panel', 'table', 'tabs', 'columns', 'container'
    }

    for component in components:
        comp_type = component.get('type', '')
        comp_key = component.get('key', '')

        # 跳過無 key 的元件
        if not comp_key:
            continue

        # 跳過按鈕類型
        if comp_type == 'button':
            continue

        # 處理布局容器 - 遞迴處理子元件
        if comp_type in {'panel', 'well', 'fieldset'}:
            sub_components = component.get('components', [])
            if sub_components:
                fields.extend(_extract_form_fields(
                    sub_components,
                    path_prefix,
                    nested_level + 1
                ))
            continue

        if comp_type == 'columns':
            for column in component.get('columns', []):
                sub_components = column.get('components', [])
                if sub_components:
                    fields.extend(_extract_form_fields(
                        sub_components,
                        path_prefix,
                        nested_level + 1
                    ))
            continue

        if comp_type == 'tabs':
            for tab in component.get('components', []):
                sub_components = tab.get('components', [])
                if sub_components:
                    fields.extend(_extract_form_fields(
                        sub_components,
                        path_prefix,
                        nested_level + 1
                    ))
            continue

        if comp_type == 'table':
            for row in component.get('rows', []):
                for cell in row:
                    sub_components = cell.get('components', [])
                    if sub_components:
                        fields.extend(_extract_form_fields(
                            sub_components,
                            path_prefix,
                            nested_level + 1
                        ))
            continue

        if comp_type == 'container':
            sub_components = component.get('components', [])
            if sub_components:
                fields.extend(_extract_form_fields(
                    sub_components,
                    f"{path_prefix}.{comp_key}",
                    nested_level + 1
                ))
            continue

        # 跳過其他布局類型
        if comp_type in LAYOUT_TYPES:
            continue

        # 取得欄位資訊
        field_path = f"{path_prefix}.{comp_key}"
        data_type = TYPE_MAPPING.get(comp_type, 'string')

        # 處理選項 (select, radio, selectboxes)
        options = None
        if comp_type in {'select', 'radio', 'selectboxes'}:
            values = component.get('data', {}).get('values', [])
            if not values:
                values = component.get('values', [])
            if values:
                options = [
                    {'value': v.get('value'), 'label': v.get('label')}
                    for v in values
                ]
            if comp_type == 'select' and component.get('multiple'):
                data_type = 'array'

        # 取得預設值
        default_value = component.get('defaultValue')

        # 取得驗證資訊
        validate = component.get('validate', {})
        required = validate.get('required', False)

        field_info = {
            'key': comp_key,
            'label': component.get('label', comp_key),
            'type': comp_type,
            'data_type': data_type,
            'default_value': default_value,
            'options': options,
            'required': required,
            'path': field_path,
            'nested_level': nested_level,
            'placeholder': component.get('placeholder', ''),
            'description': component.get('description', ''),
            'tooltip': component.get('tooltip', ''),
        }

        fields.append(field_info)

        # datagrid 和 editgrid 有子元件結構
        if comp_type in {'datagrid', 'editgrid'}:
            sub_components = component.get('components', [])
            if sub_components:
                sub_fields = _extract_form_fields(
                    sub_components,
                    f"{field_path}[*]",
                    nested_level + 1
                )
                for sf in sub_fields:
                    sf['parent_grid'] = comp_key
                fields.extend(sub_fields)

    return fields
