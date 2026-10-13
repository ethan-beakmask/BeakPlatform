"""出廠縮圖包：覆蓋率與套用行為。

縮圖包在 scripts/examples/thumbnails/，由 build_showcase_thumbnails.py 產生。
新增 node展覽館示範而沒補縮圖時第一個測試會紅——這是刻意的：
全新安裝的清單頁只有從縮圖包拿得到縮圖。
"""
import os
import sys
from types import SimpleNamespace

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from app import db  # noqa: E402
from app.defaults import api_key_request_defaults, proxy_request_defaults  # noqa: E402
from app.defaults.thumbnail_defaults import fill_template_thumbnails, pack_thumbnail  # noqa: E402
from app.models import Organization  # noqa: E402
from modules.form_workflow.models import FwFormTemplate, FwWorkflowTemplate  # noqa: E402
from scripts.examples.node_showcase import SHOWCASE_ITEMS, _demo_codes_for_module  # noqa: E402
from scripts.examples.thumbnail_pack import (  # noqa: E402
    apply_thumbnail_pack,
    list_pack_codes,
    load_data_uri,
    pack_file,
)

PNG_PREFIX = 'data:image/png;base64,'


def _expected_codes():
    forms = set()
    workflows = set()
    for _name, module_name, _defaults, _metadata in SHOWCASE_ITEMS:
        demo_forms, demo_workflows = _demo_codes_for_module(module_name)
        forms.update(demo_forms)
        workflows.update(demo_workflows)
    forms.update({api_key_request_defaults.FORM_CODE, proxy_request_defaults.FORM_CODE})
    workflows.update({api_key_request_defaults.WORKFLOW_CODE, proxy_request_defaults.WORKFLOW_CODE})
    return forms, workflows


def test_pack_covers_every_seeded_form_and_workflow():
    forms, workflows = _expected_codes()
    assert forms and workflows
    missing = [f'form:{code}' for code in sorted(forms) if not pack_file('form', code).is_file()]
    missing += [f'workflow:{code}' for code in sorted(workflows) if not pack_file('workflow', code).is_file()]
    assert not missing, '缺縮圖檔（跑 scripts/examples/build_showcase_thumbnails.py 補）：' + ', '.join(missing)


def test_pack_files_are_png_and_not_empty():
    for kind in ('form', 'workflow'):
        codes = list_pack_codes(kind)
        assert codes
        for code in codes:
            data = pack_file(kind, code).read_bytes()
            assert data.startswith(b'\x89PNG\r\n\x1a\n'), f'{kind}:{code} 不是 PNG'
            uri = load_data_uri(kind, code)
            assert uri and uri.startswith(PNG_PREFIX)


def test_load_data_uri_rejects_unknown_or_unsafe_code():
    assert load_data_uri('form', 'NO_SUCH_TEMPLATE_CODE') is None
    assert load_data_uri('form', '../thumbnail_pack') is None
    assert load_data_uri('form', '') is None


def _org(secure_code, code, domain):
    org = Organization(
        secure_code=secure_code, code=code, name=code, domain_name=domain,
        is_active=True, is_deleted=False, is_system_org=False,
    )
    db.session.add(org)
    db.session.flush()
    return org


def test_apply_thumbnail_pack_fills_templates_by_code(app):
    org = _org('thumb_org_sc', 'THUMBORG', 'thumb.local')
    form = FwFormTemplate(
        org_secure_code=org.secure_code, code='NODEDEMO_NT22_OPSET_FORM', name='f',
        schema={'components': []}, is_deleted=False,
    )
    wf = FwWorkflowTemplate(
        org_secure_code=org.secure_code, code='NODEDEMO_NT22_OPSET_FLOW', name='w',
        graph={'nodes': [], 'edges': []}, is_deleted=False, thumbnail_2x1='data:image/png;base64,OLD',
    )
    other = FwWorkflowTemplate(
        org_secure_code='someone_else', code='NODEDEMO_NT22_OPSET_FLOW', name='w2',
        graph={'nodes': [], 'edges': []}, is_deleted=False,
    )
    db.session.add_all([form, wf, other])
    db.session.flush()

    summary = apply_thumbnail_pack(
        org.secure_code,
        form_codes=['NODEDEMO_NT22_OPSET_FORM', 'NOT_IN_PACK'],
        workflow_codes=['NODEDEMO_NT22_OPSET_FLOW', 'NODEDEMO_NT01_START_FLOW'],
        overwrite=False,
    )
    assert summary['forms'] == 1
    assert summary['workflows'] == 0 and summary['kept'] == 1  # 已有縮圖且 overwrite=False
    assert summary['missing'] == ['form:NOT_IN_PACK']
    assert summary['absent'] == ['workflow:NODEDEMO_NT01_START_FLOW']
    assert form.thumbnail_2x1.startswith(PNG_PREFIX)
    assert wf.thumbnail_2x1 == 'data:image/png;base64,OLD'
    assert other.thumbnail_2x1 is None  # 不跨企業

    summary = apply_thumbnail_pack(org.secure_code, workflow_codes=['NODEDEMO_NT22_OPSET_FLOW'], form_codes=[])
    assert summary['workflows'] == 1
    assert wf.thumbnail_2x1.startswith(PNG_PREFIX) and wf.thumbnail_2x1 != 'data:image/png;base64,OLD'


def test_fill_template_thumbnails_only_fills_empty_unless_overwrite():
    form = SimpleNamespace(code=api_key_request_defaults.FORM_CODE, thumbnail_2x1=None)
    wf = SimpleNamespace(code=api_key_request_defaults.WORKFLOW_CODE, thumbnail_2x1='keep')
    applied = fill_template_thumbnails(form, wf)
    assert applied == {'form': True, 'workflow': False}
    assert form.thumbnail_2x1.startswith(PNG_PREFIX)
    assert wf.thumbnail_2x1 == 'keep'

    applied = fill_template_thumbnails(None, wf, overwrite=True)
    assert applied == {'form': False, 'workflow': True}
    assert wf.thumbnail_2x1.startswith(PNG_PREFIX)

    assert pack_thumbnail('workflow', 'NO_SUCH_CODE') is None


def test_seed_proxy_request_flow_gets_pack_thumbnails(test_org):
    proxy_request_defaults.seed_org_proxy_request_flow(test_org.secure_code)
    db.session.commit()
    form = FwFormTemplate.query.filter_by(
        org_secure_code=test_org.secure_code, code=proxy_request_defaults.FORM_CODE, is_deleted=False).first()
    wf = FwWorkflowTemplate.query.filter_by(
        org_secure_code=test_org.secure_code, code=proxy_request_defaults.WORKFLOW_CODE, is_deleted=False).first()
    assert form and form.thumbnail_2x1 and form.thumbnail_2x1.startswith(PNG_PREFIX)
    assert wf and wf.thumbnail_2x1 and wf.thumbnail_2x1.startswith(PNG_PREFIX)
