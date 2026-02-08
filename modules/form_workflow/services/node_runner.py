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

    # 加入專案路徑
    sys.path.insert(0, '/opt/BeakPlatform/backend')

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

    elif status == 'success':
        # 執行完成
        queue_item.success(result)
        db.session.commit()

        # 推進到下一個節點
        advance_to_next_nodes(queue_item)

    elif status == 'complete_workflow':
        # 完成工作流（End 節點）
        queue_item.success(result)
        db.session.commit()

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


def advance_to_next_nodes(queue_item):
    """
    推進到下一個節點

    Args:
        queue_item: 當前完成的佇列項目
    """
    from modules.form_workflow.services.workflow_engine import WorkflowEngine

    WorkflowEngine.advance_workflow(
        queue_item.workflow_instance_secure_code,
        queue_item.node_id,
        queue_item.result
    )


def handle_error(queue_item_code, error_message):
    """
    處理執行錯誤

    Args:
        queue_item_code: FwNodeExecutionQueue secure_code
        error_message: 錯誤訊息
    """
    sys.path.insert(0, '/opt/BeakPlatform/backend')

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
