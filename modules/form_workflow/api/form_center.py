"""
FormWorkflow Module - Form Center API
表單中心 API

提供一般用戶填寫表單、發起流程、查看進度等功能。

路由分散於以下子模組：
- fc_available.py  : 可用表單列表 + 權限判斷
- fc_fill.py       : 取得表單定義 + 送出表單
- fc_my_forms.py   : 我的表單列表 + 詳情
- fc_pending.py    : 待簽核任務 + 鎖定/解鎖 + 單筆簽核
- fc_batch.py      : 批次簽核
- fc_monitor.py    : 流程進度 + 執行路徑 + 執行日誌 + 表單詳情
- fc_admin.py      : 強制結束 + 刪除測試表單
- fc_utils.py      : 當前用戶 + 組織樹 + 欄位設定 + 欄位權限處理
- fc_phrases.py    : 簽核片語 CRUD
"""
from flask import Blueprint


# 建立 API Blueprint
form_center_bp = Blueprint(
    'form_workflow_form_center',
    __name__,
    url_prefix='/api/form-center'
)


# 匯入子模組以註冊路由（必須在 blueprint 定義之後）
from . import fc_available   # noqa: E402, F401
from . import fc_fill        # noqa: E402, F401
from . import fc_my_forms    # noqa: E402, F401
from . import fc_pending     # noqa: E402, F401
from . import fc_batch       # noqa: E402, F401
from . import fc_monitor     # noqa: E402, F401
from . import fc_admin       # noqa: E402, F401
from . import fc_utils       # noqa: E402, F401
from . import fc_phrases     # noqa: E402, F401
