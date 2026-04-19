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
            'url': url,
        })
        return data
