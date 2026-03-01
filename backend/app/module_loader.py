"""
BeakPlatform - Module Loader
模組載入器

負責：
1. 掃描 modules/ 目錄
2. 讀取模組元資料 (MODULE_INFO)
3. 驗證模組依賴
4. 註冊模組的 Blueprint
5. 註冊模組的選單項目
6. 執行模組的資料庫遷移
7. 註冊模組的靜態檔案目錄

靜態檔案規範：
  模組的靜態資源必須放在 modules/<name>/static/modules/<name>/ 目錄下，
  由 module_loader 自動註冊，透過 /static/modules/<name>/ URL 存取。
  禁止將模組靜態檔案複製到 backend/app/static/，避免雙份副本不同步。
"""
import os
import importlib
import importlib.util
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional

from flask import Flask, Blueprint

logger = logging.getLogger(__name__)


class ModuleInfo:
    """模組資訊封裝類別"""

    def __init__(self, name: str, path: Path, info: Dict[str, Any]):
        self.name = name
        self.path = path
        self.display_name = info.get('display_name', name)
        self.version = info.get('version', '0.0.0')
        self.description = info.get('description', '')
        self.author = info.get('author', '')
        self.dependencies = info.get('dependencies', [])
        self.platform_version = info.get('platform_version', '>=0.0.0')
        self.menu_items = info.get('menu_items', [])
        self.permissions = info.get('permissions', [])
        self.enabled = info.get('enabled', True)

        # Blueprint references (loaded later)
        self.api_blueprint = None
        self.web_blueprint = None

    def __repr__(self):
        return f"<ModuleInfo {self.name} v{self.version}>"


class ModuleLoader:
    """模組載入器"""

    # 平台版本
    PLATFORM_VERSION = '1.0.0'

    def __init__(self, app: Flask = None, modules_path: str = None):
        self.app = app
        self.modules_path = Path(modules_path) if modules_path else None
        self.modules: Dict[str, ModuleInfo] = {}
        self._loaded = False

        if app:
            self.init_app(app, modules_path)

    def init_app(self, app: Flask, modules_path: str = None):
        """初始化模組載入器"""
        self.app = app

        # 決定 modules 目錄路徑
        if modules_path:
            self.modules_path = Path(modules_path)
        else:
            # 預設在 backend 同層的 modules 目錄
            backend_path = Path(app.root_path).parent
            self.modules_path = backend_path.parent / 'modules'

        # 確保目錄存在
        self.modules_path.mkdir(parents=True, exist_ok=True)

        # 將 modules 目錄加入 Python path，讓模組可以互相匯入
        import sys
        modules_parent = str(self.modules_path.parent)
        if modules_parent not in sys.path:
            sys.path.insert(0, modules_parent)

        # 儲存到 app 擴展
        app.extensions['module_loader'] = self

        logger.info(f"ModuleLoader initialized, modules_path: {self.modules_path}")

    def discover_modules(self) -> List[str]:
        """
        掃描並發現所有模組

        Returns:
            發現的模組名稱列表
        """
        if not self.modules_path.exists():
            logger.warning(f"Modules path does not exist: {self.modules_path}")
            return []

        discovered = []

        for item in self.modules_path.iterdir():
            if not item.is_dir():
                continue

            # 跳過特殊目錄
            if item.name.startswith(('_', '.')):
                continue

            # 檢查是否有 __init__.py
            init_file = item / '__init__.py'
            if not init_file.exists():
                logger.debug(f"Skipping {item.name}: no __init__.py")
                continue

            # 嘗試讀取 MODULE_INFO
            module_info = self._load_module_info(item)
            if module_info:
                self.modules[item.name] = module_info
                discovered.append(item.name)
                logger.info(f"Discovered module: {item.name} v{module_info.version}")
            else:
                logger.warning(f"Skipping {item.name}: no valid MODULE_INFO")

        return discovered

    def _load_module_info(self, module_path: Path) -> Optional[ModuleInfo]:
        """
        載入模組的 MODULE_INFO

        Args:
            module_path: 模組目錄路徑

        Returns:
            ModuleInfo 物件，失敗時返回 None
        """
        init_file = module_path / '__init__.py'

        try:
            # 動態載入模組的 __init__.py
            spec = importlib.util.spec_from_file_location(
                f"modules.{module_path.name}",
                init_file
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # 取得 MODULE_INFO
            if not hasattr(module, 'MODULE_INFO'):
                return None

            info = module.MODULE_INFO
            if not isinstance(info, dict):
                return None

            return ModuleInfo(module_path.name, module_path, info)

        except Exception as e:
            logger.error(f"Failed to load MODULE_INFO from {module_path}: {e}")
            return None

    def validate_dependencies(self) -> Dict[str, List[str]]:
        """
        驗證模組依賴

        Returns:
            依賴錯誤字典 {module_name: [error_messages]}
        """
        errors = {}

        for name, module in self.modules.items():
            module_errors = []

            # 檢查依賴的其他模組
            for dep in module.dependencies:
                if dep not in self.modules:
                    module_errors.append(f"Missing dependency: {dep}")
                elif not self.modules[dep].enabled:
                    module_errors.append(f"Dependency disabled: {dep}")

            # TODO: 檢查平台版本要求
            # if not self._check_version_requirement(module.platform_version):
            #     module_errors.append(f"Platform version requirement not met: {module.platform_version}")

            if module_errors:
                errors[name] = module_errors

        return errors

    def load_modules(self) -> Dict[str, bool]:
        """
        載入所有已發現的模組

        Returns:
            載入結果 {module_name: success}
        """
        if self._loaded:
            logger.warning("Modules already loaded, skipping")
            return {}

        results = {}

        # 按依賴順序排序（簡單實作：無依賴的先載入）
        sorted_modules = self._sort_by_dependencies()

        for name in sorted_modules:
            module = self.modules[name]

            if not module.enabled:
                logger.info(f"Module {name} is disabled, skipping")
                results[name] = False
                continue

            try:
                self._load_module(module)
                results[name] = True
                logger.info(f"Module {name} loaded successfully")
            except Exception as e:
                results[name] = False
                logger.error(f"Failed to load module {name}: {e}")

        self._loaded = True
        return results

    def _sort_by_dependencies(self) -> List[str]:
        """
        按依賴順序排序模組

        Returns:
            排序後的模組名稱列表
        """
        # 簡單拓撲排序
        visited = set()
        result = []

        def visit(name: str):
            if name in visited:
                return
            visited.add(name)

            module = self.modules.get(name)
            if module:
                for dep in module.dependencies:
                    visit(dep)
                result.append(name)

        for name in self.modules:
            visit(name)

        return result

    def _load_module(self, module: ModuleInfo):
        """
        載入單一模組

        Args:
            module: ModuleInfo 物件
        """
        # 載入 API Blueprint
        api_init = module.path / 'api' / '__init__.py'
        if api_init.exists():
            try:
                api_module = self._import_module_file(
                    f"modules.{module.name}.api",
                    api_init
                )
                if hasattr(api_module, 'api_bp'):
                    module.api_blueprint = api_module.api_bp
                    self.app.register_blueprint(api_module.api_bp)
                    logger.debug(f"Registered API blueprint for {module.name}")

                # 註冊額外的 Blueprint（用於相容性）
                if hasattr(api_module, 'additional_blueprints'):
                    for bp in api_module.additional_blueprints:
                        self.app.register_blueprint(bp)
                        logger.debug(f"Registered additional blueprint {bp.name} for {module.name}")
            except Exception as e:
                logger.error(f"Failed to load API blueprint for {module.name}: {e}")

        # 載入 Web Blueprint
        web_init = module.path / 'web' / '__init__.py'
        if web_init.exists():
            try:
                web_module = self._import_module_file(
                    f"modules.{module.name}.web",
                    web_init
                )
                if hasattr(web_module, 'web_bp'):
                    module.web_blueprint = web_module.web_bp
                    self.app.register_blueprint(web_module.web_bp)
                    logger.debug(f"Registered Web blueprint for {module.name}")
            except Exception as e:
                logger.error(f"Failed to load Web blueprint for {module.name}: {e}")

        # 註冊模板目錄
        templates_path = module.path / 'templates'
        if templates_path.exists():
            # Flask 會自動搜尋 Blueprint 的 template_folder
            # 但我們也可以加入到 Jinja loader
            pass

        # 註冊靜態檔案目錄
        # 模組靜態檔案結構：modules/<name>/static/modules/<name>/{js,css,icons}/
        # 對應 URL：/static/modules/<name>/{js,css,icons}/
        static_path = module.path / 'static' / 'modules' / module.name
        if static_path.exists():
            static_bp = Blueprint(
                f'{module.name}_static',
                module.name,
                static_folder=str(static_path),
                static_url_path=f'/static/modules/{module.name}'
            )
            self.app.register_blueprint(static_bp)
            logger.info(f"Registered static files for {module.name}: /static/modules/{module.name}/")

        # 註冊模組翻譯目錄
        # 模組翻譯結構：modules/<name>/translations/{en,zh_CN,ja}/LC_MESSAGES/messages.po
        translations_path = module.path / 'translations'
        if translations_path.exists():
            # 將模組翻譯目錄加入 Babel 的搜尋路徑（分號分隔多路徑）
            current_dirs = self.app.config.get('BABEL_TRANSLATION_DIRECTORIES', 'translations')
            module_trans_dir = str(translations_path)
            if module_trans_dir not in current_dirs:
                self.app.config['BABEL_TRANSLATION_DIRECTORIES'] = f"{current_dirs};{module_trans_dir}"
                logger.info(f"Registered translations for {module.name}: {translations_path}")

        # 調用模組運行時初始化 hook（用於啟動背景服務等）
        self._call_init_runtime(module)

    def _import_module_file(self, module_name: str, file_path: Path):
        """
        動態匯入模組檔案

        Args:
            module_name: 模組完整名稱
            file_path: 檔案路徑

        Returns:
            匯入的模組物件
        """
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        module = importlib.util.module_from_spec(spec)

        # 將模組加入 sys.modules 讓相對匯入能運作
        import sys
        sys.modules[module_name] = module

        spec.loader.exec_module(module)
        return module

    def _call_init_runtime(self, module: ModuleInfo):
        """
        調用模組的運行時初始化 hook

        如果模組定義了 init_runtime(app) 函數，則調用它。
        用於啟動背景服務（如工作流執行器）等。

        Args:
            module: ModuleInfo 物件
        """
        init_file = module.path / '__init__.py'
        try:
            module_obj = self._import_module_file(
                f"modules.{module.name}",
                init_file
            )
            if hasattr(module_obj, 'init_runtime'):
                logger.info(f"Calling init_runtime for module {module.name}")
                module_obj.init_runtime(self.app)
        except Exception as e:
            logger.error(f"Failed to call init_runtime for {module.name}: {e}")

    def get_all_menu_items(self) -> List[Dict[str, Any]]:
        """
        取得所有已載入模組的選單項目

        Returns:
            選單項目列表
        """
        items = []
        for module in self.modules.values():
            if module.enabled and module.menu_items:
                for item in module.menu_items:
                    # 加入模組來源資訊
                    item_copy = dict(item)
                    item_copy['_module'] = module.name
                    items.append(item_copy)
        return items

    def get_all_permissions(self) -> List[Dict[str, Any]]:
        """
        取得所有已載入模組的權限定義

        Returns:
            權限定義列表
        """
        permissions = []
        for module in self.modules.values():
            if module.enabled and module.permissions:
                for perm in module.permissions:
                    perm_copy = dict(perm)
                    perm_copy['_module'] = module.name
                    permissions.append(perm_copy)
        return permissions

    def get_module(self, name: str) -> Optional[ModuleInfo]:
        """
        取得指定模組的資訊

        Args:
            name: 模組名稱

        Returns:
            ModuleInfo 物件
        """
        return self.modules.get(name)

    def get_loaded_modules(self) -> List[ModuleInfo]:
        """
        取得所有已載入的模組

        Returns:
            ModuleInfo 列表
        """
        return [m for m in self.modules.values() if m.enabled]


# 全域模組載入器實例
module_loader = ModuleLoader()


def init_module_loader(app: Flask, modules_path: str = None):
    """
    初始化模組載入器並載入所有模組

    Args:
        app: Flask 應用程式
        modules_path: 模組目錄路徑（可選）
    """
    module_loader.init_app(app, modules_path)

    # 發現模組
    discovered = module_loader.discover_modules()
    if discovered:
        logger.info(f"Discovered {len(discovered)} modules: {', '.join(discovered)}")

        # 驗證依賴
        dep_errors = module_loader.validate_dependencies()
        if dep_errors:
            for name, errors in dep_errors.items():
                logger.error(f"Module {name} has dependency errors: {errors}")
                # 停用有依賴錯誤的模組
                module_loader.modules[name].enabled = False

        # 載入模組
        results = module_loader.load_modules()
        loaded = [name for name, success in results.items() if success]
        if loaded:
            logger.info(f"Loaded {len(loaded)} modules: {', '.join(loaded)}")

            # 註冊模組權限和選單到資料庫（需要在 app context 中執行）
            def sync_module_data():
                # 同步權限
                try:
                    from .services.module_permission_service import ModulePermissionService
                    perm_results = ModulePermissionService.sync_all_module_permissions(module_loader)
                    for mod_name, result in perm_results.items():
                        if 'error' not in result:
                            logger.info(
                                f"Module {mod_name} permissions: "
                                f"{result.get('created', 0)} created, "
                                f"{result.get('updated', 0)} updated"
                            )
                except Exception as e:
                    logger.warning(f"Failed to register module permissions: {e}")

                # 同步選單
                try:
                    from .services.module_menu_service import ModuleMenuService
                    menu_results = ModuleMenuService.sync_all_module_menus(module_loader)
                    for mod_name, result in menu_results.items():
                        if 'error' not in result:
                            logger.info(
                                f"Module {mod_name} menus: "
                                f"{result.get('created', 0)} created, "
                                f"{result.get('updated', 0)} updated"
                            )
                except Exception as e:
                    logger.warning(f"Failed to register module menus: {e}")

                # 同步已安裝模組到 Lookup Table
                try:
                    from .services.lookup_service import LookupService
                    LookupService.sync_installed_modules(module_loader.get_loaded_modules())
                    logger.info("Installed modules synced to lookup table")
                except Exception as e:
                    logger.warning(f"Failed to sync installed modules: {e}")

            # 在 app context 中執行同步（可透過環境變數跳過）
            if not os.environ.get('SKIP_MODULE_SYNC'):
                with app.app_context():
                    sync_module_data()
            else:
                logger.info("Skipping module sync (SKIP_MODULE_SYNC is set)")
    else:
        logger.info("No modules found")

    return module_loader
