"""
FormWorkflow Module - SQL Procedure Whitelist Model
SqlExecutor 節點的預存程序白名單

一筆記錄 ＝ 允許流程設計者呼叫 `fw_sp` schema 內的某支函式。
**登錄一筆等同授權**，所以維護走 migration（scripts/migrations/106_sqlexecutor_whitelist.sql），
不開放 Web UI 新增。

org_secure_code 為 NULL 表示全平台共用；有值時只有該企業的流程選得到。
"""
from sqlalchemy import Column, String, Text, Boolean, Integer
from sqlalchemy.dialects.postgresql import JSONB

from app.models.base import BaseModel


class FwSqlProcedure(BaseModel):
    """SqlExecutor 可呼叫的預存程序白名單"""

    __tablename__ = 'fw_sql_procedures'

    # NULL = 全平台共用
    org_secure_code = Column(String(32), nullable=True, index=True)

    # 流程 config 存的穩定識別碼（與實際函式名解耦）
    code = Column(String(64), nullable=False)
    # fw_sp schema 內的函式名
    function_name = Column(String(63), nullable=False)

    display_name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)

    # [{"name","type","label","required","description"}]
    # 第一個必須是 p_org_secure_code（由 handler 強制帶入，設計者不可指定）
    parameters = Column(JSONB, nullable=False, default=list)

    # scalar=單值 / row=單列 / rows=多列
    result_mode = Column(String(10), nullable=False, default='rows')
    # [{"name","label"}]，純文件用途
    result_columns = Column(JSONB, nullable=False, default=list)

    max_rows = Column(Integer, nullable=False, default=100)
    is_active = Column(Boolean, nullable=False, default=True)

    def designer_parameters(self):
        """
        回給設計器的參數清單：濾掉 p_org_secure_code。

        設計者不該看到、也不該能填企業識別碼 —— 它由 handler 從流程所屬企業帶入。
        """
        return [p for p in (self.parameters or [])
                if p.get('name') != 'p_org_secure_code']

    def to_designer_dict(self):
        """設計器下拉用的精簡格式（不含 function_name，那是內部細節）"""
        return {
            'code': self.code,
            'display_name': self.display_name,
            'description': self.description or '',
            'parameters': self.designer_parameters(),
            'result_mode': self.result_mode,
            'result_columns': self.result_columns or [],
            'max_rows': self.max_rows,
        }
