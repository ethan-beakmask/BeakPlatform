"""
FormWorkflow Module - Column Display Config Model
表單中心欄位顯示設定

企業級設定：管理員可依語系配置各欄位寬度與是否隱藏。
"""
from sqlalchemy import Column, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB

from .base import ModuleBaseModel


class FwColumnDisplayConfig(ModuleBaseModel):
    """
    表單中心欄位顯示設定

    每筆記錄對應一個企業 + 語系的欄位配置。
    config JSON 格式:
    {
        "serial_number": {"width": 140, "hidden": false},
        "form_name": {"width": 120, "hidden": false},
        "subject": {"width": null, "hidden": false},
        ...
    }
    """
    __tablename__ = 'fw_column_display_config'

    locale = Column(String(10), nullable=False, default='*')
    config = Column(JSONB, nullable=False, default=dict)

    __table_args__ = (
        UniqueConstraint('org_secure_code', 'locale', name='uq_fw_col_config_org_locale'),
    )

    def to_dict(self):
        return {
            'secure_code': self.secure_code,
            'locale': self.locale,
            'config': self.config or {},
        }
