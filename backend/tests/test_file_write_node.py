# -*- coding: utf-8 -*-
"""
FileWrite 節點的安全與位元組行為測試

這個節點的風險是「重複副作用」與「越界寫檔」：一旦 queue 被標成失敗，
平台重試可能把同一段內容寫入多次；一旦路徑防護有缺口，流程設定就能改寫
允許目錄之外的檔案。

所以測試重點不是只看文字有沒有追加成功，而是：所有拒絕情境都必須回
success 並把真相放進流程變數、目標路徑必須被限制在允許目錄內、既有檔案
在截掉尾端換行以前的位元組必須完全不變。
"""
import fcntl
import hashlib
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app import db  # noqa: E402
from app.models import SystemSetting  # noqa: E402
from modules.form_workflow.models import (  # noqa: E402
    WorkflowNodeDefinition,
    WorkflowNodeOrgGrant,
)
from modules.form_workflow.services.node_handlers.file_write_handler import (  # noqa: E402
    FileWriteHandler,
    _coerce_bool,
    _coerce_int,
    _env_flag_enabled,
    _is_under_path,
)

ORG_A = 'ORG_AAAAAAAAAAAAAAAAAAAA'
ORG_B = 'ORG_BBBBBBBBBBBBBBBBBBBB'


@pytest.fixture
def filewrite_env(app, tmp_path, monkeypatch):
    monkeypatch.setenv('FILE_WRITE_NODE_ENABLED', '1')
    db.session.add(WorkflowNodeDefinition(
        secure_code='node_filewrite_0000000001',
        node_type='FileWrite',
        category='系統',
        display_name='檔案寫入',
        execution_handler='tests.FileWrite',
        org_restricted=True,
        is_active=True,
        is_deleted=False,
    ))
    db.session.add(WorkflowNodeOrgGrant(
        node_type='FileWrite',
        org_secure_code=ORG_A,
        granted_by_name='test',
        is_deleted=False,
    ))
    db.session.add(SystemSetting(
        key='file_write_base_dirs',
        value=json.dumps([str(tmp_path)]),
        value_type='json',
        category='file_write',
    ))
    db.session.commit()
    return Path(os.path.realpath(str(tmp_path)))


def make_handler(config, org=ORG_A, has_edges=True, replace=None):
    queue_item = SimpleNamespace(
        org_secure_code=org,
        node_id='n_fw_1',
        node_type='FileWrite',
        node_config=config,
        secure_code='QUEUE_TEST',
        status='PENDING',
        id=1,
        retry_count=0,
        started_at=None,
        process_id=None,
        workflow_instance_secure_code=None,
    )
    handler = FileWriteHandler(queue_item)
    flow_vars = {}
    handler.report_running = lambda: None
    handler.log_info = lambda msg, details=None: None
    handler.log_error = lambda msg, details=None: None
    handler.set_flow_var = lambda name, value: flow_vars.__setitem__(name, value)
    handler.replace_variables = replace or (lambda text, **kw: text)
    handler._has_outgoing_edges = lambda: has_edges
    return handler, flow_vars


def config_for(base_dir, file_path='out.log', **overrides):
    config = {
        'base_dir': str(base_dir),
        'file_path': file_path,
        'content': 'XYZ',
        'result_var': 'fw',
    }
    config.update(overrides)
    return config


def run_filewrite(base_dir, file_path='out.log', **overrides):
    handler, flow_vars = make_handler(config_for(base_dir, file_path, **overrides))
    return handler.handle(), flow_vars


def assert_success_response(resp):
    assert resp['status'] == 'success'
    assert resp['status'] not in ('error', 'waiting', 'pending')


@pytest.mark.parametrize('raw,expected', [
    (None, False),
    ('', False),
    (' 0 ', False),
    ('false', False),
    ('1', True),
    ('yes', True),
])
def test_env_flag_enabled_values(raw, expected):
    assert _env_flag_enabled(raw) is expected


@pytest.mark.parametrize('raw,default,expected', [
    (None, True, True),
    (None, False, False),
    ('true', False, True),
    ('off', True, False),
    (0, True, False),
    (123, False, True),
])
def test_coerce_bool_values(raw, default, expected):
    assert _coerce_bool(raw, default) is expected


@pytest.mark.parametrize('raw,expected', [
    ('7', 7),
    ('bad', 5),
    (-1, 1),
    (999, 10),
])
def test_coerce_int_defaults_and_clamps(raw, expected):
    assert _coerce_int(raw, default=5, minimum=1, maximum=10) == expected


def test_is_under_path_accepts_only_descendants(filewrite_env):
    base = str(filewrite_env)

    assert _is_under_path(str(filewrite_env / 'child.log'), base) is True
    assert _is_under_path(str(filewrite_env.parent / 'outside.log'), base) is False


@pytest.mark.parametrize('initial,expected,trimmed', [
    (b'abc', b'abc\nXYZ\n', 0),
    (b'abc\n', b'abc\nXYZ\n', 1),
    (b'abc\r\n', b'abc\nXYZ\n', 2),
    (b'abc\r', b'abc\nXYZ\n', 1),
    (b'abc\n\n\n', b'abc\nXYZ\n', 3),
    (b'abc\r\n\r\n', b'abc\nXYZ\n', 4),
    (b'abc\n\r\n', b'abc\nXYZ\n', 3),
    (b'abc\r\r\n\n\r', b'abc\nXYZ\n', 5),
    (b'', b'XYZ\n', 0),
    (b'\n\n\n', b'XYZ\n', 3),
])
def test_truncates_all_trailing_newline_bytes(filewrite_env, initial, expected, trimmed):
    target = filewrite_env / 'matrix.log'
    target.write_bytes(initial)

    resp, flow_vars = run_filewrite(
        filewrite_env,
        file_path='matrix.log',
        newline_before=True,
        newline_after=True,
    )

    assert_success_response(resp)
    assert target.read_bytes() == expected
    assert flow_vars['fw_trimmed_bytes'] == trimmed


@pytest.mark.parametrize('before,after,expected', [
    (False, False, b'abcXYZ'),
    (False, True, b'abcXYZ\n'),
    (True, False, b'abc\nXYZ'),
    (True, True, b'abc\nXYZ\n'),
])
def test_newline_before_after_combinations(filewrite_env, before, after, expected):
    target = filewrite_env / 'out.log'
    target.write_bytes(b'abc\n')

    resp, _ = run_filewrite(
        filewrite_env,
        newline_before=before,
        newline_after=after,
    )

    assert_success_response(resp)
    assert target.read_bytes() == expected


def test_content_newlines_are_written_verbatim(filewrite_env):
    target = filewrite_env / 'out.log'
    target.write_bytes(b'abc\n')

    resp, _ = run_filewrite(
        filewrite_env,
        content='L1\nL2\n',
        newline_before=False,
        newline_after=True,
    )

    assert_success_response(resp)
    assert target.read_bytes() == b'abcL1\nL2\n\n'


def test_empty_content_is_valid(filewrite_env):
    target = filewrite_env / 'out.log'
    target.write_bytes(b'abc\n\n\n')

    resp, _ = run_filewrite(filewrite_env, content='', newline_after=True)

    assert_success_response(resp)
    assert target.read_bytes() == b'abc\n'


def test_existing_prefix_bytes_remain_unchanged(filewrite_env):
    prefix = bytes(range(1, 256))
    initial = prefix + b'\r\n\r\n\n'
    target = filewrite_env / 'out.log'
    target.write_bytes(initial)

    resp, flow_vars = run_filewrite(
        filewrite_env,
        content='Z',
        newline_before=True,
        newline_after=True,
    )

    written = target.read_bytes()
    assert_success_response(resp)
    assert hashlib.md5(written[:len(prefix)]).digest() == hashlib.md5(prefix).digest()
    assert written == prefix + b'\nZ\n'
    assert flow_vars['fw_size_before'] == len(initial)
    assert flow_vars['fw_size_after'] == len(prefix) + 3
    assert flow_vars['fw_bytes_written'] == 3


def test_big5_file_prefix_and_append_bytes_are_preserved(filewrite_env):
    prefix = '中文測試行'.encode('big5')
    target = filewrite_env / 'out.log'
    target.write_bytes(prefix)

    resp, _ = run_filewrite(
        filewrite_env,
        content='新增',
        encoding='big5',
        newline_after=False,
    )

    assert_success_response(resp)
    assert target.read_bytes() == prefix + '新增'.encode('big5')


def test_binary_prefix_is_not_decoded_or_rewritten(filewrite_env):
    prefix = b'\xff\xfe\xfa\x00\x80'
    target = filewrite_env / 'out.log'
    target.write_bytes(prefix)

    resp, _ = run_filewrite(filewrite_env, content='OK')

    assert_success_response(resp)
    assert target.read_bytes() == prefix + b'OK\n'


@pytest.mark.parametrize('encoding', ['utf-16', 'rot13'])
def test_rejects_unsupported_or_non_text_encoding(filewrite_env, encoding):
    target = filewrite_env / 'out.log'
    target.write_bytes(b'abc')

    resp, flow_vars = run_filewrite(filewrite_env, encoding=encoding)

    assert_success_response(resp)
    assert resp['data']['_error_kind'] == 'bad_config'
    assert flow_vars['fw_error_kind'] == 'bad_config'
    assert target.read_bytes() == b'abc'


def test_encode_error_does_not_modify_file(filewrite_env):
    target = filewrite_env / 'out.log'
    original = b'abc\n'
    target.write_bytes(original)

    resp, flow_vars = run_filewrite(
        filewrite_env,
        content='bad \U0001F642',
        encoding='big5',
    )

    assert_success_response(resp)
    assert resp['data']['_error_kind'] == 'encode_error'
    assert flow_vars['fw_error_kind'] == 'encode_error'
    assert target.read_bytes() == original


@pytest.mark.parametrize('case_name,file_path,base_dir_factory,target_factory', [
    ('parent_escape', '../escape.log', lambda base: base, lambda base: base.parent / 'escape.log'),
    ('deep_escape', '../../escape.log', lambda base: base, lambda base: base.parent.parent / 'escape.log'),
    ('absolute_outside', None, lambda base: base, lambda base: base.parent / 'outside_abs.log'),
    ('base_not_allowed', 'out.log', lambda base: base.parent / 'unlisted_base', lambda base: base.parent / 'unlisted_base' / 'out.log'),
    ('base_missing', 'out.log', lambda base: base / 'missing_base', lambda base: base / 'missing_base' / 'out.log'),
    ('parent_missing', 'missing_parent/out.log', lambda base: base, lambda base: base / 'missing_parent' / 'out.log'),
])
def test_path_denied_cases_do_not_create_target(
    filewrite_env, case_name, file_path, base_dir_factory, target_factory
):
    base_dir = base_dir_factory(filewrite_env)
    target = target_factory(filewrite_env)
    if case_name == 'base_not_allowed':
        base_dir.mkdir()
    actual_file_path = str(target) if case_name == 'absolute_outside' else file_path

    resp, _ = run_filewrite(base_dir, file_path=actual_file_path)

    assert_success_response(resp)
    assert resp['data']['_error_kind'] == 'path_denied'
    assert not target.exists()


def test_symlink_to_outside_is_rejected_without_modifying_target(filewrite_env):
    outside = filewrite_env.parent / 'outside_target.log'
    outside.write_bytes(b'outside')
    link = filewrite_env / 'out.log'
    link.symlink_to(outside)

    resp, _ = run_filewrite(filewrite_env)

    assert_success_response(resp)
    assert resp['data']['_error_kind'] == 'path_denied'
    assert outside.read_bytes() == b'outside'


def test_symlink_to_inside_is_rejected_without_modifying_target(filewrite_env):
    inside = filewrite_env / 'inside_target.log'
    inside.write_bytes(b'inside')
    link = filewrite_env / 'out.log'
    link.symlink_to(inside)

    resp, _ = run_filewrite(filewrite_env)

    assert_success_response(resp)
    assert resp['data']['_error_kind'] == 'path_denied'
    assert inside.read_bytes() == b'inside'


@pytest.mark.parametrize('maker', [
    lambda path: path.mkdir(),
    lambda path: os.mkfifo(path),
])
def test_non_regular_file_targets_are_rejected(filewrite_env, maker):
    target = filewrite_env / 'out.log'
    maker(target)

    resp, _ = run_filewrite(filewrite_env)

    assert_success_response(resp)
    assert resp['data']['_error_kind'] == 'path_denied'


def test_missing_file_with_create_disabled_is_not_created(filewrite_env):
    target = filewrite_env / 'out.log'

    resp, _ = run_filewrite(filewrite_env, create_if_missing=False)

    assert_success_response(resp)
    assert resp['data']['_error_kind'] == 'file_not_found'
    assert not target.exists()


def test_ungranted_org_is_not_authorized_and_file_is_unchanged(filewrite_env):
    target = filewrite_env / 'out.log'
    target.write_bytes(b'abc')
    handler, _ = make_handler(config_for(filewrite_env), org=ORG_B)

    resp = handler.handle()

    assert_success_response(resp)
    assert resp['data']['_error_kind'] == 'not_authorized'
    assert target.read_bytes() == b'abc'


def test_missing_env_flag_is_not_authorized(filewrite_env, monkeypatch):
    monkeypatch.delenv('FILE_WRITE_NODE_ENABLED')

    resp, _ = run_filewrite(filewrite_env)

    assert_success_response(resp)
    assert resp['data']['_error_kind'] == 'not_authorized'


def test_disabled_env_flag_is_not_authorized(filewrite_env, monkeypatch):
    monkeypatch.setenv('FILE_WRITE_NODE_ENABLED', '0')

    resp, _ = run_filewrite(filewrite_env)

    assert_success_response(resp)
    assert resp['data']['_error_kind'] == 'not_authorized'


@pytest.mark.parametrize('case_name,config_mutator,org,expected_result', [
    ('success', lambda base, config: config, ORG_A, 'ok'),
    ('auth_denied', lambda base, config: config, ORG_B, 'exception'),
    ('path_denied', lambda base, config: {**config, 'file_path': '../escape.log'}, ORG_A, 'exception'),
    ('bad_config', lambda base, config: {**config, 'result_var': '../x'}, ORG_A, 'exception'),
])
def test_all_outcomes_return_success_status(filewrite_env, case_name, config_mutator, org, expected_result):
    target = filewrite_env / 'out.log'
    target.write_bytes(b'abc')
    config = config_mutator(filewrite_env, config_for(filewrite_env))
    handler, _ = make_handler(config, org=org)

    resp = handler.handle()

    assert_success_response(resp)
    assert resp['data']['_result'] == expected_result
    if case_name != 'success':
        assert resp['data']['_result'] == 'exception'


def test_size_limit_is_checked_before_truncating_file(filewrite_env):
    target = filewrite_env / 'out.log'
    original = b'12345678\n\n'
    target.write_bytes(original)

    resp, _ = run_filewrite(filewrite_env, max_file_bytes=5)

    assert_success_response(resp)
    assert resp['data']['_error_kind'] == 'file_too_large'
    assert target.read_bytes() == original


@pytest.mark.parametrize('overrides', [
    {'result_var': None},
    {'result_var': ''},
    {'result_var': '../x'},
    {'base_dir': ''},
    {'file_path': ''},
])
def test_bad_required_config_values_are_rejected(filewrite_env, overrides):
    config = config_for(filewrite_env)
    config.update(overrides)
    handler, _ = make_handler(config)

    resp = handler.handle()

    assert_success_response(resp)
    assert resp['data']['_error_kind'] == 'bad_config'


def test_missing_content_key_is_rejected(filewrite_env):
    config = config_for(filewrite_env)
    del config['content']
    handler, _ = make_handler(config)

    resp = handler.handle()

    assert_success_response(resp)
    assert resp['data']['_error_kind'] == 'bad_config'


def test_skip_advance_when_no_outgoing_edges(filewrite_env):
    handler, _ = make_handler(config_for(filewrite_env), has_edges=False)

    resp = handler.handle()

    assert_success_response(resp)
    assert resp['data']['skip_advance'] is True
    assert resp['data']['skip_advance_reason'] == 'filewrite_no_outgoing'


def test_skip_advance_when_stop_after_is_enabled(filewrite_env):
    handler, _ = make_handler(config_for(filewrite_env, stop_after=True), has_edges=True)

    resp = handler.handle()

    assert_success_response(resp)
    assert resp['data']['skip_advance'] is True
    assert resp['data']['skip_advance_reason'] == 'filewrite_stop_after'


def test_replaces_variables_in_file_path_and_content(filewrite_env):
    def replace(text, **kw):
        del kw
        return text.replace('${v.fname}', 'var.log').replace('${v.val}', '42')

    config = config_for(
        filewrite_env,
        file_path='${v.fname}',
        content='V=${v.val}',
        newline_after=False,
    )
    handler, _ = make_handler(config, replace=replace)

    resp = handler.handle()

    assert_success_response(resp)
    assert (filewrite_env / 'var.log').read_bytes() == b'V=42'


def test_lock_timeout_returns_timeout_without_modifying_file(filewrite_env):
    target = filewrite_env / 'out.log'
    original = b'abc'
    target.write_bytes(original)

    with target.open('rb') as locked_file:
        fcntl.flock(locked_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        resp, flow_vars = run_filewrite(filewrite_env, lock_timeout_ms=200)
        fcntl.flock(locked_file.fileno(), fcntl.LOCK_UN)

    assert_success_response(resp)
    assert resp['data']['_result'] == 'timeout'
    assert resp['data']['_error_kind'] == 'lock_timeout'
    assert flow_vars['fw_result'] == 'timeout'
    assert target.read_bytes() == original
