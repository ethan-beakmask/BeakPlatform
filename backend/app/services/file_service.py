"""
FileService - 統一檔案管理服務

所有檔案上傳/下載都經過這裡，依 storage_type 決定走 local 或 encrypted。
加密檔案使用內建 AES-256-GCM 加密，不依賴外部服務。
"""
import hashlib
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

# 加密檔案儲存目錄（可透過環境變數設定）
ENCRYPTED_STORAGE_DIR = os.getenv(
    'ENCRYPTED_STORAGE_DIR',
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        'encrypted_storage'
    )
)

# context_type → storage_type 預設對應
CONTEXT_STORAGE_MAP = {
    'org_logo': 'local',
    'wf_background': 'local',
    'form_attachment': 'encrypted',
    'subsystem_file': 'encrypted',
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


def _get_dir_file_limit() -> int:
    """取得單一目錄檔案數上限（runtime 從 DB 讀取）"""
    from ..models.system_setting import SystemSetting
    return int(SystemSetting.get('encrypted_dir_file_limit', 100000))


def _get_encrypted_dir(org_sc: str) -> str:
    """
    取得加密檔案儲存的目標目錄（按企業 + 月份隔離）。

    目錄結構: {base}/{org_sc}/{YYYYMM}/
    當月份目錄檔案數達上限時: {base}/{org_sc}/{YYYYMM}_2/, _3/ ...
    """
    year_month = datetime.utcnow().strftime('%Y%m')
    limit = _get_dir_file_limit()

    # 嘗試當月基本目錄
    candidate = os.path.join(ENCRYPTED_STORAGE_DIR, org_sc, year_month)
    os.makedirs(candidate, exist_ok=True)

    # 計算檔案數（僅數檔案，不含子目錄）
    try:
        file_count = sum(1 for e in os.scandir(candidate) if e.is_file())
    except OSError:
        file_count = 0

    if file_count < limit:
        return candidate

    # 超過上限，嘗試 _2, _3 ...
    suffix = 2
    while True:
        candidate = os.path.join(
            ENCRYPTED_STORAGE_DIR, org_sc, f'{year_month}_{suffix}'
        )
        os.makedirs(candidate, exist_ok=True)
        try:
            file_count = sum(1 for e in os.scandir(candidate) if e.is_file())
        except OSError:
            file_count = 0

        if file_count < limit:
            return candidate
        suffix += 1


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


def _resolve_encrypted_path(storage_ref: str) -> str:
    """解析加密檔案的絕對路徑"""
    return os.path.join(ENCRYPTED_STORAGE_DIR, storage_ref)


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
                storage_type: str = None, uploader_node_id: str = None) -> PlatformFile:
    """
    上傳檔案並建立 platform_files 記錄。

    Args:
        org_sc: 企業 secure_code
        file: werkzeug FileStorage 物件
        context_type: 用途類型
        context_id: 關聯的業務記錄 SC
        uploader_sc: 上傳者 SC
        storage_type: 強制指定儲存類型，None 則依 context_type 自動判斷
        uploader_node_id: 上傳時的簽核關卡 node_id

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

    # 明文 SHA-256（加密前計算，用於完整性驗證）
    file_hash = hashlib.sha256(file_data).hexdigest()

    # 加密相關欄位（僅 encrypted 類型使用）
    wrapped_dek = None
    dek_nonce = None
    file_nonce = None
    encryption_key_sc = None

    if storage_type == 'local':
        storage_ref = _store_local(file_data, ext)
    elif storage_type == 'encrypted':
        storage_ref, enc_meta = _store_encrypted(org_sc, file_data)
        wrapped_dek = enc_meta['wrapped_dek']
        dek_nonce = enc_meta['dek_nonce']
        file_nonce = enc_meta['file_nonce']
        encryption_key_sc = enc_meta['encryption_key_sc']
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
        uploader_node_id=uploader_node_id,
        status='active',
        file_hash=file_hash,
        wrapped_dek=wrapped_dek,
        dek_nonce=dek_nonce,
        file_nonce=file_nonce,
        encryption_key_sc=encryption_key_sc,
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


def _store_encrypted(org_sc: str, file_data: bytes) -> tuple[str, dict]:
    """
    加密後存到磁碟。

    Returns:
        (storage_ref, encryption_metadata)
        storage_ref: 相對路徑 "{org_sc}/{YYYYMM}/{uuid}.enc"
                     （舊格式 "{org_sc}/{uuid}.enc" 仍由 _resolve_encrypted_path 相容）
    """
    import base64
    from ..crypto.key_manager import KeyManager

    # 加密
    result = KeyManager.encrypt_file(org_sc, file_data)

    # 寫入密文（目標目錄含月份子目錄）
    enc_dir = _get_encrypted_dir(org_sc)
    filename = f'{uuid.uuid4().hex}.enc'
    full_path = os.path.join(enc_dir, filename)

    with open(full_path, 'wb') as f:
        f.write(result['ciphertext'])

    # storage_ref 使用相對於 ENCRYPTED_STORAGE_DIR 的路徑
    storage_ref = os.path.relpath(full_path, ENCRYPTED_STORAGE_DIR)

    enc_meta = {
        'wrapped_dek': result['wrapped_dek'],
        'dek_nonce': result['dek_nonce'],
        'file_nonce': base64.urlsafe_b64encode(result['file_nonce']).decode(),
        'encryption_key_sc': result['encryption_key_sc'],
    }

    return storage_ref, enc_meta


def serve_file(record: PlatformFile) -> tuple:
    """
    取得檔案內容，用於 serve（公開資源）或 download（機敏檔案）。

    Returns:
        (file_data: bytes, mime_type: str, original_name: str)

    Raises:
        FileNotFoundError: 檔案不存在
        RuntimeError: 解密失敗
    """
    if record.storage_type == 'local':
        full_path = _resolve_local_path(record.storage_ref)
        if not os.path.exists(full_path):
            raise FileNotFoundError(f'檔案不存在: {record.secure_code}')
        with open(full_path, 'rb') as f:
            data = f.read()
        return data, record.mime_type, record.original_name

    elif record.storage_type == 'encrypted':
        return _read_encrypted(record)

    else:
        raise RuntimeError(f'不支援的 storage_type: {record.storage_type}')


class FileTamperError(Exception):
    """檔案完整性異常（大小不符或 hash 不符）"""
    pass


def _read_encrypted(record: PlatformFile) -> tuple:
    """讀取並解密加密檔案"""
    from ..crypto.key_manager import KeyManager
    import base64

    full_path = _resolve_encrypted_path(record.storage_ref)
    if not os.path.exists(full_path):
        raise FileNotFoundError(f'加密檔案不存在: {record.secure_code}')

    # 前置檢查：磁碟大小 vs DB 記錄
    # AES-256-GCM 密文 = 明文 + 16 bytes (auth tag)，不應超過明文的 2 倍
    disk_size = os.path.getsize(full_path)
    if record.file_size > 0 and disk_size > record.file_size * 2:
        raise FileTamperError(
            f'檔案大小異常: file_sc={record.secure_code} '
            f'db_size={record.file_size} disk_size={disk_size}'
        )

    with open(full_path, 'rb') as f:
        ciphertext = f.read()

    # file_nonce 在 DB 中是 base64 字串
    file_nonce = base64.urlsafe_b64decode(record.file_nonce)

    plaintext = KeyManager.decrypt_file(
        org_sc=record.org_secure_code,
        ciphertext=ciphertext,
        file_nonce=file_nonce,
        wrapped_dek_b64=record.wrapped_dek,
        dek_nonce_b64=record.dek_nonce,
        encryption_key_sc=record.encryption_key_sc,
    )

    return plaintext, record.mime_type, record.original_name


def preflight_check(record: PlatformFile) -> Optional[str]:
    """
    下載前置檢查（不讀檔、不解密，微秒級）。

    Returns:
        None = 通過
        str  = 錯誤訊息（檔案異常）
    """
    if record.storage_type == 'encrypted':
        path = _resolve_encrypted_path(record.storage_ref)
    else:
        path = _resolve_local_path(record.storage_ref)

    if not os.path.exists(path):
        return 'file_missing'

    disk_size = os.path.getsize(path)
    # AES-256-GCM: 密文 = 明文 + 16 bytes tag，不應超過 2 倍
    if record.file_size > 0 and disk_size > record.file_size * 2:
        return f'size_mismatch:db={record.file_size},disk={disk_size}'

    return None


def verify_file_integrity(record: PlatformFile, plaintext: bytes) -> bool:
    """
    驗證檔案完整性：比對明文 SHA-256 與 DB 記錄的 file_hash。

    Returns:
        True = 驗證通過（或無 hash 可比對）
        False = hash 不符，檔案可能被竄改
    """
    if not record.file_hash:
        return True  # 舊檔案尚無 hash，跳過驗證
    return hashlib.sha256(plaintext).hexdigest() == record.file_hash


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

    elif record.storage_type == 'encrypted':
        full_path = _resolve_encrypted_path(record.storage_ref)
        if os.path.exists(full_path):
            try:
                os.remove(full_path)
            except OSError as e:
                logger.warning("刪除加密檔案失敗: %s - %s",
                               full_path, e)

    # 軟刪除 DB 記錄
    record.is_deleted = True
    record.status = 'deleted'
    record.deleted_at = datetime.utcnow()


def mark_pending_delete(record: PlatformFile):
    """
    標記檔案為待刪除（偽刪除）。
    實體檔案不動，等簽核確認後才真正刪除。
    """
    record.status = 'pending_delete'


def revert_single_pending_delete(record: PlatformFile):
    """
    將單一 pending_delete 檔案回復為 active。
    """
    if record.status != 'pending_delete':
        raise ValueError('檔案狀態不是 pending_delete')
    record.status = 'active'


def confirm_pending_deletes(org_sc: str, context_id: str):
    """
    簽核確認後，將所有 pending_delete 檔案正式刪除。
    """
    records = PlatformFile.query.filter_by(
        org_secure_code=org_sc,
        context_id=context_id,
        status='pending_delete',
        is_deleted=False,
    ).all()
    for record in records:
        delete_file(record)


def revert_pending_deletes(org_sc: str, context_id: str):
    """
    未簽核關閉時，將所有 pending_delete 回復為 active。
    """
    records = PlatformFile.query.filter_by(
        org_secure_code=org_sc,
        context_id=context_id,
        status='pending_delete',
        is_deleted=False,
    ).all()
    for record in records:
        record.status = 'active'


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
    """列出檔案記錄（含 active 和 pending_delete）"""
    query = PlatformFile.query.filter(
        PlatformFile.org_secure_code == org_sc,
        PlatformFile.is_deleted == False,
        PlatformFile.status.in_(['active', 'pending_delete']),
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
