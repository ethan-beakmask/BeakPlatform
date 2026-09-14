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
from .schema import schema_bp

additional_blueprints = [schema_bp]
