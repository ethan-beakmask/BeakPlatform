#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
出廠表單／流程的縮圖包（thumbnail pack）。

清單頁（表單設計器列表、流程設計器列表）的縮圖本來只在使用者進設計器按「儲存」時產生：
表單由伺服器端 html2image 截圖、流程由瀏覽器端 cytoscape 匯出 PNG。全新安裝的
node展覽館與出廠申請單（API Key 申請單、代理指定申請單）從來沒被人儲存過，
清單頁就只有灰色占位圖示。

這個模組把事先畫好的縮圖當成安裝資料的一部分：

    scripts/examples/thumbnails/forms/<FORM_CODE>.png        600x900（2:3 直式）
    scripts/examples/thumbnails/workflows/<WORKFLOW_CODE>.png 600x400（3:2 橫式）

- 檔名＝模板 `code`（同一企業內表單與流程的 code 各自唯一，分兩個目錄存放）。
- `apply_thumbnail_pack()` 依 code 把 PNG 轉成 data URI 寫進 `thumbnail_2x1`，
  不 commit，由呼叫端決定交易邊界（與其他 seed 函式一致）。
- 縮圖檔由 `scripts/examples/build_showcase_thumbnails.py` 從開發機產生；示範流程或
  表單改版後要重跑它，否則清單頁看到的是舊圖（不會報錯）。
"""
from __future__ import annotations

import base64
from pathlib import Path

PACK_DIR = Path(__file__).resolve().parent / 'thumbnails'
KIND_DIRS = {
    'form': 'forms',
    'workflow': 'workflows',
}


def pack_file(kind: str, code: str) -> Path:
    """回傳某個模板縮圖在縮圖包裡的路徑（不保證存在）。"""
    if kind not in KIND_DIRS:
        raise ValueError(f'unknown thumbnail kind: {kind}')
    if not code or '/' in code or code.startswith('.'):
        raise ValueError(f'invalid template code: {code!r}')
    return PACK_DIR / KIND_DIRS[kind] / f'{code}.png'


def list_pack_codes(kind: str) -> list[str]:
    """列出縮圖包內某一類已有縮圖的 code。"""
    directory = PACK_DIR / KIND_DIRS[kind]
    if not directory.is_dir():
        return []
    return sorted(path.stem for path in directory.glob('*.png'))


def load_data_uri(kind: str, code: str) -> str | None:
    """讀取縮圖包檔案並轉成 `thumbnail_2x1` 用的 data URI；沒有檔案回 None。"""
    try:
        path = pack_file(kind, code)
    except ValueError:
        return None
    if not path.is_file():
        return None
    data = path.read_bytes()
    if not data:
        return None
    return 'data:image/png;base64,' + base64.b64encode(data).decode('ascii')


def save_pack_file(kind: str, code: str, data_uri: str) -> Path:
    """把 data URI 形式的縮圖寫進縮圖包（產生器用）。"""
    if not data_uri or not data_uri.startswith('data:image/png;base64,'):
        raise ValueError('thumbnail must be a PNG data URI')
    path = pack_file(kind, code)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(base64.b64decode(data_uri.split(',', 1)[1]))
    return path


def apply_thumbnail_pack(org_secure_code: str, *, form_codes=None, workflow_codes=None,
                         overwrite: bool = True) -> dict:
    """
    把縮圖包套到某企業的表單／流程模板上。

    form_codes / workflow_codes 為 None 表示「縮圖包裡有的全部套」；給了清單就只套
    清單內的 code（清單內沒有縮圖檔的列進 `missing`）。overwrite=False 時只補空的。
    不 commit。
    """
    from modules.form_workflow.models import FwFormTemplate, FwWorkflowTemplate

    summary = {'forms': 0, 'workflows': 0, 'kept': 0, 'missing': [], 'absent': []}
    plan = (
        ('form', FwFormTemplate, form_codes),
        ('workflow', FwWorkflowTemplate, workflow_codes),
    )
    for kind, model, codes in plan:
        wanted = list_pack_codes(kind) if codes is None else sorted({c for c in codes if c})
        for code in wanted:
            data_uri = load_data_uri(kind, code)
            if not data_uri:
                summary['missing'].append(f'{kind}:{code}')
                continue
            template = model.query.filter_by(
                org_secure_code=org_secure_code, code=code, is_deleted=False,
            ).first()
            if not template:
                summary['absent'].append(f'{kind}:{code}')
                continue
            if template.thumbnail_2x1 and not overwrite:
                summary['kept'] += 1
                continue
            template.thumbnail_2x1 = data_uri
            summary['forms' if kind == 'form' else 'workflows'] += 1
    return summary
