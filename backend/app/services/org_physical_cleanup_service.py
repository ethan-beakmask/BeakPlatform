"""Physical cleanup helpers for organization maintenance.

This module is the only implementation point for organization-related physical
resource cleanup. Hostconfig routes must call these functions instead of
constructing paths or deleting files/directories directly.
"""
import os
import shlex
import shutil
from datetime import datetime

from flask import current_app, has_app_context
from flask_babel import gettext as _
from sqlalchemy import bindparam

from app import db
from app.models.organization import Organization
from app.models.platform_file import PlatformFile
from app.services import file_service


def get_upload_base_dir() -> str:
    return file_service.UPLOAD_BASE_DIR


def get_encrypted_storage_dir() -> str:
    return file_service.ENCRYPTED_STORAGE_DIR


def get_edl_output_dir() -> str:
    try:
        from modules.open_defense.services.edl_service import get_output_dir
        return get_output_dir()
    except Exception:
        return (
            (current_app.config.get('OD_EDL_OUTPUT_DIR') if has_app_context() else None)
            or os.getenv('OD_EDL_OUTPUT_DIR')
            or ''
        )


def safe_child_dir(base: str, name: str) -> str | None:
    if not base or not name:
        return None
    if name in {'.', '..'} or '/' in name or '\\' in name:
        return None

    try:
        real_base = os.path.realpath(base)
        joined = os.path.abspath(os.path.join(real_base, name))
        real_joined = os.path.realpath(joined)
    except (TypeError, ValueError, OSError):
        return None

    if os.path.dirname(real_joined) != real_base:
        return None
    return real_joined


def collect_org_file_records(org_codes: list[str]) -> list[PlatformFile]:
    if not org_codes:
        return []
    return PlatformFile.query.filter(
        PlatformFile.org_secure_code.in_(org_codes),
    ).all()


def _record_physical_path(record: PlatformFile) -> str | None:
    if record.storage_type == 'local':
        return file_service._resolve_local_path(record.storage_ref)
    if record.storage_type == 'encrypted':
        return file_service._resolve_encrypted_path(record.storage_ref)
    return None


def delete_org_files(org_codes: list[str]) -> dict:
    result = {'files_deleted': 0, 'files_missing': 0, 'errors': []}
    if not org_codes:
        return result

    for record in collect_org_file_records(org_codes):
        resource = f'file:{record.secure_code}'
        try:
            path = _record_physical_path(record)
            existed = bool(path and os.path.exists(path))
            file_service.delete_file(record, hard_delete_local=True)
            if existed:
                result['files_deleted'] += 1
            else:
                result['files_missing'] += 1
        except Exception as exc:
            result['errors'].append({'resource': resource, 'error': str(exc)})
    return result


def remove_org_directories(org_codes: list[str]) -> dict:
    result = {'dirs_removed': [], 'errors': []}
    if not org_codes:
        return result

    targets = [
        (get_encrypted_storage_dir(), 'encrypted_storage'),
        (get_edl_output_dir(), 'edl'),
    ]
    for org_code in org_codes:
        for base, label in targets:
            if not base:
                continue
            path = safe_child_dir(base, org_code)
            resource = f'{label}:{org_code}'
            if path is None:
                result['errors'].append({
                    'resource': resource,
                    'error': _('拒絕不安全的清理路徑'),
                })
                continue
            if not os.path.isdir(path):
                continue
            try:
                shutil.rmtree(path)
                result['dirs_removed'].append(f'{label}/{org_code}')
            except Exception as exc:
                result['errors'].append({'resource': resource, 'error': str(exc)})
    return result


def list_org_existing_directories(org_codes: list[str]) -> list[str]:
    if not org_codes:
        return []

    directories = []
    targets = [
        (get_encrypted_storage_dir(), 'encrypted_storage'),
        (get_edl_output_dir(), 'edl'),
    ]
    for org_code in org_codes:
        for base, label in targets:
            if not base:
                continue
            path = safe_child_dir(base, org_code)
            if path and os.path.isdir(path):
                directories.append(f'{label}/{org_code}')
    return directories


def _public_table_exists(table_name: str) -> bool:
    try:
        result = db.session.execute(db.text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = :schema AND table_name = :table"
        ), {'schema': 'public', 'table': table_name})
        return result.scalar() is not None
    except Exception:
        return False


def _pg_database_names() -> set[str]:
    try:
        rows = db.session.execute(db.text(
            "SELECT datname FROM pg_database WHERE datname ~ :pattern"
        ), {'pattern': r'^org_[0-9]+$'})
        return {row[0] for row in rows}
    except Exception:
        return set()


def _fw_org_database_rows(org_codes: list[str] | None = None) -> list[dict]:
    if not _public_table_exists('fw_org_databases'):
        return []

    try:
        if org_codes is None:
            rows = db.session.execute(db.text(
                "SELECT org_secure_code, db_name FROM fw_org_databases"
            ))
        elif not org_codes:
            return []
        else:
            stmt = db.text(
                "SELECT org_secure_code, db_name FROM fw_org_databases "
                "WHERE org_secure_code IN :orgs"
            ).bindparams(bindparam('orgs', expanding=True))
            rows = db.session.execute(stmt, {'orgs': org_codes})
        return [
            {'org_secure_code': row[0], 'db_name': row[1]}
            for row in rows
            if row[0] and row[1]
        ]
    except Exception:
        return []


def _manual_database_item(db_name: str, org_secure_code: str, exists: bool, reason: str) -> dict:
    return {
        'type': 'database',
        'name': db_name,
        'org_secure_code': org_secure_code,
        'exists': exists,
        'reason': reason,
        'command': f'sudo -u postgres dropdb {shlex.quote(db_name)}' if exists else '',
    }


def list_org_databases_for_orgs(org_codes: list[str]) -> list[dict]:
    if not org_codes:
        return []

    pg_names = _pg_database_names()
    return [
        {
            'db_name': row['db_name'],
            'org_secure_code': row['org_secure_code'],
            'exists': row['db_name'] in pg_names,
        }
        for row in _fw_org_database_rows(org_codes)
    ]


def list_org_database_manual_items(org_codes: list[str]) -> list[dict]:
    if not org_codes:
        return []

    pg_names = _pg_database_names()
    items = []
    for row in _fw_org_database_rows(org_codes):
        exists = row['db_name'] in pg_names
        if exists:
            continue
        items.append(_manual_database_item(
            row['db_name'],
            row['org_secure_code'],
            exists,
            _('企業資料庫登記存在，但 PostgreSQL 實體資料庫不存在，請人工確認資料一致性'),
        ))
    return items


def _existing_org_codes() -> set[str]:
    try:
        return {row[0] for row in db.session.query(Organization.secure_code).all()}
    except Exception:
        return set()


def _scan_orphan_upload_files() -> list[dict]:
    base = get_upload_base_dir()
    try:
        referenced = {
            os.path.basename(row[0])
            for row in db.session.query(PlatformFile.storage_ref).all()
            if row[0]
        }
        entries = []
        for item in os.scandir(base):
            if not item.is_file():
                continue
            if item.name in referenced:
                continue
            entries.append({
                'name': item.name,
                'size': item.stat().st_size,
                'modified_at': datetime.utcfromtimestamp(
                    os.path.getmtime(item.path)
                ).isoformat(),
            })
        return sorted(entries, key=lambda entry: entry['name'])
    except Exception:
        return []


def _dir_size_and_count(path: str) -> tuple[int, int]:
    file_count = 0
    total_size = 0
    for root, _dirs, files in os.walk(path):
        for filename in files:
            file_count += 1
            file_path = os.path.join(root, filename)
            try:
                total_size += os.path.getsize(file_path)
            except OSError:
                pass
    return file_count, total_size


def _scan_orphan_child_dirs(base: str, label: str, existing_org_codes: set[str]) -> list[dict]:
    if not base:
        return []
    try:
        entries = []
        for item in os.scandir(base):
            if not item.is_dir():
                continue
            if item.name in existing_org_codes:
                continue
            safe_path = safe_child_dir(base, item.name)
            if safe_path is None:
                continue
            if label == 'encrypted_storage':
                file_count, size = _dir_size_and_count(safe_path)
                entries.append({
                    'org_secure_code': item.name,
                    'file_count': file_count,
                    'size': size,
                })
            else:
                entries.append({'org_secure_code': item.name})
        return sorted(entries, key=lambda entry: entry['org_secure_code'])
    except Exception:
        return []


def _scan_manual_database_items() -> list[dict]:
    pg_names = _pg_database_names()
    fw_rows = _fw_org_database_rows()
    existing_org_codes = _existing_org_codes()
    valid_registered = {
        row['db_name']
        for row in fw_rows
        if row['org_secure_code'] in existing_org_codes
    }
    items = []

    for db_name in sorted(pg_names - valid_registered):
        items.append(_manual_database_item(
            db_name,
            '',
            True,
            _('企業資料庫不屬於任何現存企業，請在「企業獨立資料庫管理」頁清理'),
        ))

    for row in sorted(fw_rows, key=lambda item: item['db_name']):
        if row['db_name'] not in pg_names:
            items.append(_manual_database_item(
                row['db_name'],
                row['org_secure_code'],
                False,
                _('企業資料庫登記存在，但 PostgreSQL 實體資料庫不存在，請在「企業獨立資料庫管理」頁補建或清理'),
            ))

    return items


def scan_physical_orphans() -> dict:
    existing_org_codes = _existing_org_codes()
    orphan_upload_files = _scan_orphan_upload_files()
    orphan_encrypted_dirs = _scan_orphan_child_dirs(
        get_encrypted_storage_dir(),
        'encrypted_storage',
        existing_org_codes,
    )
    orphan_edl_dirs = _scan_orphan_child_dirs(
        get_edl_output_dir(),
        'edl',
        existing_org_codes,
    )
    manual_required = _scan_manual_database_items()
    return {
        'orphan_upload_files': orphan_upload_files,
        'orphan_encrypted_dirs': orphan_encrypted_dirs,
        'orphan_edl_dirs': orphan_edl_dirs,
        'manual_required': manual_required,
        'total_removable': (
            len(orphan_upload_files)
            + len(orphan_encrypted_dirs)
            + len(orphan_edl_dirs)
        ),
    }


def delete_physical_orphans() -> dict:
    scan = scan_physical_orphans()
    result = {'files_deleted': 0, 'dirs_removed': [], 'errors': [], 'has_errors': False}

    upload_base = get_upload_base_dir()
    for item in scan['orphan_upload_files']:
        path = safe_child_dir(upload_base, item['name'])
        if path is None:
            result['errors'].append({
                'resource': f"upload:{item['name']}",
                'error': _('拒絕不安全的清理路徑'),
            })
            continue
        try:
            if os.path.isfile(path):
                os.remove(path)
                result['files_deleted'] += 1
        except Exception as exc:
            result['errors'].append({
                'resource': f"upload:{item['name']}",
                'error': str(exc),
            })

    dir_targets = [
        (get_encrypted_storage_dir(), 'encrypted_storage', scan['orphan_encrypted_dirs']),
        (get_edl_output_dir(), 'edl', scan['orphan_edl_dirs']),
    ]
    for base, label, entries in dir_targets:
        if not base:
            continue
        for item in entries:
            org_code = item['org_secure_code']
            path = safe_child_dir(base, org_code)
            resource = f'{label}:{org_code}'
            if path is None:
                result['errors'].append({
                    'resource': resource,
                    'error': _('拒絕不安全的清理路徑'),
                })
                continue
            if not os.path.isdir(path):
                continue
            try:
                shutil.rmtree(path)
                result['dirs_removed'].append(f'{label}/{org_code}')
            except Exception as exc:
                result['errors'].append({'resource': resource, 'error': str(exc)})

    result['has_errors'] = bool(result['errors'])
    return result
