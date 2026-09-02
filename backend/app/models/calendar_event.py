"""企業行事曆事件 Model。"""
from typing import Dict, Any

from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, Index, String, Text
from sqlalchemy.orm import relationship

from .base import TenantBaseModel
from .. import db


class CalendarKind:
    ORG = 'ORG'
    PERSONAL = 'PERSONAL'


class CalendarEventType:
    LEAVE = 'LEAVE'
    TRIP = 'TRIP'
    MEETING = 'MEETING'
    ORG_EVENT = 'ORG_EVENT'
    HOLIDAY = 'HOLIDAY'
    OTHER = 'OTHER'


class CalendarVisibility:
    PUBLIC = 'PUBLIC'
    BUSY = 'BUSY'
    PRIVATE = 'PRIVATE'


class CalendarEvent(TenantBaseModel):
    """手建行事曆事件。第一期只提供唯讀投影。"""
    __tablename__ = 'calendar_events'
    __table_args__ = (
        CheckConstraint("ends_at >= starts_at", name='ck_calendar_events_range'),
        CheckConstraint(
            "calendar_kind <> 'PERSONAL' OR owner_user_secure_code IS NOT NULL",
            name='ck_calendar_events_owner',
        ),
        Index('ix_calendar_events_org_starts', 'org_secure_code', 'starts_at'),
        Index('ix_calendar_events_owner_starts', 'owner_user_secure_code', 'starts_at'),
    )

    calendar_kind = Column(String(10), nullable=False, index=True)
    owner_user_secure_code = Column(
        String(32),
        db.ForeignKey('users.secure_code'),
        nullable=True,
        index=True,
    )
    event_type = Column(String(20), nullable=False)
    title = Column(String(200), nullable=False)
    starts_at = Column(DateTime, nullable=False)
    ends_at = Column(DateTime, nullable=False)
    all_day = Column(Boolean, nullable=False, default=False)
    visibility = Column(String(10), nullable=False, default=CalendarVisibility.BUSY)
    source_type = Column(String(30), nullable=True)
    source_secure_code = Column(String(32), nullable=True)
    note = Column(Text, nullable=True)
    created_by = Column(String(100), nullable=True)

    owner = relationship('User', foreign_keys=[owner_user_secure_code])

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            'calendar_kind': self.calendar_kind,
            'owner_user_secure_code': self.owner_user_secure_code,
            'event_type': self.event_type,
            'title': self.title,
            'starts_at': self.starts_at.isoformat() if self.starts_at else None,
            'ends_at': self.ends_at.isoformat() if self.ends_at else None,
            'all_day': self.all_day,
            'visibility': self.visibility,
            'source_type': self.source_type,
            'source_secure_code': self.source_secure_code,
            'note': self.note,
        })
        return base
