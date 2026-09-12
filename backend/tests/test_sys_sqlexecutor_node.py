# -*- coding: utf-8 -*-
"""
SysSqlExecutor 節點的安全防護測試

這個節點的風險是「洩密」與「破壞」，所以測的重點不是查詢跑不跑得動，
而是：**config 被竄改之後會不會出事**。流程 graph 可以透過 API 直接 PUT 改寫，
設計器的下拉選單不是防線。

分三層：
1. 純函式（型別轉換、結果截斷、註記跳脫）—— 不碰 DB
2. 參數組裝（org 強制帶入、未宣告參數拒絕）—— 假的 queue_item，不碰 DB
3. 白名單重查與 pg_proc 覆核、唯讀交易 —— 真的打 PostgreSQL 測試庫
"""
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app import db  # noqa: E402
from modules.form_workflow.models import FwSqlProcedure  # noqa: E402
from modules.form_workflow.services.node_handlers.sys_sqlexecutor_handler import (  # noqa: E402
    MAX_CELL_CHARS, MAX_TOTAL_CHARS, ORG_PARAM,
    SysSqlExecutorHandler, SqlProcedureRejected,
    coerce_param, normalize_cell, normalize_rows, sanitize_for_comment,
)

ORG_A = 'ORG_AAAAAAAAAAAAAAAAAAAA'
ORG_B = 'ORG_BBBBBBBBBBBBBBBBBBBB'


# ==========================================================================
# 1. 純函式
# ==========================================================================

def test_coerce_text_truncates():
    out = coerce_param('x' * 9999, 'text', 'p_x')
    assert len(out) == 4000


def test_coerce_integer_ok():
    assert coerce_param(' 42 ', 'integer', 'p_x') == 42


@pytest.mark.parametrize('bad', ['42; DROP TABLE users', '1e9', '4.2', 'abc', "1' OR '1'='1"])
def test_coerce_integer_rejects_non_integer(bad):
    """整數參數只收整數字面值 —— 這是「值不會變成 SQL」的第二道"""
    with pytest.raises(SqlProcedureRejected):
        coerce_param(bad, 'integer', 'p_x')


def test_coerce_numeric_ok():
    assert coerce_param('12.50', 'numeric', 'p_x') == Decimal('12.50')


def test_coerce_numeric_rejects_expression():
    with pytest.raises(SqlProcedureRejected):
        coerce_param('1+1', 'numeric', 'p_x')


@pytest.mark.parametrize('raw,expected', [('true', True), ('FALSE', False), ('1', True), ('n', False)])
def test_coerce_boolean(raw, expected):
    assert coerce_param(raw, 'boolean', 'p_x') is expected


def test_coerce_boolean_rejects_other():
    with pytest.raises(SqlProcedureRejected):
        coerce_param('maybe', 'boolean', 'p_x')


def test_coerce_date_ok():
    assert coerce_param('2026-08-20', 'date', 'p_x') == date(2026, 8, 20)


def test_coerce_date_rejects_bad_format():
    with pytest.raises(SqlProcedureRejected):
        coerce_param('2026/08/20', 'date', 'p_x')


def test_coerce_rejects_unknown_type():
    """白名單登記了沒見過的型別時要拒絕，不能當成 text 放行"""
    with pytest.raises(SqlProcedureRejected):
        coerce_param('x', 'json', 'p_x')


def test_coerce_empty_becomes_none():
    assert coerce_param('   ', 'text', 'p_x') is None


def test_normalize_cell_types():
    assert normalize_cell(Decimal('1.5')) == 1.5
    assert normalize_cell(date(2026, 8, 20)) == '2026-08-20'
    assert normalize_cell(datetime(2026, 8, 20, 1, 2, 3)) == '2026-08-20 01:02:03'
    assert normalize_cell(b'\x00\x01') == '<binary>'
    assert normalize_cell(None) is None
    assert normalize_cell(True) is True


def test_normalize_cell_truncates_long_string():
    assert len(normalize_cell('x' * (MAX_CELL_CHARS + 500))) == MAX_CELL_CHARS


def test_normalize_rows_applies_row_limit():
    raw = [(i,) for i in range(20)]
    rows, truncated = normalize_rows(raw, ['n'], max_rows=5)
    assert len(rows) == 5
    assert truncated is True


def test_normalize_rows_not_truncated_when_within_limit():
    raw = [(1,), (2,)]
    rows, truncated = normalize_rows(raw, ['n'], max_rows=5)
    assert len(rows) == 2
    assert truncated is False


def test_normalize_rows_applies_total_size_limit():
    """
    單列很大時，列數上限擋不住總量 —— 流程變數會流到表單與簽核意見，
    沒有總量上限等於把整張表灌出去。
    """
    big = 'x' * MAX_CELL_CHARS
    raw = [(big,) for _ in range(200)]
    rows, truncated = normalize_rows(raw, ['blob'], max_rows=200)
    assert truncated is True
    assert sum(len(r['blob']) for r in rows) <= MAX_TOTAL_CHARS


def test_sanitize_for_comment_escapes_html():
    out = sanitize_for_comment('<script>alert("x")</script>')
    assert '<' not in out and '>' not in out and '"' not in out


# ==========================================================================
# 2. 參數組裝（不碰 DB）
# ==========================================================================

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
    # 變數替換獨立測試，這裡只驗參數把關；原樣回傳即可
    handler.replace_variables = lambda raw, **kwargs: raw
    return handler


def _entry(parameters=None, **kwargs):
    defaults = dict(
        code='check_stock', function_name='check_stock', display_name='查庫存',
        parameters=parameters if parameters is not None else [
            {'name': ORG_PARAM, 'type': 'text', 'required': True},
            {'name': 'p_item_code', 'type': 'text', 'required': True},
        ],
        result_mode='row', result_columns=[], max_rows=1,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_org_is_injected_from_queue_item():
    handler = _handler({'params': {'p_item_code': 'A-1001'}})
    values = handler._build_params(_entry())
    assert values[ORG_PARAM] == ORG_A


def test_config_cannot_override_org():
    """
    最關鍵的一條：graph 被改成自己帶 org 時必須整次拒絕，
    不是「忽略它然後照樣執行」—— 忽略的話這條測試會過但攻擊者會知道試錯方向。
    """
    handler = _handler({'params': {ORG_PARAM: ORG_B, 'p_item_code': 'A-1001'}})
    with pytest.raises(SqlProcedureRejected) as exc:
        handler._build_params(_entry())
    assert ORG_PARAM in str(exc.value)


def test_unknown_param_rejected():
    handler = _handler({'params': {'p_item_code': 'A-1001', 'p_evil': '1'}})
    with pytest.raises(SqlProcedureRejected):
        handler._build_params(_entry())


def test_missing_required_param_rejected():
    handler = _handler({'params': {}})
    with pytest.raises(SqlProcedureRejected):
        handler._build_params(_entry())


def test_optional_param_may_be_empty():
    entry = _entry(parameters=[
        {'name': ORG_PARAM, 'type': 'text', 'required': True},
        {'name': 'p_note', 'type': 'text', 'required': False},
    ])
    handler = _handler({'params': {'p_note': ''}})
    assert handler._build_params(entry)['p_note'] is None


def test_entry_without_org_param_rejected():
    """白名單登錄本身沒有 org 參數時不可執行 —— 那種 SP 沒有租戶邊界"""
    entry = _entry(parameters=[{'name': 'p_item_code', 'type': 'text', 'required': True}])
    handler = _handler({'params': {'p_item_code': 'A-1001'}})
    with pytest.raises(SqlProcedureRejected):
        handler._build_params(entry)


def test_missing_org_on_queue_item_rejected():
    handler = _handler({'params': {'p_item_code': 'A-1001'}}, org=None)
    with pytest.raises(SqlProcedureRejected):
        handler._build_params(_entry())


def test_illegal_declared_param_name_rejected():
    entry = _entry(parameters=[
        {'name': ORG_PARAM, 'type': 'text', 'required': True},
        {'name': 'p_x); DROP TABLE users; --', 'type': 'text', 'required': True},
    ])
    handler = _handler({'params': {}})
    with pytest.raises(SqlProcedureRejected):
        handler._build_params(entry)


def test_params_not_a_dict_rejected():
    handler = _handler({'params': ['A-1001']})
    with pytest.raises(SqlProcedureRejected):
        handler._build_params(_entry())


def test_validate_rejects_bad_result_var():
    handler = _handler({'procedure_code': 'check_stock', 'result_var': '../../etc/passwd'})
    handler.log_error = lambda *a, **k: None
    assert handler.validate() is False


def test_validate_accepts_normal_config():
    handler = _handler({'procedure_code': 'check_stock', 'result_var': 'stock'})
    assert handler.validate() is True


# ==========================================================================
# 3. 白名單重查 / pg_proc 覆核 / 唯讀交易（真的打 PostgreSQL）
# ==========================================================================

pg_only = pytest.mark.skipif(
    'sqlite' in (__import__('os').getenv('DATABASE_URL') or 'sqlite'),
    reason='需要 PostgreSQL 測試庫（scripts/run_tests.sh 會設定）',
)


@pytest.fixture
def fw_sp_schema(app):
    """在測試庫建出 fw_sp schema 與幾支測試用函式，收尾整個 DROP 掉"""
    db.session.execute(text('CREATE SCHEMA IF NOT EXISTS fw_sp'))
    db.session.execute(text("""
        CREATE OR REPLACE FUNCTION fw_sp.t_echo(p_org_secure_code TEXT, p_item_code TEXT)
        RETURNS TABLE (org TEXT, item TEXT)
        LANGUAGE sql STABLE SECURITY INVOKER
        AS $$ SELECT p_org_secure_code, p_item_code $$;
    """))
    db.session.execute(text("""
        CREATE OR REPLACE FUNCTION fw_sp.t_definer(p_org_secure_code TEXT)
        RETURNS TABLE (org TEXT)
        LANGUAGE sql STABLE SECURITY DEFINER
        AS $$ SELECT p_org_secure_code $$;
    """))
    db.session.execute(text("""
        CREATE OR REPLACE FUNCTION fw_sp.t_writer(p_org_secure_code TEXT)
        RETURNS TABLE (n INT)
        LANGUAGE plpgsql VOLATILE SECURITY INVOKER
        AS $$
        BEGIN
            -- public. 前綴不可省：_execute 的交易內 search_path 已釘為 pg_catalog
            -- （PF-190 P3-2），不限定的話這裡會先死在 relation not exist，
            -- 就測不到唯讀交易的擋寫行為了
            INSERT INTO public.fw_sql_procedures
                (secure_code, code, function_name, display_name, parameters,
                 result_mode, result_columns, max_rows, is_active, is_deleted,
                 created_at, updated_at)
            VALUES ('WRITTEN_BY_SP_0000000000', 'written_by_sp', 't_echo', 'x',
                    '[]'::jsonb, 'rows', '[]'::jsonb, 1, TRUE, FALSE, NOW(), NOW());
            RETURN QUERY SELECT 1;
        END $$;
    """))
    db.session.commit()
    yield
    db.session.rollback()
    db.session.execute(text('DROP SCHEMA IF EXISTS fw_sp CASCADE'))
    db.session.commit()


def _seed(code, org=None, function_name='t_echo', is_active=True, **kwargs):
    params = kwargs.pop('parameters', [
        {'name': ORG_PARAM, 'type': 'text', 'required': True},
        {'name': 'p_item_code', 'type': 'text', 'required': True},
    ])
    proc = FwSqlProcedure(
        org_secure_code=org, code=code, function_name=function_name,
        display_name=code, parameters=params, result_mode='rows',
        result_columns=[], max_rows=kwargs.pop('max_rows', 10),
        is_active=is_active, **kwargs)
    db.session.add(proc)
    db.session.commit()
    return proc


@pg_only
def test_load_procedure_finds_shared_entry(app):
    _seed('shared_one')
    assert _handler({'procedure_code': 'shared_one'})._load_procedure().code == 'shared_one'


@pg_only
def test_load_procedure_rejects_unknown_code(app):
    """執行期重查白名單：graph 被改成不存在的 code 一律拒絕"""
    with pytest.raises(SqlProcedureRejected):
        _handler({'procedure_code': 'not_registered'})._load_procedure()


@pg_only
def test_load_procedure_rejects_inactive(app):
    _seed('disabled_one', is_active=False)
    with pytest.raises(SqlProcedureRejected):
        _handler({'procedure_code': 'disabled_one'})._load_procedure()


@pg_only
def test_load_procedure_rejects_other_org_entry(app):
    """B 企業專屬的登錄項，A 企業的流程不得執行"""
    _seed('org_b_only', org=ORG_B)
    with pytest.raises(SqlProcedureRejected):
        _handler({'procedure_code': 'org_b_only'}, org=ORG_A)._load_procedure()


@pg_only
def test_load_procedure_prefers_org_specific(app):
    _seed('dual', org=None, function_name='t_echo')
    _seed('dual', org=ORG_A, function_name='t_echo', max_rows=7)
    entry = _handler({'procedure_code': 'dual'}, org=ORG_A)._load_procedure()
    assert entry.org_secure_code == ORG_A


@pg_only
def test_verify_function_accepts_normal_function(app, fw_sp_schema):
    handler = _handler({'procedure_code': 'shared_one'})
    handler._verify_function(_entry(function_name='t_echo'))   # 不應拋例外


@pg_only
def test_verify_function_rejects_security_definer(app, fw_sp_schema):
    """SECURITY DEFINER = 以函式擁有者的權限執行，是提權途徑，一律拒絕"""
    handler = _handler({'procedure_code': 'x'})
    entry = _entry(function_name='t_definer',
                   parameters=[{'name': ORG_PARAM, 'type': 'text', 'required': True}])
    with pytest.raises(SqlProcedureRejected) as exc:
        handler._verify_function(entry)
    assert 'SECURITY DEFINER' in str(exc.value)


@pg_only
def test_verify_function_rejects_missing_function(app, fw_sp_schema):
    handler = _handler({'procedure_code': 'x'})
    with pytest.raises(SqlProcedureRejected):
        handler._verify_function(_entry(function_name='t_nope'))


@pg_only
def test_verify_function_rejects_arity_mismatch(app, fw_sp_schema):
    """白名單宣告的參數個數與資料庫實況不符時拒絕（表可能沒跟著函式更新）"""
    handler = _handler({'procedure_code': 'x'})
    entry = _entry(function_name='t_echo',
                   parameters=[{'name': ORG_PARAM, 'type': 'text', 'required': True}])
    with pytest.raises(SqlProcedureRejected):
        handler._verify_function(entry)


@pg_only
def test_execute_is_read_only(app, fw_sp_schema):
    """
    節點不可能寫入任何東西 —— 由資料庫的唯讀交易保證，不是靠 handler 自律。

    t_writer 會 INSERT，在唯讀交易內必然被 PostgreSQL 擋下。
    """
    from sqlalchemy.exc import SQLAlchemyError

    handler = _handler({'procedure_code': 'x', 'timeout_seconds': 5})
    entry = _entry(function_name='t_writer', result_mode='rows', max_rows=10,
                   parameters=[{'name': ORG_PARAM, 'type': 'text', 'required': True}])
    with pytest.raises(SQLAlchemyError) as exc:
        handler._execute(entry, {ORG_PARAM: ORG_A})
    assert 'read-only' in str(exc.value).lower()
    # 副作用確實沒有留下
    assert FwSqlProcedure.query.filter_by(code='written_by_sp').first() is None


@pg_only
def test_execute_passes_org_as_bound_value(app, fw_sp_schema):
    """org 是 bind 值不是字串拼接：帶引號的內容原樣回來，不會變成 SQL"""
    handler = _handler({'procedure_code': 'x'})
    entry = _entry(function_name='t_echo', result_mode='rows', max_rows=10)
    weird = "' OR 1=1 --"
    columns, rows, limit = handler._execute(
        entry, {ORG_PARAM: weird, 'p_item_code': 'A-1001'})
    assert rows[0][0] == weird


@pg_only
def test_sql_note_is_not_counted_as_approval(app):
    """
    新的 action 值不可以被誤算成有效簽核。

    判定有效簽核的地方用的是**白名單** `action.in_(['approved','rejected'])`
    （fc_pending.py:413、fc_batch.py:94），所以 'sql_note' 天生不會命中。
    這條測的是「有人把 action 改成別的值」時會不會破功。
    """
    from modules.form_workflow.models import FwApprovalRecord
    from modules.form_workflow.services.node_handlers.sys_sqlexecutor_handler import (
        SysSqlExecutorHandler as _H)

    rec = FwApprovalRecord(
        org_secure_code=ORG_A, form_instance_secure_code='FI_TEST',
        workflow_instance_secure_code='WF_TEST', node_id='n1', node_name='查庫存',
        approver_secure_code=None, approver_name='SYSTEM',
        action='sql_note', comment='x')
    db.session.add(rec)
    db.session.commit()

    counted = FwApprovalRecord.query.filter(
        FwApprovalRecord.workflow_instance_secure_code == 'WF_TEST',
        FwApprovalRecord.action.in_(['approved', 'rejected'])).count()
    assert counted == 0

    # handler 真的用這個 action 值（改了值就要回頭確認上面的白名單）
    src = Path(_H.__module__.replace('.', '/') + '.py')
    assert "action='sql_note'" in (Path(__file__).resolve().parents[2] / src).read_text()
