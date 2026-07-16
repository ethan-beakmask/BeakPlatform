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

from .constants import SYSTEM_ORG_CODE


def register_cli(app):
    """註冊 CLI 命令到 Flask 應用程式"""
    app.cli.add_command(module_cli)
    app.cli.add_command(store_cli)


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
    from .services.module_role_service import ModuleRoleService

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

    # 補種模組預設角色（對所有持有效合約的企業，冪等）
    click.echo("\nSyncing module default roles...")
    try:
        role_results = ModuleRoleService.sync_all_module_roles(module_loader)
    except Exception as e:
        click.echo("  " + click.style(f"ERROR - {e}", fg="red"))
        raise
    if not role_results:
        click.echo("  (no modules declare default_roles)")
    for mod_name, result in role_results.items():
        click.echo(
            f"  {mod_name}: "
            f"{result.get('roles_created', 0)} roles created, "
            f"{result.get('roles_skipped', 0)} skipped (collision), "
            f"{result.get('mrr_created', 0)} menu role requirements, "
            f"{result.get('perms_assigned', 0)} role permissions"
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
        MenuItem.org_secure_code == SYSTEM_ORG_CODE,
        MenuItem.is_deleted == False
    ).count()
    click.echo(f"Module Menu Items: {module_menus}")

    # 列出已載入的模組
    click.echo("\nLoaded modules:")
    for module in module_loader.get_loaded_modules():
        perms = len(module.permissions) if module.permissions else 0
        menus = len(module.menu_items) if module.menu_items else 0
        click.echo(f"  - {module.name}: {perms} permissions, {menus} menu items")


# ================================================================
# Store CLI (內部商場)
# ================================================================

@click.group('store')
def store_cli():
    """內部商場管理命令"""
    pass


@store_cli.command('seed')
@click.option('--dir', 'fixture_dir', default=None, help='fixtures 目錄路徑')
@click.option('--force', is_flag=True, help='強制覆蓋已存在的商品')
@with_appcontext
def seed_store(fixture_dir, force):
    """從 fixtures/store/ 載入官方商品到 store_items"""
    import json
    from pathlib import Path
    from . import db
    from .models.store_item import StoreItem

    if fixture_dir:
        base = Path(fixture_dir)
    else:
        base = Path(current_app.root_path).parent.parent / 'fixtures' / 'store'

    if not base.exists():
        click.echo(click.style(f"Fixture directory not found: {base}", fg="red"))
        return

    json_files = sorted(base.glob('*.json'))
    if not json_files:
        click.echo("No fixture files found.")
        return

    click.echo(f"\n=== Seeding Store Items from {base} ===\n")

    stats = {'created': 0, 'updated': 0, 'skipped': 0}

    for f in json_files:
        try:
            data = json.loads(f.read_text(encoding='utf-8'))
            code = data.get('code')
            if not code:
                click.echo(click.style(f"  {f.name}: missing 'code', skipped", fg="yellow"))
                stats['skipped'] += 1
                continue

            existing = StoreItem.query.filter_by(code=code, is_deleted=False).first()

            if existing:
                if force or existing.version != data.get('version', '1.0'):
                    existing.name = data.get('name', existing.name)
                    existing.description = data.get('description')
                    existing.icon = data.get('icon')
                    existing.item_type = data.get('item_type', 'workflow_bundle')
                    existing.category = data.get('category')
                    existing.version = data.get('version', '1.0')
                    existing.payload = data.get('payload')
                    existing.source = data.get('source', 'official')
                    existing.scope = data.get('scope', 'tenant')
                    click.echo(f"  {code}: updated -> v{existing.version}")
                    stats['updated'] += 1
                else:
                    click.echo(f"  {code}: v{existing.version} unchanged, skipped")
                    stats['skipped'] += 1
            else:
                item = StoreItem(
                    code=code,
                    name=data.get('name', code),
                    description=data.get('description'),
                    icon=data.get('icon'),
                    item_type=data.get('item_type', 'workflow_bundle'),
                    category=data.get('category'),
                    version=data.get('version', '1.0'),
                    payload=data.get('payload'),
                    source=data.get('source', 'official'),
                    scope=data.get('scope', 'tenant'),
                )
                db.session.add(item)
                click.echo(f"  {code}: created v{item.version}")
                stats['created'] += 1

        except json.JSONDecodeError as e:
            click.echo(click.style(f"  {f.name}: invalid JSON - {e}", fg="red"))
            stats['skipped'] += 1
        except Exception as e:
            click.echo(click.style(f"  {f.name}: error - {e}", fg="red"))
            stats['skipped'] += 1

    db.session.commit()
    click.echo(f"\nDone: {stats['created']} created, {stats['updated']} updated, {stats['skipped']} skipped")
