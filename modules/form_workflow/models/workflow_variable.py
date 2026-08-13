"""
FormWorkflow Module - Workflow Variable Model
工作流變數模型

Scope 定義 (見 dev-notes/VARIABLE_SYSTEM_SPEC.md):
- TREE: 跨流程共享（整棵流程樹），隔離鍵 = root_instance_code
- FLOW: 單一流程實例，隔離鍵 = workflow_instance_secure_code
- NODE: 節點級，節點完成後自動清除

注意：此模型使用獨立的基礎類別，因為資料表沒有 soft delete 欄位。
"""
from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB

from app import db


class FwWorkflowVariable(db.Model):
    """
    工作流變數表

    用於儲存流程執行期間的變數。
    採用混合儲存模式（記憶體快取 + 資料庫持久化）。

    注意：此表沒有 soft delete 欄位，直接繼承 db.Model。
    """
    __tablename__ = 'fw_workflow_variables'

    # Scope 常數
    SCOPE_TREE = 'TREE'    # 跨流程共享（整棵流程樹）
    SCOPE_FLOW = 'FLOW'    # 單一流程實例
    SCOPE_NODE = 'NODE'    # 節點級（節點完成後清除）

    # 舊常數別名（過渡期相容，標記 deprecated）
    TYPE_GLOBAL = 'FLOW'   # deprecated: 用 SCOPE_FLOW
    TYPE_LOCAL = 'NODE'    # deprecated: 用 SCOPE_NODE

    # Scope 中文標籤
    SCOPE_LABELS = {
        'TREE': '跨流程',
        'FLOW': '流程級',
        'NODE': '節點級',
    }

    # 基礎欄位
    id = Column(Integer, primary_key=True)
    secure_code = Column(String(32), unique=True, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    org_secure_code = Column(String(32), nullable=False, index=True)

    # 關聯的工作流實例（FLOW/NODE scope 使用）
    workflow_instance_secure_code = Column(String(32), nullable=False, index=True)

    # TREE scope 隔離鍵（整棵流程樹共享同一個 root_instance_code）
    root_instance_code = Column(String(32), nullable=True, index=True)

    # 變數資訊
    var_name = Column(String(200), nullable=False)
    var_value = Column(JSONB, nullable=True)  # 支援各種型別

    # 變數 scope
    var_type = Column(String(50), default=SCOPE_FLOW)  # TREE / FLOW / NODE

    # 來源節點
    source_node_id = Column(String(100), nullable=True)

    # 複合唯一約束（與實際資料庫匹配）
    __table_args__ = (
        UniqueConstraint(
            'workflow_instance_secure_code', 'var_name', 'var_type',
            name='idx_fw_workflow_variables_unique'
        ),
        Index('idx_fw_workflow_variables_workflow', 'workflow_instance_secure_code'),
        Index('idx_fw_workflow_variables_name', 'var_name'),
        Index('idx_fw_workflow_variables_type', 'var_type'),
        Index('idx_fw_workflow_variables_root', 'root_instance_code'),
    )

    def __repr__(self):
        return f'<FwWorkflowVariable {self.var_name}={self.var_value} ({self.var_type})>'

    def to_dict(self):
        """轉換為字典"""
        return {
            'id': self.id,
            'secure_code': self.secure_code,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'workflow_instance_secure_code': self.workflow_instance_secure_code,
            'root_instance_code': self.root_instance_code,
            'var_name': self.var_name,
            'var_value': self.var_value,
            'var_type': self.var_type,
            'source_node_id': self.source_node_id,
        }
