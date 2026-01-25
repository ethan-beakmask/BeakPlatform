"""
FormWorkflow Module - Workflow Log Service
工作流日誌服務
"""
import json
import logging
from typing import Any, Optional, Dict
from datetime import datetime

from app import db

logger = logging.getLogger(__name__)


class WorkflowLogService:
    """工作流日誌服務"""

    @staticmethod
    def log(
        level: str,
        message: str,
        workflow_instance_id: int = None,
        node_queue_id: int = None,
        execution_id: str = None,
        node_id: str = None,
        data: Dict = None
    ):
        """
        記錄日誌到 fw_node_execution_logs 表

        Args:
            level: 日誌等級 (DEBUG, INFO, WARNING, ERROR)
            message: 日誌訊息
            workflow_instance_id: 工作流實例 ID
            node_queue_id: 節點佇列 ID
            execution_id: 執行代碼
            node_id: 節點 ID
            data: 額外資料
        """
        try:
            from sqlalchemy import text

            # 使用 raw SQL 插入
            sql = text("""
                INSERT INTO fw_node_execution_logs
                (secure_code, org_secure_code, execution_id, node_instance_id, node_type,
                 status, log_level, log_message, log_data, workflow_instance_id,
                 node_queue_id, node_id, created_at, updated_at, is_deleted)
                VALUES
                (:secure_code, :org_secure_code, :execution_id, :node_instance_id, :node_type,
                 :status, :log_level, :log_message, CAST(:log_data AS json), :workflow_instance_id,
                 :node_queue_id, :node_id, :created_at, :updated_at, false)
            """)

            import secrets
            now = datetime.utcnow()

            # 嘗試從 workflow_instance 取得 org_secure_code
            org_code = 'SYSTEM'  # 預設值
            if workflow_instance_id:
                try:
                    from ..models import FwWorkflowInstance
                    wi = FwWorkflowInstance.query.get(workflow_instance_id)
                    if wi:
                        org_code = wi.org_secure_code
                except Exception:
                    pass

            db.session.execute(sql, {
                'secure_code': secrets.token_urlsafe(16),
                'org_secure_code': org_code,
                'execution_id': execution_id or f'EXEC-{now.strftime("%Y%m%d%H%M%S")}',
                'node_instance_id': node_id or 'SYSTEM',
                'node_type': 'SYSTEM',
                'status': 'INFO',
                'log_level': level.upper(),
                'log_message': message,
                'log_data': json.dumps(data) if data else '{}',
                'workflow_instance_id': workflow_instance_id,
                'node_queue_id': node_queue_id,
                'node_id': node_id,
                'created_at': now,
                'updated_at': now
            })
            db.session.commit()

        except Exception as e:
            # rollback 以清除失敗的 session
            try:
                db.session.rollback()
            except Exception:
                pass
            # 如果資料庫寫入失敗，至少記錄到 Python logger
            logger.warning(f"Failed to write workflow log to database: {e}")
            logger.info(f"[{level}] {message} - data: {data}")

    @staticmethod
    def info(message: str, **kwargs):
        """記錄 INFO 等級日誌"""
        WorkflowLogService.log('INFO', message, **kwargs)

    @staticmethod
    def warning(message: str, **kwargs):
        """記錄 WARNING 等級日誌"""
        WorkflowLogService.log('WARNING', message, **kwargs)

    @staticmethod
    def error(message: str, **kwargs):
        """記錄 ERROR 等級日誌"""
        WorkflowLogService.log('ERROR', message, **kwargs)

    @staticmethod
    def debug(message: str, **kwargs):
        """記錄 DEBUG 等級日誌"""
        WorkflowLogService.log('DEBUG', message, **kwargs)
