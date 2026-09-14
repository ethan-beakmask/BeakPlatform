"""
OpenDefense Module - Payload Profile

來源格式設定檔,供原生 SOC payload intake 使用。
"""
from sqlalchemy import Boolean, Column, String, Index, text
from sqlalchemy.dialects.postgresql import JSONB

from .base import OdBaseModel


class OdPayloadProfile(OdBaseModel):
    """OpenDefense 原生 payload 來源格式設定檔。"""
    __tablename__ = 'od_payload_profiles'

    code = Column(String(50), nullable=False)
    name = Column(String(100), nullable=False)
    source_system = Column(String(50), nullable=False)
    correlation_id_path = Column(String(200), nullable=False)
    field_map = Column(JSONB, nullable=False, default=dict)
    severity_map = Column(JSONB, nullable=True)
    detail_path = Column(String(200), nullable=True)
    detail_item_key = Column(String(100), nullable=True)
    detail_columns = Column(JSONB, nullable=True)
    # 明細列中拿來組案件標題的欄位名(例 EventName);未設定則只用 finding_rule_id
    subject_detail_key = Column(String(100), nullable=True)
    kv_expansions = Column(JSONB, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    note = Column(String(500), nullable=True)

    __table_args__ = (
        Index(
            'uq_od_payload_profiles_org_code_active',
            'org_secure_code',
            'code',
            unique=True,
            postgresql_where=text('is_deleted = false'),
        ),
    )

    def to_dict(self):
        base = super().to_dict()
        base.update({
            'code': self.code,
            'name': self.name,
            'source_system': self.source_system,
            'correlation_id_path': self.correlation_id_path,
            'field_map': self.field_map or {},
            'severity_map': self.severity_map,
            'detail_path': self.detail_path,
            'detail_item_key': self.detail_item_key,
            'detail_columns': self.detail_columns,
            'subject_detail_key': self.subject_detail_key,
            'kv_expansions': self.kv_expansions,
            'is_active': self.is_active,
            'note': self.note,
        })
        return base
