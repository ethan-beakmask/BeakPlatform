"""
BeakPlatform - Lookup Service
通用選項清單服務

提供 lookup_categories 和 lookup_items 的 CRUD 操作。
記憶體快取：首次查詢時載入，寫入操作自動 invalidate。
"""
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any

from sqlalchemy import text

from .. import db
from ..models.lookup_category import LookupCategory
from ..models.lookup_item import LookupItem
from ..utils.security import generate_secure_code

logger = logging.getLogger(__name__)


class LookupService:
    """通用選項清單服務 -- 靜態方法風格"""

    # 記憶體快取: key = (category_code, org_secure_code)
    _cache: Dict[tuple, List[dict]] = {}

    @classmethod
    def _invalidate_cache(cls, category_code: str, org_secure_code: Optional[str] = None):
        """清除指定 category 的快取"""
        keys_to_remove = [
            k for k in cls._cache
            if k[0] == category_code
        ]
        for k in keys_to_remove:
            del cls._cache[k]

    # ----------------------------------------------------------------
    # Category 操作
    # ----------------------------------------------------------------

    @classmethod
    def get_category(cls, code: str, org_secure_code: Optional[str] = None) -> Optional[LookupCategory]:
        """取得單一類別"""
        query = LookupCategory.query.filter_by(
            code=code,
            is_deleted=False
        )
        if org_secure_code:
            query = query.filter_by(org_secure_code=org_secure_code)
        else:
            query = query.filter(LookupCategory.org_secure_code.is_(None))
        return query.first()

    @classmethod
    def get_categories(cls, org_secure_code: Optional[str] = None) -> List[LookupCategory]:
        """
        列出所有可見類別。
        系統級 (org=NULL) 一定回傳；若提供 org，也回傳該企業的。
        """
        query = LookupCategory.query.filter_by(is_deleted=False)
        if org_secure_code:
            query = query.filter(
                db.or_(
                    LookupCategory.org_secure_code.is_(None),
                    LookupCategory.org_secure_code == org_secure_code
                )
            )
        else:
            query = query.filter(LookupCategory.org_secure_code.is_(None))
        return query.order_by(LookupCategory.code).all()

    @classmethod
    def create_category(
        cls,
        code: str,
        name: str,
        org_secure_code: Optional[str] = None,
        description: Optional[str] = None,
        is_system: bool = False,
        is_hierarchical: bool = False,
        name_i18n: Optional[dict] = None,
    ) -> LookupCategory:
        """建立類別"""
        category = LookupCategory(
            secure_code=generate_secure_code(),
            org_secure_code=org_secure_code,
            code=code,
            name=name,
            name_i18n=name_i18n or {},
            description=description,
            is_system=is_system,
            is_hierarchical=is_hierarchical,
        )
        db.session.add(category)
        db.session.flush()
        return category

    @classmethod
    def get_category_by_secure_code(cls, secure_code: str) -> Optional[LookupCategory]:
        """用 secure_code 取得單一類別"""
        return LookupCategory.query.filter_by(
            secure_code=secure_code,
            is_deleted=False
        ).first()

    @classmethod
    def update_category(cls, secure_code: str, **kwargs) -> Optional[LookupCategory]:
        """更新類別"""
        category = cls.get_category_by_secure_code(secure_code)
        if not category:
            return None
        if category.is_system:
            raise ValueError('系統級類別不可修改')

        allowed_fields = ('name', 'name_i18n', 'description', 'is_hierarchical')
        for field in allowed_fields:
            if field in kwargs:
                setattr(category, field, kwargs[field])

        category.updated_at = datetime.utcnow()
        db.session.flush()
        return category

    @classmethod
    def delete_category(cls, secure_code: str) -> bool:
        """軟刪除類別 + 連帶軟刪除所有子 items"""
        category = cls.get_category_by_secure_code(secure_code)
        if not category:
            return False
        if category.is_system:
            raise ValueError('系統級類別不可刪除')

        now = datetime.utcnow()
        category.is_deleted = True
        category.deleted_at = now

        # 連帶軟刪除所有 items
        items = LookupItem.query.filter_by(
            category_code=category.code,
            org_secure_code=category.org_secure_code,
            is_deleted=False
        ).all()
        for item in items:
            item.is_deleted = True
            item.deleted_at = now

        db.session.flush()
        cls._invalidate_cache(category.code, category.org_secure_code)
        return True

    # ----------------------------------------------------------------
    # Item 操作
    # ----------------------------------------------------------------

    @classmethod
    def get_items(
        cls,
        category_code: str,
        org_secure_code: Optional[str] = None
    ) -> List[dict]:
        """
        讀取選項 (系統級 + 企業級合併)。
        結果帶快取。
        """
        cache_key = (category_code, org_secure_code)
        if cache_key in cls._cache:
            return cls._cache[cache_key]

        query = LookupItem.query.filter_by(
            category_code=category_code,
            is_deleted=False,
            is_active=True,
        )
        if org_secure_code:
            query = query.filter(
                db.or_(
                    LookupItem.org_secure_code.is_(None),
                    LookupItem.org_secure_code == org_secure_code
                )
            )
        else:
            query = query.filter(LookupItem.org_secure_code.is_(None))

        items = query.order_by(LookupItem.sort_order, LookupItem.code).all()
        result = [item.to_dict() for item in items]
        cls._cache[cache_key] = result
        return result

    @classmethod
    def create_item(
        cls,
        category_code: str,
        code: str,
        label: str,
        org_secure_code: Optional[str] = None,
        label_i18n: Optional[dict] = None,
        value: Optional[Any] = None,
        parent_code: Optional[str] = None,
        sort_order: int = 0,
    ) -> LookupItem:
        """建立選項"""
        item = LookupItem(
            secure_code=generate_secure_code(),
            org_secure_code=org_secure_code,
            category_code=category_code,
            code=code,
            label=label,
            label_i18n=label_i18n or {},
            value=value,
            parent_code=parent_code,
            sort_order=sort_order,
        )
        db.session.add(item)
        db.session.flush()
        cls._invalidate_cache(category_code, org_secure_code)
        return item

    @classmethod
    def update_item(cls, secure_code: str, **kwargs) -> Optional[LookupItem]:
        """更新選項"""
        item = LookupItem.query.filter_by(
            secure_code=secure_code,
            is_deleted=False
        ).first()
        if not item:
            return None

        allowed_fields = ('label', 'label_i18n', 'value', 'parent_code',
                          'sort_order', 'is_active')
        for field in allowed_fields:
            if field in kwargs:
                setattr(item, field, kwargs[field])

        item.updated_at = datetime.utcnow()
        db.session.flush()
        cls._invalidate_cache(item.category_code, item.org_secure_code)
        return item

    @classmethod
    def delete_item(cls, secure_code: str) -> bool:
        """軟刪除選項"""
        item = LookupItem.query.filter_by(
            secure_code=secure_code,
            is_deleted=False
        ).first()
        if not item:
            return False

        item.is_deleted = True
        item.deleted_at = datetime.utcnow()
        db.session.flush()
        cls._invalidate_cache(item.category_code, item.org_secure_code)
        return True

    # ----------------------------------------------------------------
    # 合併查詢 (系統級 + 企業級)
    # ----------------------------------------------------------------

    @classmethod
    def get_categories_merged(cls, org_secure_code: Optional[str] = None) -> List[dict]:
        """
        企業可見類別: 僅回傳企業級 (org DB)。
        系統級 (is_system=True) 為平台內部使用，不暴露給企業用戶。
        """
        result = []

        # 企業級
        if org_secure_code:
            try:
                from .lookup_org_service import LookupOrgService
                org_cats = LookupOrgService.get_categories(org_secure_code)
                result.extend(org_cats)
            except Exception as e:
                logger.warning(f'[Lookup] 讀取企業類別失敗: {e}')

        # 按 code 排序
        result.sort(key=lambda c: c.get('code', ''))
        return result

    @classmethod
    def get_items_merged(
        cls,
        category_code: str,
        org_secure_code: Optional[str] = None
    ) -> List[dict]:
        """
        企業可見 items (帶快取)。
        只回傳企業 DB 中的 items，系統級 items 不暴露。
        """
        cache_key = (category_code, org_secure_code)
        if cache_key in cls._cache:
            return cls._cache[cache_key]

        result = []

        # 企業級
        if org_secure_code:
            try:
                from .lookup_org_service import LookupOrgService
                org_items = LookupOrgService.get_items(org_secure_code, category_code)
                result.extend(org_items)
            except Exception as e:
                logger.warning(f'[Lookup] 讀取企業 items 失敗: {e}')

        # 按 (sort_order, code) 排序
        result.sort(key=lambda i: (i.get('sort_order', 0), i.get('code', '')))
        cls._cache[cache_key] = result
        return result

    @classmethod
    def get_all_items_merged(
        cls,
        category_code: str,
        org_secure_code: Optional[str] = None
    ) -> List[dict]:
        """
        管理用: 企業 items 含 inactive (不走快取)。
        """
        result = []

        # 企業級
        if org_secure_code:
            try:
                from .lookup_org_service import LookupOrgService
                org_items = LookupOrgService.get_all_items(org_secure_code, category_code)
                result.extend(org_items)
            except Exception as e:
                logger.warning(f'[Lookup] 讀取企業 items 失敗: {e}')

        result.sort(key=lambda i: (i.get('sort_order', 0), i.get('code', '')))
        return result

    @classmethod
    def resolve_item_location(cls, secure_code: str, org_secure_code: Optional[str] = None) -> str:
        """
        判斷 item 在 'system' 還是 'org'。
        先查主庫，找到即為系統級；否則查 org DB。

        Returns:
            'system' | 'org' | None
        """
        sys_item = LookupItem.query.filter_by(
            secure_code=secure_code,
            is_deleted=False
        ).first()
        if sys_item:
            return 'system'

        if org_secure_code:
            try:
                from .lookup_org_service import LookupOrgService
                org_item = LookupOrgService.get_item_by_secure_code(org_secure_code, secure_code)
                if org_item:
                    return 'org'
            except Exception:
                pass

        return None

    @classmethod
    def resolve_category_location(cls, secure_code: str, org_secure_code: Optional[str] = None) -> str:
        """
        判斷 category 在 'system' 還是 'org'。

        Returns:
            'system' | 'org' | None
        """
        sys_cat = LookupCategory.query.filter_by(
            secure_code=secure_code,
            is_deleted=False
        ).first()
        if sys_cat:
            return 'system'

        if org_secure_code:
            try:
                from .lookup_org_service import LookupOrgService
                org_cat = LookupOrgService.get_category_by_secure_code(org_secure_code, secure_code)
                if org_cat:
                    return 'org'
            except Exception:
                pass

        return None

    # ----------------------------------------------------------------
    # 模組同步
    # ----------------------------------------------------------------

    @classmethod
    def sync_installed_modules(cls, loaded_modules) -> dict:
        """
        同步已安裝模組到 INSTALLED_MODULES category。

        Args:
            loaded_modules: ModuleInfo 列表 (來自 module_loader.get_loaded_modules())

        Returns:
            {'created': N, 'updated': N, 'deactivated': N}
        """
        CATEGORY_CODE = 'INSTALLED_MODULES'
        stats = {'created': 0, 'updated': 0, 'deactivated': 0}

        # 設定 RLS context: 系統級操作需要 is_system_admin
        db.session.execute(text("SET LOCAL app.is_system_admin = 'true'"))

        # 確保 category 存在
        category = cls.get_category(CATEGORY_CODE)
        if not category:
            cls.create_category(
                code=CATEGORY_CODE,
                name='已安裝模組',
                name_i18n={'en': 'Installed Modules'},
                description='平台已安裝的模組清單 (系統自動維護)',
                is_system=True,
            )
            logger.info(f"Created lookup category: {CATEGORY_CODE}")

        # 取得現有 items
        existing_items = LookupItem.query.filter_by(
            category_code=CATEGORY_CODE,
            org_secure_code=None,
            is_deleted=False,
        ).all()
        existing_map = {item.code: item for item in existing_items}

        # 同步每個模組
        active_codes = set()
        for idx, module in enumerate(loaded_modules):
            mod_code = module.name
            active_codes.add(mod_code)

            mod_value = {
                'version': module.version,
                'description': module.description,
                'enabled': True,
            }

            if mod_code in existing_map:
                item = existing_map[mod_code]
                item.label = module.display_name
                item.value = mod_value
                item.sort_order = idx
                item.is_active = True
                item.updated_at = datetime.utcnow()
                stats['updated'] += 1
            else:
                cls.create_item(
                    category_code=CATEGORY_CODE,
                    code=mod_code,
                    label=module.display_name,
                    label_i18n={'en': module.name},
                    value=mod_value,
                    sort_order=idx,
                )
                stats['created'] += 1

        # 不在 loaded_modules 中的舊項目 -> 軟刪除
        # 但跳過手動新增的項目 (value.manual=True)
        for code, item in existing_map.items():
            if code not in active_codes:
                is_manual = isinstance(item.value, dict) and item.value.get('manual')
                if is_manual:
                    continue
                item.is_deleted = True
                item.deleted_at = datetime.utcnow()
                stats['deactivated'] += 1

        db.session.commit()
        cls._invalidate_cache(CATEGORY_CODE)

        logger.info(
            f"Installed modules sync: "
            f"{stats['created']} created, "
            f"{stats['updated']} updated, "
            f"{stats['deactivated']} deactivated"
        )
        return stats
