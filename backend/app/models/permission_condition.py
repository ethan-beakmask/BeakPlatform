"""
BeakPlatform PermissionCondition Model
權限條件 Model

ABAC (Attribute-Based Access Control) 條件定義
"""
import json
from typing import Dict, Any, Optional

from sqlalchemy import Column, String, Boolean, Text

from .base import BaseModel
from .. import db


class ConditionType:
    """
    條件類型

    定義 ABAC 條件的類別
    """
    OWNERSHIP = 'OWNERSHIP'    # 所有權條件 (OWNER, ASSIGNED)
    ORG = 'ORG'                # 組織層級條件 (SAME_DEPT, SUB_DEPT, SUBORDINATE)
    RANK = 'RANK'              # 職等條件 (MIN_RANK, LOWER_RANK)
    TIME = 'TIME'              # 時間條件 (WORK_HOURS, VALID_PERIOD)
    STATUS = 'STATUS'          # 狀態條件 (RESOURCE_STATUS, FLOW_STAGE)
    DELEGATE = 'DELEGATE'      # 代理條件 (DELEGATED_BY)


class PermissionCondition(BaseModel):
    """
    權限條件 Model

    定義系統支援的 ABAC 條件。

    條件在權限檢查時動態評估，例如：
    - OWNER: 檢查 resource.created_by == current_user.id
    - SAME_DEPT: 檢查 resource.dept == current_user.dept
    - MIN_RANK: 檢查 current_user.rank >= condition.param

    expression 欄位存儲條件的評估規則（JSON），例如：
    {
        "field": "created_by",
        "operator": "eq",
        "compare_to": "current_user.secure_code"
    }
    """
    __tablename__ = 'permission_conditions'

    # 條件代碼 (唯一)
    code = Column(
        String(50),
        unique=True,
        nullable=False,
        index=True
    )

    # 條件名稱
    name = Column(String(255), nullable=False)

    # 條件描述
    description = Column(Text, nullable=True)

    # 條件類型
    condition_type = Column(
        String(20),
        nullable=False,
        index=True
    )

    # 條件表達式 (JSON)
    expression = Column(Text, nullable=True)

    # 是否需要參數 (如 MIN_RANK 需要指定最低職等)
    requires_param = Column(Boolean, default=False, nullable=False)

    # 參數說明
    param_description = Column(String(255), nullable=True)

    # 是否為系統內建條件 (不可刪除)
    is_system_condition = Column(Boolean, default=False, nullable=False)

    # 是否啟用
    is_active = Column(Boolean, default=True, nullable=False)

    @property
    def expression_dict(self) -> Optional[Dict[str, Any]]:
        """取得條件表達式"""
        if not self.expression:
            return None
        try:
            return json.loads(self.expression)
        except (json.JSONDecodeError, TypeError):
            return None

    @expression_dict.setter
    def expression_dict(self, value: Optional[Dict[str, Any]]) -> None:
        """設定條件表達式"""
        if value is None:
            self.expression = None
        else:
            self.expression = json.dumps(value, ensure_ascii=False)

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            'code': self.code,
            'name': self.name,
            'description': self.description,
            'condition_type': self.condition_type,
            'expression': self.expression_dict,
            'requires_param': self.requires_param,
            'param_description': self.param_description,
            'is_system_condition': self.is_system_condition,
            'is_active': self.is_active,
        })
        return base

    def __repr__(self):
        return f'<PermissionCondition {self.code}>'


# 系統預設條件定義
DEFAULT_CONDITIONS = [
    # 所有權條件
    {
        'code': 'OWNER',
        'name': '資源擁有者',
        'description': '只能操作自己建立的資源',
        'condition_type': ConditionType.OWNERSHIP,
        'expression': {
            'field': 'created_by_secure_code',
            'operator': 'eq',
            'compare_to': 'current_user.secure_code'
        },
        'requires_param': False,
    },
    {
        'code': 'ASSIGNED',
        'name': '被指派者',
        'description': '只能操作指派給自己的資源',
        'condition_type': ConditionType.OWNERSHIP,
        'expression': {
            'field': 'assigned_to_secure_code',
            'operator': 'eq',
            'compare_to': 'current_user.secure_code'
        },
        'requires_param': False,
    },

    # 組織層級條件
    {
        'code': 'SAME_DEPT',
        'name': '同部門',
        'description': '只能操作同部門的資源',
        'condition_type': ConditionType.ORG,
        'expression': {
            'field': 'dept_secure_code',
            'operator': 'eq',
            'compare_to': 'current_user.primary_unit_secure_code'
        },
        'requires_param': False,
    },
    {
        'code': 'SUB_DEPT',
        'name': '下屬部門',
        'description': '可以操作下屬部門的資源',
        'condition_type': ConditionType.ORG,
        'expression': {
            'field': 'dept_secure_code',
            'operator': 'in_subtree',
            'compare_to': 'current_user.primary_unit_secure_code'
        },
        'requires_param': False,
    },
    {
        'code': 'SUBORDINATE',
        'name': '部屬',
        'description': '主管可以操作部屬的資源',
        'condition_type': ConditionType.ORG,
        'expression': {
            'field': 'owner_secure_code',
            'operator': 'is_subordinate_of',
            'compare_to': 'current_user.secure_code'
        },
        'requires_param': False,
    },

    # 職等條件
    {
        'code': 'MIN_RANK',
        'name': '最低職等',
        'description': '需要達到指定職等才能操作',
        'condition_type': ConditionType.RANK,
        'expression': {
            'field': 'current_user.job_level',
            'operator': 'gte',
            'compare_to': 'param'
        },
        'requires_param': True,
        'param_description': '最低職等代碼',
    },
    {
        'code': 'LOWER_RANK',
        'name': '較低職等',
        'description': '只能操作職等比自己低的人員資料',
        'condition_type': ConditionType.RANK,
        'expression': {
            'field': 'target_user.job_level',
            'operator': 'lt',
            'compare_to': 'current_user.job_level'
        },
        'requires_param': False,
    },

    # 時間條件
    {
        'code': 'WORK_HOURS',
        'name': '上班時間',
        'description': '只在上班時間可執行',
        'condition_type': ConditionType.TIME,
        'expression': {
            'check': 'is_work_hours',
            'work_start': '09:00',
            'work_end': '18:00',
            'work_days': [1, 2, 3, 4, 5]  # 週一到週五
        },
        'requires_param': False,
    },
    {
        'code': 'VALID_PERIOD',
        'name': '有效期限',
        'description': '資料必須在有效期限內',
        'condition_type': ConditionType.TIME,
        'expression': {
            'field': 'valid_until',
            'operator': 'gte',
            'compare_to': 'now'
        },
        'requires_param': False,
    },

    # 狀態條件
    {
        'code': 'STATUS_DRAFT',
        'name': '草稿狀態',
        'description': '只能操作草稿狀態的資源',
        'condition_type': ConditionType.STATUS,
        'expression': {
            'field': 'status',
            'operator': 'eq',
            'compare_to': 'DRAFT'
        },
        'requires_param': False,
    },
    {
        'code': 'STATUS_NOT_APPROVED',
        'name': '未核准狀態',
        'description': '只能操作未核准的資源',
        'condition_type': ConditionType.STATUS,
        'expression': {
            'field': 'status',
            'operator': 'not_in',
            'compare_to': ['APPROVED', 'COMPLETED']
        },
        'requires_param': False,
    },
    {
        'code': 'FLOW_PENDING',
        'name': '待處理流程',
        'description': '只能操作待自己處理的流程',
        'condition_type': ConditionType.STATUS,
        'expression': {
            'field': 'current_handler_secure_code',
            'operator': 'eq',
            'compare_to': 'current_user.secure_code'
        },
        'requires_param': False,
    },

    # 代理條件
    {
        'code': 'DELEGATED',
        'name': '被代理',
        'description': '透過代理機制取得的權限',
        'condition_type': ConditionType.DELEGATE,
        'expression': {
            'check': 'has_valid_delegation',
            'delegation_type': 'any'
        },
        'requires_param': False,
    },
]
