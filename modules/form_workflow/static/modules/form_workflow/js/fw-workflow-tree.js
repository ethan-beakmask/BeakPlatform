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

        async init() {
            try {
                var res = await fetch('/api/form-workflow/workflows/flow-trees/' + this.secureCode);
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
                });
            } catch (e) {
                this.error = '載入失敗: ' + e.message;
            } finally {
                this.loading = false;
            }
        },

        _renderTree(tree, rootCode) {
            var esc = function(s) { return s ? s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;') : ''; };
            var STEM_X = 111;
            var CONN_W = 149;
            var CARD_MID = 85;

            var renderCard = function(node, isRoot) {
                var href = '/api/workflows/designer/standalone?id=' + node.secure_code +
                    (isRoot ? '' : '&from=tree&root=' + rootCode) +
                    (node.is_unused ? '&editable=1' : '');
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
