"""
BeakMask Page Model
頁面 - No-Code Builder 生成的網頁
"""
from typing import Dict, Any

from sqlalchemy import Column, String, Boolean, Text, ForeignKey
from sqlalchemy.orm import relationship

from .base import TenantBaseModel


class Page(TenantBaseModel):
    """
    頁面 Model

    代表一個網頁，可由 No-Code Builder 生成。
    每個頁面有獨立的權限控制。

    page_type 說明:
    - 'list': 列表頁
    - 'detail': 詳情頁
    - 'form': 表單頁
    - 'dashboard': 儀表板
    - 'custom': 自訂頁面

    required_access 說明:
    - 'public': 不需登入
    - 'authenticated': 需登入
    - 'org_admin': 需企業管理員
    - 'system_admin': 需系統管理員
    """
    __tablename__ = 'pages'

    # 所屬模組
    module_secure_code = Column(
        String(32),
        ForeignKey('modules.secure_code'),
        nullable=True,
        index=True
    )

    # 頁面代碼 (企業內唯一)
    code = Column(String(50), nullable=False)

    # 頁面標題
    title = Column(String(200), nullable=False)

    # 頁面描述
    description = Column(Text, nullable=True)

    # 頁面類型
    page_type = Column(String(20), default='custom', nullable=False)

    # URL 路徑
    url_path = Column(String(255), nullable=False)

    # 對應的 Flask route (如果有)
    flask_route = Column(String(100), nullable=True)

    # 頁面模板 (Jinja2 template path 或 No-Code 設定 JSON)
    template = Column(Text, nullable=True)

    # Phase 1 簡化權限
    required_access = Column(String(20), default='authenticated', nullable=False)

    # 是否啟用
    is_active = Column(Boolean, default=True, nullable=False)

    # 頁面設定 (JSON - No-Code Builder 用)
    settings = Column(Text, nullable=True)

    # Relationships
    module = relationship('Module', back_populates='pages')

    # 權限等級對應 (用於快速比較)
    ACCESS_LEVELS = {
        'public': 3,
        'authenticated': 2,
        'org_admin': 1,
        'system_admin': 0,
    }

    def get_access_level(self) -> int:
        """取得數值化的存取等級 (數字越小權限越高)"""
        return self.ACCESS_LEVELS.get(self.required_access, 2)

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            'code': self.code,
            'title': self.title,
            'description': self.description,
            'page_type': self.page_type,
            'url_path': self.url_path,
            'flask_route': self.flask_route,
            'required_access': self.required_access,
            'is_active': self.is_active,
            'module_id': self.module_secure_code,
        })
        return base

    def __repr__(self):
        return f'<Page {self.code}: {self.url_path}>'
