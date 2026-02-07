"""
BeakMask JobLevel Model
職等 Model - 定義組織內的層級結構

參考：OG-01-01 公司職稱職等對照表

職等是「層級」的概念，決定：
1. 簽核權限金額上限
2. 在組織中的位階
3. 可管理的範圍（管理幅度）
"""
from typing import Dict, Any, Optional
from decimal import Decimal

from sqlalchemy import Column, String, Integer, Boolean, Text, Numeric
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from .base import TenantBaseModel
from .mixins import I18nMixin


class JobLevel(TenantBaseModel, I18nMixin):
    """
    職等 Model

    標準 9 級制：
    - 9: 總經理級 (President Level)
    - 8: 副總經理級 (Vice President Level)
    - 7: 處長級 (Director Level)
    - 6: 副處長級 (Deputy Director Level)
    - 5: 經理級 (Manager Level)
    - 4: 副理級 (Assistant Manager Level)
    - 3: 主任級 (Supervisor Level)
    - 2: 高級職員級 (Senior Staff Level)
    - 1: 職員級 (Staff Level)

    職等決定：
    - 簽核權限金額 (approval_limit)
    - 是否為管理職等 (is_manager_level)
    - 管理幅度 (management_scope)
    """
    __tablename__ = 'job_levels'

    # 職等代碼 (如: L1, L2, ... L9)
    code = Column(String(20), nullable=False, index=True)

    # 職等名稱 (中文)
    name = Column(String(100), nullable=False)

    # 多語系名稱 (JSONB: {"en": "...", "zh-CN": "...", "ja": "..."})
    name_i18n = Column(JSONB, nullable=True, default=dict)

    # [向下相容] 舊欄位 — 新程式碼請用 name_i18n
    name_en = Column(String(100), nullable=True)

    # I18nMixin 向下相容映射
    _I18N_LEGACY_FIELD_MAP = {'en': 'name_en'}

    # 職等數值 (用於比較，數字越大職等越高)
    level_order = Column(Integer, nullable=False, index=True)

    # 簽核權限金額上限 (NULL = 無上限)
    approval_limit = Column(Numeric(15, 2), nullable=True)

    # 簽核權限幣別 (預設 TWD)
    approval_currency = Column(String(3), default='TWD', nullable=False)

    # 是否為管理職等 (Level 3 以上通常是)
    is_manager_level = Column(Boolean, default=False, nullable=False)

    # 管理幅度說明
    management_scope = Column(String(100), nullable=True)

    # 描述
    description = Column(Text, nullable=True)

    # 排序順序 (顯示用)
    sort_order = Column(Integer, default=0, nullable=False)

    # 是否為系統預設 (不可刪除)
    is_system_default = Column(Boolean, default=False, nullable=False)

    # 是否啟用
    is_active = Column(Boolean, default=True, nullable=False)

    # 關聯：此職等的所有職稱
    job_titles = relationship('JobTitle', back_populates='job_level')

    # 關聯：此職等的核決權限上限 (按類別)
    approval_limits = relationship(
        'JobLevelApprovalLimit',
        back_populates='job_level',
        cascade='all, delete-orphan'
    )

    def can_approve_amount(self, amount: Decimal, currency: str = 'TWD') -> bool:
        """
        檢查此職等是否可簽核指定金額

        Args:
            amount: 金額
            currency: 幣別

        Returns:
            是否可簽核
        """
        if self.approval_limit is None:
            return True  # 無上限
        if currency != self.approval_currency:
            # TODO: 匯率轉換
            pass
        return amount <= self.approval_limit

    def is_higher_than(self, other: 'JobLevel') -> bool:
        """比較職等高低"""
        return self.level_order > other.level_order

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            'code': self.code,
            'name': self.name,
            'name_i18n': self.name_i18n or {},
            'name_en': self.name_en,
            'level_order': self.level_order,
            'approval_limit': float(self.approval_limit) if self.approval_limit else None,
            'approval_currency': self.approval_currency,
            'is_manager_level': self.is_manager_level,
            'management_scope': self.management_scope,
            'description': self.description,
            'is_system_default': self.is_system_default,
            'is_active': self.is_active,
        })
        return base

    @staticmethod
    def calculate_insert_order(lower_order: int, upper_order: int) -> int:
        """
        計算在兩個職等之間插入新職等的序號

        使用公式：(lower + upper) // 2 (無條件捨去)

        範例：
        - L100 和 L200 之間 → (100 + 200) // 2 = 150
        - L150 和 L200 之間 → (150 + 200) // 2 = 175
        - L175 和 L200 之間 → (175 + 200) // 2 = 187

        Args:
            lower_order: 較低職等的序號
            upper_order: 較高職等的序號

        Returns:
            建議的新職等序號

        Raises:
            ValueError: 如果無法再細分 (兩者差距 < 2)
        """
        if upper_order - lower_order < 2:
            raise ValueError(
                f'無法在 L{lower_order} 和 L{upper_order} 之間插入新職等，'
                f'差距太小。建議重新規劃職等序號。'
            )
        return (lower_order + upper_order) // 2

    @classmethod
    def suggest_new_level_code(cls, lower_order: int, upper_order: int) -> str:
        """
        建議新職等的代碼

        Args:
            lower_order: 較低職等的序號
            upper_order: 較高職等的序號

        Returns:
            建議的職等代碼 (如 L150)
        """
        new_order = cls.calculate_insert_order(lower_order, upper_order)
        return f'L{new_order:03d}'

    def __repr__(self):
        return f'<JobLevel {self.code}: {self.name}>'


# 職等序號設計說明：
# =====================
# 使用等距跳號而非連續號，以便未來靈活插入新職等。
#
# 設計原則：
# - 基礎間距：100 (每個主要職等間隔 100)
# - 非公司成員：L000 (非員工，如外包、顧問)
# - 最基層：L100 (職員級)
# - 最高層：L900 (總經理級)
#
# 插入新職等範例：
# - 原有 L100 (職員) 和 L200 (高級職員)
# - 想在中間加一級，新增 L150
# - 流程設計用 level_order >= 200 不受影響
#
# 再次細分範例：
# - L150 和 L200 之間再加一級 → L175
# - 理論上可無限細分

# 預設職等資料 (供 seed 使用)
# 使用等距跳號：L000, L100, L200, L300, L400, L500, L600, L700, L800, L900
DEFAULT_JOB_LEVELS = [
    {
        'code': 'L900',
        'name': '總經理級',
        'name_en': 'President Level',
        'level_order': 900,
        'approval_limit': None,  # 無上限
        'is_manager_level': True,
        'management_scope': '全公司',
    },
    {
        'code': 'L800',
        'name': '副總經理級',
        'name_en': 'Vice President Level',
        'level_order': 800,
        'approval_limit': 50000000,  # 5000 萬
        'is_manager_level': True,
        'management_scope': '多處室/事業部',
    },
    {
        'code': 'L700',
        'name': '處長級',
        'name_en': 'Director Level',
        'level_order': 700,
        'approval_limit': 10000000,  # 1000 萬
        'is_manager_level': True,
        'management_scope': '單一處室',
    },
    {
        'code': 'L600',
        'name': '副處長級',
        'name_en': 'Deputy Director Level',
        'level_order': 600,
        'approval_limit': 5000000,  # 500 萬
        'is_manager_level': True,
        'management_scope': '協助處室管理',
    },
    {
        'code': 'L500',
        'name': '經理級',
        'name_en': 'Manager Level',
        'level_order': 500,
        'approval_limit': 1000000,  # 100 萬
        'is_manager_level': True,
        'management_scope': '單一部門',
    },
    {
        'code': 'L400',
        'name': '副理級',
        'name_en': 'Assistant Manager Level',
        'level_order': 400,
        'approval_limit': 500000,  # 50 萬
        'is_manager_level': True,
        'management_scope': '協助部門管理',
    },
    {
        'code': 'L300',
        'name': '主任級',
        'name_en': 'Supervisor Level',
        'level_order': 300,
        'approval_limit': 100000,  # 10 萬
        'is_manager_level': True,
        'management_scope': '小組/專案',
    },
    {
        'code': 'L200',
        'name': '高級職員級',
        'name_en': 'Senior Staff Level',
        'level_order': 200,
        'approval_limit': 50000,  # 5 萬
        'is_manager_level': False,
        'management_scope': None,
    },
    {
        'code': 'L100',
        'name': '職員級',
        'name_en': 'Staff Level',
        'level_order': 100,
        'approval_limit': 10000,  # 1 萬
        'is_manager_level': False,
        'management_scope': None,
    },
    {
        'code': 'L000',
        'name': '非公司成員',
        'name_en': 'External',
        'level_order': 0,
        'approval_limit': 0,  # 無簽核權限
        'is_manager_level': False,
        'management_scope': None,
    },
]
