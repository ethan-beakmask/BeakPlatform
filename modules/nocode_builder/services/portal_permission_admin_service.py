"""PF-8 portal permission administration service."""
import re
from collections import defaultdict

from sqlalchemy import bindparam, text

from ..models.site_map_node import DcSiteMapNode
from .data_source_manager import DataSourceManager, ensure_portal_schema
from .portal_permission_templates import DEFAULT_ADMIN_ROLES, PERMISSION_TEMPLATES

PERMISSION_CODE_RE = re.compile(r'^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$')
ADMIN_CODE_RE = re.compile(r'^[A-Z][A-Z0-9_]{0,31}$')
RISK_LEVELS = {'low', 'normal', 'high', 'critical'}

# 權限碼仍被引用時的錯誤訊息前綴；API 層據此回 409（勿改字串，會影響狀態碼判斷）
PERMISSION_IN_USE_ERROR = '權限碼仍被引用'


def _valid_permission_code(code: str) -> bool:
    return bool(PERMISSION_CODE_RE.fullmatch((code or '').strip()))


def _valid_admin_code(code: str) -> bool:
    return bool(ADMIN_CODE_RE.fullmatch((code or '').strip()))


def _select_ids(sess, table_name, codes):
    stmt = text(f'SELECT id, code FROM {table_name} WHERE code IN :codes')
    stmt = stmt.bindparams(bindparam('codes', expanding=True))
    rows = sess.execute(stmt, {'codes': tuple(codes)}).mappings().all()
    return {row['code']: row['id'] for row in rows}


def _permission_ids(sess, codes) -> tuple[dict[str, int] | None, str]:
    if not isinstance(codes, list):
        return None, '權限碼清單格式不正確'
    normalized = []
    for code in codes:
        code = (code or '').strip() if isinstance(code, str) else ''
        if not _valid_permission_code(code):
            return None, '權限碼格式不正確'
        if code not in normalized:
            normalized.append(code)
    if not normalized:
        return {}, ''
    found = _select_ids(sess, 'portal_permissions', normalized)
    missing = [code for code in normalized if code not in found]
    if missing:
        return None, '權限碼不存在：' + ', '.join(missing)
    return found, ''


def _seed_default_admin_roles_in_session(sess):
    for idx, (code, name) in enumerate(DEFAULT_ADMIN_ROLES):
        sess.execute(
            text(
                'INSERT OR IGNORE INTO portal_admin_roles '
                '(code, name, description, is_system, enabled, display_order) '
                'VALUES (:code, :name, :description, 1, 1, :display_order)'
            ),
            {'code': code, 'name': name, 'description': '', 'display_order': idx * 10},
        )


def seed_default_admin_roles(sub_system_sc) -> None:
    ensure_portal_schema(sub_system_sc)
    with DataSourceManager().get_session(sub_system_sc, 'portal') as sess:
        _seed_default_admin_roles_in_session(sess)
        sess.commit()


def _append_map(sess, sql, key_field, value_field):
    grouped = defaultdict(list)
    for row in sess.execute(text(sql)).mappings().all():
        grouped[row[key_field]].append(row[value_field])
    return grouped


def get_permission_model(sub_system_sc) -> dict:
    ensure_portal_schema(sub_system_sc)
    with DataSourceManager().get_session(sub_system_sc, 'portal') as sess:
        if not (sess.execute(text('SELECT COUNT(*) FROM portal_admin_roles')).scalar() or 0):
            _seed_default_admin_roles_in_session(sess)
            sess.commit()
        permissions = sess.execute(text(
            'SELECT code, resource, action, description, risk_level, enabled '
            'FROM portal_permissions ORDER BY code ASC'
        )).mappings().all()
        roles = sess.execute(text(
            'SELECT code, name, description, display_order, enabled '
            'FROM portal_admin_roles ORDER BY display_order ASC, code ASC'
        )).mappings().all()
        levels = sess.execute(text(
            'SELECT code, name, rank, is_active '
            'FROM portal_levels ORDER BY rank ASC, display_order ASC, code ASC'
        )).mappings().all()
        users = sess.execute(text(
            'SELECT secure_code, username, display_name, level_code, group_code, is_active '
            'FROM portal_users ORDER BY username ASC'
        )).mappings().all()
        role_perms = _append_map(sess, (
            'SELECT r.code AS role_code, p.code AS permission_code '
            'FROM portal_role_permissions AS rp '
            'JOIN portal_admin_roles AS r ON r.id = rp.role_id '
            'JOIN portal_permissions AS p ON p.id = rp.permission_id '
            'ORDER BY p.code ASC'
        ), 'role_code', 'permission_code')
        level_perms = _append_map(sess, (
            'SELECT l.code AS level_code, p.code AS permission_code '
            'FROM portal_level_permissions AS lp '
            'JOIN portal_levels AS l ON l.id = lp.level_id '
            'JOIN portal_permissions AS p ON p.id = lp.permission_id '
            'ORDER BY p.code ASC'
        ), 'level_code', 'permission_code')
        user_roles = _append_map(sess, (
            'SELECT u.secure_code AS user_sc, r.code AS role_code '
            'FROM portal_user_roles AS ur '
            'JOIN portal_users AS u ON u.id = ur.user_id '
            'JOIN portal_admin_roles AS r ON r.id = ur.role_id '
            'ORDER BY r.code ASC'
        ), 'user_sc', 'role_code')
        user_overrides = defaultdict(list)
        for row in sess.execute(text(
            'SELECT u.secure_code AS user_sc, p.code, up.effect '
            'FROM portal_user_permissions AS up '
            'JOIN portal_users AS u ON u.id = up.user_id '
            'JOIN portal_permissions AS p ON p.id = up.permission_id '
            'ORDER BY p.code ASC'
        )).mappings().all():
            user_overrides[row['user_sc']].append({'code': row['code'], 'effect': row['effect']})
        return {
            'permissions': [dict(row) for row in permissions],
            'roles': [{**dict(row), 'permissions': role_perms[row['code']]} for row in roles],
            'levels': [{**dict(row), 'permissions': level_perms[row['code']]} for row in levels],
            'users': [
                {**dict(row), 'roles': user_roles[row['secure_code']],
                 'overrides': user_overrides[row['secure_code']]}
                for row in users
            ],
        }


def upsert_permission(sub_system_sc, code, description='', risk_level='normal') -> tuple[dict | None, str]:
    code = (code or '').strip()
    description = (description or '').strip()
    risk_level = (risk_level or '').strip()
    if not _valid_permission_code(code):
        return None, '權限碼格式不正確'
    if risk_level not in RISK_LEVELS:
        return None, '風險等級不正確'
    resource, action = code.split('.', 1)
    ensure_portal_schema(sub_system_sc)
    with DataSourceManager().get_session(sub_system_sc, 'portal') as sess:
        if sess.execute(text('SELECT 1 FROM portal_permissions WHERE code = :code'), {'code': code}).first():
            sess.execute(text(
                'UPDATE portal_permissions '
                'SET description = :description, risk_level = :risk_level, enabled = 1 '
                'WHERE code = :code'
            ), {'code': code, 'description': description, 'risk_level': risk_level})
        else:
            sess.execute(text(
                'INSERT INTO portal_permissions '
                '(code, resource, action, description, risk_level, enabled) '
                'VALUES (:code, :resource, :action, :description, :risk_level, 1)'
            ), {
                'code': code, 'resource': resource, 'action': action,
                'description': description, 'risk_level': risk_level,
            })
        row = sess.execute(text(
            'SELECT code, resource, action, description, risk_level, enabled '
            'FROM portal_permissions WHERE code = :code'
        ), {'code': code}).mappings().first()
        sess.commit()
        return dict(row), ''


def _site_map_references(sub_system_sc, code) -> bool:
    nodes = DcSiteMapNode.query.filter_by(
        sub_system_secure_code=sub_system_sc,
        is_deleted=False,
    ).all()
    for node in nodes:
        matrix = getattr(node, 'access_matrix', None)
        if not isinstance(matrix, dict):
            continue
        for rule in matrix.values():
            if isinstance(rule, dict) and code in (rule.get('required_permissions') or []):
                return True
    return False


def delete_permission(sub_system_sc, code) -> tuple[bool, str]:
    code = (code or '').strip()
    if not _valid_permission_code(code):
        return False, '權限碼格式不正確'
    ensure_portal_schema(sub_system_sc)
    with DataSourceManager().get_session(sub_system_sc, 'portal') as sess:
        permission_id = sess.execute(
            text('SELECT id FROM portal_permissions WHERE code = :code'),
            {'code': code},
        ).scalar()
        if not permission_id:
            return False, '權限碼不存在'
        refs = []
        for label, table_name in (
            ('階級', 'portal_level_permissions'),
            ('角色', 'portal_role_permissions'),
            ('使用者覆寫', 'portal_user_permissions'),
        ):
            count = sess.execute(
                text(f'SELECT COUNT(*) FROM {table_name} WHERE permission_id = :permission_id'),
                {'permission_id': permission_id},
            ).scalar() or 0
            if count:
                refs.append(label)
        if _site_map_references(sub_system_sc, code):
            refs.append('網站地圖 access_matrix')
        if refs:
            return False, PERMISSION_IN_USE_ERROR + '：' + '、'.join(refs)
        sess.execute(
            text('DELETE FROM portal_permissions WHERE id = :permission_id'),
            {'permission_id': permission_id},
        )
        sess.commit()
        return True, ''


def upsert_admin_role(sub_system_sc, code, name, description='', display_order=0) -> tuple[dict | None, str]:
    code = (code or '').strip()
    name = (name or '').strip()
    description = (description or '').strip()
    if not _valid_admin_code(code):
        return None, '角色代碼格式不正確'
    if not name:
        return None, '請輸入角色名稱'
    ensure_portal_schema(sub_system_sc)
    with DataSourceManager().get_session(sub_system_sc, 'portal') as sess:
        params = {
            'code': code, 'name': name, 'description': description,
            'display_order': int(display_order),
        }
        if sess.execute(text('SELECT 1 FROM portal_admin_roles WHERE code = :code'), {'code': code}).first():
            sess.execute(text(
                'UPDATE portal_admin_roles SET name = :name, description = :description, '
                'display_order = :display_order, enabled = 1 WHERE code = :code'
            ), params)
        else:
            sess.execute(text(
                'INSERT INTO portal_admin_roles '
                '(code, name, description, is_system, enabled, display_order) '
                'VALUES (:code, :name, :description, 0, 1, :display_order)'
            ), params)
        row = sess.execute(text(
            'SELECT code, name, description, display_order, enabled '
            'FROM portal_admin_roles WHERE code = :code'
        ), {'code': code}).mappings().first()
        sess.commit()
        return dict(row), ''


def delete_admin_role(sub_system_sc, code) -> tuple[bool, str]:
    code = (code or '').strip()
    if not _valid_admin_code(code):
        return False, '角色代碼格式不正確'
    ensure_portal_schema(sub_system_sc)
    with DataSourceManager().get_session(sub_system_sc, 'portal') as sess:
        row = sess.execute(
            text('SELECT id, is_system FROM portal_admin_roles WHERE code = :code'),
            {'code': code},
        ).mappings().first()
        if not row:
            return False, '角色不存在'
        if row['is_system']:
            return False, '系統角色不可刪除'
        sess.execute(text('DELETE FROM portal_admin_roles WHERE id = :id'), {'id': row['id']})
        sess.commit()
        return True, ''


def _replace_target_permissions(sub_system_sc, table_name, link_table, target_column, code, codes, label):
    if not _valid_admin_code(code):
        return False, f'{label}代碼格式不正確'
    ensure_portal_schema(sub_system_sc)
    with DataSourceManager().get_session(sub_system_sc, 'portal') as sess:
        target_id = sess.execute(
            text(f'SELECT id FROM {table_name} WHERE code = :code'),
            {'code': code},
        ).scalar()
        if not target_id:
            return False, f'{label}不存在'
        permission_ids, error = _permission_ids(sess, codes)
        if error:
            return False, error
        sess.execute(
            text(f'DELETE FROM {link_table} WHERE {target_column} = :target_id'),
            {'target_id': target_id},
        )
        for permission_id in permission_ids.values():
            sess.execute(
                text(
                    f'INSERT INTO {link_table} ({target_column}, permission_id) '
                    'VALUES (:target_id, :permission_id)'
                ),
                {'target_id': target_id, 'permission_id': permission_id},
            )
        sess.commit()
        return True, ''


def set_role_permissions(sub_system_sc, role_code, codes) -> tuple[bool, str]:
    return _replace_target_permissions(
        sub_system_sc, 'portal_admin_roles', 'portal_role_permissions',
        'role_id', (role_code or '').strip(), codes, '角色',
    )


def set_level_permissions(sub_system_sc, level_code, codes) -> tuple[bool, str]:
    return _replace_target_permissions(
        sub_system_sc, 'portal_levels', 'portal_level_permissions',
        'level_id', (level_code or '').strip(), codes, '階級',
    )


def set_user_roles(sub_system_sc, user_secure_code, role_codes) -> tuple[bool, str]:
    user_secure_code = (user_secure_code or '').strip()
    if not isinstance(role_codes, list):
        return False, '角色代碼清單格式不正確'
    normalized = []
    for code in role_codes:
        code = (code or '').strip() if isinstance(code, str) else ''
        if not _valid_admin_code(code):
            return False, '角色代碼格式不正確'
        if code not in normalized:
            normalized.append(code)
    ensure_portal_schema(sub_system_sc)
    with DataSourceManager().get_session(sub_system_sc, 'portal') as sess:
        user_id = sess.execute(
            text('SELECT id FROM portal_users WHERE secure_code = :secure_code'),
            {'secure_code': user_secure_code},
        ).scalar()
        if not user_id:
            return False, '帳號不存在'
        role_ids = _select_ids(sess, 'portal_admin_roles', normalized) if normalized else {}
        missing = [code for code in normalized if code not in role_ids]
        if missing:
            return False, '角色不存在：' + ', '.join(missing)
        sess.execute(text('DELETE FROM portal_user_roles WHERE user_id = :user_id'), {'user_id': user_id})
        for role_id in role_ids.values():
            sess.execute(
                text('INSERT INTO portal_user_roles (user_id, role_id) VALUES (:user_id, :role_id)'),
                {'user_id': user_id, 'role_id': role_id},
            )
        sess.commit()
        return True, ''


def set_user_permission_override(sub_system_sc, user_secure_code, code, effect, reason='') -> tuple[bool, str]:
    user_secure_code = (user_secure_code or '').strip()
    code = (code or '').strip()
    reason = (reason or '').strip()
    if not _valid_permission_code(code):
        return False, '權限碼格式不正確'
    if effect not in ('allow', 'deny', None, ''):
        return False, '權限效果不正確'
    ensure_portal_schema(sub_system_sc)
    with DataSourceManager().get_session(sub_system_sc, 'portal') as sess:
        user_id = sess.execute(
            text('SELECT id FROM portal_users WHERE secure_code = :secure_code'),
            {'secure_code': user_secure_code},
        ).scalar()
        permission_id = sess.execute(
            text('SELECT id FROM portal_permissions WHERE code = :code'),
            {'code': code},
        ).scalar()
        if not user_id:
            return False, '帳號不存在'
        if not permission_id:
            return False, '權限碼不存在'
        params = {
            'user_id': user_id, 'permission_id': permission_id,
            'effect': effect, 'reason': reason,
        }
        if effect in (None, ''):
            sess.execute(text(
                'DELETE FROM portal_user_permissions '
                'WHERE user_id = :user_id AND permission_id = :permission_id'
            ), params)
        elif sess.execute(text(
            'SELECT 1 FROM portal_user_permissions '
            'WHERE user_id = :user_id AND permission_id = :permission_id'
        ), params).first():
            sess.execute(text(
                'UPDATE portal_user_permissions SET effect = :effect, reason = :reason '
                'WHERE user_id = :user_id AND permission_id = :permission_id'
            ), params)
        else:
            sess.execute(text(
                'INSERT INTO portal_user_permissions (user_id, permission_id, effect, reason) '
                'VALUES (:user_id, :permission_id, :effect, :reason)'
            ), params)
        sess.commit()
        return True, ''


def apply_permission_template(sub_system_sc, template_code) -> tuple[dict | None, str]:
    template_code = (template_code or '').strip()
    template = PERMISSION_TEMPLATES.get(template_code)
    if not template:
        return None, '權限模板不存在'
    ensure_portal_schema(sub_system_sc)
    with DataSourceManager().get_session(sub_system_sc, 'portal') as sess:
        created = []
        permission_ids = {}
        for item in template.get('permissions') or []:
            code = item['code']
            if not _valid_permission_code(code) or item.get('risk_level') not in RISK_LEVELS:
                return None, '權限模板資料不正確'
            existing = sess.execute(
                text('SELECT id FROM portal_permissions WHERE code = :code'),
                {'code': code},
            ).scalar()
            if existing:
                permission_ids[code] = existing
                continue
            resource, action = code.split('.', 1)
            sess.execute(text(
                'INSERT INTO portal_permissions '
                '(code, resource, action, description, risk_level, enabled) '
                'VALUES (:code, :resource, :action, :description, :risk_level, 1)'
            ), {
                'code': code, 'resource': resource, 'action': action,
                'description': item.get('description') or '',
                'risk_level': item.get('risk_level') or 'normal',
            })
            permission_ids[code] = sess.execute(
                text('SELECT id FROM portal_permissions WHERE code = :code'),
                {'code': code},
            ).scalar()
            created.append(code)
        linked_levels = _link_template_targets(
            sess, 'portal_levels', 'portal_level_permissions', 'level_id',
            template.get('levels') or {}, permission_ids,
        )
        linked_roles = _link_template_targets(
            sess, 'portal_admin_roles', 'portal_role_permissions', 'role_id',
            template.get('roles') or {}, permission_ids,
        )
        sess.commit()
        return {
            'template': template_code,
            'created_permissions': created,
            'linked_levels': linked_levels,
            'linked_roles': linked_roles,
        }, ''


def _link_template_targets(sess, table_name, link_table, target_column, mapping, permission_ids):
    linked = []
    for target_code, codes in mapping.items():
        target_id = sess.execute(
            text(f'SELECT id FROM {table_name} WHERE code = :code'),
            {'code': target_code},
        ).scalar()
        if not target_id:
            continue
        actual_codes = []
        for code in codes:
            permission_id = permission_ids.get(code)
            if not permission_id:
                continue
            sess.execute(
                text(
                    f'INSERT OR IGNORE INTO {link_table} ({target_column}, permission_id) '
                    'VALUES (:target_id, :permission_id)'
                ),
                {'target_id': target_id, 'permission_id': permission_id},
            )
            actual_codes.append(code)
        linked.append({'code': target_code, 'permissions': actual_codes})
    return linked
