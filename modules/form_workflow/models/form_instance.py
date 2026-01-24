"""
FormWorkflow Module - Form Instance Model
表單實例（用戶填寫的表單）
"""
from datetime import datetime
from sqlalchemy import Column, BigInteger, String, Text, Boolean, DateTime
from sqlalchemy.dialects.postgresql import JSON

from .base import ModuleBaseModel


class FwFormInstance(ModuleBaseModel):
    """
    表單實例

    用戶填寫並提交的表單。
    """
    __tablename__ = 'fw_form_instances'

    # 關聯的模板（保留 ID 方便快速查詢）
    form_template_id = Column(BigInteger, nullable=True, index=True)
    form_template_secure_code = Column(String(32), nullable=False, index=True)
    workflow_template_id = Column(BigInteger, nullable=True, index=True)
    workflow_template_secure_code = Column(String(32), nullable=True, index=True)
    published_secure_code = Column(String(32), nullable=True, index=True)

    # 流程實例關聯
    workflow_instance_id = Column(BigInteger, nullable=True, index=True)
    workflow_instance_secure_code = Column(String(32), nullable=True, index=True)

    # 表單基本資訊（快照）
    form_name = Column(String(200), nullable=True)
    form_code = Column(String(100), nullable=True)
    form_version = Column(String(10), nullable=True)

    # 測試標記
    is_test = Column(Boolean, default=False, nullable=False, index=True)

    # 來源資訊
    source_type = Column(String(50), default='WEB', nullable=False)
    source_ip = Column(String(100), nullable=True)
    source_user_agent = Column(Text, nullable=True)
    source_api_key = Column(String(200), nullable=True)

    # 申請人（使用 secure_code，不直接關聯 users 表）
    applicant_secure_code = Column(String(32), nullable=True, index=True)
    applicant_name = Column(String(200), nullable=True)
    applicant_dept = Column(String(200), nullable=True)
    applicant_username = Column(String(200), nullable=True)
    applicant_email = Column(String(200), nullable=True)

    # 表單內容
    form_data = Column(JSON, nullable=False)
    schema_snapshot = Column(JSON, nullable=True)  # 表單 schema 快照
    builder_config = Column(JSON, nullable=True)

    # 狀態：DRAFT, INITIAL, PENDING, APPROVED, REJECTED, CANCELLED
    status = Column(String(50), default='DRAFT', nullable=False, index=True)
    current_node_id = Column(String(100), nullable=True)

    # 編號
    serial_number = Column(String(100), unique=True, nullable=False, index=True)

    # 時間
    submitted_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # 狀態名稱對應
    STATUS_NAMES = {
        'DRAFT': '草稿',
        'INITIAL': '初始化',
        'PENDING': '簽核中',
        'APPROVED': '已核准',
        'REJECTED': '已退回',
        'CANCELLED': '已取消',
    }

    def __repr__(self):
        return f'<FwFormInstance {self.serial_number}: {self.status}>'

    def to_dict(self, include_form_data=True):
        """轉換為字典"""
        data = super().to_dict()
        data.update({
            'serial_number': self.serial_number,
            'status': self.status,
            'status_name': self.STATUS_NAMES.get(self.status, self.status),
            'form_template_secure_code': self.form_template_secure_code,
            'workflow_template_secure_code': self.workflow_template_secure_code,
            'workflow_instance_secure_code': self.workflow_instance_secure_code,
            'form_name': self.form_name,
            'form_code': self.form_code,
            'form_version': self.form_version,
            'applicant_name': self.applicant_name,
            'applicant_dept': self.applicant_dept,
            'applicant_username': self.applicant_username,
            'applicant_email': self.applicant_email,
            'is_test': self.is_test,
            'source_type': self.source_type,
            'current_node_id': self.current_node_id,
        })

        if include_form_data:
            data['form_data'] = self.form_data

        if self.submitted_at:
            data['submitted_at'] = self.submitted_at.isoformat()
        if self.completed_at:
            data['completed_at'] = self.completed_at.isoformat()

        return data

    def is_draft(self):
        return self.status == 'DRAFT'

    def is_pending(self):
        return self.status == 'PENDING'

    def is_completed(self):
        return self.status in ['APPROVED', 'REJECTED', 'CANCELLED']

    def submit(self):
        """提交表單"""
        if not self.is_draft():
            raise ValueError('只有草稿狀態的表單可以提交')
        self.status = 'PENDING'
        self.submitted_at = datetime.utcnow()

    def approve(self):
        """核准"""
        self.status = 'APPROVED'
        self.completed_at = datetime.utcnow()

    def reject(self):
        """退回"""
        self.status = 'REJECTED'
        self.completed_at = datetime.utcnow()

    def cancel(self):
        """取消"""
        self.status = 'CANCELLED'
        self.completed_at = datetime.utcnow()
