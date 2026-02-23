"""
Drift Detector — 三向偏移偵測

比對 Spec vs FormIO、Spec vs SQL、完整三向比對。
偵測欄位存在性、type 不符、constraints 不符、PII 標記不符。
"""
import logging
from ..sql_sync.converter import FORMIO_TO_PG, SKIP_TYPES, GRID_TYPES

logger = logging.getLogger(__name__)


def _extract_formio_fields(form_schema):
    """
    從 FormIO schema 提取 data fields 的扁平映射

    Returns:
        dict: {field_key: {'type': str, 'validate': dict, 'is_pii': bool}}
    """
    fields = {}

    def _walk(components):
        for comp in (components or []):
            comp_type = comp.get('type', '')

            if comp_type in GRID_TYPES:
                key = comp.get('key')
                if key:
                    properties = comp.get('properties') or {}
                    is_pii = str(properties.get('pii', '')).lower() in ('true', '1')
                    fields[key] = {
                        'type': comp_type,
                        'validate': comp.get('validate') or {},
                        'is_pii': is_pii,
                    }
                continue

            if comp_type in SKIP_TYPES or (
                comp_type not in FORMIO_TO_PG and 'components' in comp
            ):
                _walk(comp.get('components', []))
                for col in comp.get('columns', []):
                    if isinstance(col, dict):
                        _walk(col.get('components', []))
                continue

            key = comp.get('key')
            if not key or key in fields:
                continue
            if comp_type in SKIP_TYPES:
                continue

            properties = comp.get('properties') or {}
            is_pii = str(properties.get('pii', '')).lower() in ('true', '1')
            fields[key] = {
                'type': comp_type,
                'validate': comp.get('validate') or {},
                'is_pii': is_pii,
            }

    _walk(form_schema.get('components', []))
    return fields


def compare_spec_vs_formio(spec_fields, formio_schema):
    """
    Spec vs FormIO 比對

    Args:
        spec_fields: spec fields list
        formio_schema: FormIO schema dict

    Returns:
        list of drifts: [{'field_key': str, 'issue': str, 'detail': str}]
    """
    drifts = []
    formio_fields = _extract_formio_fields(formio_schema or {})
    spec_map = {f['field_key']: f for f in (spec_fields or []) if f.get('field_key')}

    spec_keys = set(spec_map.keys())
    formio_keys = set(formio_fields.keys())

    # spec 有但 FormIO 沒有
    for k in (spec_keys - formio_keys):
        drifts.append({
            'field_key': k,
            'issue': 'missing_in_formio',
            'detail': f'Spec 定義了 "{k}" 但 FormIO schema 中不存在',
            'severity': 'error',
        })

    # FormIO 有但 spec 沒有
    for k in (formio_keys - spec_keys):
        drifts.append({
            'field_key': k,
            'issue': 'missing_in_spec',
            'detail': f'FormIO schema 有 "{k}" 但 Spec 未定義',
            'severity': 'warning',
        })

    # 兩邊都有：比對 type、constraints、PII
    for k in (spec_keys & formio_keys):
        spec_f = spec_map[k]
        formio_f = formio_fields[k]

        # type 比對
        if spec_f['formio_type'] != formio_f['type']:
            drifts.append({
                'field_key': k,
                'issue': 'type_mismatch',
                'detail': f'Spec type={spec_f["formio_type"]}, FormIO type={formio_f["type"]}',
                'severity': 'error',
            })

        # PII 比對
        spec_pii = spec_f.get('is_pii', False)
        formio_pii = formio_f.get('is_pii', False)
        if spec_pii != formio_pii:
            drifts.append({
                'field_key': k,
                'issue': 'pii_mismatch',
                'detail': f'Spec PII={spec_pii}, FormIO PII={formio_pii}',
                'severity': 'error',
            })

        # constraints 比對
        spec_c = spec_f.get('constraints') or {}
        formio_v = formio_f.get('validate') or {}

        if spec_c.get('required', False) != formio_v.get('required', False):
            drifts.append({
                'field_key': k,
                'issue': 'constraint_mismatch',
                'detail': f'required: Spec={spec_c.get("required")}, FormIO={formio_v.get("required")}',
                'severity': 'warning',
            })

        for prop in ('maxLength', 'minLength', 'min', 'max'):
            s_val = spec_c.get(prop)
            f_val = formio_v.get(prop)
            if s_val is not None and f_val is not None and s_val != f_val:
                drifts.append({
                    'field_key': k,
                    'issue': 'constraint_mismatch',
                    'detail': f'{prop}: Spec={s_val}, FormIO={f_val}',
                    'severity': 'warning',
                })

    return drifts


def compare_spec_vs_sql(spec_fields, column_mapping):
    """
    Spec vs SQL 比對

    Args:
        spec_fields: spec fields list
        column_mapping: FwSqlFormRegistry.column_mapping dict

    Returns:
        list of drifts
    """
    drifts = []
    if not column_mapping:
        return drifts

    spec_map = {f['field_key']: f for f in (spec_fields or []) if f.get('field_key')}

    # 過濾掉 metadata key（_ 開頭）
    sql_keys = {k for k in column_mapping.keys() if not k.startswith('_')}
    spec_keys = set(spec_map.keys())

    # spec 有但 SQL 沒有
    for k in (spec_keys - sql_keys):
        drifts.append({
            'field_key': k,
            'issue': 'missing_in_sql',
            'detail': f'Spec 定義了 "{k}" 但 SQL 表無此欄位',
            'severity': 'warning',
        })

    # SQL 有但 spec 沒有
    for k in (sql_keys - spec_keys):
        drifts.append({
            'field_key': k,
            'issue': 'missing_in_spec',
            'detail': f'SQL 表有 "{k}" 但 Spec 未定義',
            'severity': 'info',
        })

    # 兩邊都有：比對 pg_type、PII
    for k in (spec_keys & sql_keys):
        spec_f = spec_map[k]
        sql_col = column_mapping[k]

        if not isinstance(sql_col, dict):
            continue

        # pg_type 比對（spec 可自訂 pg_type）
        from .spec_generator import derive_pg_type
        spec_pg = spec_f.get('pg_type') or derive_pg_type(
            spec_f.get('formio_type', 'textfield'),
            spec_f.get('constraints'),
        )
        sql_pg = sql_col.get('pg_type', '')

        # PII 欄位在 SQL 中是 BYTEA
        spec_pii = spec_f.get('is_pii', False)
        sql_pii = sql_col.get('is_pii', False)

        if spec_pii:
            # spec 標記 PII，SQL 應該是 BYTEA
            if sql_pg.upper() != 'BYTEA':
                drifts.append({
                    'field_key': k,
                    'issue': 'pii_type_mismatch',
                    'detail': f'Spec 標記 PII 但 SQL type={sql_pg}（應為 BYTEA）',
                    'severity': 'error',
                })
        else:
            # 非 PII：比對 pg_type
            if spec_pg.upper() != sql_pg.upper():
                drifts.append({
                    'field_key': k,
                    'issue': 'type_mismatch',
                    'detail': f'Spec pg_type={spec_pg}, SQL pg_type={sql_pg}',
                    'severity': 'warning',
                })

        # PII 標記比對
        if spec_pii != sql_pii:
            drifts.append({
                'field_key': k,
                'issue': 'pii_mismatch',
                'detail': f'Spec PII={spec_pii}, SQL PII={sql_pii}',
                'severity': 'error',
            })

    return drifts


def three_way_compare(spec_fields, formio_schema, column_mapping):
    """
    完整三向比對

    Args:
        spec_fields: spec fields list
        formio_schema: FormIO schema dict
        column_mapping: column_mapping dict (可為 None)

    Returns:
        dict: {spec_vs_formio, spec_vs_sql, summary}
    """
    spec_vs_formio = compare_spec_vs_formio(spec_fields, formio_schema)
    spec_vs_sql = compare_spec_vs_sql(spec_fields, column_mapping)

    formio_fields = _extract_formio_fields(formio_schema or {})
    sql_count = len([
        k for k in (column_mapping or {}).keys()
        if not k.startswith('_')
    ]) if column_mapping else 0

    has_sql = column_mapping is not None
    sf_drifts = len(spec_vs_formio)
    ss_drifts = len(spec_vs_sql)

    # 各組比對狀態: match / mismatch / unavailable
    spec_formio_status = 'match' if sf_drifts == 0 else 'mismatch'
    if has_sql:
        spec_sql_status = 'match' if ss_drifts == 0 else 'mismatch'
    else:
        spec_sql_status = 'unavailable'

    # 整體狀態訊息
    if spec_formio_status == 'match' and spec_sql_status == 'match':
        overall = 'all_match'
    elif spec_formio_status == 'match' and spec_sql_status == 'unavailable':
        overall = 'spec_formio_match_no_sql'
    elif spec_formio_status == 'mismatch' and spec_sql_status == 'unavailable':
        overall = 'spec_formio_mismatch_no_sql'
    elif spec_formio_status == 'match' and spec_sql_status == 'mismatch':
        overall = 'spec_formio_match_sql_mismatch'
    elif spec_formio_status == 'mismatch' and spec_sql_status == 'match':
        overall = 'spec_formio_mismatch_sql_match'
    else:
        overall = 'all_mismatch'

    return {
        'spec_vs_formio': spec_vs_formio,
        'spec_vs_sql': spec_vs_sql,
        'summary': {
            'spec_field_count': len(spec_fields or []),
            'formio_field_count': len(formio_fields),
            'sql_column_count': sql_count,
            'total_drifts': sf_drifts + ss_drifts,
            'has_sql_registry': has_sql,
            'spec_formio_status': spec_formio_status,
            'spec_sql_status': spec_sql_status,
            'overall': overall,
        }
    }
