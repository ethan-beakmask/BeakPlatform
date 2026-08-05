"""PF-44 portal file metadata storage service."""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.utils.security import generate_secure_code

from .data_source_manager import DataSourceManager, ensure_portal_schema

PORTAL_FILE_CONTEXT_TYPE = 'portal_file'
DESIGNER_REF_PREFIX = 'designer:'
PORTAL_USER_REF_PREFIX = 'u:'

_DEFAULT_MAX_FILES = 20


def _row_dict(row) -> dict:
    return dict(row) if row is not None else {}


def find_file_box_widget(layout_json: dict, widget_id: str) -> dict | None:
    """從 Page IR 找出指定 file_box widget，找不到或 type 不符時回 None。"""
    if not isinstance(layout_json, dict) or not widget_id:
        return None
    page = layout_json.get('page')
    widgets = page.get('widgets') if isinstance(page, dict) else []
    indexed = _index_widgets(widgets if isinstance(widgets, list) else [])
    widget = indexed.get(widget_id)
    if isinstance(widget, dict) and widget.get('type') == 'file_box':
        return widget
    return None


def _index_widgets(widgets: list[dict]) -> dict[str, dict]:
    indexed = {}
    for widget in widgets:
        if not isinstance(widget, dict) or 'id' not in widget:
            continue
        indexed[widget['id']] = widget
        if widget.get('type') == 'layout':
            indexed.update(_index_widgets(widget.get('children', [])))
    return indexed


def widget_setting(widget: dict) -> dict:
    """回傳 file_box 設定，型別不符一律回退預設值。

    設定值**直接掛在 widget 物件上**（`{"type": "file_box", "upload_by": ...}`），
    沒有 `settings` 子物件——見 docs/PORTAL_FILE_WIDGET_SPEC.md §6 的 IR 定義。
    """
    raw = widget if isinstance(widget, dict) else {}

    upload_by = raw.get('upload_by')
    if upload_by not in {'designer', 'portal_user'}:
        upload_by = 'portal_user'

    read_scope = raw.get('read_scope')
    if not isinstance(read_scope, list):
        read_scope = []
    else:
        read_scope = [item for item in read_scope if isinstance(item, str)]

    try:
        max_files = int(raw.get('max_files', _DEFAULT_MAX_FILES))
    except (TypeError, ValueError):
        max_files = _DEFAULT_MAX_FILES
    if max_files <= 0:
        max_files = _DEFAULT_MAX_FILES

    allowed_ext = raw.get('allowed_ext')
    if isinstance(allowed_ext, list):
        normalized_ext = {
            item.strip().lower().lstrip('.')
            for item in allowed_ext
            if isinstance(item, str) and item.strip()
        }
    else:
        normalized_ext = set()

    return {
        'upload_by': upload_by,
        'per_file_acl': bool(raw.get('per_file_acl')),
        'guest_readable': bool(raw.get('guest_readable')),
        'read_scope': read_scope,
        'max_files': max_files,
        'allowed_ext': normalized_ext,
    }


def create_file_record(sub_system_sc, *, platform_file_sc, page_sc, widget_id,
                       uploader_ref, original_name, file_size, file_ext) -> dict:
    """新增 portal_files 對照列，secure_code 衝突時重試一次。"""
    ensure_portal_schema(sub_system_sc)
    last_error = None
    for _attempt in range(2):
        secure_code = generate_secure_code()
        try:
            with DataSourceManager().get_session(sub_system_sc, 'portal') as sess:
                sess.execute(
                    text(
                        'INSERT INTO portal_files '
                        '(secure_code, platform_file_sc, page_sc, widget_id, uploader_ref, '
                        'original_name, file_size, file_ext) '
                        'VALUES (:secure_code, :platform_file_sc, :page_sc, :widget_id, '
                        ':uploader_ref, :original_name, :file_size, :file_ext)'
                    ),
                    {
                        'secure_code': secure_code,
                        'platform_file_sc': platform_file_sc,
                        'page_sc': page_sc,
                        'widget_id': widget_id,
                        'uploader_ref': uploader_ref,
                        'original_name': original_name,
                        'file_size': int(file_size or 0),
                        'file_ext': (file_ext or '').lower(),
                    },
                )
                row = sess.execute(
                    text(
                        'SELECT secure_code, platform_file_sc, page_sc, widget_id, uploader_ref, '
                        'original_name, file_size, file_ext, created_at '
                        'FROM portal_files WHERE secure_code = :secure_code'
                    ),
                    {'secure_code': secure_code},
                ).mappings().first()
                return _row_dict(row)
        except IntegrityError as exc:
            last_error = exc
    raise last_error


def list_widget_files(sub_system_sc, page_sc, widget_id) -> list[dict]:
    """列出指定元件未刪除檔案。"""
    ensure_portal_schema(sub_system_sc)
    with DataSourceManager().get_session(sub_system_sc, 'portal') as sess:
        rows = sess.execute(
            text(
                'SELECT secure_code, platform_file_sc, page_sc, widget_id, uploader_ref, '
                'original_name, file_size, file_ext, created_at '
                'FROM portal_files '
                'WHERE page_sc = :page_sc AND widget_id = :widget_id AND is_deleted = 0 '
                'ORDER BY created_at DESC, id DESC'
            ),
            {'page_sc': page_sc, 'widget_id': widget_id},
        ).mappings().all()
        return [dict(row) for row in rows]


def count_uploader_files(sub_system_sc, page_sc, widget_id, uploader_ref) -> int:
    """計算指定上傳者在元件中的未刪除檔案數。"""
    ensure_portal_schema(sub_system_sc)
    with DataSourceManager().get_session(sub_system_sc, 'portal') as sess:
        return sess.execute(
            text(
                'SELECT COUNT(*) FROM portal_files '
                'WHERE page_sc = :page_sc AND widget_id = :widget_id '
                'AND uploader_ref = :uploader_ref AND is_deleted = 0'
            ),
            {'page_sc': page_sc, 'widget_id': widget_id, 'uploader_ref': uploader_ref},
        ).scalar() or 0


def get_file(sub_system_sc, file_sc) -> dict | None:
    """取得未刪除 portal_files 列。"""
    ensure_portal_schema(sub_system_sc)
    with DataSourceManager().get_session(sub_system_sc, 'portal') as sess:
        row = sess.execute(
            text(
                'SELECT secure_code, platform_file_sc, page_sc, widget_id, uploader_ref, '
                'original_name, file_size, file_ext, created_at '
                'FROM portal_files WHERE secure_code = :secure_code AND is_deleted = 0'
            ),
            {'secure_code': file_sc},
        ).mappings().first()
        return dict(row) if row else None


def soft_delete_file(sub_system_sc, file_sc) -> bool:
    """軟刪 portal_files 並清除該檔 ACL。"""
    ensure_portal_schema(sub_system_sc)
    with DataSourceManager().get_session(sub_system_sc, 'portal') as sess:
        result = sess.execute(
            text(
                "UPDATE portal_files SET is_deleted = 1, deleted_at = datetime('now') "
                "WHERE secure_code = :secure_code AND is_deleted = 0"
            ),
            {'secure_code': file_sc},
        )
        if result.rowcount:
            sess.execute(
                text('DELETE FROM portal_file_acl WHERE file_secure_code = :secure_code'),
                {'secure_code': file_sc},
            )
        return bool(result.rowcount)


def list_file_acl(sub_system_sc, file_sc) -> list[dict]:
    """列出指定檔案 ACL。"""
    ensure_portal_schema(sub_system_sc)
    with DataSourceManager().get_session(sub_system_sc, 'portal') as sess:
        rows = sess.execute(
            text(
                'SELECT grantee_type, grantee_code, created_at '
                'FROM portal_file_acl '
                'WHERE file_secure_code = :file_secure_code '
                'ORDER BY grantee_type ASC, grantee_code ASC'
            ),
            {'file_secure_code': file_sc},
        ).mappings().all()
        return [dict(row) for row in rows]


def set_file_acl(sub_system_sc, file_sc, entries: list[dict]) -> list[dict]:
    """整組覆寫指定檔案 ACL。"""
    ensure_portal_schema(sub_system_sc)
    with DataSourceManager().get_session(sub_system_sc, 'portal') as sess:
        sess.execute(
            text('DELETE FROM portal_file_acl WHERE file_secure_code = :file_secure_code'),
            {'file_secure_code': file_sc},
        )
        for entry in entries:
            sess.execute(
                text(
                    'INSERT INTO portal_file_acl '
                    '(file_secure_code, grantee_type, grantee_code) '
                    'VALUES (:file_secure_code, :grantee_type, :grantee_code)'
                ),
                {
                    'file_secure_code': file_sc,
                    'grantee_type': entry['grantee_type'],
                    'grantee_code': entry['grantee_code'],
                },
            )
        rows = sess.execute(
            text(
                'SELECT grantee_type, grantee_code, created_at '
                'FROM portal_file_acl '
                'WHERE file_secure_code = :file_secure_code '
                'ORDER BY grantee_type ASC, grantee_code ASC'
            ),
            {'file_secure_code': file_sc},
        ).mappings().all()
        return [dict(row) for row in rows]


def acl_grantees_exist(sub_system_sc, entries: list[dict]) -> tuple[bool, str]:
    """確認 ACL grantee 存在且可用。"""
    ensure_portal_schema(sub_system_sc)
    with DataSourceManager().get_session(sub_system_sc, 'portal') as sess:
        for entry in entries:
            grantee_type = entry.get('grantee_type')
            grantee_code = entry.get('grantee_code')
            if grantee_type == 'user':
                exists = sess.execute(
                    text(
                        'SELECT 1 FROM portal_users '
                        'WHERE secure_code = :code AND is_active = 1'
                    ),
                    {'code': grantee_code},
                ).first()
            elif grantee_type == 'role':
                exists = sess.execute(
                    text('SELECT 1 FROM portal_admin_roles WHERE code = :code'),
                    {'code': grantee_code},
                ).first()
            else:
                exists = None
            if not exists:
                return False, grantee_code or ''
    return True, ''
