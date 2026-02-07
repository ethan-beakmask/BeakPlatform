"""
FormWorkflow Module - Category Model
表單流程分類（二層結構）
"""
import secrets
from sqlalchemy import Column, String, Text, Boolean, Integer, event
from sqlalchemy.dialects.postgresql import JSON

from app.models.base import BaseModel


class FwCategory(BaseModel):
    """
    表單流程分類（二層結構）

    parent_secure_code 為 NULL → 第一層（父分類）
    parent_secure_code 非 NULL → 第二層（子分類）
    """
    __tablename__ = 'fw_categories'

    # 企業識別碼（NULL = 系統分類，所有企業共用）
    org_secure_code = Column(String(32), nullable=True, index=True)

    # 父分類 secure_code（NULL = 第一層）
    parent_secure_code = Column(String(32), nullable=True, index=True)

    # 基本資訊
    name = Column(String(100), nullable=False)
    description = Column(String(500), nullable=True)
    display_order = Column(Integer, default=0)

    # 系統內建分類標記（無法刪除）
    is_system = Column(Boolean, default=False, nullable=False)

    # 顯示開關（僅父分類使用）
    show_in_form_design = Column(Boolean, default=True, nullable=False)
    show_in_workflow_design = Column(Boolean, default=True, nullable=False)
    show_in_form_center = Column(Boolean, default=True, nullable=False)

    __table_args__ = (
        {'extend_existing': True},
    )

    def __repr__(self):
        return f'<FwCategory {self.name} (parent={self.parent_secure_code})>'

    @property
    def is_parent(self):
        """是否為父分類"""
        return self.parent_secure_code is None

    @property
    def is_child(self):
        """是否為子分類"""
        return self.parent_secure_code is not None

    def to_dict(self):
        """轉換為字典"""
        data = super().to_dict()
        data.update({
            'name': self.name,
            'description': self.description,
            'display_order': self.display_order,
            'is_system': self.is_system,
            'parent_secure_code': self.parent_secure_code,
            'is_parent': self.is_parent,
            'show_in_form_design': self.show_in_form_design,
            'show_in_workflow_design': self.show_in_workflow_design,
            'show_in_form_center': self.show_in_form_center,
        })
        return data

    def can_delete(self, org_secure_code=None):
        """
        檢查是否可刪除

        父分類：須先刪除所有子分類
        子分類：檢查 category_secure_code 外鍵引用
        """
        if self.is_system:
            return False, '系統內建分類無法刪除'

        from app import db

        if self.is_parent:
            # 父分類：檢查是否有子分類
            child_count = FwCategory.query.filter_by(
                parent_secure_code=self.secure_code,
                is_deleted=False
            ).count()
            if child_count > 0:
                return False, f'此分類下有 {child_count} 個子分類，請先刪除子分類'
            # 父分類也可能被表單/流程直接引用（無子分類時），繼續往下檢查

        # 檢查是否有表單/流程使用此分類的 secure_code
        from .form_template import FwFormTemplate
        from .workflow_template import FwWorkflowTemplate

        form_query = FwFormTemplate.query.filter_by(
            category_secure_code=self.secure_code,
            is_deleted=False
        )
        workflow_query = FwWorkflowTemplate.query.filter_by(
            category_secure_code=self.secure_code,
            is_deleted=False
        )

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
