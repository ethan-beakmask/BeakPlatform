"""
FormWorkflow Module - SQL Form Registry Model
SQL 同步登記表

記錄所有已建立的 SQL 同步表，存放在主資料庫 (beakplatform_dev)。
每筆記錄對應企業獨立資料庫 (org_{id}) 或集團共享資料庫 (cg_{id}) 中的一張 SQL 同步表。
"""
import secrets
from datetime import datetime
from sqlalchemy import Column, String, Integer, BigInteger, DateTime, Text, event
from sqlalchemy.dialects.postgresql import JSONB
from .base import ModuleBaseModel


class FwSqlFormRegistry(ModuleBaseModel):
    """
    SQL 同步登記表

    記錄哪些發行版本啟用了 SQL 同步，以及對應的 SQL 表名和欄位映射。
    """
    __tablename__ = 'fw_sql_form_registries'

    # PK 為 bigint（與既有資料一致，PF-168 對齊）
    id = Column(BigInteger, primary_key=True)

    org_secure_code = Column(String(100), nullable=False, index=True)

    # 來源追蹤（獨立規格無 mapping/published，允許 NULL）
    mapping_secure_code = Column(String(32), nullable=True, index=True)
    published_secure_code = Column(String(32), nullable=True, index=True)
    form_template_secure_code = Column(String(32), nullable=True)
    spec_secure_code = Column(String(32), nullable=True)

    # SQL 表資訊
    table_name = Column(String(200), nullable=False, unique=True)
    form_version = Column(String(10))
    publish_version = Column(Integer)

    # 欄位定義快照 (form.io schema → SQL columns mapping)
    # {field_key: {pg_type: 'VARCHAR(500)', nullable: True, ...}}
    column_mapping = Column(JSONB, nullable=False)

    # form.io schema 快取（建立 registry 時從 published.form_snapshot.schema 複製）
    form_schema = Column(JSONB)

    # 狀態
    status = Column(String(20), default='active')  # active / suspended / archived
    row_count = Column(Integer, default=0)
    last_synced_at = Column(DateTime)

    # 建表 DDL 備份
    create_ddl = Column(Text)

    def __repr__(self):
        return f'<FwSqlFormRegistry {self.table_name} ({self.status})>'

    def to_dict(self):
        base = super().to_dict()
        base.update({
            'mapping_secure_code': self.mapping_secure_code,
            'published_secure_code': self.published_secure_code,
            'form_template_secure_code': self.form_template_secure_code,
            'spec_secure_code': self.spec_secure_code,
            'table_name': self.table_name,
            'form_version': self.form_version,
            'publish_version': self.publish_version,
            'column_mapping': self.column_mapping,
            'status': self.status,
            'row_count': self.row_count,
            'last_synced_at': self.last_synced_at.isoformat() if self.last_synced_at else None,
        })
        return base


@event.listens_for(FwSqlFormRegistry, 'before_insert')
def generate_registry_secure_code(mapper, connection, target):
    if not target.secure_code:
        target.secure_code = secrets.token_urlsafe(16)
