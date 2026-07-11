"""
選單出廠預設值 Mixin - 負責出廠預設值的儲存、載入、重置與匯出

方法：
- _build_defaults_map: 建構預設值 map
- reset_menu_positions: 重置位置
- reset_menu_factory: 完整出廠重置
- _reset_role_requirements_from_db: 從 DB 重設角色需求
- seed_org_role_requirements: 為單一企業建立角色需求
- seed_all_orgs_role_requirements: 為所有企業建立角色需求
- save_menu_factory_defaults: 儲存當前為出廠預設值
- _load_defaults_from_db: 從 DB 載入預設值
- export_factory_sql: 匯出安裝用 SQL
"""
import json
import logging
import os
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

from ..models.menu_item import MenuItem
from ..models.menu_permission import MenuPermission
from ..models.menu_default import MenuDefault
from ..constants import SYSTEM_ORG_CODE
from .. import db

logger = logging.getLogger(__name__)


class MenuFactoryMixin:
    """選單出廠預設值管理"""

    @classmethod
    def _build_defaults_map(cls) -> Dict[str, Dict[str, Any]]:
        """
        建構完整的選單預設值 map（平台 + 模組）

        Returns:
            {code: {display_order, parent_code, depth, title, ...}, ...}
        """
        from ..defaults.menu_defaults import build_defaults_map
        from ..module_loader import module_loader
        return build_defaults_map(module_loader)

    @classmethod
    def reset_menu_positions(cls) -> Dict[str, int]:
        """
        重置選單項目位置（只還原 display_order / parent / depth）

        不影響權限、標題、icon 等其他設定。
        用戶自建選單（is_user_created=True）保持原位。

        Returns:
            {'updated': n, 'skipped': n}
        """
        defaults = cls._build_defaults_map()

        items = MenuItem.query.filter_by(is_deleted=False).all()
        code_to_item = {item.code: item for item in items}

        updated = 0
        skipped = 0

        for code, default in defaults.items():
            item = code_to_item.get(code)
            if not item:
                skipped += 1
                continue

            # 用戶自建選單保持原位（即使 code 與內建 defaults 重疊）
            if item.is_user_created:
                skipped += 1
                continue

            # 解析 parent_secure_code
            parent_code = default.get('parent_code')
            if parent_code:
                parent_item = code_to_item.get(parent_code)
                parent_sc = parent_item.secure_code if parent_item else None
            else:
                parent_sc = None

            changed = False

            if item.display_order != default['display_order']:
                item.display_order = default['display_order']
                changed = True

            if item.parent_secure_code != parent_sc:
                item.parent_secure_code = parent_sc
                changed = True

            new_depth = default.get('depth', 0)
            if item.depth != new_depth:
                item.depth = new_depth
                changed = True

            if changed:
                updated += 1

        db.session.commit()
        logger.info(f"Menu positions reset: {updated} updated, {skipped} skipped")
        return {'updated': updated, 'skipped': skipped}

    @classmethod
    def reset_menu_factory(cls) -> Dict[str, int]:
        """
        重置選單所有設定成出廠值（完全覆蓋回預設值）

        資料來源優先順序：
        1. menu_defaults 表（系統管理員儲存的快照）
        2. menu_defaults.py（程式碼內建，fallback）

        覆蓋範圍：位置、標題、icon、link_type、link_target、
        is_expanded、is_active、is_shared、required_permission、
        MenuPermission（鑰匙 1）、MenuRoleRequirement（鑰匙 2）。
        用戶自建選單（is_user_created=True）不受影響。

        Returns:
            {'updated': n, 'skipped': n, 'permissions_reset': n,
             'role_requirements_reset': n, 'source': str}
        """
        # 優先從 DB 讀取
        defaults = cls._load_defaults_from_db()
        source = 'database'
        if defaults is None:
            defaults = cls._build_defaults_map()
            source = 'builtin'

        items = MenuItem.query.filter_by(is_deleted=False).all()
        code_to_item = {item.code: item for item in items}

        updated = 0
        skipped = 0
        permissions_reset = 0

        for code, default in defaults.items():
            item = code_to_item.get(code)
            if not item:
                skipped += 1
                continue

            # 用戶自建選單不受出廠重置影響（builtin fallback 也要守住）
            if item.is_user_created:
                skipped += 1
                continue

            # 解析 parent_secure_code
            parent_code = default.get('parent_code')
            if parent_code:
                parent_item = code_to_item.get(parent_code)
                parent_sc = parent_item.secure_code if parent_item else None
            else:
                parent_sc = None

            # 位置欄位
            item.display_order = default['display_order']
            item.parent_secure_code = parent_sc
            item.depth = default.get('depth', 0)

            # 內容欄位
            item.title = default['title']
            item.icon = default.get('icon')
            item.link_type = default['link_type']
            item.link_target = default.get('link_target')
            item.is_expanded = default.get('is_expanded', False)
            item.is_active = True
            item.is_shared = default.get('is_shared', False)
            item.required_permission = default.get('required_permission')

            # 權限重置（MenuPermission，鑰匙 1）
            user_types = default.get('user_types', [])
            if user_types:
                cls.set_menu_permissions(item.secure_code, user_types)
                permissions_reset += 1

            updated += 1

        # 角色需求重置（MenuRoleRequirement，鑰匙 2）
        if source == 'database':
            # 從 DB 快照讀角色需求，全量重設
            role_req_count = cls._reset_role_requirements_from_db(
                defaults, code_to_item
            )
        else:
            role_req_count = cls.seed_all_orgs_role_requirements(code_to_item)

        db.session.commit()
        logger.info(
            f"Menu factory reset ({source}): {updated} updated, "
            f"{skipped} skipped, {permissions_reset} permissions reset, "
            f"{role_req_count} role requirements reset"
        )
        return {
            'updated': updated,
            'skipped': skipped,
            'permissions_reset': permissions_reset,
            'role_requirements_reset': role_req_count,
            'source': source,
        }

    @classmethod
    def _reset_role_requirements_from_db(
        cls,
        defaults: Dict[str, Dict[str, Any]],
        code_to_item: Dict[str, MenuItem],
    ) -> int:
        """
        從 menu_defaults 表的 role_codes 重設所有企業的角色需求

        對每個企業，用 role code 找到該企業的 role secure_code，
        全量替換 MenuRoleRequirement。

        Args:
            defaults: menu_defaults 表的快照 dict
            code_to_item: 選單 code -> MenuItem 映射

        Returns:
            重設的 MRR 記錄總數
        """
        from ..models.menu_role_requirement import MenuRoleRequirement
        from ..models.organization import Organization
        from ..models.role import Role
        from sqlalchemy import text

        db.session.execute(text("SET LOCAL app.is_system_admin = 'true'"))

        orgs = Organization.query.filter(
            Organization.is_deleted == False,
        ).all()

        total = 0
        for org in orgs:
            # 該企業的 role code -> secure_code
            org_roles = Role.query.filter(
                Role.org_secure_code == org.secure_code,
                Role.is_deleted == False,
            ).all()
            role_code_to_sc = {r.code: r.secure_code for r in org_roles}

            if not role_code_to_sc:
                continue

            # 刪除該企業現有的 MRR（hard delete，因為 unique constraint
            # 不含 is_deleted，soft delete 會導致重複插入失敗）
            MenuRoleRequirement.query.filter(
                MenuRoleRequirement.org_secure_code == org.secure_code,
            ).delete(synchronize_session=False)
            db.session.flush()

            # 重新建立
            for menu_code, default in defaults.items():
                role_codes = default.get('role_codes', [])
                if not role_codes:
                    continue

                item = code_to_item.get(menu_code)
                if not item:
                    continue

                for role_code in role_codes:
                    role_sc = role_code_to_sc.get(role_code)
                    if not role_sc:
                        continue

                    req = MenuRoleRequirement(
                        menu_secure_code=item.secure_code,
                        role_secure_code=role_sc,
                        org_secure_code=org.secure_code,
                    )
                    db.session.add(req)
                    total += 1

        return total

    @classmethod
    def seed_org_role_requirements(
        cls,
        org_secure_code: str,
        code_to_item: Dict[str, MenuItem] = None,
    ) -> int:
        """
        為指定企業建立預設選單角色需求（雙鑰匙 Key2）

        根據 MENU_ROLE_DEFAULTS 定義，找到企業的對應角色（by role code），
        為每個選單建立 MenuRoleRequirement 記錄。已存在的記錄不會重複建立。

        Args:
            org_secure_code: 目標企業 secure_code
            code_to_item: 選單 code → MenuItem 映射（可選，避免重複查詢）

        Returns:
            新建的 MRR 記錄數
        """
        from ..defaults.menu_defaults import MENU_ROLE_DEFAULTS
        from ..models.menu_role_requirement import MenuRoleRequirement
        from ..models.role import Role
        from sqlalchemy import text

        # 繞過 RLS
        db.session.execute(text("SET LOCAL app.is_system_admin = 'true'"))

        # 取得選單 code → secure_code 映射
        if code_to_item is None:
            items = MenuItem.query.filter_by(is_deleted=False).all()
            code_to_item = {item.code: item for item in items}

        # 取得該企業的角色 code → secure_code 映射
        org_roles = Role.query.filter(
            Role.org_secure_code == org_secure_code,
            Role.is_deleted == False,
        ).all()
        role_code_to_sc = {r.code: r.secure_code for r in org_roles}

        if not role_code_to_sc:
            logger.warning(
                f"No roles found for org {org_secure_code}, "
                f"skipping MRR seed"
            )
            return 0

        # 取得該企業現有的 MRR（避免重複）
        existing_mrrs = MenuRoleRequirement.query.filter(
            MenuRoleRequirement.org_secure_code == org_secure_code,
            MenuRoleRequirement.is_deleted == False,
        ).all()
        existing_keys = {
            (m.menu_secure_code, m.role_secure_code)
            for m in existing_mrrs
        }

        count = 0
        for menu_code, role_codes in MENU_ROLE_DEFAULTS.items():
            item = code_to_item.get(menu_code)
            if not item:
                continue

            for role_code in role_codes:
                role_sc = role_code_to_sc.get(role_code)
                if not role_sc:
                    continue

                key = (item.secure_code, role_sc)
                if key in existing_keys:
                    continue

                req = MenuRoleRequirement(
                    menu_secure_code=item.secure_code,
                    role_secure_code=role_sc,
                    org_secure_code=org_secure_code,
                )
                db.session.add(req)
                existing_keys.add(key)
                count += 1

        if count:
            logger.info(
                f"Seeded {count} menu role requirements for org "
                f"{org_secure_code}"
            )

        return count

    @classmethod
    def seed_all_orgs_role_requirements(
        cls,
        code_to_item: Dict[str, MenuItem] = None,
    ) -> int:
        """
        為所有企業建立預設選單角色需求

        Args:
            code_to_item: 選單 code → MenuItem 映射（可選）

        Returns:
            總共新建的 MRR 記錄數
        """
        from ..models.organization import Organization
        from sqlalchemy import text

        db.session.execute(text("SET LOCAL app.is_system_admin = 'true'"))

        orgs = Organization.query.filter(
            Organization.is_deleted == False,
            Organization.secure_code != SYSTEM_ORG_CODE,
        ).all()

        if code_to_item is None:
            items = MenuItem.query.filter_by(is_deleted=False).all()
            code_to_item = {item.code: item for item in items}

        total = 0
        # 系統企業 (SYSTEM_ORG_CODE) 也要 seed
        total += cls.seed_org_role_requirements(
            SYSTEM_ORG_CODE, code_to_item
        )
        for org in orgs:
            total += cls.seed_org_role_requirements(
                org.secure_code, code_to_item
            )

        return total

    # ========================================
    # 選單出廠預設值管理 (DB-based)
    # ========================================

    @classmethod
    def save_menu_factory_defaults(
        cls, operator_username: str
    ) -> Dict[str, Any]:
        """
        設定目前組態成出廠值（系統管理員專用）

        快照 menu_items + menu_permissions + menu_role_requirements
        寫入 menu_defaults 表（全量替換）。

        Args:
            operator_username: 操作者帳號

        Returns:
            {'message': ..., 'count': n} or {'error': ...}
        """
        from ..models.menu_role_requirement import MenuRoleRequirement
        from ..models.role import Role
        from sqlalchemy import text

        try:
            db.session.execute(text("SET LOCAL app.is_system_admin = 'true'"))

            # 1. 快照 menu_items（排除已刪除、排除用戶自建）
            items = MenuItem.query.filter(
                MenuItem.is_deleted == False,
                MenuItem.is_user_created == False,
            ).all()

            if not items:
                return {'error': '沒有可儲存的預設選單項目'}

            code_to_item = {item.code: item for item in items}

            # parent 查找用：含 user-created 項目
            # （非 user-created 項目可能掛在 user-created 根項目下）
            all_items = MenuItem.query.filter(
                MenuItem.is_deleted == False,
            ).all()
            all_sc_to_code = {
                i.secure_code: i.code for i in all_items
            }

            # 2. 快照 menu_permissions (Key1)
            all_perms = MenuPermission.query.filter(
                MenuPermission.is_deleted == False,
            ).all()
            # {menu_secure_code: [user_type, ...]}
            perm_map = {}
            for p in all_perms:
                perm_map.setdefault(p.menu_secure_code, []).append(
                    p.user_type if isinstance(p.user_type, str)
                    else p.user_type.name if hasattr(p.user_type, 'name')
                    else str(p.user_type)
                )

            # 3. 快照 menu_role_requirements (Key2)
            #    以系統企業 (SYSTEM_ORG_CODE) 的設定為基準，用 role code 紀錄
            all_mrrs = MenuRoleRequirement.query.filter(
                MenuRoleRequirement.org_secure_code == SYSTEM_ORG_CODE,
                MenuRoleRequirement.is_deleted == False,
            ).all()

            # 需要反查 role code
            role_scs = {m.role_secure_code for m in all_mrrs}
            if role_scs:
                roles = Role.query.filter(
                    Role.secure_code.in_(role_scs),
                    Role.is_deleted == False,
                ).all()
                role_sc_to_code = {r.secure_code: r.code for r in roles}
            else:
                role_sc_to_code = {}

            # {menu_secure_code: [role_code, ...]}
            mrr_map = {}
            for m in all_mrrs:
                role_code = role_sc_to_code.get(m.role_secure_code)
                if role_code:
                    mrr_map.setdefault(m.menu_secure_code, []).append(
                        role_code
                    )

            # 4. 清空 menu_defaults 表，全量寫入
            MenuDefault.query.delete()

            now = datetime.utcnow()
            count = 0
            for item in items:
                user_types = sorted(perm_map.get(item.secure_code, []))
                role_codes = sorted(mrr_map.get(item.secure_code, []))

                # parent_code: 從 parent_secure_code 反查 parent.code
                # 在所有項目中查找（含 user-created），確保跨類型父子關係正確
                parent_code = all_sc_to_code.get(
                    item.parent_secure_code
                ) if item.parent_secure_code else None

                default_row = MenuDefault(
                    code=item.code,
                    title=item.title,
                    title_i18n=item.title_i18n or {},
                    icon=item.icon,
                    link_type=item.link_type,
                    link_target=item.link_target,
                    display_order=item.display_order,
                    depth=item.depth,
                    parent_code=parent_code,
                    is_expanded=item.is_expanded,
                    is_shared=item.is_shared,
                    required_permission=item.required_permission,
                    user_types=user_types,
                    role_codes=role_codes,
                    saved_by=operator_username,
                    saved_at=now,
                )
                db.session.add(default_row)
                count += 1

            db.session.commit()
            logger.info(
                f"Menu factory defaults saved: {count} items "
                f"by {operator_username}"
            )

            return {
                'message': '選單出廠預設值已儲存',
                'count': count,
            }

        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to save menu factory defaults: {e}")
            return {'error': f'儲存失敗: {str(e)}'}

    @classmethod
    def _load_defaults_from_db(cls) -> Optional[Dict[str, Dict[str, Any]]]:
        """
        從 menu_defaults 表載入預設值

        Returns:
            {code: {display_order, parent_code, depth, title, ...}, ...}
            若表為空回傳 None（觸發 fallback）
        """
        rows = MenuDefault.query.all()
        if not rows:
            return None

        defaults = {}
        for row in rows:
            defaults[row.code] = {
                'display_order': row.display_order,
                'parent_code': row.parent_code,
                'depth': row.depth,
                'title': row.title,
                'title_i18n': row.title_i18n or {},
                'icon': row.icon,
                'link_type': row.link_type,
                'link_target': row.link_target,
                'is_expanded': row.is_expanded,
                'is_shared': row.is_shared,
                'required_permission': row.required_permission,
                'user_types': row.user_types or [],
                'role_codes': row.role_codes or [],
            }
        return defaults

    @classmethod
    def export_factory_sql(cls) -> Dict[str, Any]:
        """
        從 menu_defaults 表匯出安裝用 SQL（原廠專用）

        生成冪等 SQL，只在 menu_defaults 表為空時才插入，
        upgrade 不覆蓋用戶已儲存的預設值。

        Returns:
            {'sql': str, 'count': int} or {'error': ...}
        """
        rows = MenuDefault.query.order_by(
            MenuDefault.depth, MenuDefault.display_order
        ).all()

        if not rows:
            return {'error': 'menu_defaults 表為空，請先儲存出廠預設值'}

        now_str = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
        lines = [
            '-- BeakPlatform Menu Factory Defaults (install-only)',
            f'-- Generated: {now_str}',
            '-- ',
            '-- 安全機制: 只在 menu_defaults 表為空時才插入',
            '-- (upgrade 不會覆蓋用戶已儲存的預設值)',
            '',
            '-- 條件: 僅當 menu_defaults 表為空時執行',
            'DO $$',
            'BEGIN',
            '    IF NOT EXISTS (SELECT 1 FROM menu_defaults LIMIT 1) THEN',
            '',
        ]

        for row in rows:
            title_i18n = json.dumps(row.title_i18n or {}, ensure_ascii=False)
            user_types = json.dumps(row.user_types or [], ensure_ascii=False)
            role_codes = json.dumps(row.role_codes or [], ensure_ascii=False)

            # 轉義單引號
            title_esc = (row.title or '').replace("'", "''")
            icon_val = f"'{row.icon}'" if row.icon else 'NULL'
            link_target_val = (
                f"'{(row.link_target or '').replace(chr(39), chr(39)*2)}'"
                if row.link_target else 'NULL'
            )
            parent_code_val = (
                f"'{row.parent_code}'" if row.parent_code else 'NULL'
            )
            req_perm_val = (
                f"'{row.required_permission}'"
                if row.required_permission else 'NULL'
            )

            sql = (
                f"        INSERT INTO menu_defaults "
                f"(code, title, title_i18n, icon, link_type, link_target, "
                f"display_order, depth, parent_code, is_expanded, is_shared, "
                f"required_permission, user_types, role_codes, "
                f"saved_by, saved_at) VALUES ("
                f"'{row.code}', '{title_esc}', "
                f"'{title_i18n}'::jsonb, {icon_val}, "
                f"'{row.link_type}', {link_target_val}, "
                f"{row.display_order}, {row.depth}, {parent_code_val}, "
                f"{'true' if row.is_expanded else 'false'}, "
                f"{'true' if row.is_shared else 'false'}, "
                f"{req_perm_val}, "
                f"'{user_types}'::jsonb, '{role_codes}'::jsonb, "
                f"'factory_install', NOW());"
            )
            lines.append(sql)

        lines.extend([
            '',
            '    END IF;',
            'END $$;',
        ])

        sql_content = '\n'.join(lines)

        # 寫入 scripts/migrations/
        project_root = os.path.abspath(
            os.path.join(os.path.dirname(__file__), '..', '..', '..')
        )
        sql_path = os.path.join(
            project_root, 'scripts', 'migrations',
            '058_seed_menu_defaults.sql'
        )
        os.makedirs(os.path.dirname(sql_path), exist_ok=True)
        with open(sql_path, 'w', encoding='utf-8') as f:
            f.write(sql_content)

        logger.info(
            f"Menu factory SQL exported: {len(rows)} items "
            f"→ 058_seed_menu_defaults.sql"
        )

        return {
            'message': '安裝用 SQL 已產出',
            'count': len(rows),
            'sql_file': '058_seed_menu_defaults.sql',
        }
