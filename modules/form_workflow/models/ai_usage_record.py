"""
FormWorkflow Module - AiAgent Usage Record Model
AiAgent 節點用量記錄

這張表記錄的是 claude CLI envelope 回報的牌價估算成本，不是實際扣款或帳單。
失敗執行也要記錄，因為 CLI 逾時、啟動失敗、輸出非法或 canary 驗證失敗都代表
平台曾嘗試執行 AiAgent；有 envelope 時甚至可能已消耗 token 與估算成本。
"""
from sqlalchemy import Column, DateTime, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB

from .base import ModuleBaseModel


class FwAiUsageRecord(ModuleBaseModel):
    """AiAgent 節點單次執行的用量與配額佔位記錄。"""

    __tablename__ = 'fw_ai_usage_records'

    STATUS_RUNNING = 'running'
    STATUS_SUCCESS = 'success'
    STATUS_FAILED = 'failed'
    STATUS_BLOCKED = 'blocked'

    workflow_instance_secure_code = Column(String(32), nullable=True, index=True)
    form_instance_secure_code = Column(String(32), nullable=True)
    node_id = Column(String(64), nullable=True)
    node_name = Column(String(200), nullable=True)
    node_queue_secure_code = Column(String(32), nullable=True)
    model = Column(String(100), nullable=True)
    status = Column(String(20), nullable=False, default=STATUS_RUNNING)
    input_tokens = Column(Integer, nullable=False, default=0)
    output_tokens = Column(Integer, nullable=False, default=0)
    cache_creation_input_tokens = Column(Integer, nullable=False, default=0)
    cache_read_input_tokens = Column(Integer, nullable=False, default=0)
    cost_usd = Column(Numeric(14, 8), nullable=False, default=0)
    duration_ms = Column(Integer, nullable=False, default=0)
    num_turns = Column(Integer, nullable=False, default=0)
    model_usage = Column(JSONB, nullable=True)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=False)
    finished_at = Column(DateTime, nullable=True)

    def to_dict(self):
        """轉成 API 友善格式；不輸出內部自增 id（URL-01）。"""
        data = super().to_dict()
        data.update({
            # 刻意不輸出 org_secure_code：ModuleBaseModel.to_dict() 的既定行為就是
            # 不把租戶識別碼帶進 API 回應，而查詢端一律已依 org 過濾，帶了也無用途。
            'workflow_instance_secure_code': self.workflow_instance_secure_code,
            'form_instance_secure_code': self.form_instance_secure_code,
            'node_id': self.node_id,
            'node_name': self.node_name,
            'node_queue_secure_code': self.node_queue_secure_code,
            'model': self.model,
            'status': self.status,
            'input_tokens': self.input_tokens,
            'output_tokens': self.output_tokens,
            'cache_creation_input_tokens': self.cache_creation_input_tokens,
            'cache_read_input_tokens': self.cache_read_input_tokens,
            'cost_usd': float(self.cost_usd or 0),
            'duration_ms': self.duration_ms,
            'num_turns': self.num_turns,
            'model_usage': self.model_usage,
            'error_message': self.error_message,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'finished_at': self.finished_at.isoformat() if self.finished_at else None,
        })
        return data
