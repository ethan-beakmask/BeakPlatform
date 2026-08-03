"""Site Map portal access_matrix validation tests."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from modules.nocode_builder.api.site_map_api import _validate_access_matrix


def test_validate_access_matrix_accepts_required_permissions_default_any():
    ok, err = _validate_access_matrix({
        "read": {
            "required_permissions": ["bulletin.read"],
        },
    })

    assert ok is True
    assert err == ""


def test_validate_access_matrix_accepts_required_permissions_all():
    ok, err = _validate_access_matrix({
        "read": {
            "required_permissions": ["bulletin.read", "bulletin.create"],
            "match_mode": "all",
        },
    })

    assert ok is True
    assert err == ""


def test_validate_access_matrix_accepts_null_clear():
    ok, err = _validate_access_matrix(None)

    assert ok is True
    assert err == ""


def test_validate_access_matrix_rejects_empty_required_permissions():
    ok, err = _validate_access_matrix({
        "read": {
            "required_permissions": [],
        },
    })

    assert ok is False
    assert err


def test_validate_access_matrix_rejects_uppercase_permission_code():
    ok, err = _validate_access_matrix({
        "read": {
            "required_permissions": ["Bulletin.Read"],
        },
    })

    assert ok is False
    assert err


def test_validate_access_matrix_rejects_missing_required_permissions():
    ok, err = _validate_access_matrix({
        "read": {
            "match_mode": "any",
        },
    })

    assert ok is False
    assert err


def test_validate_access_matrix_rejects_extra_top_level_key():
    ok, err = _validate_access_matrix({
        "read": {
            "required_permissions": ["bulletin.read"],
        },
        "write": {
            "required_permissions": ["bulletin.create"],
        },
    })

    assert ok is False
    assert err


def test_validate_access_matrix_rejects_non_dict():
    ok, err = _validate_access_matrix(["GENERAL"])

    assert ok is False
    assert err
