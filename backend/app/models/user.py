"""
BeakMask User Model
用戶 Model
"""
from datetime import datetime
from typing import Dict, Any, Optional

from flask_login import UserMixin
from sqlalchemy import Column, String, Boolean, Text, Integer, UniqueConstraint
from sqlalchemy.orm import relationship
import bcrypt

from .base import TenantBaseModel
from .. import db, login_manager


class UserType:
    """用戶類型"""
    SYSTEM_ADMIN = 'SYSTEM_ADMIN'  # 系統管理員
    ORG_ADMIN = 'ORG_ADMIN'        # 企業管理員
    EMPLOYEE = 'EMPLOYEE'          # 員工
    EXTERNAL = 'EXTERNAL'          # 外部廠商


class User(TenantBaseModel, UserMixin):
    """
    用戶 Model

    繼承 TenantBaseModel，自動包含 org_secure_code 欄位。
    實作 Flask-Login 的 UserMixin。

    登入方式:
    - 共用登入頁: username@domain_name
    - 企業專屬登入頁: username (自動帶入 domain_name)
    """
    __tablename__ = 'users'

    # 組織內唯一約束
    __table_args__ = (
        UniqueConstraint('username', 'org_secure_code', name='unique_user_org'),
    )

    # 用戶名 (組織內唯一，用於登入)
    username = Column(String(100), nullable=False, index=True)

    # Email (全系統唯一)
    email = Column(String(255), unique=True, nullable=False, index=True)

    # 密碼 hash
    password_hash = Column(String(255), nullable=False)

    # 顯示名稱
    display_name = Column(String(255), nullable=False)

    # 用戶類型
    user_type = Column(
        String(20),
        default=UserType.EMPLOYEE,
        nullable=False
    )

    # 是否啟用
    is_active = Column(Boolean, default=True, nullable=False)

    # 最後登入時間
    last_login_at = Column(db.DateTime, nullable=True)

    # 主要組織單位 (部門/群組)
    primary_unit_secure_code = Column(
        String(32),
        db.ForeignKey('organizational_units.secure_code'),
        nullable=True
    )

    # 用戶設定 (JSON)
    preferences = Column(Text, nullable=True)

    # 個人資料欄位
    english_name = Column(String(255), nullable=True, comment='英文姓名')
    native_name = Column(String(255), nullable=True, comment='本國姓名')
    nickname = Column(String(100), nullable=True, comment='暱稱')
    backup_email_1 = Column(String(255), nullable=True, comment='備用 Email 1')
    backup_email_2 = Column(String(255), nullable=True, comment='備用 Email 2')
    mobile_phone_1 = Column(String(50), nullable=True, comment='手機號碼 1')
    mobile_phone_2 = Column(String(50), nullable=True, comment='手機號碼 2')
    interface_language = Column(String(10), nullable=True, comment='介面語言 (覆蓋企業設定)')
    timezone = Column(String(50), nullable=True, comment='個人時區 IANA (覆蓋企業設定)')
    navbar_display = Column(String(20), nullable=True, comment='Navbar 顯示偏好 (空=跟隨企業, nickname, employee_id, employee_id_dept)')

    # 員工編號 (組織內唯一)
    employee_id = Column(String(50), nullable=True, comment='員工編號 (組織內唯一)')

    # 密碼變更相關
    must_change_password = Column(Boolean, default=False, nullable=False, comment='是否強制變更密碼')
    password_changed_at = Column(db.DateTime, nullable=True, comment='密碼變更時間')

    # 登入失敗追蹤
    failed_login_count = Column(Integer, default=0, nullable=False, comment='連續登入失敗次數')
    locked_until = Column(db.DateTime, nullable=True, comment='帳號鎖定到期時間')
    last_failed_login = Column(db.DateTime, nullable=True, comment='最後一次登入失敗時間')

    # 企業原始管理員標記（無合約時唯一可登入的帳號）
    is_original_admin = Column(Boolean, default=False, nullable=False, comment='企業原始管理員')

    # 備註（管理員可見）
    notes = Column(Text, nullable=True, comment='用戶備註（管理員可見）')

    # 企業管理員綁定的員工帳號 (一對一)
    # 非 admin@ 的企業管理員必須綁定一個有員工編號的員工帳號
    # 當被綁定的員工帳號停用/刪除時，此管理員帳號也無法登入
    # 使用 use_alter=True 讓 SQLAlchemy 先建立表格再添加外鍵（避免自引用問題）
    bound_employee_secure_code = Column(
        String(32),
        db.ForeignKey('users.secure_code', use_alter=True, name='fk_user_bound_employee'),
        nullable=True,
        unique=True,  # 一對一：每個員工只能被一個管理員綁定
        comment='企業管理員綁定的員工帳號'
    )

    # 關聯
    organization = relationship('Organization', back_populates='users')
    primary_unit = relationship('OrganizationalUnit', foreign_keys=[primary_unit_secure_code])

    # 綁定的員工帳號關聯 (自引用)
    bound_employee = relationship(
        'User',
        foreign_keys=[bound_employee_secure_code],
        remote_side='User.secure_code',
        uselist=False
    )

    # 跨部門/社群成員關係
    unit_memberships = relationship('UserUnitMembership', back_populates='user')

    # 共用班表關聯
    work_schedule_secure_code = Column(
        String(32),
        db.ForeignKey('work_schedules.secure_code'),
        nullable=True,
        comment='用戶的共用班表，null 時使用企業預設'
    )
    work_schedule = relationship('WorkSchedule', back_populates='users')

    # 個人排班
    personal_schedules = relationship('PersonalSchedule', back_populates='user')

    # 排班調整（請假、加班等）
    schedule_adjustments = relationship(
        'ScheduleAdjustment',
        foreign_keys='ScheduleAdjustment.user_secure_code',
        back_populates='user'
    )

    @property
    def is_system_admin(self) -> bool:
        """是否為系統管理員"""
        return self.user_type == UserType.SYSTEM_ADMIN

    @property
    def is_org_admin(self) -> bool:
        """是否為企業管理員"""
        return self.user_type in (UserType.SYSTEM_ADMIN, UserType.ORG_ADMIN)

    @property
    def is_employee(self) -> bool:
        """是否為員工"""
        return self.user_type == UserType.EMPLOYEE

    @property
    def is_external(self) -> bool:
        """是否為外部廠商"""
        return self.user_type == UserType.EXTERNAL

    def set_password(self, password: str) -> None:
        """設定密碼（自動 hash）"""
        raw = password.encode('utf-8')
        if len(raw) > 72:
            raise ValueError('密碼長度超過 bcrypt 72 bytes 上限')
        salt = bcrypt.gensalt()
        self.password_hash = bcrypt.hashpw(raw, salt).decode('utf-8')

    def check_password(self, password: str) -> bool:
        """驗證密碼"""
        raw = password.encode('utf-8')
        if len(raw) > 72:
            return False
        return bcrypt.checkpw(raw, self.password_hash.encode('utf-8'))

    def get_id(self) -> str:
        """Flask-Login 需要的方法，返回用戶識別碼"""
        return str(self.id)

    def can_login(self) -> tuple[bool, Optional[str]]:
        """
        檢查用戶是否可以登入

        Returns:
            tuple[bool, str]: (是否可登入, 錯誤訊息)

        登入邏輯:
        1. 帳號停用 → 拒絕
        2. 企業不存在/停用 → 拒絕
        3. 系統管理員 → 允許
        4. 企業原始管理員 (is_original_admin=True) → 允許 (不受合約限制)
        5. 其他帳號:
           - 合約有效 → 允許
           - 合約無效 → 拒絕 (靜默，僅記錄日誌)
        """
        import logging
        logger = logging.getLogger(__name__)

        # 帳號停用
        if not self.is_active:
            return False, "帳號已停用"

        # 取得企業
        if not self.organization:
            return False, "無效的企業"

        # 企業停用
        if not self.organization.is_active:
            return False, "企業已停用"

        # 系統管理員不受合約限制
        if self.user_type == UserType.SYSTEM_ADMIN:
            return True, None

        # 企業原始管理員不受合約限制
        if self.is_original_admin:
            return True, None

        # 企業管理員檢查綁定的員工帳號
        if self.user_type == UserType.ORG_ADMIN:
            if self.bound_employee_secure_code:
                # 有綁定員工，檢查員工帳號狀態
                bound = self.bound_employee
                if bound is None or bound.is_deleted:
                    logger.warning(
                        f"企業管理員 {self.username}@{self.org_secure_code} 綁定的員工帳號已刪除"
                    )
                    return False, "綁定的員工帳號已刪除"
                if not bound.is_active:
                    logger.warning(
                        f"企業管理員 {self.username}@{self.org_secure_code} 綁定的員工帳號已停用"
                    )
                    return False, "綁定的員工帳號已停用"

        # 其他帳號檢查合約有效期
        if not self.organization.is_contract_valid():
            logger.warning(
                f"用戶 {self.username}@{self.org_secure_code} 嘗試登入，"
                f"但企業無有效合約"
            )
            return False, "帳號或密碼錯誤"  # 不洩露合約狀態，統一錯誤訊息

        return True, None

    def update_last_login(self) -> None:
        """更新最後登入時間"""
        self.last_login_at = datetime.utcnow()

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            'username': self.username,
            'email': self.email,
            'display_name': self.display_name,
            'user_type': self.user_type,
            'is_active': self.is_active,
            'is_system_admin': self.is_system_admin,
            'is_org_admin': self.is_org_admin,
            'last_login_at': self.last_login_at.isoformat() if self.last_login_at else None,
            'english_name': self.english_name,
            'native_name': self.native_name,
            'nickname': self.nickname,
            'backup_email_1': self.backup_email_1,
            'backup_email_2': self.backup_email_2,
            'mobile_phone_1': self.mobile_phone_1,
            'mobile_phone_2': self.mobile_phone_2,
            'interface_language': self.interface_language,
            'timezone': self.timezone,
            'employee_id': self.employee_id,
        })

        if self.primary_unit:
            base['primary_unit'] = {
                'id': self.primary_unit.secure_code,
                'name': self.primary_unit.name,
            }

        return base

    def __repr__(self):
        return f'<User {self.username}@{self.org_secure_code}>'


@login_manager.user_loader
def load_user(user_id: str):
    """Flask-Login user loader"""
    return User.query.get(int(user_id))
