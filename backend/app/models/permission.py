"""
BeakPlatform Permission Model
權限 Model

RBAC 權限系統 - 定義資源和操作的權限
"""
from typing import Dict, Any, List

from sqlalchemy import Column, String, Boolean, Text
from sqlalchemy.orm import relationship

from .base import BaseModel
from .. import db


class ResourceType:
    """
    資源類型

    定義系統中可被控管的資源類型
    """
    # 核心資源
    USER = 'USER'                  # 用戶
    ORGANIZATION = 'ORGANIZATION'  # 企業
    DEPARTMENT = 'DEPARTMENT'      # 部門
    GROUP = 'GROUP'                # 群組
    ROLE = 'ROLE'                  # 角色

    # 表單流程
    FORM_TEMPLATE = 'FORM_TEMPLATE'    # 表單範本
    FORM_INSTANCE = 'FORM_INSTANCE'    # 表單填報
    FLOW_DEFINITION = 'FLOW_DEFINITION'  # 流程定義
    FLOW_INSTANCE = 'FLOW_INSTANCE'    # 流程實例

    # 模組
    MODULE = 'MODULE'              # 模組
    MODULE_CONTENT = 'MODULE_CONTENT'  # 模組內容

    # 系統
    SYSTEM_SETTING = 'SYSTEM_SETTING'  # 系統設定
    AUDIT_LOG = 'AUDIT_LOG'        # 稽核日誌
    REPORT = 'REPORT'              # 報表
    CONTRACT = 'CONTRACT'          # 合約

    # 商店
    STORE_TEMPLATE = 'STORE_TEMPLATE'  # 商店模板


class ActionType:
    """
    操作類型

    定義對資源可執行的操作
    """
    # 基本 CRUD
    CREATE = 'CREATE'    # 新增
    READ = 'READ'        # 讀取/檢視
    UPDATE = 'UPDATE'    # 編輯/更新
    DELETE = 'DELETE'    # 刪除

    # 狀態變更
    ACTIVATE = 'ACTIVATE'      # 啟用
    DEACTIVATE = 'DEACTIVATE'  # 停用
    PUBLISH = 'PUBLISH'        # 發布
    ARCHIVE = 'ARCHIVE'        # 封存

    # 流程相關
    APPROVE = 'APPROVE'    # 審核通過
    REJECT = 'REJECT'      # 審核退回
    TRANSFER = 'TRANSFER'  # 轉交
    REMIND = 'REMIND'      # 催辦

    # 匯出/匯入
    EXPORT = 'EXPORT'    # 匯出
    IMPORT = 'IMPORT'    # 匯入

    # 管理
    ASSIGN = 'ASSIGN'      # 指派 (如：指派角色)
    MANAGE = 'MANAGE'      # 管理 (完整管理權限)


class PermissionLevel:
    """
    權限層級

    與角色層級對應，用於控制權限的可見性和可授予範圍
    """
    SYSTEM = 'SYSTEM'    # 系統級權限 (只有系統管理員可授予)
    ORG = 'ORG'          # 企業級權限 (企業管理員可授予)
    MODULE = 'MODULE'    # 模組級權限 (模組管理員可授予)


class Permission(BaseModel):
    """
    權限 Model

    定義「資源 + 操作」的權限組合。

    權限代碼格式：{resource_type}:{action}
    例如：user:create, form_template:read, flow_instance:approve

    權限是全局定義的，不屬於特定企業 (使用 BaseModel 而非 TenantBaseModel)。
    """
    __tablename__ = 'permissions'

    # 資源類型
    resource_type = Column(
        String(50),
        nullable=False,
        index=True
    )

    # 操作類型
    action = Column(
        String(50),
        nullable=False,
        index=True
    )

    # 權限代碼 (唯一，格式: resource_type:action)
    code = Column(
        String(100),
        unique=True,
        nullable=False,
        index=True
    )

    # 權限名稱 (顯示用)
    name = Column(String(255), nullable=False)

    # 權限描述
    description = Column(Text, nullable=True)

    # 權限層級 (控制誰可以授予此權限)
    permission_level = Column(
        String(20),
        default=PermissionLevel.ORG,
        nullable=False,
        index=True
    )

    # 是否為系統內建權限 (不可刪除)
    is_system_permission = Column(Boolean, default=False, nullable=False)

    # 是否啟用
    is_active = Column(Boolean, default=True, nullable=False)

    # 關聯: 角色權限
    role_permissions = relationship(
        'RolePermission',
        back_populates='permission',
        lazy='dynamic'
    )

    @classmethod
    def generate_code(cls, resource_type: str, action: str) -> str:
        """生成權限代碼"""
        return f'{resource_type.lower()}:{action.lower()}'

    @property
    def is_system_level(self) -> bool:
        """是否為系統級權限"""
        return self.permission_level == PermissionLevel.SYSTEM

    @property
    def is_org_level(self) -> bool:
        """是否為企業級權限"""
        return self.permission_level == PermissionLevel.ORG

    @property
    def is_module_level(self) -> bool:
        """是否為模組級權限"""
        return self.permission_level == PermissionLevel.MODULE

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            'resource_type': self.resource_type,
            'action': self.action,
            'code': self.code,
            'name': self.name,
            'description': self.description,
            'permission_level': self.permission_level,
            'is_system_permission': self.is_system_permission,
            'is_active': self.is_active,
        })
        return base

    def __repr__(self):
        return f'<Permission {self.code}>'


# 系統預設權限定義
DEFAULT_PERMISSIONS = [
    # 用戶管理
    {'resource_type': ResourceType.USER, 'action': ActionType.CREATE, 'name': '新增用戶', 'level': PermissionLevel.ORG},
    {'resource_type': ResourceType.USER, 'action': ActionType.READ, 'name': '檢視用戶', 'level': PermissionLevel.ORG},
    {'resource_type': ResourceType.USER, 'action': ActionType.UPDATE, 'name': '編輯用戶', 'level': PermissionLevel.ORG},
    {'resource_type': ResourceType.USER, 'action': ActionType.DELETE, 'name': '刪除用戶', 'level': PermissionLevel.ORG},
    {'resource_type': ResourceType.USER, 'action': ActionType.ACTIVATE, 'name': '啟用用戶', 'level': PermissionLevel.ORG},
    {'resource_type': ResourceType.USER, 'action': ActionType.DEACTIVATE, 'name': '停用用戶', 'level': PermissionLevel.ORG},

    # 部門管理
    {'resource_type': ResourceType.DEPARTMENT, 'action': ActionType.CREATE, 'name': '新增部門', 'level': PermissionLevel.ORG},
    {'resource_type': ResourceType.DEPARTMENT, 'action': ActionType.READ, 'name': '檢視部門', 'level': PermissionLevel.ORG},
    {'resource_type': ResourceType.DEPARTMENT, 'action': ActionType.UPDATE, 'name': '編輯部門', 'level': PermissionLevel.ORG},
    {'resource_type': ResourceType.DEPARTMENT, 'action': ActionType.DELETE, 'name': '刪除部門', 'level': PermissionLevel.ORG},

    # 角色管理
    {'resource_type': ResourceType.ROLE, 'action': ActionType.CREATE, 'name': '新增角色', 'level': PermissionLevel.ORG},
    {'resource_type': ResourceType.ROLE, 'action': ActionType.READ, 'name': '檢視角色', 'level': PermissionLevel.ORG},
    {'resource_type': ResourceType.ROLE, 'action': ActionType.UPDATE, 'name': '編輯角色', 'level': PermissionLevel.ORG},
    {'resource_type': ResourceType.ROLE, 'action': ActionType.DELETE, 'name': '刪除角色', 'level': PermissionLevel.ORG},
    {'resource_type': ResourceType.ROLE, 'action': ActionType.ASSIGN, 'name': '指派角色', 'level': PermissionLevel.ORG},

    # 表單範本
    {'resource_type': ResourceType.FORM_TEMPLATE, 'action': ActionType.CREATE, 'name': '新增表單範本', 'level': PermissionLevel.ORG},
    {'resource_type': ResourceType.FORM_TEMPLATE, 'action': ActionType.READ, 'name': '檢視表單範本', 'level': PermissionLevel.ORG},
    {'resource_type': ResourceType.FORM_TEMPLATE, 'action': ActionType.UPDATE, 'name': '編輯表單範本', 'level': PermissionLevel.ORG},
    {'resource_type': ResourceType.FORM_TEMPLATE, 'action': ActionType.DELETE, 'name': '刪除表單範本', 'level': PermissionLevel.ORG},
    {'resource_type': ResourceType.FORM_TEMPLATE, 'action': ActionType.PUBLISH, 'name': '發布表單範本', 'level': PermissionLevel.ORG},

    # 表單填報
    {'resource_type': ResourceType.FORM_INSTANCE, 'action': ActionType.CREATE, 'name': '填寫表單', 'level': PermissionLevel.MODULE},
    {'resource_type': ResourceType.FORM_INSTANCE, 'action': ActionType.READ, 'name': '檢視表單填報', 'level': PermissionLevel.MODULE},
    {'resource_type': ResourceType.FORM_INSTANCE, 'action': ActionType.UPDATE, 'name': '編輯表單填報', 'level': PermissionLevel.MODULE},
    {'resource_type': ResourceType.FORM_INSTANCE, 'action': ActionType.DELETE, 'name': '刪除表單填報', 'level': PermissionLevel.MODULE},
    {'resource_type': ResourceType.FORM_INSTANCE, 'action': ActionType.EXPORT, 'name': '匯出表單填報', 'level': PermissionLevel.MODULE},

    # 流程定義
    {'resource_type': ResourceType.FLOW_DEFINITION, 'action': ActionType.CREATE, 'name': '新增流程定義', 'level': PermissionLevel.ORG},
    {'resource_type': ResourceType.FLOW_DEFINITION, 'action': ActionType.READ, 'name': '檢視流程定義', 'level': PermissionLevel.ORG},
    {'resource_type': ResourceType.FLOW_DEFINITION, 'action': ActionType.UPDATE, 'name': '編輯流程定義', 'level': PermissionLevel.ORG},
    {'resource_type': ResourceType.FLOW_DEFINITION, 'action': ActionType.DELETE, 'name': '刪除流程定義', 'level': PermissionLevel.ORG},
    {'resource_type': ResourceType.FLOW_DEFINITION, 'action': ActionType.ACTIVATE, 'name': '啟用流程定義', 'level': PermissionLevel.ORG},

    # 流程實例
    {'resource_type': ResourceType.FLOW_INSTANCE, 'action': ActionType.READ, 'name': '檢視流程實例', 'level': PermissionLevel.MODULE},
    {'resource_type': ResourceType.FLOW_INSTANCE, 'action': ActionType.APPROVE, 'name': '審核通過', 'level': PermissionLevel.MODULE},
    {'resource_type': ResourceType.FLOW_INSTANCE, 'action': ActionType.REJECT, 'name': '審核退回', 'level': PermissionLevel.MODULE},
    {'resource_type': ResourceType.FLOW_INSTANCE, 'action': ActionType.TRANSFER, 'name': '轉交流程', 'level': PermissionLevel.MODULE},
    {'resource_type': ResourceType.FLOW_INSTANCE, 'action': ActionType.REMIND, 'name': '催辦流程', 'level': PermissionLevel.MODULE},

    # 模組管理
    {'resource_type': ResourceType.MODULE, 'action': ActionType.CREATE, 'name': '新增模組', 'level': PermissionLevel.ORG},
    {'resource_type': ResourceType.MODULE, 'action': ActionType.READ, 'name': '檢視模組', 'level': PermissionLevel.MODULE},
    {'resource_type': ResourceType.MODULE, 'action': ActionType.UPDATE, 'name': '編輯模組', 'level': PermissionLevel.ORG},
    {'resource_type': ResourceType.MODULE, 'action': ActionType.DELETE, 'name': '刪除模組', 'level': PermissionLevel.ORG},
    {'resource_type': ResourceType.MODULE, 'action': ActionType.MANAGE, 'name': '管理模組', 'level': PermissionLevel.MODULE},

    # 模組內容
    {'resource_type': ResourceType.MODULE_CONTENT, 'action': ActionType.CREATE, 'name': '新增內容', 'level': PermissionLevel.MODULE},
    {'resource_type': ResourceType.MODULE_CONTENT, 'action': ActionType.READ, 'name': '檢視內容', 'level': PermissionLevel.MODULE},
    {'resource_type': ResourceType.MODULE_CONTENT, 'action': ActionType.UPDATE, 'name': '編輯內容', 'level': PermissionLevel.MODULE},
    {'resource_type': ResourceType.MODULE_CONTENT, 'action': ActionType.DELETE, 'name': '刪除內容', 'level': PermissionLevel.MODULE},

    # 系統設定 (系統級)
    {'resource_type': ResourceType.SYSTEM_SETTING, 'action': ActionType.READ, 'name': '檢視系統設定', 'level': PermissionLevel.SYSTEM},
    {'resource_type': ResourceType.SYSTEM_SETTING, 'action': ActionType.UPDATE, 'name': '編輯系統設定', 'level': PermissionLevel.SYSTEM},

    # 企業管理 (系統級)
    {'resource_type': ResourceType.ORGANIZATION, 'action': ActionType.CREATE, 'name': '新增企業', 'level': PermissionLevel.SYSTEM},
    {'resource_type': ResourceType.ORGANIZATION, 'action': ActionType.READ, 'name': '檢視企業', 'level': PermissionLevel.SYSTEM},
    {'resource_type': ResourceType.ORGANIZATION, 'action': ActionType.UPDATE, 'name': '編輯企業', 'level': PermissionLevel.SYSTEM},
    {'resource_type': ResourceType.ORGANIZATION, 'action': ActionType.DELETE, 'name': '刪除企業', 'level': PermissionLevel.SYSTEM},

    # 合約管理 (系統級)
    {'resource_type': ResourceType.CONTRACT, 'action': ActionType.CREATE, 'name': '新增合約', 'level': PermissionLevel.SYSTEM},
    {'resource_type': ResourceType.CONTRACT, 'action': ActionType.READ, 'name': '檢視合約', 'level': PermissionLevel.SYSTEM},
    {'resource_type': ResourceType.CONTRACT, 'action': ActionType.UPDATE, 'name': '編輯合約', 'level': PermissionLevel.SYSTEM},
    {'resource_type': ResourceType.CONTRACT, 'action': ActionType.DELETE, 'name': '刪除合約', 'level': PermissionLevel.SYSTEM},

    # 稽核日誌
    {'resource_type': ResourceType.AUDIT_LOG, 'action': ActionType.READ, 'name': '檢視稽核日誌', 'level': PermissionLevel.ORG},
    {'resource_type': ResourceType.AUDIT_LOG, 'action': ActionType.EXPORT, 'name': '匯出稽核日誌', 'level': PermissionLevel.ORG},

    # 報表
    {'resource_type': ResourceType.REPORT, 'action': ActionType.READ, 'name': '檢視報表', 'level': PermissionLevel.ORG},
    {'resource_type': ResourceType.REPORT, 'action': ActionType.EXPORT, 'name': '匯出報表', 'level': PermissionLevel.ORG},

    # 商店 (系統級)
    {'resource_type': ResourceType.STORE_TEMPLATE, 'action': ActionType.CREATE, 'name': '上傳商店模板', 'level': PermissionLevel.ORG},
    {'resource_type': ResourceType.STORE_TEMPLATE, 'action': ActionType.READ, 'name': '瀏覽商店模板', 'level': PermissionLevel.ORG},
    {'resource_type': ResourceType.STORE_TEMPLATE, 'action': ActionType.APPROVE, 'name': '審核商店模板', 'level': PermissionLevel.SYSTEM},
    {'resource_type': ResourceType.STORE_TEMPLATE, 'action': ActionType.DELETE, 'name': '下架商店模板', 'level': PermissionLevel.SYSTEM},
]
