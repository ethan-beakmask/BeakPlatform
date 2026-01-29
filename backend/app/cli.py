"""
BeakPlatform - CLI Commands
命令列工具

使用方式:
    flask module list          # 列出所有模組
    flask module info <name>   # 顯示模組詳細資訊
    flask module sync          # 同步所有模組（權限、選單）
    flask module enable <name> # 啟用模組
    flask module disable <name># 停用模組
"""
import click
from flask import current_app
from flask.cli import with_appcontext


def register_cli(app):
    """註冊 CLI 命令到 Flask 應用程式"""
    app.cli.add_command(module_cli)


@click.group('module')
def module_cli():
    """模組管理命令"""
    pass


@module_cli.command('list')
@with_appcontext
def list_modules():
    """列出所有模組"""
    from .module_loader import module_loader

    click.echo("\n=== BeakPlatform Modules ===\n")

    modules = module_loader.modules
    if not modules:
        click.echo("No modules found.")
        return

    for name, module in modules.items():
        status = click.style("ENABLED", fg="green") if module.enabled else click.style("DISABLED", fg="red")
        click.echo(f"  {name} v{module.version} [{status}]")
        click.echo(f"    {module.display_name}")
        if module.description:
            click.echo(f"    {module.description}")
        click.echo()

    click.echo(f"Total: {len(modules)} module(s)")


@module_cli.command('info')
@click.argument('name')
@with_appcontext
def module_info(name):
    """顯示模組詳細資訊"""
    from .module_loader import module_loader

    module = module_loader.get_module(name)
    if not module:
        click.echo(f"Module '{name}' not found.", err=True)
        return

    click.echo(f"\n=== {module.display_name} ({module.name}) ===\n")
    click.echo(f"Version:     {module.version}")
    click.echo(f"Author:      {module.author or 'N/A'}")
    click.echo(f"Description: {module.description or 'N/A'}")
    click.echo(f"Enabled:     {'Yes' if module.enabled else 'No'}")
    click.echo(f"Path:        {module.path}")

    if module.dependencies:
        click.echo(f"Dependencies: {', '.join(module.dependencies)}")

    if module.permissions:
        click.echo(f"\nPermissions ({len(module.permissions)}):")
        for perm in module.permissions:
            click.echo(f"  - {perm.get('code')}: {perm.get('name')}")

    if module.menu_items:
        click.echo(f"\nMenu Items:")
        _print_menu_tree(module.menu_items, indent=2)


def _print_menu_tree(items, indent=0):
    """遞迴列印選單樹"""
    for item in items:
        prefix = " " * indent
        click.echo(f"{prefix}- {item.get('code')}: {item.get('name')}")
        children = item.get('children', [])
        if children:
            _print_menu_tree(children, indent + 2)


@module_cli.command('sync')
@click.option('--force', is_flag=True, default=False,
              help='強制覆蓋已存在的選單（會覆蓋管理員的手動修改）')
@with_appcontext
def sync_modules(force):
    """同步所有模組（權限、選單）"""
    from .module_loader import module_loader
    from .services.module_permission_service import ModulePermissionService
    from .services.module_menu_service import ModuleMenuService

    click.echo("\n=== Syncing Modules ===\n")

    if force:
        click.echo(click.style("Force mode: 將覆蓋所有手動修改", fg="yellow"))
        click.echo()

    # 同步權限
    click.echo("Syncing permissions...")
    perm_results = ModulePermissionService.sync_all_module_permissions(module_loader)
    for mod_name, result in perm_results.items():
        if 'error' in result:
            click.echo(f"  {mod_name}: " + click.style(f"ERROR - {result['error']}", fg="red"))
        else:
            click.echo(
                f"  {mod_name}: "
                f"{result.get('created', 0)} created, "
                f"{result.get('updated', 0)} updated, "
                f"{result.get('unchanged', 0)} unchanged"
            )

    # 同步選單
    click.echo("\nSyncing menus...")
    menu_results = ModuleMenuService.sync_all_module_menus(module_loader, force=force)
    for mod_name, result in menu_results.items():
        if 'error' in result:
            click.echo(f"  {mod_name}: " + click.style(f"ERROR - {result['error']}", fg="red"))
        else:
            click.echo(
                f"  {mod_name}: "
                f"{result.get('created', 0)} created, "
                f"{result.get('updated', 0)} updated, "
                f"{result.get('unchanged', 0)} unchanged"
            )

    click.echo("\n" + click.style("Sync complete!", fg="green"))


@module_cli.command('enable')
@click.argument('name')
@with_appcontext
def enable_module(name):
    """啟用模組"""
    from .module_loader import module_loader

    module = module_loader.get_module(name)
    if not module:
        click.echo(f"Module '{name}' not found.", err=True)
        return

    if module.enabled:
        click.echo(f"Module '{name}' is already enabled.")
        return

    # 啟用模組（這裡只是標記，實際需要重啟應用）
    module.enabled = True
    click.echo(f"Module '{name}' marked as enabled.")
    click.echo(click.style("Note: Restart the application to apply changes.", fg="yellow"))


@module_cli.command('disable')
@click.argument('name')
@with_appcontext
def disable_module(name):
    """停用模組"""
    from .module_loader import module_loader
    from .services.module_permission_service import ModulePermissionService
    from .services.module_menu_service import ModuleMenuService

    module = module_loader.get_module(name)
    if not module:
        click.echo(f"Module '{name}' not found.", err=True)
        return

    if not module.enabled:
        click.echo(f"Module '{name}' is already disabled.")
        return

    # 停用權限
    perm_count = ModulePermissionService.deactivate_module_permissions(name)
    click.echo(f"Deactivated {perm_count} permission(s).")

    # 停用選單
    menu_count = ModuleMenuService.deactivate_module_menus(name)
    click.echo(f"Deactivated {menu_count} menu item(s).")

    # 標記模組為停用
    module.enabled = False
    click.echo(f"Module '{name}' disabled.")
    click.echo(click.style("Note: Restart the application to fully unload the module.", fg="yellow"))


@module_cli.command('register')
@with_appcontext
def register_modules():
    """掃描並註冊新模組"""
    from .module_loader import module_loader

    click.echo("\n=== Discovering Modules ===\n")

    # 重新掃描模組
    discovered = module_loader.discover_modules()

    if discovered:
        click.echo(f"Discovered {len(discovered)} module(s):")
        for name in discovered:
            module = module_loader.get_module(name)
            click.echo(f"  - {name} v{module.version}")
    else:
        click.echo("No new modules found.")

    # 驗證依賴
    dep_errors = module_loader.validate_dependencies()
    if dep_errors:
        click.echo("\n" + click.style("Dependency errors:", fg="red"))
        for name, errors in dep_errors.items():
            for error in errors:
                click.echo(f"  {name}: {error}")

    click.echo("\nRun 'flask module sync' to synchronize permissions and menus.")


@module_cli.command('status')
@with_appcontext
def module_status():
    """顯示模組系統狀態"""
    from .module_loader import module_loader
    from .models import Permission, MenuItem

    click.echo("\n=== Module System Status ===\n")

    # 模組統計
    total = len(module_loader.modules)
    enabled = len([m for m in module_loader.modules.values() if m.enabled])
    click.echo(f"Modules: {enabled}/{total} enabled")

    # 權限統計
    module_perms = Permission.query.filter(
        Permission.code.like('%.%'),  # 模組權限格式
        Permission.is_deleted == False
    ).count()
    click.echo(f"Module Permissions: {module_perms}")

    # 選單統計
    module_menus = MenuItem.query.filter(
        MenuItem.org_secure_code == 'system.local',
        MenuItem.is_deleted == False
    ).count()
    click.echo(f"Module Menu Items: {module_menus}")

    # 列出已載入的模組
    click.echo("\nLoaded modules:")
    for module in module_loader.get_loaded_modules():
        perms = len(module.permissions) if module.permissions else 0
        menus = len(module.menu_items) if module.menu_items else 0
        click.echo(f"  - {module.name}: {perms} permissions, {menus} menu items")
