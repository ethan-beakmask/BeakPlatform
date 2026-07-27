"""Page IR 共用入口。"""
from .renderer import PageIrRenderError, render_page_ir
from .validator import validate_page_ir

__all__ = ["PageIrRenderError", "render_page_ir", "validate_page_ir"]
