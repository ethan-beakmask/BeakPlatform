"""
OpenDefense Module - Models

所有模型使用 'od_' 前綴以避免表名衝突。
"""
from .base import OdBaseModel
from .intake_key import OdIntakeKey
from .intake_event import OdIntakeEvent
from .defense_decision import (
    OdDefenseDecision,
    VALID_ACTIONS,
    VALID_TARGET_TYPES,
    VALID_DECIDED_VIA,
    VALID_STATUSES,
    VALID_SEVERITIES,
)
from .service_account import OdServiceAccount
from .form_template_mapping import OdFormTemplateMapping
from .payload_profile import OdPayloadProfile
from .protected_target import OdProtectedTarget, VALID_PROTECTED_ENTRY_TYPES

__all__ = [
    'OdBaseModel',
    'OdIntakeKey',
    'OdIntakeEvent',
    'OdDefenseDecision',
    'OdServiceAccount',
    'OdFormTemplateMapping',
    'OdPayloadProfile',
    'OdProtectedTarget',
    'VALID_ACTIONS',
    'VALID_TARGET_TYPES',
    'VALID_DECIDED_VIA',
    'VALID_STATUSES',
    'VALID_SEVERITIES',
    'VALID_PROTECTED_ENTRY_TYPES',
]
