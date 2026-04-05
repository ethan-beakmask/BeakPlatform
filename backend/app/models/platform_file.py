"""
PlatformFile Model
統一管理平台所有檔案的 metadata
"""
from sqlalchemy import Column, String, BigInteger, Text

from .base import TenantBaseModel


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
        """產生前端可用的 serve URL"""
        return f'/api/files/{self.secure_code}/serve'

    @property
    def download_url(self):
        """產生前端可用的 download URL"""
        return f'/api/files/{self.secure_code}/download'
