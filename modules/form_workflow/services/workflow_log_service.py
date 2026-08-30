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
        data: Dict = None,
        node_type: str = None,
        status: str = None,
        node_instance_id: str = None,
        org_secure_code: str = None
    ):
        """
        記錄日誌到 fw_node_execution_logs 表

        Args:
            level: 日誌等級 (DEBUG, INFO, WARNING, ERROR)
            message: 日誌訊息
            workflow_instance_id: 工作流實例 ID
            node_queue_id: 節點佇列 ID
            execution_id: 流程執行代碼；未提供時嘗試使用 workflow_instance.execution_code
            node_id: 節點 ID
            data: 額外資料
            node_type: 節點實際型別；取不到時留空
            status: 寫入當下的節點狀態（多數情形是 RUNNING），不是 log 等級；取不到時留空
            node_instance_id: 節點實例識別碼；取不到時留空
            org_secure_code: 企業 secure_code；未提供時嘗試使用 workflow_instance.org_secure_code

        取不到的欄位一律留空，不填假值；假值會讓欄位失去查詢價值，
        而 org_secure_code 的假值還會產生企業孤兒資料。
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

            workflow_instance = None
            needs_workflow_instance = (
                workflow_instance_id and
                (not org_secure_code or not execution_id)
            )
            if needs_workflow_instance:
                try:
                    from ..models import FwWorkflowInstance
                    workflow_instance = FwWorkflowInstance.query.get(workflow_instance_id)
                except Exception:
                    pass

            if not org_secure_code and workflow_instance:
                org_secure_code = workflow_instance.org_secure_code

            if not execution_id and workflow_instance:
                execution_id = workflow_instance.execution_code

            if not org_secure_code:
                logger.warning(
                    "Failed to write workflow log to database: org_secure_code is required but unavailable"
                )
                logger.info(f"[{level}] {message} - data: {data}")
                return

            db.session.execute(sql, {
                'secure_code': secrets.token_urlsafe(16),
                'org_secure_code': org_secure_code,
                'execution_id': execution_id,
                'node_instance_id': node_instance_id,
                'node_type': node_type,
                'status': status,
                'log_level': level.upper(),
                'log_message': message,
                'log_data': json.dumps(data) if data else '{}',
                'workflow_instance_id': workflow_instance_id,
                'node_queue_id': node_queue_id,
                'node_id': node_id,
                'created_at': now,
                'updated_at': now
            })
            # 刻意保留，勿移除：每筆 log 立即 commit，確保執行前紀錄先落地，
            # 即使後續節點進程被 SIGKILL 或機器斷電也能查到當時要做什麼。
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
