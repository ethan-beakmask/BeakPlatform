"""
FormWorkflow Module - Workflow Background Model
流程設計器底圖
"""
import secrets
from sqlalchemy import Column, String, Integer, event

from app.models.base import BaseModel


class FwWorkflowBackground(BaseModel):
    """
    流程設計器底圖

    儲存使用者上傳的底圖，供流程設計器使用。
    """
    __tablename__ = 'fw_workflow_backgrounds'

    # 企業識別碼
    org_secure_code = Column(String(32), nullable=False, index=True)

    # 檔案資訊
    filename = Column(String(255), nullable=False)  # 儲存的檔名（UUID）
    original_filename = Column(String(255), nullable=False)  # 原始檔名
    filepath = Column(String(500), nullable=False)  # 儲存路徑
    filesize = Column(Integer)  # 檔案大小（bytes）
    mimetype = Column(String(100))  # MIME type

    # 圖片尺寸
    width = Column(Integer)
    height = Column(Integer)

    # 描述
    description = Column(String(500))

    def __repr__(self):
        return f'<FwWorkflowBackground {self.original_filename}>'

    def to_dict(self):
        """轉換為字典"""
        data = super().to_dict()
        data.update({
            'filename': self.filename,
            'original_filename': self.original_filename,
            'filesize': self.filesize,
            'mimetype': self.mimetype,
            'width': self.width,
            'height': self.height,
            'description': self.description,
            'url': f'/static/uploads/backgrounds/{self.filename}',
        })
        return data


@event.listens_for(FwWorkflowBackground, 'before_insert')
def generate_background_secure_code(mapper, connection, target):
    """插入前自動生成 secure_code"""
    if not target.secure_code:
        target.secure_code = secrets.token_urlsafe(16)
