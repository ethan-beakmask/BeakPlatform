/* workflow-designer-init.js - 主題管理 + 節點定義載入 */

// === Workflow Designer 主題管理 ===
(function() {
    const WORKFLOW_THEME_KEY = 'workflow_designer_theme';

    function getWorkflowTheme() {
        const followSystemTheme = localStorage.getItem('workflow_designer_follow_theme');

        if (followSystemTheme === 'false') {
            return localStorage.getItem(WORKFLOW_THEME_KEY) || 'light';
        }

        const systemTheme = localStorage.getItem('theme');
        if (systemTheme) {
            return systemTheme;
        }

        return 'light';
    }

    function setWorkflowTheme(theme) {
        localStorage.setItem(WORKFLOW_THEME_KEY, theme);
        applyWorkflowTheme(theme);
    }

    function applyWorkflowTheme(theme) {
        document.documentElement.setAttribute('data-theme', theme);

        document.querySelectorAll('[data-workflow-theme]').forEach(function(btn) {
            if (btn.dataset.workflowTheme === theme) {
                btn.classList.add('active');
            } else {
                btn.classList.remove('active');
            }
        });
    }

    document.addEventListener('DOMContentLoaded', function() {
        var theme = getWorkflowTheme();
        applyWorkflowTheme(theme);

        document.querySelectorAll('[data-workflow-theme]').forEach(function(btn) {
            btn.addEventListener('click', function() {
                var t = btn.dataset.workflowTheme;
                setWorkflowTheme(t);
            });
        });
    });

    // 立即應用主題（在 DOM 載入前）
    var theme = getWorkflowTheme();
    if (document.documentElement) {
        document.documentElement.setAttribute('data-theme', theme);
    }
})();

// === 節點定義載入 ===

// 分類名稱對應
var CATEGORY_NAMES = {
    'basic': __('基本節點'),
    'form': __('表單處理'),
    'notification': __('通知機制'),
    'flow_control': __('流程控制'),
    'data': __('資料處理'),
    'operation': __('運算操作'),
    'integration': __('系統整合'),
    'security': __('安全管控'),
    'security_ops': __('資安處置'),
    'system_admin': __('系統專用')
};

// 分類圖示對應
var CATEGORY_ICONS = {
    'basic': 'fas fa-circle-dot',
    'form': 'fas fa-file-signature',
    'notification': 'fas fa-bell',
    'flow_control': 'fas fa-route',
    'data': 'fas fa-database',
    'operation': 'fas fa-calculator',
    'integration': 'fas fa-plug',
    'security': 'fas fa-lock',
    'security_ops': 'fas fa-shield-virus',
    'system_admin': 'fas fa-shield-alt'
};

async function loadNodeDefinitions() {
    try {
        var response = await fetch(window.__BP + '/api/workflows/data/node-definitions');
        var result = await response.json();

        if (!result.success) {
            throw new Error(result.message || __('載入節點定義失敗'));
        }

        var container = document.getElementById('node-categories-container');
        container.innerHTML = '';

        var grouped = result.data;
        var categoryOrder = ['basic', 'form', 'notification', 'flow_control', 'data', 'operation', 'integration', 'security', 'security_ops', 'system_admin'];

        categoryOrder.forEach(function(categoryKey) {
            if (!grouped[categoryKey] || grouped[categoryKey].length === 0) {
                return;
            }

            var nodes = grouped[categoryKey];
            var categoryName = CATEGORY_NAMES[categoryKey] || categoryKey;
            var categoryIcon = CATEGORY_ICONS[categoryKey] || 'fas fa-folder';
            var categoryId = categoryKey + '-nodes';

            var categoryDiv = document.createElement('div');
            categoryDiv.className = 'node-category';

            var headerDiv = document.createElement('div');
            headerDiv.className = 'category-header';
            headerDiv.onclick = function() { toggleCategory(categoryId); };
            headerDiv.innerHTML =
                '<span><i class="' + categoryIcon + '"></i> ' + categoryName + '</span>' +
                '<span id="' + categoryId + '-icon" class="category-icon open">\u25B6</span>';

            var contentDiv = document.createElement('div');
            contentDiv.id = categoryId;
            contentDiv.className = 'category-content open';

            var paletteDiv = document.createElement('div');
            paletteDiv.className = 'node-palette';

            nodes.forEach(function(node) {
                var nodeDiv = document.createElement('div');
                nodeDiv.className = 'palette-node ' + categoryKey;
                nodeDiv.draggable = true;
                nodeDiv.setAttribute('data-node-type', node.type);
                nodeDiv.setAttribute('data-node-label', node.label);
                nodeDiv.setAttribute('data-node-icon', node.icon || '');

                nodeDiv.innerHTML =
                    '<div class="node-icon">' +
                        '<img src="' + node.icon + '" class="node-svg-icon" alt="">' +
                    '</div>' +
                    '<div class="node-info">' +
                        '<div class="node-title">' + node.label + '</div>' +
                        '<div class="node-description">' + (node.description || '') + '</div>' +
                    '</div>';

                if (typeof setupNodeDragEvents === 'function') {
                    setupNodeDragEvents(nodeDiv);
                } else {
                    nodeDiv.addEventListener('dragstart', function(e) {
                        var nodeType = this.getAttribute('data-node-type');
                        var nodeLabel = this.getAttribute('data-node-label');
                        var nodeIcon = this.getAttribute('data-node-icon');
                        e.dataTransfer.setData('nodeType', nodeType);
                        e.dataTransfer.setData('nodeLabel', nodeLabel);
                        e.dataTransfer.setData('nodeIcon', nodeIcon);
                        e.dataTransfer.effectAllowed = 'copy';
                    });
                }

                paletteDiv.appendChild(nodeDiv);
            });

            contentDiv.appendChild(paletteDiv);
            categoryDiv.appendChild(headerDiv);
            categoryDiv.appendChild(contentDiv);
            container.appendChild(categoryDiv);
        });

        console.log('節點定義載入完成');
    } catch (error) {
        console.error('載入節點定義失敗:', error);
        var container = document.getElementById('node-categories-container');
        container.innerHTML =
            '<div style="padding: 20px; text-align: center; color: #EF4444;">' +
            '<i class="fas fa-exclamation-triangle"></i> 載入節點失敗: ' + error.message +
            '</div>';
    }
}

document.addEventListener('DOMContentLoaded', function() {
    loadNodeDefinitions();

    setTimeout(function() {
        var themeSwitcherContainer = document.getElementById('themeSwitcherContainer');
        if (themeSwitcherContainer && window.ThemeManager) {
            var switcher = ThemeManager.createThemeSwitcher();
            themeSwitcherContainer.appendChild(switcher);
        }
    }, 300);
});
