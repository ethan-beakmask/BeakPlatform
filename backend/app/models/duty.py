"""
BeakMask Duty Model
職務管理 Model

職務（Duty）是組織架構中的職責標籤，用於標記用戶在部門中的特定職責。

與其他概念的區別：
- 職稱（JobTitle）：HR 結構中的正式頭銜（經理、工程師）
- 角色（Role）：系統權限控制（表單審核者、模組管理員）
- 職務（Duty）：部門內的職責標籤（防火牆管理員、log稽核）

唯一性設計：
- 同一部門 + 同一分類 + 同一名稱 = 唯一
- 允許不同部門有相同名稱的職務（如：各部門都可以有「窗口」）

權限設計：
- 預設由部門主管有權限設定
"""
from typing import Dict, Any, List

from sqlalchemy import Column, String, Text, Integer, UniqueConstraint
from sqlalchemy.orm import relationship

from .base import TenantBaseModel
from .. import db


class DutyCategory(TenantBaseModel):
    """
    職務分類 Model

    用於分類職務，避免同名職務混亂。
    例如：
    - 技術類：防火牆管理員、網路管理員、系統維護員
    - 管理類：專案窗口、採購審核員
    - 稽核類：log稽核、資安稽核員
    """
    __tablename__ = 'duty_categories'

    # 分類代碼（組織內唯一）
    code = Column(String(50), nullable=False, index=True, comment='分類代碼')

    # 分類名稱
    name = Column(String(100), nullable=False, comment='分類名稱')

    # 描述
    description = Column(Text, nullable=True, comment='分類描述')

    # 排序順序
    sort_order = Column(Integer, default=0, nullable=False, comment='排序順序')

    # 是否啟用
    is_active = Column(db.Boolean, default=True, nullable=False, comment='是否啟用')

    # 關聯：該分類下的職務
    duties = relationship('Duty', back_populates='category', lazy='dynamic')

    __table_args__ = (
        UniqueConstraint('org_secure_code', 'code', name='uq_duty_category_code'),
    )

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            'code': self.code,
            'name': self.name,
            'description': self.description,
            'sort_order': self.sort_order,
            'is_active': self.is_active,
        })
        return base

    def __repr__(self):
        return f'<DutyCategory {self.code}:{self.name}>'


class Duty(TenantBaseModel):
    """
    職務 Model

    職務依附於：
    1. 部門（unit_secure_code）- 必填
    2. 分類（category_secure_code）- 必填
    3. 名稱（name）- 必填

    唯一性：(部門 + 分類 + 名稱) 組合唯一
    這樣允許：
    - 不同部門有相同名稱的職務
    - 同部門但不同分類有相同名稱的職務
    """
    __tablename__ = 'duties'

    # 所屬部門
    unit_secure_code = Column(
        String(32),
        db.ForeignKey('organizational_units.secure_code'),
        nullable=False,
        index=True,
        comment='所屬部門'
    )

    # 職務分類
    category_secure_code = Column(
        String(32),
        db.ForeignKey('duty_categories.secure_code'),
        nullable=False,
        index=True,
        comment='職務分類'
    )

    # 職務名稱
    name = Column(String(100), nullable=False, comment='職務名稱')

    # 描述
    description = Column(Text, nullable=True, comment='職務描述')

    # 排序順序
    sort_order = Column(Integer, default=0, nullable=False, comment='排序順序')

    # 是否啟用
    is_active = Column(db.Boolean, default=True, nullable=False, comment='是否啟用')

    # 關聯
    unit = relationship('OrganizationalUnit', foreign_keys=[unit_secure_code])
    category = relationship('DutyCategory', back_populates='duties', foreign_keys=[category_secure_code])

    # 擁有此職務的用戶（多對多，之後實作）
    # user_duties = relationship('UserDuty', back_populates='duty')

    __table_args__ = (
        # 唯一約束：部門 + 分類 + 名稱
        UniqueConstraint(
            'unit_secure_code', 'category_secure_code', 'name',
            name='uq_duty_unit_category_name'
        ),
    )

    def to_dict(self, include_relations: bool = True) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            'unit_secure_code': self.unit_secure_code,
            'category_secure_code': self.category_secure_code,
            'name': self.name,
            'description': self.description,
            'sort_order': self.sort_order,
            'is_active': self.is_active,
        })

        if include_relations:
            if self.unit:
                base['unit'] = {
                    'secure_code': self.unit.secure_code,
                    'name': self.unit.name,
                    'code': self.unit.code,
                }
            if self.category:
                base['category'] = {
                    'secure_code': self.category.secure_code,
                    'name': self.category.name,
                    'code': self.category.code,
                }

        return base

    def __repr__(self):
        return f'<Duty {self.name}>'


# 預設職務分類（供 seed 使用）
DEFAULT_DUTY_CATEGORIES = [
    {'code': 'TECH', 'name': '技術類', 'description': '技術相關職務，如系統管理、網路管理'},
    {'code': 'AUDIT', 'name': '稽核類', 'description': '稽核相關職務，如 log 稽核、資安稽核'},
    {'code': 'ADMIN', 'name': '行政類', 'description': '行政相關職務，如窗口、協調員'},
    {'code': 'MGMT', 'name': '管理類', 'description': '管理相關職務，如專案管理、採購審核'},
]
