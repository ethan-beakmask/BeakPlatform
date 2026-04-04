"""
FormWorkflow Module - Workflow Backgrounds API
流程設計器底圖管理 API
"""
import io
import logging

from flask import Blueprint, jsonify, request
from flask_login import current_user

from app.security.decorators import module_access_required
from app.platform.data import get_current_org
from app.services import file_service
from app import db, csrf

logger = logging.getLogger(__name__)

# 建立 API Blueprint
backgrounds_bp = Blueprint(
    'form_workflow_backgrounds',
    __name__,
    url_prefix='/api/workflows/backgrounds'
)


@backgrounds_bp.route('', methods=['GET'])
@module_access_required('form_workflow')
def list_backgrounds():
    """列出企業的所有底圖"""
    from ..models import FwWorkflowBackground

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'message': 'Organization not found'}), 400

    backgrounds = FwWorkflowBackground.query.filter_by(
        org_secure_code=org.secure_code,
        is_deleted=False
    ).order_by(FwWorkflowBackground.created_at.desc()).all()

    return jsonify({
        'success': True,
        'data': [bg.to_dict() for bg in backgrounds]
    })


@backgrounds_bp.route('/upload', methods=['POST'])
@csrf.exempt
@module_access_required('form_workflow')
def upload_background():
    """上傳底圖"""
    from ..models import FwWorkflowBackground

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'message': 'Organization not found'}), 400

    if 'file' not in request.files:
        return jsonify({'success': False, 'message': '未提供檔案'}), 400

    file = request.files['file']

    try:
        # 透過 FileService 上傳（驗證 + 存檔一次完成）
        pf_record = file_service.upload_file(
            org_sc=org.secure_code,
            file=file,
            context_type='wf_background',
            uploader_sc=getattr(current_user, 'secure_code', None),
        )

        # 取得圖片尺寸
        width, height = None, None
        try:
            from PIL import Image
            file.seek(0)
            img = Image.open(file)
            width, height = img.size
            img.close()
        except Exception:
            pass

        # 建立 FwWorkflowBackground 記錄（保留既有欄位相容性）
        background = FwWorkflowBackground(
            org_secure_code=org.secure_code,
            filename=pf_record.secure_code,
            original_filename=file.filename,
            filepath=pf_record.storage_ref,
            filesize=pf_record.file_size,
            mimetype=pf_record.mime_type,
            width=width,
            height=height,
            description=request.form.get('description', ''),
            platform_file_sc=pf_record.secure_code,
        )

        db.session.add(background)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': '底圖上傳成功',
            'data': background.to_dict()
        }), 201

    except ValueError as e:
        return jsonify({'success': False, 'message': str(e)}), 400
    except Exception as e:
        db.session.rollback()
        logger.exception("底圖上傳失敗")
        return jsonify({'success': False, 'message': f'上傳失敗: {str(e)}'}), 500


@backgrounds_bp.route('/<secure_code>', methods=['PUT'])
@csrf.exempt
@module_access_required('form_workflow')
def update_background(secure_code):
    """更新底圖描述"""
    from ..models import FwWorkflowBackground

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'message': 'Organization not found'}), 400

    background = FwWorkflowBackground.query.filter_by(
        secure_code=secure_code,
        org_secure_code=org.secure_code,
        is_deleted=False
    ).first()

    if not background:
        return jsonify({'success': False, 'message': '底圖不存在'}), 404

    try:
        data = request.get_json() or {}
        if 'description' in data:
            background.description = data['description'].strip()

        db.session.commit()

        return jsonify({
            'success': True,
            'message': '底圖描述已更新',
            'data': background.to_dict()
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'更新失敗: {str(e)}'}), 500


@backgrounds_bp.route('/<secure_code>', methods=['DELETE'])
@csrf.exempt
@module_access_required('form_workflow')
def delete_background(secure_code):
    """刪除底圖"""
    from ..models import FwWorkflowBackground

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'message': 'Organization not found'}), 400

    background = FwWorkflowBackground.query.filter_by(
        secure_code=secure_code,
        org_secure_code=org.secure_code,
        is_deleted=False
    ).first()

    if not background:
        return jsonify({'success': False, 'message': '底圖不存在'}), 404

    try:
        # 透過 FileService 刪除實體檔案
        if background.platform_file_sc:
            pf = file_service.get_file_by_sc(background.platform_file_sc,
                                              org_sc=org.secure_code)
            if pf:
                file_service.delete_file(pf)

        # 軟刪除 background 記錄
        background.is_deleted = True
        db.session.commit()

        return jsonify({
            'success': True,
            'message': '底圖已刪除'
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'刪除失敗: {str(e)}'}), 500
