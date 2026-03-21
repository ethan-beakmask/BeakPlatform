"""
縮圖生成服務
使用 html2image 將表單 schema 渲染為縮圖
"""
import base64
import json
import os
import tempfile
import threading
from pathlib import Path

# 嘗試匯入 html2image
try:
    from html2image import Html2Image
    HTML2IMAGE_AVAILABLE = True
except ImportError:
    HTML2IMAGE_AVAILABLE = False
    print("html2image 未安裝，表單縮圖功能不可用")

# 嘗試匯入 PIL
try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("Pillow 未安裝，表單縮圖功能不可用")


def is_available():
    """檢查縮圖功能是否可用"""
    return HTML2IMAGE_AVAILABLE and PIL_AVAILABLE


def generate_form_thumbnails(schema, form_name="表單"):
    """
    從 Form.io schema 生成表單縮圖（使用 html2image 真實渲染）

    Args:
        schema: Form.io schema dict
        form_name: 表單名稱

    Returns:
        str: thumbnail_2x1 的 base64 data URI 或 None
    """
    if not is_available():
        return None

    try:
        # 取得 vendor 靜態資源路徑（平台級）
        vendor_path = os.path.abspath(os.path.join(
            os.path.dirname(__file__),
            '..', '..', '..', 'backend', 'app', 'static', 'vendor'
        ))
        js_path = os.path.abspath(os.path.join(
            os.path.dirname(__file__),
            '..', '..', '..', 'backend', 'app', 'static', 'js'
        ))

        # 建立 HTML 內容（使用本地資源）
        html_content = f'''
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <link href="file://{vendor_path}/bootstrap.min.css" rel="stylesheet">
            <link rel="stylesheet" href="file://{vendor_path}/formio.full.min.css">
            <style>
                body {{
                    margin: 20px;
                    background-color: #f8f9fa;
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
                }}
                #form-container {{
                    background-color: white;
                    padding: 30px;
                    border-radius: 8px;
                    box-shadow: 0 2px 8px rgba(0,0,0,0.1);
                }}
            </style>
        </head>
        <body>
            <div id="form-container"></div>
            <script src="file://{vendor_path}/formio.full.min.js"></script>
            <script src="file://{js_path}/formio-form-title.js"></script>
            <script>
                Formio.icons = 'fontawesome';
                const schema = {json.dumps(schema)};
                Formio.createForm(document.getElementById('form-container'), schema, {{
                    readOnly: true
                }}).then(form => {{
                    console.log('Form rendered');
                }}).catch(err => {{
                    console.error('Error:', err);
                }});
            </script>
        </body>
        </html>
        '''

        with tempfile.TemporaryDirectory() as tmpdir:
            hti = Html2Image(
                output_path=tmpdir,
                size=(800, 800),
                browser='chrome',
                browser_executable='/usr/bin/google-chrome'
            )

            screenshot_paths = hti.screenshot(
                html_str=html_content,
                save_as='screenshot.png'
            )

            if not screenshot_paths:
                raise Exception('截圖生成失敗')

            screenshot_path = Path(tmpdir) / 'screenshot.png'
            if not screenshot_path.exists():
                raise Exception(f'截圖檔案不存在: {screenshot_path}')

            # 使用 PIL 裁切空白後生成縮圖 (600x900 直式, 2:3)
            img = Image.open(screenshot_path)

            # 自動裁切周圍空白
            bg = Image.new(img.mode, img.size, (248, 249, 250))  # #f8f9fa 背景色
            diff = Image.composite(img, bg, img.convert('L').point(lambda x: 0 if x > 245 else 255))
            bbox = diff.getbbox()
            if bbox:
                # 留一點邊距
                margin = 10
                bbox = (
                    max(0, bbox[0] - margin),
                    max(0, bbox[1] - margin),
                    min(img.width, bbox[2] + margin),
                    min(img.height, bbox[3] + margin)
                )
                img = img.crop(bbox)

            img_2x1 = img.resize((600, 900), Image.Resampling.LANCZOS)
            img_2x1_path = Path(tmpdir) / 'thumbnail_2x1.png'
            img_2x1.save(img_2x1_path, 'PNG')

            with open(img_2x1_path, 'rb') as f:
                img_data = f.read()
                img_base64 = base64.b64encode(img_data).decode('utf-8')
                thumbnail_2x1 = f'data:image/png;base64,{img_base64}'

            print(f"[thumbnail] 表單 '{form_name}' 縮圖生成成功")
            return thumbnail_2x1

    except Exception as e:
        print(f"[thumbnail] 生成失敗: {e}")
        import traceback
        traceback.print_exc()
        return None


def generate_form_thumbnails_background(app, form_id, schema, form_name):
    """
    在背景執行緒中生成縮圖並更新資料庫

    Args:
        app: Flask app 實例（用於 app context）
        form_id: 表單 ID
        schema: Form.io schema
        form_name: 表單名稱
    """
    try:
        thumbnail_2x1 = generate_form_thumbnails(schema, form_name)

        if thumbnail_2x1:
            with app.app_context():
                from app import db
                from ..models import FwFormTemplate

                form = FwFormTemplate.query.get(form_id)
                if form:
                    form.thumbnail_2x1 = thumbnail_2x1
                    db.session.commit()
                    print(f"[thumbnail] 表單 {form_id} ({form_name}) 縮圖已儲存")
                else:
                    print(f"[thumbnail] 找不到表單 {form_id}")
    except Exception as e:
        print(f"[thumbnail] 背景生成錯誤: {e}")
        import traceback
        traceback.print_exc()


def generate_form_thumbnails_async(app, form_id, schema, form_name):
    """
    啟動背景執行緒生成縮圖

    Args:
        app: Flask app 實例
        form_id: 表單 ID
        schema: Form.io schema
        form_name: 表單名稱
    """
    if not is_available():
        return

    thread = threading.Thread(
        target=generate_form_thumbnails_background,
        args=(app, form_id, schema, form_name),
        daemon=True
    )
    thread.start()
    print(f"[thumbnail] 已啟動背景生成: 表單 {form_id} ({form_name})")
