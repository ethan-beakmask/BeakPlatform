"""
FormWorkflow Module - Workflow Engine Tests
工作流引擎測試

使用方式：
    cd <project_root>/backend
    PYTHONPATH=<project_root>:<project_root>/backend pytest ../modules/form_workflow/tests/test_workflow_engine.py -v
"""
import pytest
import secrets
from datetime import datetime


class TestNodeHandlerFactory:
    """測試節點處理器工廠"""

    def test_all_handlers_registered(self):
        """測試所有處理器已註冊"""
        from modules.form_workflow.services.node_handlers.factory import NodeHandlerFactory

        expected_types = [
            'Start', 'End', 'Delay', 'Approve', 'FormAdapter',
            'Branch', 'Switch', 'Converge', 'OpSet',
            'Notify', 'Telegram', 'Email',
            'SubFlow', 'Subprocess'
        ]

        for node_type in expected_types:
            assert NodeHandlerFactory.is_registered(node_type), f'{node_type} 未註冊'

    def test_handler_count(self):
        """測試處理器數量"""
        from modules.form_workflow.services.node_handlers.factory import NodeHandlerFactory

        registered = NodeHandlerFactory.get_registered_types()
        assert len(registered) == 14, f'期望 14 個處理器，實際 {len(registered)}'


class TestStartHandler:
    """測試 Start 節點處理器"""

    def test_start_handler_success(self):
        """測試 Start 節點成功執行"""
        from modules.form_workflow.services.node_handlers.start_handler import StartHandler

        # 模擬 queue_item
        class MockQueueItem:
            secure_code = 'test-queue-item'
            org_secure_code = 'test-org'
            workflow_instance_secure_code = 'test-wf-instance'
            form_instance_secure_code = 'test-form-instance'
            node_id = 'node-Start-1'
            node_type = 'Start'
            node_config = {}
            status = 'PENDING'

        queue_item = MockQueueItem()
        handler = StartHandler(queue_item)

        result = handler.handle()

        assert result['status'] == 'success'
        assert 'data' in result


class TestEndHandler:
    """測試 End 節點處理器"""

    def test_end_handler_complete_workflow(self):
        """測試 End 節點觸發完成工作流"""
        from modules.form_workflow.services.node_handlers.end_handler import EndHandler

        class MockQueueItem:
            secure_code = 'test-queue-item'
            org_secure_code = 'test-org'
            workflow_instance_secure_code = 'test-wf-instance'
            form_instance_secure_code = 'test-form-instance'
            node_id = 'node-End-1'
            node_type = 'End'
            node_config = {}
            status = 'PENDING'

        queue_item = MockQueueItem()
        handler = EndHandler(queue_item)

        result = handler.handle()

        assert result['status'] == 'complete_workflow'


class TestBranchHandler:
    """測試 Branch 節點處理器"""

    def test_branch_handler_no_rules(self):
        """測試無規則時走 fallback 路徑"""
        from modules.form_workflow.services.node_handlers.branch_handler import BranchHandler

        class MockQueueItem:
            secure_code = 'test-queue-item'
            org_secure_code = 'test-org'
            workflow_instance_secure_code = 'test-wf-instance'
            form_instance_secure_code = 'test-form-instance'
            node_id = 'node-Branch-1'
            node_type = 'Branch'
            node_config = {}
            status = 'PENDING'

        queue_item = MockQueueItem()
        handler = BranchHandler(queue_item)

        result = handler.handle()

        assert result['status'] == 'success'
        assert result['data']['fallback_used'] == True
        assert result['data']['skip_advance'] == True
        assert result['data']['skip_advance_reason'] == 'branch_no_match'


class TestOpSetHandler:
    """測試 OpSet 節點處理器"""

    def test_opset_no_operations(self):
        """測試無操作時成功返回"""
        from modules.form_workflow.services.node_handlers.opset_handler import OpSetHandler

        class MockQueueItem:
            secure_code = 'test-queue-item'
            org_secure_code = 'test-org'
            workflow_instance_secure_code = 'test-wf-instance'
            form_instance_secure_code = 'test-form-instance'
            node_id = 'node-OpSet-1'
            node_type = 'OpSet'
            node_config = {}
            status = 'PENDING'

        queue_item = MockQueueItem()
        handler = OpSetHandler(queue_item)

        result = handler.handle()

        assert result['status'] == 'success'

    def test_opset_set_operation(self):
        """測試 set 操作"""
        from modules.form_workflow.services.node_handlers.opset_handler import OpSetHandler

        class MockQueueItem:
            secure_code = 'test-queue-item'
            org_secure_code = 'test-org'
            workflow_instance_secure_code = 'test-wf-instance'
            form_instance_secure_code = 'test-form-instance'
            node_id = 'node-OpSet-1'
            node_type = 'OpSet'
            node_config = {
                'operations': [
                    {'target_var': 'test_var', 'operation': 'set', 'value': 42}
                ]
            }
            status = 'PENDING'

        queue_item = MockQueueItem()
        handler = OpSetHandler(queue_item)

        result = handler.handle()

        assert result['status'] == 'success'
        assert result['data']['results']['test_var'] == 42


class TestNotifyHandler:
    """測試 Notify 節點處理器"""

    def test_notify_email(self):
        """測試 Email 通知"""
        from modules.form_workflow.services.node_handlers.notify_handler import NotifyHandler

        class MockQueueItem:
            secure_code = 'test-queue-item'
            org_secure_code = 'test-org'
            workflow_instance_secure_code = 'test-wf-instance'
            form_instance_secure_code = 'test-form-instance'
            node_id = 'node-Notify-1'
            node_type = 'Notify'
            node_config = {
                'type': 'email',
                'recipients': ['user1@example.com', 'user2@example.com'],
                'subject': '測試通知',
                'message': '這是測試訊息'
            }
            status = 'PENDING'

        queue_item = MockQueueItem()
        handler = NotifyHandler(queue_item)

        result = handler.handle()

        assert result['status'] == 'success'
        assert result['data']['type'] == 'email'
        assert result['data']['sent'] == True


class TestDelayHandler:
    """測試 Delay 節點處理器"""

    def test_delay_no_config(self):
        """測試無延遲配置時直接成功"""
        from modules.form_workflow.services.node_handlers.delay_handler import DelayHandler

        class MockQueueItem:
            secure_code = 'test-queue-item'
            org_secure_code = 'test-org'
            workflow_instance_secure_code = 'test-wf-instance'
            form_instance_secure_code = 'test-form-instance'
            node_id = 'node-Delay-1'
            node_type = 'Delay'
            node_config = {}
            status = 'PENDING'
            scheduled_at = None
            started_at = None

        queue_item = MockQueueItem()
        handler = DelayHandler(queue_item)

        result = handler.handle()

        assert result['status'] == 'success'
        assert '無延遲' in result['message']

    def test_delay_past_time(self):
        """測試延遲時間已過的情況"""
        from modules.form_workflow.services.node_handlers.delay_handler import DelayHandler
        from datetime import datetime, timedelta

        class MockQueueItem:
            secure_code = 'test-queue-item'
            org_secure_code = 'test-org'
            workflow_instance_secure_code = 'test-wf-instance'
            form_instance_secure_code = 'test-form-instance'
            node_id = 'node-Delay-1'
            node_type = 'Delay'
            node_config = {
                'delay_seconds': 10
            }
            status = 'PENDING'
            scheduled_at = None
            # 設定開始時間為 1 小時前（已過延遲）
            started_at = datetime.utcnow() - timedelta(hours=1)

        queue_item = MockQueueItem()
        handler = DelayHandler(queue_item)

        result = handler.handle()

        assert result['status'] == 'success'
        assert '已到' in result['message']


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
