"""FwApprovalRecord acted_as_role_code 欄位。"""
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app import db  # noqa: E402
from modules.form_workflow.models import FwApprovalRecord  # noqa: E402


def _record(test_org, suffix, acted_as_role_code=None):
    row = FwApprovalRecord(
        secure_code=f'acted_as_{suffix}',
        org_secure_code=test_org.secure_code,
        form_instance_secure_code=f'fi_{suffix}',
        workflow_instance_secure_code=f'wi_{suffix}',
        node_id='n_approve',
        node_name='主管核可',
        node_queue_secure_code=f'q_{suffix}',
        approver_secure_code=f'u_{suffix}',
        approver_name='Approver',
        action='approved',
        comment='ok',
        acted_at=datetime.utcnow(),
        acted_as_role_code=acted_as_role_code,
    )
    db.session.add(row)
    db.session.commit()
    return row


def test_approval_record_to_dict_includes_acted_as_role_code(test_org):
    assert _record(test_org, 'deputy', 'DEPT_DEPUTY').to_dict()['acted_as_role_code'] == 'DEPT_DEPUTY'
    assert _record(test_org, 'none').to_dict()['acted_as_role_code'] is None
