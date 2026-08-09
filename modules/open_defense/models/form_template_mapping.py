"""
OpenDefense Module - Form Template Mapping

規則式事件路由表(per org)。
intake_service 啟動 workflow 時依優先序與條件決定處置單模板,
模板或分流條件調整時只改規則、不改程式。
"""
from sqlalchemy import Boolean, Column, Integer, String
from sqlalchemy.dialects.postgresql import JSONB

from .base import OdBaseModel


class OdFormTemplateMapping(OdBaseModel):
    """OpenDefense 事件到 form_template 的規則式路由。"""
    __tablename__ = 'od_form_template_mappings'

    event_class = Column(String(30), nullable=True)
    form_template_secure_code = Column(String(32), nullable=False)

    name = Column(String(100), nullable=True)
    priority = Column(Integer, nullable=False, default=0)
    match_rules = Column(JSONB, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    note = Column(String(500), nullable=True)

    def to_dict(self):
        base = super().to_dict()
        base.update({
            'event_class': self.event_class,
            'form_template_secure_code': self.form_template_secure_code,
            'name': self.name,
            'priority': self.priority,
            'match_rules': self.match_rules,
            'is_active': self.is_active,
            'note': self.note,
        })
        return base
