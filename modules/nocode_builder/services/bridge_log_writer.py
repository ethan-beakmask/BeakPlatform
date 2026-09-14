"""
Data CRUD Module - Bridge Log Writer
橋接操作審計日誌寫入

獨立檔案避免 DataBridgeService <-> DcBridgeLog 循環 import。
直接用 db.session 寫入主 DB。
"""
import logging
from typing import Any, Dict, Optional

from app import db
from app.utils.security import generate_secure_code

logger = logging.getLogger(__name__)


def write_bridge_log(
    org_secure_code: str,
    sub_system_sc: str,
    direction: str,
    source_db: str,
    source_table: str,
    target_db: str,
    target_table: str,
    records_affected: int,
    status: str,
    rule_id: str = None,
    record_key: Dict = None,
    field_mapping: Dict = None,
    error_message: str = None,
    operator_sc: str = None,
):
    """寫入一筆 dc_bridge_logs 記錄"""
    from modules.nocode_builder.models.bridge_log import DcBridgeLog

    log_entry = DcBridgeLog(
        secure_code=generate_secure_code(),
        org_secure_code=org_secure_code,
        sub_system_secure_code=sub_system_sc,
        rule_id=rule_id,
        direction=direction,
        source_db=source_db,
        source_table=source_table,
        target_db=target_db,
        target_table=target_table,
        record_key=record_key,
        records_affected=records_affected,
        field_mapping=field_mapping,
        status=status,
        error_message=error_message,
        operator_secure_code=operator_sc,
    )
    db.session.add(log_entry)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
