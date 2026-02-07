"""
BeakMask Custom Exceptions
自定義例外
"""


class BeakMaskError(Exception):
    """Base exception for BeakMask"""
    pass


class ResourceNotFoundError(BeakMaskError):
    """Resource not found"""

    def __init__(self, resource_type: str, identifier: str):
        self.resource_type = resource_type
        self.identifier = identifier
        super().__init__(f"{resource_type} not found: {identifier}")


class PermissionDeniedError(BeakMaskError):
    """Permission denied"""

    def __init__(self, message: str = None, action: str = None, resource_type: str = None):
        self.action = action
        self.resource_type = resource_type
        if message:
            super().__init__(message)
        elif action and resource_type:
            super().__init__(f"Permission denied: {action} on {resource_type}")
        else:
            super().__init__("Permission denied")


class ValidationError(BeakMaskError):
    """Validation error"""

    def __init__(self, field: str, message: str):
        self.field = field
        self.message = message
        super().__init__(f"Validation error on {field}: {message}")


class TenantContextError(BeakMaskError):
    """Tenant context missing or invalid"""
    pass


class AuthenticationError(BeakMaskError):
    """Authentication failed"""
    pass


class RateLimitError(BeakMaskError):
    """Rate limit exceeded"""
    pass
