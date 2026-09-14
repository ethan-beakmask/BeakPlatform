"""
FileAccessLog Model
檔案存取稽核記錄（上傳/下載）
"""
from sqlalchemy import Column, String, Text

from .base import TenantBaseModel


class FileAccessLog(TenantBaseModel):
    """
    檔案存取稽核日誌

    記錄所有檔案的上傳與下載行為，供稽核追蹤。
    透過 context_id 關聯到業務記錄（如表單 SC），
    可與執行日誌整合顯示。

    action:
        - 'upload': 上傳
        - 'download': 下載
        - 'delete': 刪除
    """
    __tablename__ = 'file_access_logs'

    # 檔案資訊
    file_secure_code = Column(String(32), nullable=False, index=True)
    original_name = Column(String(255), nullable=False)

    # 用途 context（與 platform_files 一致）
    context_type = Column(String(50))
    context_id = Column(String(32), index=True)

    # 行為
    action = Column(String(20), nullable=False)

    # 操作者
    user_secure_code = Column(String(32), nullable=False, index=True)
    username = Column(String(100), nullable=False)

    # 來源
    ip_address = Column(String(45))

    def to_dict(self):
        base = super().to_dict()
        base.update({
            'file_secure_code': self.file_secure_code,
            'original_name': self.original_name,
            'context_type': self.context_type,
            'context_id': self.context_id,
            'action': self.action,
            'user_secure_code': self.user_secure_code,
            'username': self.username,
            'ip_address': self.ip_address,
        })
        return base
