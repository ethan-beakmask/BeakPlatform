"""Page IR 共用入口。"""
from .renderer import PageIrRenderError, render_page_ir, render_page_ir_full
from .validator import validate_page_ir

__all__ = ["PageIrRenderError", "render_page_ir", "render_page_ir_full", "validate_page_ir"]
