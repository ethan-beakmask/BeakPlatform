"""
OpenDefense Module - Base Model
模組基礎模型,沿用平台 BaseModel + org_secure_code 多租戶欄位。
"""
from sqlalchemy import Column, String

from app.models.base import BaseModel


class OdBaseModel(BaseModel):
    """
    OpenDefense 模組基礎 Model。

    繼承平台 BaseModel(id / secure_code / timestamps / soft delete),
    加入 org_secure_code 欄位作多租戶隔離,並啟用 RLS。
    """
    __abstract__ = True

    org_secure_code = Column(
        String(32),
        nullable=False,
        index=True,
    )
