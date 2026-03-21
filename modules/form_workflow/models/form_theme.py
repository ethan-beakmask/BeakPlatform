"""
FormWorkflow Module - Form Theme Model
表單風格主題
"""
import secrets
from sqlalchemy import Column, String, Text, Boolean, Integer, event
from sqlalchemy.dialects.postgresql import JSON

from app.models.base import BaseModel


class FwFormTheme(BaseModel):
    """
    表單風格主題

    每個主題對應一份 CSS 內容，以 [data-form-theme="<name>"] 為 scope。
    name 為主題識別碼（英文），display_name 為顯示名稱。
    """
    __tablename__ = 'fw_form_themes'

    # 企業識別碼（NULL = 系統主題，所有企業共用）
    org_secure_code = Column(String(32), nullable=True, index=True)

    # 基本資訊
    name = Column(String(100), nullable=False, index=True)
    display_name = Column(String(200), nullable=False)
    description = Column(String(500), nullable=True)

    # CSS 內容
    css_content = Column(Text, nullable=True)

    # 元件預設屬性（如 labelPosition, labelWidth, labelMargin）
    component_defaults = Column(JSON, nullable=True)

    # 狀態
    is_system = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    sort_order = Column(Integer, default=0)

    __table_args__ = (
        {'extend_existing': True},
    )

    def __repr__(self):
        return f'<FwFormTheme {self.name} ({self.display_name})>'

    def to_dict(self):
        """轉換為字典（不含 CSS 內容，減少傳輸量）"""
        data = super().to_dict()
        data.update({
            'name': self.name,
            'display_name': self.display_name,
            'description': self.description,
            'is_system': self.is_system,
            'is_active': self.is_active,
            'sort_order': self.sort_order,
            'has_css': bool(self.css_content),
            'css_size': len(self.css_content) if self.css_content else 0,
            'component_defaults': self.component_defaults,
        })
        return data

    def to_dict_with_css(self):
        """轉換為字典（含 CSS 內容）"""
        data = self.to_dict()
        data['css_content'] = self.css_content
        return data


@event.listens_for(FwFormTheme, 'before_insert')
def generate_theme_secure_code(mapper, connection, target):
    """插入前自動生成 secure_code"""
    if not target.secure_code:
        target.secure_code = secrets.token_urlsafe(16)
