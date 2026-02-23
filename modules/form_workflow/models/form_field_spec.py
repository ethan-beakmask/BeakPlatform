"""
FormWorkflow Module - Form Field Spec Model
欄位規格定義

作為 single source of truth，定義表單的欄位結構，
同時驅動 FormIO schema 和 SQL DDL 的產生。
"""
import secrets
from sqlalchemy import Column, String, Integer, Text, JSON, event
from .base import ModuleBaseModel


class FwFormFieldSpec(ModuleBaseModel):
    """
    欄位規格定義

    每個 form_template 最多有一筆 active spec。
    fields JSONB 是欄位定義陣列，為表單結構的 single source of truth。
    """
    __tablename__ = 'fw_form_field_specs'

    org_secure_code = Column(String(100), nullable=False, index=True)

    # 關聯表單模板
    form_template_secure_code = Column(String(32), nullable=False, index=True)

    # 版本（每次儲存遞增）
    version = Column(Integer, nullable=False, default=1)

    # 欄位定義 (JSONB array)
    fields = Column(JSON, nullable=False, default=list)

    # 狀態: active / archived
    status = Column(String(20), nullable=False, default='active')

    # 描述
    description = Column(Text)

    # 修改者
    last_modified_by = Column(String(32))
    last_modified_by_name = Column(String(200))

    def __repr__(self):
        return (
            f'<FwFormFieldSpec form={self.form_template_secure_code} '
            f'v{self.version} ({self.status})>'
        )

    def to_dict(self):
        base = super().to_dict()
        base.update({
            'form_template_secure_code': self.form_template_secure_code,
            'version': self.version,
            'fields': self.fields or [],
            'status': self.status,
            'description': self.description,
            'last_modified_by': self.last_modified_by,
            'last_modified_by_name': self.last_modified_by_name,
        })
        return base

    def get_field_keys(self):
        """取得所有 field_key 列表"""
        return [f['field_key'] for f in (self.fields or []) if f.get('field_key')]

    def get_field_by_key(self, field_key):
        """根據 field_key 取得欄位定義"""
        for f in (self.fields or []):
            if f.get('field_key') == field_key:
                return f
        return None


@event.listens_for(FwFormFieldSpec, 'before_insert')
def generate_spec_secure_code(mapper, connection, target):
    if not target.secure_code:
        target.secure_code = secrets.token_urlsafe(16)
