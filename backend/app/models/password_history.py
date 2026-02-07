"""
BeakMask Password History Model
密碼歷史記錄
"""
from sqlalchemy import Column, String, ForeignKey
from sqlalchemy.orm import relationship

from .base import BaseModel
from .. import db


class PasswordHistory(BaseModel):
    """
    密碼歷史記錄

    用於防止用戶重複使用舊密碼。
    儲存 bcrypt hash，比對時使用 bcrypt.checkpw()。
    """
    __tablename__ = 'password_history'

    # 用戶 secure_code
    user_secure_code = Column(
        String(32),
        ForeignKey('users.secure_code', ondelete='CASCADE'),
        nullable=False,
        index=True
    )

    # bcrypt hash
    password_hash = Column(String(255), nullable=False)

    # 關聯
    user = relationship('User', backref='password_histories')

    def __repr__(self):
        return f'<PasswordHistory user={self.user_secure_code} created_at={self.created_at}>'
