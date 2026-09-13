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
