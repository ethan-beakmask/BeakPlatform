/* menu.js - 動態選單元件邏輯 */

var __MENU_CONFIG = window.__MENU_CONFIG || {};

function menuComponent() {
    return {
        menuTree: [],
        expandedItems: new Set(),
        defaultExpandLevel: __MENU_CONFIG.expandLevel || 1,
        currentPath: window.location.pathname,
        userType: '',

        async loadMenu() {
            try {
                var csrfToken = document.querySelector('meta[name="csrf-token"]')?.content;
                var resp = await fetch('/bp/api/menu?layout=' + (__MENU_CONFIG.layout || 'navbar'), {
                    headers: {
                        'X-CSRFToken': csrfToken || ''
                    }
                });
                if (resp.ok) {
                    var data = await resp.json();
                    this.menuTree = data.menu;
                    this.userType = data.user_type || '';
                    this.initExpanded(this.menuTree, 0);
                }
            } catch (e) {
                console.error('Failed to load menu:', e);
            }
        },

        initExpanded(items, depth) {
            for (var i = 0; i < items.length; i++) {
                var item = items[i];
                if (depth < this.defaultExpandLevel || item.is_expanded) {
                    this.expandedItems.add(item.id);
                }
                if (item.href === this.currentPath) {
                    this.expandedItems.add(item.id);
                }
                if (item.children && item.children.length > 0) {
                    this.initExpanded(item.children, depth + 1);
                }
            }
        },

        toggleExpand(itemId) {
            if (this.expandedItems.has(itemId)) {
                this.expandedItems.delete(itemId);
            } else {
                this.expandedItems.add(itemId);
            }
            this.$nextTick(() => this.$forceUpdate?.());
        },

        isExpanded(itemId) {
            return this.expandedItems.has(itemId);
        },

        isActive(href) {
            return href && this.currentPath === href;
        },

        getMenuColorClass(item) {
            // 依 CSV 權限顏色表，viewer-independent
            var level = item.bg_level || '';
            var cross = item.is_cross_level;

            if (level === 'common') return 'menu-common';
            if (level === 'system') return cross ? 'menu-sys-cross' : 'menu-sys-only';
            if (level === 'admin') return cross ? 'menu-org-cross' : 'menu-org-only';
            if (level === 'user') return cross ? 'menu-user-cross' : 'menu-user-only';
            if (level === 'external') return 'menu-ext-only';
            return '';
        },

        renderNavbarItem(item) {
            if (item.link_type === 'divider') {
                return '<li class="menu-divider-h"></li>';
            }

            if (item.link_type === 'header') {
                var colorClass = this.getMenuColorClass(item);
                return '<li class="menu-header-h ' + colorClass + '">' + this.escapeHtml(item.title) + '</li>';
            }

            var hasChildren = item.children && item.children.length > 0;
            var isActive = this.isActive(item.href) ? 'active' : '';
            var target = item.open_in_new_tab ? ' target="_blank"' : '';
            var colorClass = this.getMenuColorClass(item);

            if (hasChildren) {
                var childrenHtml = item.children.map(function(child) { return this.renderNavbarItem(child); }.bind(this)).join('');
                return '<li class="menu-item has-submenu ' + isActive + ' ' + colorClass + '">' +
                    '<span class="menu-link" @click="toggleExpand(\'' + item.id + '\')">' +
                        (item.icon ? '<i class="' + this.escapeHtml(item.icon) + '"></i> ' : '') + this.escapeHtml(item.title) +
                        '<span class="submenu-arrow">&#9662;</span>' +
                    '</span>' +
                    '<ul class="submenu" x-show="isExpanded(\'' + item.id + '\')" x-cloak>' +
                        childrenHtml +
                    '</ul>' +
                '</li>';
            } else {
                var href = item.href || '#';
                return '<li class="menu-item ' + isActive + ' ' + colorClass + '">' +
                    '<a href="' + href + '" class="menu-link"' + target + '>' +
                        (item.icon ? '<i class="' + this.escapeHtml(item.icon) + '"></i> ' : '') + this.escapeHtml(item.title) +
                    '</a>' +
                '</li>';
            }
        },

        renderSidebarItem(item, depth) {
            var indent = depth * 16;
            var colorClass = this.getMenuColorClass(item);

            if (item.link_type === 'divider') {
                return '<div class="sidebar-divider" style="margin-left: ' + indent + 'px;"></div>';
            }

            if (item.link_type === 'header') {
                return '<div class="sidebar-header ' + colorClass + '" style="margin-left: ' + indent + 'px;">' +
                    (item.icon ? '<i class="' + this.escapeHtml(item.icon) + '"></i> ' : '') + this.escapeHtml(item.title) + '</div>';
            }

            var hasChildren = item.children && item.children.length > 0;
            var isActive = this.isActive(item.href) ? 'active' : '';
            var target = item.open_in_new_tab ? ' target="_blank"' : '';

            var html = '<div class="sidebar-item ' + isActive + ' ' + colorClass + '" style="padding-left: ' + (indent + 16) + 'px;">';

            if (hasChildren) {
                html += '<div class="sidebar-link expandable" @click="toggleExpand(\'' + item.id + '\')">' +
                    '<span>' + (item.icon ? '<i class="' + this.escapeHtml(item.icon) + '"></i> ' : '') + this.escapeHtml(item.title) + '</span>' +
                    '<span class="expand-icon">' + (this.isExpanded(item.id) ? '-' : '+') + '</span>' +
                '</div>';
            } else {
                var href = item.href || '#';
                html += '<a href="' + href + '" class="sidebar-link"' + target + '>' +
                    (item.icon ? '<i class="' + this.escapeHtml(item.icon) + '"></i> ' : '') + this.escapeHtml(item.title) + '</a>';
            }

            html += '</div>';

            if (hasChildren) {
                html += '<div class="sidebar-children" x-show="isExpanded(\'' + item.id + '\')" x-cloak>';
                for (var i = 0; i < item.children.length; i++) {
                    html += this.renderSidebarItem(item.children[i], depth + 1);
                }
                html += '</div>';
            }

            return html;
        },

        escapeHtml(str) {
            if (!str) return '';
            return str.replace(/[&<>"']/g, function(m) {
                return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[m];
            });
        }
    };
}
