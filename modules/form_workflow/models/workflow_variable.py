"""
FormWorkflow Module - Workflow Variable Model
工作流變數模型
"""
from sqlalchemy import Column, String, Integer, Text, Index, UniqueConstraint, BigInteger
from sqlalchemy.dialects.postgresql import JSON

from .base import ModuleBaseModel


class FwWorkflowVariable(ModuleBaseModel):
    """
    工作流變數表

    用於儲存流程執行期間的變數。
    採用混合儲存模式（記憶體快取 + 資料庫持久化）。
    """
    __tablename__ = 'fw_workflow_variables'

    # 變數作用域常數
    SCOPE_GLOBAL = 'GLOBAL'  # 全域變數：整個流程可見
    SCOPE_LOCAL = 'LOCAL'    # 節點級變數：只在特定節點可見

    # 關聯的工作流實例
    workflow_instance_id = Column(BigInteger, nullable=False, index=True)
    workflow_instance_secure_code = Column(String(32), nullable=True, index=True)

    # 變數資訊
    var_name = Column(String(100), nullable=False)
    var_value = Column(JSON, nullable=True)  # 支援各種型別

    # 作用域
    scope = Column(String(20), default=SCOPE_GLOBAL, nullable=False)  # GLOBAL=全域, LOCAL=節點級
    node_id = Column(String(100), nullable=True)  # 節點ID (LOCAL變數專用, GLOBAL則為NULL)

    # 額外資訊
    description = Column(Text, nullable=True)   # 變數說明
    source_node_id = Column(String(100), nullable=True)  # 來源節點

    # 複合唯一約束
    __table_args__ = (
        # 同一流程中，GLOBAL 變數名稱不重複
        UniqueConstraint(
            'workflow_instance_id', 'var_name', 'scope', 'node_id',
            name='uq_fw_workflow_var_name'
        ),
        Index('idx_fw_wv_instance', 'workflow_instance_id'),
        Index('idx_fw_wv_name', 'var_name'),
        Index('idx_fw_wv_scope', 'scope'),
    )

    def __repr__(self):
        return f'<FwWorkflowVariable {self.var_name}={self.var_value} ({self.scope})>'

    def to_dict(self):
        """轉換為字典"""
        data = super().to_dict()
        data.update({
            'workflow_instance_id': self.workflow_instance_id,
            'var_name': self.var_name,
            'var_value': self.var_value,
            'scope': self.scope,
            'node_id': self.node_id,
            'description': self.description,
            'source_node_id': self.source_node_id,
        })
        return data
