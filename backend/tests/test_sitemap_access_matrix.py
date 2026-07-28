"""Site Map portal access_matrix validation tests."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from modules.nocode_builder.api.site_map_api import _validate_access_matrix


def test_validate_access_matrix_accepts_group_unlimited():
    ok, err = _validate_access_matrix({
        "read": {
            "groups": None,
            "min_level": "GUEST",
        },
    })

    assert ok is True
    assert err == ""


def test_validate_access_matrix_accepts_group_list():
    ok, err = _validate_access_matrix({
        "read": {
            "groups": ["GENERAL", "VIP_GROUP"],
            "min_level": "MEMBER",
        },
    })

    assert ok is True
    assert err == ""


def test_validate_access_matrix_accepts_null_clear():
    ok, err = _validate_access_matrix(None)

    assert ok is True
    assert err == ""


def test_validate_access_matrix_rejects_empty_groups():
    ok, err = _validate_access_matrix({
        "read": {
            "groups": [],
            "min_level": "MEMBER",
        },
    })

    assert ok is False
    assert err


def test_validate_access_matrix_rejects_lowercase_code():
    ok, err = _validate_access_matrix({
        "read": {
            "groups": ["general"],
            "min_level": "MEMBER",
        },
    })

    assert ok is False
    assert err


def test_validate_access_matrix_rejects_missing_min_level():
    ok, err = _validate_access_matrix({
        "read": {
            "groups": None,
        },
    })

    assert ok is False
    assert err


def test_validate_access_matrix_rejects_extra_top_level_key():
    ok, err = _validate_access_matrix({
        "read": {
            "groups": None,
            "min_level": "MEMBER",
        },
        "write": {
            "groups": None,
            "min_level": "ADMIN",
        },
    })

    assert ok is False
    assert err


def test_validate_access_matrix_rejects_non_dict():
    ok, err = _validate_access_matrix(["GENERAL"])

    assert ok is False
    assert err
