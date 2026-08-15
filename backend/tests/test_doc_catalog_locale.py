from types import SimpleNamespace

import pytest
from flask import g

from app.services import doc_catalog_service


@pytest.fixture
def manual_dir(app, tmp_path, monkeypatch):
    base = tmp_path / "manual"
    base.mkdir()
    app.config["MANUAL_DOC_DIR"] = str(base)
    doc_catalog_service._CACHE["signature"] = None
    doc_catalog_service._CACHE["catalog"] = None
    monkeypatch.setattr(
        doc_catalog_service,
        "visible_menu_codes",
        lambda _user: {"allowed.menu"},
    )
    yield base
    doc_catalog_service._CACHE["signature"] = None
    doc_catalog_service._CACHE["catalog"] = None


@pytest.fixture
def user():
    return SimpleNamespace(user_type="EMPLOYEE", secure_code="user_sc")


def _write_doc(path, title, body, **meta):
    lines = ["---", f"title: {title}"]
    for key, value in meta.items():
        if isinstance(value, bool):
            value = "true" if value else "false"
        lines.append(f"{key}: {value}")
    lines.extend(["---", "", body])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_fixture_docs(base, *, include_en=True, orphan=False, variant_nav=None):
    chapter = base / "01_getting_started"
    _write_doc(
        chapter / "index.md",
        "開始使用",
        "中文章總覽",
        audience="ALL",
        chapter_order=1,
        chapter_index=True,
    )
    if include_en:
        _write_doc(
            chapter / "index.en.md",
            "Getting Started",
            "English chapter overview",
            audience="EXTERNAL",
            chapter_order=99,
            chapter_index=True,
        )
    _write_doc(
        chapter / "login.md",
        "登入",
        "中文內容",
        nav_menu="allowed.menu",
        order=10,
    )
    if include_en:
        variant_meta = {"nav_menu": variant_nav or "allowed.menu", "order": 999}
        _write_doc(
            chapter / "login.en.md",
            "Login",
            "English body",
            **variant_meta,
        )
    if orphan:
        _write_doc(chapter / "orphan.en.md", "Orphan", "Orphan body")


def test_get_manual_doc_uses_english_variant(app, manual_dir, user):
    _write_fixture_docs(manual_dir)

    with app.test_request_context("/"):
        g.locale = "en"
        doc = doc_catalog_service.get_manual_doc(
            "manual/01_getting_started/login",
            user,
        )

    assert doc["title"] == "Login"
    assert "English body" in doc["html"]
    assert "中文內容" not in doc["html"]
    assert doc["locale_fallback"] is False


def test_get_manual_doc_falls_back_to_zh_tw_for_missing_variant(app, manual_dir, user):
    _write_fixture_docs(manual_dir, include_en=False)

    with app.test_request_context("/"):
        g.locale = "en"
        doc = doc_catalog_service.get_manual_doc(
            "manual/01_getting_started/login",
            user,
        )

    assert doc["title"] == "登入"
    assert "中文內容" in doc["html"]
    assert doc["locale_fallback"] is True


def test_zh_tw_or_missing_locale_uses_main_doc_without_fallback(app, manual_dir, user):
    _write_fixture_docs(manual_dir)

    with app.test_request_context("/"):
        g.locale = "zh-TW"
        zh_doc = doc_catalog_service.get_manual_doc(
            "manual/01_getting_started/login",
            user,
        )

    with app.app_context():
        default_doc = doc_catalog_service.get_manual_doc(
            "manual/01_getting_started/login",
            user,
        )

    assert "中文內容" in zh_doc["html"]
    assert zh_doc["locale_fallback"] is False
    assert "中文內容" in default_doc["html"]
    assert default_doc["locale_fallback"] is False


def test_variant_frontmatter_does_not_change_visibility(app, manual_dir, user):
    _write_fixture_docs(manual_dir, variant_nav="denied.menu")

    with app.test_request_context("/"):
        g.locale = "en"
        doc = doc_catalog_service.get_manual_doc(
            "manual/01_getting_started/login",
            user,
        )

    assert doc is not None
    assert doc["title"] == "Login"
    assert "English body" in doc["html"]


def test_orphan_variant_is_ignored(app, manual_dir):
    _write_fixture_docs(manual_dir, orphan=True)

    with app.app_context():
        catalog = doc_catalog_service._load_catalog()
        exists = doc_catalog_service.doc_exists("manual/01_getting_started/orphan")

    assert "manual/01_getting_started/orphan" not in catalog["docs"]
    assert exists is False


def test_list_manual_uses_localized_titles(app, manual_dir, user):
    _write_fixture_docs(manual_dir)

    with app.test_request_context("/"):
        g.locale = "en"
        chapters = doc_catalog_service.list_manual(user)

    assert chapters[0]["title"] == "Getting Started"
    assert chapters[0]["entries"][0]["title"] == "Login"


def test_doc_exists_returns_true_and_false(app, manual_dir):
    _write_fixture_docs(manual_dir)

    with app.app_context():
        assert doc_catalog_service.doc_exists("manual/01_getting_started/login") is True
        assert doc_catalog_service.doc_exists("manual/01_getting_started/missing") is False
        assert doc_catalog_service.doc_exists(None) is False
