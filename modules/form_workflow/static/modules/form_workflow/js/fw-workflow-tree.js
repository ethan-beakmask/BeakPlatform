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
        _chart: null,

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
                    setTimeout(function() {
                        self._chart = WorkflowTreeChart.render(
                            '#workflow-tree-chart',
                            [tree],
                            {
                                onNodeClick: function(nodeData) {
                                    window.location.href = '/api/workflows/designer/standalone?id=' + nodeData.id + '&from=tree&root=' + self.secureCode;
                                }
                            }
                        );
                    }, 50);
                });
            } catch (e) {
                this.error = '載入失敗: ' + e.message;
            } finally {
                this.loading = false;
            }
        },

        fitChart() {
            if (this._chart) {
                this._chart.fit();
            }
        }
    };
}
