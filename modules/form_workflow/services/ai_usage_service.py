"""
FormWorkflow Module - AiAgent Usage and Quota Service

這是 AiAgent 節點用量記錄與配額判定的唯一實作位置。其他 handler、API 或管理
介面不得自行組配額 SQL，也不得自行讀寫 `ai_node_*` 或 `ai_node_defaults` 設定 key；
集中在此才能維持租戶過濾、時區日界/月界與 blocked 不計入配額的一致性。
"""
import json
import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text

from app import db
from app.models.organization import Organization
from app.models.system_setting import SystemSetting
from app.utils.timezone import local_day_start_utc, local_month_start_utc

from ..models.ai_usage_record import FwAiUsageRecord

logger = logging.getLogger(__name__)

HARDCODED_DEFAULTS = {
    'enabled': True,
    'daily_max_runs': 50,
    'monthly_max_runs': 1000,
    'daily_max_cost_usd': 1.0,
    'monthly_max_cost_usd': 20.0,
}
SYSTEM_SETTING_KEY = 'ai_node_defaults'
ORG_SETTING_PREFIX = 'ai_node_'

_KNOWN_KEYS = tuple(HARDCODED_DEFAULTS.keys())
_RUN_KEYS = {'daily_max_runs', 'monthly_max_runs'}
_COST_KEYS = {'daily_max_cost_usd', 'monthly_max_cost_usd'}
_COUNTED_STATUSES = (
    FwAiUsageRecord.STATUS_RUNNING,
    FwAiUsageRecord.STATUS_SUCCESS,
    FwAiUsageRecord.STATUS_FAILED,
)


def _system_defaults() -> Dict[str, Any]:
    setting = SystemSetting.query.filter_by(key=SYSTEM_SETTING_KEY).first()
    if not setting:
        return {}
    try:
        value = setting.get_value()
    except Exception:
        try:
            value = json.loads(setting.value or '{}')
        except Exception:
            return {}
    return value if isinstance(value, dict) else {}


def _normalize_bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() not in ('', '0', 'false', 'no', 'off')
    return bool(value)


def _normalize_limit(value: Any, *, integer: bool) -> Any:
    if value is None:
        return None
    try:
        if integer:
            normalized = int(value)
        else:
            normalized = float(value)
    except (TypeError, ValueError):
        return 0 if integer else 0.0
    if normalized < 0:
        return 0 if integer else 0.0
    return normalized


def _to_int(value: Any) -> int:
    try:
        if isinstance(value, bool):
            return 0
        return int(value)
    except (TypeError, ValueError):
        return 0


def _to_decimal(value: Any) -> Decimal:
    try:
        if isinstance(value, bool) or value is None:
            return Decimal('0')
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return Decimal('0')


def _valid_limit(limit: Any) -> bool:
    return limit is not None and float(limit) > 0


def _truncate_error(message: Optional[str]) -> Optional[str]:
    if not message:
        return None
    return str(message)[:1000]


def get_effective_config(org) -> dict:
    """取得企業有效 AiAgent 配額設定，逐項套用 org -> system -> hardcoded fallback。"""
    system = _system_defaults()
    result = {}
    for key, default in HARDCODED_DEFAULTS.items():
        sentinel = object()
        org_value = org.get_setting(f'{ORG_SETTING_PREFIX}{key}', sentinel) if org else sentinel
        if org_value is not sentinel:
            value = org_value
        elif key in system:
            value = system[key]
        else:
            value = default

        if key == 'enabled':
            result[key] = _normalize_bool(value)
        elif key in _RUN_KEYS:
            result[key] = _normalize_limit(value, integer=True)
        else:
            result[key] = _normalize_limit(value, integer=False)
    return result


def get_config_with_source(org) -> list:
    """取得企業 AiAgent 配額設定與來源，供管理 UI 呈現。"""
    system = _system_defaults()
    rows = []
    for key, default in HARDCODED_DEFAULTS.items():
        sentinel = object()
        org_value = org.get_setting(f'{ORG_SETTING_PREFIX}{key}', sentinel) if org else sentinel
        if org_value is not sentinel:
            value = org_value
            source = 'org'
        elif key in system:
            value = system[key]
            source = 'system'
        else:
            value = default
            source = 'default'

        if key == 'enabled':
            value = _normalize_bool(value)
            system_default = _normalize_bool(system.get(key, default))
        elif key in _RUN_KEYS:
            value = _normalize_limit(value, integer=True)
            system_default = _normalize_limit(system.get(key, default), integer=True)
        else:
            value = _normalize_limit(value, integer=False)
            system_default = _normalize_limit(system.get(key, default), integer=False)

        rows.append({
            'key': key,
            'value': value,
            'source': source,
            'system_default': system_default,
        })
    return rows


def set_org_config(org, updates: dict) -> list[str]:
    """寫入企業層 AiAgent 設定；不 commit。回傳被忽略的未知 key。"""
    ignored = []
    for key, value in (updates or {}).items():
        if key not in _KNOWN_KEYS:
            ignored.append(key)
            continue
        if key == 'enabled':
            normalized = _normalize_bool(value)
        elif key in _RUN_KEYS:
            if value is None:
                normalized = None
            else:
                try:
                    normalized = int(value)
                except (TypeError, ValueError):
                    ignored.append(key)
                    continue
                if normalized < 0:
                    ignored.append(key)
                    continue
        else:
            if value is None:
                normalized = None
            else:
                try:
                    normalized = float(value)
                except (TypeError, ValueError):
                    ignored.append(key)
                    continue
                if normalized < 0:
                    ignored.append(key)
                    continue
        org.set_setting(f'{ORG_SETTING_PREFIX}{key}', normalized)
    return ignored


def clear_org_config(org, keys: list[str]) -> None:
    """清除指定企業層覆寫，回歸系統預設；不 commit。"""
    settings = org.get_settings()
    for key in keys or []:
        if key in _KNOWN_KEYS:
            settings.pop(f'{ORG_SETTING_PREFIX}{key}', None)
    org.settings = json.dumps(settings, ensure_ascii=False)


def get_period_usage(org_secure_code, tz_name) -> dict:
    """回傳企業在當地今日與本月已佔用的 AiAgent 次數與估算成本。"""
    now = datetime.utcnow()
    day_start = local_day_start_utc(tz_name, now)
    month_start = local_month_start_utc(tz_name, now)

    def _aggregate(start):
        row = db.session.query(
            db.func.count(FwAiUsageRecord.id),
            db.func.coalesce(db.func.sum(FwAiUsageRecord.cost_usd), 0),
        ).filter(
            FwAiUsageRecord.org_secure_code == org_secure_code,
            FwAiUsageRecord.is_deleted == False,
            FwAiUsageRecord.status.in_(_COUNTED_STATUSES),
            FwAiUsageRecord.started_at >= start,
        ).one()
        return int(row[0] or 0), float(row[1] or 0)

    daily_runs, daily_cost = _aggregate(day_start)
    monthly_runs, monthly_cost = _aggregate(month_start)
    return {
        'day_start': day_start,
        'month_start': month_start,
        'daily_runs': daily_runs,
        'daily_cost': daily_cost,
        'monthly_runs': monthly_runs,
        'monthly_cost': monthly_cost,
    }


def _blocked_record(reason: str, **kwargs) -> Tuple[None, str]:
    """記錄一次被擋下的嘗試；同一個節點佇列項目只記一次。

    流程引擎對回 error 的節點一律重試到 max_retries（`FwNodeExecutionQueue.fail()`
    沒有「不可重試」的分支），而配額不會在重試的幾秒內恢復，所以同一個節點會被擋
    3 次。去重的理由是語意：「這個節點被配額擋下」是一次事件，不是三次，
    否則管理頁的「被擋次數」會虛報 3 倍。
    重試本身無害 —— 被擋下時根本沒呼叫 CLI，不消耗任何額度。
    """
    queue_code = kwargs.get('node_queue_secure_code')
    if queue_code:
        existing = FwAiUsageRecord.query.filter_by(
            node_queue_secure_code=queue_code,
            status=FwAiUsageRecord.STATUS_BLOCKED,
            is_deleted=False,
        ).first()
        if existing:
            db.session.commit()   # 釋放 advisory lock，不新增記錄
            return None, reason

    now = datetime.utcnow()
    rec = FwAiUsageRecord(
        status=FwAiUsageRecord.STATUS_BLOCKED,
        error_message=reason,
        started_at=now,
        finished_at=now,
        **kwargs,
    )
    db.session.add(rec)
    db.session.commit()
    return None, reason


def check_and_reserve(
    org_secure_code,
    workflow_instance_secure_code,
    node_id,
    node_name,
    node_queue_secure_code,
    form_instance_secure_code,
    model,
) -> tuple:
    """檢查配額並寫入 running 佔位列；此函式會 commit 以釋放 advisory lock。"""
    org = Organization.query.filter_by(
        secure_code=org_secure_code,
        is_deleted=False,
    ).first()
    if not org:
        return None, '找不到流程所屬企業，AiAgent 節點無法執行'

    tz_name = org.get_setting('timezone', 'Asia/Taipei')
    # pg_advisory_xact_lock 是 PostgreSQL 專用；其他 dialect 測試環境沒有此函式。
    if db.engine.dialect.name == 'postgresql':
        db.session.execute(
            text('SELECT pg_advisory_xact_lock(hashtext(:k))'),
            {'k': f'ai_usage:{org_secure_code}'},
        )
    else:
        logger.warning(
            'AiAgent usage quota advisory lock skipped for dialect %s',
            db.engine.dialect.name,
        )

    record_kwargs = {
        'org_secure_code': org_secure_code,
        'workflow_instance_secure_code': workflow_instance_secure_code,
        'node_id': node_id,
        'node_name': node_name,
        'node_queue_secure_code': node_queue_secure_code,
        'form_instance_secure_code': form_instance_secure_code,
        'model': model,
    }

    cfg = get_effective_config(org)
    if not cfg['enabled']:
        return _blocked_record('本企業已停用 AI 分析節點', **record_kwargs)

    usage = get_period_usage(org_secure_code, tz_name)
    checks = (
        ('daily_max_runs', 'daily_runs', 'AI 分析節點今日執行次數已達上限', '{used}/{limit:g}'),
        ('monthly_max_runs', 'monthly_runs', 'AI 分析節點本月執行次數已達上限', '{used}/{limit:g}'),
        ('daily_max_cost_usd', 'daily_cost', 'AI 分析節點今日估算成本已達上限', '${used:.4f}/${limit:.2f}'),
        ('monthly_max_cost_usd', 'monthly_cost', 'AI 分析節點本月估算成本已達上限', '${used:.4f}/${limit:.2f}'),
    )
    for limit_key, used_key, label, fmt in checks:
        limit = cfg[limit_key]
        if not _valid_limit(limit):
            continue
        used = usage[used_key]
        if used >= limit:
            reason = f'{label}（{fmt.format(used=used, limit=float(limit))}）'
            return _blocked_record(reason, **record_kwargs)

    rec = FwAiUsageRecord(
        status=FwAiUsageRecord.STATUS_RUNNING,
        started_at=datetime.utcnow(),
        **record_kwargs,
    )
    db.session.add(rec)
    db.session.commit()
    return rec, None


def finalize(record, envelope, error_message=None) -> None:
    """補完 running 用量列；本函式失敗不得影響流程執行。"""
    try:
        usage = envelope.get('usage') if isinstance(envelope, dict) else {}
        if not isinstance(usage, dict):
            usage = {}
        model_usage = envelope.get('modelUsage') if isinstance(envelope, dict) else None

        record.input_tokens = _to_int(usage.get('input_tokens'))
        record.output_tokens = _to_int(usage.get('output_tokens'))
        record.cache_creation_input_tokens = _to_int(usage.get('cache_creation_input_tokens'))
        record.cache_read_input_tokens = _to_int(usage.get('cache_read_input_tokens'))
        record.duration_ms = _to_int(envelope.get('duration_ms') if isinstance(envelope, dict) else None)
        record.num_turns = _to_int(envelope.get('num_turns') if isinstance(envelope, dict) else None)

        cost = _to_decimal(envelope.get('total_cost_usd') if isinstance(envelope, dict) else None)
        if cost == 0 and isinstance(model_usage, dict):
            cost = sum((_to_decimal(row.get('costUSD')) for row in model_usage.values()
                        if isinstance(row, dict)), Decimal('0'))
        record.cost_usd = cost
        record.model_usage = model_usage if isinstance(model_usage, dict) else None
        record.status = (FwAiUsageRecord.STATUS_FAILED if error_message
                         else FwAiUsageRecord.STATUS_SUCCESS)
        record.error_message = _truncate_error(error_message)
        record.finished_at = datetime.utcnow()
        db.session.commit()
    except Exception as exc:
        logger.warning('AiAgent usage finalize failed: %s', exc)
        db.session.rollback()


def summarize(org_secure_code, tz_name, start=None, end=None) -> dict:
    """彙總企業指定期間內的 AiAgent 用量。

    start 未指定時以企業當地本月 1 日零點為起點（TZ-01：日曆邊界一律換算成
    顯示時區，不能用 UTC 的月初）。start/end 都是 naive UTC。
    """
    if start is None:
        start = local_month_start_utc(tz_name, datetime.utcnow())
    query = FwAiUsageRecord.query.filter(
        FwAiUsageRecord.org_secure_code == org_secure_code,
        FwAiUsageRecord.is_deleted == False,
    )
    if start is not None:
        query = query.filter(FwAiUsageRecord.started_at >= start)
    if end is not None:
        query = query.filter(FwAiUsageRecord.started_at < end)

    records = query.all()
    status_counts = {
        FwAiUsageRecord.STATUS_RUNNING: 0,
        FwAiUsageRecord.STATUS_SUCCESS: 0,
        FwAiUsageRecord.STATUS_FAILED: 0,
        FwAiUsageRecord.STATUS_BLOCKED: 0,
    }
    by_model: Dict[str, Dict[str, Any]] = {}
    total_input = total_output = total_cache_create = total_cache_read = 0
    total_cost = Decimal('0')

    for rec in records:
        status_counts[rec.status] = status_counts.get(rec.status, 0) + 1
        total_input += rec.input_tokens or 0
        total_output += rec.output_tokens or 0
        total_cache_create += rec.cache_creation_input_tokens or 0
        total_cache_read += rec.cache_read_input_tokens or 0
        total_cost += _to_decimal(rec.cost_usd)

        model = rec.model or 'unknown'
        bucket = by_model.setdefault(model, {
            'model': model,
            'runs': 0,
            'input_tokens': 0,
            'output_tokens': 0,
            'cache_creation_input_tokens': 0,
            'cache_read_input_tokens': 0,
            'cost_usd': 0.0,
        })
        bucket['runs'] += 1
        bucket['input_tokens'] += rec.input_tokens or 0
        bucket['output_tokens'] += rec.output_tokens or 0
        bucket['cache_creation_input_tokens'] += rec.cache_creation_input_tokens or 0
        bucket['cache_read_input_tokens'] += rec.cache_read_input_tokens or 0
        bucket['cost_usd'] = float(_to_decimal(bucket['cost_usd']) + _to_decimal(rec.cost_usd))

    return {
        'start': start,
        'end': end,
        'total_runs': len(records),
        'status_counts': status_counts,
        'input_tokens': total_input,
        'output_tokens': total_output,
        'cache_creation_input_tokens': total_cache_create,
        'cache_read_input_tokens': total_cache_read,
        'cost_usd': float(total_cost),
        'by_model': list(by_model.values()),
    }
