"""
BeakMask Menu Service
選單服務 - 負責建構用戶可見的選單樹

權限設計：
- MenuPermission 交叉表決定選單對 user_type 的可見性
- org_secure_code 用於管理權限（誰能編輯選單），不影響可見性
- required_permission 設定的選單需要通過 RBAC 權限檢查
- 模組選單需要企業擁有有效合約授權才可見

實作拆分為 4 個 Mixin（按職責）：
- _menu_tree.py: 選單樹建構與可見性過濾
- _menu_crud.py: 選單 CRUD 操作與權限設定
- _menu_module_filter.py: 模組/合約/ACL/社群選單過濾
- _menu_factory.py: 出廠預設值管理
"""
from ..models.user import UserType

from ._menu_tree import MenuTreeMixin
from ._menu_crud import MenuCrudMixin
from ._menu_module_filter import MenuModuleFilterMixin
from ._menu_factory import MenuFactoryMixin


class MenuService(
    MenuTreeMixin,
    MenuCrudMixin,
    MenuModuleFilterMixin,
    MenuFactoryMixin,
):
    """
    選單服務

    負責：
    1. 建構用戶可見的選單樹
    2. 選單 CRUD 操作
    3. 選單權限過濾

    權限設計：
    - MenuPermission 交叉表決定選單對 user_type 的可見性
    - org_secure_code 用於管理權限（誰能編輯/刪除選單），不影響可見性
    - required_permission 設定的選單需要通過 RBAC 權限檢查
    """

    # 用戶類型列表 (用於權限交叉表)
    USER_TYPES = [
        UserType.SYSTEM_ADMIN,
        UserType.ORG_ADMIN,
        UserType.EMPLOYEE,
        UserType.EXTERNAL,
    ]
