"""
FormWorkflow Module - Execution Code Service

流程執行編號（`fw_workflow_instances.execution_code`）的**唯一產生實作**。

編號格式：`<PREFIX><YYYYMMDD>-NNNN`（例：`OD-20260816-0003`、`PROC-20260816-0001`）。

兩件事一起做才正確，缺一都會出事（PF-116）：

1. **序號池限定同企業**（`AND org_secure_code = :osc`）。全域池會讓企業從自己拿到的
   號碼推知其他企業當日的案件量，而唯一性約束
   `uq_fw_wi_org_execution_code` 也已經是 per-org。
2. **transaction-scoped advisory lock**（企業 + prefix + 日期）。`SELECT MAX+1`
   在並發下會算出同一個號碼，鎖在 commit/rollback 自動釋放，不會 leak。

**禁止各處自行寫 MAX+1**：本檔出現之前 intake_service 與 form_submit_service
各有一份，其中一份的鎖是 per-org、查詢池卻是全域，另一份根本沒有鎖——
兩家企業同時送件就會撞 unique（PF-116 的成因）。
"""
import logging

from sqlalchemy import text

from app import db

logger = logging.getLogger(__name__)

# 序號位數。與 SQL 內的 `\d{4}$` 及 zfill 綁在一起，改動要三處同步。
SEQ_DIGITS = 4


def next_execution_code(*, org_secure_code: str, prefix: str, date_str: str) -> str:
    """配發下一個流程執行編號（同一交易內呼叫，回傳後直接寫入 instance）。

    Args:
        org_secure_code: 企業識別碼，序號池與 advisory lock 都以它為界
        prefix: 編號前綴，需自帶分隔符（`'OD-'` / `'PROC-'`）
        date_str: `YYYYMMDD`，由呼叫端決定取 UTC 或本地時間

    Raises:
        ValueError: org_secure_code 為空（fail-closed，不允許落到全域池）
    """
    if not org_secure_code:
        raise ValueError('org_secure_code 必填：execution_code 序號池以企業為界')

    lock_key = f'fw_exec_seq:{org_secure_code}:{prefix}{date_str}'
    db.session.execute(
        text('SELECT pg_advisory_xact_lock(hashtext(:key))'),
        {'key': lock_key},
    )

    seq = db.session.execute(
        text("""
            SELECT COALESCE(MAX(CAST(SUBSTRING(execution_code FROM '\\d{4}$')
                AS INTEGER)), 0) + 1
            FROM fw_workflow_instances
            WHERE execution_code LIKE :pattern
              AND org_secure_code = :osc
        """),
        {'pattern': f'{prefix}{date_str}-%', 'osc': org_secure_code},
    ).scalar() or 1

    return f'{prefix}{date_str}-{str(seq).zfill(SEQ_DIGITS)}'
