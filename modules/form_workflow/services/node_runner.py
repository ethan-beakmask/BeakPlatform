"""
FormWorkflow Module - Node Runner
節點執行器 CLI 入口點

此腳本作為獨立程序執行，由 WorkflowExecutor 透過 subprocess 啟動。

用法：
    python -m modules.form_workflow.services.node_runner --queue-item-code <code>
"""
import os
import sys
import argparse
import logging
from datetime import datetime, timedelta

# 設定 logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] [PID:%(process)d] %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """主程式入口"""
    parser = argparse.ArgumentParser(description='Node Runner - 執行單一節點')
    parser.add_argument('--queue-item-code', type=str, required=True,
                       help='FwNodeExecutionQueue secure_code')
    args = parser.parse_args()

    queue_item_code = args.queue_item_code
    logger.info(f'Node Runner 啟動，queue_item_code={queue_item_code}, PID={os.getpid()}')

    # 動態偵測專案路徑
    _project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
    sys.path.insert(0, os.path.join(_project_root, 'backend'))

    # 初始化 Flask app context
    from app import create_app, db
    app = create_app()

    with app.app_context():
        try:
            # 取得 queue_item
            from modules.form_workflow.models import FwNodeExecutionQueue
            queue_item = FwNodeExecutionQueue.query.filter_by(
                secure_code=queue_item_code
            ).first()

            if not queue_item:
                logger.error(f'找不到 queue_item: {queue_item_code}')
                sys.exit(1)

            logger.info(f'執行節點: {queue_item.node_type} ({queue_item.node_id})')

            # 執行 handler
            result = execute_handler(queue_item)

            # 更新結果
            update_result(queue_item, result)

            logger.info(f'節點執行完成: {result.get("status")}')

        except Exception as e:
            logger.error(f'節點執行失敗: {str(e)}', exc_info=True)
            try:
                handle_error(queue_item_code, str(e))
            except:
                pass
            sys.exit(1)


def execute_handler(queue_item):
    """
    執行對應的 handler

    Args:
        queue_item: FwNodeExecutionQueue 實例

    Returns:
        dict: 執行結果
    """
    from modules.form_workflow.services.node_handlers.factory import NodeHandlerFactory

    node_type = queue_item.node_type

    # 使用工廠建立處理器
    handler = NodeHandlerFactory.create(queue_item)

    # 驗證配置
    handler.validate()

    # 執行處理
    return handler.handle()


def update_result(queue_item, result):
    """
    更新執行結果

    Args:
        queue_item: FwNodeExecutionQueue 實例
        result: 執行結果 dict
    """
    from app import db
    from modules.form_workflow.services.workflow_engine import WorkflowEngine

    status = result.get('status')

    if status == 'waiting':
        # 保持 WAITING 狀態
        queue_item.wait()
        queue_item.result = result
        # 如果有 retry_after_seconds，設定下次輪詢時間（用於 strict 模式 End 節點等）
        retry_after = result.get('data', {}).get('retry_after_seconds')
        if retry_after:
            queue_item.scheduled_at = datetime.utcnow() + timedelta(seconds=retry_after)
        db.session.commit()

    elif status == 'pending':
        # 等待條件
        queue_item.status = 'WAITING'
        queue_item.result = result
        db.session.commit()

    elif status == 'waiting_form_action':
        # FormAdapter 等待簽核（特殊狀態）
        queue_item.status = 'WAITING'
        queue_item.result = result
        db.session.commit()
        logger.info(f'FormAdapter 進入等待簽核狀態')

    elif status == 'waiting_subflow':
        # SubFlow 節點等待子流程完成（由子流程 End handler 喚醒）
        queue_item.wait()
        queue_item.result = result
        db.session.commit()
        logger.info(f'SubFlow 節點進入等待狀態，child={result.get("data", {}).get("child_instance_code")}')

    elif status == 'success':
        # 執行完成
        queue_item.success(result)
        db.session.commit()

        # 清除 NODE scope 變數（節點完成，臨時變數不再需要）
        _cleanup_node_vars(queue_item)

        # 推進到下一個節點
        advance_to_next_nodes(queue_item)

    elif status == 'complete_workflow':
        # 完成工作流（End 節點）
        queue_item.success(result)
        db.session.commit()

        # 清除 NODE scope 變數
        _cleanup_node_vars(queue_item)

        finish_mode = result.get('data', {}).get('finish_mode', 'detach')
        has_failures = result.get('data', {}).get('has_failures', False)

        # cancel 模式：主動取消所有未完成節點
        if finish_mode == 'cancel':
            WorkflowEngine.cancel_pending_nodes(
                queue_item.workflow_instance_secure_code,
                exclude_queue_item_id=queue_item.id
            )

        # strict 模式且有節點失敗 → 標記為 FAILED
        wf_status = 'FAILED' if (finish_mode == 'strict' and has_failures) else 'COMPLETED'

        WorkflowEngine.complete_workflow(
            queue_item.workflow_instance_secure_code,
            status=wf_status,
            end_message=result.get('message')
        )

    else:
        # 其他狀態視為錯誤
        queue_item.fail(result.get('message', 'Unknown error'))
        db.session.commit()


def _cleanup_node_vars(queue_item):
    """
    清除節點的 NODE scope 變數

    節點完成後呼叫，移除該節點產生的臨時變數。
    失敗時僅記錄警告，不中斷流程推進。
    """
    try:
        from modules.form_workflow.services.variable_service import VariableService
        count = VariableService.cleanup_node_vars(
            queue_item.workflow_instance_secure_code,
            queue_item.node_id
        )
        if count > 0:
            logger.info(f'已清除節點 {queue_item.node_id} 的 {count} 個 NODE 變數')
    except Exception as e:
        logger.warning(f'清除 NODE 變數失敗（不影響流程）: {e}')


def advance_to_next_nodes(queue_item):
    """
    推進到下一個節點

    解析路徑選擇：
    - selected_edges (list): Branch 節點產出，逐條 edge 推進
    - selected_edge (str): ParallelJoin 逾時等單一 edge 選擇
    - 皆無: fallback 取所有出邊

    Args:
        queue_item: 當前完成的佇列項目
    """
    from modules.form_workflow.services.workflow_engine import WorkflowEngine

    result = queue_item.result or {}
    result_data = result.get('data', {})
    selected_edges = result_data.get('selected_edges', [])
    selected_edge = result_data.get('selected_edge', '')

    if selected_edges and isinstance(selected_edges, list):
        # Branch 節點：逐條 edge 推進（去重 target node 由 advance_workflow 內部處理）
        for edge_id in selected_edges:
            WorkflowEngine.advance_workflow(
                queue_item.workflow_instance_secure_code,
                queue_item.node_id,
                edge_id
            )
    elif selected_edge and isinstance(selected_edge, str):
        # 單一 edge 選擇（ParallelJoin 逾時等）
        WorkflowEngine.advance_workflow(
            queue_item.workflow_instance_secure_code,
            queue_item.node_id,
            selected_edge
        )
    else:
        # 其他節點 / 無 selected_edges：取所有出邊
        WorkflowEngine.advance_workflow(
            queue_item.workflow_instance_secure_code,
            queue_item.node_id,
            None
        )


def handle_error(queue_item_code, error_message):
    """
    處理執行錯誤

    Args:
        queue_item_code: FwNodeExecutionQueue secure_code
        error_message: 錯誤訊息
    """
    _project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
    sys.path.insert(0, os.path.join(_project_root, 'backend'))

    from app import create_app, db
    from modules.form_workflow.models import FwNodeExecutionQueue, FwWorkflowInstance

    app = create_app()
    with app.app_context():
        queue_item = FwNodeExecutionQueue.query.filter_by(
            secure_code=queue_item_code
        ).first()

        if not queue_item:
            return

        queue_item.fail(error_message)
        db.session.commit()

        # 更新工作流實例狀態
        workflow_instance = FwWorkflowInstance.query.filter_by(
            secure_code=queue_item.workflow_instance_secure_code
        ).first()

        if workflow_instance:
            workflow_instance.status = 'ERROR'
            workflow_instance.error_message = error_message
            db.session.commit()


if __name__ == '__main__':
    main()
