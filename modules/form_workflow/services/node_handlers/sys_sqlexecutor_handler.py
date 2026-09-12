"""
FormWorkflow Module - SysSqlExecutor Handler
系統級預存程序執行節點處理器

讓流程呼叫平台主庫裡「事先登錄過」的 stored procedure，把結果寫進流程變數，
可選擇再插一筆簽核註記給人類參考（與 AiAgent 節點共用同一個出口）。
典型場景：請料單在核可前先查庫存夠不夠，不夠就在簽核意見提醒。

## 安全設計（動這個檔案前務必讀完）

節點設定存在 `fw_workflow_templates.graph`（JSON），而 graph 可以透過 API 直接
PUT 改寫 —— **設計器的下拉選單不是防線**。所以這裡的每一道都假設 config 是
攻擊者可控的：

0. **受限節點（org_restricted）**。本節點只有取得授權的企業看得到、用得到，
   出廠只授權系統預設企業。執行期由 node_runner 統一擋，handler 內另有一道
   fail-closed 最後防線（見 handle() 開頭的 is_node_allowed）。
1. **schema 寫死**。SQL 只組得出 `fw_sp.<函式名>(...)`，`fw_sp` 是本檔的字面常數。
   即使白名單表被寫入奇怪內容，可觸及範圍仍鎖在那個 schema 內。
2. **執行期重查白名單**。config 給的是 `procedure_code`，handler 拿它去
   `fw_sql_procedures` 重新查一次（含企業歸屬、is_active、is_deleted），
   查不到就拒絕。這是整個元件最關鍵的一道，漏了等於白名單不存在。
3. **識別碼白名單比對 + pg_proc 覆核**。函式名與參數名都必須通過 `IDENT_RE`，
   再查 `pg_proc` 確認該函式真的存在於 `fw_sp`、參數個數相符、
   且**不是 SECURITY DEFINER**（避免提權）。
4. **org 由系統帶入**。每支 SP 的第一個參數固定 `p_org_secure_code`，值一律取自
   `queue_item.org_secure_code`；config 裡若出現這個參數名一律拒絕整次執行。
   SP 內部必須拿它當實際 filter —— 平台主庫多數表沒有 RLS（只有 10 張有且非 FORCE）、
   `beakplatform` 又是 owner，**RLS 不會替你擋，租戶邊界就在 SP 的 WHERE 裡**。
5. **參數一律 bind，不做字串拼接**。型別依白名單登記的宣告轉換，轉不動就拒絕。
6. **唯讀交易 + statement_timeout + 固定 search_path**。走獨立連線、
   `SET TRANSACTION READ ONLY`，由資料庫層保證這個節點不可能寫入任何東西；
   交易內 `search_path` 固定為 `pg_catalog`（PF-190 P3-2），SP 內的表引用
   必須 schema 限定（`public.xxx`），沒限定的會直接 relation not exist ——
   這讓「在 search_path 上動手腳換掉目標表」整類手法失效。
7. **結果有上限**。列數、單格長度、總長度三層截斷 —— 流程變數會流到表單、
   簽核意見甚至 SQL Sync，一個沒有上限的 SP 等於把整張表灌出去。

## v1 刻意不支援寫入型 SP

寫入型 SP 會帶出一個必須先回答的問題：它與節點執行是否同一個交易？
同交易的話 SP 內不能 COMMIT；獨立交易的話流程節點失敗時副作用留在資料庫裡
（「流程回滾了但 SP 已經改了資料」）。這個問題定案之前不開放，
所以 `_execute()` 一律 READ ONLY。要放寬必須連同交易語意一起設計，
不是把那一行拿掉。

白名單維護走 migration（`scripts/migrations/106_sqlexecutor_whitelist.sql`），
不開放 Web UI —— 登錄一筆等同授權，屬於部署期決定。
"""
import json
import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from modules.form_workflow.services.node_grant_service import is_node_allowed

from .base import BaseNodeHandler

# --- 硬性常數（不從 config 讀，改這裡才會變）---
ALLOWED_SCHEMA = 'fw_sp'
IDENT_RE = re.compile(r'^[a-z][a-z0-9_]{0,62}$')
VAR_NAME_RE = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]{0,63}$')
ORG_PARAM = 'p_org_secure_code'

ALLOWED_PARAM_TYPES = {'text', 'integer', 'numeric', 'boolean', 'date'}
ALLOWED_RESULT_MODES = {'scalar', 'row', 'rows'}

HARD_MAX_ROWS = 500          # 白名單登記值再大也不會超過這個
MAX_CELL_CHARS = 2000        # 單格字串長度上限
MAX_TOTAL_CHARS = 64 * 1024  # 整份結果序列化後的長度上限
MAX_TEXT_PARAM_CHARS = 4000  # 單一 text 參數長度上限

DEFAULT_TIMEOUT = 10
MIN_TIMEOUT = 1
MAX_TIMEOUT = 60

BOOL_TRUE = {'true', 't', '1', 'yes', 'y', 'on'}
BOOL_FALSE = {'false', 'f', '0', 'no', 'n', 'off'}


class SqlProcedureRejected(Exception):
    """白名單／參數驗證失敗。訊息可以進流程 log，但不進簽核註記。"""


# --------------------------------------------------------------------------
# 純函式區（不依賴 handler 狀態，方便單獨測試）
# --------------------------------------------------------------------------

def coerce_param(raw: Any, declared_type: str, param_name: str) -> Any:
    """
    依白名單登記的型別把字串轉成實際值。轉不動一律拋 SqlProcedureRejected。

    這裡不做「盡量猜」的事 —— 猜錯的代價是把非預期的值送進 SP。
    """
    if declared_type not in ALLOWED_PARAM_TYPES:
        raise SqlProcedureRejected(f'參數 {param_name} 的型別宣告不合法: {declared_type}')

    if raw is None:
        return None
    value = raw if isinstance(raw, str) else str(raw)
    value = value.strip()
    if value == '':
        return None

    if declared_type == 'text':
        return value[:MAX_TEXT_PARAM_CHARS]

    # [0-9] 而不是 \d：\d 是 Unicode 感知，全形數字「１２３」會通過
    # （int() 轉得動、無注入面，但沒理由收）。PF-190 P3-3 起收緊為 ASCII
    if declared_type == 'integer':
        if not re.fullmatch(r'[+-]?[0-9]{1,18}', value):
            raise SqlProcedureRejected(f'參數 {param_name} 需要整數，收到「{value[:50]}」')
        return int(value)

    if declared_type == 'numeric':
        if not re.fullmatch(r'[+-]?([0-9]{1,18})(\.[0-9]{1,6})?', value):
            raise SqlProcedureRejected(f'參數 {param_name} 需要數值，收到「{value[:50]}」')
        return Decimal(value)

    if declared_type == 'boolean':
        low = value.lower()
        if low in BOOL_TRUE:
            return True
        if low in BOOL_FALSE:
            return False
        raise SqlProcedureRejected(f'參數 {param_name} 需要 true/false，收到「{value[:50]}」')

    # date
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except ValueError:
        raise SqlProcedureRejected(f'參數 {param_name} 需要 YYYY-MM-DD 日期，收到「{value[:50]}」')


def normalize_cell(value: Any) -> Any:
    """把 DB 回來的值轉成可以塞進 JSONB 流程變數的型別"""
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, datetime):
        return value.isoformat(sep=' ', timespec='seconds')
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (bytes, bytearray, memoryview)):
        return '<binary>'
    if isinstance(value, (dict, list)):
        return value
    return str(value)[:MAX_CELL_CHARS]


def normalize_rows(raw_rows: List[Any], columns: List[str],
                   max_rows: int) -> Tuple[List[Dict[str, Any]], bool]:
    """
    轉成 list[dict] 並套三層上限（列數／單格長度／總長度）。

    回傳 (rows, truncated)。truncated 為 True 時代表使用者看到的不是全部。
    """
    rows: List[Dict[str, Any]] = []
    truncated = len(raw_rows) > max_rows
    total = 0
    for raw in raw_rows[:max_rows]:
        item = {col: normalize_cell(val) for col, val in zip(columns, raw)}
        chunk = len(json.dumps(item, ensure_ascii=False, default=str))
        if total + chunk > MAX_TOTAL_CHARS:
            truncated = True
            break
        rows.append(item)
        total += chunk
    return rows, truncated


def sanitize_for_comment(text_value: str, max_len: int = MAX_CELL_CHARS) -> str:
    """寫入 fw_approval_records.comment 前的過濾（防 stored XSS）"""
    text_value = (text_value or '')[:max_len]
    return (text_value.replace('&', '&amp;').replace('<', '&lt;')
                      .replace('>', '&gt;').replace('"', '&quot;'))


# --------------------------------------------------------------------------
# Handler
# --------------------------------------------------------------------------

class SysSqlExecutorHandler(BaseNodeHandler):
    """
    預存程序執行節點

    config：
      procedure_code       白名單裡的識別碼（必填）
      params               {參數名: 值}，值可含 ${f.xxx} / ${v.xxx}
      result_var           結果寫入的流程變數名（必填）
      timeout_seconds      SQL 逾時秒數（預設 10，上限 60）
      write_approval_note  是否插一筆 fw_approval_records 註記（預設 false）
      note_template        註記內容樣板，可用 ${v.xxx} 引用本節點剛寫入的變數
      on_error             'error'（預設，走 error 邊）或 'continue'
    """

    # ---- 驗證 -----------------------------------------------------------

    def validate(self) -> bool:
        if not self.get_config_value('procedure_code'):
            self.log_error('SysSqlExecutor 節點缺少 procedure_code 設定')
            return False
        result_var = self.get_config_value('result_var')
        if not result_var:
            self.log_error('SysSqlExecutor 節點缺少 result_var 設定')
            return False
        if not VAR_NAME_RE.match(str(result_var)):
            self.log_error(f'SysSqlExecutor 的 result_var 格式不合法: {result_var}')
            return False
        return True

    def _load_procedure(self):
        """
        執行期重查白名單。查不到、停用、不屬於本企業一律拒絕（fail-closed）。

        企業專屬登錄優先於全平台共用登錄。
        """
        from sqlalchemy import or_
        from ...models import FwSqlProcedure

        code = self.get_config_value('procedure_code')
        org_code = self.queue_item.org_secure_code

        candidates = FwSqlProcedure.query.filter(
            FwSqlProcedure.code == code,
            FwSqlProcedure.is_active.is_(True),
            FwSqlProcedure.is_deleted.is_(False),
            or_(FwSqlProcedure.org_secure_code.is_(None),
                FwSqlProcedure.org_secure_code == org_code),
        ).all()

        if not candidates:
            raise SqlProcedureRejected(f'預存程序「{code}」不在白名單內或已停用')

        # 企業專屬優先
        candidates.sort(key=lambda p: 0 if p.org_secure_code else 1)
        entry = candidates[0]

        if not IDENT_RE.match(entry.function_name or ''):
            raise SqlProcedureRejected(f'白名單登錄的函式名不合法: {entry.function_name}')
        if entry.result_mode not in ALLOWED_RESULT_MODES:
            raise SqlProcedureRejected(f'白名單登錄的 result_mode 不合法: {entry.result_mode}')
        return entry

    def _verify_function(self, entry) -> None:
        """
        再向 pg_proc 覆核一次：函式真的存在於 fw_sp、參數個數相符、非 SECURITY DEFINER。

        白名單表與資料庫實況可能不同步（例如函式被改寫成 SECURITY DEFINER），
        這一道就是為了不讓「表裡寫著沒問題」直接等於「可以執行」。
        """
        from app import db

        row = db.session.execute(text("""
            SELECT p.pronargs, p.prosecdef, p.prokind
            FROM pg_proc p
            JOIN pg_namespace n ON n.oid = p.pronamespace
            WHERE n.nspname = :schema AND p.proname = :fname
        """), {'schema': ALLOWED_SCHEMA, 'fname': entry.function_name}).fetchall()

        if not row:
            raise SqlProcedureRejected(
                f'{ALLOWED_SCHEMA}.{entry.function_name} 不存在於資料庫')
        if len(row) > 1:
            raise SqlProcedureRejected(
                f'{ALLOWED_SCHEMA}.{entry.function_name} 有多個多載，無法判定要呼叫哪一個')

        pronargs, prosecdef, prokind = row[0]
        if prosecdef:
            raise SqlProcedureRejected(
                f'{ALLOWED_SCHEMA}.{entry.function_name} 是 SECURITY DEFINER，拒絕執行')
        if prokind not in ('f',):
            raise SqlProcedureRejected(
                f'{ALLOWED_SCHEMA}.{entry.function_name} 不是 function（prokind={prokind}）')
        declared = entry.parameters or []
        if pronargs != len(declared):
            raise SqlProcedureRejected(
                f'{ALLOWED_SCHEMA}.{entry.function_name} 的參數個數（{pronargs}）'
                f'與白名單登錄（{len(declared)}）不符')

    def _build_params(self, entry) -> Dict[str, Any]:
        """
        組 bind 參數。org 由系統帶入，其餘依白名單宣告逐一驗證。

        config 出現白名單沒宣告的參數名 → 整次拒絕（不是忽略），
        因為那代表 graph 與白名單已經不一致，繼續執行的行為無法預期。
        """
        declared = entry.parameters or []
        if not declared or declared[0].get('name') != ORG_PARAM:
            raise SqlProcedureRejected(
                f'白名單登錄的第一個參數必須是 {ORG_PARAM}')

        org_code = self.queue_item.org_secure_code
        if not org_code:
            raise SqlProcedureRejected('流程節點沒有企業識別碼，拒絕執行')

        declared_names = []
        for spec in declared:
            name = spec.get('name') or ''
            if not IDENT_RE.match(name):
                raise SqlProcedureRejected(f'白名單登錄的參數名不合法: {name}')
            declared_names.append(name)

        config_params = self.get_config_value('params') or {}
        if not isinstance(config_params, dict):
            raise SqlProcedureRejected('params 設定必須是物件')

        for name in config_params:
            if name == ORG_PARAM:
                raise SqlProcedureRejected(
                    f'{ORG_PARAM} 由系統帶入，節點設定不得指定')
            if name not in declared_names:
                raise SqlProcedureRejected(f'參數「{name}」不在白名單宣告內')

        values: Dict[str, Any] = {ORG_PARAM: org_code}
        for spec in declared[1:]:
            name = spec['name']
            raw = config_params.get(name)
            if isinstance(raw, str):
                # 單次非遞迴替換：代入的內容不會被二次掃描
                raw = self.replace_variables(raw)
            value = coerce_param(raw, spec.get('type') or 'text', name)
            if value is None and spec.get('required'):
                raise SqlProcedureRejected(f'參數「{name}」為必填，但代入後是空值')
            values[name] = value
        return values

    # ---- 執行 -----------------------------------------------------------

    def _timeout_ms(self) -> int:
        raw = self.get_config_value('timeout_seconds')
        try:
            seconds = int(raw)
        except (TypeError, ValueError):
            seconds = DEFAULT_TIMEOUT
        seconds = max(MIN_TIMEOUT, min(MAX_TIMEOUT, seconds))
        return seconds * 1000

    def _execute(self, entry, values: Dict[str, Any]):
        """
        獨立連線、唯讀交易、帶 statement_timeout 執行。

        - schema 是本檔常數、函式名與參數名都過了 IDENT_RE 與 pg_proc 覆核，
          所以這裡的字串組裝不引入注入面；**值一律走 bind**。
        - 用具名參數語法 `參數名 => :參數名`，順序寫錯不會靜默對錯欄位。
        - 走 db.engine 另開連線而不是 db.session：READ ONLY 必須是整個交易的屬性，
          設在流程本身的 session 上會連帶影響同交易的流程寫入。
        """
        from app import db

        arg_sql = ', '.join(f'{name} => :{name}' for name in values)
        sql = f'SELECT * FROM {ALLOWED_SCHEMA}.{entry.function_name}({arg_sql})'
        limit = max(1, min(HARD_MAX_ROWS, int(entry.max_rows or 100)))

        with db.engine.connect() as conn:
            conn.execute(text('SET TRANSACTION READ ONLY'))
            # 固定 search_path（交易內生效）：SP 的表引用必須 schema 限定，
            # 未限定者直接 relation not exist（PF-190 P3-2，belt-and-suspenders）
            conn.execute(text("SELECT set_config('search_path', 'pg_catalog', true)"))
            conn.execute(text("SELECT set_config('statement_timeout', :ms, true)"),
                         {'ms': str(self._timeout_ms())})
            result = conn.execute(text(sql), values)
            columns = list(result.keys())
            raw_rows = result.fetchmany(limit + 1)
            conn.rollback()   # 唯讀交易，明確結束不留連線狀態

        return columns, raw_rows, limit

    # ---- 寫入 -----------------------------------------------------------

    def _write_result_vars(self, entry, columns: List[str],
                           rows: List[Dict[str, Any]], truncated: bool) -> Dict[str, Any]:
        """把結果寫進流程變數，回傳給節點 result 用的摘要"""
        result_var = self.get_config_value('result_var')
        mode = entry.result_mode

        if mode == 'scalar':
            value = rows[0][columns[0]] if rows and columns else None
            self.set_flow_var(result_var, value)
            summary = {'mode': mode, 'value': value, 'row_count': len(rows)}
        elif mode == 'row':
            row = rows[0] if rows else {}
            self.set_flow_var(result_var, row)
            for col, val in row.items():
                if VAR_NAME_RE.match(col or ''):
                    self.set_flow_var(f'{result_var}_{col}', val)
            summary = {'mode': mode, 'row': row, 'row_count': len(rows)}
        else:
            self.set_flow_var(result_var, rows)
            summary = {'mode': mode, 'row_count': len(rows)}

        self.set_flow_var(f'{result_var}_count', len(rows))
        self.set_flow_var(f'{result_var}_found', bool(rows))
        self.set_flow_var(f'{result_var}_truncated', truncated)
        summary['truncated'] = truncated
        return summary

    def _write_approval_note(self, note: str) -> bool:
        """
        插一筆查詢註記到簽核紀錄（與 AiAgent 節點共用同一個出口）。

        approver_secure_code 留 NULL（不是人簽的），action 用 'sql_note'
        以便簽核進度判斷與統計把它排除在有效簽核之外。
        """
        from app import db
        from ...models import FwApprovalRecord

        fi = self.form_instance
        if not fi:
            self.log_warning('SysSqlExecutor: 找不到 form_instance，略過簽核註記')
            return False
        try:
            rec = FwApprovalRecord(
                org_secure_code=self.queue_item.org_secure_code,
                form_instance_secure_code=fi.secure_code,
                workflow_instance_secure_code=self.queue_item.workflow_instance_secure_code,
                node_id=self.queue_item.node_id,
                node_name=self.queue_item.node_name or 'SQL 查詢',
                approver_secure_code=None,
                approver_name='SYSTEM',
                action='sql_note',
                comment=note,
                assigned_at=datetime.utcnow(),
                acted_at=datetime.utcnow(),
                node_queue_secure_code=self.queue_item.secure_code,
            )
            db.session.add(rec)
            db.session.flush()
            return True
        except Exception as e:
            self.log_warning(f'SysSqlExecutor: 寫入簽核註記失敗: {e}')
            return False

    def _maybe_write_note(self, ok: bool) -> bool:
        """
        依設定寫簽核註記。註記內容在流程變數寫完之後才做變數替換，
        所以樣板可以直接引用本節點剛產生的 ${v.xxx}。
        """
        if not self.get_config_value('write_approval_note'):
            return False
        template = self.get_config_value('note_template') or ''
        if not ok:
            # 失敗時只寫固定訊息：DB 錯誤內容可能洩漏 schema，不進使用者看得到的欄位
            return self._write_approval_note('[系統] 查詢未成功，請人工確認資料。')
        body = self.replace_variables(template) if template else ''
        if not body.strip():
            return False
        return self._write_approval_note(sanitize_for_comment(body))

    # ---- 主流程 ---------------------------------------------------------

    def handle(self) -> Dict[str, Any]:
        self.report_running()

        node_type = self.queue_item.node_type
        if not is_node_allowed(node_type, self.queue_item.org_secure_code):
            self.log_error('企業未取得節點授權', {
                'node_type': node_type,
                'org_secure_code': self.queue_item.org_secure_code,
            })
            return {'status': 'error', 'message': f'企業未取得 {node_type} 節點授權'}

        if not self.validate():
            return {'status': 'error', 'message': 'SysSqlExecutor 節點設定不完整', 'data': {}}

        on_error = self.get_config_value('on_error') or 'error'
        result_var = self.get_config_value('result_var')
        error_message: Optional[str] = None
        summary: Dict[str, Any] = {}

        try:
            entry = self._load_procedure()
            self._verify_function(entry)
            values = self._build_params(entry)
            columns, raw_rows, limit = self._execute(entry, values)
            rows, truncated = normalize_rows(raw_rows, columns, limit)
            summary = self._write_result_vars(entry, columns, rows, truncated)
            summary['procedure_code'] = entry.code
        except SqlProcedureRejected as e:
            error_message = str(e)
            self.log_error(f'SysSqlExecutor 拒絕執行: {error_message}')
        except SQLAlchemyError as e:
            # DB 層錯誤（含 statement_timeout 取消）。原文只進 log，不進註記。
            error_message = f'預存程序執行失敗: {type(e).__name__}'
            self.log_error(f'SysSqlExecutor 執行失敗: {e}')
        except Exception as e:  # noqa: BLE001 - 節點不可以把未預期例外丟給 runner
            error_message = f'預存程序執行失敗: {type(e).__name__}'
            self.log_error(f'SysSqlExecutor 未預期錯誤: {e}')

        ok = error_message is None
        if not ok:
            # 讓後續節點看得出這次沒有資料，而不是拿到上一輪的舊值
            self.set_flow_var(f'{result_var}_found', False)
            self.set_flow_var(f'{result_var}_count', 0)
            self.set_flow_var(f'{result_var}_error', error_message)

        wrote_note = self._maybe_write_note(ok)

        payload = dict(summary)
        payload['ok'] = ok
        payload['error'] = error_message
        payload['wrote_note'] = wrote_note

        self.log_info(
            f'SysSqlExecutor 完成: ok={ok} '
            f'procedure={self.get_config_value("procedure_code")}',
            {'result_var': result_var, 'row_count': summary.get('row_count'),
             'truncated': summary.get('truncated'), 'error': error_message})

        if not ok and on_error == 'error':
            return {'status': 'error', 'message': error_message, 'data': payload}

        return {
            'status': 'success',
            'message': (f'查詢完成（{summary.get("row_count", 0)} 筆）'
                        if ok else f'查詢失敗但繼續流程: {error_message}'),
            'data': payload,
        }
