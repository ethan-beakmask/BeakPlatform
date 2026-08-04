"""
NoCode Builder - PageTemplate Hide Model
子系統對平台內建樣板的隱藏設定
"""
from sqlalchemy import Column, String, UniqueConstraint

from .base import ModuleBaseModel


class DcSubSystemTemplateHide(ModuleBaseModel):
    """子系統隱藏平台內建樣板"""
    __tablename__ = 'dc_sub_system_template_hides'

    sub_system_secure_code = Column(String(32), nullable=False, index=True)
    template_secure_code = Column(String(32), nullable=False, index=True)

    __table_args__ = (
        UniqueConstraint(
            'sub_system_secure_code',
            'template_secure_code',
            name='uq_dc_sub_system_template_hides',
        ),
    )
