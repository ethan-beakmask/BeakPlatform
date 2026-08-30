"""
FormWorkflow Module - Node Organization Grant Model
流程節點型別企業授權

此表為平台層授權表，org_secure_code 是被授權企業，不是資料租戶。
"""
from sqlalchemy import Column, String, Text, Index, text

from app.models.base import BaseModel


class WorkflowNodeOrgGrant(BaseModel):
    """流程節點型別對企業的授權記錄。"""

    __tablename__ = 'workflow_node_org_grants'

    node_type = Column(String(100), nullable=False, index=True)
    org_secure_code = Column(String(32), nullable=False, index=True)
    granted_by_secure_code = Column(String(32), nullable=True)
    granted_by_name = Column(String(200), nullable=True)
    note = Column(Text, nullable=True)

    __table_args__ = (
        Index(
            'uq_node_org_grant_active',
            'node_type',
            'org_secure_code',
            unique=True,
            postgresql_where=text('is_deleted = false'),
        ),
    )
