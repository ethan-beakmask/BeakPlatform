"""模組同步共用服務。"""


class ModuleSyncService:
    """集中 `flask module sync` 與 bootstrap 的模組同步順序。"""

    @staticmethod
    def sync_all(module_loader, force=False) -> dict:
        from app.services.lookup_service import LookupService
        from app.services.module_menu_service import ModuleMenuService
        from app.services.module_permission_service import ModulePermissionService
        from app.services.module_role_service import ModuleRoleService

        permissions = ModulePermissionService.sync_all_module_permissions(
            module_loader)
        menus = ModuleMenuService.sync_all_module_menus(
            module_loader, force=force)
        lookup = LookupService.sync_installed_modules(
            module_loader.get_loaded_modules())
        roles = ModuleRoleService.sync_all_module_roles(module_loader)
        return {
            'permissions': permissions,
            'menus': menus,
            'lookup': lookup,
            'roles': roles,
        }
