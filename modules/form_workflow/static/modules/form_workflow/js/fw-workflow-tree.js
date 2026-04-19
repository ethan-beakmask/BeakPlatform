/* fw-workflow-tree.js — 流程樹系圖頁面 (Mode B)
 * Window Bridge: window.__TREE_CONFIG.secureCode
 */

var __TREE_CONFIG = window.__TREE_CONFIG || {};

function workflowTreePage() {
    return {
        secureCode: __TREE_CONFIG.secureCode || '',
        loading: true,
        error: '',
        treeName: '',
        treeCode: '',
        _zoom: { scale: 1, panX: 0, panY: 0 },
        _panState: null,
        _handlers: null,

        async init() {
            try {
                var res = await fetch('/bp/api/form-workflow/workflows/flow-trees/' + this.secureCode);
                var data = await res.json();
                if (!data.success) {
                    this.error = data.error || '載入失敗';
                    return;
                }
                var tree = data.data.tree;
                this.treeName = tree.name;
                this.treeCode = tree.code;

                var self = this;
                this.$nextTick(function() {
                    var container = document.getElementById('workflow-tree-chart');
                    if (container) container.innerHTML = self._renderTree(tree, self.secureCode);
                    self._setupPanListeners();
                    self.zoomFit();
                });
            } catch (e) {
                this.error = '載入失敗: ' + e.message;
            } finally {
                this.loading = false;
            }
        },

        destroy() {
            this._teardownPanListeners();
        },

        /* ── 縮放/平移 ── */
        zoomIn() {
            this._zoom.scale = Math.min(3, this._zoom.scale * 1.25);
            this._applyTransform();
        },
        zoomOut() {
            this._zoom.scale = Math.max(0.1, this._zoom.scale / 1.25);
            this._applyTransform();
        },
        zoomFit() {
            var viewport = document.getElementById('tree-viewport');
            var container = document.getElementById('workflow-tree-chart');
            if (!viewport || !container) return;
            container.style.transform = 'none';
            var cw = container.scrollWidth;
            var ch = container.scrollHeight;
            var vw = viewport.clientWidth;
            var vh = viewport.clientHeight;
            if (cw === 0 || ch === 0) return;
            var scale = Math.min(vw / cw, vh / ch, 1);
            var panX = Math.max(0, (vw - cw * scale) / 2);
            var panY = Math.max(0, (vh - ch * scale) / 2);
            this._zoom = { scale: scale, panX: panX, panY: panY };
            this._applyTransform();
        },
        startPan(e) {
            if (e.button !== 0) return;
            if (e.target.closest('a')) return;
            e.preventDefault();
            this._panState = {
                active: true,
                startX: e.clientX,
                startY: e.clientY,
                startPanX: this._zoom.panX,
                startPanY: this._zoom.panY
            };
            document.getElementById('tree-viewport').style.cursor = 'grabbing';
        },
        onWheel(e) {
            var viewport = document.getElementById('tree-viewport');
            if (!viewport) return;
            var rect = viewport.getBoundingClientRect();
            var cx = e.clientX - rect.left;
            var cy = e.clientY - rect.top;
            var z = this._zoom;
            var oldScale = z.scale;
            var factor = e.deltaY > 0 ? 0.9 : 1.1;
            var newScale = Math.max(0.1, Math.min(3, oldScale * factor));
            z.panX = cx - (cx - z.panX) * (newScale / oldScale);
            z.panY = cy - (cy - z.panY) * (newScale / oldScale);
            z.scale = newScale;
            this._applyTransform();
        },
        _applyTransform() {
            var container = document.getElementById('workflow-tree-chart');
            if (!container) return;
            var z = this._zoom;
            container.style.transform = 'translate(' + z.panX + 'px,' + z.panY + 'px) scale(' + z.scale + ')';
        },
        _setupPanListeners() {
            var self = this;
            var onMove = function(e) {
                var ps = self._panState;
                if (!ps || !ps.active) return;
                self._zoom.panX = ps.startPanX + (e.clientX - ps.startX);
                self._zoom.panY = ps.startPanY + (e.clientY - ps.startY);
                self._applyTransform();
            };
            var onUp = function() {
                if (self._panState) self._panState.active = false;
                var vp = document.getElementById('tree-viewport');
                if (vp) vp.style.cursor = 'grab';
            };
            window.addEventListener('mousemove', onMove);
            window.addEventListener('mouseup', onUp);
            self._handlers = { mousemove: onMove, mouseup: onUp };
        },
        _teardownPanListeners() {
            if (this._handlers) {
                window.removeEventListener('mousemove', this._handlers.mousemove);
                window.removeEventListener('mouseup', this._handlers.mouseup);
                this._handlers = null;
            }
        },

        /* ── 樹渲染 ── */
        _renderTree(tree, rootCode) {
            var esc = function(s) { return s ? s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;') : ''; };
            var STEM_X = 111;
            var CONN_W = 149;
            var CARD_MID = 85;

            var renderCard = function(node, isRoot) {
                var qp = [];
                if (!isRoot) { qp.push('from=tree', 'root=' + rootCode); }
                if (node.is_unused) { qp.push('editable=1'); }
                var href = '/bp/forms/workflows/' + node.secure_code + (qp.length ? '?' + qp.join('&') : '');
                var thumb = node.thumbnail_2x1
                    ? '<img src="' + node.thumbnail_2x1 + '" style="width:210px;height:120px;object-fit:contain;border:1px solid #e5e7eb;border-radius:4px;background:#f3f4f6;">'
                    : '<div style="width:210px;height:120px;display:flex;align-items:center;justify-content:center;border:1px solid #e5e7eb;border-radius:4px;background:#f3f4f6;"><i class="ri-flow-chart" style="font-size:32px;color:#9ca3af;"></i></div>';
                var borderLeft = isRoot ? 'border-left:3px solid #6366f1;' : '';
                var unusedStyle = node.is_unused ? 'opacity:0.75;border-style:dashed;border-color:#d4944a;' : '';
                var unusedBadge = node.is_unused ? ' <span style="background:#fef3c7;color:#d97706;font-size:10px;padding:1px 6px;border-radius:3px;">unused</span>' : '';
                return '<a href="' + href + '" style="text-decoration:none;display:inline-block;" title="' + esc(node.name) + ' — 點擊進入編輯">' +
                    '<div style="display:inline-block;padding:6px;background:#fff;border:1px solid #e5e7eb;border-radius:6px;' + borderLeft + unusedStyle +
                    'box-shadow:0 1px 2px rgba(0,0,0,0.04);transition:box-shadow 0.15s;" ' +
                    'onmouseover="this.style.boxShadow=\'0 2px 8px rgba(0,0,0,0.12)\'" onmouseout="this.style.boxShadow=\'0 1px 2px rgba(0,0,0,0.04)\'">' +
                    thumb +
                    '<div style="text-align:center;padding:4px 2px 2px;font-size:12px;color:#374151;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:210px;">' +
                    esc(node.name) + unusedBadge +
                    '</div></div></a>';
            };

            var renderChildren = function(children) {
                var h = '';
                for (var i = 0; i < children.length; i++) {
                    var child = children[i];
                    var isLast = i === children.length - 1;
                    h += '<div style="display:flex;">';
                    h += '<div style="width:' + CONN_W + 'px;flex-shrink:0;position:relative;">';
                    h += '<div style="position:absolute;left:0;top:0;' + (isLast ? 'height:' + CARD_MID + 'px;' : 'bottom:0;') + 'border-left:1.5px solid #d1d5db;"></div>';
                    h += '<div style="position:absolute;left:0;top:' + CARD_MID + 'px;width:100%;border-top:1.5px solid #d1d5db;"></div>';
                    h += '</div>';
                    h += '<div style="flex:1;padding:8px 0;">';
                    h += renderCard(child, false);
                    if (child.children && child.children.length > 0) {
                        h += '<div style="margin-left:' + STEM_X + 'px;height:8px;border-left:1.5px solid #d1d5db;"></div>';
                        h += '<div style="margin-left:' + STEM_X + 'px;">';
                        h += renderChildren(child.children);
                        h += '</div>';
                    }
                    h += '</div>';
                    h += '</div>';
                }
                return h;
            };

            var html = '<div style="padding:16px 20px;">';
            html += renderCard(tree, true);
            if (tree.children && tree.children.length > 0) {
                html += '<div style="margin-left:' + STEM_X + 'px;height:8px;border-left:1.5px solid #d1d5db;"></div>';
                html += '<div style="margin-left:' + STEM_X + 'px;">';
                html += renderChildren(tree.children);
                html += '</div>';
            } else {
                html += '<div style="padding:12px 0 0 40px;color:#9ca3af;font-size:13px;">沒有子流程</div>';
            }
            html += '</div>';
            return html;
        }
    };
}
