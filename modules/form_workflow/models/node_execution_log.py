"""
FormWorkflow Module - Node Execution Log Model
節點執行日誌模型
"""
from datetime import datetime
from sqlalchemy import Column, String, Integer, Text, DateTime, BigInteger
from sqlalchemy.dialects.postgresql import JSON

from .base import ModuleBaseModel


class FwNodeExecutionLog(ModuleBaseModel):
    """
    節點執行日誌表

    記錄工作流執行過程中的所有日誌。
    """
    __tablename__ = 'fw_node_execution_logs'

    # 關聯資訊
    workflow_instance_id = Column(BigInteger, nullable=True, index=True)
    node_queue_id = Column(BigInteger, nullable=True, index=True)
    execution_id = Column(String(100), nullable=True, index=True)  # 執行代碼

    # 節點資訊
    node_id = Column(String(100), nullable=True)
    node_instance_id = Column(String(100), nullable=True)  # 節點實例 ID
    node_type = Column(String(50), nullable=True)

    # 狀態與日誌等級
    status = Column(String(50), nullable=True)
    log_level = Column(String(20), default='INFO', nullable=False)  # DEBUG, INFO, WARNING, ERROR

    # 日誌內容
    log_message = Column(Text, nullable=False)
    log_data = Column(JSON, nullable=True)  # 詳細資料

    def __repr__(self):
        return f'<FwNodeExecutionLog [{self.log_level}] {self.log_message[:50]}>'

    def to_dict(self):
        """轉換為字典"""
        data = super().to_dict()
        data.update({
            'workflow_instance_id': self.workflow_instance_id,
            'node_queue_id': self.node_queue_id,
            'execution_id': self.execution_id,
            'node_id': self.node_id,
            'node_type': self.node_type,
            'log_level': self.log_level,
            'log_message': self.log_message,
            'log_data': self.log_data,
        })
        return data
