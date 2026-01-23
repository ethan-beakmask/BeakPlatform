# 平台模組化架構規劃

**建立日期**: 2026-01-12
**狀態**: 規劃中

## 背景

BeakMask 從 a6 移植表單流程模組時遇到多處不兼容：
- ID 系統差異 (`secure_code` vs `id`)
- 用戶關聯方式不同
- 變數表欄位名稱不同
- 執行器方法簽名不同

持續在 BeakMask 中修補會越來越複雜，決定採用模組化重組方案。

## 目標架構

```
┌─────────────────────────────────────────────────────┐
│                    新專案 (待命名)                   │
├─────────────────────────────────────────────────────┤
│  Layer 3: 應用模組                                   │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ │
│  │ 表單流程模組 │ │  RPA 模組    │ │  其他模組    │ │
│  │ (from a6)    │ │ (未來擴展)   │ │              │ │
│  └──────────────┘ └──────────────┘ └──────────────┘ │
├─────────────────────────────────────────────────────┤
│  Layer 2: 整合層 (Adapter)                           │
│  - IUserProvider: 統一用戶介面                       │
│  - IPermissionChecker: 權限檢查介面                  │
│  - IOrganizationContext: 企業上下文                  │
│  - EventBus: 模組間事件通訊                          │
├─────────────────────────────────────────────────────┤
│  Layer 1: 基礎平台 (from BeakMask)                   │
│  - 認證授權 (auth_interceptor, decorators)          │
│  - 多租戶隔離 (ResourceGateway, TenantBaseModel)    │
│  - 用戶/組織/部門/角色/權限                          │
│  - 選單控制 (Menu, Page, Permission)                 │
│  - 系統設定 (SystemSetting)                          │
└─────────────────────────────────────────────────────┘
```

## Phase 1: 基礎平台抽取

### 從 BeakMask 保留的模組

#### 安全核心 (必須)
- `security/auth_interceptor.py` - 全域認證攔截
- `security/decorators.py` - 認證裝飾器
- `security/resource_gateway.py` - 資源存取控制
- `security/tenant_isolation.py` - 多租戶隔離
- `security/url_access_control.py` - URL 存取控制
- `security/security_headers.py` - 安全標頭

#### 核心模型 (必須)
- `models/base.py` - BaseModel, TenantBaseModel
- `models/user.py` - 用戶
- `models/organization.py` - 企業
- `models/organizational_unit.py` - 部門/群組
- `models/role.py` - 角色
- `models/permission.py` - 權限
- `models/role_permission.py` - 角色權限關聯
- `models/menu_item.py` - 選單項目
- `models/menu_permission.py` - 選單權限
- `models/page.py` - 頁面
- `models/module.py` - 模組
- `models/system_setting.py` - 系統設定
- `models/audit_log.py` - 稽核日誌

#### 可選模型 (視需求)
- `models/job_level.py` - 職等
- `models/job_family.py` - 職系
- `models/job_title.py` - 職稱
- `models/duty.py` - 職務
- `models/delegation.py` - 代理
- `models/contract.py` - 合約

### 移除的模組 (表單流程相關)
- `models/form_*.py` - 全部
- `models/workflow_*.py` - 全部
- `models/node_*.py` - 全部
- `models/published_*.py` - 全部
- `services/workflow/` - 整個目錄
- `api/form_*.py` - 全部
- `api/workflow_*.py` - 全部

## Phase 2: 整合層設計

### 介面定義

```python
# platform/interfaces/user_provider.py
class IUserProvider(ABC):
    """用戶資訊提供者介面"""

    @abstractmethod
    def get_current_user(self) -> UserDTO:
        """取得當前用戶"""
        pass

    @abstractmethod
    def get_user_by_id(self, user_id: str) -> Optional[UserDTO]:
        """根據 ID 取得用戶"""
        pass

    @abstractmethod
    def get_user_departments(self, user_id: str) -> List[DepartmentDTO]:
        """取得用戶所屬部門"""
        pass


# platform/interfaces/permission_checker.py
class IPermissionChecker(ABC):
    """權限檢查介面"""

    @abstractmethod
    def check_permission(self, user_id: str, permission_code: str) -> bool:
        """檢查用戶是否有指定權限"""
        pass

    @abstractmethod
    def check_menu_access(self, user_id: str, menu_code: str) -> bool:
        """檢查用戶是否可存取選單"""
        pass


# platform/interfaces/organization_context.py
class IOrganizationContext(ABC):
    """企業上下文介面"""

    @abstractmethod
    def get_current_org(self) -> OrganizationDTO:
        """取得當前企業"""
        pass

    @abstractmethod
    def get_org_settings(self, key: str) -> Any:
        """取得企業設定"""
        pass
```

### 事件匯流

```python
# platform/events/event_bus.py
class EventBus:
    """模組間事件通訊"""

    def publish(self, event_type: str, data: dict):
        """發布事件"""
        pass

    def subscribe(self, event_type: str, handler: Callable):
        """訂閱事件"""
        pass

# 事件類型範例
EVENT_USER_LOGIN = 'user.login'
EVENT_USER_LOGOUT = 'user.logout'
EVENT_FORM_SUBMITTED = 'form.submitted'
EVENT_WORKFLOW_COMPLETED = 'workflow.completed'
```

## Phase 3: a6 模組化

### 最小改動原則

a6 表單流程模組保持原有架構，只做介面適配：

```python
# modules/form_workflow/adapters/user_adapter.py
class A6UserAdapter(IUserProvider):
    """將平台用戶介面適配到 a6"""

    def __init__(self, platform_user_provider: IUserProvider):
        self.platform = platform_user_provider

    def get_current_user(self) -> UserDTO:
        user = self.platform.get_current_user()
        # 轉換為 a6 期望的格式
        return self._convert_to_a6_format(user)
```

### 模組註冊

```python
# modules/form_workflow/__init__.py
class FormWorkflowModule:
    """表單流程模組"""

    MODULE_CODE = 'form_workflow'
    MODULE_NAME = '表單流程'

    def __init__(self, platform: Platform):
        self.platform = platform
        self.user_adapter = A6UserAdapter(platform.user_provider)

    def register_routes(self, app: Flask):
        """註冊路由"""
        from .api import forms_bp, workflows_bp
        app.register_blueprint(forms_bp)
        app.register_blueprint(workflows_bp)

    def register_menus(self) -> List[MenuItem]:
        """註冊選單項目"""
        return [
            MenuItem(code='forms', name='表單管理', ...),
            MenuItem(code='workflows', name='流程管理', ...),
        ]
```

## 待確認事項

1. **新專案名稱** - 建議: `BeakPlatform`, `CorePlatform`, `BaseFrame` ?
2. **目錄位置** - `/opt/BeakPlatform/` ?
3. **Phase 1 保留模組** - 上述列表是否需要調整?
4. **HR 結構模組** - 職等/職系/職稱是否歸入基礎平台?
5. **時間管理模組** - 班表/請假是否獨立成模組?

## 下一步

1. 確認上述待確認事項
2. 建立新專案目錄結構
3. 從 BeakMask 複製基礎平台代碼
4. 設計並實作整合層介面
5. 調整 a6 為模組形式
