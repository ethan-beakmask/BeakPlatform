/**
 * sitemenu-widget.js -- SITEMENU 選單元件
 *
 * 將 Site Map 樹狀結構渲染為導航選單 (直式/橫式)。
 * 資料即時從 DB 取得，依 dc_site_map_permissions 白名單過濾。
 *
 * 設計模式同 DataListWidget: 獨立 class，支援 PageContext 整合。
 */

class SiteMenuWidget {
    constructor(container, config) {
        this.container = container;
        this.id = (config && config.id) || ('smw_' + Math.random().toString(36).slice(2, 8));

        this.config = Object.assign({
            title: '',
            orientation: 'vertical',    // 'vertical' | 'horizontal'
            startNodeSc: '',            // 起始節點 SC (空 = 整棵樹)
            startLevel: 'children',     // 'self' = 本級 | 'children' = 下一級
            bgColor: '#ffffff',
            itemBgColor: '#ffffff',
            itemTextColor: '#333333',
            itemHoverBgColor: '#e9ecef',
            itemHoverTextColor: '#333333',
            accentColor: '#e67e22',     // accent 強調色 (邊框/active/hover)
            itemGap: 6,
            hoverExpand: true,
            hoverExpandDelay: 300,
            contextOutputs: [],
            contextInputs: [],

            // 子系統 context (由 portal 注入)
            _subSystemSc: '',
            _siteMapNodeSc: '',
        }, config);

        this.tree = [];
        this.loading = true;
        this._hoverTimers = {};
        this._activeNodeSc = null;
        this._floatingPanels = [];  // 橫式: body 上的浮動 submenu
    }

    // =================================================================
    // Lifecycle
    // =================================================================

    async init() {
        // PageContext 登錄
        if (typeof PageContext !== 'undefined') {
            PageContext.register(this.id);

            var outputKeys = (this.config.contextOutputs || []).map(function (o) {
                return o.contextKey;
            });
            if (outputKeys.length > 0) {
                PageContext.registerOutputKeys(this.id, outputKeys);
            }

            var self = this;
            var inputs = this.config.contextInputs || [];
            for (var i = 0; i < inputs.length; i++) {
                (function (inp) {
                    PageContext.subscribe(inp.contextKey, self.id, function (key, value) {
                        self._onContextChange(key, value);
                    });
                })(inputs[i]);
            }
        }

        this._renderSkeleton();
        await this._loadMenuTree();
        this._renderMenu();
    }

    getConfig() {
        return Object.assign({}, this.config);
    }

    updateConfig(newConfig) {
        Object.assign(this.config, newConfig);
        // 有資料或設計模式 (mock) 都需要重新渲染
        this._renderMenu();
    }

    destroy() {
        this._closeAllFloating();
        var keys = Object.keys(this._hoverTimers);
        for (var i = 0; i < keys.length; i++) {
            clearTimeout(this._hoverTimers[keys[i]]);
        }
        this._hoverTimers = {};
        this.container.innerHTML = '';
    }

    // =================================================================
    // Data
    // =================================================================

    async _loadMenuTree() {
        var ssSc = this.config._subSystemSc;
        if (!ssSc) {
            this.loading = false;
            return;
        }
        try {
            var res = await fetch('/api/nocode-builder/sub-systems/' + ssSc + '/site-map/menu-tree');
            var data = await res.json();
            if (data.success) {
                this.tree = (data.data && data.data.tree) || [];
            }
        } catch (e) {
            console.error('SiteMenuWidget loadMenuTree:', e);
        }
        this.loading = false;
    }

    // =================================================================
    // Render
    // =================================================================

    _renderSkeleton() {
        this.container.innerHTML = '<div class="smw-root"><div class="smw-loading">載入中...</div></div>';
    }

    _renderMenu() {
        this._closeAllFloating();

        var root = document.createElement('div');
        root.className = 'smw-root smw-' + this.config.orientation;
        root.style.backgroundColor = this.config.bgColor;
        root.style.setProperty('--smw-accent', this.config.accentColor || '#e67e22');

        if (this.config.title) {
            var header = document.createElement('div');
            header.className = 'smw-header';
            header.textContent = this.config.title;
            header.style.backgroundColor = this.config.bgColor;
            root.appendChild(header);
        }

        var displayNodes = this._resolveDisplayNodes();

        if (displayNodes.length === 0) {
            // 設計模式 (無 _subSystemSc) → 顯示 mock 預覽
            if (!this.config._subSystemSc) {
                this._renderMockMenu(root);
            } else {
                var empty = document.createElement('div');
                empty.className = 'smw-empty';
                empty.innerHTML = '<i class="bi bi-menu-button-wide smw-empty-icon"></i><span>無可用選單項目</span>';
                root.appendChild(empty);
            }
            this.container.innerHTML = '';
            this.container.appendChild(root);
            return;
        }

        var ul = this._buildMenuLevel(displayNodes, 0);
        root.appendChild(ul);
        this.container.innerHTML = '';
        this.container.appendChild(root);
    }

    /**
     * 設計模式 mock 選單：讓用戶在 Studio 中預覽元件外觀
     */
    _renderMockMenu(root) {
        root.classList.add('smw-mock');

        var mockNodes = [
            { secure_code: '_m1', name: '首頁', subtitle: '主控台', icon: 'fas fa-home', children: [] },
            { secure_code: '_m2', name: '功能', subtitle: '管理中心', icon: 'fas fa-th-large', children: [
                { secure_code: '_m2a', name: '項目 A', icon: 'fas fa-file-alt', children: [] },
                { secure_code: '_m2b', name: '項目 B', icon: 'fas fa-chart-line', children: [] },
                { secure_code: '_m2c', name: '項目 C', icon: 'fas fa-database', children: [] },
            ]},
            { secure_code: '_m3', name: '報表', subtitle: '數據分析', icon: 'fas fa-chart-bar', children: [] },
            { secure_code: '_m4', name: '設定', subtitle: '系統管理', icon: 'fas fa-cog', children: [] },
        ];

        var ul = this._buildMenuLevel(mockNodes, 0);
        root.appendChild(ul);

        // Mock 浮水印
        var badge = document.createElement('div');
        badge.className = 'smw-mock-badge';
        badge.textContent = 'PREVIEW';
        root.appendChild(badge);
    }

    /**
     * 根據 startNodeSc + startLevel 從 tree 中取出要顯示的節點
     *
     * startNodeSc 為空 → 整棵樹
     * startLevel = 'self'     → 只顯示指定節點本身 (含其子樹)
     * startLevel = 'children' → 顯示指定節點的 children (各自含子樹)
     */
    _resolveDisplayNodes() {
        if (!this.config.startNodeSc) {
            return this.tree;
        }

        var target = this._findNode(this.tree, this.config.startNodeSc);
        if (!target) {
            return [];
        }

        if (this.config.startLevel === 'self') {
            return [target];
        }
        // 'children' (預設)
        return target.children || [];
    }

    /** 遞迴搜尋節點 by secure_code */
    _findNode(nodes, sc) {
        for (var i = 0; i < nodes.length; i++) {
            if (nodes[i].secure_code === sc) return nodes[i];
            if (nodes[i].children && nodes[i].children.length > 0) {
                var found = this._findNode(nodes[i].children, sc);
                if (found) return found;
            }
        }
        return null;
    }

    _buildMenuLevel(nodes, depth) {
        var isHoriz = this.config.orientation === 'horizontal';
        var ul = document.createElement('ul');
        ul.className = depth === 0 ? 'smw-menu' : 'smw-submenu';

        var gap = (this.config.itemGap != null ? this.config.itemGap : 6);
        ul.style.gap = gap + 'px';

        var self = this;
        for (var i = 0; i < nodes.length; i++) {
            var node = nodes[i];
            var li = document.createElement('li');
            li.className = 'smw-item';
            var hasChildren = node.children && node.children.length > 0;
            if (hasChildren) {
                li.classList.add('smw-has-children');
            }

            var a = this._createLink(node);
            li.appendChild(a);

            if (hasChildren) {
                var arrow = document.createElement('span');
                arrow.className = 'smw-arrow';
                a.appendChild(arrow);

                if (isHoriz) {
                    // 橫式：子選單用 floating panel 掛在 body 上
                    this._bindFloatingSubmenu(li, a, node.children, depth);
                } else {
                    // 直式：子選單內嵌在 li 中
                    var subUl = this._buildMenuLevel(node.children, depth + 1);
                    li.appendChild(subUl);

                    if (this.config.hoverExpand) {
                        this._bindHoverExpand(li, node.secure_code);
                    }

                    // Click toggle
                    (function (liRef) {
                        liRef.querySelector('.smw-link').addEventListener('click', function (e) {
                            if (liRef.classList.contains('smw-has-children')) {
                                liRef.classList.toggle('smw-open');
                            }
                        });
                    })(li);
                }
            }

            ul.appendChild(li);
        }

        return ul;
    }

    _createLink(node) {
        var a = document.createElement('a');
        a.className = 'smw-link';
        a.href = 'javascript:void(0)';
        a.setAttribute('data-sc', node.secure_code);

        if (node.icon) {
            var icon = document.createElement('i');
            icon.className = node.icon;
            a.appendChild(icon);
        }

        var text = document.createElement('span');
        text.className = 'smw-link-text';
        text.textContent = node.name;
        a.appendChild(text);

        // 橫式一級: 顯示副標題
        var isHoriz = this.config.orientation === 'horizontal';
        if (isHoriz && node.subtitle) {
            var sub = document.createElement('small');
            sub.className = 'smw-link-sub';
            sub.textContent = node.subtitle;
            a.appendChild(sub);
        }

        // 樣式
        a.style.backgroundColor = this.config.itemBgColor;
        a.style.color = this.config.itemTextColor;

        // Hover: 橫式用 accent 色，直式用 config 色
        var cfg = this.config;
        var accentColor = cfg.accentColor || '#e67e22';
        a.addEventListener('mouseenter', function () {
            a.style.backgroundColor = cfg.itemHoverBgColor;
            a.style.color = isHoriz ? accentColor : cfg.itemHoverTextColor;
        });
        a.addEventListener('mouseleave', function () {
            if (!a.classList.contains('smw-active')) {
                a.style.backgroundColor = cfg.itemBgColor;
                a.style.color = cfg.itemTextColor;
            }
        });

        // Click - emit context
        var self = this;
        a.addEventListener('click', function (e) {
            e.preventDefault();
            e.stopPropagation();
            self._onItemClick(node);
        });

        // 高亮目前節點
        if (this._activeNodeSc && node.secure_code === this._activeNodeSc) {
            a.classList.add('smw-active');
            a.style.backgroundColor = cfg.itemHoverBgColor;
            a.style.color = isHoriz ? accentColor : cfg.itemHoverTextColor;
        }

        return a;
    }

    _bindHoverExpand(li, nodeSc) {
        var self = this;
        var delay = this.config.hoverExpandDelay || 300;

        li.addEventListener('mouseenter', function () {
            self._hoverTimers[nodeSc] = setTimeout(function () {
                li.classList.add('smw-open');
            }, delay);
        });

        li.addEventListener('mouseleave', function () {
            if (self._hoverTimers[nodeSc]) {
                clearTimeout(self._hoverTimers[nodeSc]);
                delete self._hoverTimers[nodeSc];
            }
            li.classList.remove('smw-open');
        });
    }

    // =================================================================
    // Floating Submenu (橫式專用，掛在 body 上)
    // =================================================================

    /**
     * 為含子項的 li 綁定 hover/click → 顯示浮動子選單
     */
    _bindFloatingSubmenu(li, triggerLink, childNodes, parentDepth) {
        var self = this;
        var panel = null;
        var delay = this.config.hoverExpandDelay || 300;
        var timerId = null;
        var isOverPanel = false;
        var isOverTrigger = false;

        function showPanel() {
            if (panel) return;
            panel = self._createFloatingPanel(childNodes, parentDepth + 1);
            document.body.appendChild(panel);
            self._floatingPanels.push(panel);

            // 定位：根據 trigger 的位置
            var rect = triggerLink.getBoundingClientRect();
            if (parentDepth === 0) {
                // 第一層：在 trigger 下方
                panel.style.top = rect.bottom + 'px';
                panel.style.left = rect.left + 'px';
            } else {
                // 巢狀：在 trigger 右邊
                panel.style.top = rect.top + 'px';
                panel.style.left = rect.right + 'px';
            }

            // 邊界檢查：如果超出視窗右邊，改往左展開
            var panelRect = panel.getBoundingClientRect();
            if (panelRect.right > window.innerWidth) {
                panel.style.left = (rect.left - panelRect.width) + 'px';
            }
            // 如果超出視窗底部，向上調整
            if (panelRect.bottom > window.innerHeight) {
                panel.style.top = Math.max(0, window.innerHeight - panelRect.height) + 'px';
            }

            panel.addEventListener('mouseenter', function () {
                isOverPanel = true;
            });
            panel.addEventListener('mouseleave', function () {
                isOverPanel = false;
                scheduleHide();
            });

            li.classList.add('smw-open');
        }

        function hidePanel() {
            if (panel) {
                // 先關閉 panel 內的所有子 floating panel
                var childPanels = panel.querySelectorAll('[data-smw-floating]');
                // 從 body 移除此 panel
                var idx = self._floatingPanels.indexOf(panel);
                if (idx >= 0) self._floatingPanels.splice(idx, 1);
                if (panel.parentNode) panel.parentNode.removeChild(panel);
                panel = null;
            }
            li.classList.remove('smw-open');
        }

        function scheduleHide() {
            setTimeout(function () {
                if (!isOverPanel && !isOverTrigger) {
                    hidePanel();
                }
            }, 100);
        }

        if (this.config.hoverExpand) {
            li.addEventListener('mouseenter', function () {
                isOverTrigger = true;
                timerId = setTimeout(showPanel, delay);
            });
            li.addEventListener('mouseleave', function () {
                isOverTrigger = false;
                if (timerId) { clearTimeout(timerId); timerId = null; }
                scheduleHide();
            });
        }

        // Click toggle
        triggerLink.addEventListener('click', function (e) {
            e.preventDefault();
            e.stopPropagation();
            if (panel) {
                hidePanel();
            } else {
                showPanel();
            }
        });
    }

    /**
     * 建立掛在 body 的浮動 submenu panel
     */
    _createFloatingPanel(nodes, depth) {
        var panel = document.createElement('div');
        panel.className = 'smw-floating-panel';
        if (depth > 1) {
            panel.classList.add('smw-nested-panel');
        }
        panel.setAttribute('data-smw-floating', '1');
        panel.style.position = 'fixed';
        panel.style.zIndex = '10000';
        panel.style.background = this.config.bgColor || '#fff';
        panel.style.minWidth = '200px';
        panel.style.setProperty('--smw-accent', this.config.accentColor || '#e67e22');

        var ul = document.createElement('ul');
        ul.className = 'smw-menu smw-floating-menu';
        var gap = (this.config.itemGap != null ? this.config.itemGap : 6);
        ul.style.gap = gap + 'px';

        for (var i = 0; i < nodes.length; i++) {
            var node = nodes[i];
            var li = document.createElement('li');
            li.className = 'smw-item';
            li.style.position = 'relative';
            var hasChildren = node.children && node.children.length > 0;
            if (hasChildren) li.classList.add('smw-has-children');

            var a = this._createLink(node);
            li.appendChild(a);

            if (hasChildren) {
                var arrow = document.createElement('span');
                arrow.className = 'smw-arrow';
                arrow.style.borderTop = '4px solid transparent';
                arrow.style.borderBottom = '4px solid transparent';
                arrow.style.borderLeft = '5px solid currentColor';
                arrow.style.display = 'inline-block';
                arrow.style.marginLeft = '6px';
                a.appendChild(arrow);

                this._bindFloatingSubmenu(li, a, node.children, depth);
            }

            ul.appendChild(li);
        }

        panel.appendChild(ul);
        return panel;
    }

    /** 關閉所有浮動 panel */
    _closeAllFloating() {
        for (var i = 0; i < this._floatingPanels.length; i++) {
            var p = this._floatingPanels[i];
            if (p.parentNode) p.parentNode.removeChild(p);
        }
        this._floatingPanels = [];
    }

    // =================================================================
    // Context
    // =================================================================

    _onItemClick(node) {
        this._activeNodeSc = node.secure_code;

        // 關閉所有浮動 submenu
        this._closeAllFloating();

        // 更新高亮（含 floating panel 內的 link）
        var links = this.container.querySelectorAll('.smw-link');
        var cfg = this.config;
        for (var i = 0; i < links.length; i++) {
            links[i].classList.remove('smw-active');
            links[i].style.backgroundColor = cfg.itemBgColor;
            links[i].style.color = cfg.itemTextColor;
        }
        var active = this.container.querySelector('.smw-link[data-sc="' + node.secure_code + '"]');
        if (active) {
            active.classList.add('smw-active');
            active.style.backgroundColor = cfg.itemHoverBgColor;
            active.style.color = cfg.itemHoverTextColor;
        }

        // 導航：切換頁面（portal 注入的 callback）
        if (typeof this.config._onNavigate === 'function' && node.page_layout_secure_code) {
            this.config._onNavigate(node);
        }

        // Emit context outputs
        var outputs = this.config.contextOutputs || [];
        for (var i = 0; i < outputs.length; i++) {
            var out = outputs[i];
            if (out.event === 'menu-click' && out.contextKey) {
                var value = node[out.sourceField] || null;
                if (typeof PageContext !== 'undefined') {
                    PageContext.set(out.contextKey, value, this.id);
                }
            }
        }
    }

    _onContextChange(key, value) {
        // 可用於外部指定高亮節點
        var inputs = this.config.contextInputs || [];
        for (var i = 0; i < inputs.length; i++) {
            if (inputs[i].contextKey === key && inputs[i].targetField === 'active_node') {
                this._activeNodeSc = value;
                this._renderMenu();
                return;
            }
        }
    }
}
