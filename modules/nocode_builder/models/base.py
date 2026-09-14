"""
Data CRUD Module - Base Model
模組基礎模型

繼承自平台的 BaseModel，使用 org_secure_code 字串欄位進行租戶隔離。
"""
from sqlalchemy import Column, String

from app.models.base import BaseModel


class ModuleBaseModel(BaseModel):
    """
    模組基礎 Model

    繼承平台的 BaseModel（包含 id, secure_code, timestamps, soft delete），
    加入 org_secure_code 欄位用於多租戶隔離。
    """
    __abstract__ = True

    org_secure_code = Column(
        String(32),
        nullable=False,
        index=True
    )

    def to_dict(self):
        """轉換為字典"""
        return super().to_dict()
