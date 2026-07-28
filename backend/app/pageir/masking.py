"""Page IR 欄位視覺遮罩（server 端唯一實作）。"""
from __future__ import annotations

MASK_CHAR = "*"
FULL_MASK = "********"


def mask_value(value, mask: dict | None):
    """依 mask 設定回傳遮罩後的值；mask 為 None 時原樣回傳。"""
    if mask is None:
        return value
    if value is None:
        return None

    text = str(value)
    if text == "":
        return ""

    if not isinstance(mask, dict):
        return _full_mask(text)

    mask_type = mask.get("type")
    if mask_type == "partial":
        return _partial_mask(text, mask)
    if mask_type == "email":
        return _email_mask(text)
    if mask_type == "phone":
        return _phone_mask(text)
    return _full_mask(text)


def masked_fields(specs) -> set[str]:
    """從 columns/fields 定義取出有設 mask 的欄位名集合。
    specs 是 list[dict]，每個 dict 可能有 'field' 與 'mask'。
    """
    fields = set()
    for spec in specs or []:
        if not isinstance(spec, dict):
            continue
        field = spec.get("field")
        if isinstance(field, str) and spec.get("mask") is not None:
            fields.add(field)
    return fields


def apply_row_masks(rows: list[dict], specs) -> list[dict]:
    """對 rows 逐列套用遮罩，回傳新的 list（不可原地修改輸入）。
    未在 specs 出現的 key 原樣保留（例如 _sc）。
    """
    masks = _masks_by_field(specs)
    masked_rows = []
    for row in rows or []:
        if not isinstance(row, dict):
            masked_rows.append(row)
            continue
        masked = dict(row)
        for field, mask in masks.items():
            if field in masked:
                masked[field] = mask_value(masked[field], mask)
        masked_rows.append(masked)
    return masked_rows


def apply_record_masks(record: dict | None, specs) -> dict | None:
    """detail 單筆用。record 為 None 時回 None。"""
    if record is None:
        return None
    if not isinstance(record, dict):
        return record
    masked = dict(record)
    for field, mask in _masks_by_field(specs).items():
        if field in masked:
            masked[field] = mask_value(masked[field], mask)
    return masked


def _masks_by_field(specs) -> dict[str, dict]:
    masks = {}
    for spec in specs or []:
        if not isinstance(spec, dict):
            continue
        field = spec.get("field")
        if isinstance(field, str) and spec.get("mask") is not None:
            masks[field] = spec.get("mask")
    return masks


def _full_mask(_text: str) -> str:
    return FULL_MASK


def _partial_mask(text: str, mask: dict) -> str:
    keep_head = _bounded_int(mask.get("keep_head"), 0)
    keep_tail = _bounded_int(mask.get("keep_tail"), 4)
    if len(text) <= keep_head + keep_tail:
        return FULL_MASK
    middle_len = len(text) - keep_head - keep_tail
    head = text[:keep_head] if keep_head else ""
    tail = text[-keep_tail:] if keep_tail else ""
    return f"{head}{MASK_CHAR * middle_len}{tail}"


def _email_mask(text: str) -> str:
    if "@" not in text:
        return FULL_MASK
    local, domain = text.split("@", 1)
    if len(local) < 3:
        return f"{MASK_CHAR * 3}@{domain}"
    return f"{local[0]}{MASK_CHAR * (len(local) - 2)}{local[-1]}@{domain}"


def _phone_mask(text: str) -> str:
    digit_count = sum(1 for char in text if char.isdigit())
    if digit_count < 8:
        return FULL_MASK

    seen = 0
    chars = []
    for char in text:
        if not char.isdigit():
            chars.append(char)
            continue
        seen += 1
        if seen <= 4 or seen > digit_count - 3:
            chars.append(char)
        else:
            chars.append(MASK_CHAR)
    return "".join(chars)


def _bounded_int(value, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return min(8, max(0, parsed))
