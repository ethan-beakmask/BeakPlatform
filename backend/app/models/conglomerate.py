"""
BeakMask Conglomerate Model
集團 Model

集團是企業分群概念，用於大集團的子公司管理、關係緊密的
供應鏈合作，以及平台管理上的企業歸類；它不提供跨企業共用資料庫。

2026-09-13 定案（BBN 待辦 PF-269）：
- spec_formulate（規格制定模組）保留，其 DDL 注入問題另案 PF-268 白名單化。
- 集團共用資料庫（Conglomerate shared DB，cg_<id> 庫）功能因安全因素整個移除：
  它讓多家企業共用一個 PostgreSQL 庫、只靠 RLS 隔離，且建表 DDL 走原樣內插，
  攻擊面不值得保留。dev 與 BeakPlatform-VM 兩個環境都是 0 個集團、0 個 cg_* 庫，沒有資料要遷移。
- 「集團」作為企業分群的概念保留（conglomerates / conglomerate_logs 表、
  organizations.conglomerate_secure_code、企業列表的 [集團設定]／篩選／徽章、部門頁顯示集團名）。
  只拿掉「共用 DB」那一半。

共用資料庫功能已於 2026-09-13 依 PF-269 移除（安全因素），不要復活。
"""
from typing import Dict, Any

from sqlalchemy import Column, String, Boolean, Text
from sqlalchemy.orm import relationship

from .base import BaseModel


class Conglomerate(BaseModel):
    """
    集團 Model

    集團只作為企業分群，不直接存放業務資料：
    1. 記錄哪些企業屬於同一集團
    2. 提供集團層級的管理功能

    2026-09-13 定案（BBN 待辦 PF-269）：
    - spec_formulate（規格制定模組）保留，其 DDL 注入問題另案 PF-268 白名單化。
    - 集團共用資料庫（Conglomerate shared DB，cg_<id> 庫）功能因安全因素整個移除：
      它讓多家企業共用一個 PostgreSQL 庫、只靠 RLS 隔離，且建表 DDL 走原樣內插，
      攻擊面不值得保留。dev 與 BeakPlatform-VM 兩個環境都是 0 個集團、0 個 cg_* 庫，沒有資料要遷移。
    - 「集團」作為企業分群的概念保留（conglomerates / conglomerate_logs 表、
      organizations.conglomerate_secure_code、企業列表的 [集團設定]／篩選／徽章、部門頁顯示集團名）。
      只拿掉「共用 DB」那一半。

    共用資料庫功能已於 2026-09-13 依 PF-269 移除（安全因素），不要復活。
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

    def to_dict(self) -> Dict[str, Any]:
        """轉換為字典"""
        base = super().to_dict()
        base.update({
            'code': self.code,
            'name': self.name,
            'description': self.description,
            'is_active': self.is_active,
            'organization_count': self.organization_count,
        })

        return base

    def __repr__(self):
        return f'<Conglomerate {self.code} ({self.name})>'
