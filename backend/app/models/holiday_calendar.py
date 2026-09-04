"""Enterprise holiday calendar drafts and published snapshots."""
from typing import Any, Dict

from sqlalchemy import Column, Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from .base import TenantBaseModel


class HolidayCalendarSource:
    TW_GOV = 'TW_GOV'
    CUSTOM = 'CUSTOM'
    ALL = (TW_GOV, CUSTOM)


class HolidayCalendarStatus:
    DRAFT = 'DRAFT'
    PUBLISHED = 'PUBLISHED'


class HolidayEntryStage:
    DRAFT = 'DRAFT'
    PUBLISHED = 'PUBLISHED'


class HolidayCalendar(TenantBaseModel):
    __tablename__ = 'holiday_calendars'
    __table_args__ = (
        Index(
            'uq_holiday_calendars_org_gov_year',
            'org_secure_code',
            'year',
            unique=True,
            postgresql_where=text("source = 'TW_GOV' AND is_deleted = false"),
        ),
    )

    name = Column(String(100), nullable=False)
    source = Column(String(20), nullable=False)
    year = Column(Integer, nullable=True)
    status = Column(String(20), nullable=False, default=HolidayCalendarStatus.DRAFT)
    published_at = Column(DateTime, nullable=True)
    published_targets = Column(JSONB, nullable=True)
    source_ref = Column(String(500), nullable=True)
    note = Column(Text, nullable=True)

    entries = relationship(
        'HolidayCalendarEntry',
        back_populates='calendar',
        cascade='all, delete-orphan',
    )

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            'name': self.name,
            'source': self.source,
            'year': self.year,
            'status': self.status,
            'published_at': self.published_at.isoformat() if self.published_at else None,
            'published_targets': self.published_targets or [],
            'source_ref': self.source_ref,
            'note': self.note,
            'draft_count': getattr(self, 'draft_count', 0),
            'published_count': getattr(self, 'published_count', 0),
            'has_unpublished_changes': getattr(self, 'has_unpublished_changes', False),
            'published_target_names': getattr(self, 'published_target_names', []),
        })
        return base

    def __repr__(self):
        return f'<HolidayCalendar {self.name}: {self.source}>'


class HolidayCalendarEntry(TenantBaseModel):
    __tablename__ = 'holiday_calendar_entries'
    __table_args__ = (
        UniqueConstraint(
            'calendar_secure_code',
            'stage',
            'entry_date',
            name='uq_holiday_calendar_entries_calendar_stage_date',
        ),
    )

    calendar_secure_code = Column(
        String(32),
        ForeignKey('holiday_calendars.secure_code'),
        nullable=False,
        index=True,
    )
    stage = Column(String(20), nullable=False)
    entry_date = Column(Date, nullable=False)
    holiday_type = Column(String(20), nullable=False)
    work_periods = Column(JSONB, nullable=True)
    description = Column(String(200), nullable=True)

    calendar = relationship('HolidayCalendar', back_populates='entries')

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            'calendar_secure_code': self.calendar_secure_code,
            'stage': self.stage,
            'entry_date': self.entry_date.isoformat() if self.entry_date else None,
            'holiday_type': self.holiday_type,
            'work_periods': self.work_periods,
            'description': self.description,
        })
        return base

    def __repr__(self):
        return f'<HolidayCalendarEntry {self.entry_date}: {self.holiday_type}>'
