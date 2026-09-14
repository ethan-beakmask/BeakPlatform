import os
import sys

from app import db
from app.models.organization import Organization
from app.models.platform_file import PlatformFile
from app.services import org_physical_cleanup_service as svc


def _patch_storage_dirs(monkeypatch, tmp_path):
    uploads = tmp_path / 'uploads'
    encrypted = tmp_path / 'encrypted_storage'
    edl = tmp_path / 'edl'
    monkeypatch.setattr(svc.file_service, 'UPLOAD_BASE_DIR', str(uploads))
    monkeypatch.setattr(svc.file_service, 'ENCRYPTED_STORAGE_DIR', str(encrypted))
    monkeypatch.setattr(svc, 'get_edl_output_dir', lambda: str(edl))
    return uploads, encrypted, edl


def test_safe_child_dir_rejects_invalid_names(tmp_path):
    base = tmp_path / 'base'
    base.mkdir()

    assert svc.safe_child_dir(str(base), '..') is None
    assert svc.safe_child_dir(str(base), '.') is None
    assert svc.safe_child_dir(str(base), 'a/b') is None
    assert svc.safe_child_dir(str(base), '') is None
    assert svc.safe_child_dir('', 'child') is None


def test_safe_child_dir_rejects_symlink_escape(tmp_path):
    base = tmp_path / 'base'
    outside = tmp_path / 'outside'
    base.mkdir()
    outside.mkdir()
    (base / 'escape').symlink_to(outside, target_is_directory=True)

    assert svc.safe_child_dir(str(base), 'escape') is None


def test_safe_child_dir_accepts_normal_name(tmp_path):
    base = tmp_path / 'base'
    base.mkdir()

    assert svc.safe_child_dir(str(base), 'org_sc') == os.path.realpath(base / 'org_sc')


def test_get_edl_output_dir_falls_back_to_config_env_and_empty(app, monkeypatch):
    monkeypatch.setitem(
        sys.modules,
        'modules.open_defense.services.edl_service',
        None,
    )

    monkeypatch.setenv('OD_EDL_OUTPUT_DIR', '/env/edl')
    app.config['OD_EDL_OUTPUT_DIR'] = '/config/edl'
    assert svc.get_edl_output_dir() == '/config/edl'

    app.config['OD_EDL_OUTPUT_DIR'] = ''
    assert svc.get_edl_output_dir() == '/env/edl'

    monkeypatch.delenv('OD_EDL_OUTPUT_DIR', raising=False)
    assert svc.get_edl_output_dir() == ''


def test_scan_physical_orphans_missing_dirs_is_fail_safe(app, monkeypatch, tmp_path):
    uploads, encrypted, edl = _patch_storage_dirs(monkeypatch, tmp_path)

    assert not uploads.exists()
    assert not encrypted.exists()
    assert not edl.exists()

    result = svc.scan_physical_orphans()

    assert result['orphan_upload_files'] == []
    assert result['orphan_encrypted_dirs'] == []
    assert result['orphan_edl_dirs'] == []


def test_scan_physical_orphans_detects_unreferenced_upload_file(app, monkeypatch, tmp_path):
    uploads, _encrypted, _edl = _patch_storage_dirs(monkeypatch, tmp_path)
    uploads.mkdir()
    (uploads / 'referenced.png').write_bytes(b'referenced')
    (uploads / 'orphan.png').write_bytes(b'orphan')

    org = Organization(
        secure_code='org_scan_upload',
        code='ORG_SCAN_UPLOAD',
        name='Org Scan Upload',
        domain_name='scan-upload.local',
    )
    db.session.add(org)
    db.session.add(PlatformFile(
        secure_code='file_scan_upload',
        org_secure_code=org.secure_code,
        storage_type='local',
        storage_ref='referenced.png',
        original_name='referenced.png',
        file_size=10,
        context_type='org_logo',
        status='active',
    ))
    db.session.commit()

    result = svc.scan_physical_orphans()

    assert [item['name'] for item in result['orphan_upload_files']] == ['orphan.png']
    assert result['orphan_upload_files'][0]['size'] == len(b'orphan')
    assert 'T' in result['orphan_upload_files'][0]['modified_at']


def test_empty_org_code_inputs_do_not_query_db(monkeypatch):
    def fail_query(*args, **kwargs):
        raise AssertionError('DB should not be queried for empty org_codes')

    monkeypatch.setattr(svc, 'PlatformFile', type('PlatformFileTrap', (), {
        'org_secure_code': object(),
        'filter': fail_query,
        'query': type('QueryTrap', (), {'filter': fail_query})(),
    })())

    assert svc.collect_org_file_records([]) == []
    assert svc.delete_org_files([]) == {
        'files_deleted': 0,
        'files_missing': 0,
        'errors': [],
    }
    assert svc.remove_org_directories([]) == {
        'dirs_removed': [],
        'errors': [],
    }


def test_delete_physical_orphans_does_not_delete_base_dirs(app, monkeypatch, tmp_path):
    uploads, encrypted, edl = _patch_storage_dirs(monkeypatch, tmp_path)
    uploads.mkdir()
    encrypted.mkdir()
    edl.mkdir()
    orphan_code = 'missing_org_dirs'
    (encrypted / orphan_code).mkdir()
    (encrypted / orphan_code / 'payload.bin').write_bytes(b'encrypted')
    (edl / orphan_code).mkdir()
    (edl / orphan_code / 'payload.json').write_bytes(b'edl')

    result = svc.delete_physical_orphans()

    assert uploads.exists()
    assert encrypted.exists()
    assert edl.exists()
    assert not (encrypted / orphan_code).exists()
    assert not (edl / orphan_code).exists()
    assert result['dirs_removed'] == [
        f'encrypted_storage/{orphan_code}',
        f'edl/{orphan_code}',
    ]
    assert result['has_errors'] is False


def test_delete_physical_orphans_preserves_existing_org_dirs(app, monkeypatch, tmp_path):
    _uploads, encrypted, edl = _patch_storage_dirs(monkeypatch, tmp_path)
    encrypted.mkdir()
    edl.mkdir()

    org = Organization(
        secure_code='existing_org_dirs',
        code='EXISTING_DIRS',
        name='Existing Dirs',
        domain_name='existing-dirs.local',
    )
    db.session.add(org)
    db.session.commit()

    (encrypted / org.secure_code).mkdir()
    encrypted_file = encrypted / org.secure_code / 'keep.bin'
    encrypted_file.write_bytes(b'keep encrypted')
    (edl / org.secure_code).mkdir()
    edl_file = edl / org.secure_code / 'keep.json'
    edl_file.write_bytes(b'keep edl')

    orphan_code = 'orphan_dir_control'
    (encrypted / orphan_code).mkdir()
    (encrypted / orphan_code / 'remove.bin').write_bytes(b'remove encrypted')
    (edl / orphan_code).mkdir()
    (edl / orphan_code / 'remove.json').write_bytes(b'remove edl')

    result = svc.delete_physical_orphans()

    assert (encrypted / org.secure_code).is_dir()
    assert encrypted_file.read_bytes() == b'keep encrypted'
    assert (edl / org.secure_code).is_dir()
    assert edl_file.read_bytes() == b'keep edl'
    assert not (encrypted / orphan_code).exists()
    assert not (edl / orphan_code).exists()
    assert result['has_errors'] is False


def test_remove_org_directories_removes_targets_and_ignores_missing(app, monkeypatch, tmp_path):
    _uploads, encrypted, edl = _patch_storage_dirs(monkeypatch, tmp_path)
    encrypted.mkdir()
    edl.mkdir()
    org_code = 'remove_org_dirs'
    (encrypted / org_code).mkdir()
    (encrypted / org_code / 'payload.bin').write_bytes(b'encrypted')
    (edl / org_code).mkdir()
    (edl / org_code / 'payload.json').write_bytes(b'edl')

    result = svc.remove_org_directories([org_code])

    assert result == {
        'dirs_removed': [
            f'encrypted_storage/{org_code}',
            f'edl/{org_code}',
        ],
        'errors': [],
    }
    assert encrypted.exists()
    assert edl.exists()
    assert not (encrypted / org_code).exists()
    assert not (edl / org_code).exists()

    missing_result = svc.remove_org_directories(['missing_org_dirs'])

    assert missing_result == {'dirs_removed': [], 'errors': []}
