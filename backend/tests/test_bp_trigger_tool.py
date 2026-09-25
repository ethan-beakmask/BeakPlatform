import base64
import importlib.util
from pathlib import Path

from app.security.hmac_verifier import compute_signature


SCRIPT_PATH = Path(__file__).resolve().parents[2] / 'scripts' / 'bp_trigger.py'


def load_tool():
    spec = importlib.util.spec_from_file_location('bp_trigger_tool', SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_decode_secret_accepts_unpadded_base64url():
    tool = load_tool()
    raw = b'0123456789abcdef0123456789abcdef'
    encoded = base64.urlsafe_b64encode(raw).decode('ascii').rstrip('=')

    assert tool.decode_secret(encoded) == raw


def test_signature_matches_platform_hmac_verifier():
    tool = load_tool()
    secret = b'0123456789abcdef0123456789abcdef'
    timestamp = '1800000000'
    body = b'{"subject":"hello","form_data":{"a":"b"}}'

    assert tool.compute_request_signature(secret, timestamp, body) == compute_signature(secret, timestamp, body)


def test_form_code_prints_merged_result(monkeypatch, capsys):
    tool = load_tool()

    def fake_call_platform(base, key_id, secret, method, path, body=None, bad_signature=False):
        return 200, {
            'success': True,
            'merged': True,
            'data': {
                'merged_into': {
                    'execution_code': 'PROC-20260925-0001',
                    'od_event_count': 2,
                },
            },
        }

    monkeypatch.setattr(tool, 'call_platform', fake_call_platform)
    rc = tool.main([
        '--base', 'http://example.test/beakplatform',
        '--key-id', 'ak_test',
        '--secret', base64.urlsafe_b64encode(b'0123456789abcdef0123456789abcdef').decode('ascii'),
        '--form-code', 'SEC_INCIDENT_RESPONSE',
        '--subject', 'test',
        '--group-key', 'case-1',
    ])

    out = capsys.readouterr().out
    assert rc == 0
    assert '事件已併入既有案件 PROC-20260925-0001（累計 2 筆）' in out
