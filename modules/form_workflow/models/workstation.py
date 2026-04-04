"""
FormWorkflow Module - Workstation Model
工作站定義（表單中心的專業視角）
"""
import secrets
from sqlalchemy import Column, String, Text, Boolean, Integer, event
from sqlalchemy.dialects.postgresql import JSON

from .base import ModuleBaseModel


class FwWorkstation(ModuleBaseModel):
    """
    工作站定義

    企業管理員可建立多個工作站，每個工作站是表單中心的一個篩選視角。
    例如：SOC 資安監控中心、客服調度中心。

    URL: /forms/center/<code>
    """
    __tablename__ = 'fw_workstations'

    # 工作站識別
    code = Column(String(50), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    description = Column(String(500), nullable=True)
    icon = Column(String(50), nullable=True)

    # 篩選規則（JSON）
    # {
    #   "categories": ["cat_sc_1", ...],      # 限定分類 secure_code
    #   "tags": ["TAG_CODE_1", ...],           # 限定標籤 code
    #   "source_types": ["SYSTEM", "WEB"],     # 限定來源類型
    #   "form_templates": ["ft_sc_1", ...],    # 白名單指定模板
    #   "match_mode": "all"                    # all=交集, any=聯集
    # }
    filter_rules = Column(JSON, nullable=False, default=dict)

    # UI 配置（JSON）
    # {
    #   "default_section": "pending",
    #   "sections": {
    #     "available": {"visible": true, "label": "可用表單"},
    #     "pending":   {"visible": true, "label": "待處理", "expanded": true},
    #     "tracking":  {"visible": true, "label": "追蹤中"},
    #     "history":   {"visible": true, "label": "歷史"}
    #   },
    #   "auto_refresh_interval": 5
    # }
    ui_config = Column(JSON, nullable=False, default=dict)

    # 狀態
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    display_order = Column(Integer, default=0)

    # 建立/編輯者
    created_by_secure_code = Column(String(32), nullable=True)
    created_by_name = Column(String(100), nullable=True)
    updated_by_secure_code = Column(String(32), nullable=True)
    updated_by_name = Column(String(100), nullable=True)

    def __repr__(self):
        return f'<FwWorkstation {self.code}: {self.name}>'

    def to_dict(self):
        data = super().to_dict()
        data.update({
            'code': self.code,
            'name': self.name,
            'description': self.description,
            'icon': self.icon,
            'filter_rules': self.filter_rules or {},
            'ui_config': self.ui_config or {},
            'is_active': self.is_active,
            'display_order': self.display_order,
            'created_by_name': self.created_by_name,
            'updated_by_name': self.updated_by_name,
        })
        return data


@event.listens_for(FwWorkstation, 'before_insert')
def generate_ws_secure_code(mapper, connection, target):
    if not target.secure_code:
        target.secure_code = secrets.token_urlsafe(16)
