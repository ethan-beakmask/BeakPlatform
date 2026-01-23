"""
BeakMask Recipient Group Model
收件人群組

用於系統通知的收件人群組設定，支援：
- 選取整個部門（可選是否包含子部門）
- 選取個別用戶
- 排除特定部門或用戶
"""
import json
from datetime import datetime
from typing import Dict, Any, List, Optional, Set

from sqlalchemy import Column, String, Boolean, Text, Integer

from .base import TenantBaseModel
from .. import db


class RecipientGroup(TenantBaseModel):
    """
    收件人群組

    儲存結構（JSON）：
    - included_units: [{"id": "xxx", "include_children": true}, ...]
    - included_users: ["user_id_1", "user_id_2", ...]
    - excluded_units: ["unit_id_1", "unit_id_2", ...]
    - excluded_users: ["user_id_1", "user_id_2", ...]
    """
    __tablename__ = 'recipient_groups'

    # 群組名稱
    name = Column(String(100), nullable=False, comment='群組名稱')

    # 描述
    description = Column(Text, nullable=True, comment='描述說明')

    # 優先順序（數字越小越優先，用於排序）
    priority = Column(Integer, default=100, nullable=False, comment='優先順序')

    # 是否啟用
    is_active = Column(Boolean, default=True, nullable=False, comment='是否啟用')

    # 收件人設定（JSON 格式）
    # 包含的部門列表 [{"id": "secure_code", "include_children": bool}, ...]
    _included_units = Column('included_units', Text, nullable=True, comment='包含的部門（JSON）')

    # 包含的用戶列表 ["user_secure_code", ...]
    _included_users = Column('included_users', Text, nullable=True, comment='包含的用戶（JSON）')

    # 排除的部門列表 ["unit_secure_code", ...]
    _excluded_units = Column('excluded_units', Text, nullable=True, comment='排除的部門（JSON）')

    # 排除的用戶列表 ["user_secure_code", ...]
    _excluded_users = Column('excluded_users', Text, nullable=True, comment='排除的用戶（JSON）')

    # ========== 屬性存取器 ==========

    @property
    def included_units(self) -> List[Dict[str, Any]]:
        """取得包含的部門列表"""
        if self._included_units:
            try:
                return json.loads(self._included_units)
            except json.JSONDecodeError:
                return []
        return []

    @included_units.setter
    def included_units(self, value: List[Dict[str, Any]]) -> None:
        """設定包含的部門列表"""
        self._included_units = json.dumps(value) if value else None

    @property
    def included_users(self) -> List[str]:
        """取得包含的用戶列表"""
        if self._included_users:
            try:
                return json.loads(self._included_users)
            except json.JSONDecodeError:
                return []
        return []

    @included_users.setter
    def included_users(self, value: List[str]) -> None:
        """設定包含的用戶列表"""
        self._included_users = json.dumps(value) if value else None

    @property
    def excluded_units(self) -> List[str]:
        """取得排除的部門列表"""
        if self._excluded_units:
            try:
                return json.loads(self._excluded_units)
            except json.JSONDecodeError:
                return []
        return []

    @excluded_units.setter
    def excluded_units(self, value: List[str]) -> None:
        """設定排除的部門列表"""
        self._excluded_units = json.dumps(value) if value else None

    @property
    def excluded_users(self) -> List[str]:
        """取得排除的用戶列表"""
        if self._excluded_users:
            try:
                return json.loads(self._excluded_users)
            except json.JSONDecodeError:
                return []
        return []

    @excluded_users.setter
    def excluded_users(self, value: List[str]) -> None:
        """設定排除的用戶列表"""
        self._excluded_users = json.dumps(value) if value else None

    # ========== 業務方法 ==========

    def resolve_recipients(self) -> List[Dict[str, str]]:
        """
        解析收件人列表

        Returns:
            List[Dict]: [{"user_id": "xxx", "email": "xxx", "name": "xxx"}, ...]
            email 使用 backup_email_1（系統通知專用）
        """
        from .user import User
        from .organizational_unit import OrganizationalUnit

        # 收集所有包含的用戶 ID
        included_user_ids: Set[str] = set()

        # 1. 從部門收集用戶
        for unit_config in self.included_units:
            unit_id = unit_config.get('id')
            include_children = unit_config.get('include_children', False)

            unit = OrganizationalUnit.query.filter_by(
                secure_code=unit_id,
                org_secure_code=self.org_secure_code,
                is_deleted=False
            ).first()

            if unit:
                # 取得該部門的所有用戶
                if include_children:
                    # 包含所有子部門
                    units = unit.get_descendants(include_self=True)
                    unit_ids = [u.secure_code for u in units]
                else:
                    unit_ids = [unit.secure_code]

                # 查詢這些部門的用戶
                users = User.query.filter(
                    User.primary_unit_secure_code.in_(unit_ids),
                    User.org_secure_code == self.org_secure_code,
                    User.is_active == True,
                    User.is_deleted == False
                ).all()

                for user in users:
                    included_user_ids.add(user.secure_code)

        # 2. 加入個別選取的用戶
        for user_id in self.included_users:
            included_user_ids.add(user_id)

        # 3. 排除部門中的用戶
        for unit_id in self.excluded_units:
            unit = OrganizationalUnit.query.filter_by(
                secure_code=unit_id,
                org_secure_code=self.org_secure_code,
                is_deleted=False
            ).first()

            if unit:
                # 排除該部門及所有子部門的用戶
                units = unit.get_descendants(include_self=True)
                unit_ids = [u.secure_code for u in units]

                users = User.query.filter(
                    User.primary_unit_secure_code.in_(unit_ids),
                    User.org_secure_code == self.org_secure_code,
                    User.is_deleted == False
                ).all()

                for user in users:
                    included_user_ids.discard(user.secure_code)

        # 4. 排除個別用戶
        for user_id in self.excluded_users:
            included_user_ids.discard(user_id)

        # 5. 查詢最終用戶列表，取得系統通知專用信箱
        if not included_user_ids:
            return []

        users = User.query.filter(
            User.secure_code.in_(list(included_user_ids)),
            User.is_active == True,
            User.is_deleted == False
        ).all()

        recipients = []
        for user in users:
            # 使用系統通知專用信箱 (backup_email_1)，若無則使用主要 email
            notification_email = user.backup_email_1 or user.email
            recipients.append({
                'user_id': user.secure_code,
                'email': notification_email,
                'name': user.display_name or user.username
            })

        return recipients

    def get_recipient_count(self) -> int:
        """取得收件人數量（預估，不做完整解析）"""
        return len(self.resolve_recipients())

    def to_dict(self, include_recipient_count: bool = False) -> Dict[str, Any]:
        """轉換為字典"""
        base = super().to_dict()
        base.update({
            'name': self.name,
            'description': self.description,
            'priority': self.priority,
            'is_active': self.is_active,
            'included_units': self.included_units,
            'included_users': self.included_users,
            'excluded_units': self.excluded_units,
            'excluded_users': self.excluded_users,
        })

        if include_recipient_count:
            base['recipient_count'] = self.get_recipient_count()

        return base

    def __repr__(self):
        return f'<RecipientGroup {self.name}>'
