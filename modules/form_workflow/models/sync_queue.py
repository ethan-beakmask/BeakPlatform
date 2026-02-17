"""
FormWorkflow Module - Sync Queue Model
SQL 同步佇列

表單提交/簽核時寫入佇列，由背景 Worker 非同步處理。
"""
import secrets
from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, Text, event
from .base import ModuleBaseModel


class FwSyncQueue(ModuleBaseModel):
    """
    SQL 同步佇列

    每筆表單提交或簽核修改都會產生一筆佇列項目，
    由背景 Worker 撈取後 UPSERT 到企業專屬資料庫。
    """
    __tablename__ = 'fw_sync_queue'

    # 同步目標
    form_instance_secure_code = Column(String(32), nullable=False, index=True)
    published_secure_code = Column(String(32), nullable=False, index=True)
    registry_id = Column(Integer, index=True)  # FwSqlFormRegistry.id (加速 worker 查詢)

    # 動作
    action = Column(String(20), nullable=False, default='upsert')  # upsert / delete

    # 狀態
    status = Column(String(20), nullable=False, default='pending', index=True)
    # pending → processing → completed / failed

    # 重試
    retry_count = Column(Integer, default=0, nullable=False)
    max_retries = Column(Integer, default=3, nullable=False)
    last_error = Column(Text)

    # 時間
    queued_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)

    def __repr__(self):
        return f'<FwSyncQueue {self.status}: {self.form_instance_secure_code}>'

    def mark_processing(self):
        self.status = 'processing'
        self.started_at = datetime.utcnow()

    def mark_completed(self):
        self.status = 'completed'
        self.completed_at = datetime.utcnow()

    def mark_failed(self, error_msg):
        self.retry_count += 1
        self.last_error = str(error_msg)[:2000]
        if self.retry_count >= self.max_retries:
            self.status = 'failed'
        else:
            self.status = 'pending'  # 回到待處理，等待重試

    def to_dict(self):
        base = super().to_dict()
        base.update({
            'form_instance_secure_code': self.form_instance_secure_code,
            'published_secure_code': self.published_secure_code,
            'action': self.action,
            'status': self.status,
            'retry_count': self.retry_count,
            'last_error': self.last_error,
            'queued_at': self.queued_at.isoformat() if self.queued_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
        })
        return base


@event.listens_for(FwSyncQueue, 'before_insert')
def generate_queue_secure_code(mapper, connection, target):
    if not target.secure_code:
        target.secure_code = secrets.token_urlsafe(16)
