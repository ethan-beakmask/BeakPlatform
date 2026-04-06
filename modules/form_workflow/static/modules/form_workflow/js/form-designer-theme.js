/**
 * form-designer-theme.js -- 表單風格主題管理
 * 從 form-designer-main.js 拆分
 *
 * 依賴全域變數: formBuilder, currentFormTheme (form-designer-main.js)
 * 提供全域: DEFAULT_THEME_FOR_NEW_FORM, _themeComponentDefaults,
 *           setFormTheme(), getThemeComponentDefaults(), _walkComponents(),
 *           applyThemeDefaultsToAll(), loadFormThemes()
 */

const DEFAULT_THEME_FOR_NEW_FORM = 'parallel-label';  // 新表單預設風格

// 主題的元件預設屬性快取 { themeName: {labelPosition, labelWidth, ...} }
const _themeComponentDefaults = {};

// 表單風格主題切換
function setFormTheme(theme) {
    currentFormTheme = theme || 'default';
    const wrapper = document.getElementById('builder-wrapper');
    if (wrapper) {
        if (currentFormTheme === 'default') {
            wrapper.removeAttribute('data-form-theme');
        } else {
            wrapper.setAttribute('data-form-theme', currentFormTheme);
        }
    }
    const dropdown = document.getElementById('form-theme');
    if (dropdown) {
        dropdown.value = currentFormTheme;
    }
    // 切換主題時，對已存在的元件套用 component_defaults
    if (formBuilder) {
        applyThemeDefaultsToAll();
    }
}

// 取得當前主題的元件預設屬性
function getThemeComponentDefaults() {
    return _themeComponentDefaults[currentFormTheme] || null;
}

// 遞迴走訪 schema 所有元件
function _walkComponents(components, fn) {
    if (!components) return;
    components.forEach(comp => {
        fn(comp);
        // 巢狀結構：columns, fieldset, panel, tabs, well, table
        if (comp.columns) {
            comp.columns.forEach(col => _walkComponents(col.components, fn));
        }
        if (comp.components) {
            _walkComponents(comp.components, fn);
        }
        if (comp.rows) {
            comp.rows.forEach(row => row.forEach(cell => _walkComponents(cell.components, fn)));
        }
    });
}

// 切換主題時，強制套用到所有已存在的 input 元件
function applyThemeDefaultsToAll() {
    if (!formBuilder) return;
    const defaults = getThemeComponentDefaults();
    const schema = formBuilder.schema;
    if (!schema || !schema.components) return;
    const props = ['labelPosition', 'labelWidth', 'labelMargin'];
    _walkComponents(schema.components, comp => {
        if (comp.input === false) return;
        if (!defaults) {
            // 切回 formio預設 (default) 時，移除主題設定的屬性，回歸 Form.io 原始行為
            props.forEach(prop => { delete comp[prop]; });
        } else {
            props.forEach(prop => {
                if (defaults[prop] !== undefined) {
                    comp[prop] = defaults[prop];
                }
            });
        }
    });
    // 重建 builderGroups 讓新拖入的元件也用新主題的預設值
    formBuilder.options.builder = buildBuilderGroups();
    // 重新渲染 builder
    formBuilder.setForm(schema).then(() => {
        formBuilder.redraw();
    });
}

// 從 API 載入可用主題並填充下拉選單
function loadFormThemes() {
    return fetch('/api/form-workflow/form-themes')
        .then(r => r.json())
        .then(json => {
            if (!json.success) return;
            const dropdown = document.getElementById('form-theme');
            if (!dropdown) return;
            json.data.forEach(theme => {
                // 快取元件預設屬性
                if (theme.component_defaults) {
                    _themeComponentDefaults[theme.name] = theme.component_defaults;
                }
                // 跳過已存在的選項
                if (dropdown.querySelector(`option[value="${theme.name}"]`)) return;
                const opt = document.createElement('option');
                opt.value = theme.name;
                opt.textContent = theme.display_name;
                dropdown.appendChild(opt);
            });
            // 恢復當前選中值
            if (currentFormTheme && currentFormTheme !== 'default') {
                dropdown.value = currentFormTheme;
            }
        })
        .catch(e => console.warn('載入主題清單失敗:', e));
}
