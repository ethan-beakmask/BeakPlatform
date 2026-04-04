"""
FormWorkflow Module - Approval Canned Message Model
簽核罐頭訊息
"""
from sqlalchemy import Column, String, Text, Integer

from .base import ModuleBaseModel


class FwApprovalCannedMessage(ModuleBaseModel):
    """
    簽核罐頭訊息

    用戶可自訂常用的簽核意見文字，簽核時快速選取追加。
    """
    __tablename__ = 'fw_approval_canned_messages'

    user_secure_code = Column(String(32), nullable=False, index=True)
    text = Column(Text, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)

    def __repr__(self):
        return f'<FwApprovalCannedMessage {self.secure_code}: {self.text[:20]}>'

    def to_dict(self):
        data = super().to_dict()
        data.update({
            'text': self.text,
            'sort_order': self.sort_order,
        })
        return data
