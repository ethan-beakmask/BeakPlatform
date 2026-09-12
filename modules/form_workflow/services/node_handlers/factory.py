"""
FormWorkflow Module - Node Handler Factory
節點處理器工廠

負責建立和註冊節點處理器。
"""
from typing import Dict, Type
from .base import BaseNodeHandler


class NodeHandlerFactory:
    """節點處理器工廠"""

    # 註冊的處理器
    _handlers: Dict[str, Type[BaseNodeHandler]] = {}

    @classmethod
    def register(cls, node_type: str, handler_class: Type[BaseNodeHandler]):
        """
        註冊節點處理器

        Args:
            node_type: 節點類型（如 'Start', 'End', 'Approve'）
            handler_class: 處理器類別
        """
        cls._handlers[node_type] = handler_class

    @classmethod
    def create(cls, queue_item) -> BaseNodeHandler:
        """
        建立節點處理器

        Args:
            queue_item: FwNodeExecutionQueue 實例

        Returns:
            BaseNodeHandler: 節點處理器實例

        Raises:
            ValueError: 找不到對應的處理器
        """
        node_type = queue_item.node_type

        # 先嘗試精確匹配
        if node_type in cls._handlers:
            handler_class = cls._handlers[node_type]
            return handler_class(queue_item)

        # 大小寫不敏感查找
        node_type_lower = node_type.lower()
        for registered_type, handler_class in cls._handlers.items():
            if registered_type.lower() == node_type_lower:
                return handler_class(queue_item)

        raise ValueError(f'找不到節點類型 {node_type} 的處理器')

    @classmethod
    def get_registered_types(cls) -> list:
        """
        取得已註冊的節點類型

        Returns:
            list: 節點類型列表
        """
        return list(cls._handlers.keys())

    @classmethod
    def is_registered(cls, node_type: str) -> bool:
        """
        檢查節點類型是否已註冊

        Args:
            node_type: 節點類型

        Returns:
            bool: 是否已註冊
        """
        if node_type in cls._handlers:
            return True

        node_type_lower = node_type.lower()
        for registered_type in cls._handlers.keys():
            if registered_type.lower() == node_type_lower:
                return True

        return False


def register_builtin_handlers():
    """
    註冊內建處理器

    節點類型名稱與 API 定義 (_get_node_definitions) 一致，不使用別名。
    Factory 已支援大小寫不敏感查找，無需重複註冊。
    """
    from .start_handler import StartHandler
    from .end_handler import EndHandler
    from .delay_handler import DelayHandler
    from .formadapter_handler import FormAdapterHandler
    from .branch_handler import BranchHandler
    from .parallelfork_handler import ParallelForkHandler
    from .paralleljoin_handler import ParallelJoinHandler
    from .opset_handler import OpSetHandler
    from .fieldread_handler import FieldReadHandler
    from .fieldwrite_handler import FieldWriteHandler
    from .telegram_handler import TelegramHandler
    from .email_handler import EmailHandler
    from .sys_emailrelay_handler import SysEmailRelayHandler
    from .subflow_handler import SubFlowHandler
    from .sub_system_provision_handler import SubSystemProvisionHandler
    from .navbar_broadcast_handler import NavbarBroadcastHandler
    from .alert_broadcast_handler import AlertBroadcastHandler
    from .decision_writer_handler import DecisionWriterHandler
    from .api_key_action_handler import ApiKeyActionHandler
    from .api_key_issue_handler import ApiKeyIssueHandler
    from .ai_agent_handler import AiAgentHandler
    from .sys_sqlexecutor_handler import SysSqlExecutorHandler
    from .os_executor_handler import OsExecutorHandler
    from .os_file_read_handler import OsFileReadHandler
    from .os_file_write_handler import OsFileWriteHandler
    from .hr_lookup_handler import HrLookupHandler
    from .op_proxy_grant_handler import OpProxyGrantHandler

    # 流程控制
    NodeHandlerFactory.register('Start', StartHandler)
    NodeHandlerFactory.register('End', EndHandler)

    # 簽核
    NodeHandlerFactory.register('FormAdapter', FormAdapterHandler)

    # 時間控制
    NodeHandlerFactory.register('Delay', DelayHandler)

    # 分支
    NodeHandlerFactory.register('Branch', BranchHandler)

    # 並行分支/匯合
    NodeHandlerFactory.register('ParallelFork', ParallelForkHandler)
    # ParallelFork 已於 2026-08-30 移出設計器工具列（無實際功能，見 CLAUDE.md），
    # 但既有發行快照仍含此節點，註冊必須保留，否則舊流程執行時會拋 ValueError
    NodeHandlerFactory.register('ParallelJoin', ParallelJoinHandler)

    # 企業級通知
    NodeHandlerFactory.register('Telegram', TelegramHandler)
    NodeHandlerFactory.register('EmailAdapter', EmailHandler)

    # 系統級通知（SysTelegram 複用 TelegramHandler）
    NodeHandlerFactory.register('SysTelegram', TelegramHandler)
    NodeHandlerFactory.register('SysEmailRelay', SysEmailRelayHandler)

    # 子流程
    NodeHandlerFactory.register('SubFlow', SubFlowHandler)

    # 變數操作
    NodeHandlerFactory.register('OpSet', OpSetHandler)
    NodeHandlerFactory.register('OpFieldRead', FieldReadHandler)
    NodeHandlerFactory.register('OpFieldWrite', FieldWriteHandler)
    NodeHandlerFactory.register('OpHrLookup', HrLookupHandler)
    NodeHandlerFactory.register('OpProxyGrant', OpProxyGrantHandler)

    # 整合（系統動作）
    NodeHandlerFactory.register('SubSystemProvision', SubSystemProvisionHandler)

    # 廣播
    NodeHandlerFactory.register('NavbarBroadcast', NavbarBroadcastHandler)
    NodeHandlerFactory.register('AlertBroadcast', AlertBroadcastHandler)

    # OpenDefense
    NodeHandlerFactory.register('DecisionWriter', DecisionWriterHandler)

    # 安全（API Key 機器處置）
    NodeHandlerFactory.register('ApiKeyAction', ApiKeyActionHandler)
    NodeHandlerFactory.register('ApiKeyIssue', ApiKeyIssueHandler)

    # AI 分析
    NodeHandlerFactory.register('AiAgent', AiAgentHandler)

    # 預存程序（白名單、唯讀）
    NodeHandlerFactory.register('SysSqlExecutor', SysSqlExecutorHandler)

    # 系統（OS 命令執行，兩道授權閘門，見 dev-notes/OS_EXECUTOR_SPEC.md）
    NodeHandlerFactory.register('OsExecutor', OsExecutorHandler)

    # 系統（唯讀檔案讀取，授權低 OsExecutor 一階，見 dev-notes/OS_EXECUTOR_SPEC.md 第六節）
    NodeHandlerFactory.register('OsFileRead', OsFileReadHandler)
    # 系統（檔案追加寫入，與 OsFileRead 分開授權，見 dev-notes/OS_FILE_WRITE_SPEC.md）
    NodeHandlerFactory.register('OsFileWrite', OsFileWriteHandler)


# 自動執行註冊
register_builtin_handlers()
