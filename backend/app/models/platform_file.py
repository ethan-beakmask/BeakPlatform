"""
PlatformFile Model
統一管理平台所有檔案的 metadata
"""
from flask import has_request_context, request
from sqlalchemy import Column, String, BigInteger, Text

from .base import TenantBaseModel


def _url_prefix() -> str:
    """nginx 掛載前綴（/beakplatform）。無 request context 時回空字串。"""
    return request.script_root if has_request_context() else ''


class PlatformFile(TenantBaseModel):
    """
    平台檔案記錄

    storage_type:
        - 'local': 存於磁碟 uploads/ 目錄，storage_ref = 相對路徑
        - 'encrypted': 加密存於 encrypted_storage/ 目錄，storage_ref = 相對路徑

    context_type:
        - 'org_logo': 企業 Logo
        - 'wf_background': 工作流設計器底圖
        - 'form_attachment': 表單簽核附件
        - 'subsystem_file': 子系統業務附件
    """
    __tablename__ = 'platform_files'

    # 儲存資訊
    storage_type = Column(String(16), nullable=False)
    storage_ref = Column(String(255), nullable=False)

    # 檔案 metadata
    original_name = Column(String(255), nullable=False)
    file_size = Column(BigInteger, nullable=False, default=0)
    mime_type = Column(String(100))
    file_ext = Column(String(10))

    # 用途 context
    context_type = Column(String(50), nullable=False)
    context_id = Column(String(32))

    # 上傳者
    uploader_sc = Column(String(32))
    uploader_node_id = Column(String(100))

    # 狀態: active, pending_delete, deleted
    status = Column(String(20), nullable=False, default='active')

    # 完整性驗證 (SHA-256 of plaintext)
    file_hash = Column(String(64))

    # 加密 metadata (僅 storage_type='encrypted' 使用)
    wrapped_dek = Column(Text)
    dek_nonce = Column(String(64))
    file_nonce = Column(String(64))
    encryption_key_sc = Column(String(32))

    def to_dict(self):
        base = super().to_dict()
        base.update({
            'original_name': self.original_name,
            'file_size': self.file_size,
            'mime_type': self.mime_type,
            'file_ext': self.file_ext,
            'context_type': self.context_type,
            'context_id': self.context_id,
            'storage_type': self.storage_type,
            'status': self.status,
            'uploader_sc': self.uploader_sc,
            'uploader_node_id': self.uploader_node_id,
        })
        return base

    @property
    def serve_url(self):
        """產生前端可用的 serve URL

        前綴一律用 request.script_root（FRONT-10）：app 掛在 nginx 的 /beakplatform
        底下，而 Flask 的 request.path 不含該前綴。少了它，瀏覽器會拿絕對路徑去打
        /api/files/<sc>/serve 而 404（症狀是圖片破圖、只有 F12 看得到）。
        無 request context（背景任務、CLI）時回相對路徑，呼叫端自行處理。
        """
        return f'{_url_prefix()}/api/files/{self.secure_code}/serve'

    @property
    def download_token_url(self):
        """產生前端取得一次性下載 token 的 API URL (POST)；前綴理由同 serve_url"""
        return f'{_url_prefix()}/api/files/{self.secure_code}/download-token'
