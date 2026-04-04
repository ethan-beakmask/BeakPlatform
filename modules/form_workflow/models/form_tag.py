"""
FormWorkflow Module - Form Tag Model
表單標籤（工作站篩選用的額外維度）
"""
import secrets
from sqlalchemy import Column, String, Integer, Boolean, event

from .base import ModuleBaseModel


class FwFormTag(ModuleBaseModel):
    """
    表單標籤

    提供分類之外的額外標記維度，用於工作站篩選。
    例如：SECURITY、CUSTOMER_SERVICE、INCIDENT、DISPATCH
    """
    __tablename__ = 'fw_form_tags'

    code = Column(String(50), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    description = Column(String(500), nullable=True)
    color = Column(String(20), nullable=True)
    display_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True, nullable=False)

    # 建立者
    created_by_name = Column(String(100), nullable=True)

    def __repr__(self):
        return f'<FwFormTag {self.code}: {self.name}>'

    def to_dict(self):
        data = super().to_dict()
        data.update({
            'code': self.code,
            'name': self.name,
            'description': self.description,
            'color': self.color,
            'display_order': self.display_order,
            'is_active': self.is_active,
        })
        return data


@event.listens_for(FwFormTag, 'before_insert')
def generate_tag_secure_code(mapper, connection, target):
    if not target.secure_code:
        target.secure_code = secrets.token_urlsafe(16)
