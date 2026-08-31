"""
FormWorkflow Module - Workflows API
工作流程設計器 API

提供與 A6 相容的 API 端點，支援流程設計器前端。
"""
import secrets
from datetime import datetime
from flask import Blueprint, jsonify, request
from flask_login import current_user

from app.security.decorators import module_access_required, page_keys_required
from app.platform.auth import (
    has_permission,
    require_permission,
)
from app.platform.data import get_current_org, get_current_org_code
from app import db, csrf
from flask_babel import gettext as _

from ..services.node_grant_service import (
    allowed_restricted_types,
    find_unauthorized_node_types,
)

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
                "icon": "/bp/static/modules/form_workflow/icons/workflow/start.svg",
                "config": {},
                "description": "",
                "position": {"x": -175, "y": -50}
            },
            {
                "id": "node-End",
                "label": "結束",
                "type": "End",
                "icon": "/bp/static/modules/form_workflow/icons/workflow/end.svg",
                "config": {},
                "description": "",
                "position": {"x": 875, "y": 350}
            }
        ],
        "edges": [],
        "relayPoints": []
    }


def _find_duplicate_subflow_name(org_secure_code, name, parent_secure_code, exclude_id=None):
    """回傳同範圍內已存在的同名子流程（沒有則 None）

    子流程清單與樹系圖只顯示 name，同名等於使用者無法辨識自己在編輯哪一個，
    所以在建立與改名時擋下。比對範圍：
      - 專屬子流程：同一父流程底下
      - 通用子流程：同企業的所有通用子流程（清單就是這個範圍）
    跨父流程同名是合理的（不同流程樹各有一個「通知」子流程），
    因此不加 DB 唯一約束，只在這兩個入口擋。
    """
    from ..models import FwWorkflowTemplate

    query = FwWorkflowTemplate.query.filter(
        FwWorkflowTemplate.org_secure_code == org_secure_code,
        FwWorkflowTemplate.is_subprocess == True,  # noqa: E712
        FwWorkflowTemplate.is_deleted == False,    # noqa: E712
        FwWorkflowTemplate.name == name,
    )
    if parent_secure_code:
        query = query.filter(
            FwWorkflowTemplate.parent_workflow_secure_code == parent_secure_code
        )
    else:
        query = query.filter(
            FwWorkflowTemplate.parent_workflow_secure_code.is_(None)
        )
    if exclude_id is not None:
        query = query.filter(FwWorkflowTemplate.id != exclude_id)

    return query.first()


def _duplicate_subflow_name_response(name, parent_secure_code):
    if parent_secure_code:
        message = _('同一主流程下已有名為「%(name)s」的子流程，請換一個名稱', name=name)
    else:
        message = _('已有名為「%(name)s」的通用子流程，請換一個名稱', name=name)
    return jsonify({'success': False, 'error': message}), 409


def _reject_unauthorized_graph_nodes(graph, org):
    unauthorized = find_unauthorized_node_types(
        graph,
        org.secure_code if org else None,
    )
    if unauthorized:
        return jsonify({
            'success': False,
            'error': _('流程中含有本企業未獲授權的節點型別：%(types)s',
                       types=', '.join(unauthorized))
        }), 403
    return None




# =============================================================================
# 數據 API
# =============================================================================
# （原本此處有 /list 與 /designer 兩支回 HTML 的頁面路由，2026-09-01 PF-145 施工4
#   移除：與 form_workflow_web.workflows / workflow_detail 重複，且 /api/ 前綴
#   在 PageRoleGuard.SKIP_PREFIXES 內，結構上不可能被雙鑰匙保護。）

@workflows_bp.route('/data/templates')
@module_access_required('form_workflow')
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

    # flow_type 篩選：main=主流程, subflow=子流程, 不傳=全部
    # 保留 include_subprocess 向下相容
    flow_type = request.args.get('flow_type', '').strip().lower()
    if flow_type == 'main':
        query = query.filter(FwWorkflowTemplate.is_subprocess == False)
    elif flow_type == 'subflow':
        query = query.filter(FwWorkflowTemplate.is_subprocess == True)
    else:
        include_subprocess = request.args.get('include_subprocess', 'false').lower() == 'true'
        if not include_subprocess:
            query = query.filter(FwWorkflowTemplate.is_subprocess == False)

    templates = query.order_by(FwWorkflowTemplate.updated_at.desc()).all()

    return jsonify({
        'success': True,
        'templates': [t.to_dict(include_graph=False) for t in templates]
    })


@workflows_bp.route('/data/templates/<secure_code>')
@module_access_required('form_workflow')
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
@module_access_required('form_workflow')
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

    graph = data.get('graph') or _get_default_graph()
    unauthorized_response = _reject_unauthorized_graph_nodes(graph, org)
    if unauthorized_response:
        return unauthorized_response

    user_name = getattr(current_user, 'display_name', '') or getattr(current_user, 'native_name', '') or ''

    template = FwWorkflowTemplate(
        secure_code=secrets.token_urlsafe(16),
        org_secure_code=org.secure_code,
        name=name,
        code=code,
        description=data.get('description', ''),
        graph=graph,
        cytoscape_config=data.get('cytoscape_config') or _get_default_graph(),
        is_active=data.get('is_active', True),
        is_subprocess=data.get('is_subprocess', False),
        owner_secure_code=current_user.secure_code,
        created_by_secure_code=current_user.secure_code,
        created_by_name=user_name,
        updated_by_secure_code=current_user.secure_code,
        updated_by_name=user_name,
    )

    db.session.add(template)
    db.session.commit()

    return jsonify({
        'success': True,
        'secure_code': template.secure_code,
        **template.to_dict(include_graph=True),
        'message': _('流程模板已建立')
    })


@workflows_bp.route('/data/templates/<secure_code>', methods=['PUT'])
@csrf.exempt
@module_access_required('form_workflow')
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

    if 'graph' in data:
        unauthorized_response = _reject_unauthorized_graph_nodes(data['graph'], org)
        if unauthorized_response:
            return unauthorized_response

    # 記錄舊的 revision（用於判斷是否首次儲存）
    old_revision = template.revision or 0

    if 'name' in data:
        new_name = (data['name'] or '').strip()
        if template.is_subprocess and new_name and new_name != template.name:
            if _find_duplicate_subflow_name(
                org.secure_code,
                new_name,
                template.parent_workflow_secure_code,
                exclude_id=template.id,
            ):
                return _duplicate_subflow_name_response(
                    new_name, template.parent_workflow_secure_code
                )
        template.name = new_name
    if 'description' in data:
        template.description = data['description']
    if 'graph' in data:
        template.graph = data['graph']
    if 'cytoscape_config' in data:
        template.cytoscape_config = data['cytoscape_config']
    if 'category_secure_code' in data:
        template.category_secure_code = data['category_secure_code']
        # 同步更新舊 category 字串（過渡期）
        from ..models import FwCategory
        cat = FwCategory.query.filter_by(
            secure_code=data['category_secure_code'], is_deleted=False
        ).first()
        if cat and cat.parent_secure_code:
            parent = FwCategory.query.filter_by(
                secure_code=cat.parent_secure_code, is_deleted=False
            ).first()
            template.category = parent.name if parent else cat.name
        elif cat:
            template.category = cat.name
    elif 'category' in data:
        template.category = data['category']
    if 'is_active' in data:
        template.is_active = data['is_active']

    # 縮圖
    if 'thumbnail_2x1' in data:
        template.thumbnail_2x1 = data['thumbnail_2x1']

    # 有內容變更時遞增 revision
    if data.get('graph') or data.get('cytoscape_config'):
        template.revision = (template.revision or 0) + 1

    # 更新最後編輯者
    user_name = getattr(current_user, 'display_name', '') or getattr(current_user, 'native_name', '') or ''
    template.updated_by_secure_code = current_user.secure_code
    template.updated_by_name = user_name

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
            form_category = template.category if hasattr(template, 'category') and template.category else '流程記錄'

            form_template = FwFormTemplate(
                secure_code=secrets.token_urlsafe(16),
                org_secure_code=org.secure_code,
                code=form_code,
                name=template.name,
                version='AA',
                description=f'{template.name} 流程記錄單',
                category=form_category,
                category_secure_code='SYS_CAT_WORKFLOW_REC',
                schema={
                    "components": [
                        {
                            "type": "htmlelement",
                            "tag": "h3",
                            "attrs": [{"attr": "style", "value": "text-align:center; margin:0 0 0.5rem 0;"}],
                            "content": template.name,
                            "key": "formTitle",
                            "input": False,
                            "tableView": False
                        },
                    ],
                    "display": "form"
                },
                is_active=True,
                is_published=False,
                owner_secure_code=current_user.secure_code,
                created_by_secure_code=current_user.secure_code,
                created_by_name=user_name,
                updated_by_secure_code=current_user.secure_code,
                updated_by_name=user_name,
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

    # 自動建立的表單 → 背景生成縮圖
    if auto_created_form and auto_created_form.schema:
        try:
            from ..services.thumbnail_service import generate_form_thumbnails_async, is_available
            if is_available():
                from flask import current_app
                generate_form_thumbnails_async(
                    current_app._get_current_object(),
                    auto_created_form.id,
                    auto_created_form.schema,
                    auto_created_form.name
                )
        except Exception as e:
            print(f"[thumbnail] 自動建立表單縮圖觸發失敗: {e}")

    # 建立回應
    response_data = {
        'success': True,
        **template.to_dict(include_graph=True),
        'message': _('流程模板已更新')
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
        response_data['message'] = _('流程模板已更新，並自動建立表單「%(name)s」及配對', name=auto_created_form.name)

    return jsonify(response_data)


@workflows_bp.route('/data/templates/<secure_code>', methods=['DELETE'])
@csrf.exempt
@module_access_required('form_workflow')
def delete_template(secure_code):
    """刪除流程模板（軟刪除）

    刪除邏輯：
    - 遞迴軟刪除所有專屬子流程（有 parent_workflow_secure_code 的）
    - 連帶軟刪除相關的表單-流程配對（fw_form_workflow_mappings）
    - 通用子流程（parent_workflow_secure_code 為 NULL）不受影響
    - 已發行版本（有快照）和歷史實例保留不動
    - 若有運行中的流程實例則阻擋刪除
    """
    from ..models import (
        FwWorkflowTemplate, FwWorkflowInstance, FwFormWorkflowMapping
    )

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

    # 遞迴收集所有專屬子流程（BFS）
    exclusive_subflows = []
    queue = [template.secure_code]
    visited = {template.secure_code}
    while queue:
        parent_code = queue.pop(0)
        children = FwWorkflowTemplate.query.filter_by(
            parent_workflow_secure_code=parent_code,
            org_secure_code=org.secure_code,
            is_deleted=False
        ).all()
        for child in children:
            if child.secure_code not in visited:
                visited.add(child.secure_code)
                exclusive_subflows.append(child)
                queue.append(child.secure_code)

    # 要刪除的所有 secure_code（主流程 + 專屬子流程）
    all_codes = [template.secure_code] + [sf.secure_code for sf in exclusive_subflows]

    # 檢查是否有運行中的流程實例
    running_count = FwWorkflowInstance.query.filter(
        FwWorkflowInstance.workflow_template_secure_code.in_(all_codes),
        FwWorkflowInstance.org_secure_code == org.secure_code,
        FwWorkflowInstance.status.in_(['PENDING', 'RUNNING']),
        FwWorkflowInstance.is_deleted == False
    ).count()

    if running_count > 0:
        return jsonify({
            'success': False,
            'error': _('無法刪除：尚有 %(count)s 個運行中的流程實例', count=running_count)
        }), 409

    now = datetime.utcnow()

    # 軟刪除主流程
    template.is_deleted = True
    template.updated_at = now

    # 軟刪除所有專屬子流程
    for sf in exclusive_subflows:
        sf.is_deleted = True
        sf.updated_at = now

    # 軟刪除相關的表單-流程配對
    related_mappings = FwFormWorkflowMapping.query.filter(
        FwFormWorkflowMapping.workflow_template_secure_code.in_(all_codes),
        FwFormWorkflowMapping.org_secure_code == org.secure_code,
        FwFormWorkflowMapping.is_deleted == False
    ).all()
    for mapping in related_mappings:
        mapping.is_deleted = True
        mapping.updated_at = now

    db.session.commit()

    deleted_names = [template.name] + [sf.name for sf in exclusive_subflows]
    mapping_count = len(related_mappings)

    return jsonify({
        'success': True,
        'message': _('流程模板已刪除'),
        'details': {
            'deleted_workflows': deleted_names,
            'deleted_mappings': mapping_count
        }
    })


@workflows_bp.route('/data/templates/<secure_code>/save-new-version', methods=['POST'])
@csrf.exempt
@module_access_required('form_workflow')
def save_new_version(secure_code):
    """另存新版：複製目前流程為新記錄，版本號遞增"""
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
    graph = data.get('graph') or template.graph
    unauthorized_response = _reject_unauthorized_graph_nodes(graph, org)
    if unauthorized_response:
        return unauthorized_response

    # 遞增版本號
    current_version = template.version or 'AA'
    if len(current_version) >= 2:
        first, second = current_version[0], current_version[1]
        if second == 'Z':
            new_version = chr(ord(first) + 1) + 'A'
        else:
            new_version = first + chr(ord(second) + 1)
    else:
        new_version = 'AB'

    # 建立新記錄（複製原流程）
    new_template = FwWorkflowTemplate(
        secure_code=secrets.token_urlsafe(16),
        org_secure_code=org.secure_code,
        code=template.code,
        # 另存新版刻意沿用同名（靠 version 區分），不做 _find_duplicate_subflow_name 檢查
        name=data.get('name') or template.name,
        description=data.get('description') or template.description,
        category=template.category,
        category_secure_code=template.category_secure_code,
        graph=graph,
        cytoscape_config=data.get('cytoscape_config') or template.cytoscape_config,
        version=new_version,
        revision=1,
        is_active=True,
        is_published=False,
        is_subprocess=template.is_subprocess,
        parent_workflow_secure_code=template.parent_workflow_secure_code,
        parent_workflow_id=template.parent_workflow_id,
        form_template_secure_code=template.form_template_secure_code,
        permission_type=template.permission_type,
        owner_secure_code=current_user.secure_code,
    )

    db.session.add(new_template)
    db.session.flush()  # 取得 new_template.id（mapping FK 需要）

    # 複製表單-流程配對關係
    mappings = FwFormWorkflowMapping.query.filter_by(
        workflow_template_secure_code=template.secure_code,
        org_secure_code=org.secure_code,
        is_deleted=False
    ).all()

    for m in mappings:
        new_mapping = FwFormWorkflowMapping(
            secure_code=secrets.token_urlsafe(16),
            org_secure_code=org.secure_code,
            form_template_id=m.form_template_id,
            form_template_secure_code=m.form_template_secure_code,
            form_template_code=m.form_template_code,
            form_template_version=m.form_template_version,
            workflow_template_id=new_template.id,
            workflow_template_secure_code=new_template.secure_code,
            workflow_template_code=new_template.code,
            workflow_template_version=new_version,
            is_active=m.is_active,
            is_published=False
        )
        db.session.add(new_mapping)

    db.session.commit()

    return jsonify({
        'success': True,
        'data': new_template.to_dict(include_graph=True),
        'message': _('已另存新版本 %(version)s', version=new_version)
    })


# =============================================================================
# 節點定義 API
# =============================================================================

@workflows_bp.route('/data/node-definitions')
@module_access_required('form_workflow')
def get_node_definitions():
    """
    取得節點定義列表（按分類分組）- 從 DB 查詢

    過濾邏輯：
    - Start 節點不出現在面板（由系統自動建立，一個流程只能有一個起點）
    - org_restricted=True 的節點只有獲授權的企業可見
    """
    from ..models import WorkflowNodeDefinition

    definitions = WorkflowNodeDefinition.query.filter_by(
        is_active=True, is_deleted=False
    ).all()

    org = get_current_org()
    allowed_org_restricted = allowed_restricted_types(
        org.secure_code if org else None,
    )

    # 將節點按分類分組
    category_map = {
        '基本': 'basic',
        '表單': 'form',
        '通知': 'notification',
        '控制': 'flow_control',
        '變數': 'data',
        '操作': 'operation',
        '整合': 'integration',
        '安全': 'security',
        '資安處置': 'security_ops',
        '系統': 'system_admin',
    }

    grouped = {}
    for node_def in definitions:
        # 隱藏 Start 節點（由系統自動建立，避免用戶重複拖放）
        if node_def.node_type == 'Start':
            continue

        if node_def.org_restricted and node_def.node_type not in allowed_org_restricted:
            continue

        category_key = category_map.get(node_def.category, 'basic')

        if category_key not in grouped:
            grouped[category_key] = []

        # DB 存前綴無關路徑（/static/...），回傳時補上部署前綴
        icon = node_def.icon or ''
        if icon.startswith('/static/'):
            icon = request.script_root + icon

        grouped[category_key].append({
            'type': node_def.node_type,
            'label': f'{node_def.display_name} ({node_def.node_type})',
            'icon': icon,
            'description': node_def.description or ''
        })

    return jsonify({
        'success': True,
        'data': grouped
    })


@workflows_bp.route('/data/sql-procedures')
@module_access_required('form_workflow')
def get_sql_procedures():
    """
    取得 SqlExecutor 節點可用的預存程序白名單（設計器下拉用）

    只回傳全平台共用（org_secure_code 為 NULL）與本企業專屬的登錄項目。
    回應刻意不含 function_name —— 那是內部細節，設計器用穩定識別碼 code 就夠；
    handler 執行時也是拿 code 重查白名單，不吃前端送來的函式名。

    參數清單已在 model 端濾掉 p_org_secure_code：企業識別碼由 handler 從流程
    所屬企業強制帶入，設計者不該看到也不該能填。
    """
    from sqlalchemy import or_
    from ..models import FwSqlProcedure

    org_code = get_current_org_code()

    procedures = FwSqlProcedure.query.filter(
        FwSqlProcedure.is_active.is_(True),
        FwSqlProcedure.is_deleted.is_(False),
        or_(FwSqlProcedure.org_secure_code.is_(None),
            FwSqlProcedure.org_secure_code == org_code),
    ).order_by(FwSqlProcedure.display_name).all()

    return jsonify({
        'success': True,
        'data': [p.to_designer_dict() for p in procedures]
    })


@workflows_bp.route('/nodes/<node_type>/schema')
@module_access_required('form_workflow')
def get_node_schema(node_type):
    """取得節點的配置 schema - 從 DB 查詢"""
    from sqlalchemy import func
    from ..models import WorkflowNodeDefinition

    node_def = WorkflowNodeDefinition.query.filter(
        func.lower(WorkflowNodeDefinition.node_type) == node_type.lower(),
        WorkflowNodeDefinition.is_deleted == False
    ).first()

    if node_def:
        return jsonify({
            'success': True,
            'schema': node_def.config_schema or {}
        })

    return jsonify({
        'success': False,
        'error': f'Node type {node_type} not found'
    }), 404


# =============================================================================
# 子流程 API
# =============================================================================

@workflows_bp.route('/data/subflows/available')
@module_access_required('form_workflow')
def list_available_subflows():
    """取得可用的子流程列表（分區結構）

    回傳：
    - dedicated: 同一根主流程下的專屬子流程（含 is_referenced 標記）
    - common_categories: 通用子流程按 category 分組
    """
    from ..models import FwWorkflowTemplate
    from sqlalchemy import or_
    from collections import OrderedDict

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    parent_id = request.args.get('parent_id')  # 當前流程的 secure_code

    # 追溯到最頂端主流程
    root_code = parent_id
    if parent_id:
        visited = set()
        current = parent_id
        for _hop in range(10):
            if current in visited:
                break
            visited.add(current)
            wf = FwWorkflowTemplate.query.filter_by(
                secure_code=current,
                org_secure_code=org.secure_code,
                is_deleted=False
            ).first()
            if not wf or not wf.parent_workflow_secure_code:
                root_code = current
                break
            current = wf.parent_workflow_secure_code
        else:
            root_code = current

    # 收集同一根主流程下所有流程的 secure_code（遞迴向下）+ 載入 graph
    family_codes = set()
    family_workflows = []  # 儲存所有家族流程物件
    if root_code:
        family_codes.add(root_code)
        root_wf = FwWorkflowTemplate.query.filter_by(
            secure_code=root_code,
            org_secure_code=org.secure_code,
            is_deleted=False
        ).first()
        if root_wf:
            family_workflows.append(root_wf)
        queue = [root_code]
        while queue:
            code = queue.pop(0)
            children = FwWorkflowTemplate.query.filter_by(
                parent_workflow_secure_code=code,
                org_secure_code=org.secure_code,
                is_deleted=False
            ).all()
            for child in children:
                if child.secure_code not in family_codes:
                    family_codes.add(child.secure_code)
                    family_workflows.append(child)
                    queue.append(child.secure_code)

    # 掃描家族所有流程的 graph，收集被引用的 childFlowId（用 code 比對）
    referenced_codes = set()
    for wf in family_workflows:
        graph = wf.graph or {}
        for node in graph.get('nodes', []):
            config = node.get('config') or {}
            child_flow_id = config.get('childFlowId')
            if child_flow_id:
                referenced_codes.add(child_flow_id)

    # 查詢專屬子流程（同家族）
    dedicated_subflows = []
    if family_codes:
        dedicated_subflows = FwWorkflowTemplate.query.filter(
            FwWorkflowTemplate.org_secure_code == org.secure_code,
            FwWorkflowTemplate.is_subprocess == True,
            FwWorkflowTemplate.is_deleted == False,
            FwWorkflowTemplate.parent_workflow_secure_code.in_(family_codes)
        ).order_by(FwWorkflowTemplate.name).all()

    # 查詢通用子流程（無 parent）
    common_subflows = FwWorkflowTemplate.query.filter(
        FwWorkflowTemplate.org_secure_code == org.secure_code,
        FwWorkflowTemplate.is_subprocess == True,
        FwWorkflowTemplate.is_deleted == False,
        FwWorkflowTemplate.parent_workflow_secure_code == None
    ).order_by(FwWorkflowTemplate.category, FwWorkflowTemplate.name).all()

    # 專屬子流程回傳
    dedicated_data = [
        {
            'secure_code': sf.secure_code,
            'code': sf.code,
            'name': sf.name,
            'description': sf.description,
            'is_referenced': sf.code in referenced_codes
        }
        for sf in dedicated_subflows
    ]

    # 預載分類名稱對照表（透過 category_secure_code 查 FwCategory）
    from ..models import FwCategory
    cat_codes = {sf.category_secure_code for sf in common_subflows if sf.category_secure_code}
    cat_name_map = {}
    if cat_codes:
        cats = FwCategory.query.filter(
            FwCategory.secure_code.in_(cat_codes),
            FwCategory.is_deleted == False
        ).all()
        # 建立 secure_code → FwCategory 物件的映射
        cat_obj_map = {c.secure_code: c for c in cats}
        # 收集所有 parent_secure_code 以便查詢父分類名稱
        parent_codes = {c.parent_secure_code for c in cats if c.parent_secure_code}
        parent_codes -= cat_codes  # 排除已查過的
        if parent_codes:
            parent_cats = FwCategory.query.filter(
                FwCategory.secure_code.in_(parent_codes),
                FwCategory.is_deleted == False
            ).all()
            for pc in parent_cats:
                cat_obj_map[pc.secure_code] = pc
        # 組合分類名稱（二層：parent > child，一層：直接用名稱）
        for sc, cat in cat_obj_map.items():
            if sc not in cat_codes:
                continue
            if cat.parent_secure_code and cat.parent_secure_code in cat_obj_map:
                cat_name_map[sc] = f'{cat_obj_map[cat.parent_secure_code].name} > {cat.name}'
            else:
                cat_name_map[sc] = cat.name

    # 通用子流程按分類分組
    category_map = OrderedDict()
    for sf in common_subflows:
        cat_name = cat_name_map.get(sf.category_secure_code, '其他')
        if cat_name not in category_map:
            category_map[cat_name] = []
        category_map[cat_name].append({
            'secure_code': sf.secure_code,
            'code': sf.code,
            'name': sf.name,
            'description': sf.description
        })

    common_categories = [
        {'category_name': cat_name, 'subflows': subflows}
        for cat_name, subflows in category_map.items()
    ]

    return jsonify({
        'success': True,
        'data': {
            'dedicated': dedicated_data,
            'common_categories': common_categories
        }
    })


@workflows_bp.route('/data/subflows/create', methods=['POST'])
@csrf.exempt
@module_access_required('form_workflow')
def create_subflow():
    """建立子流程"""
    from ..models import FwWorkflowTemplate

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    data = request.get_json() or {}
    name = data.get('name', '').strip()
    parent_id = data.get('parent_id')  # secure_code of parent workflow

    if not name:
        return jsonify({'success': False, 'error': 'Name is required'}), 400

    if _find_duplicate_subflow_name(org.secure_code, name, parent_id):
        return _duplicate_subflow_name_response(name, parent_id)

    graph = data.get('graph') or _get_default_graph()
    unauthorized_response = _reject_unauthorized_graph_nodes(graph, org)
    if unauthorized_response:
        return unauthorized_response

    code = f'SF{secrets.token_hex(4).upper()}'

    # 如果有 parent_id（secure_code），查詢實際的數值 ID
    parent_workflow_id = None
    if parent_id:
        parent_wf = FwWorkflowTemplate.query.filter_by(
            secure_code=parent_id,
            org_secure_code=org.secure_code,
            is_deleted=False
        ).first()
        if parent_wf:
            parent_workflow_id = parent_wf.id

    subflow = FwWorkflowTemplate(
        secure_code=secrets.token_urlsafe(16),
        org_secure_code=org.secure_code,
        name=name,
        code=code,
        description=data.get('description', ''),
        graph=graph,
        cytoscape_config=data.get('cytoscape_config') or _get_default_graph(),
        is_active=True,
        is_subprocess=True,
        parent_workflow_secure_code=parent_id,
        parent_workflow_id=parent_workflow_id,
        owner_secure_code=current_user.secure_code
    )

    db.session.add(subflow)
    db.session.commit()

    return jsonify({
        'success': True,
        'data': {
            'secure_code': subflow.secure_code,
            'code': subflow.code,
            'name': subflow.name,
            'description': subflow.description,
        },
        'message': _('子流程已建立')
    })


@workflows_bp.route('/data/subflows/<secure_code>', methods=['DELETE'])
@csrf.exempt
@module_access_required('form_workflow')
@page_keys_required('form_workflow.workflows')
def delete_subflow(secure_code):
    """刪除專屬子流程

    只能刪除專屬子流程（有 parent_workflow_secure_code 的）。
    若被家族其他流程的 graph 引用則回 409。
    遞迴軟刪除其下層專屬子流程。
    """
    from ..models import FwWorkflowTemplate

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    subflow = FwWorkflowTemplate.query.filter_by(
        secure_code=secure_code,
        org_secure_code=org.secure_code,
        is_deleted=False
    ).first()

    if not subflow:
        return jsonify({'success': False, 'error': _('找不到子流程')}), 404

    # 只能刪專屬子流程
    if not subflow.parent_workflow_secure_code:
        return jsonify({'success': False, 'error': _('無法刪除通用子流程')}), 403

    # 追溯到根主流程，收集整個家族
    root_code = subflow.parent_workflow_secure_code
    visited = set()
    current = root_code
    for _hop in range(10):
        if current in visited:
            break
        visited.add(current)
        wf = FwWorkflowTemplate.query.filter_by(
            secure_code=current,
            org_secure_code=org.secure_code,
            is_deleted=False
        ).first()
        if not wf or not wf.parent_workflow_secure_code:
            root_code = current
            break
        current = wf.parent_workflow_secure_code

    # BFS 收集家族所有流程
    family_codes = {root_code}
    family_workflows = []
    root_wf = FwWorkflowTemplate.query.filter_by(
        secure_code=root_code,
        org_secure_code=org.secure_code,
        is_deleted=False
    ).first()
    if root_wf:
        family_workflows.append(root_wf)
    queue = [root_code]
    while queue:
        code = queue.pop(0)
        children = FwWorkflowTemplate.query.filter_by(
            parent_workflow_secure_code=code,
            org_secure_code=org.secure_code,
            is_deleted=False
        ).all()
        for child in children:
            if child.secure_code not in family_codes:
                family_codes.add(child.secure_code)
                family_workflows.append(child)
                queue.append(child.secure_code)

    # 檢查此子流程的 code 是否被家族任何流程的 graph 引用
    for wf in family_workflows:
        graph = wf.graph or {}
        for node in graph.get('nodes', []):
            config = node.get('config') or {}
            if config.get('childFlowId') == subflow.code:
                return jsonify({
                    'success': False,
                    'error': _('此子流程正被「%(name)s」引用，無法刪除', name=wf.name)
                }), 409

    # 遞迴收集要刪除的子流程（此子流程 + 其下層專屬子流程）
    to_delete = [subflow]
    del_queue = [subflow.secure_code]
    del_visited = {subflow.secure_code}
    while del_queue:
        parent_code = del_queue.pop(0)
        children = FwWorkflowTemplate.query.filter_by(
            parent_workflow_secure_code=parent_code,
            org_secure_code=org.secure_code,
            is_deleted=False
        ).all()
        for child in children:
            if child.secure_code not in del_visited:
                del_visited.add(child.secure_code)
                to_delete.append(child)
                del_queue.append(child.secure_code)

    # 軟刪除
    deleted_names = []
    for wf in to_delete:
        wf.is_deleted = True
        deleted_names.append(wf.name)

    db.session.commit()

    return jsonify({
        'success': True,
        'message': _('已刪除 %(count)s 個子流程', count=len(to_delete)),
        'deleted': deleted_names
    })


# =============================================================================
# 變數映射 API
# =============================================================================

@workflows_bp.route('/data/variable-mapping', methods=['GET', 'POST'])
@csrf.exempt
@module_access_required('form_workflow')
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
                    {'name': 'fi.applicant', 'type': 'string', 'description': '申請人姓名'},
                    {'name': 'fi.applicant_dept', 'type': 'string', 'description': '申請人部門'},
                    {'name': 'fi.applicant_email', 'type': 'string', 'description': '申請人信箱'},
                    {'name': 'fi.serial', 'type': 'string', 'description': '表單編號'},
                    {'name': 'fi.name', 'type': 'string', 'description': '表單名稱'},
                    {'name': 'fi.subject', 'type': 'string', 'description': '表單主旨'},
                    {'name': 'fi.status', 'type': 'string', 'description': '表單狀態'},
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
        return jsonify({'success': False, 'message': _('建立變數映射失敗: %(error)s', error=str(e))}), 500


# =============================================================================
# 組織樹 API（用於選擇簽核人）
# =============================================================================

@workflows_bp.route('/data/org-tree')
@module_access_required('form_workflow')
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
@module_access_required('form_workflow')
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
@module_access_required('form_workflow')
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
            return jsonify({'success': False, 'message': _('流程不存在')}), 404

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
        return jsonify({'success': False, 'message': _('取得配對表單失敗: %(error)s', error=str(e))}), 500


@workflows_bp.route('/data/forms/<form_id>/fields', methods=['GET'])
@module_access_required('form_workflow')
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
            return jsonify({'success': False, 'message': _('表單不存在')}), 404

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
        return jsonify({'success': False, 'message': _('分析表單欄位失敗: %(error)s', error=str(e))}), 500


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


# =============================================================================
# 廣播節點輔助 API（用於 AlertBroadcast 目標選擇）
# =============================================================================

@workflows_bp.route('/data/org-roles')
@module_access_required('form_workflow')
def get_org_roles():
    """取得企業角色列表（用於廣播目標選擇）"""
    from app.models import Role

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    roles = Role.query.filter_by(
        org_secure_code=org.secure_code,
        is_active=True,
        is_deleted=False
    ).order_by(Role.name).all()

    return jsonify({
        'success': True,
        'roles': [{'secure_code': r.secure_code, 'code': r.code, 'name': r.name} for r in roles]
    })


@workflows_bp.route('/data/org-departments')
@module_access_required('form_workflow')
def get_org_departments():
    """取得企業部門列表（用於廣播目標選擇）"""
    from app.models.organizational_unit import OrganizationalUnit, UnitType

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    departments = OrganizationalUnit.query.filter_by(
        org_secure_code=org.secure_code,
        unit_type=UnitType.DEPARTMENT,
        is_active=True,
        is_deleted=False
    ).order_by(OrganizationalUnit.sort_order.asc()).all()

    return jsonify({
        'success': True,
        'departments': [{
            'secure_code': d.secure_code,
            'code': d.code,
            'name': d.name,
            'full_path': d.full_path,
        } for d in departments]
    })


@workflows_bp.route('/data/org-api-keys')
@module_access_required('form_workflow')
def get_org_api_keys():
    """取得企業 API Key 清單（用於 ApiKeyAction 節點選擇處置對象；不含 secret）"""
    from app.services import api_key_service

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'error': 'Organization not found'}), 400

    keys = api_key_service.list_keys(org.secure_code)
    return jsonify({
        'success': True,
        'keys': [{
            'key_id': k.key_id,
            'name': k.name,
            'status': k.status,
            'consumer_label': k.consumer_label,
        } for k in keys]
    })
