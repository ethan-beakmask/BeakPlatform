"""
FormWorkflow Module - Form Template Model
表單模板
"""
from sqlalchemy import Column, String, Text, Boolean, DateTime, BigInteger
from sqlalchemy.dialects.postgresql import JSON

from .base import ModuleBaseModel


class FwFormTemplate(ModuleBaseModel):
    """
    表單模板

    儲存 form.io schema 格式的表單定義。
    """
    __tablename__ = 'fw_form_templates'

    # 基本資訊
    code = Column(String(100), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(100), nullable=True, index=True)
    category_secure_code = Column(String(32), nullable=True, index=True)

    # form.io schema
    schema = Column(JSON, nullable=False)

    # 版本控制
    version = Column(String(2), default='AA')  # AA~ZZ (676 組合)
    revision = Column(BigInteger, default=1)   # 修訂號

    # 設計器配置
    builder_config = Column(JSON, default=dict)

    # 縮圖 (base64)
    thumbnail_2x1 = Column(Text, nullable=True)
    thumbnail_1x1 = Column(Text, nullable=True)
    thumbnail_1x2 = Column(Text, nullable=True)

    # 狀態
    is_published = Column(Boolean, default=False, nullable=False, index=True)
    publish_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    is_protected = Column(Boolean, default=False, nullable=False)

    # 權限控制
    permission_type = Column(String(20), default='org', nullable=False)
    owner_secure_code = Column(String(50), nullable=True, index=True)
    allowed_editors = Column(JSON, nullable=True)

    # 建立者/編輯者
    created_by_secure_code = Column(String(32), nullable=True)
    created_by_name = Column(String(100), nullable=True)
    updated_by_secure_code = Column(String(32), nullable=True)
    updated_by_name = Column(String(100), nullable=True)

    def __repr__(self):
        return f'<FwFormTemplate {self.code}: {self.name}>'

    def to_dict(self, include_schema=True):
        """轉換為字典"""
        data = super().to_dict()
        data.update({
            'code': self.code,
            'name': self.name,
            'description': self.description,
            'category': self.category,
            'category_secure_code': self.category_secure_code,
            'version': self.version,
            'revision': self.revision,
            'thumbnail_2x1': self.thumbnail_2x1,
            'is_published': self.is_published,
            'is_active': self.is_active,
            'is_protected': self.is_protected,
            'owner_secure_code': self.owner_secure_code,
            'created_by_secure_code': self.created_by_secure_code,
            'created_by_name': self.created_by_name,
            'updated_by_secure_code': self.updated_by_secure_code,
            'updated_by_name': self.updated_by_name,
        })

        if include_schema:
            data['schema'] = self.schema
            data['builder_config'] = self.builder_config
        else:
            data['has_schema'] = self.schema is not None
            data['component_count'] = len(self.schema.get('components', [])) if self.schema else 0

        if self.publish_at:
            data['publish_at'] = self.publish_at.isoformat()

        return data

    def can_publish(self):
        """檢查是否可以發布"""
        if not self.schema:
            return False, '表單 schema 不可為空'
        if not self.schema.get('components'):
            return False, '表單必須包含至少一個元件'
        return True, 'OK'
