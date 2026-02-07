"""
BeakPlatform Base Model
所有 Model 的基類，包含共用欄位和方法
"""
from datetime import datetime
from typing import Dict, Any

from sqlalchemy import Column, DateTime, Boolean, String, Index
from sqlalchemy.ext.declarative import declared_attr

from .. import db
from ..utils.security import generate_secure_code


class TimestampMixin:
    """時間戳記 Mixin"""
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class SoftDeleteMixin:
    """軟刪除 Mixin"""
    is_deleted = Column(Boolean, default=False, nullable=False, index=True)
    deleted_at = Column(DateTime, nullable=True)


class SecureCodeMixin:
    """
    Secure Code Mixin
    使用 URL-safe token 作為外部識別碼，不暴露自增 ID
    """
    @declared_attr
    def secure_code(cls):
        return Column(
            String(32),
            unique=True,
            nullable=False,
            default=generate_secure_code,
            index=True
        )


class BaseModel(db.Model, TimestampMixin, SoftDeleteMixin, SecureCodeMixin):
    """
    基礎 Model
    包含：
    - 自增 ID (內部使用)
    - secure_code (外部識別碼)
    - 時間戳記
    - 軟刪除
    """
    __abstract__ = True

    id = Column(db.Integer, primary_key=True)

    def to_dict(self) -> Dict[str, Any]:
        """
        轉換為字典，用於 API 回應。
        子類別應覆寫此方法以添加額外欄位。

        注意：不應包含內部 id，只使用 secure_code
        """
        return {
            'id': self.secure_code,  # 使用 secure_code 作為 public ID（向後相容）
            'secure_code': self.secure_code,  # 明確的 secure_code 欄位
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class TenantBaseModel(BaseModel):
    """
    多租戶基礎 Model
    繼承此類的 Model 會自動加入租戶欄位和隔離機制
    """
    __abstract__ = True

    @declared_attr
    def org_secure_code(cls):
        return Column(
            String(32),
            db.ForeignKey('organizations.secure_code'),
            nullable=False,
            index=True
        )

    def to_dict(self) -> Dict[str, Any]:
        """轉換為字典，不包含 org_secure_code（避免洩漏）"""
        base = super().to_dict()
        # org_secure_code 不應該暴露給一般用戶
        return base
