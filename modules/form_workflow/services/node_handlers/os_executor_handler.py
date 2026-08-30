"""
FormWorkflow Module - OsExecutor Handler
OS 命令執行節點處理器

OsExecutor 讓流程在平台主機上執行設計者指定的 shell 命令，權限等同
executor 服務的 OS 帳號。因此它只做「誰能用」的兩道授權閘門：
`OS_NODE_ENABLED` 必須啟用，且企業 secure_code 必須列在系統設定
`os_node_allowed_orgs`。handler 執行期每次重查，設計器可見性不是防線。

本節點採四分法：ok / exception / timeout / dispatched，四種都回
`status='success'`。這是為了避開 `FwNodeExecutionQueue.fail()` 的自動重試；
任意 OS 命令可能有副作用，不能因 exit code 或格式不符就由平台重跑三次。

等待型命令的 stdout/stderr 一律落檔，不用 PIPE。任意命令可能產生大量輸出，
也可能讓孫進程繼承 fd；PIPE 會讓 node_runner 阻塞，造成平台 queue 卡死。

等待型子進程使用 `start_new_session=True` 形成自己的 process group。End cancel
會殺 node_runner 的 process group，碰不到這個子進程，所以執行期間必須安裝
SIGTERM handler，在 node_runner 被終止前用最多 1 秒把 OS 子進程一起收掉。

命令模板中的變數一律 `shlex.quote()` 後代入，只有 `${...!raw}` 明確要求 raw
時才原樣代入。這限制的是填表人或 webhook payload，避免外部輸入冒用流程設計者
的 OS 執行權限。
"""
import hashlib
import json
import os
import re
import shlex
import signal
import subprocess
import tempfile
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from app import db
from app.models import SystemSetting, User

from .base import BaseNodeHandler

NODE_TYPE = 'OsExecutor'
VAR_NAME_RE = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]{0,63}$')
ENV_NAME_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]{0,127}$')
_VAR_RE = re.compile(r'\$\{([^}]+)\}')
UNIT_NAME_RE = re.compile(r'^[A-Za-z0-9_.-]+$')
ANSI_RE = re.compile(r'\x1b\[[0-9;?]*[a-zA-Z]')
CTRL_RE = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')

MIN_TIMEOUT = 1
MAX_TIMEOUT = 3600
DEFAULT_TIMEOUT = 60

OUTPUT_FILE_READ_LIMIT = 1024 * 1024
OUTPUT_VAR_LIMIT = 4096
OUTPUT_LOG_LIMIT = 2048

OUT_DIR_ROOT = '/opt/tmp/osnode'
UNIT_PREFIX = 'bp-'

RESERVED_ENV = ('BP_EXEC', 'BP_ORG', 'BP_WF', 'PATH', 'HOME', 'LANG')

DEFAULT_MAX_CONCURRENT_PER_ORG = 3
CONCURRENCY_RETRY_SECONDS = 15

SIGTERM_GRACE_SECONDS = 1.0
NOTIFY_THROTTLE_MINUTES = 30


class OsExecutorRejected(Exception):
    """設定、授權或啟動階段拒絕。會轉成四分法 exception，不外拋。"""

    def __init__(self, message: str, error_kind: str = 'bad_config'):
        super().__init__(message)
        self.error_kind = error_kind


class OsExecutorConcurrencyLimit(Exception):
    """同企業 OsExecutor 併發已達上限，應轉成 waiting 而不是 exception。"""


def _env_flag_enabled(value: Optional[str]) -> bool:
    return value is not None and value.strip().lower() not in ('', '0', 'false')


def _coerce_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ('1', 'true', 'yes', 'y', 'on')
    return bool(value)


def _coerce_timeout(value: Any) -> int:
    try:
        seconds = int(value)
    except (TypeError, ValueError):
        seconds = DEFAULT_TIMEOUT
    return max(MIN_TIMEOUT, min(MAX_TIMEOUT, seconds))


def _coerce_exit_codes(value: Any) -> List[int]:
    if not isinstance(value, list) or not value:
        return [0]
    codes = []
    for item in value:
        try:
            codes.append(int(item))
        except (TypeError, ValueError):
            continue
    return codes or [0]


def _sanitize_text(value: str) -> str:
    return CTRL_RE.sub('', ANSI_RE.sub('', value or ''))


def _truncate_text(value: str, limit: int) -> str:
    if not value:
        return ''
    return value[:limit]


def _read_output_file(path: str) -> Tuple[str, int, bool, str]:
    if not path or not os.path.exists(path):
        return '', 0, False, hashlib.sha256(b'').hexdigest()

    size = os.path.getsize(path)
    sha = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            sha.update(chunk)

    truncated = size > OUTPUT_FILE_READ_LIMIT
    with open(path, 'rb') as f:
        if truncated:
            half = OUTPUT_FILE_READ_LIMIT // 2
            head = f.read(half)
            f.seek(max(0, size - half))
            tail = f.read(half)
            omitted = size - len(head) - len(tail)
            raw = head + f'\n...(省略 {omitted} bytes)...\n'.encode('utf-8') + tail
        else:
            raw = f.read()

    return _sanitize_text(raw.decode('utf-8', errors='replace')), size, truncated, sha.hexdigest()


class OsExecutorHandler(BaseNodeHandler):
    """OS 命令執行節點。"""

    def __init__(self, queue_item):
        super().__init__(queue_item)
        self._child_process: Optional[subprocess.Popen] = None
        self._child_pgid: Optional[int] = None
        self._sigterm_kill_result = ''

    def validate(self) -> bool:
        return True

    def handle(self) -> Dict[str, Any]:
        self.report_running()

        os_dispatch: Dict[str, Any] = {}
        result_var = str(self.get_config_value('result_var') or '').strip()
        tmp_dir = None

        try:
            self._check_concurrency()
            auth_error = self._authorization_error()
            if auth_error:
                raise OsExecutorRejected(auth_error, 'not_authorized')

            config = self._load_config()
            result_var = config['result_var']
            expanded_command, var_sources = self._expand_command(config['command'])
            extra_env, extra_env_keys = self._build_extra_env(config['extra_env'])
            env = self._build_env(extra_env)

            if config['cwd']:
                cwd = config['cwd']
            else:
                tmp_dir = tempfile.TemporaryDirectory(prefix='osnode-')
                cwd = tmp_dir.name

            unit = self._unit_name() if not config['wait_for_result'] else None
            self._log_before_execute(
                config, expanded_command, var_sources, cwd, extra_env_keys, unit)

            if config['wait_for_result']:
                result, os_dispatch = self._run_waiting(config, expanded_command, cwd, env)
            else:
                result, os_dispatch = self._run_dispatched(
                    config, expanded_command, env, extra_env_keys, unit)

            if config['stop_after']:
                result['skip_advance'] = True
                result['skip_advance_reason'] = 'os_stop_after'
            elif not self._has_outgoing_edges():
                result['skip_advance'] = True
                result['skip_advance_reason'] = 'os_no_outgoing'

            self._write_result_vars(result_var, result)
            self._log_after_execute(result, os_dispatch)
            self._notify_if_needed(result)
            return self._success_response(result, os_dispatch)

        except OsExecutorRejected as e:
            result = self._empty_result()
            result.update({'_result': 'exception', '_error_kind': e.error_kind})
            self._write_result_vars_if_possible(result_var, result)
            self.log_error('OsExecutor 拒絕執行', {
                'error_kind': e.error_kind,
                'reason': str(e),
            })
            self._notify_if_needed(result)
            return self._success_response(result, os_dispatch, message='OsExecutor 未執行')

        except OsExecutorConcurrencyLimit:
            return {
                'status': 'waiting',
                'message': 'OsExecutor 併發已達上限，稍後重試',
                'data': {'retry_after_seconds': CONCURRENCY_RETRY_SECONDS},
            }

        except Exception as e:
            db.session.rollback()
            result = self._empty_result()
            result.update({'_result': 'exception', '_error_kind': 'runtime_error'})
            self._write_result_vars_if_possible(result_var, result)
            self.log_error('OsExecutor 執行例外', {
                'error_kind': 'runtime_error',
                'error': str(e),
            })
            self._notify_if_needed(result)
            return self._success_response(result, os_dispatch, message='OsExecutor 執行例外')

        finally:
            if tmp_dir is not None:
                tmp_dir.cleanup()

    def _authorization_error(self) -> Optional[str]:
        if not _env_flag_enabled(os.environ.get('OS_NODE_ENABLED')):
            return 'OS_NODE_ENABLED 未啟用'

        allowed_orgs = SystemSetting.get('os_node_allowed_orgs', [])
        if not isinstance(allowed_orgs, list):
            allowed_orgs = []
        if self.queue_item.org_secure_code not in allowed_orgs:
            return '企業未列入 os_node_allowed_orgs 白名單'
        return None

    def _check_concurrency(self) -> None:
        from ...models import FwNodeExecutionQueue

        try:
            limit = int(os.environ.get(
                'OS_NODE_MAX_CONCURRENT_PER_ORG',
                DEFAULT_MAX_CONCURRENT_PER_ORG))
        except ValueError:
            limit = DEFAULT_MAX_CONCURRENT_PER_ORG
        limit = max(1, limit)

        running = FwNodeExecutionQueue.query.filter(
            FwNodeExecutionQueue.org_secure_code == self.queue_item.org_secure_code,
            FwNodeExecutionQueue.node_type == NODE_TYPE,
            FwNodeExecutionQueue.status == 'RUNNING',
            FwNodeExecutionQueue.id != self.queue_item.id,
        ).count()
        if running >= limit:
            raise OsExecutorConcurrencyLimit()

    def _load_config(self) -> Dict[str, Any]:
        command = self.get_config_value('command')
        if not isinstance(command, str) or not command.strip():
            raise OsExecutorRejected('command 為必填')

        result_var = self.get_config_value('result_var')
        if not isinstance(result_var, str) or not VAR_NAME_RE.match(result_var):
            raise OsExecutorRejected('result_var 格式不合法')

        cwd = self.get_config_value('cwd')
        if cwd:
            if not isinstance(cwd, str) or not os.path.isdir(cwd):
                raise OsExecutorRejected('cwd 不存在或不是目錄')

        expect_pattern = self.get_config_value('expect_pattern')
        if expect_pattern and (not isinstance(expect_pattern, str) or len(expect_pattern) > 200):
            raise OsExecutorRejected('expect_pattern 格式不合法或超過 200 字元')

        kill_on_timeout = self.get_config_value('kill_on_timeout') or 'group'
        if kill_on_timeout not in ('group', 'process', 'none'):
            raise OsExecutorRejected('kill_on_timeout 必須是 group/process/none')

        cancel_scope = self.get_config_value('cancel_scope') or 'unit'
        if cancel_scope not in ('unit', 'detach'):
            raise OsExecutorRejected('cancel_scope 必須是 unit/detach')

        extra_env = self.get_config_value('extra_env') or {}
        if not isinstance(extra_env, dict):
            raise OsExecutorRejected('extra_env 必須是物件')

        return {
            'command': command.strip(),
            'result_var': result_var,
            'timeout_seconds': _coerce_timeout(
                self.get_config_value('timeout_seconds', DEFAULT_TIMEOUT)),
            'wait_for_result': _coerce_bool(
                self.get_config_value('wait_for_result'), True),
            'expect_exit_codes': _coerce_exit_codes(
                self.get_config_value('expect_exit_codes')),
            'expect_pattern': expect_pattern or '',
            'expect_json': _coerce_bool(self.get_config_value('expect_json'), False),
            'cwd': cwd or '',
            'extra_env': extra_env,
            'kill_on_timeout': kill_on_timeout,
            'cancel_scope': cancel_scope,
            'stop_after': _coerce_bool(self.get_config_value('stop_after'), False),
            'notify_on_exception': _coerce_bool(
                self.get_config_value('notify_on_exception'), True),
        }

    def _expand_command(self, template: str) -> Tuple[str, List[Dict[str, Any]]]:
        sources: List[Dict[str, Any]] = []

        def replace(match):
            expr = match.group(1)
            raw = expr.endswith('!raw')
            lookup_expr = expr[:-4] if raw else expr
            value = self.replace_variables('${' + lookup_expr + '}')
            value = '' if value is None else str(value)
            sources.append({'expr': lookup_expr, 'raw': raw, 'value_len': len(value)})
            return value if raw else shlex.quote(value)

        return _VAR_RE.sub(replace, template), sources

    def _expand_env_value(self, template: Any) -> str:
        if template is None:
            return ''

        def replace(match):
            expr = match.group(1)
            lookup_expr = expr[:-4] if expr.endswith('!raw') else expr
            value = self.replace_variables('${' + lookup_expr + '}')
            return '' if value is None else str(value)

        return _VAR_RE.sub(replace, str(template))

    def _build_extra_env(self, extra_env: Dict[str, Any]) -> Tuple[Dict[str, str], List[str]]:
        env = {}
        for key, value in extra_env.items():
            if not isinstance(key, str) or not ENV_NAME_RE.match(key):
                raise OsExecutorRejected(f'extra_env 名稱不合法: {key}')
            if key in RESERVED_ENV:
                raise OsExecutorRejected(f'extra_env 不可覆蓋保留變數: {key}')
            env[key] = self._expand_env_value(value)
        return env, sorted(env.keys())

    def _build_env(self, extra_env: Dict[str, str]) -> Dict[str, str]:
        env = {
            'HOME': os.environ.get('HOME') or os.path.expanduser('~'),
            'PATH': os.environ.get('PATH') or '/usr/local/bin:/usr/bin:/bin',
            'LANG': 'en_US.UTF-8',
            'BP_EXEC': self.queue_item.secure_code,
            'BP_ORG': self.queue_item.org_secure_code or '',
            'BP_WF': self.queue_item.workflow_instance_secure_code or '',
        }
        env.update(extra_env)
        return env

    def _unit_name(self) -> str:
        unit = f'{UNIT_PREFIX}{self.queue_item.secure_code}'
        if not UNIT_NAME_RE.match(unit) or not unit.startswith(UNIT_PREFIX):
            raise OsExecutorRejected('queue secure_code 不符合 systemd unit 名稱限制')
        return unit

    def _has_outgoing_edges(self) -> bool:
        graph = {}
        if self.workflow_instance:
            graph = self.workflow_instance.graph_snapshot or {}
            if not graph:
                from ...models import FwWorkflowTemplate
                template = FwWorkflowTemplate.query.filter_by(
                    secure_code=self.workflow_instance.workflow_template_secure_code,
                    is_deleted=False,
                ).first()
                graph = template.graph if template else {}

        for edge in graph.get('edges', []):
            edge_data = edge.get('data', edge)
            if edge_data.get('source') == self.queue_item.node_id:
                return True
        return False

    def _output_paths(self) -> Tuple[str, str]:
        day_dir = os.path.join(OUT_DIR_ROOT, datetime.utcnow().strftime('%Y%m%d'))
        os.makedirs(day_dir, mode=0o750, exist_ok=True)
        return (
            os.path.join(day_dir, f'{self.queue_item.secure_code}.out'),
            os.path.join(day_dir, f'{self.queue_item.secure_code}.err'),
        )

    def _run_waiting(
        self,
        config: Dict[str, Any],
        expanded_command: str,
        cwd: str,
        env: Dict[str, str],
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        out_path, err_path = self._output_paths()
        start = time.monotonic()
        exit_code = None
        killed = ''
        old_handler = None
        result_kind = 'exception'
        error_kind = ''

        with open(out_path, 'wb') as out_file, open(err_path, 'wb') as err_file:
            proc = subprocess.Popen(
                ['/bin/bash', '-c', expanded_command],
                stdin=subprocess.DEVNULL,
                stdout=out_file,
                stderr=err_file,
                cwd=cwd,
                env=env,
                start_new_session=True,
            )
            self._child_process = proc
            try:
                self._child_pgid = os.getpgid(proc.pid)
            except OSError:
                self._child_pgid = None

            os_dispatch = {
                'mode': 'subprocess',
                'pid': proc.pid,
                'pgid': self._child_pgid,
                'unit': None,
                'mark': self.queue_item.secure_code,
                'cancel_scope': 'unit',
            }
            self._store_os_dispatch(os_dispatch)
            old_handler = self._install_sigterm_handler()

            try:
                exit_code = proc.wait(timeout=config['timeout_seconds'])
            except subprocess.TimeoutExpired:
                result_kind = 'timeout'
                error_kind = 'timeout'
                killed = self._terminate_child(proc, config['kill_on_timeout'], 3.0)
                if config['kill_on_timeout'] == 'none':
                    self.log_warning('OsExecutor 逾時但依設定不殺進程', {
                        'pid': proc.pid,
                        'kill_on_timeout': 'none',
                    })

        if old_handler is not None:
            self._restore_sigterm_handler(old_handler)
        self._child_process = None
        self._child_pgid = None

        duration_ms = int((time.monotonic() - start) * 1000)
        stdout, stdout_len, stdout_truncated, stdout_sha = _read_output_file(out_path)
        stderr, stderr_len, stderr_truncated, _stderr_sha = _read_output_file(err_path)
        truncated = stdout_truncated or stderr_truncated

        if result_kind != 'timeout':
            result_kind, error_kind = self._classify_finished(
                exit_code, stdout, config['expect_exit_codes'],
                config['expect_pattern'], config['expect_json'])

        result = {
            '_result': result_kind,
            '_exit_code': exit_code,
            '_stdout': _truncate_text(stdout, OUTPUT_VAR_LIMIT),
            '_stderr': _truncate_text(stderr, OUTPUT_VAR_LIMIT),
            '_duration_ms': duration_ms,
            '_truncated': truncated,
            '_killed': killed,
            '_pid': proc.pid,
            '_unit': '',
            '_error_kind': error_kind,
            '_stdout_len': stdout_len,
            '_stderr_len': stderr_len,
            '_stdout_log': _truncate_text(stdout, OUTPUT_LOG_LIMIT),
            '_stderr_log': _truncate_text(stderr, OUTPUT_LOG_LIMIT),
            '_stdout_sha256': stdout_sha,
            '_stdout_path': out_path,
            '_stderr_path': err_path,
        }
        return result, os_dispatch

    def _run_dispatched(
        self,
        config: Dict[str, Any],
        expanded_command: str,
        env: Dict[str, str],
        extra_env_keys: List[str],
        unit: str,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        argv = [
            'sudo', '-n', 'systemd-run',
            f'--uid={os.getuid()}',
            f'--unit={unit}',
            f'--setenv=BP_EXEC={env["BP_EXEC"]}',
            f'--setenv=BP_ORG={env["BP_ORG"]}',
            f'--setenv=BP_WF={env["BP_WF"]}',
        ]
        for key in extra_env_keys:
            argv.append(f'--setenv={key}={env[key]}')
        argv.extend(['/bin/bash', '-c', expanded_command])

        start = time.monotonic()
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=30,
            env=self._build_env({}),
        )
        duration_ms = int((time.monotonic() - start) * 1000)

        stdout = _sanitize_text(proc.stdout or '')
        stderr = _sanitize_text(proc.stderr or '')
        if proc.returncode != 0:
            raise OsExecutorRejected(
                f'systemd-run 提交失敗: {stderr[:200] or stdout[:200]}',
                'dispatch_failed')

        os_dispatch = {
            'mode': 'systemd_run',
            'pid': None,
            'pgid': None,
            'unit': unit,
            'mark': self.queue_item.secure_code,
            'cancel_scope': config['cancel_scope'],
        }
        self._store_os_dispatch(os_dispatch)

        return {
            '_result': 'dispatched',
            '_exit_code': None,
            '_stdout': _truncate_text(stdout, OUTPUT_VAR_LIMIT),
            '_stderr': _truncate_text(stderr, OUTPUT_VAR_LIMIT),
            '_duration_ms': duration_ms,
            '_truncated': len(stdout) > OUTPUT_VAR_LIMIT or len(stderr) > OUTPUT_VAR_LIMIT,
            '_killed': '',
            '_pid': None,
            '_unit': unit,
            '_error_kind': '',
            '_stdout_len': len(stdout),
            '_stderr_len': len(stderr),
            '_stdout_log': _truncate_text(stdout, OUTPUT_LOG_LIMIT),
            '_stderr_log': _truncate_text(stderr, OUTPUT_LOG_LIMIT),
            '_stdout_sha256': hashlib.sha256((proc.stdout or '').encode('utf-8')).hexdigest(),
            '_stdout_path': '',
            '_stderr_path': '',
        }, os_dispatch

    def _classify_finished(
        self,
        exit_code: Optional[int],
        stdout: str,
        expect_exit_codes: List[int],
        expect_pattern: str,
        expect_json: bool,
    ) -> Tuple[str, str]:
        if exit_code not in expect_exit_codes:
            return 'exception', 'exit_code'

        if expect_pattern:
            try:
                if re.search(expect_pattern, stdout) is None:
                    return 'exception', 'expect_pattern'
            except re.error:
                return 'exception', 'expect_pattern_invalid'

        if expect_json:
            try:
                json.loads(stdout)
            except Exception:
                return 'exception', 'expect_json'

        return 'ok', ''

    def _store_os_dispatch(self, os_dispatch: Dict[str, Any]) -> None:
        self.queue_item.result = {'os_dispatch': os_dispatch}
        db.session.commit()

    def _install_sigterm_handler(self):
        try:
            return signal.signal(signal.SIGTERM, self._on_sigterm)
        except ValueError as e:
            self.log_warning('OsExecutor 無法安裝 SIGTERM handler', {'error': str(e)})
            return None

    def _restore_sigterm_handler(self, old_handler) -> None:
        try:
            signal.signal(signal.SIGTERM, old_handler)
        except ValueError as e:
            self.log_warning('OsExecutor 無法還原 SIGTERM handler', {'error': str(e)})

    def _on_sigterm(self, signum, frame) -> None:
        if self._child_process is not None:
            try:
                self._sigterm_kill_result = self._terminate_child(
                    self._child_process, 'group', SIGTERM_GRACE_SECONDS)
            except Exception:
                pass
        os._exit(143)

    def _terminate_child(
        self,
        proc: subprocess.Popen,
        mode: str,
        grace_seconds: float,
    ) -> str:
        if mode == 'none':
            return 'none'

        target_group = mode == 'group'
        try:
            if target_group:
                pgid = self._child_pgid or os.getpgid(proc.pid)
                os.killpg(pgid, signal.SIGTERM)
            else:
                os.kill(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            return f'{mode}_already_gone'

        deadline = time.monotonic() + grace_seconds
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                return f'{mode}_sigterm'
            time.sleep(0.1)

        try:
            if target_group:
                pgid = self._child_pgid or os.getpgid(proc.pid)
                os.killpg(pgid, signal.SIGKILL)
            else:
                os.kill(proc.pid, signal.SIGKILL)
            proc.wait(timeout=1)
            return f'{mode}_sigkill'
        except ProcessLookupError:
            return f'{mode}_already_gone'
        except subprocess.TimeoutExpired:
            return f'{mode}_sigkill_pending'

    def _empty_result(self) -> Dict[str, Any]:
        return {
            '_result': 'exception',
            '_exit_code': None,
            '_stdout': '',
            '_stderr': '',
            '_duration_ms': 0,
            '_truncated': False,
            '_killed': '',
            '_pid': None,
            '_unit': '',
            '_error_kind': '',
        }

    def _write_result_vars_if_possible(self, result_var: str, result: Dict[str, Any]) -> None:
        if result_var and VAR_NAME_RE.match(result_var):
            self._write_result_vars(result_var, result)

    def _write_result_vars(self, result_var: str, result: Dict[str, Any]) -> None:
        for suffix in (
            '_result', '_exit_code', '_stdout', '_stderr', '_duration_ms',
            '_truncated', '_killed', '_pid', '_unit', '_error_kind',
        ):
            self.set_flow_var(f'{result_var}{suffix}', result.get(suffix))

    def _success_response(
        self,
        result: Dict[str, Any],
        os_dispatch: Dict[str, Any],
        message: Optional[str] = None,
    ) -> Dict[str, Any]:
        public_result = {
            key: result.get(key)
            for key in (
                '_result', '_exit_code', '_stdout', '_stderr', '_duration_ms',
                '_truncated', '_killed', '_pid', '_unit', '_error_kind',
                'skip_advance', 'skip_advance_reason',
            )
            if key in result
        }
        return {
            'status': 'success',
            'message': message or f"OsExecutor: {result.get('_result')}",
            'data': public_result,
            'os_dispatch': os_dispatch,
        }

    def _log_before_execute(
        self,
        config: Dict[str, Any],
        expanded_command: str,
        var_sources: List[Dict[str, Any]],
        cwd: str,
        extra_env_keys: List[str],
        unit: Optional[str],
    ) -> None:
        # WorkflowLogService 每筆 log 都 commit；這筆必須在 Popen/systemd-run 前落地，
        # 否則機器斷電或 node_runner 被 SIGKILL 時會失去追責線索。
        self.log_info('OsExecutor 即將執行命令', {
            'command_template': config['command'],
            'command_expanded': expanded_command,
            'var_sources': var_sources,
            'cwd': cwd,
            'timeout_seconds': config['timeout_seconds'],
            'wait_for_result': config['wait_for_result'],
            'extra_env_keys': extra_env_keys,
            'run_as_uid': os.getuid(),
            'bp_exec': self.queue_item.secure_code,
            'unit': unit,
        })

    def _log_after_execute(self, result: Dict[str, Any], os_dispatch: Dict[str, Any]) -> None:
        details = {
            'result': result.get('_result'),
            'exit_code': result.get('_exit_code'),
            'duration_ms': result.get('_duration_ms'),
            'stdout_len': result.get('_stdout_len'),
            'stderr_len': result.get('_stderr_len'),
            'truncated': result.get('_truncated'),
            'killed': result.get('_killed'),
            'stdout_head': result.get('_stdout_log'),
            'stderr_head': result.get('_stderr_log'),
            'stdout_sha256': result.get('_stdout_sha256'),
            'stdout_path': result.get('_stdout_path'),
            'stderr_path': result.get('_stderr_path'),
            'error_kind': result.get('_error_kind'),
            'os_dispatch': os_dispatch,
        }
        if result.get('_result') in ('ok', 'dispatched'):
            self.log_info('OsExecutor 執行完成', details)
        else:
            self.log_error('OsExecutor 執行異常', details)

    def _notify_if_needed(self, result: Dict[str, Any]) -> None:
        if result.get('_result') not in ('exception', 'timeout'):
            return
        if _coerce_bool(self.get_config_value('notify_on_exception'), True) is False:
            return

        try:
            message = f"OsExecutor 例外通知已送出: {self.queue_item.node_id}/{result.get('_result')}"
            from ...models import FwNodeExecutionLog, FwWorkflowTemplate

            cutoff = datetime.utcnow() - timedelta(minutes=NOTIFY_THROTTLE_MINUTES)
            recent = FwNodeExecutionLog.query.filter(
                FwNodeExecutionLog.org_secure_code == self.queue_item.org_secure_code,
                FwNodeExecutionLog.node_id == self.queue_item.node_id,
                FwNodeExecutionLog.log_message == message,
                FwNodeExecutionLog.created_at > cutoff,
            ).first()
            if recent:
                return

            recipients = self.get_config_value('notify_to')
            if not isinstance(recipients, list) or not recipients:
                recipients = []
                if self.workflow_instance and self.workflow_instance.workflow_template_secure_code:
                    template = FwWorkflowTemplate.query.filter_by(
                        secure_code=self.workflow_instance.workflow_template_secure_code,
                        is_deleted=False,
                    ).first()
                    if template and template.updated_by_secure_code:
                        recipients = [template.updated_by_secure_code]

            if not recipients:
                self.log_warning('OsExecutor 例外通知略過：沒有可用收件人')
                return

            users = User.query.filter(
                User.secure_code.in_(recipients),
                User.org_secure_code == self.queue_item.org_secure_code,
                User.is_deleted.is_(False),
                User.is_active.is_(True),
                User.email.isnot(None),
            ).all()
            if not users:
                self.log_warning('OsExecutor 例外通知略過：收件人不存在或已停用')
                return

            from app.services.email_service import EmailService

            title = f"OsExecutor 節點異常: {result.get('_result')}"
            content = (
                f"節點：{self.queue_item.node_name or self.queue_item.node_id}\n"
                f"流程：{self.queue_item.workflow_instance_secure_code}\n"
                f"結果：{result.get('_result')}\n"
                f"錯誤類型：{result.get('_error_kind') or ''}\n"
                f"Queue：{self.queue_item.secure_code}"
            )
            for user in users:
                EmailService.send_notification(user.email, title, content)
            self.log_info(message, {'recipient_count': len(users)})
        except Exception as e:
            self.log_warning('OsExecutor 例外通知失敗', {'error': str(e)})
