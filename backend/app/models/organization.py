"""
BeakMask Organization Model
企業/組織 Model
"""
import json
from datetime import date, datetime, timedelta
from typing import Dict, Any, Optional, Tuple

from sqlalchemy import Column, String, Boolean, Text, Integer, ForeignKey
from sqlalchemy.orm import relationship

from .base import BaseModel
from .. import db


# 企業帳號上限的平台預設值。
# 這是全平台唯一來源：model default 與所有建立企業的路徑一律引用它，
# 不要在別處另寫數字（2026-08-30 之前有六個互相打架的預設值）。
DEFAULT_ORG_USER_LIMIT = 50

# 計入企業帳號上限的 user_type。
# ORG_ADMIN 綁定一個企業成員帳號、SYSTEM_ADMIN 是平台級身分，兩者都不是獨立人頭。
USER_LIMIT_COUNTED_USER_TYPES = ('EMPLOYEE', 'EXTERNAL')


def counts_toward_user_limit(user_type: str) -> bool:
    """該 user_type 是否計入企業帳號上限"""
    return user_type in USER_LIMIT_COUNTED_USER_TYPES


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
    - is_system_org=True 為系統企業，永久有效，不受合約限制
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
    user_limit = Column(Integer, default=DEFAULT_ORG_USER_LIMIT, nullable=False)

    # 是否啟用
    is_active = Column(Boolean, default=True, nullable=False)

    # 企業設定 (JSON)
    settings = Column(Text, nullable=True)  # Store as JSON string

    # 聯絡資訊
    contact_person = Column(String(100), nullable=True)
    contact_email = Column(String(255), nullable=True)
    contact_phone = Column(String(50), nullable=True)
    address = Column(Text, nullable=True)

    # 是否為系統企業（每套部署唯一，用於不依賴環境變數識別系統企業）
    is_system_org = Column(Boolean, default=False, nullable=False, index=True)

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
        'country': 'TW',              # ISO 3166-1 alpha-2，決定預設班表週休日與假日表網路來源
        'timezone': 'Asia/Taipei',    # 企業主要時區
        'name_connector': '.',        # 帳號姓名連接符號 (., _, -, 或空字串)
        'display_name_field': 'native_name',  # 顯示名稱欄位 (native_name|english_name|nickname|username|employee_id)
        'login_employee_show_logo': True,   # 企業成員登入頁顯示企業 Logo
        'login_employee_show_name': True,   # 企業成員登入頁顯示企業名稱
        'login_external_show_logo': True,   # 外部廠商登入頁顯示企業 Logo
        'login_external_show_name': True,   # 外部廠商登入頁顯示企業名稱
        'broadcast_poll_interval_minutes': 1,  # 廣播輪詢間隔（分鐘）
    }

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

    def local_today(self, ref: datetime = None) -> date:
        """依企業設定的時區回傳當地日曆日（合約效期等日曆日判定用）。"""
        from app.utils.timezone import local_today
        return local_today(self.get_setting('timezone', 'Asia/Taipei'), ref)

    def get_contract_valid_range(self) -> Optional[Tuple[date, date]]:
        """
        取得所有有效合約的日期範圍

        Returns:
            Tuple[date, date]: (最早開始日期, 最晚結束日期)
            None: 如果沒有有效合約

        合約日期為純日期（不涉及時區），比對時以企業時區的「今天」為準。
        """
        # 系統企業永久有效
        if self.is_system_org:
            return (
                date(2000, 1, 1),
                date(2099, 12, 31)
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

        return (min(start_dates), max(end_dates))

    def is_contract_valid(self) -> bool:
        """
        檢查企業是否在合約有效期內

        Returns:
            bool: True 如果在有效期內

        純日期比較：以企業設定時區的「今天」為準（TZ-01），避免 UTC 凌晨死區。
        """
        contract_range = self.get_contract_valid_range()
        if not contract_range:
            return False

        today = self.local_today()
        start, end = contract_range
        return start <= today <= end

    def get_active_user_count(self) -> int:
        """
        取得計入帳號上限的啟用帳號數（僅 EMPLOYEE 與 EXTERNAL，且排除服務帳號）。

        服務帳號（`is_service_account`，例如 NoCode portal 的公用送件帳號）
        由系統自動建立、無法登入，而且 /external-users 列表刻意不顯示它們，
        計入的話會佔掉一個使用者管理不到的名額。
        """
        from .user import User
        return User.query.filter(
            User.org_secure_code == self.secure_code,
            User.is_active == True,
            User.is_deleted == False,
            User.is_service_account == False,
            User.user_type.in_(USER_LIMIT_COUNTED_USER_TYPES)
        ).count()

    def can_create_user(self, user_type: str = None) -> bool:
        """
        檢查是否還能再增加一個「計入上限」的啟用帳號。

        user_type 省略時視為要新增計入上限的帳號（沿用舊語意，顯示用途照舊）。
        傳入不計入上限的 user_type（ORG_ADMIN / SYSTEM_ADMIN）時一律回 True。
        """
        if user_type is not None and not counts_toward_user_limit(user_type):
            return True
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
