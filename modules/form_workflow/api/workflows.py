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
                "icon": "/static/icons/workflow/start.svg",
                "config": {},
                "description": "",
                "position": {"x": -175, "y": -50}
            },
            {
                "id": "node-End",
                "label": "結束",
                "type": "End",
                "icon": "/static/icons/workflow/end.svg",
                "config": {},
                "description": "",
                "position": {"x": 875, "y": 350}
            }
        ],
        "edges": [],
        "relayPoints": []
    }


def _get_node_definitions():
    """取得節點定義列表"""
    return [
        {
            "node_type": "Start",
            "display_name": "開始",
            "description": "流程的起點",
            "icon": "/static/icons/workflow/start.svg",
            "category": "基本",
            "config_schema": {},
            "is_active": True
        },
        {
            "node_type": "End",
            "display_name": "結束",
            "description": "流程的終點",
            "icon": "/static/icons/workflow/end.svg",
            "category": "基本",
            "config_schema": {},
            "is_active": True
        },
        {
            "node_type": "FormAdapter",
            "display_name": "簽核",
            "description": "表單簽核節點",
            "icon": "/static/icons/workflow/form.svg",
            "category": "表單",
            "config_schema": {
                "assigneeType": "string",
                "assigneeValue": "string",
                "approvalMode": "string"
            },
            "is_active": True
        },
        {
            "node_type": "Delay",
            "display_name": "暫停",
            "description": "延遲執行指定時間",
            "icon": "/static/icons/workflow/delay.svg",
            "category": "控制",
            "config_schema": {
                "delay_seconds": "number"
            },
            "is_active": True
        },
        {
            "node_type": "Branch",
            "display_name": "條件分支",
            "description": "根據條件選擇路徑",
            "icon": "/static/icons/workflow/branch.svg",
            "category": "控制",
            "config_schema": {},
            "is_active": True
        },
        {
            "node_type": "Converge",
            "display_name": "匯合",
            "description": "等待多條路徑匯合",
            "icon": "/static/icons/workflow/converge.svg",
            "category": "控制",
            "config_schema": {
                "mode": "string"
            },
            "is_active": True
        },
        {
            "node_type": "Telegram",
            "display_name": "Telegram 通知",
            "description": "發送 Telegram 訊息",
            "icon": "/static/icons/workflow/telegram.svg",
            "category": "通知",
            "config_schema": {
                "message": "string",
                "chat_id": "string"
            },
            "is_active": True
        },
        {
            "node_type": "EmailAdapter",
            "display_name": "Email 通知",
            "description": "發送 Email",
            "icon": "/static/icons/workflow/email.svg",
            "category": "通知",
            "config_schema": {
                "to": "string",
                "subject": "string",
                "body": "string"
            },
            "is_active": True
        },
        {
            "node_type": "SubFlow",
            "display_name": "子流程",
            "description": "呼叫其他工作流程",
            "icon": "/static/icons/workflow/subflow.svg",
            "category": "控制",
            "config_schema": {
                "childFlowId": "string"
            },
            "is_active": True
        },
        {
            "node_type": "OpSet",
            "display_name": "設定變數",
            "description": "設定流程變數值",
            "icon": "/static/icons/workflow/settings.svg",
            "category": "變數",
            "config_schema": {
                "variables": "array"
            },
            "is_active": True
        },
        {
            "node_type": "OpFieldRead",
            "display_name": "讀取欄位",
            "description": "從表單讀取欄位到變數",
            "icon": "/static/icons/workflow/form-read.svg",
            "category": "變數",
            "config_schema": {
                "mappings": "array"
            },
            "is_active": True
        },
        {
            "node_type": "OpFieldWrite",
            "display_name": "寫入欄位",
            "description": "將變數寫入表單欄位",
            "icon": "/static/icons/workflow/form-write.svg",
            "category": "變數",
            "config_schema": {
                "mappings": "array"
            },
            "is_active": True
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
    if 'is_active' in data:
        template.is_active = data['is_active']

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
    """取得節點定義列表（按分類分組）"""
    definitions = _get_node_definitions()

    # 將節點按分類分組
    category_map = {
        '基本': 'basic',
        '表單': 'form',
        '通知': 'notification',
        '控制': 'flow_control',
        '變數': 'data',
        '操作': 'operation',
        '整合': 'integration',
        '系統': 'system_admin'
    }

    grouped = {}
    for node_def in definitions:
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
    """取得或建立變數映射"""
    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    if request.method == 'GET':
        # 取得變數映射（目前回傳空的結構）
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
    else:
        # POST - 儲存變數映射（目前只回傳成功）
        data = request.get_json() or {}
        return jsonify({
            'success': True,
            'message': '變數映射已儲存'
        })


# =============================================================================
# 組織樹 API（用於選擇簽核人）
# =============================================================================

@workflows_bp.route('/org-tree')
@login_required
def get_org_tree():
    """取得組織架構樹（用於選擇簽核人）"""
    from app.models.department import Department
    from app.models.user import User

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    # 取得部門
    departments = Department.query.filter_by(
        org_secure_code=org.secure_code,
        is_deleted=False
    ).all()

    # 取得用戶
    users = User.query.filter_by(
        org_secure_code=org.secure_code,
        is_active=True
    ).all()

    def build_tree(parent_code=None):
        result = []
        for dept in departments:
            if dept.parent_secure_code == parent_code:
                node = {
                    'id': f'dept_{dept.secure_code}',
                    'text': dept.name,
                    'type': 'department',
                    'secure_code': dept.secure_code,
                    'children': build_tree(dept.secure_code)
                }
                # 添加該部門的用戶
                dept_users = [u for u in users if u.department_secure_code == dept.secure_code]
                for user in dept_users:
                    node['children'].append({
                        'id': f'user_{user.secure_code}',
                        'text': user.display_name or user.username,
                        'type': 'user',
                        'secure_code': user.secure_code
                    })
                result.append(node)
        return result

    tree = build_tree(None)

    return jsonify({
        'success': True,
        'tree': tree
    })
