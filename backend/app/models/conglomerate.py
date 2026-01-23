"""
BeakMask Conglomerate Model
集團 Model

集團是多個企業的聯合體，用於：
- 大集團的子公司管理
- 關係緊密的供應鏈合作
- 跨企業資料共享（透過獨立的共享資料庫）
"""
from typing import Dict, Any, Optional

from sqlalchemy import Column, String, Boolean, Text
from sqlalchemy.orm import relationship

from .base import BaseModel


class Conglomerate(BaseModel):
    """
    集團 Model

    集團不直接存放業務資料，而是：
    1. 記錄哪些企業屬於同一集團
    2. 管理集團共享資料庫的連線資訊
    3. 提供集團層級的管理功能

    資料共享機制：
    - 每個集團可有獨立的共享資料庫
    - 企業透過流程系統的 SQL Node 讀寫共享資料
    - 共享資料庫的 Schema 複製自本系統表結構
    """
    __tablename__ = 'conglomerates'

    # 集團代碼 (唯一，用於內部識別)
    code = Column(String(50), unique=True, nullable=False, index=True)

    # 集團名稱
    name = Column(String(255), nullable=False)

    # 集團描述
    description = Column(Text, nullable=True)

    # 是否啟用
    is_active = Column(Boolean, default=True, nullable=False)

    # === 共享資料庫連線資訊 ===
    # 由系統管理員手動建立資料庫後填入
    # 連線資訊加密存放

    # 資料庫主機
    shared_db_host = Column(String(255), nullable=True)

    # 資料庫連接埠
    shared_db_port = Column(String(10), nullable=True)

    # 資料庫名稱
    shared_db_name = Column(String(100), nullable=True)

    # 資料庫使用者（該集團專用，權限受限）
    shared_db_user = Column(String(100), nullable=True)

    # 資料庫密碼（加密存放）
    shared_db_password_encrypted = Column(Text, nullable=True)

    # 是否已設定共享資料庫
    has_shared_db = Column(Boolean, default=False, nullable=False)

    # 關聯
    organizations = relationship(
        'Organization',
        back_populates='conglomerate',
        lazy='dynamic'
    )

    @property
    def organization_count(self) -> int:
        """取得集團內企業數量"""
        return self.organizations.filter_by(is_deleted=False).count()

    @property
    def active_organization_count(self) -> int:
        """取得集團內啟用的企業數量"""
        return self.organizations.filter_by(
            is_deleted=False,
            is_active=True
        ).count()

    def get_shared_db_config(self) -> Optional[Dict[str, str]]:
        """
        取得共享資料庫連線設定

        Returns:
            dict: 連線設定，若未設定則返回 None
        """
        if not self.has_shared_db:
            return None

        # TODO: 解密 shared_db_password_encrypted
        return {
            'host': self.shared_db_host,
            'port': self.shared_db_port or '5432',
            'database': self.shared_db_name,
            'user': self.shared_db_user,
            # 'password': decrypt(self.shared_db_password_encrypted)
        }

    def to_dict(self, include_db_info: bool = False) -> Dict[str, Any]:
        """
        轉換為字典

        Args:
            include_db_info: 是否包含資料庫連線資訊（僅系統管理員可見）
        """
        base = super().to_dict()
        base.update({
            'code': self.code,
            'name': self.name,
            'description': self.description,
            'is_active': self.is_active,
            'has_shared_db': self.has_shared_db,
            'organization_count': self.organization_count,
        })

        if include_db_info and self.has_shared_db:
            base.update({
                'shared_db_host': self.shared_db_host,
                'shared_db_port': self.shared_db_port,
                'shared_db_name': self.shared_db_name,
                'shared_db_user': self.shared_db_user,
                # 不輸出密碼
            })

        return base

    def __repr__(self):
        return f'<Conglomerate {self.code} ({self.name})>'
