#!/usr/bin/env python3
"""節點端到端驗收工具（2026-08-30 PF-181/182 期間寫的，NT-xx 補測可直接沿用）

不必經表單提交：直接建 FwWorkflowTemplate + FwWorkflowInstance + 一筆 Start 的
PENDING queue 記錄，executor 會自己撿起來跑完整流程（Start -> 受測節點 -> End）。

用法（一律先 `set -a && source .env && set +a`，再用 venv/bin/python 跑）:

  # 線性圖 Start -> <節點> -> End(cancel)
  PROBE_NODE_TYPE=OsExecutor venv/bin/python dev-notes/tools/node_probe.py \
      create ok '{"command":"/bin/echo hi","result_var":"r","timeout_seconds":30}'
      -> 印出 workflow instance secure_code

  # 並行圖 Start ->〔受測節點〕/〔End(cancel)〕，用來驗 cancel 協同
  ... create cancel-test '<config json>' parallel

  # 建立時順便寫流程變數（驗變數插值用）
  ... create quote '<config json>' 'var:payload=; touch /tmp/PWNED ; #'

  wait  <instance_sc> [timeout_sec]   等到流程進終態
  show  <instance_sc>                 印出 queue／流程變數／log 三者

環境變數 PROBE_NODE_TYPE 決定受測節點型別（預設 OsExecutor）。
ORG 常數是本機 beluga 的 secure_code，換環境要改。

**本檔刻意放在 dev-notes/（不推 GitHub）**：它寫死了本機的企業 secure_code。
"""
import json
import os
import secrets
import sys
import time
from datetime import datetime

sys.path.insert(0, '/opt/BeakPlatform-dev')
sys.path.insert(0, '/opt/BeakPlatform-dev/backend')

ORG = '_9c8TewkRkCBEf3XsUdqeF'   # beluga


def sc():
    return secrets.token_urlsafe(16)


def build_graph_parallel(os_config):
    """Start 同時接 OsExecutor（長命令）與 End(cancel)，用來驗 cancel 協同。"""
    return {
        'nodes': [
            {'id': 'start', 'type': 'Start', 'label': '開始', 'config': {},
             'position': {'x': 100, 'y': 100}},
            {'id': 'os1', 'type': 'OsExecutor', 'label': 'OS 命令', 'config': os_config,
             'position': {'x': 300, 'y': 60}},
            {'id': 'end1', 'type': 'End', 'label': '結束',
             'config': {'finish_mode': 'cancel', 'wait_seconds': 8},
             'position': {'x': 300, 'y': 200}},
        ],
        'edges': [
            {'id': 'e1', 'source': 'start', 'target': 'os1', 'label': ''},
            {'id': 'e2', 'source': 'start', 'target': 'end1', 'label': ''},
        ],
    }


def build_graph(os_config):
    return {
        'nodes': [
            {'id': 'start', 'type': 'Start', 'label': '開始', 'config': {},
             'position': {'x': 100, 'y': 100}},
            {'id': 'os1', 'type': os.environ.get('PROBE_NODE_TYPE', 'OsExecutor'),
             'label': '節點', 'config': os_config,
             'position': {'x': 300, 'y': 100}},
            {'id': 'end1', 'type': 'End', 'label': '結束',
             'config': {'finish_mode': 'cancel'},
             'position': {'x': 500, 'y': 100}},
        ],
        'edges': [
            {'id': 'e1', 'source': 'start', 'target': 'os1', 'label': ''},
            {'id': 'e2', 'source': 'os1', 'target': 'end1', 'label': ''},
        ],
    }


def main():
    from app import create_app, db
    app = create_app()
    with app.app_context():
        from modules.form_workflow.models import (
            FwWorkflowTemplate, FwWorkflowInstance, FwNodeExecutionQueue,
            FwWorkflowVariable, FwNodeExecutionLog)

        cmd = sys.argv[1]

        if cmd == 'create':
            label = sys.argv[2]
            os_config = json.loads(sys.argv[3])
            parallel = len(sys.argv) > 4 and sys.argv[4] == 'parallel'
            graph = build_graph_parallel(os_config) if parallel else build_graph(os_config)
            tpl_sc = sc()
            tpl = FwWorkflowTemplate(
                secure_code=tpl_sc, org_secure_code=ORG,
                code=f'OSPROBE_{datetime.utcnow().strftime("%H%M%S")}_{secrets.token_hex(2)}',
                name=f'OsExecutor 驗收 {label}', graph=graph,
                is_published=False, is_active=True, is_protected=False,
                permission_type='ALL', is_subprocess=False)
            db.session.add(tpl)
            db.session.flush()

            inst_sc = sc()
            inst = FwWorkflowInstance(
                secure_code=inst_sc, org_secure_code=ORG,
                workflow_template_secure_code=tpl_sc,
                status='RUNNING',
                execution_code=f'OSPROBE-{datetime.utcnow().strftime("%Y%m%d%H%M%S")}',
                is_test=True, workflow_depth=0,
                graph_snapshot=graph, workflow_name=f'OsExecutor 驗收 {label}',
                started_at=datetime.utcnow(),
                root_instance_code=inst_sc)
            db.session.add(inst)
            db.session.flush()

            q = FwNodeExecutionQueue(
                secure_code=sc(), org_secure_code=ORG,
                workflow_instance_secure_code=inst_sc,
                node_id='start', node_type='Start', node_name='開始',
                node_config={}, status='PENDING', retry_count=0, max_retries=3,
                scheduled_at=datetime.utcnow(), priority=5)
            db.session.add(q)
            db.session.commit()

            # 額外的流程變數：參數形如 var:<name>=<value>
            for extra in sys.argv[4:]:
                if extra.startswith('var:'):
                    name, _, value = extra[4:].partition('=')
                    from modules.form_workflow.services.variable_service import VariableService
                    VariableService.set_flow_var(inst_sc, name, value, ORG, 'probe')
            db.session.commit()
            print(inst_sc)
            return

        inst_sc = sys.argv[2]

        if cmd == 'wait':
            timeout = int(sys.argv[3]) if len(sys.argv) > 3 else 90
            deadline = time.time() + timeout
            while time.time() < deadline:
                db.session.expire_all()
                inst = FwWorkflowInstance.query.filter_by(secure_code=inst_sc).first()
                if inst and inst.status in ('COMPLETED', 'CANCELLED', 'ERROR', 'FAILED'):
                    print(f'final status={inst.status} after {int(time.time() - (deadline - timeout))}s')
                    return
                time.sleep(2)
            inst = FwWorkflowInstance.query.filter_by(secure_code=inst_sc).first()
            print(f'TIMEOUT waiting; status={inst.status if inst else "?"}')
            return

        if cmd == 'show':
            inst = FwWorkflowInstance.query.filter_by(secure_code=inst_sc).first()
            print(f'== instance {inst_sc} status={inst.status} exec={inst.execution_code}')
            for q in FwNodeExecutionQueue.query.filter_by(
                    workflow_instance_secure_code=inst_sc).order_by(
                    FwNodeExecutionQueue.id).all():
                print(f'-- queue {q.node_id}/{q.node_type} status={q.status} '
                      f'retry={q.retry_count} pid={q.process_id} err={q.error_message}')
                print('   result=' + json.dumps(q.result, ensure_ascii=False)[:1200])
            print('== flow vars')
            for v in FwWorkflowVariable.query.filter_by(
                    workflow_instance_secure_code=inst_sc).order_by(
                    FwWorkflowVariable.id).all():
                print(f'   {v.var_name} = {str(v.var_value)[:200]}')
            print('== logs')
            wi_id = inst.id
            for lg in FwNodeExecutionLog.query.filter_by(
                    workflow_instance_id=wi_id).order_by(FwNodeExecutionLog.id).all():
                print(f'   [{lg.log_level}] node_type={lg.node_type} node_id={lg.node_id} '
                      f'status={lg.status} exec_id={lg.execution_id} inst_id={lg.node_instance_id}')
                print(f'      {lg.log_message}')
                if lg.log_data:
                    print('      data=' + json.dumps(lg.log_data, ensure_ascii=False)[:900])
            return


if __name__ == '__main__':
    main()
