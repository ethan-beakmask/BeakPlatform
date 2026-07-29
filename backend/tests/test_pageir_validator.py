"""Page IR v3 驗證器單元測試。"""
from __future__ import annotations

from copy import deepcopy

from app.pageir import validate_page_ir


def valid_doc():
    return {
        "ir_version": 3,
        "page": {
            "id": "sample-page",
            "title_i18n": {"zh-TW": "範例頁面", "en": "Sample Page"},
            "widgets": [
                {
                    "id": "main-layout",
                    "type": "layout",
                    "columns": 2,
                    "gap": 16,
                    "children": [
                        {
                            "id": "page-title",
                            "type": "text",
                            "level": "h1",
                            "content_i18n": {"zh-TW": "範例"},
                        },
                        {
                            "id": "inner-layout",
                            "type": "layout",
                            "columns": 1,
                            "children": [
                                {
                                    "id": "sample-detail",
                                    "type": "detail",
                                    "binding": {
                                        "resource": "guest",
                                        "view": "detail",
                                        "fields": ["name", "email"],
                                    },
                                    "layout_columns": 2,
                                    "fields": [
                                        {"field": "name", "label_i18n": {"zh-TW": "姓名"}},
                                        {"field": "email", "label_i18n": {"zh-TW": "信箱"}},
                                    ],
                                }
                            ],
                        },
                    ],
                },
                {
                    "id": "guest-table",
                    "type": "table",
                    "binding": {
                        "resource": "guest",
                        "view": "list",
                        "fields": ["name", "email", "created_at"],
                    },
                    "columns": [
                        {
                            "field": "name",
                            "label_i18n": {"zh-TW": "姓名"},
                            "sortable": True,
                        },
                        {"field": "email", "label_i18n": {"zh-TW": "信箱"}},
                    ],
                    "page_size": 20,
                    "default_sort": {"field": "created_at", "dir": "desc"},
                    "row_actions_ref": "row-actions",
                },
                {
                    "id": "guest-form",
                    "type": "form",
                    "formio_schema": {
                        "components": [
                            {"key": "name", "type": "textfield", "label": "Name"}
                        ]
                    },
                    "submit_action_ref": "form-actions",
                },
                {
                    "id": "row-actions",
                    "type": "actions",
                    "buttons": [
                        {
                            "id": "approve-button",
                            "label_i18n": {"zh-TW": "核准"},
                            "style": "primary",
                            "permission": "guest.approve",
                            "action_ref": "guest.approve",
                        }
                    ],
                },
                {
                    "id": "form-actions",
                    "type": "actions",
                    "buttons": [
                        {
                            "id": "submit-button",
                            "label_i18n": {"zh-TW": "送出"},
                            "style": "secondary",
                            "permission": "guest.submit",
                            "action_ref": "guest.submit",
                        }
                    ],
                },
            ],
        },
    }


def error_codes(doc):
    ok, errors = validate_page_ir(doc)
    assert not ok
    return {error["code"] for error in errors}


def test_valid_complete_document():
    ok, errors = validate_page_ir(valid_doc())

    assert ok is True
    assert errors == []


def test_schema_accepts_table_row_link_ref():
    doc = valid_doc()
    doc["page"]["widgets"][1]["row_link_ref"] = "sample-detail"

    ok, errors = validate_page_ir(doc)

    assert ok is True
    assert errors == []


def test_legacy_v2_is_rejected():
    ok, errors = validate_page_ir({"version": 2, "widgets": []})

    assert ok is False
    assert errors == [
        {
            "path": "",
            "message": "Page IR v2 is deprecated; rebuild the page as Page IR v3",
            "code": "legacy_v2",
        }
    ]


def test_unknown_widget_type_is_rejected():
    doc = valid_doc()
    doc["page"]["widgets"][0]["type"] = "chart"

    assert "oneOf" in error_codes(doc)


def test_additional_properties_are_rejected():
    doc = valid_doc()
    doc["page"]["widgets"][1]["sql"] = "select * from guests"
    doc["page"]["widgets"][1]["binding"]["where"] = "id = 1"

    assert "additionalProperties" in error_codes(doc)


def test_uppercase_random_style_id_is_rejected():
    doc = valid_doc()
    doc["page"]["widgets"][1]["id"] = "Widget_1"

    assert "pattern" in error_codes(doc)


def test_duplicate_widget_and_button_id_is_rejected():
    doc = valid_doc()
    doc["page"]["widgets"][4]["buttons"][0]["id"] = "guest-table"

    assert "unique_id" in error_codes(doc)


def test_layout_nesting_depth_five_is_rejected():
    doc = valid_doc()
    nested = {
        "id": "level-one",
        "type": "layout",
        "columns": 1,
        "children": [],
    }
    current = nested
    for index in range(2, 6):
        child = {
            "id": f"level-{index}",
            "type": "layout",
            "columns": 1,
            "children": [],
        }
        current["children"].append(child)
        current = child
    doc["page"]["widgets"] = [nested]

    assert "nesting_depth" in error_codes(doc)


def test_table_column_field_must_be_in_binding_fields():
    doc = valid_doc()
    doc["page"]["widgets"][1]["columns"][0]["field"] = "phone"

    assert "field_not_in_binding" in error_codes(doc)


def test_row_actions_ref_must_point_to_actions_widget():
    missing_doc = valid_doc()
    missing_doc["page"]["widgets"][1]["row_actions_ref"] = "missing-actions"

    non_actions_doc = deepcopy(valid_doc())
    non_actions_doc["page"]["widgets"][1]["row_actions_ref"] = "guest-form"

    assert "dangling_ref" in error_codes(missing_doc)
    assert "dangling_ref" in error_codes(non_actions_doc)


def test_actions_button_requires_permission():
    doc = valid_doc()
    del doc["page"]["widgets"][3]["buttons"][0]["permission"]

    assert "required" in error_codes(doc)
