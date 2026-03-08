"""
用戶編號規則模型

支援多租戶，每個企業可設定多組編號規則。
包含：編號規則、計數器、已使用編號三個模型。
"""
from datetime import datetime
from typing import Dict, Any, List, Optional

from sqlalchemy import Column, String, Boolean, Text, Integer
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from .base import TenantBaseModel
from .. import db


class NumberingElementType:
    """編號元素類型"""
    PREFIX = 'prefix'           # 前綴文字
    SUFFIX = 'suffix'           # 後綴文字
    SEQUENCE = 'sequence'       # 序號
    YEAR = 'year'               # 公元年碼
    YEAR_OFFSET = 'year_offset' # 年換算碼（如民國年）
    MONTH = 'month'             # 月碼


class NumberingResetPeriod:
    """序號重置週期"""
    NEVER = 'never'     # 永不重置
    YEARLY = 'yearly'   # 每年重置
    MONTHLY = 'monthly' # 每月重置


class NumberingUsageScope:
    """編號使用範圍"""
    INTERNAL_ONLY = 'INTERNAL_ONLY'         # 內部專用（員工、公司資產）
    EXTERNAL_ONLY = 'EXTERNAL_ONLY'         # 外部專用（廠商、訪客）
    INTERNAL_UNIVERSAL = 'INTERNAL_UNIVERSAL'  # 內部通用（門禁卡、跨公司資源）


class NumberingDefaultFor:
    """預設用途"""
    NONE = None              # 非預設
    EMPLOYEE = 'EMPLOYEE'    # 員工編號預設
    EXTERNAL = 'EXTERNAL'    # 外部廠商預設


class UserNumberingRule(TenantBaseModel):
    """
    用戶編號規則

    每個企業可設定多組編號規則，其中一組為預設規則。
    規則包含多個元素（前綴、序號、年碼等）的組合配置。
    """
    __tablename__ = 'user_numbering_rules'

    # 基本資訊
    name = Column(String(100), nullable=False, comment='規則名稱')
    description = Column(Text, comment='規則描述')

    # 規則配置 (JSONB)
    elements = Column(JSONB, nullable=False, comment='編號元素配置')

    # 使用範圍
    usage_scope = Column(
        String(20),
        default=NumberingUsageScope.INTERNAL_ONLY,
        nullable=False,
        comment='使用範圍: INTERNAL_ONLY=內部專用, EXTERNAL_ONLY=外部專用, INTERNAL_UNIVERSAL=內部通用'
    )

    # 狀態
    default_for = Column(
        String(20),
        nullable=True,
        comment='預設用途: EMPLOYEE=員工預設, EXTERNAL=外部廠商預設, NULL=非預設'
    )
    is_active = Column(Boolean, default=True, nullable=False, comment='是否啟用')

    @property
    def is_default(self) -> bool:
        """向後兼容：是否為任一預設規則"""
        return self.default_for is not None

    # 關聯
    counters = relationship(
        'UserNumberingCounter',
        back_populates='rule',
        cascade='all, delete-orphan',
        lazy='dynamic'
    )

    def get_total_length(self) -> int:
        """取得設定的總長度"""
        return self.elements.get('total_length', 0)

    def get_components(self) -> List[dict]:
        """取得排序後的元素列表"""
        components = self.elements.get('components', [])
        return sorted(components, key=lambda x: x.get('order', 0))

    def get_sequence_config(self) -> Optional[dict]:
        """取得序號配置"""
        for comp in self.get_components():
            if comp.get('type') == NumberingElementType.SEQUENCE:
                return comp
        return None

    def get_prefix_config(self) -> Optional[dict]:
        """取得前綴配置"""
        for comp in self.get_components():
            if comp.get('type') == NumberingElementType.PREFIX:
                return comp
        return None

    def get_suffix_config(self) -> Optional[dict]:
        """取得後綴配置"""
        for comp in self.get_components():
            if comp.get('type') == NumberingElementType.SUFFIX:
                return comp
        return None

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            'name': self.name,
            'description': self.description,
            'elements': self.elements,
            'usage_scope': self.usage_scope,
            'default_for': self.default_for,
            'is_default': self.is_default,  # 向後兼容
            'is_active': self.is_active,
        })
        return base

    def __repr__(self):
        return f'<UserNumberingRule {self.org_secure_code}/{self.name}>'


class UserNumberingCounter(TenantBaseModel):
    """
    用戶編號計數器

    追蹤各規則在不同週期的序號狀態。
    使用 period_key 區分不同重置週期（年/月/永久）。
    """
    __tablename__ = 'user_numbering_counters'

    # 關聯規則
    rule_secure_code = Column(
        String(32),
        db.ForeignKey('user_numbering_rules.secure_code'),
        nullable=False,
        comment='關聯的編號規則'
    )

    # 週期識別
    period_key = Column(
        String(20),
        nullable=False,
        comment='週期識別（年/月/永久）'
    )

    # 計數器狀態
    prefix_index = Column(
        Integer,
        default=0,
        nullable=False,
        comment='當前前綴索引'
    )
    suffix_index = Column(
        Integer,
        default=0,
        nullable=False,
        comment='當前後綴索引'
    )
    current_seq = Column(
        Integer,
        default=0,
        nullable=False,
        comment='當前序號'
    )

    # 關聯
    rule = relationship('UserNumberingRule', back_populates='counters')

    __table_args__ = (
        db.UniqueConstraint(
            'org_secure_code', 'rule_secure_code', 'period_key',
            name='uq_numbering_counter'
        ),
    )

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            'rule_secure_code': self.rule_secure_code,
            'period_key': self.period_key,
            'prefix_index': self.prefix_index,
            'suffix_index': self.suffix_index,
            'current_seq': self.current_seq,
        })
        return base

    def __repr__(self):
        return f'<UserNumberingCounter {self.rule_secure_code}/{self.period_key}>'


class UsedUserNumber(TenantBaseModel):
    """
    已使用的用戶編號

    記錄所有已使用的編號，防止重複。
    無論是自動產生還是手動輸入的編號都會記錄在此。
    """
    __tablename__ = 'used_user_numbers'

    # 編號資訊
    number = Column(
        String(50),
        nullable=False,
        comment='編號值'
    )

    # 關聯資訊（可選）
    user_secure_code = Column(
        String(32),
        db.ForeignKey('users.secure_code'),
        nullable=True,
        comment='使用此編號的用戶'
    )
    rule_secure_code = Column(
        String(32),
        db.ForeignKey('user_numbering_rules.secure_code'),
        nullable=True,
        comment='產生此編號的規則'
    )

    __table_args__ = (
        db.UniqueConstraint(
            'org_secure_code', 'number',
            name='uq_used_number'
        ),
    )

    @classmethod
    def is_number_used(cls, org_secure_code: str, number: str) -> bool:
        """檢查編號是否已被使用"""
        return cls.query.filter_by(
            org_secure_code=org_secure_code,
            number=number
        ).first() is not None

    @classmethod
    def record_number(
        cls,
        org_secure_code: str,
        number: str,
        user_secure_code: Optional[str] = None,
        rule_secure_code: Optional[str] = None
    ) -> 'UsedUserNumber':
        """記錄已使用的編號"""
        used = cls(
            org_secure_code=org_secure_code,
            number=number,
            user_secure_code=user_secure_code,
            rule_secure_code=rule_secure_code
        )
        db.session.add(used)
        return used

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            'number': self.number,
            'user_secure_code': self.user_secure_code,
            'rule_secure_code': self.rule_secure_code,
        })
        return base

    def __repr__(self):
        return f'<UsedUserNumber {self.org_secure_code}/{self.number}>'
