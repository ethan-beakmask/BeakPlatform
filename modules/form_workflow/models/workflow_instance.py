"""
FormWorkflow Module - Workflow Instance Model
工作流實例
"""
from datetime import datetime
from sqlalchemy import Column, BigInteger, String, Text, DateTime, Integer, Boolean, Index, text as sa_text
from sqlalchemy.dialects.postgresql import JSONB

from .base import ModuleBaseModel


class FwWorkflowInstance(ModuleBaseModel):
    """
    工作流實例

    執行中的流程。
    """
    __tablename__ = 'fw_workflow_instances'
    __table_args__ = (
        Index(
            'uq_fw_wi_org_execution_code',
            'org_secure_code', 'execution_code',
            unique=True,
            postgresql_where=sa_text('is_deleted = false'),
        ),
    )

    # 關聯（保留 ID 方便快速查詢）
    form_instance_id = Column(BigInteger, nullable=True, index=True)
    form_instance_secure_code = Column(String(32), nullable=True, index=True)
    workflow_template_id = Column(BigInteger, nullable=True, index=True)
    workflow_template_secure_code = Column(String(32), nullable=False, index=True)
    published_secure_code = Column(String(32), nullable=True, index=True)

    # 流程基本資訊（快照）
    workflow_name = Column(String(200), nullable=True)
    workflow_version = Column(String(10), nullable=True)
    graph_snapshot = Column(JSONB, nullable=True)  # 流程圖快照

    # 測試標記
    is_test = Column(Boolean, default=False, nullable=False, index=True)

    # 子流程關聯
    parent_instance_code = Column(String(32), nullable=True, index=True)  # 父流程實例
    root_instance_code = Column(String(32), nullable=True, index=True)    # 根流程實例
    workflow_depth = Column(Integer, default=0, nullable=False)           # 流程深度（0=主流程）

    # 狀態：PENDING, RUNNING, COMPLETED, FAILED, CANCELLED
    status = Column(String(50), default='PENDING', nullable=False, index=True)

    # 當前節點
    current_node_id = Column(String(100), nullable=True)
    current_node_type = Column(String(50), nullable=True)

    # 執行紀錄
    execution_code = Column(String(50), nullable=False, index=True)
    execution_log = Column(JSONB, default=list)  # 執行日誌

    # 流程變數
    variables = Column(JSONB, default=dict)

    # NoCode portal 來源追蹤
    nocode_sub_system_sc = Column(String(32), nullable=True, index=True)
    nocode_user_ref = Column(String(64), nullable=True, index=True)

    # 錯誤資訊
    error_message = Column(Text, nullable=True)
    error_node_id = Column(String(100), nullable=True)

    # 時間
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # 狀態名稱對應
    STATUS_NAMES = {
        'PENDING': '等待中',
        'RUNNING': '執行中',
        'COMPLETED': '已完成',
        'FAILED': '執行失敗',
        'CANCELLED': '已取消',
    }

    def __repr__(self):
        return f'<FwWorkflowInstance {self.execution_code}: {self.status}>'

    def to_dict(self, include_log=False):
        """轉換為字典"""
        data = super().to_dict()
        data.update({
            'execution_code': self.execution_code,
            'status': self.status,
            'status_name': self.STATUS_NAMES.get(self.status, self.status),
            'form_instance_secure_code': self.form_instance_secure_code,
            'workflow_template_secure_code': self.workflow_template_secure_code,
            'current_node_id': self.current_node_id,
            'current_node_type': self.current_node_type,
            'error_message': self.error_message,
        })

        if include_log:
            data['execution_log'] = self.execution_log

        if self.started_at:
            data['started_at'] = self.started_at.isoformat()
        if self.completed_at:
            data['completed_at'] = self.completed_at.isoformat()

        return data

    def start(self):
        """開始執行"""
        self.status = 'RUNNING'
        self.started_at = datetime.utcnow()

    def complete(self):
        """完成"""
        self.status = 'COMPLETED'
        self.completed_at = datetime.utcnow()

    def fail(self, error_message, error_node_id=None):
        """失敗"""
        self.status = 'FAILED'
        self.error_message = error_message
        self.error_node_id = error_node_id
        self.completed_at = datetime.utcnow()

    def cancel(self):
        """取消"""
        self.status = 'CANCELLED'
        self.completed_at = datetime.utcnow()
