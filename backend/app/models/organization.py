"""
BeakMask Organization Model
企業/組織 Model
"""
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple

from sqlalchemy import Column, String, Boolean, Text, Integer, ForeignKey
from sqlalchemy.orm import relationship

from .base import BaseModel
from .. import db


class CustomerType:
    """企業客戶類型"""
    TRIAL = 'TRIAL'          # 試用
    FORMAL = 'FORMAL'        # 正式客戶
    BLACKLIST = 'BLACKLIST'  # 黑名單


class Organization(BaseModel):
    """
    企業/組織 Model

    企業是多租戶隔離的最上層單位。
    所有資源都屬於某個企業。

    特殊企業:
    - domain_name='system.local' 為系統企業，永久有效，不受合約限制
    """
    __tablename__ = 'organizations'

    # 企業代碼 (唯一，用於內部識別)
    code = Column(String(50), unique=True, nullable=False, index=True)

    # 企業名稱
    name = Column(String(255), nullable=False)

    # 企業顯示名稱（多語言）
    display_name = Column(String(255), nullable=True, comment='多語言顯示名稱')

    # 登入網域 (唯一，用於登入識別，如: acme.com.tw)
    domain_name = Column(String(255), unique=True, nullable=False, index=True)

    # 企業描述
    description = Column(Text, nullable=True)

    # 客戶類型
    customer_type = Column(
        String(20),
        default=CustomerType.TRIAL,
        nullable=False
    )

    # 帳號數量上限
    user_limit = Column(Integer, default=50, nullable=False)

    # 是否啟用
    is_active = Column(Boolean, default=True, nullable=False)

    # 企業設定 (JSON)
    settings = Column(Text, nullable=True)  # Store as JSON string

    # 聯絡資訊
    contact_person = Column(String(100), nullable=True)
    contact_email = Column(String(255), nullable=True)
    contact_phone = Column(String(50), nullable=True)
    address = Column(Text, nullable=True)

    # 所屬集團（可為空，獨立企業沒有集團）
    conglomerate_secure_code = Column(
        String(32),
        ForeignKey('conglomerates.secure_code'),
        nullable=True,
        index=True
    )

    # 關聯
    conglomerate = relationship('Conglomerate', back_populates='organizations')
    contracts = relationship('Contract', back_populates='organization', lazy='dynamic')
    users = relationship('User', back_populates='organization', lazy='dynamic')

    # 預設企業設定
    DEFAULT_SETTINGS = {
        'allow_user_self_edit': True,  # 允許用戶修改自己的資料
        'locale': 'zh-TW',            # 企業常用語系
        'timezone': 'Asia/Taipei',    # 企業主要時區
    }

    @property
    def is_system_org(self) -> bool:
        """是否為系統企業"""
        return self.domain_name == 'system.local'

    def get_settings(self) -> Dict[str, Any]:
        """取得所有企業設定"""
        if not self.settings:
            return dict(self.DEFAULT_SETTINGS)
        try:
            saved = json.loads(self.settings)
            # 合併預設值（確保新增的設定有預設值）
            result = dict(self.DEFAULT_SETTINGS)
            result.update(saved)
            return result
        except json.JSONDecodeError:
            return dict(self.DEFAULT_SETTINGS)

    def get_setting(self, key: str, default: Any = None) -> Any:
        """取得單一企業設定"""
        settings = self.get_settings()
        if default is None:
            default = self.DEFAULT_SETTINGS.get(key)
        return settings.get(key, default)

    def set_setting(self, key: str, value: Any) -> None:
        """設定單一企業設定"""
        settings = self.get_settings()
        settings[key] = value
        self.settings = json.dumps(settings, ensure_ascii=False)

    def set_settings(self, new_settings: Dict[str, Any]) -> None:
        """批次設定多個企業設定"""
        settings = self.get_settings()
        settings.update(new_settings)
        self.settings = json.dumps(settings, ensure_ascii=False)

    def get_contract_valid_range(self) -> Optional[Tuple[datetime, datetime]]:
        """
        取得所有有效合約的日期範圍

        Returns:
            Tuple[datetime, datetime]: (最早開始日期, 最晚結束日期的最後一秒)
            None: 如果沒有有效合約
        """
        # 系統企業永久有效
        if self.is_system_org:
            return (
                datetime(2000, 1, 1),
                datetime(2099, 12, 31, 23, 59, 59)
            )

        # 避免循環導入
        from .contract import Contract, ContractStatus

        active_contracts = Contract.query.filter(
            Contract.org_secure_code == self.secure_code,
            Contract.status == ContractStatus.ACTIVE,
            Contract.is_deleted == False
        ).all()

        if not active_contracts:
            return None

        # 找出最早開始和最晚結束
        start_dates = [c.start_date for c in active_contracts]
        end_dates = [c.end_date for c in active_contracts]

        earliest_start = min(start_dates)
        latest_end = max(end_dates)

        # 將 date 轉換為 datetime，結束日期取當天最後一秒
        start_datetime = datetime.combine(earliest_start, datetime.min.time())
        end_datetime = datetime.combine(latest_end, datetime.max.time())

        return (start_datetime, end_datetime)

    def is_contract_valid(self) -> bool:
        """
        檢查企業是否在合約有效期內

        Returns:
            bool: True 如果在有效期內
        """
        contract_range = self.get_contract_valid_range()
        if not contract_range:
            return False

        now = datetime.utcnow()
        start, end = contract_range
        return start <= now <= end

    def get_active_user_count(self) -> int:
        """取得目前啟用的帳號數量"""
        from .user import User
        return User.query.filter(
            User.org_secure_code == self.secure_code,
            User.is_active == True,
            User.is_deleted == False
        ).count()

    def can_create_user(self) -> bool:
        """檢查是否還可以建立新帳號"""
        return self.get_active_user_count() < self.user_limit

    def to_dict(self, include_contracts: bool = False) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            'code': self.code,
            'name': self.name,
            'display_name': self.display_name,
            'domain_name': self.domain_name,
            'description': self.description,
            'customer_type': self.customer_type,
            'user_limit': self.user_limit,
            'is_active': self.is_active,
            'contact_person': self.contact_person,
            'contact_email': self.contact_email,
            'contact_phone': self.contact_phone,
            'is_system_org': self.is_system_org,
            'is_contract_valid': self.is_contract_valid(),
            'conglomerate_secure_code': self.conglomerate_secure_code,
        })

        # 包含集團資訊
        if self.conglomerate:
            base['conglomerate'] = {
                'id': self.conglomerate.secure_code,
                'code': self.conglomerate.code,
                'name': self.conglomerate.name,
            }

        if include_contracts:
            contract_range = self.get_contract_valid_range()
            if contract_range:
                base['contract_valid_from'] = contract_range[0].isoformat()
                base['contract_valid_until'] = contract_range[1].isoformat()

        return base

    def __repr__(self):
        return f'<Organization {self.code} ({self.domain_name})>'
