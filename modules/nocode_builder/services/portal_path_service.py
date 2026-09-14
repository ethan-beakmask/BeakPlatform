"""
NoCode Builder - Portal Path Service
公開子系統路徑管理

管理 PUBLIC_PORTAL_PATHS lookup 表:
  - 建立子系統時自動產生不可猜測的路徑 ID
  - 上線/下線切換路徑狀態
  - 刪除子系統時移除路徑記錄
  - 透過 path_id 查詢對應子系統

Lookup 欄位對應:
  category_code = 'PUBLIC_PORTAL_PATHS'
  code          = 8 字元隨機路徑 ID (secrets.token_urlsafe)
  label         = 子系統顯示名稱
  value_str     = sub_system_secure_code
  is_active     = 路徑是否啟用
  org_secure_code = NULL (系統級)
"""
import logging
import secrets
from typing import Optional, Dict, Any

from app import db
from app.models.lookup_item import LookupItem

logger = logging.getLogger(__name__)

CATEGORY_CODE = 'PUBLIC_PORTAL_PATHS'

# 重試次數上限 (防 code 碰撞)
_MAX_RETRIES = 10


def _generate_path_id() -> str:
    """產生 8 字元 URL-safe 隨機路徑 ID"""
    return secrets.token_urlsafe(6)  # 6 bytes → 8 chars base64


def create_portal_path(
    sub_system_sc: str,
    display_name: str,
) -> Optional[LookupItem]:
    """
    為子系統建立公開路徑記錄

    Args:
        sub_system_sc: 子系統 secure_code
        display_name: 子系統顯示名稱

    Returns:
        建立的 LookupItem，失敗回 None
    """
    # 冪等: 已有記錄就回傳
    existing = LookupItem.query.filter_by(
        category_code=CATEGORY_CODE,
        value_str=sub_system_sc,
        is_active=True,
    ).first()
    if existing:
        logger.info(
            'Portal path already exists: path_id=%s, sub_system=%s',
            existing.code, sub_system_sc,
        )
        return existing

    # 產生不重複的 path_id
    for _ in range(_MAX_RETRIES):
        path_id = _generate_path_id()
        conflict = LookupItem.query.filter_by(
            category_code=CATEGORY_CODE,
            code=path_id,
        ).first()
        if not conflict:
            break
    else:
        logger.error('Failed to generate unique path_id after %d retries', _MAX_RETRIES)
        return None

    item = LookupItem(
        org_secure_code=None,
        category_code=CATEGORY_CODE,
        code=path_id,
        label=display_name,
        value_str=sub_system_sc,
        is_active=False,  # 建立時預設不啟用，publish 時才啟用
        sort_order=0,
    )
    db.session.add(item)
    db.session.flush()

    logger.info(
        'Portal path created: path_id=%s, sub_system=%s',
        path_id, sub_system_sc,
    )
    return item


def get_by_path_id(path_id: str) -> Optional[LookupItem]:
    """
    透過 path_id 查詢路徑記錄

    Args:
        path_id: 8 字元路徑 ID

    Returns:
        LookupItem 或 None
    """
    return LookupItem.query.filter_by(
        category_code=CATEGORY_CODE,
        code=path_id,
    ).first()


def get_by_sub_system(sub_system_sc: str) -> Optional[LookupItem]:
    """
    透過子系統 secure_code 查詢路徑記錄

    Args:
        sub_system_sc: 子系統 secure_code

    Returns:
        LookupItem 或 None
    """
    return LookupItem.query.filter_by(
        category_code=CATEGORY_CODE,
        value_str=sub_system_sc,
    ).first()


def set_active(sub_system_sc: str, active: bool) -> bool:
    """
    切換路徑啟用狀態 (publish/unpublish 連動)

    Args:
        sub_system_sc: 子系統 secure_code
        active: True=啟用, False=停用

    Returns:
        是否成功
    """
    item = get_by_sub_system(sub_system_sc)
    if not item:
        logger.warning(
            'Portal path not found for sub_system=%s, skip set_active',
            sub_system_sc,
        )
        return False

    item.is_active = active
    logger.info(
        'Portal path %s: path_id=%s, sub_system=%s',
        'activated' if active else 'deactivated',
        item.code, sub_system_sc,
    )
    return True


def delete_portal_path(sub_system_sc: str) -> bool:
    """
    刪除子系統的路徑記錄

    Args:
        sub_system_sc: 子系統 secure_code

    Returns:
        是否成功刪除
    """
    item = get_by_sub_system(sub_system_sc)
    if not item:
        return False

    path_id = item.code
    db.session.delete(item)
    logger.info(
        'Portal path deleted: path_id=%s, sub_system=%s',
        path_id, sub_system_sc,
    )
    return True


def update_label(sub_system_sc: str, new_label: str) -> bool:
    """
    更新路徑顯示名稱 (子系統改名連動)

    Args:
        sub_system_sc: 子系統 secure_code
        new_label: 新的顯示名稱

    Returns:
        是否成功
    """
    item = get_by_sub_system(sub_system_sc)
    if not item:
        return False

    item.label = new_label
    return True
