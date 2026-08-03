"""Page IR v3 layout engine validation and rendering tests."""
from __future__ import annotations
import os
import sys
from pathlib import Path
import pytest
from flask import Flask
os.environ.setdefault("SYSTEM_ORG_CODE", "system.local")
os.environ.setdefault("SECRET_KEY", "test-secret")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.pageir import render_page_ir_full, validate_page_ir
from app.pageir.context import clear_render_context, set_render_context
@pytest.fixture
def pir_app():
    app = Flask(__name__, template_folder="../app/templates")
    app.secret_key = "test-secret"
    app.jinja_env.globals["_"] = lambda text, **kwargs: text % kwargs if kwargs else text
    app.jinja_env.globals["egress_visibility"] = lambda resource, context, field: "clear"
    app.jinja_env.globals["egress_value"] = lambda resource, context, record_sc, field, value: value
    app.jinja_env.filters["tz_format"] = lambda value, fmt="%Y-%m-%d %H:%M": "DATE"
    return app
@pytest.fixture(autouse=True)
def reset_context():
    yield
    clear_render_context()
def t(i, c=None):
    return {"id": i, "type": "text", "level": "h2", "content_i18n": {"zh-TW": c or i}}
def layout():
    return {"id": "layout-one", "type": "layout", "columns": 2, "gap": 8, "children": [t("child-one", "Child One")]}
def doc(widgets, **kw):
    page = {"id": "engine-page", "title_i18n": {"zh-TW": "Engine"}, "widgets": widgets}
    page.update(kw)
    return {"ir_version": 3, "page": page}
def z(i, ids, **kw):
    item = {"id": i, "row": 1, "col": 1, "row_span": 1, "col_span": 1, "widget_ids": ids}
    item.update(kw)
    return item
def gcan(*zones, **kw):
    canvas = {"min_width": 1280, "col_widths": [1, 2, 1], "row_heights": [120, 240], "gap": 8, "zones": list(zones)}
    canvas.update(kw)
    return canvas
def f(i, ids, **kw):
    item = {"id": i, "x": 0, "y": 0, "w": 6, "h": 4, "widget_ids": ids}
    item.update(kw)
    return item
def fcan(*frames, **kw):
    canvas = {"min_width": 1280, "row_unit": 60, "columns": 12, "gap": 8, "frames": list(frames)}
    canvas.update(kw)
    return canvas
def codes(errors):
    return {error["code"] for error in errors}
def test_missing_engine_renders_flow_branch_with_responsive_classes(pir_app):
    d = doc([layout()])
    ok, errors = validate_page_ir(d)
    assert ok, errors
    with pir_app.test_request_context("/"):
        set_render_context("platform")
        rendered = render_page_ir_full(d)
    assert rendered["engine"] == "flow"
    assert "pir-canvas" not in rendered["html"]
    assert "pir-layout--responsive" in rendered["html"]
def test_flow_engine_with_canvas_fails_validation():
    ok, errors = validate_page_ir(doc([t("text-one")], engine="flow", canvas={}))
    assert not ok
    assert "not" in codes(errors)
def test_grid_engine_missing_canvas_fails_validation():
    ok, errors = validate_page_ir(doc([t("text-one")], engine="grid"))
    assert not ok
    assert "required" in codes(errors)
def test_grid_zone_overlap():
    d = doc([t("text-one"), t("text-two")], engine="grid", canvas=gcan(z("zone-one", ["text-one"], col_span=2), z("zone-two", ["text-two"], col=2)))
    ok, errors = validate_page_ir(d)
    assert not ok
    assert "zone_overlap" in codes(errors)
def test_grid_zone_out_of_range():
    d = doc([t("text-one")], engine="grid", canvas=gcan(z("zone-one", ["text-one"], col=3, col_span=2)))
    ok, errors = validate_page_ir(d)
    assert not ok
    assert "zone_out_of_range" in codes(errors)
def test_free_frame_out_of_range():
    d = doc([t("text-one")], engine="free", canvas=fcan(f("frame-one", ["text-one"], x=8, w=5)))
    ok, errors = validate_page_ir(d)
    assert not ok
    assert "frame_out_of_range" in codes(errors)
def test_canvas_dangling_widget_ref():
    d = doc([t("text-one")], engine="grid", canvas=gcan(z("zone-one", ["missing-one"])))
    ok, errors = validate_page_ir(d)
    assert not ok
    assert "dangling_widget_ref" in codes(errors)
def test_canvas_nested_widget_ref():
    d = doc([layout()], engine="grid", canvas=gcan(z("zone-one", ["child-one"])))
    ok, errors = validate_page_ir(d)
    assert not ok
    assert "nested_widget_ref" in codes(errors)
def test_canvas_duplicate_widget_ref():
    d = doc([t("text-one")], engine="grid", canvas=gcan(z("zone-one", ["text-one"]), z("zone-two", ["text-one"], col=2)))
    ok, errors = validate_page_ir(d)
    assert not ok
    assert "duplicate_widget_ref" in codes(errors)
def test_zone_id_collides_with_widget_id():
    d = doc([t("text-one")], engine="grid", canvas=gcan(z("text-one", ["text-one"])))
    ok, errors = validate_page_ir(d)
    assert not ok
    assert "unique_id" in codes(errors)
def test_unreferenced_top_level_widget_validates_but_is_not_rendered(pir_app):
    d = doc([t("text-one", "Placed Widget"), t("text-two", "Unused Widget")], engine="grid", canvas=gcan(z("zone-one", ["text-one"])))
    ok, errors = validate_page_ir(d)
    assert ok, errors
    with pir_app.test_request_context("/"):
        set_render_context("platform")
        rendered = render_page_ir_full(d)
    assert "Placed Widget" in rendered["html"]
    assert "Unused Widget" not in rendered["html"]
@pytest.mark.parametrize("engine", ["grid", "free"])
def test_grid_and_free_render_canvas_styles(pir_app, engine):
    if engine == "grid":
        canvas = gcan(z("zone-one", ["text-one"], row=2, col=2, row_span=1, col_span=2))
        expected = ["min-width: 1280px", "grid-template-columns: 1fr 2fr 1fr", "grid-area: 2 / 2 / span 1 / span 2"]
    else:
        canvas = fcan(f("frame-one", ["text-one"], x=2, y=3, w=4, h=5))
        expected = ["min-width: 1280px", "grid-auto-rows: 60px", "grid-column: 3 / span 4", "grid-row: 4 / span 5"]
    d = doc([t("text-one")], engine=engine, canvas=canvas)
    with pir_app.test_request_context("/"):
        set_render_context("platform")
        rendered = render_page_ir_full(d)
    assert rendered["engine"] == engine
    for marker in expected:
        assert marker in rendered["html"]
    assert "pir-layout--responsive" not in rendered["html"]
def test_canvas_numeric_bounds_rejected_by_schema():
    d = doc([t("text-one")], engine="grid", canvas=gcan(z("zone-one", ["text-one"]), min_width=99999))
    ok, errors = validate_page_ir(d)
    assert not ok
    assert "maximum" in codes(errors)
