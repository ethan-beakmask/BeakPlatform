"""
FormWorkflow Module - Form Workflow Mapping Model
表單-流程配對模型

管理表單模板與工作流模板的關聯。
"""
import secrets
from datetime import datetime
from sqlalchemy import Column, BigInteger, String, Boolean, Integer, DateTime, JSON, ForeignKey, event
from sqlalchemy.orm import relationship
from .base import ModuleBaseModel


class FwFormWorkflowMapping(ModuleBaseModel):
    """
    表單-流程配對表

    管理表單與工作流之間的關聯關係。
    一個表單可以對應多個流程（透過條件觸發），
    發行時會複製到 FwPublishedFormWorkflow 作為執行版本。
    """
    __tablename__ = 'fw_form_workflow_mappings'

    # 組織隔離
    org_secure_code = Column(String(100), nullable=False, index=True)

    # 表單資訊
    form_template_id = Column(BigInteger, ForeignKey('fw_form_templates.id'), nullable=False, index=True)
    form_template_secure_code = Column(String(32), nullable=False, index=True)
    form_template_code = Column(String(100))  # 表單代碼
    form_template_version = Column(String(10))  # 表單版本

    # 流程資訊
    workflow_template_id = Column(BigInteger, ForeignKey('fw_workflow_templates.id'), nullable=False, index=True)
    workflow_template_secure_code = Column(String(32), nullable=False, index=True)
    workflow_template_code = Column(String(100))  # 流程代碼
    workflow_template_version = Column(String(10))  # 流程版本

    # 關聯
    form_template = relationship('FwFormTemplate', foreign_keys=[form_template_id])
    workflow_template = relationship('FwWorkflowTemplate', foreign_keys=[workflow_template_id])

    # 狀態
    is_active = Column(Boolean, default=True, nullable=False)
    priority = Column(Integer, default=0, nullable=False)  # 優先順序（多流程時）

    # 發行狀態
    is_published = Column(Boolean, default=False, nullable=False)  # 是否已發行
    publish_at = Column(DateTime)  # 預約發行時間

    # 條件觸發（可選）
    trigger_condition = Column(JSON)  # 觸發條件 JSON

    # 備註
    description = Column(String(500))

    def __repr__(self):
        return f'<FwFormWorkflowMapping {self.secure_code}: Form#{self.form_template_id} -> Workflow#{self.workflow_template_id}>'

    def to_dict(self, include_relations=False):
        """
        轉換為字典

        Args:
            include_relations: 是否包含關聯資訊
        """
        data = {
            'id': self.id,
            'secure_code': self.secure_code,
            'org_secure_code': self.org_secure_code,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,

            # 表單資訊
            'form_template_id': self.form_template_id,
            'form_template_secure_code': self.form_template_secure_code,
            'form_template_code': self.form_template_code,
            'form_template_version': self.form_template_version,

            # 流程資訊
            'workflow_template_id': self.workflow_template_id,
            'workflow_template_secure_code': self.workflow_template_secure_code,
            'workflow_template_code': self.workflow_template_code,
            'workflow_template_version': self.workflow_template_version,

            # 狀態
            'is_active': self.is_active,
            'priority': self.priority,
            'is_published': self.is_published,
            'publish_at': self.publish_at.isoformat() if self.publish_at else None,

            # 條件
            'trigger_condition': self.trigger_condition,
            'description': self.description,
        }

        return data

    @classmethod
    def get_mappings_for_form(cls, form_template_id: int, org_secure_code: str):
        """
        取得指定表單的所有配對

        Args:
            form_template_id: 表單模板 ID
            org_secure_code: 組織代碼

        Returns:
            list[FwFormWorkflowMapping]
        """
        return cls.query.filter_by(
            form_template_id=form_template_id,
            org_secure_code=org_secure_code,
            is_deleted=False
        ).order_by(cls.priority.desc()).all()

    @classmethod
    def get_active_mapping(cls, form_template_id: int, org_secure_code: str, form_data: dict = None):
        """
        取得指定表單的有效配對（考慮條件觸發）

        Args:
            form_template_id: 表單模板 ID
            org_secure_code: 組織代碼
            form_data: 表單資料（用於條件判斷）

        Returns:
            FwFormWorkflowMapping or None
        """
        mappings = cls.get_mappings_for_form(form_template_id, org_secure_code)

        for mapping in mappings:
            if not mapping.is_active:
                continue

            # 如果沒有條件，直接返回
            if not mapping.trigger_condition:
                return mapping

            # 有條件時，評估條件
            if cls._evaluate_condition(mapping.trigger_condition, form_data):
                return mapping

        # 如果沒有符合條件的配對，返回第一個有效的
        for mapping in mappings:
            if mapping.is_active:
                return mapping

        return None

    @staticmethod
    def _evaluate_condition(condition: dict, form_data: dict) -> bool:
        """
        評估觸發條件

        簡單的條件評估，支援：
        - field: 欄位名稱
        - operator: 運算符（eq, ne, gt, lt, gte, lte, contains）
        - value: 比較值

        Args:
            condition: 條件定義
            form_data: 表單資料

        Returns:
            bool: 條件是否符合
        """
        if not condition or not form_data:
            return True

        field = condition.get('field')
        operator = condition.get('operator', 'eq')
        value = condition.get('value')

        if not field:
            return True

        field_value = form_data.get(field)

        if operator == 'eq':
            return field_value == value
        elif operator == 'ne':
            return field_value != value
        elif operator == 'gt':
            return field_value > value if field_value is not None else False
        elif operator == 'lt':
            return field_value < value if field_value is not None else False
        elif operator == 'gte':
            return field_value >= value if field_value is not None else False
        elif operator == 'lte':
            return field_value <= value if field_value is not None else False
        elif operator == 'contains':
            return value in str(field_value) if field_value is not None else False

        return True


# 自動生成 secure_code
@event.listens_for(FwFormWorkflowMapping, 'before_insert')
def generate_mapping_secure_code(mapper, connection, target):
    """插入前自動生成 secure_code"""
    if not target.secure_code:
        target.secure_code = secrets.token_urlsafe(16)
