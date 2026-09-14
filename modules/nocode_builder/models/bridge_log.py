"""
Data CRUD Module - BridgeLog Model
資料橋接操作日誌

記錄每次 PG ↔ SQLite 橋接操作的審計追蹤。
"""
from typing import Dict, Any

from sqlalchemy import Column, String, Text, Integer, Boolean
from sqlalchemy.dialects.postgresql import JSONB

from .base import ModuleBaseModel


class DcBridgeLog(ModuleBaseModel):
    """資料橋接操作日誌"""
    __tablename__ = 'dc_bridge_logs'

    sub_system_secure_code = Column(String(32), nullable=False, index=True)
    rule_id = Column(String(64), nullable=True)

    # 方向: publish / update / collect
    direction = Column(String(20), nullable=False)

    # 來源 / 目標
    source_db = Column(String(20), nullable=False)
    source_table = Column(String(128), nullable=False)
    target_db = Column(String(20), nullable=False)
    target_table = Column(String(128), nullable=False)

    # 操作記錄
    record_key = Column(JSONB, nullable=True)
    records_affected = Column(Integer, nullable=False, default=0)
    field_mapping = Column(JSONB, nullable=True)

    # 狀態
    status = Column(String(20), nullable=False, default='success')
    error_message = Column(Text, nullable=True)

    # 操作者
    operator_secure_code = Column(String(32), nullable=True)

    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data.update({
            'sub_system_secure_code': self.sub_system_secure_code,
            'rule_id': self.rule_id,
            'direction': self.direction,
            'source_db': self.source_db,
            'source_table': self.source_table,
            'target_db': self.target_db,
            'target_table': self.target_table,
            'record_key': self.record_key,
            'records_affected': self.records_affected,
            'field_mapping': self.field_mapping,
            'status': self.status,
            'error_message': self.error_message,
            'operator_secure_code': self.operator_secure_code,
        })
        return data
