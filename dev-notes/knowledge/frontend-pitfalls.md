# 前端開發陷阱與解決方案

## 1. 表單安全 Fallback

### 問題
只依賴 JavaScript (`@submit.prevent`) 處理表單，當 JS 失敗時會用 GET 方式提交，導致敏感資料出現在 URL。

### 解決方案
**永遠在 HTML 層面設定安全 fallback:**
```html
<form method="POST" action="/auth/login" @submit.prevent="submit">
    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
    <!-- ... -->
</form>
```

### 檢查清單
- [ ] 所有表單都有 `method="POST"`
- [ ] 敏感表單都有 CSRF token
- [ ] 後端同時支援 JSON 和表單提交

---

## 2. Tailwind CSS CDN 限制

### 問題
Tailwind CDN (Play CDN) 版本不支援:
- `@apply` 語法
- 自訂 plugins
- 部分進階功能

### 解決方案
1. **開發階段**: 使用純 CSS inline styles 或自訂 CSS classes
2. **生產環境**: 使用完整 Tailwind 建置流程

### 範例
```css
/* 不要用 @apply */
.btn-primary {
    @apply bg-blue-500 text-white; /* CDN 不支援 */
}

/* 改用純 CSS */
.btn-primary {
    background-color: #3B82F6;
    color: white;
}
```

---

## 3. SVG 尺寸控制

### 問題
SVG 預設會擴展到容器大小，若 CSS 未正確載入，SVG 可能佔滿整個視窗。

### 解決方案
1. **最佳**: 避免使用 SVG 裝飾，用純文字符號替代
2. **次選**: 使用 inline style 設定尺寸
3. **備用**: CSS fallback 限制最大尺寸

```html
<!-- 最佳: 純文字 -->
<a href="...">← 返回</a>

<!-- 次選: inline style -->
<svg style="width:24px;height:24px;">...</svg>

<!-- 備用: CSS fallback -->
<style>
svg { max-width: 24px; max-height: 24px; }
</style>
```

---

## 4. Jinja2 模板繼承陷阱

### 問題
使用 `{% block body %}` 替換整個 body 時，會丟失 base.html 中 body 結尾的 scripts。

### 解決方案
1. **方法一**: 內容頁面用 `{% block content %}`，不要替換整個 body
2. **方法二**: 特殊頁面（如登入）使用獨立完整 HTML，不繼承 base

### 模板結構
```
base.html:
├── <head>
├── <body>
│   ├── {% block body %}
│   │   ├── navbar
│   │   ├── {% block content %}{% endblock %}
│   │   └── footer
│   └── {% endblock %}
│   ├── <script src="app.js">
│   └── {% block scripts %}{% endblock %}
└── </body>

page.html:
{% extends 'base.html' %}
{% block content %}  <-- 用這個，不要用 block body
    ...
{% endblock %}
```

---

## 5. Alpine.js 載入時序

### 問題
Alpine.js 用 `defer` 載入，若元件函數定義在 Alpine 載入前，會找不到。

### 解決方案
1. 元件函數定義在 `{% block scripts %}` 區塊內
2. 確保 scripts 區塊在 Alpine.js 載入後執行
3. 或使用 `x-init` 內聯定義

```html
<!-- 正確: 函數定義在模板底部 -->
{% block scripts %}
<script>
function myComponent() {
    return { ... }
}
</script>
{% endblock %}
```

---

## 6. Alpine.js `<template x-for>` 在 `<select>` 內的限制

### 問題
在 `<select>` 元素內使用 `<template x-for>` 渲染動態選項時，若資料是**異步載入**的，會導致 Alpine.js 的 DOM 操作失敗：

```
Uncaught TypeError: Cannot read properties of undefined (reading 'after')
```

### 原因
1. HTML 規範中 `<select>` 只允許 `<option>` 和 `<optgroup>` 作為子元素
2. 瀏覽器對 `<select>` 內部 DOM 有特殊處理
3. 當資料異步更新時，Alpine.js 的 `.after()` DOM 插入操作找不到正確節點

### 會出問題的寫法
```html
<!-- 資料異步載入時會報錯 -->
<select x-model="selected">
    <option value="">請選擇</option>
    <template x-for="item in asyncItems" :key="item.id">
        <option :value="item.id" x-text="item.name"></option>
    </template>
</select>
```

### 解決方案
使用 `x-html` 動態渲染整個 options HTML：

```html
<select x-model="selected" x-html="renderOptions()"></select>

<script>
function myComponent() {
    return {
        asyncItems: [],
        selected: '',

        renderOptions() {
            let html = '<option value="">請選擇</option>';
            for (const item of this.asyncItems) {
                html += `<option value="${item.id}">${this.escapeHtml(item.name)}</option>`;
            }
            return html;
        },

        escapeHtml(str) {
            if (!str) return '';
            return str.replace(/[&<>"']/g, m => ({
                '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
            })[m]);
        }
    };
}
</script>
```

### 注意
- **靜態陣列**（硬編碼在 JS 中）使用 `<template x-for>` 通常沒問題
- **異步資料**（API 載入）必須改用 `x-html` 方式
