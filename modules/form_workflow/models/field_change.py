"""
FormWorkflow Module - Field Change Record Model
表單欄位變更歷史

記錄簽核過程中，簽核者對表單欄位的修改。
"""
from datetime import datetime
from sqlalchemy import Column, String, Text, DateTime, JSON

from .base import ModuleBaseModel


class FwFormFieldChange(ModuleBaseModel):
    """
    表單欄位變更記錄

    追蹤每個簽核關卡中，簽核者對表單欄位的修改。
    """
    __tablename__ = 'fw_form_field_changes'

    # 關聯
    form_instance_secure_code = Column(String(32), nullable=False, index=True)
    workflow_instance_secure_code = Column(String(32), nullable=True, index=True)

    # 發生在哪個簽核關卡
    node_id = Column(String(100), nullable=False)
    node_name = Column(String(200), nullable=True)

    # 修改者
    changed_by_secure_code = Column(String(32), nullable=False, index=True)
    changed_by_name = Column(String(200), nullable=True)

    # 欄位資訊
    field_key = Column(String(200), nullable=False)
    field_label = Column(String(200), nullable=True)

    # 變更值 (JSONB 以支援各種型別)
    old_value = Column(JSON, nullable=True)
    new_value = Column(JSON, nullable=True)

    # 時間
    changed_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f'<FwFormFieldChange {self.form_instance_secure_code}/{self.node_id}: {self.field_key}>'

    def to_dict(self):
        data = super().to_dict()
        data.update({
            'form_instance_secure_code': self.form_instance_secure_code,
            'node_id': self.node_id,
            'node_name': self.node_name,
            'changed_by_name': self.changed_by_name,
            'field_key': self.field_key,
            'field_label': self.field_label,
            'old_value': self.old_value,
            'new_value': self.new_value,
            'changed_at': self.changed_at.isoformat() if self.changed_at else None,
        })
        return data
