/**
 * form-designer-main.js -- 表單設計器主檔索引
 * 原始 2006 行已拆分為 7 個子模組
 *
 * 子模組載入順序 (HTML 中須依序載入):
 *   form-designer-toast.js      -- Toast 通知系統
 *   form-designer-theme.js      -- 風格主題管理
 *   form-designer-background.js -- BackgroundManager 底圖管理
 *   form-designer-preview.js    -- 預覽 + 列印預覽
 *   form-designer-save.js       -- CJK 處理、儲存/儲存關閉/新版/放棄
 *   form-designer-template.js   -- TemplateManager 範本管理
 *   form-designer-init.js       -- Builder 初始化、寬度、Schema、分類載入
 *
 * 依賴: Formio (由 HTML 先行載入), AuthModule
 */

// 第一時間覆寫 CDN — 封閉網路環境，指向本地 vendor
// 必須用 setBaseUrl() 才會觸發 updateUrls() 重新計算所有路徑
if (Formio.cdn && typeof Formio.cdn.setBaseUrl === 'function') {
    Formio.cdn.setBaseUrl('/static/vendor');
    console.log('Formio CDN 已覆寫，ACE 路徑:', Formio.cdn.ace);
}
Formio.ace = { basePath: '/static/vendor/ace' };

// v5 預設改用 Bootstrap Icons，強制使用 Font Awesome
Formio.icons = 'fontawesome';

console.log('Form.io 版本:', Formio.version || '未知');


// ==================== 全域共享狀態 ====================
let formBuilder;
let hasUnsavedChanges = false;
let currentFormId = null;  // 目前編輯的表單 ID
let currentFormWidth = null;  // 目前表單寬度（null 表示全寬）
let currentFormTheme = 'default';  // 目前表單風格主題
let hasEverSaved = false;  // 追蹤是否曾在設計器儲存過
