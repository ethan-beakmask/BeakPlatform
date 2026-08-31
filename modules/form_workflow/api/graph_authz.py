"""
FormWorkflow Module - Graph 寫入授權守門（PF-196 收斂）

所有會把 graph 寫入 fw_workflow_templates（或發行快照）的 API 入口，
在寫入前呼叫 reject_unauthorized_graph_nodes()；批次入口（匯入、批次另存）
逐項用 find_unauthorized_node_types() 判定後以各自的 per-item 格式回報。
唯一判定實作在 node_grant_service.find_unauthorized_node_types()。

2026-09-01 之前這個 helper 在 workflows.py / workflow_routes.py / mappings.py
各有一份一字不差的複本，且 batch_import 完全沒有檢查。
"""
from flask import jsonify
from flask_babel import gettext as _

from ..services.node_grant_service import find_unauthorized_node_types


def reject_unauthorized_graph_nodes(graph, org):
    """graph 含本企業未授權的 restricted 節點時回傳 (403 response)，否則 None。"""
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
