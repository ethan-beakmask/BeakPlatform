"""
FormWorkflow Module - Conglomerate Database Model
集團共享資料庫登記表

每個集團可有一組獨立的共享資料庫，供成員企業跨企業資料交換。
帳號密碼以 Fernet 對稱加密儲存（共用 FwOrgDatabase 的加密機制）。

帳號設計：
- admin (cgadmin_{id}): DDL 操作（建表/改表），由平台 /spec-formulate/ 使用
- member (cgmember_{id}): DML 操作（讀寫資料），所有成員企業共用
  搭配 RLS (Row-Level Security) 控制各企業只能寫入自己的資料
"""
import secrets
from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, Boolean, Text, event
from app.models.base import BaseModel


# 複用 FwOrgDatabase 的加密機制
from .org_database import encrypt_credential, decrypt_credential


class FwConglomerateDatabase(BaseModel):
    """
    集團共享資料庫登記表

    每集團一筆記錄，追蹤：
    - 資料庫名稱 (cg_{conglomerate_id})
    - 高權限帳號 (cgadmin_{id}) — 建表、DDL 維護（平台使用）
    - 共用帳號 (cgmember_{id}) — DML 讀寫（成員企業使用，搭配 RLS）
    - 帳號密碼皆加密儲存
    """
    __tablename__ = 'fw_conglomerate_databases'

    # 集團 secure_code（來自 conglomerates.secure_code）
    conglomerate_secure_code = Column(
        String(32), nullable=False, unique=True, index=True
    )

    # 集團 ID（來自 conglomerates.id，用於生成庫名）
    conglomerate_id = Column(Integer, nullable=False, unique=True, index=True)

    # 資料庫資訊
    db_name = Column(String(100), nullable=False, unique=True)
    db_host = Column(String(255), default='localhost')
    db_port = Column(Integer, default=5432)

    # 高權限帳號（DDL：CREATE/DROP TABLE，平台用）
    admin_user = Column(String(100), nullable=False)
    admin_password_enc = Column(Text, nullable=False)

    # 共用帳號（DML：SELECT/INSERT/UPDATE/DELETE，成員企業用，搭配 RLS）
    member_user = Column(String(100), nullable=False)
    member_password_enc = Column(Text, nullable=False)

    # 狀態
    is_ready = Column(Boolean, default=False, nullable=False)
    last_credential_rotation = Column(DateTime)

    def __repr__(self):
        return f'<FwConglomerateDatabase {self.db_name} (ready={self.is_ready})>'

    @property
    def admin_password(self):
        return decrypt_credential(self.admin_password_enc)

    @admin_password.setter
    def admin_password(self, value):
        self.admin_password_enc = encrypt_credential(value)

    @property
    def member_password(self):
        return decrypt_credential(self.member_password_enc)

    @member_password.setter
    def member_password(self, value):
        self.member_password_enc = encrypt_credential(value)

    def get_admin_dsn(self):
        """取得高權限連線字串（DDL 操作）"""
        pwd = self.admin_password
        return (
            f'postgresql://{self.admin_user}:{pwd}'
            f'@{self.db_host}:{self.db_port}/{self.db_name}'
        )

    def get_member_dsn(self):
        """取得共用帳號連線字串（DML 操作，需搭配 SET app.org_code）"""
        pwd = self.member_password
        return (
            f'postgresql://{self.member_user}:{pwd}'
            f'@{self.db_host}:{self.db_port}/{self.db_name}'
        )

    def to_dict(self):
        """不暴露密碼"""
        base = super().to_dict()
        base.update({
            'conglomerate_secure_code': self.conglomerate_secure_code,
            'conglomerate_id': self.conglomerate_id,
            'db_name': self.db_name,
            'db_host': self.db_host,
            'db_port': self.db_port,
            'admin_user': self.admin_user,
            'member_user': self.member_user,
            'is_ready': self.is_ready,
            'last_credential_rotation': (
                self.last_credential_rotation.isoformat()
                if self.last_credential_rotation else None
            ),
        })
        return base


@event.listens_for(FwConglomerateDatabase, 'before_insert')
def generate_cg_db_secure_code(mapper, connection, target):
    if not target.secure_code:
        target.secure_code = secrets.token_urlsafe(16)
