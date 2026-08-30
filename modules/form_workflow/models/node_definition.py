"""
FormWorkflow Module - Node Definition Model
工作流程節點定義

此表為 SYSTEM scope，org_secure_code 為 nullable，
因此繼承 BaseModel 而非 ModuleBaseModel。
"""
from sqlalchemy import Column, String, Text, Boolean, Integer
from sqlalchemy.dialects.postgresql import JSONB

from app.models.base import BaseModel


class WorkflowNodeDefinition(BaseModel):
    """
    工作流程節點定義

    作為 node type 的 single source of truth，
    API 直接查此表回傳節點定義，不再硬編碼。
    """
    __tablename__ = 'workflow_node_definitions'

    node_type = Column(String(100), unique=True, nullable=False, index=True)
    is_active = Column(Boolean, nullable=False, default=True)
    scope = Column(String(20), nullable=False, default='SYSTEM')
    org_secure_code = Column(String(32), nullable=True, index=True)
    category = Column(String(100), nullable=False)
    display_name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    icon = Column(String(200), nullable=True)
    execution_handler = Column(String(200), nullable=False)
    config_schema = Column(JSONB, nullable=True)

    # Canvas 顯示屬性
    canvas_shape = Column(String(50), default='roundrectangle')
    canvas_color = Column(String(50), default='#3B82F6')
    canvas_width = Column(Integer, default=120)
    canvas_height = Column(Integer, default=60)

    # 連線限制
    max_input_connections = Column(Integer, default=-1)
    max_output_connections = Column(Integer, default=-1)

    # 逾時設定
    default_timeout_seconds = Column(Integer, default=120)
    max_timeout_seconds = Column(Integer, default=3600)

    # 權限
    require_system_admin = Column(Boolean, nullable=False, default=False)
    # 企業授權：True 表示此節點型別必須在 workflow_node_org_grants 有該企業的
    # 授權記錄才可見／可用（OsExecutor、FileRead 這類主機側節點）
    org_restricted = Column(Boolean, nullable=False, default=False)

    # is_active, is_deleted 已由 BaseModel 提供

    def to_api_dict(self):
        """
        回傳與原 _get_node_definitions() 相同的 dict 結構，
        確保 API 回傳格式不變。
        """
        return {
            'node_type': self.node_type,
            'display_name': self.display_name,
            'description': self.description or '',
            'icon': self.icon or '',
            'category': self.category,
            'config_schema': self.config_schema or {},
            'is_active': self.is_active,
            'require_system_admin': self.require_system_admin,
        }
