"""
BeakMask JobTitle Model
職稱 Model - 定義具體的職位名稱

參考：OG-01-01 公司職稱職等對照表

職稱是「職等 + 職系」的具體組合：
- 經理 (Manager) = L5 經理級 + 管理職
- 專案經理 (Project Manager) = L5 經理級 + 工程技術職
- 業務代表 (Sales Representative) = L1 職員級 + 業務職

職稱決定：
1. 企業成員在組織中的正式頭銜
2. 對應的職等（決定簽核權限）
3. 對應的職系（決定職涯發展路線）
"""
from typing import Dict, Any

from sqlalchemy import Column, String, Integer, Boolean, Text, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from .base import TenantBaseModel
from .mixins import I18nMixin
from .. import db


class JobTitle(TenantBaseModel, I18nMixin):
    """
    職稱 Model

    職稱 = 職等 + 職系 的具體組合

    範例：
    - 總經理 (President) = L9 + 管理職
    - 資深顧問 (Senior Consultant) = L8 + 專業職
    - 業務代表 (Sales Representative) = L1 + 業務職
    """
    __tablename__ = 'job_titles'

    # 職稱代碼 (如: PRES, MGR, SR_ENG)
    code = Column(String(30), nullable=False, index=True)

    # 職稱名稱 (中文)
    name = Column(String(100), nullable=False)

    # 多語系名稱 (JSONB: {"en": "...", "zh-CN": "...", "ja": "..."})
    name_i18n = Column(JSONB, nullable=True, default=dict)

    # [向下相容] 舊欄位 — 新程式碼請用 name_i18n
    name_en = Column(String(100), nullable=True)

    # I18nMixin 向下相容映射
    _I18N_LEGACY_FIELD_MAP = {'en': 'name_en'}

    # 職稱簡稱 (用於顯示)
    short_name = Column(String(50), nullable=True)

    # 對應職等
    job_level_secure_code = Column(
        String(32),
        ForeignKey('job_levels.secure_code'),
        nullable=False,
        index=True
    )

    # 對應職系
    job_family_secure_code = Column(
        String(32),
        ForeignKey('job_families.secure_code'),
        nullable=False,
        index=True
    )

    # 描述 (職責說明)
    description = Column(Text, nullable=True)

    # 是否為主管職稱 (帶人)
    is_supervisor = Column(Boolean, default=False, nullable=False)

    # 排序順序
    sort_order = Column(Integer, default=0, nullable=False)

    # 是否為系統預設 (不可刪除)
    is_system_default = Column(Boolean, default=False, nullable=False)

    # 是否啟用
    is_active = Column(Boolean, default=True, nullable=False)

    # 關聯
    job_level = relationship('JobLevel', back_populates='job_titles')
    job_family = relationship('JobFamily', back_populates='job_titles')

    # 擁有此職稱的企業成員
    employees = relationship('EmployeePosition', back_populates='job_title')

    @property
    def full_name(self) -> str:
        """完整名稱（中英文）"""
        if self.name_en:
            return f'{self.name} ({self.name_en})'
        return self.name

    @property
    def level_order(self) -> int:
        """取得職等數值"""
        return self.job_level.level_order if self.job_level else 0

    @property
    def approval_limit(self):
        """取得簽核權限金額"""
        return self.job_level.approval_limit if self.job_level else None

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            'code': self.code,
            'name': self.name,
            'name_i18n': self.name_i18n or {},
            'name_en': self.name_en,
            'short_name': self.short_name,
            'full_name': self.full_name,
            'description': self.description,
            'is_supervisor': self.is_supervisor,
            'is_system_default': self.is_system_default,
            'is_active': self.is_active,
            'job_level_id': self.job_level_secure_code,
            'job_family_id': self.job_family_secure_code,
        })

        if self.job_level:
            base['job_level'] = {
                'id': self.job_level.secure_code,
                'code': self.job_level.code,
                'name': self.job_level.name,
                'level_order': self.job_level.level_order,
                'approval_limit': float(self.job_level.approval_limit) if self.job_level.approval_limit else None,
            }

        if self.job_family:
            base['job_family'] = {
                'id': self.job_family.secure_code,
                'code': self.job_family.code,
                'name': self.job_family.name,
                'family_type': self.job_family.family_type,
            }

        return base

    def __repr__(self):
        return f'<JobTitle {self.code}: {self.name}>'


# 預設職稱資料 (供 seed 使用，對應 PDF 表格)
# 職等使用等距跳號：L000, L100, L200, L300, L400, L500, L600, L700, L800, L900
DEFAULT_JOB_TITLES = [
    # L900 - 總經理級
    {'code': 'PRES', 'name': '總經理', 'name_en': 'President', 'level': 'L900', 'family': 'MGR', 'is_supervisor': True},
    {'code': 'EVP', 'name': '執行副總經理', 'name_en': 'Executive Vice President', 'level': 'L900', 'family': 'MGR', 'is_supervisor': True},

    # L800 - 副總經理級
    {'code': 'SVP', 'name': '資深副總經理', 'name_en': 'Senior Vice President', 'level': 'L800', 'family': 'MGR', 'is_supervisor': True},
    {'code': 'VP', 'name': '副總經理', 'name_en': 'Vice President', 'level': 'L800', 'family': 'MGR', 'is_supervisor': True},
    {'code': 'SR_CONSULT', 'name': '資深顧問', 'name_en': 'Senior Consultant', 'level': 'L800', 'family': 'PROF', 'is_supervisor': False},
    {'code': 'CONSULT', 'name': '顧問', 'name_en': 'Consultant', 'level': 'L800', 'family': 'PROF', 'is_supervisor': False},
    {'code': 'CHIEF_ENG', 'name': '總工程師', 'name_en': 'Chief Engineer', 'level': 'L800', 'family': 'TECH', 'is_supervisor': False},

    # L700 - 處長級
    {'code': 'SR_DIR', 'name': '資深處長', 'name_en': 'Senior Director', 'level': 'L700', 'family': 'MGR', 'is_supervisor': True},
    {'code': 'DIR', 'name': '處長', 'name_en': 'Director', 'level': 'L700', 'family': 'MGR', 'is_supervisor': True},
    {'code': 'SR_SA', 'name': '資深特別助理', 'name_en': 'Senior Special Assistant', 'level': 'L700', 'family': 'PROF', 'is_supervisor': False},
    {'code': 'DEP_CHIEF_ENG', 'name': '副總工程師', 'name_en': 'Deputy Chief Engineer', 'level': 'L700', 'family': 'TECH', 'is_supervisor': False},

    # L600 - 副處長級
    {'code': 'DEP_DIR', 'name': '副處長', 'name_en': 'Deputy Director', 'level': 'L600', 'family': 'MGR', 'is_supervisor': True},
    {'code': 'SA', 'name': '特別助理', 'name_en': 'Special Assistant', 'level': 'L600', 'family': 'PROF', 'is_supervisor': False},

    # L500 - 經理級
    {'code': 'MGR', 'name': '經理', 'name_en': 'Manager', 'level': 'L500', 'family': 'MGR', 'is_supervisor': True},
    {'code': 'PM', 'name': '專案經理', 'name_en': 'Project Manager', 'level': 'L500', 'family': 'PROF', 'is_supervisor': False},
    {'code': 'PM_TECH', 'name': '專案經理', 'name_en': 'Project Manager', 'level': 'L500', 'family': 'TECH', 'is_supervisor': False},

    # L400 - 副理級
    {'code': 'ASST_MGR', 'name': '副理', 'name_en': 'Assistant Manager', 'level': 'L400', 'family': 'MGR', 'is_supervisor': True},
    {'code': 'ASST_PM', 'name': '專案副理', 'name_en': 'Assistant Project Manager', 'level': 'L400', 'family': 'PROF', 'is_supervisor': False},
    {'code': 'ASST_PM_TECH', 'name': '專案副理', 'name_en': 'Project Assistant Manager', 'level': 'L400', 'family': 'TECH', 'is_supervisor': False},

    # L300 - 主任級
    {'code': 'SUPV', 'name': '主任', 'name_en': 'Supervisor', 'level': 'L300', 'family': 'MGR', 'is_supervisor': True},
    {'code': 'PL', 'name': '專案主任', 'name_en': 'Project Leader', 'level': 'L300', 'family': 'PROF', 'is_supervisor': False},
    {'code': 'PRIN_ENG', 'name': '主任工程師', 'name_en': 'Principal Engineer', 'level': 'L300', 'family': 'TECH', 'is_supervisor': False},

    # L200 - 高級職員級
    {'code': 'SR_SPEC', 'name': '高級專員', 'name_en': 'Senior Specialist', 'level': 'L200', 'family': 'PROF', 'is_supervisor': False},
    {'code': 'SR_SALES', 'name': '高級業務代表', 'name_en': 'Senior Sales Representative', 'level': 'L200', 'family': 'SALES', 'is_supervisor': False},
    {'code': 'SR_CS', 'name': '高級客服代表', 'name_en': 'Senior Customer Service Representative', 'level': 'L200', 'family': 'CS', 'is_supervisor': False},
    {'code': 'SR_ADMIN', 'name': '高級專員', 'name_en': 'Senior Specialist', 'level': 'L200', 'family': 'ADMIN', 'is_supervisor': False},
    {'code': 'SR_ENG', 'name': '高級工程師', 'name_en': 'Senior Engineer', 'level': 'L200', 'family': 'TECH', 'is_supervisor': False},
    {'code': 'SR_TECH_REP', 'name': '高級技術代表', 'name_en': 'Senior Technical Representative', 'level': 'L200', 'family': 'TECH', 'is_supervisor': False},

    # L100 - 職員級
    {'code': 'SPEC', 'name': '專員', 'name_en': 'Specialist', 'level': 'L100', 'family': 'PROF', 'is_supervisor': False},
    {'code': 'SALES', 'name': '業務代表', 'name_en': 'Sales Representative', 'level': 'L100', 'family': 'SALES', 'is_supervisor': False},
    {'code': 'CSR', 'name': '客服代表', 'name_en': 'Customer Service Representative', 'level': 'L100', 'family': 'CS', 'is_supervisor': False},
    {'code': 'ADMIN_SPEC', 'name': '專員', 'name_en': 'Specialist', 'level': 'L100', 'family': 'ADMIN', 'is_supervisor': False},
    {'code': 'ENG', 'name': '專案工程師', 'name_en': 'Engineer', 'level': 'L100', 'family': 'TECH', 'is_supervisor': False},
    {'code': 'TECH_REP', 'name': '技術代表', 'name_en': 'Technical Representative', 'level': 'L100', 'family': 'TECH', 'is_supervisor': False},

    # L000 - 外部廠商
    {'code': 'CONTRACTOR', 'name': '約聘人員', 'name_en': 'Contractor', 'level': 'L000', 'family': 'PROF', 'is_supervisor': False},
    {'code': 'INTERN', 'name': '實習生', 'name_en': 'Intern', 'level': 'L000', 'family': 'PROF', 'is_supervisor': False},
    {'code': 'VENDOR', 'name': '廠商代表', 'name_en': 'Vendor Representative', 'level': 'L000', 'family': 'PROF', 'is_supervisor': False},
]
