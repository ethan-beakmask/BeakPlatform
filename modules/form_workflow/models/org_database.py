"""
FormWorkflow Module - Org Database Model
企業專屬資料庫登記表

每個啟用 SQL Sync 的企業都有一組獨立的資料庫與帳號。
帳號密碼以 Fernet 對稱加密儲存，Flask app 不直接持有明文密碼。
"""
import secrets
from datetime import datetime
from cryptography.fernet import Fernet
from sqlalchemy import Column, String, Integer, DateTime, Boolean, Text, event
from .base import ModuleBaseModel


# 加密金鑰從環境變數或 config 載入
_fernet = None


def _get_fernet():
    """延遲載入 Fernet 實例"""
    global _fernet
    if _fernet is None:
        import os
        key = os.environ.get('SYNC_CREDENTIAL_KEY')
        if not key:
            raise RuntimeError('SYNC_CREDENTIAL_KEY 環境變數未設定')
        _fernet = Fernet(key.encode() if isinstance(key, str) else key)
    return _fernet


def encrypt_credential(plaintext):
    """加密憑證"""
    if not plaintext:
        return None
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt_credential(ciphertext):
    """解密憑證"""
    if not ciphertext:
        return None
    return _get_fernet().decrypt(ciphertext.encode()).decode()


class FwOrgDatabase(ModuleBaseModel):
    """
    企業專屬資料庫登記表

    每企業一筆記錄，追蹤：
    - 資料庫名稱 (org_{org_id})
    - 高權限帳號 (bfadmin_{org_id}) — 建表、DDL 維護
    - 低權限帳號 (bfsync_{org_id}) — INSERT/UPDATE/SELECT
    - 帳號密碼皆加密儲存
    """
    __tablename__ = 'fw_org_databases'

    # 企業 ID（來自 organizations.id，用於生成庫名）
    org_id = Column(Integer, nullable=False, unique=True, index=True)

    # 資料庫資訊
    db_name = Column(String(100), nullable=False, unique=True)
    db_host = Column(String(255), default='localhost')
    db_port = Column(Integer, default=5432)

    # 高權限帳號（DDL：CREATE/DROP TABLE）
    admin_user = Column(String(100), nullable=False)
    admin_password_enc = Column(Text, nullable=False)

    # 低權限帳號（DML：INSERT/UPDATE/SELECT）
    sync_user = Column(String(100), nullable=False)
    sync_password_enc = Column(Text, nullable=False)

    # 狀態
    is_ready = Column(Boolean, default=False, nullable=False)
    last_credential_rotation = Column(DateTime)

    def __repr__(self):
        return f'<FwOrgDatabase {self.db_name} (ready={self.is_ready})>'

    @property
    def admin_password(self):
        return decrypt_credential(self.admin_password_enc)

    @admin_password.setter
    def admin_password(self, value):
        self.admin_password_enc = encrypt_credential(value)

    @property
    def sync_password(self):
        return decrypt_credential(self.sync_password_enc)

    @sync_password.setter
    def sync_password(self, value):
        self.sync_password_enc = encrypt_credential(value)

    def get_admin_dsn(self):
        """取得高權限連線字串"""
        pwd = self.admin_password
        return f'postgresql://{self.admin_user}:{pwd}@{self.db_host}:{self.db_port}/{self.db_name}'

    def get_sync_dsn(self):
        """取得低權限連線字串"""
        pwd = self.sync_password
        return f'postgresql://{self.sync_user}:{pwd}@{self.db_host}:{self.db_port}/{self.db_name}'

    def to_dict(self):
        """不暴露密碼"""
        base = super().to_dict()
        base.update({
            'org_id': self.org_id,
            'db_name': self.db_name,
            'db_host': self.db_host,
            'db_port': self.db_port,
            'admin_user': self.admin_user,
            'sync_user': self.sync_user,
            'is_ready': self.is_ready,
            'last_credential_rotation': self.last_credential_rotation.isoformat() if self.last_credential_rotation else None,
        })
        return base


@event.listens_for(FwOrgDatabase, 'before_insert')
def generate_org_db_secure_code(mapper, connection, target):
    if not target.secure_code:
        target.secure_code = secrets.token_urlsafe(16)
