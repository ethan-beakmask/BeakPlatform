"""
BeakMask SystemSetting Model
系統設定 Model - 儲存系統級設定值
"""
import json
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import Column, String, Text, DateTime

from .base import BaseModel
from .. import db


class SystemSetting(BaseModel):
    """
    系統設定 Model

    用於儲存系統級設定，如 E-MailRelay 設定、系統名稱等。
    注意：這是系統級設定，不屬於任何企業，因此繼承 BaseModel 而非 TenantBaseModel。
    """
    __tablename__ = 'system_settings'

    # 設定鍵（唯一）
    key = Column(
        String(100),
        unique=True,
        nullable=False,
        index=True,
        comment='設定鍵'
    )

    # 設定值（JSON 字串）
    value = Column(
        Text,
        nullable=False,
        comment='設定值'
    )

    # 值類型
    value_type = Column(
        String(20),
        default='string',
        nullable=False,
        comment='值類型: string, integer, boolean, json'
    )

    # 設定說明
    description = Column(
        Text,
        nullable=True,
        comment='設定說明'
    )

    # 分類（用於分組顯示）
    category = Column(
        String(50),
        default='general',
        nullable=False,
        index=True,
        comment='設定分類'
    )

    # 修改者
    updated_by = Column(
        String(100),
        nullable=True,
        comment='最後修改者'
    )

    # 修改時間
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        comment='最後修改時間'
    )

    def get_value(self) -> Any:
        """根據 value_type 返回正確類型的值"""
        if self.value_type == 'integer':
            return int(self.value)
        elif self.value_type == 'boolean':
            return self.value.lower() in ('true', '1', 'yes')
        elif self.value_type == 'json':
            return json.loads(self.value)
        else:
            return self.value

    def set_value(self, value: Any) -> None:
        """根據 value_type 設定值"""
        if self.value_type == 'integer':
            self.value = str(int(value))
        elif self.value_type == 'boolean':
            self.value = 'true' if value else 'false'
        elif self.value_type == 'json':
            self.value = json.dumps(value)
        else:
            self.value = str(value)

    def to_dict(self) -> dict:
        base = super().to_dict()
        base.update({
            'key': self.key,
            'value': self.get_value(),
            'raw_value': self.value,
            'value_type': self.value_type,
            'description': self.description,
            'category': self.category,
            'updated_by': self.updated_by,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        })
        return base

    @staticmethod
    def get(key: str, default: Any = None) -> Any:
        """取得設定值"""
        setting = SystemSetting.query.filter_by(key=key).first()
        if setting:
            return setting.get_value()
        return default

    @staticmethod
    def set(
        key: str,
        value: Any,
        updated_by: str = 'SYSTEM',
        value_type: str = 'string',
        description: str = None,
        category: str = 'general'
    ) -> 'SystemSetting':
        """設定值（自動建立或更新）"""
        setting = SystemSetting.query.filter_by(key=key).first()
        if setting:
            setting.set_value(value)
            setting.updated_by = updated_by
            setting.updated_at = datetime.utcnow()
        else:
            setting = SystemSetting(
                key=key,
                value=str(value),
                value_type=value_type,
                description=description,
                category=category,
                updated_by=updated_by
            )
            db.session.add(setting)
        db.session.commit()
        return setting

    @staticmethod
    def get_by_category(category: str) -> list:
        """取得某分類的所有設定"""
        return SystemSetting.query.filter_by(category=category).all()

    def __repr__(self):
        return f'<SystemSetting {self.key}={self.value}>'
