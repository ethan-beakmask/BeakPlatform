# FILE-01: 檔案上傳/下載統一規範

**所有檔案操作必須透過統一元件，禁止自行實作上傳/下載邏輯。**

## 架構總覽

```
前端 BkFileAttachment → POST /api/files/upload → file_service.upload_file()
                                                      ├── local (org_logo, wf_background)
                                                      └── encrypted (form_attachment, subsystem_file, portal_file)
                                                           └── crypto/key_manager.py (AES-256-GCM)
```

## 加密機制 (內建，非外部服務)

- **位置**: `backend/app/crypto/` (engine.py + key_manager.py)
- **演算法**: AES-256-GCM
- **金鑰架構**: Master Key (env) → Org Key (DB per 企業) → File DEK (per 檔案隨機)
- **觸發時機**: `storage_type='encrypted'` 時自動加解密，程式不需手動呼叫加密函式
- **加密檔案儲存**: `ENCRYPTED_STORAGE_DIR` 環境變數指定的目錄，按企業隔離子目錄

## context_type 與 storage_type 對應

| context_type | storage_type | 加密 | 說明 |
|---|---|---|---|
| `org_logo` | `local` | 否 | 企業 Logo |
| `wf_background` | `local` | 否 | 工作流設計器底圖 |
| `form_attachment` | `encrypted` | 是 | 表單簽核附件 |
| `subsystem_file` | `encrypted` | 是 | 子系統業務附件 |
| `portal_file` | `encrypted` | 是 | NoCode portal 末端用戶檔案（PF-44） |

**新增 context_type 時**：在 `file_service.py` 的 `CONTEXT_STORAGE_MAP`、`CONTEXT_ALLOWED_EXT`、`CONTEXT_MAX_SIZE` 三個 dict 中加入對應設定。

`/api/files/upload` 只接受 `GENERIC_UPLOAD_CONTEXT_TYPES`（`form_attachment` / `subsystem_file`）。其他 context_type 必須走各自專屬端點，例如 Logo、背景圖與 portal 檔案端點，避免未知 context_type 繞過副檔名白名單或低權限帳號寫入公開檔案語境。

## 後端開發 - 上傳

```python
from app.services import file_service

record = file_service.upload_file(
    org_sc=org.secure_code,       # 企業 SC (租戶隔離)
    file=request.files['file'],   # werkzeug FileStorage
    context_type='form_attachment', # 用途類型 → 自動決定加不加密
    context_id='RECORD_SC',       # 關聯的業務記錄 SC (選填)
    uploader_sc=current_user.secure_code,
)
db.session.commit()
# record.secure_code 用於前端存取
# record.serve_url / record.download_url 用於產生連結
```

## 後端開發 - 下載/讀取

```python
record = file_service.get_file_by_sc(secure_code, org_sc=org.secure_code)
data, mime_type, original_name = file_service.serve_file(record)
# data 是明文 bytes，加密檔案已自動解密
```

## 後端開發 - 刪除

```python
file_service.delete_file(record)  # 刪除實體檔案 + 軟刪除 DB 記錄
db.session.commit()
```

## 前端開發 - BkFileAttachment 元件

```html
<script src="/static/js/bk-file-attachment.js"></script>
<div id="attachments"></div>
<script>
const att = new BkFileAttachment('#attachments', {
    contextType: 'form_attachment',
    contextId: '{{ record.secure_code }}',
    readonly: false,
    maxFiles: 10,
    onUpload: (file) => { /* 上傳完成 */ },
    onDelete: (fileSc) => { /* 刪除完成 */ },
});
att.init();
</script>
```

## 禁止事項

- **禁止** 繞過 `file_service` 直接讀寫 uploads/ 或 encrypted_storage/ 目錄
- **禁止** 在前端自行實作上傳 API 呼叫（應使用 `BkFileAttachment`）
- **禁止** 手動呼叫 `crypto/engine.py` 加解密檔案（應透過 `file_service` 自動處理）
- **禁止** 將 `ENCRYPTION_MASTER_KEY` 硬編碼或寫入版控

---

*本文件自 CLAUDE.md 抽出（2026-07-29），主檔僅留核心規則與指針。*
