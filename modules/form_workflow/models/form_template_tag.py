"""
FormWorkflow Module - Form Template Tag Model
表單模板與標籤的多對多關聯
"""
import secrets
from sqlalchemy import Column, String, event

from .base import ModuleBaseModel


class FwFormTemplateTag(ModuleBaseModel):
    """
    表單模板 - 標籤關聯（多對多）

    將標籤附加到表單模板上，供工作站篩選使用。
    """
    __tablename__ = 'fw_form_template_tags'

    form_template_secure_code = Column(String(32), nullable=False, index=True)
    tag_secure_code = Column(String(32), nullable=False, index=True)

    def __repr__(self):
        return f'<FwFormTemplateTag template={self.form_template_secure_code} tag={self.tag_secure_code}>'

    def to_dict(self):
        return {
            'secure_code': self.secure_code,
            'form_template_secure_code': self.form_template_secure_code,
            'tag_secure_code': self.tag_secure_code,
        }


@event.listens_for(FwFormTemplateTag, 'before_insert')
def generate_ftt_secure_code(mapper, connection, target):
    if not target.secure_code:
        target.secure_code = secrets.token_urlsafe(16)
