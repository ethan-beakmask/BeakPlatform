"""
FormWorkflow Module - Form Field Spec History Model
欄位規格版本歷史

記錄每次 spec 變更的快照和差異。
"""
import secrets
from sqlalchemy import Column, String, Integer, Text, JSON, event
from .base import ModuleBaseModel


class FwFormFieldSpecHistory(ModuleBaseModel):
    """
    欄位規格版本歷史

    每次 spec 被更新時，儲存一筆歷史記錄，
    包含當時的欄位快照和與前一版的差異。
    """
    __tablename__ = 'fw_form_field_spec_histories'

    # 關聯 spec
    spec_secure_code = Column(String(32), nullable=False, index=True)

    # 關聯表單模板（冗餘，方便查詢）
    form_template_secure_code = Column(String(32), nullable=False, index=True)

    # 版本號
    version = Column(Integer, nullable=False)

    # 欄位快照
    fields_snapshot = Column(JSON, nullable=False, default=list)

    # 變更描述
    change_description = Column(Text)

    # 變更差異
    change_diff = Column(JSON)

    # 修改者
    changed_by = Column(String(32))
    changed_by_name = Column(String(200))

    def __repr__(self):
        return (
            f'<FwFormFieldSpecHistory spec={self.spec_secure_code} '
            f'v{self.version}>'
        )

    def to_dict(self):
        base = super().to_dict()
        base.update({
            'spec_secure_code': self.spec_secure_code,
            'form_template_secure_code': self.form_template_secure_code,
            'version': self.version,
            'fields_snapshot': self.fields_snapshot or [],
            'change_description': self.change_description,
            'change_diff': self.change_diff,
            'changed_by': self.changed_by,
            'changed_by_name': self.changed_by_name,
        })
        return base


@event.listens_for(FwFormFieldSpecHistory, 'before_insert')
def generate_history_secure_code(mapper, connection, target):
    if not target.secure_code:
        target.secure_code = secrets.token_urlsafe(16)
