"""
FormWorkflow Module - Workflow Backgrounds API
流程設計器底圖管理 API
"""
import os
import uuid
from flask import Blueprint, jsonify, request, current_app
from werkzeug.utils import secure_filename

from app.security.decorators import login_required
from app.platform.data import get_current_org
from app import db, csrf

# 建立 API Blueprint
backgrounds_bp = Blueprint(
    'form_workflow_backgrounds',
    __name__,
    url_prefix='/api/workflows/backgrounds'
)

# 允許的圖片格式
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp'}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB


def allowed_file(filename):
    """檢查檔案是否允許"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def get_upload_dir():
    """取得上傳目錄"""
    # 使用 backend/app/static/uploads/backgrounds 目錄
    upload_dir = '/opt/BeakPlatform/backend/app/static/uploads/backgrounds'
    os.makedirs(upload_dir, exist_ok=True)
    return upload_dir


@backgrounds_bp.route('', methods=['GET'])
@login_required
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
@login_required
def upload_background():
    """上傳底圖"""
    from ..models import FwWorkflowBackground

    org = get_current_org()
    if not org:
        return jsonify({'success': False, 'message': 'Organization not found'}), 400

    # 檢查是否有檔案
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': '未提供檔案'}), 400

    file = request.files['file']

    if file.filename == '':
        return jsonify({'success': False, 'message': '未選擇檔案'}), 400

    if not allowed_file(file.filename):
        return jsonify({'success': False, 'message': '不支援的檔案格式（支援: png, jpg, jpeg, gif, bmp, webp）'}), 400

    filepath = None
    try:
        # 讀取檔案內容
        file_content = file.read()
        file_size = len(file_content)

        # 檢查檔案大小
        if file_size > MAX_FILE_SIZE:
            return jsonify({'success': False, 'message': '檔案太大（最大 5MB）'}), 400

        # 生成唯一檔名
        ext = file.filename.rsplit('.', 1)[1].lower()
        unique_filename = f"{uuid.uuid4().hex}.{ext}"

        # 儲存檔案
        upload_dir = get_upload_dir()
        filepath = os.path.join(upload_dir, unique_filename)
        with open(filepath, 'wb') as f:
            f.write(file_content)

        # 取得圖片尺寸
        width, height = None, None
        try:
            from PIL import Image
            img = Image.open(filepath)
            width, height = img.size
            img.close()
        except Exception:
            pass

        # 儲存到資料庫
        background = FwWorkflowBackground(
            org_secure_code=org.secure_code,
            filename=unique_filename,
            original_filename=secure_filename(file.filename) or file.filename,
            filepath=filepath,
            filesize=file_size,
            mimetype=file.mimetype,
            width=width,
            height=height,
            description=request.form.get('description', ''),
        )

        db.session.add(background)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': '底圖上傳成功',
            'data': background.to_dict()
        }), 201

    except Exception as e:
        db.session.rollback()
        # 如果已經儲存檔案，刪除它
        if filepath and os.path.exists(filepath):
            os.remove(filepath)
        return jsonify({'success': False, 'message': f'上傳失敗: {str(e)}'}), 500


@backgrounds_bp.route('/<secure_code>', methods=['PUT'])
@csrf.exempt
@login_required
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
@login_required
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
        # 刪除檔案
        if background.filepath and os.path.exists(background.filepath):
            os.remove(background.filepath)

        # 軟刪除
        background.is_deleted = True
        db.session.commit()

        return jsonify({
            'success': True,
            'message': '底圖已刪除'
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'刪除失敗: {str(e)}'}), 500
