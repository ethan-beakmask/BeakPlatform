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

    標準節點類型（共 19 種）：
    - Start, End, Abandon: 流程控制
    - FormAdapter: 簽核
    - Delay: 延遲
    - Branch, Converge: 分支/匯合
    - ParallelFork, ParallelJoin: 並行分支/匯合
    - Telegram, EmailAdapter: 企業級通知
    - SysTelegram, EmailRelay: 系統級通知
    - NavbarBroadcast, AlertBroadcast: 企業級廣播
    - SubFlow: 子流程
    - OpSet, OpFieldRead, OpFieldWrite: 變數操作
    """
    from .start_handler import StartHandler
    from .end_handler import EndHandler
    from .delay_handler import DelayHandler
    from .formadapter_handler import FormAdapterHandler
    from .branch_handler import BranchHandler
    from .converge_handler import ConvergeHandler
    from .parallelfork_handler import ParallelForkHandler
    from .paralleljoin_handler import ParallelJoinHandler
    from .opset_handler import OpSetHandler
    from .fieldread_handler import FieldReadHandler
    from .fieldwrite_handler import FieldWriteHandler
    from .telegram_handler import TelegramHandler
    from .email_handler import EmailHandler
    from .emailrelay_handler import EmailRelayHandler
    from .subflow_handler import SubFlowHandler
    from .abandon_handler import AbandonHandler
    from .sub_system_provision_handler import SubSystemProvisionHandler
    from .navbar_broadcast_handler import NavbarBroadcastHandler
    from .alert_broadcast_handler import AlertBroadcastHandler
    from .decision_writer_handler import DecisionWriterHandler
    from .api_key_action_handler import ApiKeyActionHandler
    from .ai_agent_handler import AiAgentHandler

    # 流程控制
    NodeHandlerFactory.register('Start', StartHandler)
    NodeHandlerFactory.register('End', EndHandler)
    NodeHandlerFactory.register('Abandon', AbandonHandler)

    # 簽核
    NodeHandlerFactory.register('FormAdapter', FormAdapterHandler)

    # 時間控制
    NodeHandlerFactory.register('Delay', DelayHandler)

    # 分支/匯合
    NodeHandlerFactory.register('Branch', BranchHandler)
    NodeHandlerFactory.register('Converge', ConvergeHandler)

    # 並行分支/匯合
    NodeHandlerFactory.register('ParallelFork', ParallelForkHandler)
    NodeHandlerFactory.register('ParallelJoin', ParallelJoinHandler)

    # 企業級通知
    NodeHandlerFactory.register('Telegram', TelegramHandler)
    NodeHandlerFactory.register('EmailAdapter', EmailHandler)

    # 系統級通知（SysTelegram 複用 TelegramHandler）
    NodeHandlerFactory.register('SysTelegram', TelegramHandler)
    NodeHandlerFactory.register('EmailRelay', EmailRelayHandler)

    # 子流程
    NodeHandlerFactory.register('SubFlow', SubFlowHandler)

    # 變數操作
    NodeHandlerFactory.register('OpSet', OpSetHandler)
    NodeHandlerFactory.register('OpFieldRead', FieldReadHandler)
    NodeHandlerFactory.register('OpFieldWrite', FieldWriteHandler)

    # 整合（系統動作）
    NodeHandlerFactory.register('SubSystemProvision', SubSystemProvisionHandler)

    # 廣播
    NodeHandlerFactory.register('NavbarBroadcast', NavbarBroadcastHandler)
    NodeHandlerFactory.register('AlertBroadcast', AlertBroadcastHandler)

    # OpenDefense
    NodeHandlerFactory.register('DecisionWriter', DecisionWriterHandler)

    # 安全（API Key 機器處置）
    NodeHandlerFactory.register('ApiKeyAction', ApiKeyActionHandler)

    # AI 分析
    NodeHandlerFactory.register('AiAgent', AiAgentHandler)


# 自動執行註冊
register_builtin_handlers()
