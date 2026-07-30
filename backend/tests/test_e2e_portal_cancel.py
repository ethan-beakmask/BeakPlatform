"""Portal cancel e2e test.

This test talks to the locally running BeakPlatform service over HTTP and
asserts PostgreSQL side effects directly. Run it alone with:

    ../venv/bin/python -m pytest tests/test_e2e_portal_cancel.py -q -m e2e
"""
from __future__ import annotations

import contextlib
import re
import secrets
import time

import psycopg2
import pytest
import requests


pytestmark = pytest.mark.e2e

BASE_URL = "http://192.168.0.16:7000/beakplatform"
PORTAL_URL = f"{BASE_URL}/public/portal/ubwdM7Tp"
PAGE_SC = "FORMTEST00000000000001"
FORM_WIDGET_ID = "form-1"
ACTIONS_WIDGET_ID = "acts-1"
SUBMISSIONS_WIDGET_ID = "subs-1"
PORTAL_USERNAME = "p4tester"
PORTAL_PASSWORD = "p4test123"
# p4tester 在該子系統 portal.db 的 portal_users.id = 1；
# 若 portal.db 帳號被重建，這個值要跟著改（斷言失敗會直接指向這裡）。
EXPECTED_USER_REF = "u:1"
EXPECTED_SUB_SYSTEM_SC = "8uopl3mNbDzGDUGAcNQqNe"
ORG_SC = "_9c8TewkRkCBEf3XsUdqeF"
DB_CONFIG = {
    "host": "localhost",
    "dbname": "beakplatform_dev",
    "user": "beakplatform",
    "password": "postgres123",
}
ACTIVE_QUEUE_STATUSES = ("PENDING", "RUNNING", "WAITING")


@contextlib.contextmanager
def _connect():
    """psycopg2 的 `with conn` 只管交易不關連線，這裡補上關閉避免累積。"""
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def _find_widget(doc: dict, widget_id: str) -> dict | None:
    def walk(widgets):
        if not isinstance(widgets, list):
            return None
        for widget in widgets:
            if not isinstance(widget, dict):
                continue
            if widget.get("id") == widget_id:
                return widget
            found = walk(widget.get("children"))
            if found is not None:
                return found
        return None

    if not isinstance(doc, dict):
        return None
    return walk((doc.get("page") or {}).get("widgets"))


def _assert_acceptance_layout():
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT layout_json
            FROM dc_page_layouts
            WHERE secure_code = %s AND is_deleted = false
            """,
            (PAGE_SC,),
        )
        row = cur.fetchone()

    if row is None:
        pytest.skip("驗收頁配置已被改動：找不到 dc_page_layouts FORMTEST00000000000001")

    layout_json = row[0]
    actions = _find_widget(layout_json, ACTIONS_WIDGET_ID)
    submissions = _find_widget(layout_json, SUBMISSIONS_WIDGET_ID)
    if actions is None or submissions is None or submissions.get("row_actions_ref") != ACTIONS_WIDGET_ID:
        pytest.skip("驗收頁配置已被改動：acts-1 或 subs-1.row_actions_ref 不符合預期")


def _csrf_token(session: requests.Session) -> str:
    response = session.get(f"{PORTAL_URL}/p/{PAGE_SC}", timeout=10)
    assert response.status_code == 200, f"取 portal 頁失敗 status={response.status_code}"
    match = re.search(r'csrf-token" content="([^"]*)"', response.text)
    assert match, "取 portal CSRF token 失敗：頁面缺 csrf-token meta"
    return match.group(1)


def _new_e2e_secure_code() -> str:
    token = re.sub(r"[^A-Za-z0-9]", "", secrets.token_urlsafe(12))
    return f"E2E{token}"[:32]


def _fetch_workflow_pair(execution_code: str):
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT
              wi.secure_code AS wi_sc,
              fi.secure_code AS fi_sc,
              wi.nocode_user_ref,
              wi.nocode_sub_system_sc
            FROM fw_workflow_instances wi
            JOIN fw_form_instances fi ON fi.secure_code = wi.form_instance_secure_code
            WHERE wi.execution_code = %s
            """,
            (execution_code,),
        )
        return cur.fetchone()


def _insert_waiting_node(queue_sc: str, wi_sc: str, fi_sc: str):
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO fw_node_execution_queue (
              secure_code, org_secure_code, workflow_instance_secure_code,
              form_instance_secure_code, node_id, node_type, node_name, node_config,
              status, priority, scheduled_at, is_deleted, created_at, updated_at)
            VALUES (%s, %s, %s, %s, 'node-E2E-Approve', 'Approve', 'E2E 待辦節點',
                    '{}'::json, 'WAITING', 10, now(), false, now(), now())
            """,
            (queue_sc, ORG_SC, wi_sc, fi_sc),
        )


def _set_workflow_owner(wi_sc: str, owner_ref: str):
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE fw_workflow_instances SET nocode_user_ref = %s WHERE secure_code = %s",
            (owner_ref, wi_sc),
        )


def _wait_for_queue_settled(execution_code: str, wi_sc: str):
    for _ in range(40):
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT status
                FROM fw_workflow_instances
                WHERE secure_code = %s
                """,
                (wi_sc,),
            )
            wi_status = cur.fetchone()[0]
            cur.execute(
                """
                SELECT status, count(*)
                FROM fw_node_execution_queue
                WHERE workflow_instance_secure_code = %s AND is_deleted = false
                GROUP BY status
                """,
                (wi_sc,),
            )
            queue_counts = dict(cur.fetchall())
            active_count = sum(queue_counts.get(status, 0) for status in ACTIVE_QUEUE_STATUSES)
        if active_count == 0:
            return wi_status, queue_counts
        time.sleep(0.5)
    pytest.fail(
        f"撤單後 queue 未收斂 execution_code={execution_code} "
        f"wi_sc={wi_sc} queue_counts={queue_counts}"
    )


def _fetch_cancel_assertions(wi_sc: str, queue_sc: str):
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT status FROM fw_node_execution_queue WHERE secure_code = %s",
            (queue_sc,),
        )
        queue_row = cur.fetchone()
        cur.execute(
            """
            SELECT action, approver_name, comment
            FROM fw_approval_records
            WHERE workflow_instance_secure_code = %s
              AND node_id = 'FORCE_END'
              AND is_deleted = false
            """,
            (wi_sc,),
        )
        approval_rows = cur.fetchall()
    return queue_row, approval_rows


def _cleanup(wi_sc: str | None, fi_sc: str | None, serial_number: str | None):
    with _connect() as conn, conn.cursor() as cur:
        if wi_sc:
            cur.execute(
                "DELETE FROM fw_node_execution_queue WHERE workflow_instance_secure_code = %s",
                (wi_sc,),
            )
            cur.execute(
                "DELETE FROM fw_approval_records WHERE workflow_instance_secure_code = %s",
                (wi_sc,),
            )
            cur.execute(
                "DELETE FROM fw_workflow_variables WHERE workflow_instance_secure_code = %s",
                (wi_sc,),
            )
            cur.execute(
                "UPDATE fw_workflow_instances SET is_deleted = true WHERE secure_code = %s",
                (wi_sc,),
            )
        if fi_sc:
            cur.execute(
                "UPDATE fw_form_instances SET is_deleted = true WHERE secure_code = %s",
                (fi_sc,),
            )
        if serial_number:
            cur.execute(
                "UPDATE dc_sub_systems SET is_deleted = true WHERE provision_serial_number = %s",
                (serial_number,),
            )


def test_portal_cancel_submission_e2e():
    try:
        requests.get(BASE_URL, timeout=3)
    except requests.RequestException:
        pytest.skip("dev 服務未啟動")

    _assert_acceptance_layout()

    session = requests.Session()
    execution_code = None
    serial_number = None
    wi_sc = None
    fi_sc = None
    queue_sc = None

    try:
        login = session.post(
            f"{PORTAL_URL}/login",
            data={"username": PORTAL_USERNAME, "password": PORTAL_PASSWORD},
            timeout=10,
        )
        assert login.status_code < 400, f"portal 登入失敗 status={login.status_code}"

        csrf_token = _csrf_token(session)
        unique_text = f"E2E-{secrets.token_urlsafe(12)}"
        submit = session.post(
            f"{PORTAL_URL}/api/pages/{PAGE_SC}/widgets/{FORM_WIDGET_ID}/submit",
            json={"textField": unique_text},
            headers={"X-CSRFToken": csrf_token},
            timeout=20,
        )
        assert submit.status_code == 201, f"送件失敗 status={submit.status_code} body={submit.text[:500]}"
        submit_json = submit.json()
        execution_code = submit_json["data"]["execution_code"]
        serial_number = submit_json["data"]["serial_number"]

        pair = _fetch_workflow_pair(execution_code)
        assert pair is not None, f"送件後查不到 workflow execution_code={execution_code}"
        wi_sc, fi_sc, user_ref, sub_system_sc = pair
        assert user_ref == EXPECTED_USER_REF, f"portal 身分未帶入 execution_code={execution_code}"
        assert sub_system_sc == EXPECTED_SUB_SYSTEM_SC, (
            f"portal 子系統未帶入 execution_code={execution_code} sub_system={sub_system_sc}"
        )

        queue_sc = _new_e2e_secure_code()
        _insert_waiting_node(queue_sc, wi_sc, fi_sc)

        cancel_url = f"{PORTAL_URL}/api/pages/{PAGE_SC}/widgets/{ACTIONS_WIDGET_ID}/submissions/{fi_sc}/cancel"
        no_csrf = session.post(cancel_url, timeout=10)
        assert no_csrf.status_code == 400, (
            f"負向 A 缺 CSRF 應回 400 execution_code={execution_code} "
            f"status={no_csrf.status_code}"
        )

        _set_workflow_owner(wi_sc, "u:999")
        try:
            idor = session.post(cancel_url, headers={"X-CSRFToken": csrf_token}, timeout=10)
            assert idor.status_code == 404, (
                f"負向 B IDOR 應回 404 execution_code={execution_code} status={idor.status_code}"
            )
        finally:
            _set_workflow_owner(wi_sc, EXPECTED_USER_REF)

        cancel = session.post(cancel_url, headers={"X-CSRFToken": csrf_token}, timeout=20)
        assert cancel.status_code == 200, (
            f"正常撤單失敗 execution_code={execution_code} "
            f"status={cancel.status_code} body={cancel.text[:500]}"
        )
        cancel_json = cancel.json()
        assert cancel_json["data"]["execution_code"] == execution_code, (
            f"撤單回應 execution_code 不一致 expected={execution_code} body={cancel_json}"
        )

        wi_status, queue_counts = _wait_for_queue_settled(execution_code, wi_sc)
        assert wi_status == "CANCELLED", (
            f"workflow 未取消 execution_code={execution_code} wi_status={wi_status}"
        )
        assert not any(queue_counts.get(status, 0) for status in ACTIVE_QUEUE_STATUSES), (
            f"queue 仍有非終態節點 execution_code={execution_code} queue_counts={queue_counts}"
        )

        queue_row, approval_rows = _fetch_cancel_assertions(wi_sc, queue_sc)
        assert queue_row == ("CANCELLED",), (
            f"E2E WAITING 節點未被取消 execution_code={execution_code} queue_sc={queue_sc}"
        )
        assert len(approval_rows) == 1, (
            f"FORCE_END approval 筆數錯誤 execution_code={execution_code} rows={approval_rows}"
        )
        action, approver_name, comment = approval_rows[0]
        assert action == "FORCE_END", f"FORCE_END action 錯誤 execution_code={execution_code}"
        assert approver_name.startswith("portal:"), (
            f"FORCE_END approver_name 錯誤 execution_code={execution_code} approver={approver_name}"
        )
        assert "user_ref=u:1" in comment, (
            f"FORCE_END comment 缺 user_ref execution_code={execution_code} comment={comment}"
        )

        duplicate = session.post(cancel_url, headers={"X-CSRFToken": csrf_token}, timeout=10)
        assert duplicate.status_code == 409, (
            f"負向 C 重複撤單應回 409 execution_code={execution_code} status={duplicate.status_code}"
        )
        assert duplicate.json().get("error") == "not_cancellable", (
            f"負向 C error 錯誤 execution_code={execution_code} body={duplicate.text[:500]}"
        )
    finally:
        _cleanup(wi_sc, fi_sc, serial_number)
