"""
FormWorkflow Module - Category Model
表單流程分類
"""
import secrets
from sqlalchemy import Column, String, Text, Boolean, Integer, event
from sqlalchemy.dialects.postgresql import JSON

from app.models.base import BaseModel


class FwCategory(BaseModel):
    """
    表單流程分類

    用於分類表單範本和工作流程範本。
    每個企業可以有自己的分類，也可以使用系統預設分類。
    系統分類的 org_secure_code 為 NULL。
    """
    __tablename__ = 'fw_categories'

    # 企業識別碼（NULL = 系統分類，所有企業共用）
    org_secure_code = Column(String(32), nullable=True, index=True)

    # 基本資訊
    name = Column(String(100), nullable=False)
    description = Column(String(500), nullable=True)
    display_order = Column(Integer, default=0)

    # 系統內建分類標記（無法刪除）
    is_system = Column(Boolean, default=False, nullable=False)

    # 顯示開關
    show_in_form_design = Column(Boolean, default=True, nullable=False)
    show_in_workflow_design = Column(Boolean, default=True, nullable=False)
    show_in_form_center = Column(Boolean, default=True, nullable=False)

    # 唯一約束：同一企業內分類名稱唯一
    __table_args__ = (
        # db.UniqueConstraint('name', 'org_secure_code', name='fw_categories_name_org_unique'),
        {'extend_existing': True},
    )

    def __repr__(self):
        return f'<FwCategory {self.name}>'

    def to_dict(self):
        """轉換為字典"""
        data = super().to_dict()
        data.update({
            'name': self.name,
            'description': self.description,
            'display_order': self.display_order,
            'is_system': self.is_system,
            'show_in_form_design': self.show_in_form_design,
            'show_in_workflow_design': self.show_in_workflow_design,
            'show_in_form_center': self.show_in_form_center,
        })
        return data

    def can_delete(self, org_secure_code=None):
        """檢查是否可刪除"""
        if self.is_system:
            return False, '系統內建分類無法刪除'

        # 檢查是否有表單或流程使用此分類
        from .form_template import FwFormTemplate
        from .workflow_template import FwWorkflowTemplate

        # 建立查詢條件
        form_query = FwFormTemplate.query.filter_by(category=self.name, is_deleted=False)
        workflow_query = FwWorkflowTemplate.query.filter_by(category=self.name, is_deleted=False)

        # 如果有指定企業，只檢查同企業的表單/流程
        if org_secure_code:
            form_query = form_query.filter_by(org_secure_code=org_secure_code)
            workflow_query = workflow_query.filter_by(org_secure_code=org_secure_code)

        form_count = form_query.count()
        workflow_count = workflow_query.count()

        if form_count > 0 or workflow_count > 0:
            return False, f'此分類正被 {form_count} 個表單和 {workflow_count} 個流程使用，無法刪除'

        return True, 'OK'


@event.listens_for(FwCategory, 'before_insert')
def generate_category_secure_code(mapper, connection, target):
    """插入前自動生成 secure_code"""
    if not target.secure_code:
        target.secure_code = secrets.token_urlsafe(16)
