"""
BeakPlatform EmployeePosition Model
員工職位 Model - 紀錄員工的職位指派

一個員工可以有多個職位：
1. 主要職位 (Primary Position) - 正式職務
2. 兼任職位 (Concurrent Position) - 在其他部門兼任
3. 代理職位 (Acting Position) - 暫時代理

每個職位指派都有：
- 所屬部門
- 職稱（決定職等和簽核權限）
- 有效期限
- 是否為主管
"""
from datetime import date, datetime
from typing import Dict, Any, Optional

from sqlalchemy import Column, String, Integer, Boolean, Date, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship

from .base import TenantBaseModel
from .. import db


class PositionType:
    """職位類型"""
    PRIMARY = 'PRIMARY'          # 主要職位
    CONCURRENT = 'CONCURRENT'    # 兼任職位
    ACTING = 'ACTING'            # 代理職位
    TEMPORARY = 'TEMPORARY'      # 臨時指派


class EmployeePosition(TenantBaseModel):
    """
    員工職位 Model

    紀錄員工在組織中擔任的職位，支援：
    - 一人多職（主要職位 + 兼任）
    - 有效期限（兼任、代理通常有期限）
    - 直屬主管關係
    """
    __tablename__ = 'employee_positions'

    # 員工
    user_secure_code = Column(
        String(32),
        ForeignKey('users.secure_code'),
        nullable=False,
        index=True
    )

    # 職稱
    job_title_secure_code = Column(
        String(32),
        ForeignKey('job_titles.secure_code'),
        nullable=False,
        index=True
    )

    # 所屬部門
    unit_secure_code = Column(
        String(32),
        ForeignKey('organizational_units.secure_code'),
        nullable=False,
        index=True
    )

    # 職位類型
    position_type = Column(
        String(20),
        default=PositionType.PRIMARY,
        nullable=False,
        index=True
    )

    # 是否為該部門主管
    is_unit_head = Column(Boolean, default=False, nullable=False)

    # 直屬主管 (員工 secure_code)
    # 這是最重要的欄位！表單簽核會用到
    direct_manager_secure_code = Column(
        String(32),
        ForeignKey('users.secure_code'),
        nullable=True,
        index=True
    )

    # 虛線主管 (Matrix 組織用，如專案主管)
    dotted_line_manager_secure_code = Column(
        String(32),
        ForeignKey('users.secure_code'),
        nullable=True,
        index=True
    )

    # 有效期限
    effective_from = Column(Date, nullable=False, default=date.today)
    effective_until = Column(Date, nullable=True)  # NULL = 無期限

    # 指派原因/備註
    remarks = Column(Text, nullable=True)

    # 指派者
    assigned_by = Column(String(100), nullable=True)
    assigned_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # 是否啟用
    is_active = Column(Boolean, default=True, nullable=False)

    # 關聯
    user = relationship('User', foreign_keys=[user_secure_code],
                       backref=db.backref('positions', lazy='dynamic'))
    job_title = relationship('JobTitle', back_populates='employees')
    unit = relationship('OrganizationalUnit', foreign_keys=[unit_secure_code])
    direct_manager = relationship('User', foreign_keys=[direct_manager_secure_code])
    dotted_line_manager = relationship('User', foreign_keys=[dotted_line_manager_secure_code])

    @property
    def is_primary(self) -> bool:
        """是否為主要職位"""
        return self.position_type == PositionType.PRIMARY

    @property
    def is_concurrent(self) -> bool:
        """是否為兼任職位"""
        return self.position_type == PositionType.CONCURRENT

    @property
    def is_acting(self) -> bool:
        """是否為代理職位"""
        return self.position_type == PositionType.ACTING

    @property
    def is_valid(self) -> bool:
        """檢查職位是否在有效期內"""
        today = date.today()
        if self.effective_from and today < self.effective_from:
            return False
        if self.effective_until and today > self.effective_until:
            return False
        return self.is_active

    @property
    def job_level_order(self) -> int:
        """取得職等數值（用於比較）"""
        if self.job_title and self.job_title.job_level:
            return self.job_title.job_level.level_order
        return 0

    @property
    def approval_limit(self):
        """取得簽核權限金額"""
        if self.job_title and self.job_title.job_level:
            return self.job_title.job_level.approval_limit
        return None

    def get_manager_chain(self) -> list:
        """
        取得主管鏈（往上追溯到最高主管）

        Returns:
            List[User]: 從直屬主管到最高主管的列表
        """
        chain = []
        visited = set()
        current_manager = self.direct_manager

        while current_manager and current_manager.secure_code not in visited:
            chain.append(current_manager)
            visited.add(current_manager.secure_code)

            # 找該主管的主要職位
            manager_position = EmployeePosition.query.filter(
                EmployeePosition.user_secure_code == current_manager.secure_code,
                EmployeePosition.position_type == PositionType.PRIMARY,
                EmployeePosition.is_active == True,
                EmployeePosition.is_deleted == False
            ).first()

            if manager_position:
                current_manager = manager_position.direct_manager
            else:
                break

        return chain

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            'user_id': self.user_secure_code,
            'job_title_id': self.job_title_secure_code,
            'unit_id': self.unit_secure_code,
            'position_type': self.position_type,
            'is_unit_head': self.is_unit_head,
            'is_primary': self.is_primary,
            'is_valid': self.is_valid,
            'direct_manager_id': self.direct_manager_secure_code,
            'dotted_line_manager_id': self.dotted_line_manager_secure_code,
            'effective_from': self.effective_from.isoformat() if self.effective_from else None,
            'effective_until': self.effective_until.isoformat() if self.effective_until else None,
            'remarks': self.remarks,
            'is_active': self.is_active,
        })

        if self.job_title:
            base['job_title'] = {
                'id': self.job_title.secure_code,
                'name': self.job_title.name,
                'name_en': self.job_title.name_en,
                'level_order': self.job_level_order,
                'approval_limit': float(self.approval_limit) if self.approval_limit else None,
            }

        if self.unit:
            base['unit'] = {
                'id': self.unit.secure_code,
                'name': self.unit.name,
                'full_path': self.unit.full_path,
            }

        if self.direct_manager:
            base['direct_manager'] = {
                'id': self.direct_manager.secure_code,
                'name': self.direct_manager.display_name,
            }

        return base

    def __repr__(self):
        return f'<EmployeePosition {self.user_secure_code} -> {self.job_title_secure_code}>'
