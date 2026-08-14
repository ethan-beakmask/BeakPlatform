## 前端規範（BeakPlatform，違反會導致排版錯亂或功能靜默失效）

### 平台沒有載入 Bootstrap

全域 CSS 只有 `common.css` + `base-layout.css`，提供 `.btn` / `.data-table` /
`.form-control` / `.modal-overlay` 等基礎元件，**沒有 Grid 系統**。

**禁止**使用：`row`、`col-md-*`、`container-fluid`、`card` / `card-header` / `card-body`、
`table-sm`、`table-hover`、`mb-3`、`p-0`、`d-flex` 等 Bootstrap class（寫了完全無效果，
排版會全部擠在一起）。

排版一律用 CSS Grid / Flexbox。模組 class 加模組前綴（`wks-`、`ird-`、`fw-`、`pir-`）。

### CSS 變數白名單（只能用這些，禁止自創）

```
主色    --color-primary  --color-primary-hover  --color-primary-light
語意色  --color-danger   --color-danger-hover   --color-danger-light
        --color-success  --color-success-hover  --color-success-light
        --color-warning  --color-warning-hover  --color-warning-light
        --color-info     --color-info-hover     --color-info-light
文字    --color-text  --color-text-secondary  --color-text-muted
背景    --color-bg  --color-bg-white  --color-bg-light  --color-bg-header
邊框    --color-border  --color-border-light
其他    --border-radius  --border-radius-lg
        --font-size-base  --font-size-sm  --font-size-xs
```

**禁止**自創 `--text-primary`、`--surface-color` 這類不存在的變數——
CSS fallback 值會生效，曾造成整頁深色 fallback、白底白字。

**這條管的是「引用全站色票」**。在自己的 scope 裡定義、自己使用的區域變數
（例如某個版面檔在 `.xxx-page` 上定義 `--xxx-shell-max: 1800px`）不在此限，
因為不存在「引用到不存在的變數」的風險，而且能把散落的尺寸集中成一處。
判別方式：**變數是別人定義的（`common.css` 的 `:root`）就必須照白名單；
是自己定義自己用的就可以**。
範例：`backend/app/static/css/platform-manual.css` 頂端的 `--manual-*`。

### Alpine.js 四條硬規則

**1. `x-for` / `x-if` 的直接子節點必須是單一 element**

**2. 有 `x-show` 的元素禁止用 inline style 設 `display`**

```html
<!-- 錯誤：x-show 還原時會清掉 inline display，flex 佈局遺失退回 block -->
<div x-show="visible" style="display:flex; gap:8px;">
<!-- 正確：佈局屬性寫在 class -->
<div x-show="visible" class="my-flex-container">
```

**3. select 綁動態 `x-for` options 時，option 必須加 `:selected`**

```html
<!-- 錯誤：初次渲染顯示第一個 option，不是實際 state 值 -->
<select x-model="col.field">
    <template x-for="f in fields" :key="f"><option :value="f" x-text="f"></option></template>
</select>
<!-- 正確 -->
<select x-model="col.field">
    <template x-for="f in fields" :key="f">
        <option :value="f" :selected="f === col.field" x-text="f"></option>
    </template>
</select>
```

Alpine 設定 select value 早於 x-for 展開 options，找不到對應 option 就退回第一個。
症狀是「一進頁面顯示錯的，手動改一次就正常」，極易漏看。options 靜態寫死時不必加。

**4. Modal 禁用 `@click.away` 關閉**

**5. `x-data` 屬性用單引號包**

```html
<!-- 錯誤：tojson 的雙引號與屬性雙引號互咬，整個元件初始化失敗 -->
<div x-data="wksManager({{ sc|tojson }})">
<!-- 正確 -->
<div x-data='wksManager({{ sc|tojson }})'>
```

症狀是滿螢幕 `Alpine Expression Error: xxx is not defined`。

### Jinja2 `dict.update` 陷阱

```jinja2
{# 錯誤：取到的是 dict 的內建 update 方法，永遠 truthy #}
{% if widget.caps.update %}
{# 正確 #}
{% if widget.caps['update'] %}
```

只有 `update` 會錯（`create` / `delete` 不是 dict 方法），所以是**只錯一個分支**的現象。
凡 dict 傳進模板且 key 可能撞到 dict 方法（`update`/`items`/`keys`/`values`/`get`/`copy`/`pop`），
一律用 `['key']`。

### 元件級可見性（D2）需要注入 caps

`BkCaps.can(code)` 讀的是 `window.__PAGE_CAPS`，**該變數由各頁面自行注入，無全域預設**。
漏注入時 `can()` 恆為 false，症狀是**按鈕點下去完全沒反應、console 也不報錯**。

```python
from app.services.capability_service import build_caps
return render_template('...', page_caps=build_caps(['module.permission_code']))
```
```html
<script>window.__PAGE_CAPS = {{ page_caps | default({}) | tojson }};</script>
```

模板層的 `{% if can('...') %}` 走後端 Jinja2 global，與此無關——
所以會出現「按鈕有渲染但點了沒用」的矛盾特徵。
（`layouts/base.html` 已載入 capability.js，不必重複引入。）

### Modal 表單元素

CSS 全寬規則必須排除 radio/checkbox，否則它們會被撐到 100% 寬、
擠壓同列文字成直排：

```css
.stu-field input:not([type="radio"]):not([type="checkbox"]),
.stu-field select, .stu-field textarea { width: 100%; }
```

含表單的 Modal 建議最小寬度 450px，用 inline style 覆蓋（`style="width:500px;"`）。

### JS/CSS 分離（FRONT-01）

模板中禁止內嵌大量 JS/CSS。CSS 抽成 `.css`、JS 抽成 `.js`，
只有初始化呼叫、Jinja2 變數注入這類膠水碼可留在 HTML（不超過 30 行）。

需要把 Jinja2 變數帶進 JS 時用 window bridge：

```html
<script>window.__PAGE_CONFIG = { id: '{{ obj.secure_code }}', year: {{ year }} };</script>
<script src="/static/.../page.js"></script>
```

單一 HTML 模板不超過 500 行，超過就拆（modal 抽成 `_xxx_modals.html`）。

### 模組靜態檔位置

```
modules/<name>/static/modules/<name>/js|css|icons/
```
存取 URL：`/static/modules/<name>/js/xxx.js`。
**禁止**複製到 `backend/app/static/`（那裡只放平台級資源）。
