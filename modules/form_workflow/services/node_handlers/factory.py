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

    命名規範（PascalCase）：
    - Start, End: 流程控制
    - Delay: 延遲
    - Branch, Switch, Converge: 分支/匯合
    - Approve, FormAdapter: 簽核
    - OpSet: 變數設定
    - Notify, Telegram, Email: 通知
    - SubFlow, Subprocess: 子流程
    """
    from .start_handler import StartHandler
    from .end_handler import EndHandler
    from .delay_handler import DelayHandler
    from .approve_handler import ApproveHandler
    from .formadapter_handler import FormAdapterHandler
    from .branch_handler import BranchHandler
    from .converge_handler import ConvergeHandler
    from .switch_handler import SwitchHandler
    from .opset_handler import OpSetHandler
    from .fieldread_handler import FieldReadHandler
    from .fieldwrite_handler import FieldWriteHandler
    from .notify_handler import NotifyHandler
    from .telegram_handler import TelegramHandler
    from .email_handler import EmailHandler
    from .subflow_handler import SubFlowHandler

    # 流程控制
    NodeHandlerFactory.register('Start', StartHandler)
    NodeHandlerFactory.register('START', StartHandler)  # A6 兼容
    NodeHandlerFactory.register('End', EndHandler)
    NodeHandlerFactory.register('END', EndHandler)  # A6 兼容

    # 時間控制
    NodeHandlerFactory.register('Delay', DelayHandler)
    NodeHandlerFactory.register('DELAY', DelayHandler)  # A6 兼容
    NodeHandlerFactory.register('TIME', DelayHandler)   # A6 兼容

    # 簽核
    NodeHandlerFactory.register('Approve', ApproveHandler)
    NodeHandlerFactory.register('FormAdapter', FormAdapterHandler)  # 專用 FormAdapter 處理器
    NodeHandlerFactory.register('FORMADAPTER', FormAdapterHandler)  # A6 兼容

    # 分支/匯合
    NodeHandlerFactory.register('Branch', BranchHandler)
    NodeHandlerFactory.register('Switch', SwitchHandler)
    NodeHandlerFactory.register('Converge', ConvergeHandler)

    # 變數設定與欄位操作
    NodeHandlerFactory.register('OpSet', OpSetHandler)
    NodeHandlerFactory.register('OPSET', OpSetHandler)  # A6 兼容
    NodeHandlerFactory.register('FieldRead', FieldReadHandler)
    NodeHandlerFactory.register('OP_FIELDREAD', FieldReadHandler)  # A6 兼容
    NodeHandlerFactory.register('FieldWrite', FieldWriteHandler)
    NodeHandlerFactory.register('OP_FIELDWRITE', FieldWriteHandler)  # A6 兼容

    # 通知
    NodeHandlerFactory.register('Notify', NotifyHandler)
    NodeHandlerFactory.register('Telegram', TelegramHandler)
    NodeHandlerFactory.register('TELEGRAM', TelegramHandler)  # A6 兼容
    NodeHandlerFactory.register('Email', EmailHandler)
    NodeHandlerFactory.register('EMAIL', EmailHandler)  # A6 兼容
    NodeHandlerFactory.register('EMAILRELAY', EmailHandler)  # A6 兼容

    # 子流程
    NodeHandlerFactory.register('SubFlow', SubFlowHandler)
    NodeHandlerFactory.register('Subprocess', SubFlowHandler)  # 兼容舊名稱


# 自動執行註冊
register_builtin_handlers()
