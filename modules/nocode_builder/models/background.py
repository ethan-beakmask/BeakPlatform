"""
NoCode Builder - Background Model
底圖圖庫
"""
from sqlalchemy import Column, String, Integer

from .base import ModuleBaseModel


class DcBackground(ModuleBaseModel):
    """底圖圖庫"""
    __tablename__ = 'dc_backgrounds'

    filename = Column(String(255), nullable=False)
    original_filename = Column(String(255), nullable=False)
    filepath = Column(String(500), nullable=False)
    filesize = Column(Integer)
    mimetype = Column(String(100))
    width = Column(Integer)
    height = Column(Integer)
    description = Column(String(500))
    platform_file_sc = Column(String(32), nullable=True)

    def to_dict(self):
        data = super().to_dict()
        if self.platform_file_sc:
            url = f'/api/files/{self.platform_file_sc}/serve'
        else:
            url = f'/bp/static/uploads/backgrounds/{self.filename}'
        data.update({
            'filename': self.filename,
            'original_filename': self.original_filename,
            'filesize': self.filesize,
            'mimetype': self.mimetype,
            'width': self.width,
            'height': self.height,
            'description': self.description,
            # menu widget 的底圖存的是 platform_files 的 secure_code（renderer 會用它
            # 查 context_type=nc_background），不是 DcBackground 自己的 secure_code。
            # 少了這個欄位，前端只能存錯的 sc，底圖選了永遠不生效。
            'platform_file_sc': self.platform_file_sc,
            'url': url,
        })
        return data
