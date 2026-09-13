import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app import db
from app.models import FwDemoInventory
from modules.form_workflow.models import FwCategory
from scripts.examples.node_showcase import SHOWCASE_ITEMS, ensure_showcase_category


def test_ensure_showcase_category_is_idempotent(app, test_org):
    first = ensure_showcase_category(test_org)
    db.session.flush()
    second = ensure_showcase_category(test_org)
    db.session.flush()

    assert first.secure_code == second.secure_code
    assert FwCategory.query.filter_by(
        org_secure_code=test_org.secure_code,
        name='node展覽館',
        is_deleted=False,
    ).count() == 1
    assert second.show_in_form_design is True
    assert second.show_in_workflow_design is True
    assert second.show_in_form_center is True


def test_showcase_items_are_importable_and_expose_provision(app):
    assert SHOWCASE_ITEMS
    for _name, module_name, _opts in SHOWCASE_ITEMS:
        module = importlib.import_module(module_name)
        assert callable(getattr(module, 'provision', None)), module_name


def test_fw_demo_inventory_model_can_create_and_query(app, test_org):
    row = FwDemoInventory(
        org_secure_code=test_org.secure_code,
        item_code='TEST-NODE-SHOWCASE-001',
        item_name='Node Showcase Test Item',
        qty_on_hand=10,
        safety_qty=5,
        unit='PCS',
    )
    db.session.add(row)
    db.session.commit()

    found = FwDemoInventory.query.filter_by(
        org_secure_code=test_org.secure_code,
        item_code='TEST-NODE-SHOWCASE-001',
        is_deleted=False,
    ).first()
    assert found is not None
    assert found.item_name == 'Node Showcase Test Item'
