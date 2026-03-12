"""
FormWorkflow Module - Base Model
模組基礎模型

繼承自平台的 BaseModel，但不使用 ForeignKey 連結到 organizations 表，
而是使用 org_secure_code 字串欄位，透過平台接口查詢組織資訊。
"""
from datetime import datetime
from typing import Dict, Any

from sqlalchemy import Column, String, DateTime, Boolean

# 從平台匯入基礎類別
from app.models.base import BaseModel


class ModuleBaseModel(BaseModel):
    """
    模組基礎 Model

    繼承平台的 BaseModel（包含 id, secure_code, timestamps, soft delete），
    加入 org_secure_code 欄位用於多租戶隔離。

    不使用 ForeignKey 連結到 organizations 表，
    模組透過平台接口 (app.platform.data) 查詢組織資訊。
    """
    __abstract__ = True

    # 企業識別碼（不用 ForeignKey，避免硬耦合）
    org_secure_code = Column(
        String(32),
        nullable=False,
        index=True
    )

    def to_dict(self) -> Dict[str, Any]:
        """轉換為字典"""
        base = super().to_dict()
        # 不暴露 org_secure_code 給一般 API 回應
        return base
