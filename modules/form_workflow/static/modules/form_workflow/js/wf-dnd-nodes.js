/**
 * wf-dnd-nodes.js -- 拖放初始化、圖示對照表、節點/連線建立
 * 從 wf-core.js 拆分
 * 依賴: workflow-main.js, wf-cy-init.js
 */


        // 初始化拖拉功能
        function initDragAndDrop() {
            console.log('🎯 初始化拖放功能...');

            const paletteNodes = document.querySelectorAll('.palette-node');
            const cyContainer = document.getElementById('cy');

            console.log('  面板節點數:', paletteNodes.length);
            console.log('  畫布容器存在:', !!cyContainer);

            if (!cyContainer) {
                console.error('❌ 畫布容器不存在，無法綁定拖放事件');
                return;
            }

            // 綁定 dragstart 事件到左側節點
            let dragstartCount = 0;
            paletteNodes.forEach(node => {
                node.addEventListener('dragstart', function(e) {
                    const nodeType = this.getAttribute('data-node-type');
                    e.dataTransfer.setData('nodeType', nodeType);

                    // 測試節點使用特定的測試文字
                    let title = this.querySelector('.node-title').textContent;
                    if (nodeType === 'test_node_inside' || nodeType === 'test_node_outside') {
                        title = '測試圖形文字大小12345678';
                    } else if (nodeType === 'test_node_3colors') {
                        title = '三色圖案測試';
                    } else if (nodeType === 'test_node_image') {
                        title = '網路圖片測試';
                    } else if (nodeType === 'test_node_circle') {
                        title = '圓形遮罩測試';
                    }

                    e.dataTransfer.setData('nodeLabel', title);

                    // 取得節點圖示 - 優先從 data-node-icon 屬性，其次從 img 元素
                    let nodeIcon = this.getAttribute('data-node-icon') || '';
                    if (!nodeIcon) {
                        const imgElement = this.querySelector('.node-icon img');
                        if (imgElement && imgElement.src) {
                            nodeIcon = imgElement.src;
                        }
                    }
                    e.dataTransfer.setData('nodeIcon', nodeIcon);

                    console.log('🎯 拖拉開始:', nodeType, title, nodeIcon);
                });
                dragstartCount++;
            });
            console.log(`  ✓ 已綁定 ${dragstartCount} 個節點的 dragstart 事件`);

            // 綁定 dragover 事件到畫布
            cyContainer.addEventListener('dragover', function(e) {
                e.preventDefault();
            });
            console.log('  ✓ 已綁定畫布 dragover 事件');

            // 綁定 drop 事件到畫布
            cyContainer.addEventListener('drop', function(e) {
                e.preventDefault();
                console.log('🎯 Drop 事件觸發');

                const nodeType = e.dataTransfer.getData('nodeType');
                const nodeLabel = e.dataTransfer.getData('nodeLabel');
                const nodeIcon = e.dataTransfer.getData('nodeIcon');

                console.log('  節點類型:', nodeType);
                console.log('  節點標籤:', nodeLabel);
                console.log('  節點圖示:', nodeIcon);

                if (nodeType) {
                    const containerBB = cyContainer.getBoundingClientRect();
                    const mouseX = e.clientX - containerBB.left;
                    const mouseY = e.clientY - containerBB.top;

                    const pan = cy.pan();
                    const zoom = cy.zoom();

                    const modelX = (mouseX - pan.x) / zoom;
                    const modelY = (mouseY - pan.y) / zoom;

                    console.log('  添加節點到位置:', { x: modelX, y: modelY });
                    addNode(nodeType, nodeLabel, { x: modelX, y: modelY }, nodeIcon);
                } else {
                    console.warn('⚠️ 未取得節點類型');
                }
            });
            console.log('  ✓ 已綁定畫布 drop 事件');
            console.log('✅ 拖放功能初始化完成');
        }

        // Font Awesome class 到 SVG path 的映射表（使用 Font Awesome 6 的 SVG 路徑）
        const faIconSvgMap = {
            'fas fa-play': 'M73 39c-14.8-9.1-33.4-9.4-48.5-.9S0 62.6 0 80L0 432c0 17.4 9.4 33.4 24.5 41.9s33.7 8.1 48.5-.9L361 297c14.3-8.8 23-24.2 23-41s-8.7-32.2-23-41L73 39z',
            'fas fa-stop': 'M0 128C0 92.7 28.7 64 64 64L320 64c35.3 0 64 28.7 64 64l0 256c0 35.3-28.7 64-64 64L64 448c-35.3 0-64-28.7-64-64L0 128z',
            'fas fa-database': 'M448 80l0 48c0 44.2-100.3 80-224 80S0 172.2 0 128L0 80C0 35.8 100.3 0 224 0S448 35.8 448 80zM393.2 214.7c20.8-7.4 39.9-16.9 54.8-28.6L448 240c0 44.2-100.3 80-224 80S0 284.2 0 240l0-53.9c14.9 11.8 34 21.2 54.8 28.6C99.7 230.7 159.5 240 224 240s124.3-9.3 169.2-25.3zM0 346.1c14.9 11.8 34 21.2 54.8 28.6C99.7 390.7 159.5 400 224 400s124.3-9.3 169.2-25.3c20.8-7.4 39.9-16.9 54.8-28.6l0 85.9c0 44.2-100.3 80-224 80S0 476.2 0 432l0-85.9z',
            'fas fa-ban': 'M367.2 412.5L99.5 144.8C77.1 176.1 64 214.5 64 256c0 106 86 192 192 192c41.5 0 79.9-13.1 111.2-35.5zm45.3-45.3C434.9 335.9 448 297.5 448 256c0-106-86-192-192-192c-41.5 0-79.9 13.1-111.2 35.5L412.5 367.2zM0 256a256 256 0 1 1 512 0A256 256 0 1 1 0 256z',
            'fas fa-sitemap': 'M80 48a48 48 0 1 1 96 0A48 48 0 1 1 80 48zm64 193.7l0 65.1 51.2 35.8c11.3 7.9 13.9 23.5 5.9 34.8s-23.5 13.9-34.8 5.9L128 355.6l-38.4 26.9c-11.3 7.9-26.9 5.3-34.8-5.9s-5.3-26.9 5.9-34.8L112 306.7l0-65.1c-49.3-12.5-85.8-56.9-85.8-109.6C26.2 59.1 85.1 0 157.9 0s131.7 59.1 131.7 132C289.6 184.7 253.1 229.1 203.8 241.7z',
            'fas fa-clock': 'M256 0a256 256 0 1 1 0 512A256 256 0 1 1 256 0zM232 120l0 136c0 8 4 15.5 10.7 20l96 64c11 7.4 25.9 4.4 33.3-6.7s4.4-25.9-6.7-33.3L280 243.2 280 120c0-13.3-10.7-24-24-24s-24 10.7-24 24z',
            'fas fa-code-branch': 'M80 104a24 24 0 1 0 0-48 24 24 0 1 0 0 48zm80-24c0 32.8-19.7 61-48 73.3l0 87.8c18.8-10.9 40.7-17.1 64-17.1l96 0c35.3 0 64-28.7 64-64l0-6.7C307.7 141 288 112.8 288 80c0-44.2 35.8-80 80-80s80 35.8 80 80c0 32.8-19.7 61-48 73.3l0 6.7c0 70.7-57.3 128-128 128l-96 0c-35.3 0-64 28.7-64 64l0 6.7c28.3 12.3 48 40.5 48 73.3c0 44.2-35.8 80-80 80s-80-35.8-80-80c0-32.8 19.7-61 48-73.3l0-6.7 0-198.7C19.7 141 0 112.8 0 80C0 35.8 35.8 0 80 0s80 35.8 80 80zm232 0a24 24 0 1 0 -48 0 24 24 0 1 0 48 0zM80 456a24 24 0 1 0 0-48 24 24 0 1 0 0 48z',
            'fas fa-compress-arrows-alt': 'M436 192L392 192l-24 0 0-24 0-44 0-24 24 0 44 0 24 0 0 48-24 0-20 0 0 20 0 24-24 0 0 24 24 0 0 24 0 44 0 24-24 0-44 0-24 0 0-48 24 0 20 0 0-20 0-24 24 0 0-24zm-360 0l24 0 0 24-24 0 0 24 0 20-20 0-24 0 0 48 24 0 44 0 24 0 0-24 0-44 0-24-24 0 0-24 24 0 0-24 0-20 20 0 24 0 0-48-24 0-44 0-24 0 0 24 0 44 0 24z',
            'fas fa-clipboard-list': 'M280 64l40 0c35.3 0 64 28.7 64 64l0 320c0 35.3-28.7 64-64 64L64 512c-35.3 0-64-28.7-64-64L0 128C0 92.7 28.7 64 64 64l40 0 9.6 0C121 27.5 153.3 0 192 0s71 27.5 78.4 64l9.6 0zM64 112c-8.8 0-16 7.2-16 16l0 320c0 8.8 7.2 16 16 16l256 0c8.8 0 16-7.2 16-16l0-320c0-8.8-7.2-16-16-16l-16 0 0 24c0 13.3-10.7 24-24 24l-88 0-88 0c-13.3 0-24-10.7-24-24l0-24-16 0zm128-8a24 24 0 1 0 0-48 24 24 0 1 0 0 48z',
            'fas fa-calendar-times': 'M128 0c17.7 0 32 14.3 32 32l0 32 128 0 0-32c0-17.7 14.3-32 32-32s32 14.3 32 32l0 32 48 0c26.5 0 48 21.5 48 48l0 48L0 160l0-48C0 85.5 21.5 64 48 64l48 0 0-32c0-17.7 14.3-32 32-32zM0 192l448 0 0 272c0 26.5-21.5 48-48 48L48 512c-26.5 0-48-21.5-48-48L0 192z',
            'fas fa-envelope': 'M48 64C21.5 64 0 85.5 0 112c0 15.1 7.1 29.3 19.2 38.4L236.8 313.6c11.4 8.5 27 8.5 38.4 0L492.8 150.4c12.1-9.1 19.2-23.3 19.2-38.4c0-26.5-21.5-48-48-48L48 64zM0 176L0 384c0 35.3 28.7 64 64 64l384 0c35.3 0 64-28.7 64-64l0-208L294.4 339.2c-22.8 17.1-54 17.1-76.8 0L0 176z',
            'fas fa-copy': 'M208 0L332.1 0c12.7 0 24.9 5.1 33.9 14.1l67.9 67.9c9 9 14.1 21.2 14.1 33.9L448 336c0 26.5-21.5 48-48 48l-192 0c-26.5 0-48-21.5-48-48l0-288c0-26.5 21.5-48 48-48zM48 128l80 0 0 64-64 0 0 256 192 0 0-32 64 0 0 48c0 26.5-21.5 48-48 48L48 512c-26.5 0-48-21.5-48-48L0 176c0-26.5 21.5-48 48-48z',
            'fas fa-calculator': 'M64 0C28.7 0 0 28.7 0 64L0 448c0 35.3 28.7 64 64 64l256 0c35.3 0 64-28.7 64-64l0-384c0-35.3-28.7-64-64-64L64 0zM96 64l192 0c17.7 0 32 14.3 32 32l0 32c0 17.7-14.3 32-32 32L96 160c-17.7 0-32-14.3-32-32l0-32c0-17.7 14.3-32 32-32z',
            'fas fa-bell': 'M224 0c-17.7 0-32 14.3-32 32l0 19.2C119 66 64 130.6 64 208l0 18.8c0 47-17.3 92.4-48.5 127.6l-7.4 8.3c-8.4 9.4-10.4 22.9-5.3 34.4S19.4 416 32 416l384 0c12.6 0 24-7.4 29.2-18.9s3.1-25-5.3-34.4l-7.4-8.3C401.3 319.2 384 273.9 384 226.8l0-18.8c0-77.4-55-142-128-156.8L256 32c0-17.7-14.3-32-32-32zm45.3 493.3c12-12 18.7-28.3 18.7-45.3l-64 0-64 0c0 17 6.7 33.3 18.7 45.3s28.3 18.7 45.3 18.7s33.3-6.7 45.3-18.7z',
            'fas fa-route': 'M512 96c0 50.2-59.1 125.1-84.6 155c-3.8 4.4-9.4 6.1-14.5 5L320 256c-17.7 0-32 14.3-32 32s14.3 32 32 32l96 0c53 0 96 43 96 96s-43 96-96 96l-276.4 0c8.7-9.9 19.3-22.6 30-36.8c6.3-8.4 12.8-17.6 19-27.2L416 448c17.7 0 32-14.3 32-32s-14.3-32-32-32l-96 0c-53 0-96-43-96-96s43-96 96-96l39.8 0c-21-31.5-39.8-67.7-39.8-96c0-53 43-96 96-96s96 43 96 96z',
            'fas fa-plug': 'M96 0C78.3 0 64 14.3 64 32l0 96 64 0 0-96c0-17.7-14.3-32-32-32zm0 256l64 0 0-64-64 0 0 64zM320 0c-17.7 0-32 14.3-32 32l0 96 64 0 0-96c0-17.7-14.3-32-32-32zm32 256l0-64-64 0 0 64 64 0zm88-32c13.3 0 24-10.7 24-24s-10.7-24-24-24l-40 0 0-48c0-44.2-35.8-80-80-80l-192 0c-44.2 0-80 35.8-80 80l0 48-40 0c-13.3 0-24 10.7-24 24s10.7 24 24 24l40 0 0 80c0 80.2 59 146.6 136 158.2l0 49.8 80 0 0-49.8c77-11.6 136-78 136-158.2l0-80 40 0z',
            'fas fa-cog': 'M495.9 166.6c3.2 8.7 .5 18.4-6.4 24.6l-43.3 39.4c1.1 8.3 1.7 16.8 1.7 25.4s-.6 17.1-1.7 25.4l43.3 39.4c6.9 6.2 9.6 15.9 6.4 24.6c-4.4 11.9-9.7 23.3-15.8 34.3l-4.7 8.1c-6.6 11-14 21.4-22.1 31.2c-5.9 7.2-15.7 9.6-24.5 6.8l-55.7-17.7c-13.4 10.3-28.2 18.9-44 25.4l-12.5 57.1c-2 9.1-9 16.3-18.2 17.8c-13.8 2.3-28 3.5-42.5 3.5s-28.7-1.2-42.5-3.5c-9.2-1.5-16.2-8.7-18.2-17.8l-12.5-57.1c-15.8-6.5-30.6-15.1-44-25.4L83.1 425.9c-8.8 2.8-18.6 .3-24.5-6.8c-8.1-9.8-15.5-20.2-22.1-31.2l-4.7-8.1c-6.1-11-11.4-22.4-15.8-34.3c-3.2-8.7-.5-18.4 6.4-24.6l43.3-39.4C64.6 273.1 64 264.6 64 256s.6-17.1 1.7-25.4L22.4 191.2c-6.9-6.2-9.6-15.9-6.4-24.6c4.4-11.9 9.7-23.3 15.8-34.3l4.7-8.1c6.6-11 14-21.4 22.1-31.2c5.9-7.2 15.7-9.6 24.5-6.8l55.7 17.7c13.4-10.3 28.2-18.9 44-25.4l12.5-57.1c2-9.1 9-16.3 18.2-17.8C227.3 1.2 241.5 0 256 0s28.7 1.2 42.5 3.5c9.2 1.5 16.2 8.7 18.2 17.8l12.5 57.1c15.8 6.5 30.6 15.1 44 25.4l55.7-17.7c8.8-2.8 18.6-.3 24.5 6.8c8.1 9.8 15.5 20.2 22.1 31.2l4.7 8.1c6.1 11 11.4 22.4 15.8 34.3zM256 336a80 80 0 1 0 0-160 80 80 0 1 0 0 160z'
        };

        // 將 SVG path 轉換��� data URL
        function getSvgDataUrl(iconClass, color = '#333333') {
            const path = faIconSvgMap[iconClass];
            if (!path) return '';

            // 根據圖示調整 viewBox（大多數 FA 圖示是 512x512）
            const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><path fill="${color}" d="${path}"/></svg>`;
            return 'data:image/svg+xml,' + encodeURIComponent(svg);
        }

        // Font Awesome class 到 Unicode 的映射表（備用）
        const faIconMap = {
            'fas fa-play': '\uf04b',
            'fas fa-stop': '\uf04d',
            'fas fa-database': '\uf1c0',
            'fas fa-ban': '\uf05e',
            'fas fa-sitemap': '\uf0e8',
            'fas fa-clock': '\uf017',
            'fas fa-code-branch': '\uf126',
            'fas fa-compress-arrows-alt': '\uf78c',
            'fas fa-clipboard-list': '\uf46d',
            'fas fa-calendar-times': '\uf273',
            'fas fa-envelope': '\uf0e0',
            'fas fa-copy': '\uf0c5',
            'fas fa-calculator': '\uf1ec',
            'fas fa-circle-dot': '\uf192',
            'fas fa-file-signature': '\uf573',
            'fas fa-bell': '\uf0f3',
            'fas fa-route': '\uf4d7',
            'fas fa-plug': '\uf1e6',
            'fas fa-cog': '\uf013',
            'fas fa-cogs': '\uf085'
        };

        // 新增節點
        function addNode(type, label, position, icon) {
            pushUndoState();
            type = normalizeNodeType(type) || type;
            nodeCounter++;
            const nodeId = `node-${type}-${nodeCounter}`;

            // 判斷 icon 是本地 SVG 路徑還是 Font Awesome class
            let iconUrl = '';
            if (icon) {
                if (icon.startsWith('/bp/static/') || icon.startsWith('http')) {
                    // 已經是 URL 路徑，直接使用
                    iconUrl = icon;
                } else {
                    // 舊的 Font Awesome class，使用舊方法轉換（向後兼容）
                    iconUrl = getSvgDataUrl(icon, '#333333');
                }
            }

            const newNode = cy.add({
                data: {
                    id: nodeId,
                    label: label,           // 顯示名稱（預設為節點類型的中文名）
                    type: type,
                    icon: icon || '',       // 保存 icon 路徑或 class
                    iconUrl: iconUrl,       // 保存實際的圖示 URL
                    description: '',        // 描述預設為空
                    config: {}
                },
                position: position
            });

            // 套用圖示背景
            if (iconUrl) {
                newNode.style({
                    'background-image': iconUrl,
                    'background-fit': 'contain',
                    'background-clip': 'none'
                });
            }

            // 套用全域邊框隱藏 class
            if (!globalNodeBorder) {
                newNode.addClass('no-border');
            }

            updateStatus(`已新增節點: ${label} (${nodeId})`);

            // 自動選取新節點並切換設定面板
            cy.elements().unselect();
            newNode.select();
            showNodeInfo(newNode);
        }

        // 建立連線
        function createEdge(sourceNode, targetNode) {
            // 驗證 1：防止自連接
            if (sourceNode.id() === targetNode.id()) {
                updateStatus('❌ 不能連接節點到自己', 'error');
                return false;
            }

            // 驗證 2：防止異類連接（node ↔ group）
            const sourceIsCompound = isGroupNode(sourceNode);
            const targetIsCompound = isGroupNode(targetNode);

            // 檢查是否為異類連接
            if (sourceIsCompound !== targetIsCompound) {
                updateStatus('❌ 不能在節點與群組之間建立連線', 'error');
                return false;
            }

            // 通過驗證，建立連線
            pushUndoState();
            edgeCounter++;
            const edgeId = `edge-${edgeCounter}`;

            cy.add({
                data: {
                    id: edgeId,
                    source: sourceNode.id(),
                    target: targetNode.id(),
                    label: ''
                }
            });

            // 更新線段選擇器
            updateEdgeSelector();
            return true;
        }
