/**
 * fc-monitor.js — 執行監控 mixin (Cytoscape 流程圖 + 日誌 + 自動刷新)
 * 由 form-center.js 拆分而來
 */
function fcMonitor() {
    return {
        // --- State ---
        showMonitorModal: false,
        monitoringExecution: null,
        cyInstance: null,
        autoRefresh: true,
        autoRefreshTimer: null,
        workflowTabs: [],
        activeWorkflowTab: null,
        workflowGraphCache: {},
        monitorPage: 'overview',  // 'overview' | 'detail' | 'formContent' | 'approvals'
        monitorData: null,        // logs API 資料
        logSearchQuery: '',       // 日誌搜尋
        monitorStatus: {
            flowStatus: '-',
            activeCount: 0,
            completedCount: 0,
            failedCount: 0,
            waitingCount: 0,
            executionHistory: []
        },
        formDetail: null,
        loadingFormDetail: false,
        formDetailViewer: null,
        monitorFlowChartCy: null,
        approvalSortAsc: false,

        // --- Computed ---

        // 過濾後的日誌
        get filteredLogs() {
            const logs = this.monitorData?.logs || [];
            if (!this.logSearchQuery) return logs;
            const q = this.logSearchQuery.toLowerCase();
            return logs.filter(log =>
                (log.message || '').toLowerCase().includes(q) ||
                (log.node_id || '').toLowerCase().includes(q) ||
                (log.workflow_name || '').toLowerCase().includes(q) ||
                JSON.stringify(log.data || {}).toLowerCase().includes(q)
            );
        },

        // 變數變化記錄
        get variableChanges() {
            const logs = this.monitorData?.logs || [];
            const changes = [];

            for (const log of logs) {
                const time = typeof BkTime !== 'undefined' ? BkTime.format(log.timestamp, 'time') : (log.timestamp?.split(' ')[1] || '');
                const node = log.node_id?.replace('node-', '') || '';
                const displayName = log.display_name || node;
                const workflowName = log.workflow_name || '';
                const data = log.data || {};

                // 讀取欄位（OpFieldRead）
                if (log.message?.includes('讀取欄位:')) {
                    const match = log.message.match(/讀取欄位:\s*(\S+)\s*=\s*(.+)/);
                    if (match) {
                        changes.push({
                            timestamp: time,
                            node: node,
                            displayName: displayName,
                            workflowName: workflowName,
                            action: 'read',
                            actionLabel: 'read',
                            varName: match[1],
                            displayValue: match[2]
                        });
                    }
                }
                // 變數操作完成（OpSet）
                else if (log.message?.includes('變數操作完成:')) {
                    const match = log.message.match(/變數操作完成:\s*(\S+)\s*=\s*(.*)/);
                    if (match) {
                        changes.push({
                            timestamp: time,
                            node: node,
                            displayName: displayName,
                            workflowName: workflowName,
                            action: 'set',
                            actionLabel: data.operation || 'set',
                            varName: match[1],
                            displayValue: match[2] || '(空)'
                        });
                    }
                }
            }
            return changes;
        },

        // --- Methods ---

        async viewExecutionDetail(item) {
            console.log('檢視執行:', item);
            this.monitoringExecution = item;

            // 重置監控狀態
            this.monitorStatus = {
                flowStatus: item.workflow_status || item.status || '-',
                activeCount: 0,
                completedCount: 0,
                failedCount: 0,
                waitingCount: 0,
                executionHistory: []
            };

            this.workflowTabs = [];
            this.activeWorkflowTab = null;
            this.workflowGraphCache = {};
            this.monitorPage = 'overview';
            this.monitorData = null;
            this.logSearchQuery = '';
            this.formDetail = null;
            this.loadingFormDetail = false;
            this.showMonitorModal = true;

            await this.$nextTick();

            try {
                // 同時載入 path（含 workflow_tabs）和 logs
                const instanceId = item.execution_code || item.workflow_instance_secure_code || item.secure_code;
                const [pathLoaded, logsLoaded] = await Promise.all([
                    this.loadExecutionSnapshot(item),
                    this.loadExecutionLogs(instanceId)
                ]);

                // 從快取取得主流程的圖並初始化 Cytoscape
                const mainTab = this.workflowTabs.find(t => t.is_main);
                if (mainTab && this.workflowGraphCache[mainTab.instance_id]) {
                    this.initializeCytoscape(this.workflowGraphCache[mainTab.instance_id]);
                } else if (this.workflowTabs.length > 0) {
                    // 如果沒有標記為主流程，使用第一個
                    const firstTab = this.workflowTabs[0];
                    if (this.workflowGraphCache[firstTab.instance_id]) {
                        this.initializeCytoscape(this.workflowGraphCache[firstTab.instance_id]);
                    }
                } else {
                    console.warn('無法從追蹤資料取得流程圖');
                }

                // 啟動自動刷新
                if (this.autoRefresh) {
                    this.startAutoRefresh();
                }
            } catch (error) {
                console.error('載入流程追蹤錯誤:', error);
                this.showToast('載入流程圖失敗', 'error');
            }
        },

        async loadExecutionLogs(instanceId) {
            console.log('[LOGS] loadExecutionLogs 呼叫, instanceId:', instanceId);
            try {
                const url = `/bp/api/form-center/executions/${instanceId}/logs`;
                console.log('[LOGS] 請求 URL:', url);
                const response = await fetch(url);
                console.log('[LOGS] 回應狀態:', response.status);
                const result = await response.json();
                console.log('[LOGS] 回應內容:', result);

                if (result.success) {
                    this.monitorData = result.data;
                    console.log('[LOGS] logs 數量:', result.data?.logs?.length || 0);
                    console.log('[LOGS] variables:', result.data?.variables);
                } else {
                    console.error('[LOGS] 載入失敗:', result.error);
                }
            } catch (error) {
                console.error('[LOGS] 載入錯誤:', error);
            }
        },

        async loadExecutionSnapshot(item) {
            try {
                // 使用 execution_code 或 workflow_instance_secure_code
                const instanceId = item.execution_code || item.workflow_instance_secure_code || item.secure_code;
                const response = await fetch(`/bp/api/form-center/executions/${instanceId}/path`);
                const result = await response.json();

                if (result.success) {
                    const data = result.data;

                    // 更新監控狀態
                    this.monitorStatus.flowStatus = data.instance_status || item.status;
                    this.monitorStatus.activeCount = (data.active_nodes || []).length;
                    this.monitorStatus.completedCount = (data.completed_nodes || []).length;
                    this.monitorStatus.failedCount = (data.failed_nodes || []).length;
                    this.monitorStatus.waitingCount = (data.waiting_nodes || []).length;
                    this.monitorStatus.executionHistory = data.execution_history || [];

                    // 更新 workflow_tabs（主流程 + 子流程）
                    if (data.workflow_tabs && data.workflow_tabs.length > 0) {
                        this.workflowTabs = data.workflow_tabs;
                        // 快取每個流程的圖資料
                        data.workflow_tabs.forEach(tab => {
                            this.workflowGraphCache[tab.instance_id] = tab.graph;
                        });
                        // 如果尚未選擇 Tab，預設選擇主流程
                        if (!this.activeWorkflowTab) {
                            const mainTab = data.workflow_tabs.find(t => t.is_main);
                            if (mainTab) {
                                this.activeWorkflowTab = mainTab.instance_id;
                            } else if (data.workflow_tabs.length > 0) {
                                this.activeWorkflowTab = data.workflow_tabs[0].instance_id;
                            }
                        }
                    }

                    // 更新當前選中流程的節點樣式
                    this.updateCurrentTabNodeStyles(data);

                    console.log('執行快照已載入:', data);
                } else {
                    console.error('載入執行快照失敗:', result.error);
                }
            } catch (error) {
                console.error('載入執行快照錯誤:', error);
            }
        },

        updateCurrentTabNodeStyles(data) {
            if (!this.cyInstance) return;

            this.cyInstance.nodes().removeClass('node-running node-completed node-failed node-waiting');

            // 找出當前 Tab 對應的節點執行記錄
            const currentHistory = (data.execution_history || []).filter(
                h => h.workflow_instance_id === this.activeWorkflowTab
            );

            currentHistory.forEach(h => {
                const node = this.cyInstance.getElementById(h.node_id);
                if (node.length > 0) {
                    if (h.status === 'RUNNING') {
                        node.addClass('node-running');
                    } else if (h.status === 'SUCCESS') {
                        node.addClass('node-completed');
                    } else if (['FAILED', 'ERROR', 'TIMEOUT'].includes(h.status)) {
                        node.addClass('node-failed');
                    } else if (['WAITING', 'PENDING', 'INITIAL'].includes(h.status)) {
                        node.addClass('node-waiting');
                    }
                }
            });
        },

        async switchWorkflowTab(wf) {
            if (this.activeWorkflowTab === wf.instance_id) return;

            this.activeWorkflowTab = wf.instance_id;
            console.log('切換到流程:', wf.name);

            // 從快取載入流程圖
            const graphData = this.workflowGraphCache[wf.instance_id];
            if (graphData) {
                this.initializeCytoscape(graphData);
                // 重新載入快照以更新節點狀態
                if (this.monitoringExecution) {
                    await this.loadExecutionSnapshot(this.monitoringExecution);
                }
            } else {
                console.warn('找不到流程圖資料:', wf.name);
            }
        },

        initializeCytoscape(graphData) {
            if (!graphData) {
                console.error('無流程圖資料');
                return;
            }

            // 銷毀舊實例
            if (this.cyInstance) {
                this.cyInstance.destroy();
            }

            // 轉換 graph 資料為 Cytoscape 格式
            const elements = [];

            // 添加節點
            if (graphData.nodes) {
                graphData.nodes.forEach(node => {
                    elements.push({
                        data: {
                            id: node.id || node.data?.id,
                            label: node.data?.label || node.label || node.id,
                            type: node.data?.type || node.type
                        },
                        position: node.position || { x: 0, y: 0 }
                    });
                });
            }

            // 添加連線
            if (graphData.edges) {
                graphData.edges.forEach(edge => {
                    elements.push({
                        data: {
                            id: edge.id,
                            source: edge.source,
                            target: edge.target,
                            label: edge.label || edge.data?.label || ''
                        }
                    });
                });
            }

            // 建立 Cytoscape 實例
            this.cyInstance = cytoscape({
                container: document.getElementById('cy-monitor'),
                elements: elements,
                style: [
                    {
                        selector: 'node',
                        style: {
                            'background-color': '#E0E0E0',
                            'label': 'data(label)',
                            'text-valign': 'center',
                            'text-halign': 'center',
                            'font-size': '11px',
                            'width': 80,
                            'height': 36,
                            'border-width': 2,
                            'border-color': '#999',
                            'text-wrap': 'wrap',
                            'text-max-width': '70px'
                        }
                    },
                    {
                        selector: 'edge',
                        style: {
                            'width': 2,
                            'line-color': '#999',
                            'target-arrow-color': '#999',
                            'target-arrow-shape': 'triangle',
                            'curve-style': 'bezier',
                            'label': 'data(label)',
                            'font-size': '9px',
                            'text-rotation': 'autorotate'
                        }
                    },
                    // 執行中節點
                    {
                        selector: '.node-running',
                        style: {
                            'background-color': '#FFC107',
                            'border-color': '#FF9800',
                            'border-width': 3
                        }
                    },
                    // 已完成節點
                    {
                        selector: '.node-completed',
                        style: {
                            'background-color': '#4CAF50',
                            'border-color': '#388E3C',
                            'border-width': 2
                        }
                    },
                    // 失敗節點
                    {
                        selector: '.node-failed',
                        style: {
                            'background-color': '#F44336',
                            'border-color': '#D32F2F',
                            'border-width': 3
                        }
                    },
                    // 等待節點
                    {
                        selector: '.node-waiting',
                        style: {
                            'background-color': '#E3F2FD',
                            'border-color': '#2196F3',
                            'border-width': 3,
                            'border-style': 'dashed'
                        }
                    }
                ],
                layout: {
                    name: 'preset'
                },
                userZoomingEnabled: true,
                userPanningEnabled: true,
                boxSelectionEnabled: false
            });

            // 調整視圖以顯示所有節點
            this.cyInstance.fit(null, 50);

            console.log('Cytoscape 已初始化，節點數:', elements.filter(e => !e.data.source).length);
        },

        closeMonitorModal() {
            this.stopAutoRefresh();

            if (this.cyInstance) {
                this.cyInstance.destroy();
                this.cyInstance = null;
            }
            if (this.monitorFlowChartCy) {
                this.monitorFlowChartCy.destroy();
                this.monitorFlowChartCy = null;
            }

            // 重置狀態
            this.monitorStatus = {
                flowStatus: '-',
                activeCount: 0,
                completedCount: 0,
                failedCount: 0,
                waitingCount: 0,
                executionHistory: []
            };

            this.workflowTabs = [];
            this.activeWorkflowTab = null;
            this.workflowGraphCache = {};
            this.monitorPage = 'overview';
            this.monitorData = null;
            this.logSearchQuery = '';
            this.formDetail = null;
            this.showMonitorModal = false;
            this.monitoringExecution = null;

            // 清理表單檢視器
            if (this.formDetailViewer) {
                this.formDetailViewer.destroy();
                this.formDetailViewer = null;
            }
            this.cleanupFormBackground('formDetailViewer');
        },

        // 切換到表單內容頁籤
        async switchToFormContent() {
            this.monitorPage = 'formContent';
            if (!this.formDetail) {
                await this.loadFormDetail();
            } else {
                // 已載入，重新渲染表單
                this.$nextTick(() => this.renderFormViewer());
            }
        },

        // 切換到簽核歷史頁籤
        async switchToApprovalHistory() {
            this.monitorPage = 'approvals';
            if (!this.formDetail) {
                await this.loadFormDetail();
            }
        },

        // 切換到流程總圖頁籤（監控對話框內）
        async switchToMonitorFlowChart() {
            this.monitorPage = 'flowChart';
            // 等兩次 nextTick：第一次讓 Alpine 更新 x-show，第二次讓瀏覽器完成 layout
            await this.$nextTick();
            await this.$nextTick();

            const mainTab = this.workflowTabs.find(t => t.is_main) || this.workflowTabs[0];
            if (!mainTab) return;

            // graph 可能在 tab 物件上或在 workflowGraphCache 中
            const graph = mainTab.graph || this.workflowGraphCache[mainTab.instance_id];
            if (!graph) return;

            const codeToTab = {};
            this.workflowTabs.forEach(t => {
                if (t.workflow_code) {
                    if (!t.graph && this.workflowGraphCache[t.instance_id]) {
                        t.graph = this.workflowGraphCache[t.instance_id];
                    }
                    codeToTab[t.workflow_code] = t;
                }
            });

            const flatResult = this._fcFlattenGraph(graph, codeToTab, 0, '', null);
            const finalResult = this._fcApplyReplace(flatResult);
            this._fcApplyStatus(finalResult, { execution_history: this.monitorStatus.executionHistory });

            if (this.monitorFlowChartCy) {
                this.monitorFlowChartCy.destroy();
            }
            this.monitorFlowChartCy = this._fcRenderCytoscape('cy-monitor-flowchart', finalResult);
        },

        // 載入表單詳情
        async loadFormDetail() {
            if (!this.monitoringExecution) return;

            this.loadingFormDetail = true;
            try {
                const secureCode = this.monitoringExecution.secure_code;
                const response = await fetch(`/bp/api/form-center/form-detail/${secureCode}`);
                const result = await response.json();

                if (result.success) {
                    this.formDetail = result.data;
                    console.log('表單詳情載入完成:', this.formDetail);

                    // 如果在表單內容頁，渲染表單
                    if (this.monitorPage === 'formContent') {
                        this.$nextTick(() => this.renderFormViewer());
                    }
                } else {
                    console.error('載入表單詳情失敗:', result.error);
                    this.showToast('載入表單詳情失敗', 'error');
                }
            } catch (error) {
                console.error('載入表單詳情錯誤:', error);
                this.showToast('載入表單詳情錯誤', 'error');
            } finally {
                this.loadingFormDetail = false;
            }
        },

        // 渲染表單檢視器（監控模態框 - 表單內容頁籤）
        async renderFormViewer() {
            if (!this.formDetail?.schema) return;
            if (this.formDetailViewer) {
                this.formDetailViewer.destroy();
                this.formDetailViewer = null;
            }
            this.formDetailViewer = await this._renderFormReadOnly(
                'formDetailViewer',
                this.formDetail.schema,
                this.formDetail.form_data,
                this.formDetail.builder_config
            );
        },

        toggleAutoRefresh() {
            if (this.autoRefresh) {
                this.startAutoRefresh();
            } else {
                this.stopAutoRefresh();
            }
        },

        startAutoRefresh() {
            this.stopAutoRefresh();
            if (this.autoRefresh && this.monitoringExecution) {
                this.autoRefreshTimer = setInterval(() => {
                    this.refreshMonitor();
                }, 5000);
                console.log('自動刷新已啟動（每5秒）');
            }
        },

        stopAutoRefresh() {
            if (this.autoRefreshTimer) {
                clearInterval(this.autoRefreshTimer);
                this.autoRefreshTimer = null;
                console.log('自動刷新已停止');
            }
        },

        async refreshMonitor() {
            if (!this.monitoringExecution) return;
            await this.loadExecutionSnapshot(this.monitoringExecution);
        },

        async confirmForceEnd() {
            if (!confirm('確定要強制結束此流程？此操作將取消所有執行中的節點並結束流程。')) return;
            await this.executeForceEnd();
        },

        async executeForceEnd() {
            const secureCode = this.monitoringExecution?.secure_code;
            if (!secureCode) return;
            try {
                const res = await fetch(`/bp/api/form-center/force-end/${secureCode}`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': document.querySelector('meta[name="csrf-token"]')?.content
                    }
                });
                const result = await res.json();
                if (result.success) {
                    this.showToast('流程已強制結束', 'success');
                    await this.refreshMonitor();
                    this.loadTracking();
                    this.loadSigned();
                    this.loadHistory();
                    this.loadSignedHistory();
                } else {
                    this.showToast(result.error || '操作失敗', 'error');
                }
            } catch (e) {
                this.showToast('操作失敗', 'error');
            }
        },

        formatHistoryTime(dateStr) {
            return BkTime.format(dateStr, 'time');
        },
    };
}
