# -*- coding: utf-8 -*-
"""
出廠表單／流程的縮圖來源：讀 scripts/examples/thumbnails/ 的縮圖包。

API Key 申請單、代理指定申請單在每家企業建立時種入，node展覽館在全新安裝時種入；
它們從來沒被人在設計器按過儲存，清單頁本來只有占位圖示。縮圖包與套用邏輯在
scripts/examples/thumbnail_pack.py，這裡只是給 backend/app/defaults 用的薄殼：
在 Flask 服務內 `scripts` 套件靠 module_loader 插進 sys.path 才找得到，
找不到時退回以檔案路徑載入，兩者都失敗就當沒有縮圖（不中止種入）。
"""
from __future__ import annotations

import importlib.util
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_PACK_MODULE_PATH = Path(__file__).resolve().parents[3] / 'scripts' / 'examples' / 'thumbnail_pack.py'


def _load_pack_module():
    try:
        from scripts.examples import thumbnail_pack
        return thumbnail_pack
    except ImportError:
        pass
    if not _PACK_MODULE_PATH.is_file():
        return None
    spec = importlib.util.spec_from_file_location('_bp_thumbnail_pack', _PACK_MODULE_PATH)
    if not spec or not spec.loader:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def pack_thumbnail(kind: str, code: str) -> str | None:
    """回傳縮圖包內該模板的 data URI；沒有縮圖或縮圖包不可用回 None。"""
    try:
        module = _load_pack_module()
        if module is None:
            return None
        return module.load_data_uri(kind, code)
    except Exception as exc:  # noqa: BLE001 - 縮圖只是裝飾，不能讓種入失敗
        logger.warning('thumbnail pack unavailable kind=%s code=%s err=%s', kind, code, exc)
        return None


def fill_template_thumbnails(form_tpl=None, wf_tpl=None, *, overwrite: bool = False) -> dict:
    """把縮圖包套到剛種入的表單／流程模板；預設只補空的，force 重種時 overwrite=True。"""
    applied = {'form': False, 'workflow': False}
    for kind, template in (('form', form_tpl), ('workflow', wf_tpl)):
        if template is None or not getattr(template, 'code', None):
            continue
        if template.thumbnail_2x1 and not overwrite:
            continue
        data_uri = pack_thumbnail(kind, template.code)
        if data_uri:
            template.thumbnail_2x1 = data_uri
            applied[kind] = True
    return applied
