"""
FormWorkflow Module - OsFileWrite Handler
檔案寫入節點處理器

OsFileWrite 是系統級、低階檔案追加能力：它不經 shell，只對允許 base_dir 下的一般檔案
追加字串。它與 OsFileRead 分開授權，因為可讀不等於可寫。

本節點有三道護欄：`OS_FILE_WRITE_NODE_ENABLED` 執行期開關、通用節點企業授權，
以及平台設定、企業設定、節點設定三層 base_dir 交集。目標檔最後一段 symlink
一律拒絕，開檔時也使用 `O_NOFOLLOW` 作為 TOCTOU 防線。

結果語彙只有 ok / exception / timeout，且全部回 `status='success'`。這是為了避開
`FwNodeExecutionQueue.fail()` 的自動重試；寫檔是有副作用的操作，被平台自動重跑會
寫進重複資料。因此失敗真相只放在流程變數 `<result_var>_result` 與
fw_node_execution_logs（level=ERROR），判斷本節點成敗不能看 queue 的 status。

v1 刻意同步完成、不回 waiting / pending。若日後改成非同步，
`workflow_executor.py` 內兩處節點型別清單都必須加上 OsFileWrite，漏了節點會永遠卡在
WAITING 而且不報錯。
"""
import codecs
import errno
import fcntl
import os
import re
import stat
import time
from typing import Any, Dict, Iterable, List, Optional, Tuple

from app import db
from app.models import SystemSetting
from modules.form_workflow.services.node_grant_service import is_node_allowed

from .base import BaseNodeHandler

NODE_TYPE = 'OsFileWrite'
VAR_NAME_RE = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]{0,63}$')

DEFAULT_MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_FILE_BYTES_HARD = 512 * 1024 * 1024
DEFAULT_LOCK_TIMEOUT_MS = 5000
MAX_LOCK_TIMEOUT_MS_HARD = 60000
TAIL_SCAN_BLOCK_SIZE = 8192
OUTPUT_LOG_LIMIT = 2048


class OsFileWriteRejected(Exception):
    """設定、授權或寫入階段拒絕。會轉成 success/exception，不外拋。"""

    def __init__(
        self,
        message: str,
        error_kind: str = 'bad_config',
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.error_kind = error_kind
        self.details = details or {}


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


def _is_under_path(path: str, base_dir: str) -> bool:
    try:
        return os.path.commonpath([path, base_dir]) == base_dir
    except ValueError:
        return False


class OsFileWriteHandler(BaseNodeHandler):
    """檔案追加寫入節點。"""

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
            result['_content_head'] = config['content'][:OUTPUT_LOG_LIMIT]

            self._log_before_write(config)
            write_result = self._write_file(config, file_path)
            result.update(write_result)
            result['_result'] = result.get('_result') or 'ok'

        except OsFileWriteRejected as e:
            result.update(e.details)
            result['_result'] = 'timeout' if e.error_kind == 'lock_timeout' else 'exception'
            result['_error_kind'] = e.error_kind
            self.log_error('OsFileWrite 拒絕寫入', {
                'error_kind': e.error_kind,
                'reason': str(e),
            })

        except (FileNotFoundError, PermissionError, OSError) as e:
            result['_result'] = 'exception'
            result['_error_kind'] = self._io_error_kind(e)
            self.log_error('OsFileWrite 寫入例外', {
                'error_kind': result['_error_kind'],
                'error': str(e),
            })

        except Exception as e:
            db.session.rollback()
            result['_result'] = 'exception'
            result['_error_kind'] = 'runtime_error'
            self.log_error('OsFileWrite 執行例外', {
                'error_kind': 'runtime_error',
                'error': str(e),
            })

        finally:
            result['_duration_ms'] = int((time.monotonic() - start) * 1000)
            if config and not result.get('_content_head'):
                result['_content_head'] = config.get('content', '')[:OUTPUT_LOG_LIMIT]
            self._write_result_vars_if_possible(result_var, result)
            self._log_after_write(result)

        if _coerce_bool(self.get_config_value('stop_after'), False):
            result['skip_advance'] = True
            result['skip_advance_reason'] = 'filewrite_stop_after'
        elif not self._has_outgoing_edges():
            result['skip_advance'] = True
            result['skip_advance_reason'] = 'os_file_write_no_outgoing'

        return self._success_response(result)

    def _check_authorized(self) -> None:
        if not _env_flag_enabled(os.environ.get('OS_FILE_WRITE_NODE_ENABLED')):
            raise OsFileWriteRejected('OS_FILE_WRITE_NODE_ENABLED 未啟用', 'not_authorized')

        if not is_node_allowed(NODE_TYPE, self.queue_item.org_secure_code):
            raise OsFileWriteRejected('企業未取得 OsFileWrite 節點授權', 'not_authorized')

    def _load_config(self) -> Dict[str, Any]:
        result_var = self.get_config_value('result_var')
        if not isinstance(result_var, str) or not VAR_NAME_RE.match(result_var):
            raise OsFileWriteRejected('result_var 格式不合法')

        base_dir = self.get_config_value('base_dir')
        if not isinstance(base_dir, str) or not base_dir.strip():
            raise OsFileWriteRejected('base_dir 為必填')

        file_path = self.get_config_value('file_path')
        if not isinstance(file_path, str) or not file_path.strip():
            raise OsFileWriteRejected('file_path 為必填')

        if 'content' not in self.node_config or not isinstance(self.node_config.get('content'), str):
            raise OsFileWriteRejected('content 為必填')

        encoding = str(self.get_config_value('encoding') or 'utf-8')
        self._validate_encoding(encoding)
        content = self.replace_variables(self.node_config.get('content', ''))
        try:
            body = content.encode(encoding, errors='strict')
            newline = '\n'.encode(encoding, errors='strict')
        except UnicodeEncodeError as e:
            raise OsFileWriteRejected(f'content 編碼失敗: {e}', 'encode_error')

        return {
            'base_dir': base_dir.strip(),
            'file_path': self.replace_variables(file_path),
            'content': content,
            'body': body,
            'newline': newline,
            'newline_smart': _coerce_bool(self.get_config_value('newline_smart'), True),
            'newline_before': _coerce_bool(self.get_config_value('newline_before'), False),
            'newline_after': _coerce_bool(self.get_config_value('newline_after'), True),
            'create_if_missing': _coerce_bool(self.get_config_value('create_if_missing'), True),
            'encoding': encoding,
            'max_file_bytes': _coerce_int(
                self.get_config_value('max_file_bytes'),
                DEFAULT_MAX_FILE_BYTES,
                1,
                MAX_FILE_BYTES_HARD,
            ),
            'lock_timeout_ms': _coerce_int(
                self.get_config_value('lock_timeout_ms'),
                DEFAULT_LOCK_TIMEOUT_MS,
                1,
                MAX_LOCK_TIMEOUT_MS_HARD,
            ),
            'result_var': result_var,
            'stop_after': _coerce_bool(self.get_config_value('stop_after'), False),
        }

    def _validate_encoding(self, encoding: str) -> None:
        normalized = encoding.lower().replace('-', '').replace('_', '')
        if normalized.startswith('utf16') or normalized.startswith('utf32'):
            raise OsFileWriteRejected('encoding 不支援 UTF-16/UTF-32 家族', 'bad_config')
        try:
            codecs.lookup(encoding)
            # rot13 / base64 這類 codec 查得到卻不是文字編碼，str.encode() 會拋
            # LookupError。在這裡先試一次，錯誤才會歸到 bad_config 而不是 runtime_error。
            ''.encode(encoding)
        except LookupError:
            raise OsFileWriteRejected('encoding 不存在或不是文字編碼', 'bad_config')

    def _resolve_allowed_paths(self, config: Dict[str, Any]) -> Tuple[str, str]:
        node_base = os.path.realpath(config['base_dir'])
        if not os.path.isdir(node_base):
            raise OsFileWriteRejected('base_dir 不存在或不是目錄', 'path_denied')

        platform_dirs = self._real_existing_dirs(SystemSetting.get('os_file_write_base_dirs', []))
        if not platform_dirs:
            raise OsFileWriteRejected('os_file_write_base_dirs 未設定允許目錄', 'path_denied')

        org_map = SystemSetting.get('os_file_write_org_base_dirs', {})
        if not isinstance(org_map, dict):
            org_map = {}
        if self.queue_item.org_secure_code in org_map:
            org_dirs = self._real_existing_dirs(org_map.get(self.queue_item.org_secure_code))
        else:
            org_dirs = platform_dirs
        if not org_dirs:
            raise OsFileWriteRejected('企業沒有可用的 os_file_write_org_base_dirs', 'path_denied')

        if not self._under_any(node_base, platform_dirs) or not self._under_any(node_base, org_dirs):
            raise OsFileWriteRejected('base_dir 不在平台與企業允許目錄交集內', 'path_denied')

        requested_path = config['file_path']
        if os.path.isabs(requested_path):
            abs_path = requested_path
        else:
            abs_path = os.path.join(node_base, requested_path)
        parent = os.path.realpath(os.path.dirname(abs_path))
        name = os.path.basename(abs_path)
        if not name or name in ('.', '..') or '/' in name:
            raise OsFileWriteRejected('file_path 檔名不合法', 'path_denied')

        final_path = os.path.join(parent, name)
        if not os.path.isdir(parent):
            raise OsFileWriteRejected('file_path 父目錄不存在或不是目錄', 'path_denied')
        if not _is_under_path(final_path, node_base):
            raise OsFileWriteRejected('file_path 不在 base_dir 之下', 'path_denied')
        if os.path.islink(final_path):
            raise OsFileWriteRejected('file_path 是 symlink，拒絕寫入', 'path_denied')
        if os.path.lexists(final_path):
            file_stat = os.lstat(final_path)
            if not stat.S_ISREG(file_stat.st_mode):
                raise OsFileWriteRejected('file_path 不是一般檔案', 'path_denied')
        return node_base, final_path

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

    def _write_file(self, config: Dict[str, Any], file_path: str) -> Dict[str, Any]:
        fd = -1
        locked = False
        created = False
        try:
            created = not os.path.lexists(file_path)
            flags = os.O_RDWR | os.O_NOFOLLOW
            if config['create_if_missing']:
                flags |= os.O_CREAT
            try:
                fd = os.open(file_path, flags, 0o640)
            except OSError as e:
                if e.errno == errno.ELOOP:
                    raise OsFileWriteRejected('file_path 是 symlink，拒絕寫入', 'path_denied')
                raise
            try:
                self._lock_fd(fd, config['lock_timeout_ms'])
            except OsFileWriteRejected as e:
                if e.error_kind == 'lock_timeout':
                    e.details['_created'] = created
                raise
            locked = True

            file_stat = os.fstat(fd)
            if not stat.S_ISREG(file_stat.st_mode):
                raise OsFileWriteRejected('file_path 不是一般檔案', 'path_denied', {
                    '_created': created,
                })

            size_before = int(file_stat.st_size)
            trimmed_bytes = self._count_trailing_newlines(fd, size_before)
            new_size = size_before - trimmed_bytes
            payload = self._build_payload(config, new_size)
            if size_before + len(payload) > config['max_file_bytes']:
                raise OsFileWriteRejected('寫入後會超過 max_file_bytes', 'file_too_large', {
                    '_trimmed_bytes': trimmed_bytes,
                    '_size_before': size_before,
                    '_size_after': size_before,
                    '_created': created,
                })

            if trimmed_bytes > 0:
                os.ftruncate(fd, new_size)
            os.lseek(fd, 0, os.SEEK_END)
            bytes_written = self._write_all(fd, payload)
            os.fsync(fd)
            size_after = int(os.fstat(fd).st_size)

            return {
                '_result': 'ok',
                '_error_kind': '',
                '_file_path': file_path,
                '_bytes_written': bytes_written,
                '_trimmed_bytes': trimmed_bytes,
                '_size_before': size_before,
                '_size_after': size_after,
                '_created': created,
            }
        finally:
            if fd >= 0:
                try:
                    if locked:
                        fcntl.flock(fd, fcntl.LOCK_UN)
                finally:
                    os.close(fd)

    def _lock_fd(self, fd: int, timeout_ms: int) -> None:
        deadline = time.monotonic() + (timeout_ms / 1000)
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return
            except (BlockingIOError, OSError):
                if time.monotonic() >= deadline:
                    raise OsFileWriteRejected('取得檔案鎖逾時', 'lock_timeout')
                time.sleep(0.05)

    def _pread_exact(self, fd: int, count: int, offset: int) -> bytes:
        """讀滿 count 位元組才回傳。os.pread 允許短讀，而檔尾掃描一旦拿到不是真正
        檔尾的那一段，就會把真實資料誤判成尾端換行而截掉，所以這裡不接受短讀。"""
        chunks = []
        remaining = count
        while remaining > 0:
            part = os.pread(fd, remaining, offset + (count - remaining))
            if not part:
                raise OSError('pread 提前遇到 EOF，檔案在寫入期間被縮短')
            chunks.append(part)
            remaining -= len(part)
        return b''.join(chunks)

    def _count_trailing_newlines(self, fd: int, size_before: int) -> int:
        trimmed = 0
        position = size_before
        while position > 0:
            read_size = min(TAIL_SCAN_BLOCK_SIZE, position)
            position -= read_size
            block = self._pread_exact(fd, read_size, position)
            index = len(block) - 1
            while index >= 0 and block[index] in (0x0A, 0x0D):
                trimmed += 1
                index -= 1
            if index >= 0:
                break
        return trimmed

    def _build_payload(self, config: Dict[str, Any], new_size: int) -> bytes:
        use_prefix = config['newline_smart'] or config['newline_before']
        prefix = config['newline'] if use_prefix and new_size > 0 else b''
        suffix = config['newline'] if config['newline_after'] else b''
        return prefix + config['body'] + suffix

    def _write_all(self, fd: int, payload: bytes) -> int:
        total = 0
        while total < len(payload):
            written = os.write(fd, payload[total:])
            if written == 0:
                raise OSError('os.write returned 0')
            total += written
        return total

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
            '_error_kind': '',
            '_file_path': '',
            '_bytes_written': 0,
            '_trimmed_bytes': 0,
            '_size_before': 0,
            '_size_after': 0,
            '_created': False,
            '_duration_ms': 0,
            '_content_head': '',
        }

    def _write_result_vars_if_possible(self, result_var: str, result: Dict[str, Any]) -> None:
        if result_var and VAR_NAME_RE.match(result_var):
            self._write_result_vars(result_var, result)

    def _write_result_vars(self, result_var: str, result: Dict[str, Any]) -> None:
        for suffix in (
            '_result', '_error_kind', '_file_path', '_bytes_written', '_trimmed_bytes',
            '_size_before', '_size_after', '_created',
        ):
            self.set_flow_var(f'{result_var}{suffix}', result.get(suffix))

    def _success_response(self, result: Dict[str, Any]) -> Dict[str, Any]:
        data = {
            key: result.get(key)
            for key in (
                '_result', '_error_kind', '_file_path', '_bytes_written', '_trimmed_bytes',
                '_size_before', '_size_after', '_created',
                'skip_advance', 'skip_advance_reason',
            )
            if key in result
        }
        return {
            'status': 'success',
            'message': f"OsFileWrite: {result.get('_result')}",
            'data': data,
        }

    def _log_before_write(self, config: Dict[str, Any]) -> None:
        self.log_info('OsFileWrite 即將寫入', {
            'base_dir': config.get('base_dir_real'),
            'file_path': config.get('file_path_real'),
            'content_len': len(config.get('content') or ''),
            'newline_smart': config['newline_smart'],
            'newline_before': config['newline_before'],
            'newline_after': config['newline_after'],
            'create_if_missing': config['create_if_missing'],
            'encoding': config['encoding'],
            'max_file_bytes': config['max_file_bytes'],
        })

    def _log_after_write(self, result: Dict[str, Any]) -> None:
        details = {
            'result': result.get('_result'),
            'error_kind': result.get('_error_kind'),
            'bytes_written': result.get('_bytes_written'),
            'trimmed_bytes': result.get('_trimmed_bytes'),
            'size_before': result.get('_size_before'),
            'size_after': result.get('_size_after'),
            'duration_ms': result.get('_duration_ms'),
            'content_head': result.get('_content_head') or '',
        }
        if result.get('_result') == 'ok':
            self.log_info('OsFileWrite 寫入完成', details)
        else:
            self.log_error('OsFileWrite 寫入異常', details)

    def _io_error_kind(self, error: Exception) -> str:
        if isinstance(error, FileNotFoundError):
            return 'file_not_found'
        if isinstance(error, PermissionError):
            return 'permission_denied'
        return 'io_error'
