"""系統權限與 ABAC 條件出廠預設值 seeding。"""
import json
import logging

from app import db
from app.models.permission import Permission, DEFAULT_PERMISSIONS
from app.models.permission_condition import PermissionCondition, DEFAULT_CONDITIONS

logger = logging.getLogger(__name__)


def seed_system_permissions(force=False) -> dict:
    """初始化系統預設權限。"""
    result = {
        'permissions_created': 0,
        'permissions_total': len(DEFAULT_PERMISSIONS),
        'conditions_created': 0,
        'conditions_total': len(DEFAULT_CONDITIONS),
    }

    existing_perm_count = Permission.query.filter_by(
        is_system_permission=True, is_deleted=False
    ).count()

    if existing_perm_count > 0 and not force:
        logger.info("已存在 %s 個系統權限，跳過", existing_perm_count)
    else:
        if force:
            logger.info("清除現有 %s 個系統權限...", existing_perm_count)
            Permission.query.filter_by(is_system_permission=True).delete(
                synchronize_session=False
            )
            db.session.commit()

        created = 0
        for perm_data in DEFAULT_PERMISSIONS:
            code = Permission.generate_code(
                perm_data['resource_type'],
                perm_data['action']
            )

            if Permission.query.filter_by(code=code).first():
                continue

            perm = Permission(
                resource_type=perm_data['resource_type'],
                action=perm_data['action'],
                code=code,
                name=perm_data['name'],
                description=perm_data.get('description'),
                permission_level=perm_data['level'],
                is_system_permission=True,
                is_active=True
            )
            db.session.add(perm)
            created += 1

        db.session.commit()
        result['permissions_created'] = created
        logger.info(
            "建立 %s 個系統權限 (共 %s 個定義)",
            created, len(DEFAULT_PERMISSIONS),
        )

    existing_cond_count = PermissionCondition.query.filter_by(
        is_system_condition=True, is_deleted=False
    ).count()

    if existing_cond_count > 0 and not force:
        logger.info("已存在 %s 個 ABAC 條件，跳過", existing_cond_count)
    else:
        if force:
            PermissionCondition.query.filter_by(
                is_system_condition=True
            ).delete(synchronize_session=False)
            db.session.commit()

        created = 0
        for cond_data in DEFAULT_CONDITIONS:
            code = cond_data['code']

            if PermissionCondition.query.filter_by(code=code).first():
                continue

            cond = PermissionCondition(
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
                is_active=True
            )
            db.session.add(cond)
            created += 1

        db.session.commit()
        result['conditions_created'] = created
        logger.info(
            "建立 %s 個 ABAC 條件 (共 %s 個定義)",
            created, len(DEFAULT_CONDITIONS),
        )

    return result
