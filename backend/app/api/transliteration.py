"""
Transliteration API
亞洲語系拼音轉換 API

提供 CJK（中日韓）文字轉羅馬字/拼音的功能。
"""
from flask import Blueprint, request, jsonify

from ..security.decorators import login_required
from ..services.transliteration_service import TransliterationService

api_transliteration = Blueprint('api_transliteration', __name__)


@api_transliteration.route('/name', methods=['POST'])
@login_required
def transliterate_name():
    """
    人名拼音轉換

    POST /api/transliterate/name
    Body: {"name": "張三"}

    Returns:
        {
            "success": true,
            "data": {
                "original": "張三",
                "romanized": "Zhang San",
                "language": "zh",
                "confidence": "high"
            }
        }
    """
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'message': '請提供 JSON 資料'}), 400

    name = data.get('name', '').strip()
    if not name:
        return jsonify({'success': False, 'message': '請提供 name 參數'}), 400

    result = TransliterationService.transliterate_name(name)

    return jsonify({
        'success': True,
        'data': result
    })


@api_transliteration.route('/text', methods=['POST'])
@login_required
def transliterate_text():
    """
    一般文字拼音轉換

    POST /api/transliterate/text
    Body: {
        "text": "你好世界",
        "capitalize": true,
        "source_lang": null  // 可選，自動偵測
    }

    Returns:
        {
            "success": true,
            "data": {
                "original": "你好世界",
                "result": "Ni Hao Shi Jie",
                "language": "zh"
            }
        }
    """
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'message': '請提供 JSON 資料'}), 400

    text = data.get('text', '').strip()
    if not text:
        return jsonify({'success': False, 'message': '請提供 text 參數'}), 400

    capitalize = data.get('capitalize', True)
    source_lang = data.get('source_lang')

    result, lang = TransliterationService.transliterate(
        text,
        source_lang=source_lang,
        capitalize=capitalize
    )

    return jsonify({
        'success': True,
        'data': {
            'original': text,
            'result': result,
            'language': lang
        }
    })


@api_transliteration.route('/detect', methods=['POST'])
@login_required
def detect_language():
    """
    偵測文字語系

    POST /api/transliterate/detect
    Body: {"text": "こんにちは"}

    Returns:
        {
            "success": true,
            "data": {
                "text": "こんにちは",
                "language": "ja",
                "language_name": "日文"
            }
        }
    """
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'message': '請提供 JSON 資料'}), 400

    text = data.get('text', '').strip()
    if not text:
        return jsonify({'success': False, 'message': '請提供 text 參數'}), 400

    lang = TransliterationService.detect_language(text)

    # 語言名稱對照
    lang_names = {
        'zh': '中文',
        'ja': '日文',
        'ko': '韓文',
        'unknown': '未知',
        'mixed': '混合'
    }

    return jsonify({
        'success': True,
        'data': {
            'text': text,
            'language': lang,
            'language_name': lang_names.get(lang, '未知')
        }
    })
