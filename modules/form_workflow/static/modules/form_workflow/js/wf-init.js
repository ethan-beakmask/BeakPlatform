/**
 * wf-init.js -- 權限檢查 + DOMContentLoaded 初始化
 * 從 workflow-main.js 拆分
 * 注意: 此檔案必須最後載入 (在所有 wf-*.js 之後)
 */

        // ==================== 權限檢查與 UI 控制 ====================
        function checkPermissionsAndUpdateUI() {
            // 檢查所有帶有 data-permission 屬性的元素
            document.querySelectorAll('[data-permission]').forEach(element => {
                const requiredPermissions = element.getAttribute('data-permission').split(',');
                const hasAccess = requiredPermissions.some(perm => AuthModule.hasPermission(perm.trim()));

                if (!hasAccess) {
                    element.style.display = 'none';
                    element.setAttribute('disabled', 'disabled');
                }
            });

            console.log('✅ 權限檢查完成');
        }

        // 初始化
        document.addEventListener('DOMContentLoaded', async function() {
            console.log('🚀 初始化 Workflow Designer');

            // 防止瀏覽器縮放和導航手勢
            document.addEventListener('wheel', function(e) {
                /* 調試用：記錄所有滾輪事件
                const wheelLog = {
                    timestamp: new Date().toISOString(),
                    deltaX: e.deltaX,
                    deltaY: e.deltaY,
                    deltaZ: e.deltaZ || 0,
                    deltaMode: e.deltaMode,
                    ctrlKey: e.ctrlKey,
                    metaKey: e.metaKey,
                    shiftKey: e.shiftKey,
                    altKey: e.altKey,
                    target: e.target.className || e.target.tagName,
                    clientX: e.clientX,
                    clientY: e.clientY
                };

                try {
                    const logs = JSON.parse(localStorage.getItem('workflow_wheel_logs') || '[]');
                    logs.push(wheelLog);
                    if (logs.length > 50) logs.shift();
                    localStorage.setItem('workflow_wheel_logs', JSON.stringify(logs));
                } catch (err) {
                    console.error('無法儲存滾輪日誌:', err);
                }
                */

                // 1. 防止 Ctrl/Cmd + 滾輪縮放
                if (e.ctrlKey || e.metaKey) {
                    e.preventDefault();
                    console.log('🛑 已阻止 Ctrl+滾輪縮放');
                    return;
                }

                // 2. 防止水平滾動觸發後退/前進手勢
                // 注意：只在明確是水平滾動時才阻止
                if (Math.abs(e.deltaX) > Math.abs(e.deltaY) && Math.abs(e.deltaX) > 10) {
                    // 明顯的水平滾動手勢，可能觸發導航
                    e.preventDefault();
                    console.warn('🛑 已阻止水平滾動手勢（可能觸發後退）', wheelLog);
                    return;
                }
            }, { passive: false });

            // 防止鍵盤縮放快捷鍵 (Ctrl +, Ctrl -, Ctrl 0)
            document.addEventListener('keydown', function(e) {
                if ((e.ctrlKey || e.metaKey) && (e.key === '+' || e.key === '-' || e.key === '=' || e.key === '0')) {
                    e.preventDefault();
                }
            });

            // 防止觸控板雙指縮放手勢
            document.addEventListener('gesturestart', function(e) {
                e.preventDefault();
            });

            document.addEventListener('gesturechange', function(e) {
                e.preventDefault();
            });

            document.addEventListener('gestureend', function(e) {
                e.preventDefault();
            });

            // 防止瀏覽器後退按鈕造成的意外離開（加入歷史記錄鎖定）
            // 使用更激進的方式阻止後退
            let preventBackCount = 0;

            // 持續推入歷史記錄
            window.history.pushState(null, '', window.location.href);

            window.addEventListener('popstate', function(e) {
                preventBackCount++;

                // 記錄詳細的後退資訊到 localStorage（用於調試）
                const backLog = {
                    timestamp: new Date().toISOString(),
                    preventCount: preventBackCount,
                    hasUnsavedChanges: hasUnsavedChanges,
                    url: window.location.href,
                    userAgent: navigator.userAgent,
                    screenSize: `${window.innerWidth}x${window.innerHeight}`,
                    scrollPosition: { x: window.scrollX, y: window.scrollY },
                    stackTrace: new Error().stack
                };

                try {
                    localStorage.setItem('workflow_back_log', JSON.stringify(backLog));
                } catch (e) {
                    console.error('無法儲存後退日誌:', e);
                }

                // 用戶按了後退按鈕
                console.warn(`⚠️ 偵測到後退操作 (第 ${preventBackCount} 次)`, backLog);

                // 立即推入新的歷史記錄，阻止後退
                window.history.pushState(null, '', window.location.href);

                // 只在第一次時詢問用戶
                if (preventBackCount === 1) {
                    // 檢查是否有未儲存的變更
                    if (hasUnsavedChanges) {
                        // 有未儲存的變更，顯示警告
                        const confirmLeave = confirm(__('您有未儲存的變更，確定要離開嗎？'));
                        if (confirmLeave) {
                            // 用戶確認離開
                            console.log('✅ 用戶確認離開');
                            window.location.href = window.__BP + '/forms/workflows';
                        } else {
                            console.log('❌ 用戶取消離開');
                            updateStatus(__('已取消離開，繼續編輯'), 'info');
                        }
                    } else {
                        // 沒有未儲存的變更，詢問是否要離開
                        const confirmLeave = confirm(__('確定要返回流程目錄嗎？'));
                        if (confirmLeave) {
                            console.log('✅ 用戶確認返回目錄');
                            window.location.href = window.__BP + '/forms/workflows';
                        } else {
                            console.log('❌ 用戶取消');
                            updateStatus(__('已取消返回，繼續編輯'), 'info');
                        }
                    }
                } else {
                    // 後續的後退嘗試，直接阻止並提示
                    if (preventBackCount === 2) {
                        updateStatus(__('🛡️ 後退已被阻擋（請使用上方的「放棄」按鈕返回目錄）'), 'warning');
                    }
                }
            });

            // 防止頁面關閉時丟失未儲存的變更
            window.addEventListener('beforeunload', function(e) {
                if (hasUnsavedChanges) {
                    e.preventDefault();
                    e.returnValue = ''; // Chrome 需要這行
                    return '您有未儲存的變更，確定要離開嗎？';
                }
            });

            /* 調試用：顯示後退日誌
            try {
                const backLog = localStorage.getItem('workflow_back_log');
                const wheelLogs = localStorage.getItem('workflow_wheel_logs');

                if (backLog) {
                    console.warn('📋 上次後退操作記錄:', JSON.parse(backLog));
                    const logData = JSON.parse(backLog);
                    updateStatus(`⚠️ 偵測到後退操作 (${new Date(logData.timestamp).toLocaleString()})`, 'warning');
                }

                if (wheelLogs) {
                    const logs = JSON.parse(wheelLogs);
                    if (logs.length > 0) {
                        console.warn('📋 水平滾動攔截記錄:', logs);
                    }
                }
            } catch (e) {
                console.error('讀取日誌失敗:', e);
            }

            // 調試函數
            window.showBackLogs = function() {
                try {
                    const backLog = localStorage.getItem('workflow_back_log');
                    const wheelLogs = localStorage.getItem('workflow_wheel_logs');

                    console.group('📋 導航日誌');
                    if (backLog) {
                        console.warn('後退操作:', JSON.parse(backLog));
                    } else {
                        console.log('無後退記錄');
                    }

                    if (wheelLogs) {
                        console.warn('水平滾動攔截:', JSON.parse(wheelLogs));
                    } else {
                        console.log('無滾輪記錄');
                    }
                    console.groupEnd();
                } catch (e) {
                    console.error('讀取日誌失敗:', e);
                }
            };

            window.clearBackLogs = function() {
                localStorage.removeItem('workflow_back_log');
                localStorage.removeItem('workflow_wheel_logs');
                console.log('✅ 已清除所有導航日誌');
            };

            window.exportWheelLogs = function() {
                try {
                    const logs = JSON.parse(localStorage.getItem('workflow_wheel_logs') || '[]');
                    if (logs.length === 0) {
                        console.log('無滾輪記錄');
                        return;
                    }

                    console.log(`📊 共 ${logs.length} 筆滾輪記錄`);
                    console.table(logs);

                    const last10 = logs.slice(-10);
                    console.group('🔍 最後 10 筆滾輪事件分析');
                    last10.forEach((log, i) => {
                        const ratio = Math.abs(log.deltaX) / Math.abs(log.deltaY);
                        const direction = Math.abs(log.deltaX) > Math.abs(log.deltaY) ? __('水平') : __('垂直');
                        console.log(`${i + 1}. ${direction} | deltaX:${log.deltaX.toFixed(2)} deltaY:${log.deltaY.toFixed(2)} | 比例:${ratio.toFixed(2)} | target:${log.target}`);
                    });
                    console.groupEnd();

                    const horizontalScrolls = logs.filter(log => Math.abs(log.deltaX) > Math.abs(log.deltaY));
                    if (horizontalScrolls.length > 0) {
                        console.warn(`⚠️ 發現 ${horizontalScrolls.length} 筆水平滾動事件:`, horizontalScrolls);
                    }
                } catch (e) {
                    console.error('匯出日誌失敗:', e);
                }
            };

            console.log('💡 調試提示: showBackLogs() | exportWheelLogs() | clearBackLogs()');
            */

            initCytoscape();
            window.cy = cy;  // 暴露給外部模組（formadapter-decisions.js 等）
            initDragAndDrop();
            initMinimap();

            // 初始化頁籤（預設顯示第一個）
            switchTab('canvas');

            // 載入底圖列表（必須在載入流程前完成，否則無法還原底圖設定）
            await loadBackgrounds();

            // 載入分類列表（必須 await，否則後續設定 category 時 option 尚未填入）
            await loadCategories();

            // 從 URL 取得參數
            const urlParams = new URLSearchParams(window.location.search);
            const workflowId = window.__DESIGNER_ID || urlParams.get('id');
            const isNewWorkflow = urlParams.get('new') === '1';
            const workflowName = urlParams.get('name') || '';
            const workflowCategory = urlParams.get('category') || '';
            const workflowDescription = urlParams.get('description') || '';

            // 判斷行為
            if (workflowId) {
                // 有 id，直接開啟舊檔案進行編輯
                const wasJustCreated = urlParams.get('created') === '1';
                console.log('📂 開啟現有流程:', workflowId, wasJustCreated ? '(剛建立)' : '');
                hasEverSaved = !wasJustCreated;  // 剛建立的標記為未儲存
                await enterDesignMode(workflowId);
                updateStatus(__('載入流程中...'));
            } else if (isNewWorkflow) {
                // 新增流程，直接進入設計模式
                console.log('✨ 新增流程');
                hasEverSaved = false;  // 新建流程，標記為從未儲存
                createNewWorkflowAndEnter(workflowName, workflowCategory, workflowDescription);
                updateStatus(__('新增流程中...'));
            } else {
                // 沒有參數，自動進入新增模式
                console.log('✨ 無參數，自動建立新流程');
                hasEverSaved = false;  // 新建流程，標記為從未儲存
                createNewWorkflowAndEnter('新流程', '', '');
                updateStatus(__('新增流程中...'));
            }

            // 等待 auth.js 載入後執行權限檢查
            setTimeout(() => {
                if (typeof AuthModule !== 'undefined' && AuthModule.isAuthenticated()) {
                    checkPermissionsAndUpdateUI();
                }
            }, 100);

            console.log('✅ 初始化完成');

            // 初始化流程樹
            initFlowTree();
        });

