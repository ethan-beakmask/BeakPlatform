"""
Spec Formulate Module - Conglomerate Table Registry
集團共享 DB 表格登記表

追蹤集團 DB 中每張表的建立者企業，用於：
1. 限制表管理權限：只有建立者企業能改表/刪表
2. 記錄表的來源與建立時間
"""
import secrets
from sqlalchemy import Column, String, Text, event
from app.models.base import BaseModel


class FwConglomerateTableRegistry(BaseModel):
    """
    集團共享 DB 表格登記表

    記錄集團 DB 中每張表是由哪個企業建立的。
    平台的 /spec-formulate/ 在執行 DDL 前檢查此表，
    確保只有建立者企業能修改或刪除表結構。
    """
    __tablename__ = 'fw_conglomerate_table_registry'

    # 集團 secure_code
    conglomerate_secure_code = Column(
        String(32), nullable=False, index=True
    )

    # 表名
    table_name = Column(String(100), nullable=False)

    # 建立者企業 secure_code
    creator_org_secure_code = Column(
        String(32), nullable=False, index=True
    )

    # 建立者企業名稱（快照，方便顯示）
    creator_org_name = Column(String(255))

    # 關聯的 SPEC secure_code（nullable，手動建表時無 SPEC）
    spec_secure_code = Column(String(32), nullable=True)

    # 描述
    description = Column(Text, nullable=True)

    # 狀態: active / dropped
    status = Column(String(20), nullable=False, default='active')

    def __repr__(self):
        return (
            f'<FwConglomerateTableRegistry '
            f'{self.table_name} by {self.creator_org_secure_code}>'
        )

    def to_dict(self):
        base = super().to_dict()
        base.update({
            'conglomerate_secure_code': self.conglomerate_secure_code,
            'table_name': self.table_name,
            'creator_org_secure_code': self.creator_org_secure_code,
            'creator_org_name': self.creator_org_name,
            'spec_secure_code': self.spec_secure_code,
            'description': self.description,
            'status': self.status,
        })
        return base


@event.listens_for(FwConglomerateTableRegistry, 'before_insert')
def generate_cg_table_reg_secure_code(mapper, connection, target):
    if not target.secure_code:
        target.secure_code = secrets.token_urlsafe(16)
