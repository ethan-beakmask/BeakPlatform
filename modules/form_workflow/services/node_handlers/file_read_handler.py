"""
FormWorkflow Module - FileRead Handler
檔案讀取節點處理器

FileRead 不是 OsExecutor 的配套節點，而是刻意獨立的低一階授權能力：它不經 shell、
只做唯讀檔案讀取，且讀取路徑必須鎖在允許的 base_dir 之下。因此企業可以只取得
讀 log 或狀態檔的能力，而不必同時取得平台主機命令執行權限。

本節點有三道護欄：`FILE_READ_NODE_ENABLED` 執行期開關、通用節點企業授權，
以及平台設定、企業設定、節點設定三層 base_dir 交集。所有路徑都用 realpath
後再以 commonpath 驗證，避免 `../` 與 symlink 逃逸。

結果語彙沿用外部世界節點的四分法精神：ok / exception / timeout 都回
`status='success'`。這是為了避開 `FwNodeExecutionQueue.fail()` 的自動重試；
授權拒絕、檔案不存在或掃描逾時重試三次沒有意義，也會干擾流程語意。

`max_scan_ms` 只能在行與行之間檢查，對單次 Python `re.search()` 卡住無效。
因此 regex 模式在 v1 以樣式長度與單行輸入 64KB 上限控制最壞情況；真正的
regex timeout 留待 v2 改用支援 timeout 的第三方套件。
"""
import os
import re
import time
from collections import deque
from datetime import datetime
from typing import Any, Deque, Dict, Iterable, List, Optional, Pattern, Tuple

from app import db
from app.models import SystemSetting
from modules.form_workflow.services.node_grant_service import is_node_allowed

from .base import BaseNodeHandler

NODE_TYPE = 'FileRead'
VAR_NAME_RE = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]{0,63}$')
ANSI_RE = re.compile(r'\x1b\[[0-9;?]*[a-zA-Z]')
CTRL_RE = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')

MODES = ('whole', 'head', 'tail', 'around')
OCCURRENCES = ('first', 'last', 'all')
MATCH_SCOPES = ('anywhere', 'line_start')
MATCH_MODES = ('literal', 'regex')

DEFAULT_LINES = 50
MAX_LINES = 5000
DEFAULT_BEFORE = 3
DEFAULT_AFTER = 3
MAX_CONTEXT_LINES = 200
DEFAULT_MAX_WINDOWS = 10
MAX_WINDOWS_HARD = 100

MAX_READ_BYTES = 256 * 1024
DEFAULT_MAX_SCAN_BYTES = 64 * 1024 * 1024
MAX_SCAN_BYTES_HARD = 512 * 1024 * 1024
DEFAULT_MAX_SCAN_MS = 5000
MAX_SCAN_MS_HARD = 60000

MAX_LINE_BYTES = 64 * 1024
MAX_PATTERN_CHARS = 200
TAIL_BLOCK_SIZE = 64 * 1024
OUTPUT_LOG_LIMIT = 2048


class FileReadRejected(Exception):
    """設定、授權或讀取階段拒絕。會轉成 success/exception，不外拋。"""

    def __init__(self, message: str, error_kind: str = 'bad_config'):
        super().__init__(message)
        self.error_kind = error_kind


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


def _coerce_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(maximum, number))


def _sanitize_text(value: str) -> str:
    return CTRL_RE.sub('', ANSI_RE.sub('', value or ''))


def _decode_line(raw: bytes, encoding: str) -> str:
    return _sanitize_text(raw.decode(encoding, errors='replace').rstrip('\n'))


def _is_under_path(path: str, base_dir: str) -> bool:
    try:
        return os.path.commonpath([path, base_dir]) == base_dir
    except ValueError:
        return False


class FileReadHandler(BaseNodeHandler):
    """唯讀檔案讀取節點。"""

    def validate(self) -> bool:
        return True

    def handle(self) -> Dict[str, Any]:
        self.report_running()

        start = time.monotonic()
        result_var = str(self.get_config_value('result_var') or '').strip()
        config: Dict[str, Any] = {}
        result = self._empty_result()

        try:
            self._check_authorized()
            config = self._load_config()
            result_var = config['result_var']
            base_dir, file_path = self._resolve_allowed_paths(config)
            config['base_dir_real'] = base_dir
            config['file_path_real'] = file_path

            file_stat = os.stat(file_path)
            result['_file_size'] = int(file_stat.st_size)
            result['_file_mtime'] = datetime.utcfromtimestamp(
                file_stat.st_mtime).isoformat() + 'Z'

            self._log_before_read(config)
            read_result = self._read_file(config, file_path, file_stat.st_size)
            result.update(read_result)
            result['_result'] = result.get('_result') or 'ok'

        except FileReadRejected as e:
            result['_result'] = 'exception'
            result['_error_kind'] = e.error_kind
            self.log_error('FileRead 拒絕讀取', {
                'error_kind': e.error_kind,
                'reason': str(e),
            })

        except (FileNotFoundError, PermissionError, OSError) as e:
            result['_result'] = 'exception'
            result['_error_kind'] = self._io_error_kind(e)
            self.log_error('FileRead 讀取例外', {
                'error_kind': result['_error_kind'],
                'error': str(e),
            })

        except Exception as e:
            db.session.rollback()
            result['_result'] = 'exception'
            result['_error_kind'] = 'runtime_error'
            self.log_error('FileRead 執行例外', {
                'error_kind': 'runtime_error',
                'error': str(e),
            })

        finally:
            result['_duration_ms'] = int((time.monotonic() - start) * 1000)
            self._write_result_vars_if_possible(result_var, result)
            self._log_after_read(result)

        if _coerce_bool(self.get_config_value('stop_after'), False):
            result['skip_advance'] = True
            result['skip_advance_reason'] = 'fileread_stop_after'
        elif not self._has_outgoing_edges():
            result['skip_advance'] = True
            result['skip_advance_reason'] = 'fileread_no_outgoing'

        return self._success_response(result)

    def _check_authorized(self) -> None:
        if not _env_flag_enabled(os.environ.get('FILE_READ_NODE_ENABLED')):
            raise FileReadRejected('FILE_READ_NODE_ENABLED 未啟用', 'not_authorized')

        if not is_node_allowed(NODE_TYPE, self.queue_item.org_secure_code):
            raise FileReadRejected('企業未取得 FileRead 節點授權', 'not_authorized')

    def _load_config(self) -> Dict[str, Any]:
        result_var = self.get_config_value('result_var')
        if not isinstance(result_var, str) or not VAR_NAME_RE.match(result_var):
            raise FileReadRejected('result_var 格式不合法')

        base_dir = self.get_config_value('base_dir')
        if not isinstance(base_dir, str) or not base_dir.strip():
            raise FileReadRejected('base_dir 為必填')

        file_path = self.get_config_value('file_path')
        if not isinstance(file_path, str) or not file_path.strip():
            raise FileReadRejected('file_path 為必填')

        mode = self.get_config_value('mode') or 'whole'
        if mode not in MODES:
            raise FileReadRejected('mode 必須是 whole/head/tail/around')

        occurrence = self.get_config_value('occurrence') or 'first'
        if occurrence not in OCCURRENCES:
            raise FileReadRejected('occurrence 必須是 first/last/all')

        match_scope = self.get_config_value('match_scope') or 'anywhere'
        if match_scope not in MATCH_SCOPES:
            raise FileReadRejected('match_scope 必須是 anywhere/line_start')

        match_mode = self.get_config_value('match_mode') or 'literal'
        if match_mode not in MATCH_MODES:
            raise FileReadRejected('match_mode 必須是 literal/regex')

        keyword = ''
        if mode == 'around':
            raw_keyword = self.get_config_value('keyword')
            if not isinstance(raw_keyword, str) or raw_keyword == '':
                raise FileReadRejected('around 模式 keyword 為必填')
            keyword = self.replace_variables(raw_keyword)
            if match_mode == 'regex' and len(keyword) > MAX_PATTERN_CHARS:
                raise FileReadRejected('regex 樣式超過 200 字元', 'bad_pattern')

        return {
            'base_dir': base_dir.strip(),
            'file_path': self.replace_variables(file_path),
            'result_var': result_var,
            'mode': mode,
            'lines': _coerce_int(self.get_config_value('lines'), DEFAULT_LINES, 1, MAX_LINES),
            'keyword': keyword,
            'before': _coerce_int(
                self.get_config_value('before'), DEFAULT_BEFORE, 0, MAX_CONTEXT_LINES),
            'after': _coerce_int(
                self.get_config_value('after'), DEFAULT_AFTER, 0, MAX_CONTEXT_LINES),
            'occurrence': occurrence,
            'max_windows': _coerce_int(
                self.get_config_value('max_windows'), DEFAULT_MAX_WINDOWS, 1, MAX_WINDOWS_HARD),
            'match_scope': match_scope,
            'match_mode': match_mode,
            'max_scan_bytes': _coerce_int(
                self.get_config_value('max_scan_bytes'),
                DEFAULT_MAX_SCAN_BYTES,
                1,
                MAX_SCAN_BYTES_HARD,
            ),
            'max_scan_ms': _coerce_int(
                self.get_config_value('max_scan_ms'), DEFAULT_MAX_SCAN_MS, 1, MAX_SCAN_MS_HARD),
            'encoding': str(self.get_config_value('encoding') or 'utf-8'),
            'stop_after': _coerce_bool(self.get_config_value('stop_after'), False),
        }

    def _resolve_allowed_paths(self, config: Dict[str, Any]) -> Tuple[str, str]:
        node_base = os.path.realpath(config['base_dir'])
        if not os.path.isdir(node_base):
            raise FileReadRejected('base_dir 不存在或不是目錄', 'path_denied')

        platform_dirs = self._real_existing_dirs(SystemSetting.get('file_read_base_dirs', []))
        if not platform_dirs:
            raise FileReadRejected('file_read_base_dirs 未設定允許目錄', 'path_denied')

        org_map = SystemSetting.get('file_read_org_base_dirs', {})
        if not isinstance(org_map, dict):
            org_map = {}
        if self.queue_item.org_secure_code in org_map:
            org_dirs = self._real_existing_dirs(org_map.get(self.queue_item.org_secure_code))
        else:
            org_dirs = platform_dirs
        if not org_dirs:
            raise FileReadRejected('企業沒有可用的 file_read_org_base_dirs', 'path_denied')

        if not self._under_any(node_base, platform_dirs) or not self._under_any(node_base, org_dirs):
            raise FileReadRejected('base_dir 不在平台與企業允許目錄交集內', 'path_denied')

        requested_path = config['file_path']
        if os.path.isabs(requested_path):
            file_path = os.path.realpath(requested_path)
        else:
            file_path = os.path.realpath(os.path.join(node_base, requested_path))

        if not _is_under_path(file_path, node_base):
            raise FileReadRejected('file_path 不在 base_dir 之下', 'path_denied')
        if not os.path.isfile(file_path):
            raise FileReadRejected('file_path 不存在或不是一般檔案', 'path_denied')
        return node_base, file_path

    def _real_existing_dirs(self, value: Any) -> List[str]:
        if not isinstance(value, list):
            return []
        dirs = []
        for item in value:
            if not isinstance(item, str) or not item.strip():
                continue
            real = os.path.realpath(item.strip())
            if os.path.isdir(real):
                dirs.append(real)
        return dirs

    def _under_any(self, path: str, dirs: Iterable[str]) -> bool:
        return any(_is_under_path(path, base_dir) for base_dir in dirs)

    def _read_file(self, config: Dict[str, Any], file_path: str, file_size: int) -> Dict[str, Any]:
        mode = config['mode']
        if mode == 'whole':
            lines, truncated = self._read_whole(file_path, config['encoding'], file_size)
            return self._content_result(lines, truncated)
        if mode == 'head':
            lines, truncated = self._read_head(file_path, config['encoding'], config['lines'])
            return self._content_result(lines, truncated)
        if mode == 'tail':
            lines, truncated = self._read_tail(file_path, config['encoding'], config['lines'])
            return self._content_result(lines, truncated)
        return self._read_around(file_path, config)

    def _read_whole(self, file_path: str, encoding: str, file_size: int) -> Tuple[List[str], bool]:
        with open(file_path, 'rb') as f:
            raw = f.read(MAX_READ_BYTES + 1)
        truncated = file_size > MAX_READ_BYTES or len(raw) > MAX_READ_BYTES
        if truncated:
            raw = raw[:MAX_READ_BYTES]
            last_newline = raw.rfind(b'\n')
            if last_newline >= 0:
                raw = raw[:last_newline + 1]
        return self._raw_to_lines(raw, encoding), truncated

    def _read_head(self, file_path: str, encoding: str, lines: int) -> Tuple[List[str], bool]:
        output: List[str] = []
        collected = 0
        truncated = False
        with open(file_path, 'rb') as f:
            while len(output) < lines and collected < MAX_READ_BYTES:
                raw = f.readline(MAX_READ_BYTES - collected + 1)
                if not raw:
                    break
                if collected + len(raw) > MAX_READ_BYTES:
                    raw = raw[:MAX_READ_BYTES - collected]
                    truncated = True
                collected += len(raw)
                output.append(_decode_line(raw, encoding))
                if truncated:
                    break
        return output, truncated

    def _read_tail(self, file_path: str, encoding: str, lines: int) -> Tuple[List[str], bool]:
        file_size = os.path.getsize(file_path)
        blocks: Deque[bytes] = deque()
        position = file_size
        newline_count = 0
        collected = 0

        with open(file_path, 'rb') as f:
            while position > 0 and newline_count <= lines and collected < MAX_READ_BYTES:
                read_size = min(TAIL_BLOCK_SIZE, position, MAX_READ_BYTES - collected)
                position -= read_size
                f.seek(position)
                block = f.read(read_size)
                blocks.appendleft(block)
                newline_count += block.count(b'\n')
                collected += len(block)

        raw = b''.join(blocks)
        parts = raw.split(b'\n')
        if parts and parts[-1] == b'':
            parts = parts[:-1]
        selected = parts[-lines:] if lines else []
        output = [_sanitize_text(part.decode(encoding, errors='replace')) for part in selected]
        # 只有「撞到 MAX_READ_BYTES 才停」算截斷。湊滿 lines 行就停是 tail 的正常行為，
        # 標成截斷會讓這個旗標對 tail 完全失去鑑別力（大檔的 tail 永遠是 True）。
        truncated = collected >= MAX_READ_BYTES and position > 0
        return output, truncated

    def _read_around(self, file_path: str, config: Dict[str, Any]) -> Dict[str, Any]:
        matcher = self._compile_matcher(config)
        before = config['before']
        after = config['after']
        occurrence = config['occurrence']
        max_windows = config['max_windows']
        max_scan_bytes = config['max_scan_bytes']
        deadline = time.monotonic() + (config['max_scan_ms'] / 1000)

        previous: Deque[Tuple[int, str]] = deque(maxlen=before)
        windows: List[List[str]] = []
        last_window: List[str] = []
        current: Optional[Dict[str, Any]] = None
        match_count = 0
        scan_truncated = False
        line_truncated = False
        timed_out = False
        bytes_seen = 0

        for line_no, raw_line, consumed, was_line_truncated in self._iter_limited_lines(
            file_path, config['encoding'], max_scan_bytes):
            bytes_seen += consumed
            if was_line_truncated:
                line_truncated = True

            if line_no % 500 == 0 and time.monotonic() > deadline:
                timed_out = True
                scan_truncated = True
                break

            if current and line_no > current['end']:
                finished = current['lines']
                if occurrence == 'last':
                    last_window = finished
                else:
                    windows.append(finished)
                    if occurrence == 'first' or len(windows) >= max_windows:
                        # 先清掉 current 再 break，否則迴圈後的收尾會把同一個窗口
                        # 再 append 一次（症狀：輸出重複同一段並多出一條 -- 分隔線）
                        current = None
                        scan_truncated = True
                        break
                current = None

            matched = self._match_line(raw_line, config, matcher)
            if matched:
                match_count += 1
                start = max(1, line_no - before)
                end = line_no + after
                if current and start <= current['end'] + 1:
                    current['end'] = max(current['end'], end)
                    if not current['lines'] or current['last_line_no'] != line_no:
                        current['lines'].append(raw_line)
                        current['last_line_no'] = line_no
                else:
                    context = [text for prev_no, text in previous if prev_no >= start]
                    context.append(raw_line)
                    current = {'end': end, 'lines': context, 'last_line_no': line_no}
            elif current and line_no <= current['end']:
                current['lines'].append(raw_line)
                current['last_line_no'] = line_no

            previous.append((line_no, raw_line))
            if bytes_seen >= max_scan_bytes:
                scan_truncated = True
                break

        if current:
            if occurrence == 'last':
                last_window = current['lines']
            elif len(windows) < max_windows:
                windows.append(current['lines'])
            else:
                scan_truncated = True

        if occurrence == 'last':
            windows = [last_window] if last_window else []

        lines = self._join_windows(windows)
        content = '\n'.join(lines)
        truncated = False
        if len(content.encode(config['encoding'], errors='replace')) > MAX_READ_BYTES:
            content = content.encode(config['encoding'], errors='replace')[:MAX_READ_BYTES].decode(
                config['encoding'], errors='replace')
            lines = content.splitlines()
            truncated = True

        return {
            '_result': 'timeout' if timed_out else 'ok',
            '_content': content,
            '_lines': lines,
            '_match_count': match_count,
            '_truncated': truncated,
            '_scan_truncated': scan_truncated,
            '_line_truncated': line_truncated,
            '_error_kind': 'scan_timeout' if timed_out else '',
        }

    def _iter_limited_lines(
        self,
        file_path: str,
        encoding: str,
        max_scan_bytes: int,
    ) -> Iterable[Tuple[int, str, int, bool]]:
        consumed_total = 0
        line_no = 0
        with open(file_path, 'rb') as f:
            while consumed_total < max_scan_bytes:
                raw = f.readline(MAX_LINE_BYTES + 1)
                if not raw:
                    break
                consumed = len(raw)
                had_newline = raw.endswith(b'\n')
                line_truncated = len(raw) > MAX_LINE_BYTES
                if line_truncated:
                    raw = raw[:MAX_LINE_BYTES]
                    while consumed_total + consumed < max_scan_bytes and not had_newline:
                        rest = f.readline(TAIL_BLOCK_SIZE)
                        if not rest:
                            break
                        consumed += len(rest)
                        if rest.endswith(b'\n'):
                            break
                consumed_total += consumed
                line_no += 1
                yield line_no, _decode_line(raw, encoding), consumed, line_truncated

    def _compile_matcher(self, config: Dict[str, Any]) -> Optional[Pattern[str]]:
        if config['match_mode'] != 'regex':
            return None
        try:
            return re.compile(config['keyword'])
        except re.error as e:
            raise FileReadRejected(f'regex 樣式不合法: {e}', 'bad_pattern')

    def _match_line(
        self,
        line: str,
        config: Dict[str, Any],
        matcher: Optional[Pattern[str]],
    ) -> bool:
        if config['match_mode'] == 'literal':
            if config['match_scope'] == 'line_start':
                return line.startswith(config['keyword'])
            return config['keyword'] in line

        if matcher is None:
            return False
        if config['match_scope'] == 'line_start':
            return matcher.match(line) is not None
        return matcher.search(line) is not None

    def _raw_to_lines(self, raw: bytes, encoding: str) -> List[str]:
        if not raw:
            return []
        text = _sanitize_text(raw.decode(encoding, errors='replace'))
        return text.splitlines()

    def _content_result(self, lines: List[str], truncated: bool) -> Dict[str, Any]:
        content = '\n'.join(lines)
        return {
            '_result': 'ok',
            '_content': content,
            '_lines': lines,
            '_match_count': 0,
            '_truncated': truncated,
            '_scan_truncated': False,
            '_error_kind': '',
        }

    def _join_windows(self, windows: List[List[str]]) -> List[str]:
        output: List[str] = []
        for index, window in enumerate(windows):
            if index > 0:
                output.append('--')
            output.extend(window)
        return output

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

    def _empty_result(self) -> Dict[str, Any]:
        return {
            '_result': 'exception',
            '_content': '',
            '_lines': [],
            '_match_count': 0,
            '_file_size': 0,
            '_file_mtime': '',
            '_truncated': False,
            '_scan_truncated': False,
            '_error_kind': '',
            '_duration_ms': 0,
        }

    def _write_result_vars_if_possible(self, result_var: str, result: Dict[str, Any]) -> None:
        if result_var and VAR_NAME_RE.match(result_var):
            self._write_result_vars(result_var, result)

    def _write_result_vars(self, result_var: str, result: Dict[str, Any]) -> None:
        for suffix in (
            '_result', '_content', '_lines', '_match_count', '_file_size', '_file_mtime',
            '_truncated', '_scan_truncated', '_error_kind',
        ):
            self.set_flow_var(f'{result_var}{suffix}', result.get(suffix))

    def _success_response(self, result: Dict[str, Any]) -> Dict[str, Any]:
        data = {
            key: result.get(key)
            for key in (
                '_result', '_content', '_lines', '_match_count', '_file_size', '_file_mtime',
                '_truncated', '_scan_truncated', '_error_kind',
                'skip_advance', 'skip_advance_reason',
            )
            if key in result
        }
        return {
            'status': 'success',
            'message': f"FileRead: {result.get('_result')}",
            'data': data,
        }

    def _log_before_read(self, config: Dict[str, Any]) -> None:
        self.log_info('FileRead 即將讀取', {
            'mode': config['mode'],
            'base_dir': config.get('base_dir_real'),
            'file_path': config.get('file_path_real'),
            'keyword_len': len(config.get('keyword') or ''),
            'occurrence': config['occurrence'],
            'match_scope': config['match_scope'],
            'match_mode': config['match_mode'],
            'lines': config['lines'],
            'before': config['before'],
            'after': config['after'],
            'max_windows': config['max_windows'],
            'max_scan_bytes': config['max_scan_bytes'],
            'max_scan_ms': config['max_scan_ms'],
        })

    def _log_after_read(self, result: Dict[str, Any]) -> None:
        details = {
            'result': result.get('_result'),
            'match_count': result.get('_match_count'),
            'file_size': result.get('_file_size'),
            'truncated': result.get('_truncated'),
            'scan_truncated': result.get('_scan_truncated'),
            'duration_ms': result.get('_duration_ms'),
            'content_head': (result.get('_content') or '')[:OUTPUT_LOG_LIMIT],
            'error_kind': result.get('_error_kind'),
        }
        if result.get('_result') == 'ok':
            self.log_info('FileRead 讀取完成', details)
        else:
            self.log_error('FileRead 讀取異常', details)

    def _io_error_kind(self, error: Exception) -> str:
        if isinstance(error, FileNotFoundError):
            return 'file_not_found'
        if isinstance(error, PermissionError):
            return 'permission_denied'
        return 'io_error'
