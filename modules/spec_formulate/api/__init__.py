"""
Spec Formulate Module - API Routes
規格制定模組 API
"""
from flask import Blueprint

api_bp = Blueprint(
    'spec_formulate_api',
    __name__,
    url_prefix='/api/spec-formulate'
)

# 導入 API Blueprints
from .field_specs import field_specs_bp
from .export import export_bp
from .readers import readers_bp
from .multifaceted import multifaceted_bp

additional_blueprints = [field_specs_bp, export_bp, readers_bp, multifaceted_bp]
