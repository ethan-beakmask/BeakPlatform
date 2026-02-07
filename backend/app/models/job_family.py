"""
BeakPlatform JobFamily Model
職系 Model - 定義職涯發展軌道

參考：OG-01-01 公司職稱職等對照表

職系是「專業領域」的概念，代表不同的職涯發展軌道：
1. 管理職 (People Manager) - 帶人主管
2. 專業職 (Individual Contributor) - 不帶人的專業人員
   - 業務職 (Sales)
   - 客服職 (Customer Service)
   - 行政職 (Administration)
   - 工程技術職 (Technical)

雙軌制：
- 員工可選擇往「管理職」或「專業職」發展
- 兩條軌道的職等是對等的（如：經理 = 專案經理）
"""
from typing import Dict, Any, List

from sqlalchemy import Column, String, Integer, Boolean, Text, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from .base import TenantBaseModel
from .mixins import I18nMixin
from .. import db


class JobFamilyType:
    """職系類型"""
    MANAGER = 'MANAGER'          # 管理職 (People Manager)
    PROFESSIONAL = 'PROFESSIONAL'  # 專業職 (Individual Contributor)


class JobFamily(TenantBaseModel, I18nMixin):
    """
    職系 Model

    職系代表專業領域/職涯軌道：
    - 管理職 (MANAGER): 帶人主管軌道
    - 專業職 (PROFESSIONAL): 不帶人的專業軌道

    支援樹狀結構：
    - 專業職下可細分：業務職、客服職、行政職、工程技術職
    """
    __tablename__ = 'job_families'

    # 職系類型
    family_type = Column(
        String(20),
        default=JobFamilyType.PROFESSIONAL,
        nullable=False,
        index=True
    )

    # 職系代碼 (如: MGR, SALES, CS, ADMIN, TECH)
    code = Column(String(20), nullable=False, index=True)

    # 職系名稱 (中文)
    name = Column(String(100), nullable=False)

    # 多語系名稱 (JSONB: {"en": "...", "zh-CN": "...", "ja": "..."})
    name_i18n = Column(JSONB, nullable=True, default=dict)

    # [向下相容] 舊欄位 — 新程式碼請用 name_i18n
    name_en = Column(String(100), nullable=True)

    # I18nMixin 向下相容映射
    _I18N_LEGACY_FIELD_MAP = {'en': 'name_en'}

    # 父職系 (用於細分，如 PROFESSIONAL 下有 SALES, CS, ADMIN, TECH)
    parent_secure_code = Column(
        String(32),
        ForeignKey('job_families.secure_code', use_alter=True, name='fk_job_family_parent'),
        nullable=True,
        index=True
    )

    # 描述
    description = Column(Text, nullable=True)

    # 排序順序
    sort_order = Column(Integer, default=0, nullable=False)

    # 是否為系統預設 (不可刪除)
    is_system_default = Column(Boolean, default=False, nullable=False)

    # 是否啟用
    is_active = Column(Boolean, default=True, nullable=False)

    # 關聯
    parent = relationship(
        'JobFamily',
        remote_side='JobFamily.secure_code',
        backref='children',
        foreign_keys=[parent_secure_code]
    )

    # 此職系的所有職稱
    job_titles = relationship('JobTitle', back_populates='job_family')

    @property
    def is_manager_track(self) -> bool:
        """是否為管理職軌道"""
        return self.family_type == JobFamilyType.MANAGER

    @property
    def is_professional_track(self) -> bool:
        """是否為專業職軌道"""
        return self.family_type == JobFamilyType.PROFESSIONAL

    def to_dict(self, include_children: bool = False) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            'family_type': self.family_type,
            'code': self.code,
            'name': self.name,
            'name_i18n': self.name_i18n or {},
            'name_en': self.name_en,
            'description': self.description,
            'is_system_default': self.is_system_default,
            'is_active': self.is_active,
            'parent_id': self.parent_secure_code,
        })

        if include_children:
            base['children'] = [
                child.to_dict(include_children=True)
                for child in self.children
                if not child.is_deleted
            ]

        return base

    def __repr__(self):
        return f'<JobFamily {self.code}: {self.name}>'


# 預設職系資料 (供 seed 使用)
DEFAULT_JOB_FAMILIES = [
    # 管理職
    {
        'code': 'MGR',
        'name': '管理職',
        'name_en': 'People Manager',
        'family_type': JobFamilyType.MANAGER,
        'description': '帶人主管，負責團隊管理與人員發展',
        'parent_code': None,
    },
    # 專業職（根）
    {
        'code': 'PROF',
        'name': '專業職',
        'name_en': 'Individual Contributor',
        'family_type': JobFamilyType.PROFESSIONAL,
        'description': '不帶人的專業人員，專注於專業技能發展',
        'parent_code': None,
    },
    # 專業職細分
    {
        'code': 'SALES',
        'name': '業務職',
        'name_en': 'Sales Position',
        'family_type': JobFamilyType.PROFESSIONAL,
        'description': '負責業務開發與客戶關係維護',
        'parent_code': 'PROF',
    },
    {
        'code': 'CS',
        'name': '客服職',
        'name_en': 'Customer Service Position',
        'family_type': JobFamilyType.PROFESSIONAL,
        'description': '負責客戶服務與問題處理',
        'parent_code': 'PROF',
    },
    {
        'code': 'ADMIN',
        'name': '行政職',
        'name_en': 'Administration Position',
        'family_type': JobFamilyType.PROFESSIONAL,
        'description': '負責行政支援與內部管理',
        'parent_code': 'PROF',
    },
    {
        'code': 'TECH',
        'name': '工程技術職',
        'name_en': 'Technical Position',
        'family_type': JobFamilyType.PROFESSIONAL,
        'description': '負責技術研發與工程實作',
        'parent_code': 'PROF',
    },
]
