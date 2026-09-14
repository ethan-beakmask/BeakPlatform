"""系統權限與 ABAC 條件出廠預設值 seeding。

`seed_system_permissions()` 是 fresh 與 update 兩條 bootstrap 路徑共用的入口，
**一律逐 code 補缺**：DEFAULT_PERMISSIONS / DEFAULT_CONDITIONS 中 code 不存在的才建立，
已存在的一律不動（不改名、不改層級、不復活軟刪除）。所以新增出廠定義之後，
既有環境跑 `scripts/bootstrap_db.py --update` 就會補齊。

2026-09-04（PF-241）之前 force=False 是「DB 已有任何系統權限就整批跳過」，
後來加進出廠定義的資源型 CRUD 碼在既有環境永遠補不進去，而 CLAUDE.md 卻一直寫著
「逐 code 補缺」。fresh install 因此缺 17 種 ResourceGateway 資源型碼、
對應管理 API 對每一種身分都 403。
"""
import json
import logging

from app import db
from app.models.permission import Permission, DEFAULT_PERMISSIONS
from app.models.permission_condition import PermissionCondition, DEFAULT_CONDITIONS

logger = logging.getLogger(__name__)


def _existing_codes(column) -> set:
    # 含軟刪除的記錄：code 有 unique 約束，軟刪除的一樣會撞
    return {code for (code,) in db.session.query(column).all()}


def _seed_permissions(force: bool) -> int:
    if force:
        deleted = Permission.query.filter_by(is_system_permission=True).delete(
            synchronize_session=False
        )
        db.session.commit()
        logger.info("force：清除 %s 個系統權限後重建", deleted)

    existing = _existing_codes(Permission.code)
    created = 0
    for perm_data in DEFAULT_PERMISSIONS:
        code = Permission.generate_code(
            perm_data['resource_type'],
            perm_data['action']
        )
        if code in existing:
            continue
        db.session.add(Permission(
            resource_type=perm_data['resource_type'],
            action=perm_data['action'],
            code=code,
            name=perm_data['name'],
            description=perm_data.get('description'),
            permission_level=perm_data['level'],
            is_system_permission=True,
            is_active=True,
        ))
        existing.add(code)
        created += 1

    db.session.commit()
    logger.info(
        "系統權限：新建 %s 個，出廠定義共 %s 個",
        created, len(DEFAULT_PERMISSIONS),
    )
    return created


def _seed_conditions(force: bool) -> int:
    if force:
        deleted = PermissionCondition.query.filter_by(
            is_system_condition=True
        ).delete(synchronize_session=False)
        db.session.commit()
        logger.info("force：清除 %s 個 ABAC 條件後重建", deleted)

    existing = _existing_codes(PermissionCondition.code)
    created = 0
    for cond_data in DEFAULT_CONDITIONS:
        code = cond_data['code']
        if code in existing:
            continue
        db.session.add(PermissionCondition(
            code=code,
            name=cond_data['name'],
            description=cond_data.get('description'),
            condition_type=cond_data['condition_type'],
            expression=json.dumps(
                cond_data['expression'], ensure_ascii=False
            ) if cond_data.get('expression') else None,
            requires_param=cond_data.get('requires_param', False),
            param_description=cond_data.get('param_description'),
            is_system_condition=True,
            is_active=True,
        ))
        existing.add(code)
        created += 1

    db.session.commit()
    logger.info(
        "ABAC 條件：新建 %s 個，出廠定義共 %s 個",
        created, len(DEFAULT_CONDITIONS),
    )
    return created


def seed_system_permissions(force=False) -> dict:
    """初始化系統預設權限與 ABAC 條件（逐 code 補缺，冪等）。

    force=True 會先刪除所有 is_system_permission / is_system_condition 的記錄再重建；
    只在 fresh install 或維運入口 `scripts/init_permissions.py --force` 使用。
    """
    return {
        'permissions_created': _seed_permissions(force),
        'permissions_total': len(DEFAULT_PERMISSIONS),
        'conditions_created': _seed_conditions(force),
        'conditions_total': len(DEFAULT_CONDITIONS),
    }
