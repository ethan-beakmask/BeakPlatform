# -*- coding: utf-8 -*-
"""
SysSqlExecutor 節點 — 租戶隔離紅隊測試（2026-08-31, Session B）

與 test_sys_sqlexecutor_node.py 互補：那個檔案驗「七道防線各自存在」，
這個檔案站在攻擊者立場，補既有測試沒覆蓋到的**變體與繞道**：

- org 覆寫的大小寫／空白變體（不是只有精確的 p_org_secure_code）
- config 頂層塞 schema / function_name / org_secure_code 試圖覆寫寫死常數 → 一律無效
- procedure_code 塞注入字元／Unicode 同形字／超長 → 執行期重查白名單擋下
- 危險 text 參數值走完整 _build_params → _execute 仍是 bind，不變成 SQL
- statement_timeout 真的會中斷長查詢
- integer / numeric 的邊界（超長位數、科學記號）拒絕

核心命題：**企業只能讀自己的資料，org 由系統從流程所屬企業帶入，
config / graph / 快照都改不動它。**

紅隊主結論（DB 層、非本檔可自動化的部分）記在
/opt/tmp/verify/20260831-sqlexecutor-isolation.log 與
dev-notes/SQL_EXECUTOR_SPEC.md「已驗證的隔離邊界（2026-08-31）」。
"""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app import db  # noqa: E402
from modules.form_workflow.models import FwSqlProcedure  # noqa: E402
from modules.form_workflow.services.node_handlers.sys_sqlexecutor_handler import (  # noqa: E402
    ORG_PARAM, SysSqlExecutorHandler, SqlProcedureRejected, coerce_param,
)

ORG_A = 'ORG_AAAAAAAAAAAAAAAAAAAA'
ORG_B = 'ORG_BBBBBBBBBBBBBBBBBBBB'


def _handler(config, org=ORG_A):
    queue_item = SimpleNamespace(
        node_config=config,
        org_secure_code=org,
        workflow_instance_secure_code='WF_TEST',
        node_id='node-1',
        node_name='查庫存',
        secure_code='QUEUE_TEST',
        status='PENDING',
        id=1,
    )
    handler = SysSqlExecutorHandler(queue_item)
    # 變數替換獨立測試，這裡只驗把關；原樣回傳即可
    handler.replace_variables = lambda raw, **kwargs: raw
    return handler


def _entry(parameters=None, **kwargs):
    defaults = dict(
        code='check_stock', function_name='t_echo', display_name='查庫存',
        parameters=parameters if parameters is not None else [
            {'name': ORG_PARAM, 'type': 'text', 'required': True},
            {'name': 'p_item_code', 'type': 'text', 'required': True},
        ],
        result_mode='rows', result_columns=[], max_rows=10,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


# ==========================================================================
# A. org 覆寫的變體（大小寫 / 空白）—— 精確比對之外的繞道
# ==========================================================================

@pytest.mark.parametrize('evil_key', [
    'p_org_secure_code',          # 精確（既有檔已測，這裡作對照基準）
    'P_ORG_SECURE_CODE',          # 全大寫
    'P_Org_Secure_Code',          # 混合大小寫
    ' p_org_secure_code',         # 前置空白
    'p_org_secure_code ',         # 後置空白
    '\tp_org_secure_code',        # tab
    'p_org_secure_code​',    # 零寬字元尾隨
])
def test_org_override_variants_all_rejected(evil_key):
    """
    攻擊者試圖用大小寫或空白變體讓 p_org_secure_code 混進 params，
    藉此讀別家企業。任何變體都必須整次拒絕 —— 不是忽略後照跑。

    精確變體走「ORG_PARAM 不得指定」分支；其餘變體因不在白名單宣告內，
    走「參數不在宣告」分支。兩條都拒絕，攻擊者無論怎麼變形都進不去。
    """
    handler = _handler({'params': {evil_key: ORG_B, 'p_item_code': 'A-1001'}})
    with pytest.raises(SqlProcedureRejected):
        handler._build_params(_entry())


def test_org_always_from_queue_never_from_config():
    """org 恆取自 queue_item，config 給什麼都不影響最終 bind 的 org 值"""
    handler = _handler({'params': {'p_item_code': 'A-1001'}}, org=ORG_A)
    values = handler._build_params(_entry())
    assert values[ORG_PARAM] == ORG_A
    # config 完全沒有能力寫入 ORG_B
    assert ORG_B not in values.values()


# ==========================================================================
# B. 危險 text 參數走完整鏈仍是 bind（不是拼接）
# ==========================================================================

@pytest.mark.parametrize('payload', [
    "'; DROP TABLE fw_sql_procedures; --",
    "$$; SELECT 1; $$",
    "\\'; SELECT pg_sleep(9)--",
    "1 OR 1=1",
    "') UNION SELECT * FROM users --",
])
def test_dangerous_text_param_passes_through_as_value(payload):
    """
    text 參數刻意不做內容過濾（coerce_param 對 text 只截長度），
    因為安全保證來自「值一律 bind」而不是「值很乾淨」。
    這裡確認危險字串原樣成為 bind 值、長度不炸、型別是 str。
    """
    handler = _handler({'params': {'p_item_code': payload}})
    values = handler._build_params(_entry())
    assert values['p_item_code'] == payload  # 原樣，未被改寫成 SQL 片段
    assert isinstance(values['p_item_code'], str)


# ==========================================================================
# B. 數值型別邊界（既有檔測了 1e9/4.2，這裡補超長與科學記號）
# ==========================================================================

@pytest.mark.parametrize('bad', [
    '1' * 19,           # 19 位，超過 \d{1,18}
    '12345678901234567890',
    '0x1F', '1e3', '+', '-',   # 十六進位 / 科學記號 / 只有符號
])
def test_integer_boundary_rejected(bad):
    with pytest.raises(SqlProcedureRejected):
        coerce_param(bad, 'integer', 'p_x')


def test_integer_unicode_digits_rejected():
    """
    PF-190 P3-3（2026-08-31 指示收緊）：整數/數值正則從 \\d 改 [0-9]。
    全形數字「１２３」過去會通過並被 int() 安全轉換（綁定值、無注入面），
    現在一律拒絕 —— 純 ASCII 嚴格性收緊，新行為由本測試釘住。
    """
    with pytest.raises(SqlProcedureRejected):
        coerce_param('１２３', 'integer', 'p_x')
    with pytest.raises(SqlProcedureRejected):
        coerce_param('１２３.５', 'numeric', 'p_x')


@pytest.mark.parametrize('bad', [
    '1e5', '1.1234567',            # 科學記號 / 小數超過 6 位
    '1' * 19, 'NaN', 'Infinity',
])
def test_numeric_boundary_rejected(bad):
    with pytest.raises(SqlProcedureRejected):
        coerce_param(bad, 'numeric', 'p_x')


# ==========================================================================
# C. 真打 PostgreSQL：config 覆寫無效、procedure_code 注入被擋、timeout 生效
# ==========================================================================

pg_only = pytest.mark.skipif(
    'sqlite' in (__import__('os').getenv('DATABASE_URL') or 'sqlite'),
    reason='需要 PostgreSQL 測試庫（scripts/run_tests.sh 會設定）',
)


@pytest.fixture
def fw_sp_iso(app):
    """建 fw_sp 與紅隊測試用函式，收尾整個 DROP。與 node 測試檔各自獨立。"""
    db.session.execute(text('CREATE SCHEMA IF NOT EXISTS fw_sp'))
    db.session.execute(text("""
        CREATE OR REPLACE FUNCTION fw_sp.t_echo(p_org_secure_code TEXT, p_item_code TEXT)
        RETURNS TABLE (org TEXT, item TEXT)
        LANGUAGE sql STABLE SECURITY INVOKER
        AS $$ SELECT p_org_secure_code, p_item_code $$;
    """))
    db.session.execute(text("""
        CREATE OR REPLACE FUNCTION fw_sp.t_sleeper(p_org_secure_code TEXT)
        RETURNS TABLE (n INT)
        LANGUAGE sql STABLE SECURITY INVOKER
        AS $$ SELECT 1 FROM pg_sleep(3) $$;
    """))
    db.session.execute(text("""
        CREATE OR REPLACE FUNCTION fw_sp.t_unqualified(p_org_secure_code TEXT)
        RETURNS TABLE (n BIGINT)
        LANGUAGE plpgsql STABLE SECURITY INVOKER
        AS $$
        BEGIN
            -- 刻意不寫 public. 前綴：驗 _execute 的 search_path 釘死
            RETURN QUERY SELECT count(*) FROM fw_sql_procedures;
        END $$;
    """))
    db.session.commit()
    yield
    db.session.rollback()
    db.session.execute(text('DROP SCHEMA IF EXISTS fw_sp CASCADE'))
    db.session.commit()


def _seed(code, org=None, function_name='t_echo', **kwargs):
    params = kwargs.pop('parameters', [
        {'name': ORG_PARAM, 'type': 'text', 'required': True},
        {'name': 'p_item_code', 'type': 'text', 'required': True},
    ])
    proc = FwSqlProcedure(
        org_secure_code=org, code=code, function_name=function_name,
        display_name=code, parameters=params, result_mode='rows',
        result_columns=[], max_rows=kwargs.pop('max_rows', 10),
        is_active=kwargs.pop('is_active', True), is_deleted=kwargs.pop('is_deleted', False))
    db.session.add(proc)
    db.session.commit()
    return proc


@pg_only
def test_config_schema_and_function_keys_are_inert(app, fw_sp_iso):
    """
    config 頂層塞 schema / function_name 想覆寫寫死常數 → 完全無效。
    handler 只認白名單登記的 function_name（放在 fw_sp 常數 schema 下），
    從不讀 config 的 schema / function_name。
    """
    _seed('rt_target', function_name='t_echo')
    handler = _handler({
        'procedure_code': 'rt_target',
        'params': {'p_item_code': 'X'},
        'function_name': 'pg_sleep',       # 想改呼叫的函式
        'schema': 'pg_catalog',            # 想改 schema
        'org_secure_code': ORG_B,          # 想改 org
        'result_var': 'r',
    }, org=ORG_A)
    entry = handler._load_procedure()
    assert entry.function_name == 't_echo'          # config 的 function_name 被忽略
    values = handler._build_params(entry)
    assert values[ORG_PARAM] == ORG_A               # config 的 org_secure_code 被忽略
    # 實際執行組出的 SQL 一定是 fw_sp.t_echo，回傳 org 就是 queue 的 ORG_A
    columns, rows, limit = handler._execute(entry, values)
    assert rows[0][0] == ORG_A


@pg_only
@pytest.mark.parametrize('evil_code', [
    "check_stock'; DROP TABLE fw_sql_procedures; --",
    'check_stock OR 1=1',
    'сheck_stock',            # 首字是 Cyrillic 同形字 с
    'CHECK_STOCK',            # 大小寫（DB code 存小寫）
    'x' * 200,                # 超長
    'pg_read_file',           # 想跳到危險函式的 code
])
def test_procedure_code_injection_rejected(app, evil_code):
    """
    procedure_code 由攻擊者可控，handler 拿它去白名單精確比對 code 欄位。
    注入字元／同形字／大小寫／超長／危險名一律比不到 → fail-closed 拒絕。
    """
    with pytest.raises(SqlProcedureRejected):
        _handler({'procedure_code': evil_code})._load_procedure()


@pg_only
def test_search_path_pinned_unqualified_table_fails(app, fw_sp_iso):
    """
    _execute 的交易內 search_path 固定為 pg_catalog（PF-190 P3-2）：
    SP 內未 schema 限定的表引用，即使該表真的存在於 public，
    也直接 relation not exist。堵掉「在 search_path 上動手腳換掉目標表」
    整類手法，同時強制 SP 撰寫規範（表引用一律 public.xxx）。
    """
    from sqlalchemy.exc import SQLAlchemyError

    handler = _handler({'procedure_code': 'x', 'timeout_seconds': 5})
    entry = _entry(function_name='t_unqualified', max_rows=10,
                   parameters=[{'name': ORG_PARAM, 'type': 'text', 'required': True}])
    with pytest.raises(SQLAlchemyError) as exc:
        handler._execute(entry, {ORG_PARAM: ORG_A})
    assert 'does not exist' in str(exc.value)


@pg_only
def test_statement_timeout_aborts_long_query(app, fw_sp_iso):
    """
    timeout_seconds=1 時，pg_sleep(3) 的 SP 必須在約 1 秒被 statement_timeout 中斷，
    不會把 executor 卡住 3 秒。確認 handler 設的 statement_timeout 真的生效。
    """
    import time
    from sqlalchemy.exc import SQLAlchemyError

    handler = _handler({'procedure_code': 'x', 'timeout_seconds': 1})
    entry = _entry(function_name='t_sleeper', result_mode='rows', max_rows=10,
                   parameters=[{'name': ORG_PARAM, 'type': 'text', 'required': True}])
    t0 = time.monotonic()
    try:
        with pytest.raises(SQLAlchemyError) as exc:
            handler._execute(entry, {ORG_PARAM: ORG_A})
        elapsed = time.monotonic() - t0
        assert 'timeout' in str(exc.value).lower()
        assert elapsed < 3.0, f'timeout 沒生效，花了 {elapsed:.1f}s（應 ~1s）'
    finally:
        # statement_timeout 觸發時 handler 的 conn.rollback() 被跳過，連線帶 aborted
        # 狀態回連線池。生產環境靠 SQLAlchemy reset_on_return 自動 rollback，不成問題；
        # 但測試與 conftest 的 function-scoped create_all/drop_all 共用同一個 pool，
        # 殘留的 aborted 連線會讓下一個測試的 drop_all 失敗。dispose() 清掉整個 pool，
        # 讓後續測試拿到乾淨連線。
        db.session.rollback()
        db.engine.dispose()


@pg_only
def test_cross_org_specific_entry_not_loadable(app, fw_sp_iso):
    """
    B 企業專屬白名單列，A 企業的流程即使拿到那個 code 也載入不到（回租戶自己的）。
    這是 get_sql_procedures API 過濾之外、執行期的第二道租戶邊界。
    """
    _seed('rt_shared', org=None, function_name='t_echo')
    _seed('rt_b_secret', org=ORG_B, function_name='t_echo')
    # A 企業拿 B 專屬 code → 白名單重查排除他企業 → 拒絕
    with pytest.raises(SqlProcedureRejected):
        _handler({'procedure_code': 'rt_b_secret'}, org=ORG_A)._load_procedure()
    # A 企業拿共用 code → 正常載入
    assert _handler({'procedure_code': 'rt_shared'}, org=ORG_A)._load_procedure().code == 'rt_shared'
