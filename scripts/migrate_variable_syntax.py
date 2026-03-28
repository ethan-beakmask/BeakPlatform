"""
變數系統 v2 語法遷移腳本

掃描所有 workflow template 的 graph JSON，將節點配置中的舊變數語法轉換為 v2 前綴制語法。

用法：
    python scripts/migrate_variable_syntax.py --dry-run   # 預覽變更
    python scripts/migrate_variable_syntax.py             # 執行遷移

遷移規則：
  引用語法 (${...} 內部):
    ${form.field}           → ${f.field}
    ${form.applicant_name}  → ${fi.applicant}
    ${form.serial_number}   → ${fi.serial}
    ${workflow.instance_code}→ ${wi.code}
    ${workflow.name}        → ${wi.name}
    ${workflow.execution_code}→ ${wi.exec_code}
    ${timestamp}            → ${t.now}
    ${timestamp.date}       → ${t.date}
    ${timestamp.time}       → ${t.time}
    ${node.display_name}    → ${n.name}
    ${表單名::欄位}          → ${f.<key>} (查 form schema)
    ${bare_name}            → ${v.bare_name} (非保留前綴且非表單欄位)
"""
import argparse
import json
import logging
import os
import re
import sys

# 基於本檔位置動態偵測專案路徑
_script_dir = os.path.dirname(os.path.abspath(__file__))
_project_dir = os.path.dirname(_script_dir)
sys.path.insert(0, os.path.join(_project_dir, 'backend'))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

# fi. 對應的舊 form.* 系統欄位
FORM_SYSTEM_FIELDS = {
    'form.applicant_name': 'fi.applicant',
    'form.applicant_dept': 'fi.applicant_dept',
    'form.applicant_email': 'fi.applicant_email',
    'form.applicant_code': 'fi.applicant_code',
    'form.serial_number': 'fi.serial',
    'form.display_name': 'fi.name',
    'form.instance_code': 'fi.code',
    'form.instance_id': 'fi.code',  # id → code
}

# wi. 對應的舊 workflow.* 欄位
WORKFLOW_FIELDS = {
    'workflow.instance_code': 'wi.code',
    'workflow.instance_id': 'wi.code',
    'workflow.name': 'wi.name',
    'workflow.execution_code': 'wi.exec_code',
}

# t. 對應的舊 timestamp 欄位
TIMESTAMP_FIELDS = {
    'timestamp': 't.now',
    'timestamp.date': 't.date',
    'timestamp.time': 't.time',
}

# n. 對應的舊 node.* 欄位
NODE_FIELDS = {
    'node.display_name': 'n.name',
}

# v2 前綴集合（不需要遷移的）
V2_PREFIXES = ('f.', 'fi.', 'v.', 'wi.', 'n.', 't.')


def get_form_field_label_to_key(form_instance_code, db_session):
    """
    查表單 schema 建立 label → key 映射（用於 :: 語法遷移）
    """
    from modules.form_workflow.models import FwFormInstance, FwFormTemplate
    fi = FwFormInstance.query.filter_by(secure_code=form_instance_code).first()
    if not fi:
        return {}

    ft = FwFormTemplate.query.filter_by(secure_code=fi.form_template_secure_code).first()
    if not ft or not ft.schema:
        return {}

    mapping = {}
    schema = ft.schema
    components = schema.get('components', [])
    if not components and 'schema' in schema:
        components = schema['schema'].get('components', [])

    def walk(comps):
        for comp in comps:
            key = comp.get('key')
            label = comp.get('label')
            if key and label:
                mapping[label] = key
            # 遞迴子元件
            for sub_key in ('components', 'columns', 'rows'):
                sub = comp.get(sub_key)
                if isinstance(sub, list):
                    for item in sub:
                        if isinstance(item, dict):
                            if 'components' in item:
                                walk(item['components'])
                            elif 'key' in item:
                                if item.get('key') and item.get('label'):
                                    mapping[item['label']] = item['key']

    walk(components)
    return mapping


def migrate_var_expr(var_expr, label_to_key=None):
    """
    遷移單一變數表達式（${...} 內部的文字）

    Returns:
        (new_expr, changed: bool)
    """
    # 已是 v2 前綴 → 不動
    for prefix in V2_PREFIXES:
        if var_expr.startswith(prefix):
            return var_expr, False

    # form.* 系統欄位 → fi.*
    if var_expr in FORM_SYSTEM_FIELDS:
        return FORM_SYSTEM_FIELDS[var_expr], True

    # form.* 一般欄位 → f.*
    if var_expr.startswith('form.'):
        return 'f.' + var_expr[5:], True

    # workflow.* → wi.*
    if var_expr in WORKFLOW_FIELDS:
        return WORKFLOW_FIELDS[var_expr], True
    if var_expr.startswith('workflow.'):
        return 'wi.' + var_expr[9:], True

    # timestamp* → t.*
    if var_expr in TIMESTAMP_FIELDS:
        return TIMESTAMP_FIELDS[var_expr], True
    if var_expr.startswith('timestamp'):
        return 't.' + var_expr[len('timestamp'):].lstrip('.'), True

    # node.* → n.*
    if var_expr in NODE_FIELDS:
        return NODE_FIELDS[var_expr], True
    if var_expr.startswith('node.'):
        return 'n.' + var_expr[5:], True

    # 顯示變數 (表單名::欄位標籤) → f.<key>
    if '::' in var_expr:
        parts = var_expr.split('::')
        if len(parts) == 2:
            field_label = parts[1].strip()
            # 處理 "標籤(key)" 格式
            explicit_key = None
            if '(' in field_label and field_label.endswith(')'):
                idx = field_label.rfind('(')
                explicit_key = field_label[idx + 1:-1]
                field_label = field_label[:idx]

            if explicit_key:
                return f'f.{explicit_key}', True

            if label_to_key and field_label in label_to_key:
                return f'f.{label_to_key[field_label]}', True

            # 找不到 key，保留原樣
            logger.warning(f"  顯示變數 '{var_expr}' 找不到對應 key，保留原樣")
            return var_expr, False

    # 無前綴裸名 → v.<name>
    # 排除看起來像表單欄位的（含空格或中文）
    if re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', var_expr):
        return f'v.{var_expr}', True

    # 其他（含中文等）保留原樣
    logger.warning(f"  無法遷移 '{var_expr}'，保留原樣")
    return var_expr, False


def migrate_text(text, label_to_key=None):
    """
    遷移文字中的所有 ${...} 引用

    Returns:
        (new_text, changes: list of (old, new))
    """
    if not isinstance(text, str) or '${' not in text:
        return text, []

    changes = []

    def replace_fn(match):
        old_expr = match.group(1)
        new_expr, changed = migrate_var_expr(old_expr, label_to_key)
        if changed:
            changes.append((f'${{{old_expr}}}', f'${{{new_expr}}}'))
        return f'${{{new_expr}}}'

    new_text = re.sub(r'\$\{([^}]+)\}', replace_fn, text)
    return new_text, changes


def migrate_config(config, label_to_key=None):
    """
    遞迴遍歷 node config，遷移所有文字欄位中的變數引用

    Returns:
        (new_config, all_changes)
    """
    if not config:
        return config, []

    all_changes = []

    def walk(obj):
        if isinstance(obj, str):
            new_val, changes = migrate_text(obj, label_to_key)
            all_changes.extend(changes)
            return new_val
        elif isinstance(obj, dict):
            return {k: walk(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [walk(item) for item in obj]
        return obj

    new_config = walk(config)
    return new_config, all_changes


def process_template(template, dry_run=True):
    """處理單一 workflow template"""
    graph = template.graph
    if not graph or 'nodes' not in graph:
        return 0

    total_changes = 0
    graph_modified = False

    # 嘗試找表單 label→key 映射
    label_to_key = {}
    # workflow template 可能對應多個 form，這裡取 graph 中 FormAdapter 不直接幫助
    # 改由 form_template 的 schema 取
    try:
        from modules.form_workflow.models import FwFormTemplate, FwFormWorkflowMapping
        mapping = FwFormWorkflowMapping.query.filter_by(
            workflow_template_secure_code=template.secure_code,
            is_deleted=False
        ).first()
        if mapping:
            ft = FwFormTemplate.query.filter_by(
                secure_code=mapping.form_template_secure_code
            ).first()
            if ft and ft.schema:
                schema = ft.schema
                components = schema.get('components', [])
                if not components and 'schema' in schema:
                    components = schema['schema'].get('components', [])

                def walk_comps(comps):
                    for comp in comps:
                        key = comp.get('key')
                        label = comp.get('label')
                        if key and label:
                            label_to_key[label] = key
                        for sub_key in ('components', 'columns', 'rows'):
                            sub = comp.get(sub_key)
                            if isinstance(sub, list):
                                for item in sub:
                                    if isinstance(item, dict):
                                        if 'components' in item:
                                            walk_comps(item['components'])
                                        elif item.get('key') and item.get('label'):
                                            label_to_key[item['label']] = item['key']
                walk_comps(components)
    except Exception as e:
        logger.debug(f"  查表單 schema 失敗: {e}")

    for node in graph['nodes']:
        node_id = node.get('id', '?')
        node_type = node.get('type', '?')
        config = node.get('config', {})

        if not config:
            continue

        new_config, changes = migrate_config(config, label_to_key)

        if changes:
            total_changes += len(changes)
            graph_modified = True

            for old, new in changes:
                action = '[DRY-RUN]' if dry_run else '[MIGRATE]'
                logger.info(f"  {action} {node_id} ({node_type}): {old} → {new}")

            if not dry_run:
                node['config'] = new_config

    # 也處理 graph_snapshot（存在於 workflow instances，但這裡只處理 templates）

    if graph_modified and not dry_run:
        from sqlalchemy.orm.attributes import flag_modified
        template.graph = graph
        flag_modified(template, 'graph')

    return total_changes


def main():
    parser = argparse.ArgumentParser(description='變數系統 v2 語法遷移')
    parser.add_argument('--dry-run', action='store_true', default=False,
                        help='預覽模式，不修改資料')
    parser.add_argument('--include-snapshots', action='store_true', default=False,
                        help='同時遷移運行中實例的 graph_snapshot（預設不處理）')
    args = parser.parse_args()

    from app import create_app, db
    app = create_app()

    with app.app_context():
        from modules.form_workflow.models import FwWorkflowTemplate

        templates = FwWorkflowTemplate.query.filter_by(is_deleted=False).all()
        logger.info(f"掃描 {len(templates)} 個 workflow templates...")

        grand_total = 0

        for t in templates:
            logger.info(f"\n[{t.name}] (version={t.version}, code={t.secure_code})")
            count = process_template(t, dry_run=args.dry_run)
            if count == 0:
                logger.info("  無變更")
            grand_total += count

        if args.include_snapshots:
            from modules.form_workflow.models import FwWorkflowInstance
            instances = FwWorkflowInstance.query.filter(
                FwWorkflowInstance.status.in_(['RUNNING', 'WAITING']),
                FwWorkflowInstance.graph_snapshot.isnot(None)
            ).all()
            logger.info(f"\n掃描 {len(instances)} 個運行中實例的 graph_snapshot...")

            for inst in instances:
                logger.info(f"\n[Instance {inst.secure_code}] status={inst.status}")
                # 創建 fake template 物件來複用 process_template
                class FakeTemplate:
                    def __init__(self, graph, sc):
                        self.graph = graph
                        self.secure_code = sc
                        self.name = f"instance-{sc}"
                        self.version = "snapshot"
                fake = FakeTemplate(inst.graph_snapshot, inst.workflow_template_secure_code)
                count = process_template(fake, dry_run=args.dry_run)
                if count > 0 and not args.dry_run:
                    from sqlalchemy.orm.attributes import flag_modified
                    inst.graph_snapshot = fake.graph
                    flag_modified(inst, 'graph_snapshot')
                grand_total += count

        logger.info(f"\n{'='*60}")
        logger.info(f"總計變更: {grand_total} 處")

        if grand_total > 0 and not args.dry_run:
            db.session.commit()
            logger.info("已提交到資料庫")
        elif args.dry_run and grand_total > 0:
            logger.info("(dry-run 模式，未修改資料庫)")


if __name__ == '__main__':
    main()
