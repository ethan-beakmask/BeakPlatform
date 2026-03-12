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

# 導入 field_specs API Blueprint
from .field_specs import field_specs_bp

additional_blueprints = [field_specs_bp]
