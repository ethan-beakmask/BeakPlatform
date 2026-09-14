"""
FormWorkflow Module - End Handler
結束節點處理器

三種結束模式（主流程與子流程都會讀，PF-200 起）：
- detach (分離執行): 直接結束流程，不處理其他未完成節點（由終態檢查擋住後續推進）
- cancel (取消/終止): 「中止」語意——結束並主動取消本層與所有下層的未完成節點，
  流程實例與表單記 CANCELLED（Abandon 已於 PF-200 併入此模式後刪除）。
  放在子流程時只收自己與後代（scope='subtree'），不影響上一層。
- strict (嚴格等待): 等待所有其他節點完成後才結束；若有節點失敗則流程標記失敗

子流程結束（workflow_instance.parent_instance_code 不為 None）：
- 喚醒父流程的 SubFlow 節點並回報結束方式（subflow_result: completed / cancelled）
- 父流程依 SubFlow 節點的 resultRouting 配置決定走哪些出邊（未配置＝所有出邊）
- 同時寫入父流程變數 ${v.<subflow_node_id>_result} / ${v.<subflow_node_id>_child}
- 喚醒失敗不再靜默吞掉：把父流程的 SubFlow 節點標 FAILED，讓卡死變成看得見的錯誤
"""
import logging
import time
from datetime import datetime
from typing import Dict, Any, Optional
from .base import BaseNodeHandler

logger = logging.getLogger(__name__)

# wait_seconds 上限保護（秒）。node_config 是自由 JSON，可被 API 直接 PUT 改，
# 沒有後端驗證時 time.sleep() 會無上限阻塞該節點的 OS 子行程。
# 300 秒與設計器面板 input[max] 一致。
MAX_WAIT_SECONDS = 300


class EndHandler(BaseNodeHandler):
    """結束節點處理器"""

    FINISH_MODE_NAMES = {
        'detach': '分離執行',
        'cancel': '取消/終止',
        'strict': '嚴格等待',
    }

    def _clamp_wait_seconds(self, raw, default) -> float:
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return default
        if value < 0:
            return 0
        if value > MAX_WAIT_SECONDS:
            self.log_warning(
                f'wait_seconds={value} 超過上限 {MAX_WAIT_SECONDS}，已夾限')
            return MAX_WAIT_SECONDS
        return value

    def handle(self) -> Dict[str, Any]:
        """
        處理結束節點

        雙路徑：
        1. 子流程 → _handle_subflow_end()（完成子流程 + 喚醒父流程）
        2. 主流程 → _handle_main_flow_end()（原有邏輯）
        """
        self.report_running()

        # 判斷是否為子流程
        from ...models import FwWorkflowInstance
        workflow_instance = FwWorkflowInstance.query.filter_by(
            secure_code=self.queue_item.workflow_instance_secure_code,
            is_deleted=False
        ).first()

        if workflow_instance and workflow_instance.parent_instance_code:
            return self._handle_subflow_end(workflow_instance)

        return self._handle_main_flow_end()

    def _handle_main_flow_end(self) -> Dict[str, Any]:
        """主流程結束處理"""
        finish_mode = self.node_config.get('finish_mode', 'detach')
        wait_seconds = self._clamp_wait_seconds(self.node_config.get('wait_seconds', 3), 3)
        mode_name = self.FINISH_MODE_NAMES.get(finish_mode, finish_mode)

        self.log_info('結束節點啟動', {
            'workflow_instance': self.queue_item.workflow_instance_secure_code,
            'node_id': self.queue_item.node_id,
            'finish_mode': finish_mode,
            'wait_seconds': wait_seconds
        })

        # 等待指定秒數（給平行分支一點收尾時間）
        if wait_seconds > 0:
            self.log_info(f'等待 {wait_seconds} 秒後執行結束模式: {mode_name}')
            time.sleep(wait_seconds)

        # 根據模式執行
        if finish_mode == 'strict':
            return self._handle_strict(mode_name)

        data = {
            'finish_mode': finish_mode,
            'completed_at': datetime.utcnow().isoformat()
        }
        if finish_mode == 'cancel':
            # PF-200：cancel＝中止。流程與表單記 CANCELLED（原 Abandon 的行為）；
            # node_runner 依 data.workflow_status 白名單採用，並取消整棵樹未完成節點。
            data['workflow_status'] = 'CANCELLED'
            self.log_info('流程中止（cancel 模式）')
            return {
                'status': 'complete_workflow',
                'message': '流程已中止',
                'data': data
            }

        self.log_info(f'流程結束（{mode_name}模式）')
        return {
            'status': 'complete_workflow',
            'message': f'流程已結束（{mode_name}）',
            'data': data
        }

    def _handle_subflow_end(self, workflow_instance) -> Dict[str, Any]:
        """
        子流程結束處理（PF-200 起讀 finish_mode）

        1. strict：等本子流程實例的其他節點完成（失敗則子流程標 FAILED、父節點標 FAILED）
        2. 找到父流程的 SubFlow 節點 queue item，標 SUCCESS 並附 subflow_result
        3. 寫入父流程變數 <node>_result / <node>_child，再依 resultRouting 推進父流程
        4. cancel：回傳 workflow_status='CANCELLED'，node_runner 以 scope='subtree'
           取消自己與所有後代（上一層不受影響）
        """
        parent_code = workflow_instance.parent_instance_code
        child_code = workflow_instance.secure_code
        finish_mode = self.node_config.get('finish_mode', 'detach')

        self.log_info('子流程結束節點啟動', {
            'child_instance': child_code,
            'parent_instance': parent_code,
            'depth': workflow_instance.workflow_depth,
            'finish_mode': finish_mode
        })

        # 等待（給子流程其他分支收尾時間）
        wait_seconds = self._clamp_wait_seconds(self.node_config.get('wait_seconds', 1), 1)
        if wait_seconds > 0:
            time.sleep(wait_seconds)

        # strict：等其他節點完成；有失敗 → 子流程 FAILED、父 SubFlow 節點 FAILED
        if finish_mode == 'strict':
            unfinished = self._unfinished_nodes()
            if unfinished:
                node_info = [f"{n.node_name or n.node_id}({n.status})" for n in unfinished]
                self.log_info(f'嚴格等待：仍有 {len(unfinished)} 個未完成節點', {
                    'unfinished_nodes': node_info
                })
                return {
                    'status': 'waiting',
                    'message': f'等待 {len(unfinished)} 個節點完成',
                    'data': {
                        'finish_mode': 'strict',
                        'unfinished_count': len(unfinished),
                        'retry_after_seconds': 30
                    }
                }
            failed = self._failed_nodes()
            if failed:
                self.log_warning(f'嚴格等待：{len(failed)} 個節點失敗，子流程標記失敗')
                self._fail_parent_subflow_node(
                    parent_code, child_code,
                    f'子流程嚴格等待發現 {len(failed)} 個節點失敗',
                    parent_node_id=self._find_parent_node_id(child_code))
                return {
                    'status': 'complete_workflow',
                    'message': f'子流程結束（嚴格等待，{len(failed)} 個節點失敗）',
                    'data': {
                        'finish_mode': 'strict',
                        'workflow_status': 'FAILED',
                        'parent_instance_code': parent_code,
                        'completed_at': datetime.utcnow().isoformat()
                    }
                }

        subflow_result = 'cancelled' if finish_mode == 'cancel' else 'completed'

        try:
            # 找到父流程中的 SubFlow 節點 ID
            parent_node_id = self._find_parent_node_id(child_code)
            if not parent_node_id:
                # 沒有父 queue item 可標——改用 parent_instance_code 把上一層所有
                # 等待中的 SubFlow 節點標 FAILED。可能誤傷上一層其他正常等待中的
                # SubFlow 節點，但「誤標 FAILED（看得見、查得到）」遠優於
                # 「永久卡在 WAITING（不報錯、無回收路徑）」，且走到這條路徑本身
                # 就代表資料已經不一致。刻意的取捨，不是 bug。
                self.log_error('找不到父流程 SubFlow 節點 ID，'
                               '將上一層等待中的 SubFlow 節點標記為失敗以避免永久卡死')
                self._fail_parent_subflow_node(
                    parent_code, child_code,
                    f'子流程 {child_code} 結束時找不到對應的父節點（START queue item 缺 parent_node_id）')
                workflow_instance.error_message = '結束時找不到父流程 SubFlow 節點 ID'
                return self._subflow_complete_result(parent_code, finish_mode, subflow_result)

            # 更新父流程 SubFlow 節點為 SUCCESS（含 subflow_result）
            parent_queue_item = self._complete_parent_subflow_node(
                parent_code, parent_node_id, child_code, subflow_result)

            # 寫入父流程變數（在推進之前；上一層不在 subtree 內，不會被取消）
            self._write_parent_vars(parent_code, parent_node_id, child_code, subflow_result)

            # 依 resultRouting 推進父流程
            self._trigger_parent_next_nodes(
                parent_code, parent_node_id, parent_queue_item, subflow_result)

            self.log_info('子流程結束，已喚醒父流程', {
                'parent_node_id': parent_node_id,
                'parent_instance': parent_code,
                'subflow_result': subflow_result
            })

        except Exception as e:
            logger.error(f'子流程結束喚醒父流程失敗: {e}', exc_info=True)
            self.log_error(f'喚醒父流程失敗: {str(e)}')
            # 不靜默吞掉：把父節點標 FAILED，避免上一層永久卡在 WAITING
            try:
                self._fail_parent_subflow_node(
                    parent_code, child_code, f'子流程喚醒父流程失敗: {str(e)}')
            except Exception as e2:
                logger.error(f'標記父流程 SubFlow 節點失敗也失敗了: {e2}', exc_info=True)

        return self._subflow_complete_result(parent_code, finish_mode, subflow_result)

    def _unfinished_nodes(self):
        from ...models import FwNodeExecutionQueue
        return FwNodeExecutionQueue.query.filter(
            FwNodeExecutionQueue.workflow_instance_secure_code ==
            self.queue_item.workflow_instance_secure_code,
            FwNodeExecutionQueue.id != self.queue_item.id,
            FwNodeExecutionQueue.status.in_(['PENDING', 'RUNNING', 'WAITING'])
        ).all()

    def _failed_nodes(self):
        from ...models import FwNodeExecutionQueue
        return FwNodeExecutionQueue.query.filter(
            FwNodeExecutionQueue.workflow_instance_secure_code ==
            self.queue_item.workflow_instance_secure_code,
            FwNodeExecutionQueue.id != self.queue_item.id,
            FwNodeExecutionQueue.status == 'FAILED'
        ).all()

    def _find_parent_node_id(self, child_instance_code: str) -> Optional[str]:
        """
        從子流程的 START queue item 取得原始 parent_node_id

        原理：SubFlowHandler 建立子流程 START 節點時會設定 parent_node_id，
        而後續由 advance_workflow() 建立的節點不會攜帶此欄位。
        所以需要回查 START 節點的 queue item。
        """
        from sqlalchemy import func
        from ...models import FwNodeExecutionQueue

        start_item = FwNodeExecutionQueue.query.filter(
            FwNodeExecutionQueue.workflow_instance_secure_code == child_instance_code,
            func.lower(FwNodeExecutionQueue.node_type) == 'start',
            FwNodeExecutionQueue.parent_node_id.isnot(None)
        ).first()

        return start_item.parent_node_id if start_item else None

    def _complete_parent_subflow_node(
        self,
        parent_instance_code: str,
        parent_node_id: str,
        child_instance_code: str,
        subflow_result: str
    ):
        """更新父流程中 SubFlow queue item 為 SUCCESS，回傳該 queue item（供路由讀 config）"""
        from app import db
        from ...models import FwNodeExecutionQueue

        parent_queue_item = FwNodeExecutionQueue.query.filter(
            FwNodeExecutionQueue.workflow_instance_secure_code == parent_instance_code,
            FwNodeExecutionQueue.node_id == parent_node_id,
            FwNodeExecutionQueue.status == 'WAITING'
        ).first()

        if parent_queue_item:
            parent_queue_item.success({
                'status': 'success',
                'message': '子流程已中止' if subflow_result == 'cancelled' else '子流程已完成',
                'data': {
                    'child_instance_code': child_instance_code,
                    'subflow_result': subflow_result,
                    'completed_at': datetime.utcnow().isoformat()
                }
            })
            db.session.commit()
            self.log_info(f'父流程 SubFlow 節點已更新為 SUCCESS: {parent_node_id} '
                          f'(subflow_result={subflow_result})')
        else:
            self.log_warning(f'找不到父流程 WAITING 狀態的 SubFlow 節點: {parent_node_id}')

        return parent_queue_item

    def _fail_parent_subflow_node(self, parent_instance_code: str,
                                  child_instance_code: str, reason: str,
                                  parent_node_id: str = None):
        """
        把父流程等待中的 SubFlow 節點標成 FAILED（喚醒失敗的補救，PF-200 改動 5）

        parent_node_id 為 None 時比對所有 WAITING 的 SubFlow 型節點。
        node_type 用 lower() 比對——設計器寫進 graph 的是 'Subflow'（小寫 f），
        queue item 逐字複製，精確比對 'SubFlow' 會 0 筆命中而靜默失效。
        """
        from sqlalchemy import func
        from app import db
        from ...models import FwNodeExecutionQueue

        query = FwNodeExecutionQueue.query.filter(
            FwNodeExecutionQueue.workflow_instance_secure_code == parent_instance_code,
            FwNodeExecutionQueue.status == 'WAITING',
            func.lower(FwNodeExecutionQueue.node_type) == 'subflow'
        )
        if parent_node_id:
            query = query.filter(FwNodeExecutionQueue.node_id == parent_node_id)

        items = query.all()
        for item in items:
            # 不用 item.fail()——它會重試 3 次（狀態回 PENDING），executor 撿起來
            # 會重新執行 SubFlow 節點、再開一個全新的子流程。這裡是終局失敗，直接標。
            item.status = 'FAILED'
            item.error_message = f'{reason} (child={child_instance_code})'
            item.completed_at = datetime.utcnow()
        if items:
            db.session.commit()
            self.log_info(f'已將父流程 {len(items)} 個等待中的 SubFlow 節點標記為 FAILED')
        else:
            self.log_warning('父流程沒有等待中的 SubFlow 節點可標記')

    def _write_parent_vars(self, parent_instance_code: str, parent_node_id: str,
                           child_instance_code: str, subflow_result: str):
        """寫入父流程變數，讓上一層的 Branch / 訊息模板引用得到"""
        try:
            from ..variable_service import VariableService
            org_code = self.queue_item.org_secure_code
            VariableService.set_flow_var(
                parent_instance_code, f'{parent_node_id}_result', subflow_result,
                org_code=org_code, source_node_id=self.queue_item.node_id)
            VariableService.set_flow_var(
                parent_instance_code, f'{parent_node_id}_child', child_instance_code,
                org_code=org_code, source_node_id=self.queue_item.node_id)
        except Exception as e:
            # 變數只是輔助管道（主要機制是出邊路由），失敗不阻斷喚醒
            self.log_warning(f'寫入父流程變數失敗（不影響推進）: {e}')

    def _trigger_parent_next_nodes(self, parent_instance_code: str, parent_node_id: str,
                                   parent_queue_item=None, subflow_result: str = 'completed'):
        """
        推進父流程。

        SubFlow 節點可配置 resultRouting（{'completed': [edge...], 'cancelled': [edge...]}），
        依子流程結束方式走指定出邊；未配置（或該結果無對應）＝走所有出邊（既有行為）。
        """
        from ..workflow_engine import WorkflowEngine

        routing = {}
        if parent_queue_item and isinstance(parent_queue_item.node_config, dict):
            routing = parent_queue_item.node_config.get('resultRouting') or {}
        edges = routing.get(subflow_result) if isinstance(routing, dict) else None

        new_items = []
        if edges and isinstance(edges, list):
            for edge_id in edges:
                new_items.extend(WorkflowEngine.advance_workflow(
                    parent_instance_code, parent_node_id, edge_id))
            self.log_info(f'父流程依 resultRouting({subflow_result}) 推進 {len(edges)} 條出邊')
        else:
            new_items = WorkflowEngine.advance_workflow(
                parent_instance_code, parent_node_id)

        if new_items:
            node_names = [item.node_name or item.node_id for item in new_items]
            self.log_info(f'父流程已推進，新節點: {node_names}')
        else:
            self.log_info('父流程推進完成（無新節點，可能已到 End）')

    def _subflow_complete_result(self, parent_code: str, finish_mode: str,
                                 subflow_result: str) -> Dict[str, Any]:
        """子流程完成的返回結果"""
        if finish_mode == 'cancel':
            # node_runner 對 cancel 且有 parent 的 instance 用 scope='subtree'
            # 取消自己與所有後代；workflow_status 讓子流程實例記 CANCELLED（PF-203）
            return {
                'status': 'complete_workflow',
                'message': '子流程已中止',
                'data': {
                    'finish_mode': 'cancel',
                    'workflow_status': 'CANCELLED',
                    'subflow_result': subflow_result,
                    'parent_instance_code': parent_code,
                    'completed_at': datetime.utcnow().isoformat()
                }
            }
        return {
            'status': 'complete_workflow',
            'message': '子流程已結束',
            'data': {
                'finish_mode': 'subflow_end',
                'subflow_result': subflow_result,
                'parent_instance_code': parent_code,
                'completed_at': datetime.utcnow().isoformat()
            }
        }

    def _handle_strict(self, mode_name: str) -> Dict[str, Any]:
        """
        嚴格等待模式（主流程）：等待所有其他節點完成後才結束

        - 仍有 PENDING/RUNNING/WAITING 節點 → 返回 waiting，30 秒後重試
        - 有 FAILED 節點 → 結束流程並標記失敗
        - 全部完成 → 正常結束流程
        """
        unfinished = self._unfinished_nodes()
        if unfinished:
            node_info = [f"{n.node_name or n.node_id}({n.status})" for n in unfinished]
            self.log_info(f'嚴格等待：仍有 {len(unfinished)} 個未完成節點', {
                'unfinished_nodes': node_info
            })
            return {
                'status': 'waiting',
                'message': f'等待 {len(unfinished)} 個節點完成',
                'data': {
                    'finish_mode': 'strict',
                    'unfinished_count': len(unfinished),
                    'retry_after_seconds': 30
                }
            }

        failed = self._failed_nodes()
        if failed:
            node_info = [n.node_name or n.node_id for n in failed]
            self.log_warning(f'嚴格等待：{len(failed)} 個節點失敗', {
                'failed_nodes': node_info
            })
            return {
                'status': 'complete_workflow',
                'message': f'流程結束（{mode_name}，{len(failed)} 個節點失敗）',
                'data': {
                    'finish_mode': 'strict',
                    'has_failures': True,
                    'failed_count': len(failed),
                    'completed_at': datetime.utcnow().isoformat()
                }
            }

        # 所有節點都已完成
        self.log_info('嚴格等待：所有節點已完成，結束流程')
        return {
            'status': 'complete_workflow',
            'message': f'流程已結束（{mode_name}，所有節點完成）',
            'data': {
                'finish_mode': 'strict',
                'has_failures': False,
                'completed_at': datetime.utcnow().isoformat()
            }
        }
