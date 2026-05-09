"""
OpenDefense Module - Form Template Mapping

event_class -> form_template_secure_code 的對應表(per org)。
intake_service 啟動 workflow 時依此查找處置單模板,模板被換掉時只改對應、不改程式。
"""
from sqlalchemy import Column, String, UniqueConstraint

from .base import OdBaseModel


class OdFormTemplateMapping(OdBaseModel):
    """event_class -> form_template 對應(取代硬編 default)"""
    __tablename__ = 'od_form_template_mappings'

    event_class = Column(String(30), nullable=False)
    form_template_secure_code = Column(String(32), nullable=False)

    note = Column(String(500), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            'org_secure_code', 'event_class',
            name='uq_od_template_map_org_event',
        ),
    )

    def to_dict(self):
        base = super().to_dict()
        base.update({
            'event_class': self.event_class,
            'form_template_secure_code': self.form_template_secure_code,
            'note': self.note,
        })
        return base
