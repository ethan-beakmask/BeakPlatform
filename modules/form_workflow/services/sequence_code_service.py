"""
FormWorkflow Module - Sequence Code Service

流程執行編號（`fw_workflow_instances.execution_code`）與表單編號
（`fw_form_instances.serial_number`）的**唯一 SELECT MAX+1 產生實作**。

兩件事一起做才正確，缺一都會出事：

1. **序號池限定同企業**（`AND org_secure_code = :osc`）。全域池會讓企業從自己拿到的
   號碼推知其他企業當日送件量，而唯一性約束也已經改為 per-org。
2. **transaction-scoped advisory lock**（企業 + prefix + 日期）。`SELECT MAX+1`
   在並發下會算出同一個號碼，鎖在 commit/rollback 自動釋放，不會 leak。

**禁止各處自行寫 MAX+1**。動態識別字只允許本模組內的表名/欄名常數，
`_next_seq()` 是私有函式，外部不得傳入 table/column；呼叫端只能使用具名函式。
"""
import logging

from sqlalchemy import text

from app import db

logger = logging.getLogger(__name__)

_EXEC_TABLE = 'fw_workflow_instances'
_EXEC_COLUMN = 'execution_code'
_FORM_TABLE = 'fw_form_instances'
_FORM_COLUMN = 'serial_number'
_ALLOWED_TARGETS = {
    (_EXEC_TABLE, _EXEC_COLUMN),
    (_FORM_TABLE, _FORM_COLUMN),
}


def _next_seq(
    *,
    table: str,
    column: str,
    org_secure_code: str,
    prefix: str,
    date_str: str,
    digits: int,
    lock_ns: str,
    seq_pattern: str,
) -> str:
    """配發下一個 per-org 序號。

    `table` / `column` 必須是本模組常數組合，不接受外部輸入。SQL 識別字無法用
    bind parameter，因此這裡 fail-closed 檢查白名單後才組入 SQL；其他值一律走
    bind parameter。
    """
    if (table, column) not in _ALLOWED_TARGETS:
        raise ValueError('不允許的序號目標')
    if not org_secure_code:
        raise ValueError(f'org_secure_code 必填：{column} 序號池以企業為界')
    if digits <= 0:
        raise ValueError('digits 必須大於 0')

    lock_key = f'{lock_ns}:{org_secure_code}:{prefix}{date_str}'
    db.session.execute(
        text('SELECT pg_advisory_xact_lock(hashtext(:key))'),
        {'key': lock_key},
    )

    seq = db.session.execute(
        text(f"""
            SELECT COALESCE(MAX(CAST(SUBSTRING({column} FROM :seq_pattern)
                AS INTEGER)), 0) + 1
            FROM {table}
            WHERE {column} LIKE :pattern
              AND org_secure_code = :osc
        """),
        {
            'seq_pattern': seq_pattern,
            'pattern': f'{prefix}{date_str}-%',
            'osc': org_secure_code,
        },
    ).scalar() or 1

    return f'{prefix}{date_str}-{str(seq).zfill(digits)}'


def next_execution_code(*, org_secure_code: str, prefix: str, date_str: str) -> str:
    """配發下一個流程執行編號（同一交易內呼叫，回傳後直接寫入 instance）。

    Args:
        org_secure_code: 企業識別碼，序號池與 advisory lock 都以它為界
        prefix: 編號前綴，需自帶分隔符（`'OD-'` / `'PROC-'`）
        date_str: `YYYYMMDD`，由呼叫端決定取 UTC 或本地時間

    Raises:
        ValueError: org_secure_code 為空（fail-closed，不允許落到全域池）
    """
    return _next_seq(
        table=_EXEC_TABLE,
        column=_EXEC_COLUMN,
        org_secure_code=org_secure_code,
        prefix=prefix,
        date_str=date_str,
        digits=4,
        lock_ns='fw_exec_seq',
        seq_pattern=r'\d{4}$',
    )


def next_org_form_seq(*, org_secure_code: str) -> int:
    """配發企業內表單流水號（L2，`fw_form_instances.org_form_seq`）。

    與編號字串不同，這是純整數、不分日期與前綴，唯一性由
    `uq_form_org_seq (org_secure_code, org_form_seq) WHERE org_form_seq IS NOT NULL`
    保護。同樣需要 advisory lock：`MAX+1` 在並發下會算出同一個值，
    同企業兩人同時送件就撞該約束。
    """
    if not org_secure_code:
        raise ValueError('org_secure_code 必填：org_form_seq 以企業為界')

    db.session.execute(
        text('SELECT pg_advisory_xact_lock(hashtext(:key))'),
        {'key': f'fw_org_form_seq:{org_secure_code}'},
    )
    return db.session.execute(
        text("""
            SELECT COALESCE(MAX(org_form_seq), 0) + 1
            FROM fw_form_instances
            WHERE org_secure_code = :osc
        """),
        {'osc': org_secure_code},
    ).scalar() or 1


def next_form_serial_number(
    *,
    org_secure_code: str,
    prefix: str,
    date_str: str,
    digits: int,
) -> str:
    """配發下一個表單編號 fallback 序號。

    TEST 編號維持 `\\d{4}$` / 4 位；FORM fallback 維持舊有 `\\d+$` / 5 位，
    避免既有非 5 位尾碼資料被 MAX 查詢漏掉。
    """
    seq_pattern = r'\d+$' if prefix == 'FORM-' and digits == 5 else rf'\d{{{digits}}}$'
    return _next_seq(
        table=_FORM_TABLE,
        column=_FORM_COLUMN,
        org_secure_code=org_secure_code,
        prefix=prefix,
        date_str=date_str,
        digits=digits,
        lock_ns='fw_serial_seq',
        seq_pattern=seq_pattern,
    )
