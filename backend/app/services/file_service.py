"""
FileService - 統一檔案管理服務

所有檔案上傳/下載都經過這裡，依 storage_type 決定走 local 或 BeakSeal。
"""
import logging
import os
import uuid
from datetime import datetime
from typing import Optional

from werkzeug.datastructures import FileStorage

from .. import db
from ..models.platform_file import PlatformFile
from ..utils.security import generate_secure_code

logger = logging.getLogger(__name__)

# 上傳根目錄（backend/uploads/，在 static/ 之外，不可被直接存取）
UPLOAD_BASE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    'uploads'
)

# context_type → storage_type 預設對應
CONTEXT_STORAGE_MAP = {
    'org_logo': 'local',
    'wf_background': 'local',
    'form_attachment': 'beakseal',
    'subsystem_file': 'beakseal',
}

# context_type → 允許的副檔名
CONTEXT_ALLOWED_EXT = {
    'org_logo': {'png', 'jpg', 'jpeg', 'gif', 'svg', 'webp'},
    'wf_background': {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp'},
    'form_attachment': {'pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx',
                        'odt', 'ods', 'csv', 'txt', 'rtf',
                        'png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp',
                        'zip', '7z', 'rar'},
    'subsystem_file': {'pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx',
                       'odt', 'ods', 'csv', 'txt', 'rtf',
                       'png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp',
                       'zip', '7z', 'rar'},
}

# context_type → 檔案大小上限 (bytes)
CONTEXT_MAX_SIZE = {
    'org_logo': 2 * 1024 * 1024,       # 2MB
    'wf_background': 5 * 1024 * 1024,   # 5MB
    'form_attachment': 50 * 1024 * 1024, # 50MB
    'subsystem_file': 50 * 1024 * 1024,  # 50MB
}

# 預設上限
DEFAULT_MAX_SIZE = 50 * 1024 * 1024  # 50MB


def _get_upload_dir():
    """取得 local 檔案儲存的絕對路徑（在 static/ 之外）"""
    os.makedirs(UPLOAD_BASE_DIR, exist_ok=True)
    return UPLOAD_BASE_DIR


def _resolve_local_path(storage_ref: str) -> str:
    """
    解析 storage_ref 為絕對路徑。
    新格式: 純檔名 (如 abc123.png) -> UPLOAD_BASE_DIR/abc123.png
    舊格式: uploads/xxx (遷移期相容) -> UPLOAD_BASE_DIR/xxx
    """
    # 去除可能的 uploads/ 前綴（遷移期向下相容）
    if storage_ref.startswith('uploads/'):
        storage_ref = storage_ref[len('uploads/'):]
    return os.path.join(UPLOAD_BASE_DIR, storage_ref)


def _validate_file(file: FileStorage, context_type: str) -> Optional[str]:
    """
    驗證檔案，回傳錯誤訊息或 None（通過）。
    """
    if not file or file.filename == '':
        return '未選擇檔案'

    # 副檔名檢查
    ext = ''
    if '.' in file.filename:
        ext = file.filename.rsplit('.', 1)[1].lower()

    allowed = CONTEXT_ALLOWED_EXT.get(context_type)
    if allowed and ext not in allowed:
        return f'不支援的檔案格式，允許: {", ".join(sorted(allowed))}'

    # 檔案大小（先讀取再回捲）
    file.seek(0, 2)
    size = file.tell()
    file.seek(0)

    max_size = CONTEXT_MAX_SIZE.get(context_type, DEFAULT_MAX_SIZE)
    if size > max_size:
        max_mb = max_size // 1024 // 1024
        return f'檔案過大，上限 {max_mb}MB'

    return None


def upload_file(org_sc: str, file: FileStorage, context_type: str,
                context_id: str = None, uploader_sc: str = None,
                storage_type: str = None) -> PlatformFile:
    """
    上傳檔案並建立 platform_files 記錄。

    Args:
        org_sc: 企業 secure_code
        file: werkzeug FileStorage 物件
        context_type: 用途類型
        context_id: 關聯的業務記錄 SC
        uploader_sc: 上傳者 SC
        storage_type: 強制指定儲存類型，None 則依 context_type 自動判斷

    Returns:
        PlatformFile 記錄

    Raises:
        ValueError: 驗證失敗
        RuntimeError: 儲存失敗
    """
    # 驗證
    error = _validate_file(file, context_type)
    if error:
        raise ValueError(error)

    # 決定 storage_type
    if storage_type is None:
        storage_type = CONTEXT_STORAGE_MAP.get(context_type, 'local')

    # 檔案 metadata
    ext = ''
    if '.' in file.filename:
        ext = file.filename.rsplit('.', 1)[1].lower()

    file.seek(0, 2)
    file_size = file.tell()
    file.seek(0)

    file_data = file.read()
    file.seek(0)

    if storage_type == 'local':
        storage_ref = _store_local(file_data, ext)
    elif storage_type == 'beakseal':
        storage_ref = _store_beakseal(org_sc, uploader_sc, file_data,
                                       file.filename)
    else:
        raise ValueError(f'不支援的 storage_type: {storage_type}')

    # 建立 DB 記錄
    record = PlatformFile(
        secure_code=generate_secure_code(),
        org_secure_code=org_sc,
        storage_type=storage_type,
        storage_ref=storage_ref,
        original_name=file.filename,
        file_size=file_size,
        mime_type=file.mimetype,
        file_ext=ext,
        context_type=context_type,
        context_id=context_id,
        uploader_sc=uploader_sc,
        status='active',
    )

    db.session.add(record)
    # 不在這裡 commit，讓呼叫端控制 transaction
    return record


def _store_local(file_data: bytes, ext: str) -> str:
    """存到 local 磁碟，回傳檔名（不含目錄前綴）"""
    filename = f'{uuid.uuid4().hex}.{ext}' if ext else uuid.uuid4().hex
    upload_dir = _get_upload_dir()
    full_path = os.path.join(upload_dir, filename)

    with open(full_path, 'wb') as f:
        f.write(file_data)

    return filename


def _store_beakseal(org_sc: str, user_sc: str, file_data: bytes,
                    filename: str) -> str:
    """加密存到 BeakSeal，回傳 file_id"""
    from .vault_service import get_client as get_vault_client

    client = get_vault_client()
    result = client.encrypt_file(org_sc, user_sc or 'system',
                                 file_data, filename)
    return result.get('file_id', '')


def serve_file(record: PlatformFile) -> tuple:
    """
    取得檔案內容，用於 serve（公開資源）或 download（機敏檔案）。

    Returns:
        (file_data: bytes, mime_type: str, original_name: str)

    Raises:
        FileNotFoundError: 檔案不存在
        RuntimeError: BeakSeal 解密失敗
    """
    if record.storage_type == 'local':
        full_path = _resolve_local_path(record.storage_ref)
        if not os.path.exists(full_path):
            raise FileNotFoundError(f'檔案不存在: {record.secure_code}')
        with open(full_path, 'rb') as f:
            data = f.read()
        return data, record.mime_type, record.original_name

    elif record.storage_type == 'beakseal':
        from .vault_service import get_client as get_vault_client

        client = get_vault_client()
        data = client.decrypt_file(record.storage_ref,
                                   org_id=record.org_secure_code)
        return data, record.mime_type, record.original_name

    else:
        raise RuntimeError(f'不支援的 storage_type: {record.storage_type}')


def delete_file(record: PlatformFile, hard_delete_local: bool = True):
    """
    刪除檔案（軟刪除 DB 記錄 + 清除實體檔案）。

    Args:
        record: PlatformFile 記錄
        hard_delete_local: 是否刪除 local 實體檔案
    """
    # 刪除實體
    if record.storage_type == 'local' and hard_delete_local:
        full_path = _resolve_local_path(record.storage_ref)
        if os.path.exists(full_path):
            try:
                os.remove(full_path)
            except OSError as e:
                logger.warning("刪除 local 檔案失敗: %s - %s",
                               full_path, e)

    elif record.storage_type == 'beakseal':
        try:
            from .vault_service import get_client as get_vault_client
            client = get_vault_client()
            client.delete_file(record.storage_ref,
                               org_id=record.org_secure_code)
        except Exception as e:
            logger.warning("刪除 BeakSeal 檔案失敗: %s - %s",
                           record.storage_ref, e)

    # 軟刪除 DB 記錄
    record.is_deleted = True
    record.status = 'deleted'
    record.deleted_at = datetime.utcnow()


def get_file_by_sc(secure_code: str, org_sc: str = None) -> Optional[PlatformFile]:
    """
    依 secure_code 取得檔案記錄。

    Args:
        secure_code: 檔案的 secure_code
        org_sc: 限定企業（租戶隔離），None 表示不限
    """
    query = PlatformFile.query.filter_by(
        secure_code=secure_code,
        is_deleted=False,
    )
    if org_sc:
        query = query.filter_by(org_secure_code=org_sc)
    return query.first()


def list_files(org_sc: str, context_type: str = None,
               context_id: str = None) -> list:
    """列出檔案記錄"""
    query = PlatformFile.query.filter_by(
        org_secure_code=org_sc,
        is_deleted=False,
    )
    if context_type:
        query = query.filter_by(context_type=context_type)
    if context_id:
        query = query.filter_by(context_id=context_id)

    return query.order_by(PlatformFile.created_at.desc()).all()


def get_context_file(org_sc: str, context_type: str,
                     context_id: str = None) -> Optional[PlatformFile]:
    """取得特定 context 的唯一檔案（如 org_logo）"""
    query = PlatformFile.query.filter_by(
        org_secure_code=org_sc,
        context_type=context_type,
        is_deleted=False,
    )
    if context_id:
        query = query.filter_by(context_id=context_id)
    return query.first()
