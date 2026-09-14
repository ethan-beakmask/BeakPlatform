/* global Alpine, Formio, BkI18n, __ */
function irDesigner() {
    const BP = window.__BP || '';
    const apiBase = `${BP}/api/nocode-builder`;

    function tr(text, params) {
        return window.__ ? window.__(text, params) : text;
    }

    function clone(value) {
        return JSON.parse(JSON.stringify(value));
    }

    function slugify(text) {
        return String(text || 'page')
            .toLowerCase()
            .replace(/[^a-z0-9]+/g, '-')
            .replace(/^-+|-+$/g, '')
            .replace(/^[^a-z]+/, '') || 'page';
    }

    function csrfToken() {
        const meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.content : '';
    }

    return {
        secureCode: '',
        designerUrl: '',
        previewUrl: '',
        pageName: '',
        pageTitleZh: '',
        doc: { ir_version: 3, page: { id: 'page', title_i18n: { 'zh-TW': '' }, widgets: [] } },
        meta: { resources: [], actions: [], portal_actions: [] },
        subSystems: [],
        dataScope: '',
        mountedSubSystem: '',
        formMappings: [],
        formMappingsLoadFailed: false,
        siteMapNodes: [],
        siteMapLoaded: false,
        siteMapError: '',
        menuBackgrounds: [],
        menuBackgroundsLoaded: false,
        menuBackgroundError: '',
        menuUploadingBackground: false,
        previewGroup: '',
        previewLevel: '',
        portalOrgLoaded: false,
        portalOrgScope: '',
        portalGroups: [],
        portalLevels: [],
        portalPermissions: [],
        selectedId: '',
        activeWidget: null,
        engine: 'flow',
        gridEditor: null,
        freeGrid: null,
        selectedZoneId: '',
        canvasMeta: {},
        _zoneGeometry: {},   // zone id -> 幾何快照，供 zone 消失時判斷元件由誰接手
        errors: [],
        showIssueModal: false,
        saveTemplateModal: {
            open: false,
            saving: false,
            error: '',
            name: '',
            description: '',
            category: '常用',
            scope: 'sub_system',
        },
        sharedComponents: [],
        sharedComponentsLoaded: false,
        sharedComponentsError: '',
        sharedComponentsScope: '',
        sharedComponentEditor: {
            open: false,
            saving: false,
            error: '',
            source: null,
            draft: null,
            dirty: false,
        },
        toast: { show: false, message: '' },
        _toastTimer: null,
        dirty: false,
        savedSnapshot: '',
        dragType: '',
        counters: {},
        showFormModal: false,
        formBuilder: null,
        formBuilderWidget: null,
        // label 一律「英文型別 中文名」並列，方便對照 layout_json 裡的 type
        palette: [
            { type: 'layout', label: `layout ${tr('版面')}` },
            { type: 'text', label: `text ${tr('文字')}` },
            { type: 'menu', label: `menu ${tr('選單')}` },
            { type: 'table', label: `table ${tr('表格')}` },
            { type: 'detail', label: `detail ${tr('明細')}` },
            { type: 'master_detail', label: `master_detail ${tr('主細表')}` },
            { type: 'actions', label: `actions ${tr('動作')}` },
            { type: 'form', label: `form ${tr('表單')}` },
        ],
        accessActions: [
            { key: 'read', label: tr('檢視') },
            { key: 'create', label: tr('新增') },
            { key: 'update', label: tr('編輯') },
            { key: 'delete', label: tr('刪除') },
        ],
        formAccessActions: [
            { key: 'create', label: tr('新增') },
        ],
        masterDetailAccessActions: [
            { key: 'create', label: tr('新增') },
            { key: 'update', label: tr('編輯') },
        ],
        actionsAccessActions: [
            { key: 'read', label: tr('檢視') },
            { key: 'update', label: tr('執行動作') },
        ],
        menuSystemLinks: [
            { link: 'login', label: tr('登入') },
            { link: 'register', label: tr('註冊') },
            { link: 'logout', label: tr('登出') },
        ],
        menuColorFields: [
            { key: 'bg_color', label: tr('背景色') },
            { key: 'item_bg_color', label: tr('項目背景色') },
            { key: 'item_text_color', label: tr('項目文字色') },
            { key: 'item_hover_bg_color', label: tr('滑過背景色') },
            { key: 'item_hover_text_color', label: tr('滑過文字色') },
            { key: 'accent_color', label: tr('強調色') },
            { key: 'border_color', label: tr('框線色') },
        ],
        engineOptions: [
            { code: 'flow', name: tr('流式') },
            { code: 'grid', name: tr('矩陣') },
            { code: 'free', name: tr('自由') },
        ],
        overflowOptions: [
            { code: 'auto', name: tr('內部捲動') },
            { code: 'visible', name: tr('不裁切') },
        ],

        async init() {
            this.$watch('previewGroup', () => this.persistPreviewIdentity());
            this.$watch('previewLevel', () => this.persistPreviewIdentity());
            const cfg = window.__IR_DESIGNER_CONFIG || {};
            this.secureCode = cfg.secureCode || '';
            this.designerUrl = cfg.designerUrl || '';
            this.previewUrl = cfg.previewUrl || '';
            await Promise.all([this.loadPage(), this.loadSubSystems(), this.loadMeta(this.dataScope), this.loadFormMappings()]);
            await this.detectPortalScope();
            await this.ensurePortalOrg();
            await this.loadSharedComponents();
            this.syncCounters();
            this.initLayoutEngineState();
            await Alpine.nextTick();
            this.mountGridEditor();
            this.mountFreeGrid();
            this.savedSnapshot = this.snapshot();
        },

        async loadPage() {
            const res = await fetch(`${apiBase}/pages/${this.secureCode}`);
            const data = await res.json();
            if (!data.success) {
                this.errors = [{ path: '', message: data.error || tr('載入失敗') }];
                return;
            }
            this.pageName = data.data.name || '';
            this.mountedSubSystem = data.data.sub_system_secure_code || '';
            const layout = data.data.layout_json || {};
            if (layout.ir_version === 3 && layout.page) {
                this.doc = clone(layout);
                this.normalizeWidgets(this.doc.page.widgets || []);
            } else {
                this.doc = {
                    ir_version: 3,
                    page: {
                        id: slugify(data.data.name || 'page').slice(0, 64),
                        title_i18n: { 'zh-TW': data.data.name || '' },
                        widgets: [],
                    },
                };
            }
            this.pageTitleZh = this.doc.page.title_i18n['zh-TW'] || this.pageName || '';
        },

        normalizeWidgets(widgets) {
            for (const widget of widgets) {
                if (widget.shared_ref) continue;
                if (widget.type === 'table' && !widget.default_sort) {
                    const first = (widget.binding && widget.binding.fields && widget.binding.fields[0]) || '';
                    widget.default_sort = { field: first, dir: 'asc' };
                }
                if (widget.type === 'table') this.normalizeMasks(widget.columns || []);
                if (widget.type === 'detail') this.normalizeMasks(widget.fields || []);
                if (widget.type === 'master_detail') this.normalizeMasterDetailWidget(widget);
                if (widget.type === 'menu') this.normalizeMenuWidget(widget);
                if (widget.type === 'layout') this.normalizeWidgets(widget.children || []);
            }
        },

        normalizeMenuWidget(widget) {
            if (!widget.title_i18n) widget.title_i18n = { 'zh-TW': '', en: '' };
            if (widget.title_i18n.en === undefined) widget.title_i18n.en = '';
            if (!Array.isArray(widget.items)) widget.items = [];
            const normalizeItems = (items) => {
                for (let index = (items || []).length - 1; index >= 0; index -= 1) {
                    const item = items[index];
                    if (!item || !['node', 'system'].includes(item.kind)) {
                        items.splice(index, 1);
                        continue;
                    }
                    if (item && item.kind === 'node') {
                        if (!Array.isArray(item.children)) item.children = [];
                        normalizeItems(item.children);
                    } else if (item && item.kind === 'system') {
                        delete item.children;
                    }
                }
            };
            normalizeItems(widget.items);
            widget.source_mode = widget.source_mode === 'auto' ? 'auto' : 'manual';
            widget.include_system_links = Boolean(widget.include_system_links);
            if (!widget.orientation) widget.orientation = 'vertical';
            if (!Number.isInteger(widget.item_gap)) widget.item_gap = 6;
            if (widget.hover_expand === undefined) widget.hover_expand = true;
            if (!widget.nav_source) widget.nav_source = 'self';
            if (!widget.nav_key) widget.nav_key = 'nav';
            if (!widget.style || typeof widget.style !== 'object' || Array.isArray(widget.style)) {
                widget.style = {};
            }
            const styleDefaults = {
                bg_color: '#ffffff',
                item_bg_color: '#ffffff',
                item_text_color: '#333333',
                item_hover_bg_color: '#e9ecef',
                item_hover_text_color: '#333333',
                accent_color: '#e67e22',
                border_color: '#dddddd',
                border_width: 1,
                border_radius: 4,
                background_file: '',
                background_size: 'cover',
                background_repeat: 'no-repeat',
                background_position: 'center',
            };
            for (const [key, value] of Object.entries(styleDefaults)) {
                if (widget.style[key] === undefined) widget.style[key] = value;
            }
            for (const key of ['bg_color', 'item_bg_color', 'item_text_color', 'item_hover_bg_color', 'item_hover_text_color', 'accent_color', 'border_color']) {
                if (!/^#[0-9a-fA-F]{6}$/.test(widget.style[key] || '')) widget.style[key] = styleDefaults[key];
            }
            const borderWidth = Number.parseInt(widget.style.border_width, 10);
            const borderRadius = Number.parseInt(widget.style.border_radius, 10);
            widget.style.border_width = Number.isFinite(borderWidth) ? Math.min(8, Math.max(0, borderWidth)) : 1;
            widget.style.border_radius = Number.isFinite(borderRadius) ? Math.min(32, Math.max(0, borderRadius)) : 4;
            if (!['cover', 'contain', 'auto'].includes(widget.style.background_size)) widget.style.background_size = 'cover';
            if (!['no-repeat', 'repeat', 'repeat-x', 'repeat-y'].includes(widget.style.background_repeat)) widget.style.background_repeat = 'no-repeat';
            if (!['center', 'top', 'bottom', 'left', 'right'].includes(widget.style.background_position)) widget.style.background_position = 'center';
        },

        normalizeMasterDetailWidget(widget) {
            if (!widget.master) widget.master = { binding: this.emptyBinding(), fields: [] };
            if (!widget.master.binding) widget.master.binding = this.emptyBinding();
            if (!Array.isArray(widget.master.binding.fields)) widget.master.binding.fields = [];
            if (!Array.isArray(widget.master.fields)) widget.master.fields = [];
            if (!widget.detail) widget.detail = { binding: this.emptyBinding(), columns: [] };
            if (!widget.detail.binding) widget.detail.binding = this.emptyBinding();
            if (!Array.isArray(widget.detail.binding.fields)) widget.detail.binding.fields = [];
            if (!Array.isArray(widget.detail.columns)) widget.detail.columns = [];
            this.normalizeMasks(widget.master.fields);
            this.normalizeMasks(widget.detail.columns);
            if (widget.master.editable !== true) delete widget.master.editable;
            if (!widget.master.layout_columns) delete widget.master.layout_columns;
            if (!widget.detail.foreign_key) delete widget.detail.foreign_key;
            if (!widget.detail.page_size) delete widget.detail.page_size;
            if (widget.history && widget.history.enabled !== true) delete widget.history;
            if (widget.history) {
                if (!widget.history.page_size) delete widget.history.page_size;
                if (widget.history.default_sort && !widget.history.default_sort.field) delete widget.history.default_sort;
            }
        },

        normalizeMasks(specs) {
            for (const spec of specs || []) {
                const mask = spec.mask;
                if (!mask || !mask.type) {
                    delete spec.mask;
                    continue;
                }
                if (!['partial', 'full', 'email', 'phone'].includes(mask.type)) {
                    spec.mask = { type: 'full' };
                } else if (mask.type === 'partial') {
                    spec.mask = {
                        type: 'partial',
                        keep_head: this.clampMaskParam(mask.keep_head, 0),
                        keep_tail: this.clampMaskParam(mask.keep_tail, 4),
                    };
                } else {
                    spec.mask = { type: mask.type };
                }
                if (Object.prototype.hasOwnProperty.call(spec, 'sortable')) spec.sortable = false;
            }
        },

        normalizeAccessMatrix(widgets) {
            for (const widget of widgets || []) {
                const matrix = widget.access_matrix;
                if (matrix) {
                    for (const action of Object.keys(matrix)) {
                        const rule = matrix[action];
                        if (!rule || Object.keys(rule).length === 0) {
                            delete matrix[action];
                            continue;
                        }
                        if (!Array.isArray(rule.required_permissions) || rule.required_permissions.length === 0) {
                            delete matrix[action];
                            continue;
                        }
                        rule.match_mode = rule.match_mode === 'all' ? 'all' : 'any';
                    }
                }
                if (matrix && Object.keys(matrix).length === 0) {
                    delete widget.access_matrix;
                }
                if (widget.type === 'layout') this.normalizeAccessMatrix(widget.children || []);
            }
        },

        normalizeWidgetMasks(widgets) {
            for (const widget of widgets || []) {
                // 引用共用元件的 widget 只留 id/type/shared_ref/access_matrix，
                // 補預設值會把 items、title_i18n 這類無效設定寫回頁面 IR
                if (widget.shared_ref) continue;
                if (widget.type === 'table') this.normalizeMasks(widget.columns || []);
                if (widget.type === 'detail') this.normalizeMasks(widget.fields || []);
                if (widget.type === 'master_detail') this.normalizeMasterDetailWidget(widget);
                if (widget.type === 'menu') this.normalizeMenuWidget(widget);
                if (widget.type === 'layout') this.normalizeWidgetMasks(widget.children || []);
            }
        },

        normalizeActionButtons(widgets) {
            for (const widget of widgets || []) {
                if (widget.type === 'actions') {
                    for (const btn of widget.buttons || []) {
                        if (!btn.permission) delete btn.permission;
                    }
                }
                if (widget.type === 'layout') this.normalizeActionButtons(widget.children || []);
            }
        },

        async loadMeta(scope = '') {
            try {
                const url = scope
                    ? `${BP}/api/pageir/meta?sub_system=${encodeURIComponent(scope)}`
                    : `${BP}/api/pageir/meta`;
                const res = await fetch(url);
                const data = await res.json();
                if (data.success) {
                    this.meta = {
                        resources: scope ? (data.portal_resources || []) : (data.resources || []),
                        actions: data.actions || [],
                        portal_actions: data.portal_actions || [],
                    };
                }
            } catch (err) {
                this.errors = [{ path: '', message: tr('Meta 載入失敗') }];
            }
        },

        async loadFormMappings() {
            try {
                const res = await fetch(`${BP}/api/mappings?is_published=true&is_archived=false`);
                const data = await res.json();
                if (!res.ok || !data.success) {
                    this.formMappings = [];
                    this.formMappingsLoadFailed = true;
                    return;
                }
                this.formMappings = Array.isArray(data.data) ? data.data : [];
                this.formMappingsLoadFailed = false;
            } catch (err) {
                this.formMappings = [];
                this.formMappingsLoadFailed = true;
            }
        },

        async loadSubSystems() {
            try {
                const res = await fetch(`${BP}/api/nocode-builder/sub-systems`);
                const data = await res.json();
                if (!data.success) {
                    this.subSystems = [];
                    console.warn('[IR Designer] sub-systems load failed:', data.error || data);
                    return;
                }
                this.subSystems = (data.data || []).map((item) => ({
                    secure_code: item.secure_code,
                    name: item.name,
                })).filter((item) => item.secure_code);
            } catch (err) {
                this.subSystems = [];
                console.warn('[IR Designer] sub-systems load failed:', err);
            }
        },

        async onScopeChange() {
            this.resetPreviewIdentity();
            this.resetSiteMap();
            await this.loadMeta(this.dataScope);
            await this.ensurePortalOrg();
            await this.loadSharedComponents(true);
            if (this.selectedWidget && this.selectedWidget.type === 'menu') {
                await this.loadSiteMap();
            }
        },

        siteMapScope() {
            return this.dataScope || this.mountedSubSystem || '';
        },

        canManageSharedComponents() {
            return !window.BkCaps || window.BkCaps.can('nocode_builder.manage');
        },

        showZonePanel() {
            return !this.sharedComponentEditor.open
                && this.engine !== 'flow'
                && !!this.selectedZoneId
                && !!this.selectedZoneMeta();
        },

        async loadSharedComponents(force = false) {
            const scope = this.siteMapScope();
            this.sharedComponentsError = '';
            if (!scope || !window.BkSharedComponent) {
                this.sharedComponents = [];
                this.sharedComponentsLoaded = false;
                this.sharedComponentsScope = '';
                return;
            }
            if (!force && this.sharedComponentsLoaded && this.sharedComponentsScope === scope) return;
            try {
                this.sharedComponents = await window.BkSharedComponent.list(scope) || [];
                this.sharedComponentsLoaded = true;
                this.sharedComponentsScope = scope;
            } catch (err) {
                this.sharedComponents = [];
                this.sharedComponentsLoaded = false;
                this.sharedComponentsScope = '';
                this.sharedComponentsError = err.message || tr('載入共用元件失敗');
            }
        },

        sharedComponentByRef(ref) {
            return (this.sharedComponents || []).find((row) => row.secure_code === ref) || null;
        },

        sharedComponentsForWidget(widget) {
            if (!widget) return [];
            return (this.sharedComponents || []).filter((row) => row.widget_type === widget.type);
        },

        selectedSharedComponentName(widget) {
            const row = this.sharedComponentByRef(widget && widget.shared_ref);
            return row && row.widget_json ? row.name : '';
        },

        resetSiteMap() {
            this.siteMapNodes = [];
            this.siteMapLoaded = false;
            this.siteMapError = '';
        },

        flattenSiteMap(nodes) {
            const rows = [];
            const sortNodes = (items) => [...(items || [])].sort((a, b) => {
                const orderA = Number(a && a.display_order);
                const orderB = Number(b && b.display_order);
                if (Number.isFinite(orderA) && Number.isFinite(orderB) && orderA !== orderB) return orderA - orderB;
                if (Number.isFinite(orderA) && !Number.isFinite(orderB)) return -1;
                if (!Number.isFinite(orderA) && Number.isFinite(orderB)) return 1;
                return 0;
            });
            const walk = (items, depth) => {
                for (const node of sortNodes(items)) {
                    if (!node || !node.secure_code) continue;
                    rows.push({
                        secure_code: node.secure_code,
                        name: node.name || node.secure_code,
                        node_type: node.node_type || '',
                        depth,
                        page_layout_secure_code: node.page_layout_secure_code || '',
                    });
                    walk(node.children || [], depth + 1);
                }
            };
            walk(nodes, 0);
            return rows;
        },

        async loadSiteMap() {
            const scope = this.siteMapScope();
            this.siteMapError = '';
            if (!scope) {
                this.siteMapNodes = [];
                this.siteMapLoaded = false;
                return;
            }
            try {
                const res = await fetch(`${apiBase}/sub-systems/${encodeURIComponent(scope)}/site-map`);
                const data = await res.json();
                if (!res.ok || !data.success) {
                    this.siteMapNodes = [];
                    this.siteMapLoaded = false;
                    this.siteMapError = tr('載入 Site Map 失敗');
                    console.error('[IR Designer] site map load failed:', data.error || data);
                    return;
                }
                this.siteMapNodes = this.flattenSiteMap(data.data || []);
                this.siteMapLoaded = true;
            } catch (err) {
                this.siteMapNodes = [];
                this.siteMapLoaded = false;
                this.siteMapError = tr('載入 Site Map 失敗');
                console.error('[IR Designer] site map load failed:', err);
            }
        },

        async loadMenuBackgrounds() {
            this.menuBackgroundError = '';
            try {
                const res = await fetch(`${apiBase}/backgrounds`);
                const data = await res.json();
                if (!res.ok || !data.success) {
                    this.menuBackgrounds = [];
                    this.menuBackgroundsLoaded = false;
                    this.menuBackgroundError = tr('載入底圖失敗');
                    return;
                }
                // 只留有 platform_file_sc 的底圖：renderer 認的是 platform_files 的
                // secure_code，早期上傳到 static/uploads 的舊底圖沒有對應檔案記錄，
                // 選了也不會生效，不如不給選。
                const rows = Array.isArray(data.data) ? data.data : [];
                this.menuBackgrounds = rows.filter((bg) => bg && bg.platform_file_sc);
                this.menuBackgroundsLoaded = true;
            } catch (err) {
                this.menuBackgrounds = [];
                this.menuBackgroundsLoaded = false;
                this.menuBackgroundError = tr('載入底圖失敗');
            }
        },

        async ensurePortalOrg() {
            if (!this.dataScope) return;
            if (this.portalOrgLoaded && this.portalOrgScope === this.dataScope) return;
            try {
                const res = await fetch(`${BP}/api/nocode-builder/sub-systems/${encodeURIComponent(this.dataScope)}/portal/org`);
                const data = await res.json();
                if (!res.ok || !data.success) {
                    this.portalGroups = [];
                    this.portalLevels = [];
                    this.portalPermissions = [];
                    this.portalOrgScope = '';
                    this.portalOrgLoaded = false;
                    console.warn('[IR Designer] portal org load failed:', data.error || data);
                    return;
                }
                const orgData = data.data || {};
                this.portalGroups = orgData.groups || [];
                this.portalLevels = orgData.levels || [];
                await this.loadPortalPermissions(this.dataScope);
                this.portalOrgScope = this.dataScope;
                this.portalOrgLoaded = true;
                this.syncPreviewIdentity();
            } catch (err) {
                this.portalGroups = [];
                this.portalLevels = [];
                this.portalPermissions = [];
                this.portalOrgScope = '';
                this.portalOrgLoaded = false;
                console.warn('[IR Designer] portal org load failed:', err);
            }
        },

        async loadPortalPermissions(scope) {
            const res = await fetch(`${BP}/api/nocode-builder/sub-systems/${encodeURIComponent(scope)}/portal/permission-model`);
            const data = await res.json();
            if (!res.ok || !data.success) {
                this.portalPermissions = [];
                console.warn('[IR Designer] portal permission model load failed:', data.error || data);
                return;
            }
            const model = data.data || {};
            this.portalPermissions = Array.isArray(model.permissions) ? model.permissions : [];
        },

        activePortalGroups() {
            return (this.portalGroups || []).filter((group) => group && group.code && group.is_active !== false);
        },

        sortedPortalLevels() {
            return [...(this.portalLevels || [])]
                .filter((level) => level && level.code && level.is_active !== false)
                .sort((a, b) => Number(a.rank || 0) - Number(b.rank || 0));
        },

        previewIdentityLabel() {
            const group = this.activePortalGroups().find((item) => item.code === this.previewGroup);
            const groupText = group ? `${group.name} (${group.code})` : tr('不限群組');
            const level = this.sortedPortalLevels().find((item) => item.code === this.previewLevel);
            const levelText = level
                ? `${level.name} (${level.code}, rank ${level.rank})`
                : (this.previewLevel || '-');
            return `${groupText} / ${levelText}`;
        },

        activePortalPermissions() {
            return (this.portalPermissions || []).filter((perm) => perm && perm.code);
        },

        defaultPreviewLevel() {
            const levels = this.sortedPortalLevels();
            if (levels.some((level) => level.code === 'GUEST')) return 'GUEST';
            return (levels[0] && levels[0].code) || 'GUEST';
        },

        previewIdentityStorageKey() {
            if (!this.dataScope) return '';
            return `bk.ir-designer.preview-identity.${this.dataScope}`;
        },

        loadStoredPreviewIdentity() {
            const key = this.previewIdentityStorageKey();
            if (!key) return null;
            try {
                const raw = sessionStorage.getItem(key);
                if (!raw) return null;
                const parsed = JSON.parse(raw);
                if (!parsed || typeof parsed !== 'object') return null;
                return {
                    group: String(parsed.group || ''),
                    level: String(parsed.level || ''),
                };
            } catch (err) {
                return null;
            }
        },

        persistPreviewIdentity() {
            const key = this.previewIdentityStorageKey();
            if (!key) return;
            // 切換 dataScope 的過程中 previewGroup/Level 會被清空，此時若寫入，
            // 會把「即將切過去的那個子系統」的既有存檔洗成空值。
            // 等該子系統的組織資料真正載完（portalOrgScope 對齊 dataScope）才寫。
            if (!this.portalOrgLoaded || this.portalOrgScope !== this.dataScope) return;
            try {
                sessionStorage.setItem(key, JSON.stringify({
                    group: this.previewGroup || '',
                    level: this.previewLevel || '',
                }));
            } catch (err) {
                // sessionStorage may be unavailable in private browsing modes.
            }
        },

        resetPreviewIdentity() {
            this.previewGroup = '';
            this.previewLevel = '';
        },

        syncPreviewIdentity() {
            if (!this.previewGroup && !this.previewLevel) {
                const stored = this.loadStoredPreviewIdentity();
                if (stored) {
                    this.previewGroup = stored.group;
                    this.previewLevel = stored.level;
                }
            }
            if (this.previewGroup && !this.activePortalGroups().some((group) => group.code === this.previewGroup)) {
                this.previewGroup = '';
            }
            const levels = this.sortedPortalLevels();
            if (!levels.some((level) => level.code === this.previewLevel)) {
                this.previewLevel = this.defaultPreviewLevel();
            }
        },

        widgetActionEnabled(action) {
            const widget = this.selectedWidget;
            return !!(widget && widget.access_matrix && widget.access_matrix[action]);
        },

        toggleWidgetAction(action, enabled) {
            const widget = this.selectedWidget;
            if (!widget) return;
            if (enabled) {
                if (!widget.access_matrix) widget.access_matrix = {};
                if (!widget.access_matrix[action]) {
                    widget.access_matrix[action] = { required_permissions: [], match_mode: 'any' };
                }
            } else if (widget.access_matrix) {
                delete widget.access_matrix[action];
                if (Object.keys(widget.access_matrix).length === 0) {
                    delete widget.access_matrix;
                }
            }
            this.markDirty();
        },

        widgetActionPermissions(action) {
            const widget = this.selectedWidget;
            const rule = widget && widget.access_matrix && widget.access_matrix[action];
            return rule && Array.isArray(rule.required_permissions) ? rule.required_permissions : [];
        },

        toggleWidgetPermission(action, code) {
            const widget = this.selectedWidget;
            const rule = widget && widget.access_matrix && widget.access_matrix[action];
            if (!rule || !code) return;
            if (!Array.isArray(rule.required_permissions)) rule.required_permissions = [];
            const index = rule.required_permissions.indexOf(code);
            if (index >= 0) {
                rule.required_permissions.splice(index, 1);
            } else {
                rule.required_permissions.push(code);
            }
            this.markDirty();
        },

        widgetActionMatchMode(action) {
            const widget = this.selectedWidget;
            const rule = widget && widget.access_matrix && widget.access_matrix[action];
            return rule && rule.match_mode === 'all' ? 'all' : 'any';
        },

        setWidgetActionMatchMode(action, mode) {
            const widget = this.selectedWidget;
            const rule = widget && widget.access_matrix && widget.access_matrix[action];
            if (!rule) return;
            rule.match_mode = mode === 'all' ? 'all' : 'any';
            this.markDirty();
        },

        get selectedWidget() {
            if (this.sharedComponentEditor.open && this.sharedComponentEditor.draft) {
                return this.sharedComponentEditor.draft;
            }
            return this.findWidget(this.selectedId) || this.activeWidget;
        },

        get treeRows() {
            const rows = [];
            const walk = (widgets, depth) => {
                widgets.forEach((widget) => {
                    rows.push({ widget, depth });
                    if (widget.type === 'layout') {
                        walk(widget.children || [], depth + 1);
                    }
                });
            };
            walk(this.doc.page.widgets || [], 0);
            return rows;
        },

        get actionWidgets() {
            return this.treeRows.map((row) => row.widget).filter((widget) => widget.type === 'actions');
        },

        get rowLinkTargets() {
            return this.treeRows
                .map((row) => row.widget)
                .filter((widget) => widget.type === 'detail' || widget.type === 'form' || widget.type === 'master_detail');
        },

        get formActionRefs() {
            return (this.meta.actions || []).filter((ref) => /^[a-z][a-z0-9_.:-]{1,127}$/.test(ref));
        },

        get formPortalActionRefs() {
            return (this.meta.portal_actions || []).filter((ref) => /^[a-z][a-z0-9_.:-]{1,127}$/.test(ref));
        },

        defaultActionRef() {
            return (this.meta.portal_actions || [])[0] || (this.meta.actions || [])[0] || '';
        },

        get selectedResource() {
            const widget = this.selectedWidget;
            if (!widget || !widget.binding) return null;
            return this.meta.resources.find((res) => res.code === widget.binding.resource) || null;
        },

        get selectedResourceViews() {
            return (this.selectedResource && this.selectedResource.views) || [];
        },

        get selectedResourceFields() {
            return (this.selectedResource && this.selectedResource.fields) || [];
        },

        widgetTypeLabel(widget) {
            const item = this.palette.find((entry) => entry.type === (widget && widget.type));
            return item ? item.label : ((widget && widget.type) || '');
        },

        emptyBinding() {
            return { resource: '', view: '', fields: [] };
        },

        resourceForBinding(binding) {
            if (!binding) return null;
            return this.meta.resources.find((res) => res.code === binding.resource) || null;
        },

        viewsForBinding(binding) {
            const resource = this.resourceForBinding(binding);
            return (resource && resource.views) || [];
        },

        fieldsForBinding(binding) {
            const resource = this.resourceForBinding(binding);
            return (resource && resource.fields) || [];
        },

        writableFieldsForBinding(binding) {
            const resource = this.resourceForBinding(binding);
            return (resource && resource.writable_fields) || [];
        },

        formatResourceOption(res) {
            if (!res) return '';
            return res.name ? `${res.name} (${res.code})` : res.code;
        },

        formatFormMappingOption(mapping) {
            if (!mapping) return '';
            const name = mapping.published_form_name || mapping.form_template_name || '';
            const code = mapping.form_template_code || mapping.secure_code || '';
            return name && code ? `${name} (${code})` : (name || code);
        },

        formSubmitReady() {
            const widget = this.selectedWidget;
            return !!(
                widget
                && widget.mapping_ref
                && widget.submit_action_ref
                && widget.access_matrix
                && widget.access_matrix.create
            );
        },

        formMissingItems() {
            const widget = this.selectedWidget || {};
            const missing = [];
            if (!widget.mapping_ref) missing.push(tr('表單流程配對'));
            if (!widget.submit_action_ref) missing.push(tr('送出動作'));
            if (!(widget.access_matrix && widget.access_matrix.create)) missing.push(tr('新增准入'));
            return missing;
        },

        firstPortalBindingResource(widgets) {
            const list = widgets || this.doc.page.widgets || [];
            for (const widget of list) {
                const resource = widget.binding && widget.binding.resource;
                if (resource && resource.indexOf('portal:') === 0) return resource;
                const masterResource = widget.master && widget.master.binding && widget.master.binding.resource;
                if (masterResource && masterResource.indexOf('portal:') === 0) return masterResource;
                const detailResource = widget.detail && widget.detail.binding && widget.detail.binding.resource;
                if (detailResource && detailResource.indexOf('portal:') === 0) return detailResource;
                if (widget.type === 'layout') {
                    const found = this.firstPortalBindingResource(widget.children || []);
                    if (found) return found;
                }
            }
            return '';
        },

        async detectPortalScope() {
            // 掛載關係優先：純 form 頁沒有 portal: binding 可推導，
            // 但仍需要 dataScope 才能顯示元件准入設定。
            if (this.mountedSubSystem) {
                this.dataScope = this.mountedSubSystem;
                await this.loadMeta(this.dataScope);
                return;
            }
            const portalCode = this.firstPortalBindingResource();
            if (!portalCode || !this.subSystems.length) return;
            for (const subSystem of this.subSystems.slice(0, 10)) {
                try {
                    const res = await fetch(`${BP}/api/pageir/meta?sub_system=${encodeURIComponent(subSystem.secure_code)}`);
                    const data = await res.json();
                    if (!data.success) continue;
                    const resources = data.portal_resources || [];
                    if (resources.some((resource) => resource.code === portalCode)) {
                        this.dataScope = subSystem.secure_code;
                        this.meta = {
                            resources,
                            actions: data.actions || [],
                            portal_actions: data.portal_actions || [],
                        };
                        return;
                    }
                } catch (err) {
                    console.warn('[IR Designer] portal scope detect failed:', err);
                }
            }
        },

        findWidget(id, widgets) {
            if (!id) return null;
            const list = widgets || this.doc.page.widgets || [];
            for (const widget of list) {
                if (widget.id === id) return widget;
                if (widget.type === 'layout') {
                    const found = this.findWidget(id, widget.children || []);
                    if (found) return found;
                }
            }
            return null;
        },

        findTopLevelWidget(id) {
            return (this.doc.page.widgets || []).find((widget) => widget.id === id) || null;
        },

        assignedWidgetIds() {
            const ids = new Set();
            for (const meta of Object.values(this.canvasMeta || {})) {
                for (const id of meta.widget_ids || []) ids.add(id);
            }
            return ids;
        },

        unplacedTopLevelWidgets() {
            const assigned = this.assignedWidgetIds();
            return (this.doc.page.widgets || []).filter((widget) => widget && widget.id && !assigned.has(widget.id));
        },

        topLevelWidgetRows() {
            return (this.doc.page.widgets || []).filter((widget) => widget && widget.id).map((widget) => ({
                widget,
                zoneId: this.zoneIdForWidget(widget.id),
            }));
        },

        zoneIdForWidget(widgetId) {
            for (const [zoneId, meta] of Object.entries(this.canvasMeta || {})) {
                if (Array.isArray(meta.widget_ids) && meta.widget_ids.includes(widgetId)) return zoneId;
            }
            return '';
        },

        widgetPlacementLabel(widgetId) {
            return this.zoneIdForWidget(widgetId) || tr('未放置');
        },

        selectedZoneMeta() {
            return (this.selectedZoneId && this.canvasMeta[this.selectedZoneId]) || null;
        },

        selectedZoneWidgets() {
            const meta = this.selectedZoneMeta();
            if (!meta) return [];
            return (meta.widget_ids || []).map((id) => this.findTopLevelWidget(id)).filter(Boolean);
        },

        addWidgetToSelectedZone(widgetId) {
            const meta = this.selectedZoneMeta();
            const widget = this.findTopLevelWidget(widgetId);
            if (!meta || !widget) return;
            if (!Array.isArray(meta.widget_ids)) meta.widget_ids = [];
            if (!meta.widget_ids.includes(widgetId)) {
                meta.widget_ids.push(widgetId);
                this.markDirty();
                this.refreshZoneContents();
            }
        },

        removeWidgetFromSelectedZone(widgetId) {
            const meta = this.selectedZoneMeta();
            if (!meta || !Array.isArray(meta.widget_ids)) return;
            const index = meta.widget_ids.indexOf(widgetId);
            if (index < 0) return;
            meta.widget_ids.splice(index, 1);
            this.markDirty();
            this.refreshZoneContents();
        },

        moveWidgetInSelectedZone(widgetId, dir) {
            const meta = this.selectedZoneMeta();
            if (!meta || !Array.isArray(meta.widget_ids)) return;
            const index = meta.widget_ids.indexOf(widgetId);
            const target = index + dir;
            if (index < 0 || target < 0 || target >= meta.widget_ids.length) return;
            const item = meta.widget_ids.splice(index, 1)[0];
            meta.widget_ids.splice(target, 0, item);
            this.markDirty();
            this.refreshZoneContents();
        },

        setSelectedZoneOverflow(value) {
            const meta = this.selectedZoneMeta();
            if (!meta) return;
            meta.overflow = value === 'visible' ? 'visible' : 'auto';
            this.markDirty();
        },

        findParent(id, widgets, parent) {
            const list = widgets || this.doc.page.widgets || [];
            for (const widget of list) {
                if (widget.id === id) return { parent, siblings: list, widget };
                if (widget.type === 'layout') {
                    const found = this.findParent(id, widget.children || [], widget);
                    if (found) return found;
                }
            }
            return null;
        },

        addWidget(type) {
            if (!type) return;
            // 編輯共用元件時左側樹顯示的是頁面、不是 draft，這裡加進去的元件既看不到
            // 也選不到（selectWidget 在編輯模式一律 return），只會變成看不見的孤兒
            if (this.sharedComponentEditor.open) return;
            const selected = this.selectedWidget;
            const widget = this.newWidget(type);
            if (selected && selected.type === 'layout' && !selected.shared_ref) {
                selected.children.push(widget);
            } else {
                this.doc.page.widgets.push(widget);
            }
            this.selectedId = widget.id;
            this.activeWidget = widget;
            this.selectedZoneId = '';
            if (widget.type === 'menu' && !this.siteMapLoaded && !this.siteMapError) {
                this.loadSiteMap();
            }
            if (widget.type === 'menu' && !this.menuBackgroundsLoaded && !this.menuBackgroundError) {
                this.loadMenuBackgrounds();
            }
            this.markDirty();
        },

        addWidgetToZone(type, zoneId) {
            if (!type || !zoneId || !this.canvasMeta[zoneId]) return;
            const widget = this.newWidget(type);
            this.doc.page.widgets.push(widget);
            if (!Array.isArray(this.canvasMeta[zoneId].widget_ids)) this.canvasMeta[zoneId].widget_ids = [];
            this.canvasMeta[zoneId].widget_ids.push(widget.id);
            this.selectedId = widget.id;
            this.activeWidget = widget;
            this.selectedZoneId = '';
            if (widget.type === 'menu' && !this.siteMapLoaded && !this.siteMapError) {
                this.loadSiteMap();
            }
            if (widget.type === 'menu' && !this.menuBackgroundsLoaded && !this.menuBackgroundError) {
                this.loadMenuBackgrounds();
            }
            this.refreshZoneContents();
            this.markDirty();
        },

        newWidget(type) {
            const id = this.nextId(type);
            const firstBinding = this.defaultBinding();
            const firstField = firstBinding.fields[0] || 'id';
            if (type === 'layout') {
                return { id, type, columns: 1, gap: 16, children: [] };
            }
            if (type === 'text') {
                return { id, type, level: 'p', content_i18n: { 'zh-TW': tr('文字'), en: '' } };
            }
            if (type === 'menu') {
                return {
                    id,
                    type,
                    title_i18n: { 'zh-TW': tr('選單'), en: '' },
                    items: [],
                    source_mode: 'manual',
                    include_system_links: false,
                    orientation: 'vertical',
                    item_gap: 6,
                    hover_expand: true,
                    nav_source: 'self',
                    nav_key: 'nav',
                    style: this.menuStyleDefaults(),
                };
            }
            if (type === 'table') {
                return {
                    id, type, binding: firstBinding,
                    columns: [{ field: firstField, label_i18n: { 'zh-TW': firstField, en: firstField }, sortable: false }],
                    page_size: 20,
                    default_sort: { field: firstField, dir: 'asc' },
                };
            }
            if (type === 'detail') {
                return {
                    id, type, binding: firstBinding,
                    layout_columns: 1,
                    fields: [{ field: firstField, label_i18n: { 'zh-TW': firstField, en: firstField } }],
                };
            }
            if (type === 'master_detail') {
                return {
                    id,
                    type,
                    master: { binding: this.emptyBinding(), fields: [] },
                    detail: { binding: this.emptyBinding(), foreign_key: '', columns: [] },
                };
            }
            if (type === 'actions') {
                return {
                    id, type,
                    buttons: [{
                        id: this.nextId('btn'),
                        label_i18n: { 'zh-TW': tr('執行'), en: 'Run' },
                        style: 'secondary',
                        action_ref: this.defaultActionRef(),
                    }],
                };
            }
            return { id, type: 'form', formio_schema: { display: 'form', components: [] } };
        },

        defaultBinding() {
            const resource = this.meta.resources[0] || { code: 'user', views: ['list'], fields: ['username'] };
            return {
                resource: resource.code || '',
                view: (resource.views || [])[0] || '',
                fields: (resource.fields || []).slice(0, 1),
            };
        },

        nextId(type) {
            this.counters[type] = (this.counters[type] || 0) + 1;
            return `${type}-${this.counters[type]}`;
        },

        syncCounters() {
            this.treeRows.forEach((row) => {
                const parts = row.widget.id.match(/^([a-z_]+)-(\d+)$/);
                if (parts) {
                    this.counters[parts[1]] = Math.max(this.counters[parts[1]] || 0, Number(parts[2]));
                }
            });
        },

        initLayoutEngineState() {
            const page = this.doc.page || {};
            this.engine = page.engine === 'grid' || page.engine === 'free' ? page.engine : 'flow';
            this.canvasMeta = {};
            const zones = this.engine === 'free'
                ? (page.canvas && Array.isArray(page.canvas.frames) ? page.canvas.frames : [])
                : (page.canvas && Array.isArray(page.canvas.zones) ? page.canvas.zones : []);
            for (const zone of zones) {
                if (!zone || !zone.id) continue;
                this.canvasMeta[zone.id] = {
                    overflow: zone.overflow === 'visible' ? 'visible' : 'auto',
                    widget_ids: Array.isArray(zone.widget_ids) ? [...zone.widget_ids] : [],
                };
            }
            if (this.engine === 'grid' && !page.canvas) {
                this.doc.page.canvas = this.defaultGridCanvas();
                this.initLayoutEngineState();
            }
            if (this.engine === 'free' && !page.canvas) {
                this.doc.page.canvas = this.defaultFreeCanvas();
                this.initLayoutEngineState();
            }
        },

        defaultGridCanvas() {
            return {
                min_width: 1280,
                gap: 8,
                col_widths: [1, 1],
                row_heights: [120, 120],
                zones: [
                    { id: 'z1', row: 1, col: 1, row_span: 1, col_span: 1, overflow: 'auto', widget_ids: [] },
                    { id: 'z2', row: 1, col: 2, row_span: 1, col_span: 1, overflow: 'auto', widget_ids: [] },
                    { id: 'z3', row: 2, col: 1, row_span: 1, col_span: 1, overflow: 'auto', widget_ids: [] },
                    { id: 'z4', row: 2, col: 2, row_span: 1, col_span: 1, overflow: 'auto', widget_ids: [] },
                ],
            };
        },

        defaultFreeCanvas() {
            return {
                min_width: 1280,
                row_unit: 60,
                columns: 12,
                gap: 8,
                frames: [
                    { id: 'f1', x: 0, y: 0, w: 6, h: 4, overflow: 'auto', widget_ids: [] },
                ],
            };
        },

        mountGridEditor() {
            if (this.engine !== 'grid') return;
            const el = document.getElementById('ird-grid-layout-editor');
            if (!el || typeof GridLayoutEditor === 'undefined') return;
            if (!this.doc.page.canvas) this.doc.page.canvas = this.defaultGridCanvas();
            if (!this.gridEditor) {
                this.gridEditor = new GridLayoutEditor(el, { rows: 2, cols: 2, layoutOnly: true });
                this.gridEditor.onZoneSelect = (zoneId) => {
                    this.selectedZoneId = zoneId;
                    this.selectedId = '';
                    this.activeWidget = null;
                };
                this.gridEditor.onChanged = () => {
                    this.syncCanvasMetaWithGeometry();
                    this.markDirty();
                };
                this.gridEditor.onZoneDrop = (zoneId, event) => {
                    const type = this.dragType || (event.dataTransfer && event.dataTransfer.getData('text/plain'));
                    this.addWidgetToZone(type, zoneId);
                    this.dragType = '';
                };
            }
            this.gridEditor.loadCanvas(this.doc.page.canvas);
            this.syncCanvasMetaWithGeometry();
        },

        mountFreeGrid() {
            if (this.engine !== 'free') return;
            const el = document.getElementById('ird-free-gridstack');
            if (!el || typeof GridStack === 'undefined') return;
            if (!this.doc.page.canvas) this.doc.page.canvas = this.defaultFreeCanvas();
            if (this.freeGrid) {
                this.freeGrid.destroy(false);
                this.freeGrid = null;
            }
            const canvas = this.normalizeFreeCanvas(this.doc.page.canvas);
            this.doc.page.canvas = canvas;
            el.style.minWidth = `${canvas.min_width}px`;
            this.freeGrid = GridStack.init({
                column: 12,
                cellHeight: `${canvas.row_unit}px`,
                margin: canvas.gap / 2,
                float: true,
                disableOneColumnMode: true,
            }, el);
            this.renderFreeFrames(canvas.frames || []);
            this.syncFreeMetaWithGeometry();
            this.freeGrid.on('change', () => {
                this.syncFreeMetaWithGeometry();
                this.markDirty();
            });
        },

        renderFreeFrames(frames) {
            if (!this.freeGrid) return;
            this.freeGrid.removeAll(false);
            for (const frame of frames || []) {
                // GridStack v11 起 addWidget() 不收 HTMLElement（只會 console.error
                // 後轉呼叫 makeWidget），既有元素一律直接走 makeWidget
                this.freeGrid.makeWidget(this.createFreeFrameElement(frame));
            }
            this.refreshZoneContents();
        },

        createFreeFrameElement(frame) {
            const item = document.createElement('div');
            item.className = 'grid-stack-item';
            item.setAttribute('gs-id', frame.id);
            item.setAttribute('gs-x', frame.x);
            item.setAttribute('gs-y', frame.y);
            item.setAttribute('gs-w', frame.w);
            item.setAttribute('gs-h', frame.h);
            item.dataset.frameId = frame.id;

            const content = document.createElement('div');
            content.className = 'grid-stack-item-content';
            content.onclick = () => this.selectFreeFrame(frame.id);
            content.addEventListener('dragover', (event) => {
                event.preventDefault();
                event.stopPropagation();
                content.classList.add('ird-free-frame-drag-over');
            });
            content.addEventListener('dragleave', () => {
                content.classList.remove('ird-free-frame-drag-over');
            });
            content.addEventListener('drop', (event) => {
                event.preventDefault();
                event.stopPropagation();
                content.classList.remove('ird-free-frame-drag-over');
                const type = this.dragType || (event.dataTransfer && event.dataTransfer.getData('text/plain'));
                this.addWidgetToZone(type, frame.id);
                this.dragType = '';
            });
            item.appendChild(content);
            return item;
        },

        selectFreeFrame(frameId) {
            if (!frameId || !this.canvasMeta[frameId]) return;
            this.selectedZoneId = frameId;
            this.selectedId = '';
            this.activeWidget = null;
            this.refreshFreeFrameContents();
        },

        addFreeFrame() {
            if (this.engine !== 'free') return;
            if (!this.doc.page.canvas) this.doc.page.canvas = this.defaultFreeCanvas();
            const id = this.nextFreeFrameId();
            const frame = { id, x: 0, y: 0, w: 4, h: 3, overflow: 'auto', widget_ids: [] };
            this.canvasMeta[id] = { overflow: 'auto', widget_ids: [] };
            if (this.freeGrid) {
                this.freeGrid.makeWidget(this.createFreeFrameElement(frame));
                this.syncFreeMetaWithGeometry();
            } else {
                this.doc.page.canvas.frames = [...(this.doc.page.canvas.frames || []), frame];
            }
            this.selectFreeFrame(id);
            this.markDirty();
        },

        deleteFreeFrame(frameId) {
            if (this.engine !== 'free' || !frameId || !this.canvasMeta[frameId]) return;
            const widgetIds = Array.isArray(this.canvasMeta[frameId].widget_ids) ? this.canvasMeta[frameId].widget_ids : [];
            if (widgetIds.length && !confirm(tr('此框內的元件會回到未放置清單，確定刪除？'))) return;
            if (this.freeGrid) {
                const nodes = this.freeGrid.engine && this.freeGrid.engine.nodes ? this.freeGrid.engine.nodes : [];
                const node = nodes.find((item) => String(item.id || (item.el && item.el.getAttribute('gs-id')) || '') === frameId);
                const el = node && node.el;
                // 第二參數是 removeDOM，傳 false 會讓被刪掉的框留在畫面上
                // （資料層已消失、視覺還在，存檔後使用者才發現對不上）
                if (el) this.freeGrid.removeWidget(el, true);
            }
            delete this.canvasMeta[frameId];
            if (this.doc.page.canvas && Array.isArray(this.doc.page.canvas.frames)) {
                this.doc.page.canvas.frames = this.doc.page.canvas.frames.filter((frame) => frame.id !== frameId);
            }
            if (this.selectedZoneId === frameId) this.selectedZoneId = '';
            this.syncFreeMetaWithGeometry();
            this.markDirty();
        },

        nextFreeFrameId() {
            const used = new Set(Object.keys(this.canvasMeta || {}));
            let index = 1;
            while (used.has(`f${index}`) || this.findWidget(`f${index}`)) index += 1;
            return `f${index}`;
        },

        normalizeFreeCanvas(canvas) {
            const minWidth = this._clampNumber(canvas && canvas.min_width, 1280, 320, 4096);
            const rowUnit = this._clampNumber(canvas && canvas.row_unit, 60, 20, 200);
            const gap = this._clampNumber(canvas && canvas.gap, 8, 0, 64);
            const used = new Set();
            const frames = [];
            const sourceFrames = canvas && Array.isArray(canvas.frames) ? canvas.frames : [];
            for (const raw of sourceFrames) {
                if (!raw) continue;
                let id = String(raw.id || '');
                if (!this.isValidSlug(id) || used.has(id)) id = this.nextFreeFrameId();
                used.add(id);
                const x = this._clampNumber(raw.x, 0, 0, 11);
                const w = this._clampNumber(raw.w, 4, 1, 12 - x);
                frames.push({
                    id,
                    x,
                    y: this._clampNumber(raw.y, 0, 0, 999),
                    w,
                    h: this._clampNumber(raw.h, 3, 1, 200),
                    overflow: raw.overflow === 'visible' ? 'visible' : 'auto',
                    widget_ids: Array.isArray(raw.widget_ids) ? raw.widget_ids.filter((widgetId) => this.findTopLevelWidget(widgetId)) : [],
                });
            }
            return { min_width: minWidth, row_unit: rowUnit, columns: 12, gap, frames };
        },

        updateFreeCanvasOptions() {
            if (this.engine !== 'free') return;
            if (!this.doc.page.canvas) this.doc.page.canvas = this.defaultFreeCanvas();
            const canvas = this.normalizeFreeCanvas(this.doc.page.canvas);
            this.doc.page.canvas.min_width = canvas.min_width;
            this.doc.page.canvas.row_unit = canvas.row_unit;
            this.doc.page.canvas.columns = 12;
            this.doc.page.canvas.gap = canvas.gap;
            if (this.freeGrid) {
                this.freeGrid.cellHeight(`${canvas.row_unit}px`);
                this.freeGrid.margin(canvas.gap / 2);
                this.freeGrid.el.style.minWidth = `${canvas.min_width}px`;
            }
            this.markDirty();
        },

        syncFreeMetaWithGeometry() {
            if (!this.freeGrid) return;
            const frames = [];
            const next = {};
            const nodes = (this.freeGrid.engine && this.freeGrid.engine.nodes ? this.freeGrid.engine.nodes : [])
                .slice()
                .sort((a, b) => (a.y - b.y) || (a.x - b.x) || String(a.id || '').localeCompare(String(b.id || '')));
            for (const node of nodes) {
                const id = String(node.id || (node.el && node.el.getAttribute('gs-id')) || '');
                if (!id) continue;
                const old = this.canvasMeta[id] || {};
                next[id] = {
                    overflow: old.overflow === 'visible' ? 'visible' : 'auto',
                    widget_ids: Array.isArray(old.widget_ids) ? old.widget_ids.filter((widgetId) => this.findTopLevelWidget(widgetId)) : [],
                };
                frames.push({
                    id,
                    x: this._clampNumber(node.x, 0, 0, 11),
                    y: this._clampNumber(node.y, 0, 0, 999),
                    w: this._clampNumber(node.w, 1, 1, 12),
                    h: this._clampNumber(node.h, 1, 1, 200),
                });
            }
            this.canvasMeta = next;
            if (this.selectedZoneId && !this.canvasMeta[this.selectedZoneId]) this.selectedZoneId = '';
            if (!this.doc.page.canvas) this.doc.page.canvas = this.defaultFreeCanvas();
            this.doc.page.canvas.frames = frames;
            this.refreshZoneContents();
        },

        onEngineChange(value) {
            if (value === this.engine) return;
            if ((this.engine !== 'flow' || value !== 'flow') && !confirm(tr('版面配置會被清除，元件不會被刪除'))) return;
            if (value === 'free') {
                this.engine = 'free';
                this.doc.page.engine = 'free';
                this.doc.page.canvas = this.defaultFreeCanvas();
                this.initLayoutEngineState();
                this.selectedZoneId = '';
                if (this.gridEditor) {
                    this.gridEditor.destroy();
                    this.gridEditor = null;
                }
                this.markDirty();
                Alpine.nextTick(() => this.mountFreeGrid());
                return;
            }
            if (value === 'grid') {
                this.engine = 'grid';
                this.doc.page.engine = 'grid';
                this.doc.page.canvas = this.defaultGridCanvas();
                this.initLayoutEngineState();
                this.selectedZoneId = '';
                if (this.freeGrid) {
                    this.freeGrid.destroy(false);
                    this.freeGrid = null;
                }
                this.markDirty();
                Alpine.nextTick(() => this.mountGridEditor());
                return;
            }
            this.engine = 'flow';
            delete this.doc.page.engine;
            delete this.doc.page.canvas;
            this.canvasMeta = {};
            this.selectedZoneId = '';
            if (this.gridEditor) {
                this.gridEditor.destroy();
                this.gridEditor = null;
            }
            if (this.freeGrid) {
                this.freeGrid.destroy(false);
                this.freeGrid = null;
            }
            this.markDirty();
        },

        // 合併 / 拆分 / 重建矩陣都會讓某些 zone 消失。消失的 zone 若還放著元件，
        // 元件必須有去處，否則會靜默消失（實測：z3 空 + z4 有元件 合併後元件不見，
        // 未放置清單也不會列回來，使用者完全無從察覺）。
        // 規則：消失 zone 的元件併入「覆蓋它原本左上角的新 zone」（合併必然成立），
        // 找不到覆蓋者（例如整個矩陣被重建）就讓它回到未放置清單。
        syncCanvasMetaWithGeometry() {
            if (!this.gridEditor) return;
            const geometry = this.gridEditor.toCanvas();
            const zones = geometry.zones || [];
            const next = {};
            for (const zone of zones) {
                const old = this.canvasMeta[zone.id] || {};
                next[zone.id] = {
                    overflow: old.overflow === 'visible' ? 'visible' : 'auto',
                    widget_ids: Array.isArray(old.widget_ids) ? old.widget_ids.filter((id) => this.findTopLevelWidget(id)) : [],
                };
            }

            const covering = (row, col) => zones.find((zone) => (
                row >= zone.row && row < zone.row + zone.row_span
                && col >= zone.col && col < zone.col + zone.col_span
            ));
            for (const [zoneId, meta] of Object.entries(this.canvasMeta || {})) {
                if (next[zoneId]) continue;
                const orphans = (Array.isArray(meta.widget_ids) ? meta.widget_ids : [])
                    .filter((id) => this.findTopLevelWidget(id));
                if (!orphans.length) continue;
                const geo = (this._zoneGeometry || {})[zoneId];
                const host = geo ? covering(geo.row, geo.col) : null;
                if (!host || !next[host.id]) continue;   // 找不到接手者：留在未放置清單
                for (const id of orphans) {
                    if (!next[host.id].widget_ids.includes(id)) next[host.id].widget_ids.push(id);
                }
            }

            this._zoneGeometry = {};
            for (const zone of zones) {
                this._zoneGeometry[zone.id] = {
                    row: zone.row, col: zone.col, row_span: zone.row_span, col_span: zone.col_span,
                };
            }
            this.canvasMeta = next;
            if (this.selectedZoneId && !this.canvasMeta[this.selectedZoneId]) this.selectedZoneId = '';
            this.refreshZoneContents();
        },

        // 把每個 zone 放了哪些元件標到矩陣格子上（只看 zone id 看不出哪格有內容）
        refreshZoneContents() {
            if (this.engine === 'free') {
                this.refreshFreeFrameContents();
                return;
            }
            if (!this.gridEditor) return;
            const map = {};
            for (const [zoneId, meta] of Object.entries(this.canvasMeta || {})) {
                map[zoneId] = (Array.isArray(meta.widget_ids) ? meta.widget_ids : [])
                    .map((id) => {
                        const widget = this.findTopLevelWidget(id);
                        return widget ? `${id} (${widget.type})` : id;
                    });
            }
            this.gridEditor.setZoneContents(map);
        },

        refreshFreeFrameContents() {
            if (!this.freeGrid) return;
            const nodes = this.freeGrid.engine && this.freeGrid.engine.nodes ? this.freeGrid.engine.nodes : [];
            for (const node of nodes) {
                const id = String(node.id || (node.el && node.el.getAttribute('gs-id')) || '');
                const content = node.el && node.el.querySelector('.grid-stack-item-content');
                if (!id || !content) continue;
                node.el.classList.toggle('ird-free-frame-selected', id === this.selectedZoneId);
                content.innerHTML = '';
                const head = document.createElement('div');
                head.className = 'ird-free-frame-head';
                const label = document.createElement('span');
                label.className = 'ird-free-frame-id';
                label.textContent = id;
                head.appendChild(label);
                content.appendChild(head);

                const list = document.createElement('div');
                list.className = 'ird-free-frame-items';
                const meta = this.canvasMeta[id] || {};
                for (const widgetId of meta.widget_ids || []) {
                    const widget = this.findTopLevelWidget(widgetId);
                    const item = document.createElement('div');
                    item.className = 'ird-free-frame-widget';
                    item.textContent = widget ? `${widgetId} (${widget.type})` : widgetId;
                    list.appendChild(item);
                }
                content.appendChild(list);
                content.onclick = () => this.selectFreeFrame(id);
            }
        },

        buildGridCanvas() {
            const base = this.gridEditor ? this.gridEditor.toCanvas() : (this.doc.page.canvas || this.defaultGridCanvas());
            const minWidth = this._clampNumber(this.doc.page.canvas && this.doc.page.canvas.min_width, 1280, 320, 4096);
            const gap = this._clampNumber(this.doc.page.canvas && this.doc.page.canvas.gap, 8, 0, 64);
            const zones = (base.zones || []).map((zone) => {
                const meta = this.canvasMeta[zone.id] || {};
                return Object.assign({}, zone, {
                    overflow: meta.overflow === 'visible' ? 'visible' : 'auto',
                    widget_ids: Array.isArray(meta.widget_ids) ? [...meta.widget_ids] : [],
                });
            });
            return Object.assign({}, base, { min_width: minWidth, gap, zones });
        },

        buildFreeCanvas() {
            if (this.freeGrid) this.syncFreeMetaWithGeometry();
            const base = this.normalizeFreeCanvas(this.doc.page.canvas || this.defaultFreeCanvas());
            const frames = (base.frames || []).map((frame) => {
                const meta = this.canvasMeta[frame.id] || {};
                const x = this._clampNumber(frame.x, 0, 0, 11);
                const w = this._clampNumber(frame.w, 1, 1, 12 - x);
                return Object.assign({}, frame, {
                    x,
                    w,
                    overflow: meta.overflow === 'visible' ? 'visible' : 'auto',
                    widget_ids: Array.isArray(meta.widget_ids) ? [...meta.widget_ids] : [],
                });
            });
            return Object.assign({}, base, { columns: 12, frames });
        },

        _clampNumber(value, fallback, min, max) {
            const n = Number.parseInt(value, 10);
            if (!Number.isFinite(n)) return fallback;
            return Math.min(max, Math.max(min, n));
        },

        selectWidget(id) {
            if (this.sharedComponentEditor.open) return;
            this.selectedId = id;
            this.activeWidget = this.findWidget(id);
            this.selectedZoneId = '';
            if (this.activeWidget && this.activeWidget.type === 'menu' && !this.siteMapLoaded && !this.siteMapError) {
                this.loadSiteMap();
            }
            if (this.activeWidget && this.activeWidget.type === 'menu' && !this.menuBackgroundsLoaded && !this.menuBackgroundError) {
                this.loadMenuBackgrounds();
            }
            if (this.activeWidget) this.loadSharedComponents();
        },

        moveWidget(id, dir) {
            const found = this.findParent(id);
            if (!found) return;
            const index = found.siblings.findIndex((widget) => widget.id === id);
            const target = index + dir;
            if (target < 0 || target >= found.siblings.length) return;
            const item = found.siblings.splice(index, 1)[0];
            found.siblings.splice(target, 0, item);
            this.markDirty();
        },

        removeWidget(id) {
            const found = this.findParent(id);
            if (!found) return;
            const index = found.siblings.findIndex((widget) => widget.id === id);
            found.siblings.splice(index, 1);
            for (const meta of Object.values(this.canvasMeta || {})) {
                if (Array.isArray(meta.widget_ids)) {
                    meta.widget_ids = meta.widget_ids.filter((widgetId) => widgetId !== id);
                }
            }
            if (this.selectedId === id) {
                this.selectedId = '';
                this.activeWidget = null;
            }
            this.markDirty();
            if (this.engine !== 'flow') this.refreshZoneContents();
        },

        onIdInput(value) {
            const widget = this.selectedWidget;
            if (!widget) return;
            this.selectedId = value;
            this.markDirty();
        },

        isValidSlug(value) {
            return /^[a-z][a-z0-9-]{1,63}$/.test(value || '');
        },

        onResourceChange() {
            const widget = this.selectedWidget;
            const resource = this.selectedResource;
            if (!widget || !resource) return;
            widget.binding.view = (resource.views || [])[0] || '';
            widget.binding.fields = (resource.fields || []).slice(0, 1);
            this.syncBindingFields();
        },

        onMasterDetailResourceChange(section) {
            const part = this.masterDetailPart(section);
            if (!part || !part.binding) return;
            const resource = this.resourceForBinding(part.binding);
            if (!resource) return;
            part.binding.view = (resource.views || [])[0] || '';
            part.binding.fields = (resource.fields || []).slice(0, 1);
            if (section === 'detail') delete part.foreign_key;
            this.syncMasterDetailBindingFields(section);
        },

        syncBindingFields() {
            const widget = this.selectedWidget;
            if (!widget || !widget.binding) return;
            if (!widget.binding.fields.length && this.selectedResourceFields.length) {
                widget.binding.fields.push(this.selectedResourceFields[0]);
            }
            const allowed = new Set(widget.binding.fields);
            const first = widget.binding.fields[0] || '';
            if (widget.type === 'table') {
                widget.columns = (widget.columns || []).filter((col) => allowed.has(col.field));
                if (!widget.columns.length && first) this.addTableColumn();
                if (!allowed.has(widget.default_sort.field)) widget.default_sort.field = first;
            }
            if (widget.type === 'detail') {
                widget.fields = (widget.fields || []).filter((fieldDef) => allowed.has(fieldDef.field));
                if (!widget.fields.length && first) this.addDetailField();
            }
            this.markDirty();
        },

        masterDetailPart(section) {
            const widget = this.selectedWidget;
            if (!widget || widget.type !== 'master_detail') return null;
            return section === 'master' ? widget.master : widget.detail;
        },

        syncMasterDetailBindingFields(section) {
            const part = this.masterDetailPart(section);
            if (!part || !part.binding) return;
            if (!Array.isArray(part.binding.fields)) part.binding.fields = [];
            const available = this.fieldsForBinding(part.binding);
            if (!part.binding.fields.length && available.length) {
                part.binding.fields.push(available[0]);
            }
            const allowed = new Set(part.binding.fields);
            const first = part.binding.fields[0] || '';
            if (section === 'master') {
                part.fields = (part.fields || []).filter((fieldDef) => allowed.has(fieldDef.field));
                if (!part.fields.length && first) this.addMasterDetailField('master');
            } else {
                part.columns = (part.columns || []).filter((col) => allowed.has(col.field));
                if (!part.columns.length && first) this.addMasterDetailField('detail');
                const history = this.selectedWidget && this.selectedWidget.history;
                if (history && history.default_sort && !allowed.has(history.default_sort.field)) {
                    history.default_sort.field = first;
                }
            }
            this.markDirty();
        },

        addTableColumn() {
            const widget = this.selectedWidget;
            if (!widget) return;
            const field = (widget.binding.fields || [])[0] || '';
            if (!field) return;
            widget.columns.push({ field, label_i18n: { 'zh-TW': field, en: field }, sortable: false });
            this.markDirty();
        },

        addDetailField() {
            const widget = this.selectedWidget;
            if (!widget) return;
            const field = (widget.binding.fields || [])[0] || '';
            if (!field) return;
            widget.fields.push({ field, label_i18n: { 'zh-TW': field, en: field } });
            this.markDirty();
        },

        addMasterDetailField(section) {
            const part = this.masterDetailPart(section);
            if (!part || !part.binding) return;
            const field = (part.binding.fields || [])[0] || '';
            if (!field) return;
            if (section === 'master') {
                part.fields.push({ field, label_i18n: { 'zh-TW': field, en: field } });
            } else {
                part.columns.push({ field, label_i18n: { 'zh-TW': field, en: field }, sortable: false });
            }
            this.markDirty();
        },

        maskType(spec) {
            return (spec && spec.mask && spec.mask.type) || '';
        },

        setMaskType(spec, type) {
            if (!spec) return;
            if (!type) {
                delete spec.mask;
            } else if (type === 'partial') {
                spec.mask = { type: 'partial', keep_head: 0, keep_tail: 4 };
            } else if (['full', 'email', 'phone'].includes(type)) {
                spec.mask = { type };
            } else {
                spec.mask = { type: 'full' };
            }
            if (spec.mask && Object.prototype.hasOwnProperty.call(spec, 'sortable')) spec.sortable = false;
            this.markDirty();
        },

        setMaskParam(spec, key, value) {
            if (!spec || !spec.mask || spec.mask.type !== 'partial') return;
            if (!['keep_head', 'keep_tail'].includes(key)) return;
            const parsed = Number(value);
            if (!Number.isInteger(parsed) || parsed < 0 || parsed > 8) return;
            spec.mask[key] = parsed;
            this.markDirty();
        },

        clampMaskParam(value, fallback) {
            const parsed = Number(value);
            if (!Number.isInteger(parsed)) return fallback;
            return Math.min(8, Math.max(0, parsed));
        },

        addActionButton() {
            const widget = this.selectedWidget;
            if (!widget) return;
            widget.buttons.push({
                id: this.nextId('btn'),
                label_i18n: { 'zh-TW': tr('執行'), en: 'Run' },
                style: 'secondary',
                action_ref: this.defaultActionRef(),
            });
            this.markDirty();
        },

        removeArrayItem(items, idx) {
            items.splice(idx, 1);
            this.markDirty();
        },

        emptyToDelete(obj, key) {
            if (!obj[key]) delete obj[key];
            this.markDirty();
        },

        setOptionalWidgetValue(obj, key, value) {
            if (!obj) return;
            obj[key] = value;
            this.emptyToDelete(obj, key);
        },

        setOptionalNumberValue(obj, key, value) {
            if (!obj) return;
            if (value === '' || value === null || value === undefined) {
                delete obj[key];
            } else {
                const parsed = Number(value);
                if (Number.isInteger(parsed)) obj[key] = parsed;
            }
            this.markDirty();
        },

        menuStyleDefaults() {
            return {
                bg_color: '#ffffff',
                item_bg_color: '#ffffff',
                item_text_color: '#333333',
                item_hover_bg_color: '#e9ecef',
                item_hover_text_color: '#333333',
                accent_color: '#e67e22',
                border_color: '#dddddd',
                border_width: 1,
                border_radius: 4,
                background_file: '',
                background_size: 'cover',
                background_repeat: 'no-repeat',
                background_position: 'center',
            };
        },

        menuWalk(items, visit, depth = 0, path = []) {
            for (let index = 0; index < (items || []).length; index += 1) {
                const item = items[index];
                visit(item, depth, path.concat(index), items, index);
                if (item && item.kind === 'node') this.menuWalk(item.children || [], visit, depth + 1, path.concat(index));
            }
        },

        menuPath(value) {
            return String(value || '').split('.').filter((part) => part !== '').map((part) => Number(part));
        },

        menuPathKey(path) {
            return (path || []).join('.');
        },

        menuParentByPath(widget, path) {
            if (!widget || !Array.isArray(widget.items) || !Array.isArray(path) || path.length === 0) return null;
            let siblings = widget.items;
            for (let depth = 0; depth < path.length - 1; depth += 1) {
                const item = siblings[path[depth]];
                if (!item || item.kind !== 'node') return null;
                if (!Array.isArray(item.children)) item.children = [];
                siblings = item.children;
            }
            const index = path[path.length - 1];
            if (index < 0 || index >= siblings.length) return null;
            return { siblings, index, item: siblings[index] };
        },

        menuFindNode(sc) {
            return (this.siteMapNodes || []).find((node) => node.secure_code === sc) || null;
        },

        menuItemLabel(item) {
            if (!item) return '';
            if (item.kind === 'system') {
                const found = this.menuSystemLinks.find((row) => row.link === item.link);
                return found ? found.label : item.link;
            }
            const node = this.menuFindNode(item.node);
            return node ? node.name : tr('（節點已刪除）');
        },

        menuItemKindLabel(item) {
            if (!item) return '';
            if (item.kind === 'system') return tr('系統連結');
            const node = this.menuFindNode(item.node);
            if (!node) return tr('已刪除');
            return node.node_type === 'folder' ? tr('資料夾') : tr('網頁');
        },

        selectedMenuRows(widget) {
            const rows = [];
            this.menuWalk((widget && widget.items) || [], (item, depth, path, siblings, index) => {
                rows.push({
                    item,
                    depth,
                    path: this.menuPathKey(path),
                    key: `${this.menuPathKey(path)}:${item.kind}:${item.node || item.link || ''}`,
                    canUp: index > 0,
                    canDown: index < siblings.length - 1,
                    canOutdent: path.length > 1,
                    canIndent: item.kind === 'node' && index > 0 && siblings[index - 1] && siblings[index - 1].kind === 'node' && this.menuSubtreeDepth(item) + path.length <= 5,
                    label: this.menuItemLabel(item),
                    kindLabel: this.menuItemKindLabel(item),
                    deleted: item.kind === 'node' && !this.menuFindNode(item.node),
                });
            });
            return rows;
        },

        menuSubtreeDepth(item) {
            if (!item || item.kind !== 'node' || !Array.isArray(item.children) || item.children.length === 0) return 1;
            return 1 + Math.max(...item.children.map((child) => this.menuSubtreeDepth(child)));
        },

        menuHasNode(widget, sc) {
            let found = false;
            this.menuWalk((widget && widget.items) || [], (item) => {
                if (item && item.kind === 'node' && item.node === sc) found = true;
            });
            return found;
        },

        menuHasSystemLink(widget, link) {
            let found = false;
            this.menuWalk((widget && widget.items) || [], (item) => {
                if (item && item.kind === 'system' && item.link === link) found = true;
            });
            return found;
        },

        availableMenuNodes(widget) {
            return (this.siteMapNodes || []).filter((node) => !this.menuHasNode(widget, node.secure_code));
        },

        addMenuNode(widget, sc) {
            if (!widget || !sc || this.menuHasNode(widget, sc)) return;
            if (!Array.isArray(widget.items)) widget.items = [];
            widget.items.push({ kind: 'node', node: sc, children: [] });
            this.markDirty();
        },

        toggleMenuNode(widget, sc, checked) {
            if (!widget || !sc) return;
            if (checked) {
                this.addMenuNode(widget, sc);
            } else {
                this.removeMenuNode(widget, sc, false);
            }
        },

        toggleMenuSystemLink(widget, link, checked) {
            if (!widget || !link) return;
            if (!Array.isArray(widget.items)) widget.items = [];
            if (checked) {
                if (!this.menuHasSystemLink(widget, link)) {
                    widget.items.push({ kind: 'system', link });
                    this.markDirty();
                }
                return;
            }
            let changed = false;
            const removeFrom = (items) => {
                for (let index = (items || []).length - 1; index >= 0; index -= 1) {
                    const item = items[index];
                    if (item.kind === 'system' && item.link === link) {
                        items.splice(index, 1);
                        changed = true;
                    } else if (item.kind === 'node') {
                        removeFrom(item.children || []);
                    }
                }
            };
            removeFrom(widget.items);
            if (changed) this.markDirty();
        },

        removeMenuNode(widget, sc, ask = true) {
            if (!widget || !sc) return;
            let removed = false;
            const removeFrom = (items) => {
                for (let index = (items || []).length - 1; index >= 0; index -= 1) {
                    const item = items[index];
                    if (item.kind === 'node' && item.node === sc) {
                        items.splice(index, 1);
                        removed = true;
                    } else if (item.kind === 'node') {
                        removeFrom(item.children || []);
                    }
                }
            };
            if (ask && !window.confirm(tr('確定要移除此項目與其子項目？'))) return;
            removeFrom(widget.items || []);
            if (removed) this.markDirty();
        },

        moveMenuItem(widget, pathValue, dir) {
            const found = this.menuParentByPath(widget, this.menuPath(pathValue));
            if (!found) return;
            const target = found.index + dir;
            if (target < 0 || target >= found.siblings.length) return;
            const item = found.siblings.splice(found.index, 1)[0];
            found.siblings.splice(target, 0, item);
            this.markDirty();
        },

        indentMenuItem(widget, pathValue) {
            const path = this.menuPath(pathValue);
            const found = this.menuParentByPath(widget, path);
            if (!found || found.index === 0 || !found.item || found.item.kind !== 'node') return;
            if (this.menuSubtreeDepth(found.item) + path.length > 5) return;
            const prev = found.siblings[found.index - 1];
            if (!prev || prev.kind !== 'node') return;
            if (!Array.isArray(prev.children)) prev.children = [];
            const item = found.siblings.splice(found.index, 1)[0];
            prev.children.push(item);
            this.markDirty();
        },

        outdentMenuItem(widget, pathValue) {
            const path = this.menuPath(pathValue);
            if (path.length < 2) return;
            const found = this.menuParentByPath(widget, path);
            const parent = this.menuParentByPath(widget, path.slice(0, -1));
            if (!found || !parent) return;
            const item = found.siblings.splice(found.index, 1)[0];
            parent.siblings.splice(parent.index + 1, 0, item);
            this.markDirty();
        },

        removeMenuItem(widget, pathValue) {
            const found = this.menuParentByPath(widget, this.menuPath(pathValue));
            if (!found) return;
            if (!window.confirm(tr('確定要移除此項目與其子項目？'))) return;
            found.siblings.splice(found.index, 1);
            this.markDirty();
        },

        menuItemCount(widget) {
            let count = 0;
            this.menuWalk((widget && widget.items) || [], () => { count += 1; });
            return count;
        },

        sharedComponentScope() {
            return this.siteMapScope();
        },

        sharedRefKeepKeys() {
            return ['id', 'type', 'shared_ref', 'access_matrix'];
        },

        stripLocalConfig(widget) {
            const keep = this.sharedRefKeepKeys();
            for (const key of Object.keys(widget || {})) {
                if (!keep.includes(key)) delete widget[key];
            }
        },

        buildSharedWidgetJson(widget) {
            const json = clone(widget);
            delete json.id;
            delete json.shared_ref;
            delete json.access_matrix;
            if (json.type === 'table') {
                delete json.row_actions_ref;
                delete json.row_link_ref;
            }
            if (json.type === 'menu' && json.style && !json.style.background_file) {
                delete json.style.background_file;
            }
            return json;
        },

        async applySharedComponentRef(widget, ref) {
            if (!widget || !ref || !this.canManageSharedComponents()) return;
            await this.loadSharedComponents();
            const row = this.sharedComponentByRef(ref);
            if (!row || row.widget_type !== widget.type) return;
            widget.shared_ref = ref;
            this.stripLocalConfig(widget);
            this.markDirty();
        },

        async saveWidgetAsSharedComponent(widget) {
            if (!widget || !this.canManageSharedComponents()) return;
            const scope = this.sharedComponentScope();
            if (!scope) {
                alert(tr('此頁尚未掛在子系統下，無法建立共用元件'));
                return;
            }
            const name = (window.prompt(tr('共用元件名稱')) || '').trim();
            if (!name) return;
            try {
                const created = await window.BkSharedComponent.create(scope, {
                    name,
                    widget_json: this.buildSharedWidgetJson(widget),
                });
                await this.loadSharedComponents(true);
                widget.shared_ref = created.secure_code;
                this.stripLocalConfig(widget);
                this.markDirty();
            } catch (err) {
                alert(err.message || tr('建立共用元件失敗'));
            }
        },

        unlinkSharedComponent(widget) {
            if (!widget || !widget.shared_ref || !this.canManageSharedComponents()) return;
            const row = this.sharedComponentByRef(widget.shared_ref);
            if (!row || !row.widget_json) return;
            const pageMatrix = widget.access_matrix ? clone(widget.access_matrix) : null;
            const json = clone(row.widget_json);
            this.stripLocalConfig(widget);
            delete widget.shared_ref;
            for (const [key, value] of Object.entries(json)) {
                if (key === 'id' || key === 'access_matrix') continue;
                widget[key] = value;
            }
            if (pageMatrix) widget.access_matrix = pageMatrix;
            else if (json.access_matrix) widget.access_matrix = clone(json.access_matrix);
            if (widget.type === 'menu') this.normalizeMenuWidget(widget);
            this.markDirty();
        },

        openSharedComponentEditor(widget) {
            if (!widget || !widget.shared_ref || !this.canManageSharedComponents()) return;
            const row = this.sharedComponentByRef(widget.shared_ref);
            if (!row || !row.widget_json) return;
            const widgetJson = row.widget_json || {};
            this.sharedComponentEditor = {
                open: true,
                saving: false,
                error: '',
                source: row,
                draft: {
                    id: '__shared__',
                    ...clone(widgetJson),
                },
                dirty: false,
            };
            if (this.sharedComponentEditor.draft.type === 'menu') this.normalizeMenuWidget(this.sharedComponentEditor.draft);
            if (!this.siteMapLoaded && !this.siteMapError) this.loadSiteMap();
        },

        closeSharedComponentEditor() {
            if (this.sharedComponentEditor.saving) return;
            if (this.sharedComponentEditor.dirty && !window.confirm(tr('共用元件尚未儲存，確定要放棄變更嗎？'))) return;
            this.sharedComponentEditor = {
                open: false,
                saving: false,
                error: '',
                source: null,
                draft: null,
                dirty: false,
            };
        },

        async saveSharedComponentEditor() {
            const editor = this.sharedComponentEditor;
            const scope = this.sharedComponentScope();
            if (!editor.open || !editor.source || !editor.draft || !scope || !this.canManageSharedComponents()) return;
            editor.saving = true;
            editor.error = '';
            try {
                const widgetJson = this.buildSharedWidgetJson(editor.draft);
                await window.BkSharedComponent.update(scope, editor.source.secure_code, {
                    widget_json: widgetJson,
                });
                await this.loadSharedComponents(true);
                // closeSharedComponentEditor() 在 saving 為真時會直接 return，
                // 所以要先放掉 saving 再關，否則存檔成功後 modal 停在原地不動。
                editor.saving = false;
                editor.dirty = false;
                this.closeSharedComponentEditor();
            } catch (err) {
                editor.error = err.message || tr('儲存共用元件失敗');
            } finally {
                editor.saving = false;
            }
        },

        menuBackgroundUrl(sc) {
            return sc ? `${BP}/api/files/${encodeURIComponent(sc)}/serve` : '';
        },

        async uploadMenuBackground(event) {
            const input = event && event.target;
            const file = input && input.files && input.files[0];
            if (!file) return;
            this.menuUploadingBackground = true;
            this.menuBackgroundError = '';
            try {
                const form = new FormData();
                form.append('file', file);
                const res = await fetch(`${apiBase}/backgrounds/upload`, {
                    method: 'POST',
                    headers: { 'X-CSRFToken': csrfToken() },
                    body: form,
                });
                const data = await res.json();
                if (!res.ok || !data.success) {
                    this.menuBackgroundError = data.error || tr('上傳底圖失敗');
                    return;
                }
                await this.loadMenuBackgrounds();
                const widget = this.selectedWidget;
                if (widget && widget.type === 'menu') {
                    this.normalizeMenuWidget(widget);
                    widget.style.background_file = (data.data && data.data.platform_file_sc) || '';
                    this.markDirty();
                }
            } catch (err) {
                this.menuBackgroundError = tr('上傳底圖失敗');
            } finally {
                this.menuUploadingBackground = false;
                if (input) input.value = '';
            }
        },

        resetMenuStyle(widget) {
            if (!widget) return;
            widget.style = this.menuStyleDefaults();
            this.markDirty();
        },

        navKeyValid(widget) {
            return /^[A-Za-z0-9_-]{1,32}$/.test((widget && widget.nav_key) || '');
        },

        setMasterEditable(enabled) {
            const widget = this.selectedWidget;
            if (!widget || widget.type !== 'master_detail') return;
            if (enabled) {
                widget.master.editable = true;
            } else {
                delete widget.master.editable;
            }
            this.markDirty();
        },

        toggleMasterDetailHistory(enabled) {
            const widget = this.selectedWidget;
            if (!widget || widget.type !== 'master_detail') return;
            if (enabled) {
                const first = ((widget.detail && widget.detail.binding && widget.detail.binding.fields) || [])[0] || '';
                widget.history = { enabled: true };
                if (first) widget.history.default_sort = { field: first, dir: 'asc' };
            } else {
                delete widget.history;
            }
            this.markDirty();
        },

        setHistorySortField(value) {
            const widget = this.selectedWidget;
            if (!widget || widget.type !== 'master_detail' || !widget.history) return;
            if (!value) {
                delete widget.history.default_sort;
            } else {
                const dir = (widget.history.default_sort && widget.history.default_sort.dir) || 'asc';
                widget.history.default_sort = { field: value, dir };
            }
            this.markDirty();
        },

        setHistorySortDir(value) {
            const widget = this.selectedWidget;
            if (!widget || widget.type !== 'master_detail' || !widget.history || !widget.history.default_sort) return;
            widget.history.default_sort.dir = value === 'desc' ? 'desc' : 'asc';
            this.markDirty();
        },

        async formioBuilderOptions() {
            const language = (typeof BkI18n !== 'undefined' && BkI18n._locale) || 'zh-TW';
            const options = { language };
            if (language === 'zh-TW') {
                try {
                    const res = await fetch(`${BP}/static/vendor/formio-i18n-zh-TW.json`);
                    if (res.ok) options.i18n = { 'zh-TW': await res.json() };
                } catch (err) {
                    console.warn('[IR Designer] form.io i18n load failed:', err);
                }
            }
            return options;
        },

        async openFormBuilder() {
            const widget = this.selectedWidget;
            if (!widget || widget.type !== 'form') return;
            this.formBuilderWidget = widget;
            this.showFormModal = true;
            await Alpine.nextTick();
            const el = document.getElementById('ird-form-builder');
            el.innerHTML = '';
            this.formBuilder = await Formio.builder(el, clone(widget.formio_schema || { display: 'form', components: [] }), await this.formioBuilderOptions());
        },

        closeFormBuilder() {
            this.showFormModal = false;
            this.formBuilder = null;
            this.formBuilderWidget = null;
            const el = document.getElementById('ird-form-builder');
            if (el) el.innerHTML = '';
        },

        saveFormBuilder() {
            if (!this.formBuilder || !this.formBuilderWidget) return;
            this.formBuilderWidget.formio_schema = clone(this.formBuilder.schema || { display: 'form', components: [] });
            this.closeFormBuilder();
            this.markDirty();
        },

        buildDoc() {
            this.doc.page.title_i18n['zh-TW'] = this.pageTitleZh || this.pageName || '';
            if (!this.doc.page.id) this.doc.page.id = slugify(this.pageTitleZh || this.pageName).slice(0, 64);
            const doc = clone(this.doc);
            if (this.engine === 'grid') {
                doc.page.engine = 'grid';
                doc.page.canvas = this.buildGridCanvas();
            } else if (this.engine === 'free') {
                doc.page.engine = 'free';
                doc.page.canvas = this.buildFreeCanvas();
            } else {
                delete doc.page.engine;
                delete doc.page.canvas;
            }
            this.normalizeWidgetMasks(doc.page.widgets || []);
            this.normalizeAccessMatrix(doc.page.widgets || []);
            this.normalizeActionButtons(doc.page.widgets || []);
            this.normalizeMenuOnSave(doc.page.widgets || []);
            return doc;
        },

        // 「不使用底圖」在 UI 上是空字串，但 schema 的 background_file 有 pattern，
        // 空字串會被擋成 400。沒選底圖就不該送這個 key。
        normalizeMenuOnSave(widgets) {
            for (const widget of widgets || []) {
                if (widget.type === 'menu' && widget.style && !widget.style.background_file) {
                    delete widget.style.background_file;
                }
                if (widget.type === 'layout') this.normalizeMenuOnSave(widget.children || []);
            }
        },

        // 存檔前的本地檢查：後端 schema 擋得住，但回來的是一大串 JSON Schema 術語，
        // 使用者看不出「選單一個項目都沒勾」這種小事。先在前端講人話。
        localSaveErrors(widgets, path, includePageIssues = true) {
            const errors = [];
            if (includePageIssues && this.engine === 'grid') {
                errors.push(...this.localGridSaveIssues());
            }
            if (includePageIssues && this.engine === 'free') {
                errors.push(...this.localFreeSaveIssues());
            }
            (widgets || []).forEach((widget, index) => {
                const widgetPath = `${path}[${index}]`;
                if (widget.shared_ref) return;
                if (widget.type === 'menu' && !widget.shared_ref && widget.source_mode !== 'auto' && this.menuItemCount(widget) === 0) {
                    errors.push({
                        path: widgetPath,
                        widget_id: widget.id,
                        severity: 'error',
                        message: tr('選單「{id}」尚未選擇任何網頁或系統連結', { id: widget.id }),
                    });
                }
                if (widget.type === 'menu' && !this.navKeyValid(widget)) {
                    errors.push({
                        path: widgetPath,
                        widget_id: widget.id,
                        severity: 'error',
                        message: tr('選單「{id}」的聯動參數名只能使用英數字、底線或連字號，長度 1 到 32', { id: widget.id }),
                    });
                }
                if (widget.type === 'layout') {
                    errors.push(...this.localSaveErrors(widget.children, `${widgetPath}.children`, false));
                }
            });
            return errors;
        },

        localGridSaveIssues() {
            const issues = [];
            const canvas = this.buildGridCanvas();
            const rows = (canvas.row_heights || []).length;
            const cols = (canvas.col_widths || []).length;
            const occupied = new Set();
            for (const zone of canvas.zones || []) {
                const r1 = zone.row;
                const c1 = zone.col;
                const r2 = zone.row + zone.row_span - 1;
                const c2 = zone.col + zone.col_span - 1;
                if (r1 < 1 || c1 < 1 || r2 > rows || c2 > cols) {
                    issues.push({
                        path: `page.canvas.zones.${zone.id}`,
                        severity: 'error',
                        message: tr('區塊「{id}」超出矩陣範圍', { id: zone.id }),
                    });
                    continue;
                }
                for (let r = r1; r <= r2; r++) {
                    for (let c = c1; c <= c2; c++) {
                        const key = `${r}:${c}`;
                        if (occupied.has(key)) {
                            issues.push({
                                path: `page.canvas.zones.${zone.id}`,
                                severity: 'error',
                                message: tr('區塊「{id}」和其他區塊重疊', { id: zone.id }),
                            });
                        }
                        occupied.add(key);
                    }
                }
            }
            const assigned = new Set();
            for (const zone of canvas.zones || []) {
                for (const id of zone.widget_ids || []) assigned.add(id);
            }
            for (const widget of this.doc.page.widgets || []) {
                if (widget && widget.id && !assigned.has(widget.id)) {
                    issues.push({
                        path: `page.widgets.${widget.id}`,
                        widget_id: widget.id,
                        severity: 'warning',
                        message: tr('元件「{id}」還沒有放進任何區塊，儲存後不會顯示', { id: widget.id }),
                    });
                }
            }
            return issues;
        },

        localFreeSaveIssues() {
            const issues = [];
            const canvas = this.buildFreeCanvas();
            const occupied = new Set();
            for (const frame of canvas.frames || []) {
                const x1 = frame.x;
                const y1 = frame.y;
                const x2 = frame.x + frame.w - 1;
                const y2 = frame.y + frame.h - 1;
                if (x1 < 0 || y1 < 0 || x2 > 11 || y2 > 999 || frame.w < 1 || frame.h < 1) {
                    issues.push({
                        path: `page.canvas.frames.${frame.id}`,
                        severity: 'error',
                        message: tr('框「{id}」超出自由畫布範圍', { id: frame.id }),
                    });
                    continue;
                }
                for (let y = y1; y <= y2; y++) {
                    for (let x = x1; x <= x2; x++) {
                        const key = `${x}:${y}`;
                        if (occupied.has(key)) {
                            issues.push({
                                path: `page.canvas.frames.${frame.id}`,
                                severity: 'error',
                                message: tr('框「{id}」和其他框重疊', { id: frame.id }),
                            });
                        }
                        occupied.add(key);
                    }
                }
            }
            const assigned = new Set();
            for (const frame of canvas.frames || []) {
                for (const id of frame.widget_ids || []) assigned.add(id);
            }
            for (const widget of this.doc.page.widgets || []) {
                if (widget && widget.id && !assigned.has(widget.id)) {
                    issues.push({
                        path: `page.widgets.${widget.id}`,
                        widget_id: widget.id,
                        severity: 'warning',
                        message: tr('元件「{id}」還沒有放進任何框，儲存後不會顯示', { id: widget.id }),
                    });
                }
            }
            return issues;
        },

        // 回傳是否儲存成功（previewPage 會依此決定要不要開預覽分頁）
        async savePage() {
            this.errors = [];
            this.showIssueModal = false;
            const localErrors = this.localSaveErrors(this.doc.page.widgets, 'page.widgets');
            const blockingErrors = localErrors.filter((err) => err.severity !== 'warning');
            if (blockingErrors.length) {
                this.errors = localErrors;
                this.openIssueModal();
                return false;
            }
            this.errors = localErrors;
            const body = {
                name: this.pageTitleZh || this.pageName || tr('未命名頁面'),
                layout_json: this.buildDoc(),
            };
            try {
                const res = await fetch(`${apiBase}/pages/${this.secureCode}`, {
                    method: 'PUT',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': csrfToken(),
                    },
                    body: JSON.stringify(body),
                });
                const data = await res.json();
                if (!res.ok || !data.success) {
                    this.errors = data.errors || [{ path: '', message: data.error || tr('儲存失敗') }];
                    this.openIssueModal();
                    return false;
                }
                this.pageName = data.data.name || body.name;
                this.dirty = false;
                this.savedSnapshot = this.snapshot();
                this.errors = localErrors;
                if (localErrors.length) this.openIssueModal();
                this.showToast(tr('已儲存'));
                return true;
            } catch (err) {
                this.errors = [{ path: '', message: err.message || tr('儲存失敗') }];
                this.openIssueModal();
                return false;
            }
        },

        openSaveTemplateModal() {
            this.saveTemplateModal = {
                open: true,
                saving: false,
                error: '',
                name: this.pageTitleZh || this.pageName || '',
                description: '',
                category: tr('常用'),
                scope: this.mountedSubSystem ? 'sub_system' : 'org',
            };
        },

        closeSaveTemplateModal() {
            this.saveTemplateModal.open = false;
            this.saveTemplateModal.saving = false;
        },

        async saveAsTemplate() {
            const name = (this.saveTemplateModal.name || '').trim();
            const category = (this.saveTemplateModal.category || '').trim() || tr('常用');
            let scope = this.saveTemplateModal.scope === 'org' ? 'org' : 'sub_system';
            if (!this.mountedSubSystem) scope = 'org';
            if (!name) {
                this.saveTemplateModal.error = tr('名稱為必填');
                return;
            }
            this.saveTemplateModal.saving = true;
            this.saveTemplateModal.error = '';
            // 樣板存的是「當下畫面」的 IR，未存檔時會與頁面實際內容不一致。
            // 這一步由程式代勞，不能指望使用者記得先按儲存。
            if (this.dirty || this.snapshot() !== this.savedSnapshot) {
                if (!(await this.savePage())) {
                    // 儲存失敗時 savePage 已開啟問題清單，關掉本視窗才看得到。
                    this.closeSaveTemplateModal();
                    return;
                }
            }
            const layoutJson = this.buildDoc();
            const thumbnailSvg = window.BkPageTemplate.buildThumbnailSvg(layoutJson);
            try {
                const res = await fetch(`${apiBase}/templates`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': csrfToken(),
                    },
                    body: JSON.stringify({
                        name,
                        description: this.saveTemplateModal.description || '',
                        category,
                        scope,
                        sub_system_secure_code: this.mountedSubSystem,
                        source_sub_system_sc: this.mountedSubSystem,
                        layout_json: layoutJson,
                        thumbnail_svg: thumbnailSvg,
                    }),
                });
                const data = await res.json();
                if (!res.ok || !data.success) {
                    this.saveTemplateModal.error = data.error || tr('儲存樣板失敗');
                    return;
                }
                this.closeSaveTemplateModal();
                this.showToast(tr('已另存為樣板'));
            } catch (err) {
                this.saveTemplateModal.error = err.message || tr('儲存樣板失敗');
            } finally {
                this.saveTemplateModal.saving = false;
            }
        },

        showToast(message) {
            this.toast = { show: true, message };
            if (this._toastTimer) clearTimeout(this._toastTimer);
            this._toastTimer = setTimeout(() => { this.toast.show = false; }, 3000);
        },

        async previewPage() {
            const needSave = this.dirty || this.snapshot() !== this.savedSnapshot;
            // window.open 必須在使用者點擊的同步階段呼叫，否則 await savePage() 之後
            // 已不在手勢語境、會被瀏覽器的彈窗封鎖擋掉。先開空白分頁佔位，存檔失敗再關掉。
            const win = needSave ? window.open('', '_blank') : null;
            if (needSave && !(await this.savePage())) {
                if (win) win.close();
                return;
            }
            const target = this.buildPreviewUrl();
            if (win && !win.closed) {
                win.location = target;
            } else {
                window.open(target, '_blank');
            }
        },

        buildPreviewUrl() {
            if (!this.dataScope) return this.previewUrl;
            this.syncPreviewIdentity();
            const url = new URL(this.previewUrl, window.location.origin);
            url.searchParams.set('sub', this.dataScope);
            if (this.previewGroup) {
                url.searchParams.set('group', this.previewGroup);
            } else {
                url.searchParams.delete('group');
            }
            if (this.previewLevel) {
                url.searchParams.set('level', this.previewLevel);
            } else {
                url.searchParams.delete('level');
            }
            return url.toString();
        },

        markDirty() {
            if (this.sharedComponentEditor.open) {
                this.sharedComponentEditor.dirty = true;
                return;
            }
            this.dirty = true;
        },

        snapshot() {
            return JSON.stringify(this.buildDoc());
        },

        // 訊息本身已經寫明是哪個元件，再前置 page.widgets[1] 這種技術路徑
        // 只會讓使用者看不懂。只有無法定位到元件時才退回顯示 path。
        formatError(err) {
            const message = err.message || tr('驗證失敗');
            if (err.widget_id) return message;
            const path = err.path ? `${err.path}: ` : '';
            return `${path}${message}`;
        },

        issueSummary() {
            const count = this.errors.length;
            const errorCount = this.errors.filter((err) => err.severity !== 'warning').length;
            const warningCount = count - errorCount;
            if (errorCount && warningCount) {
                return tr('{errors} 個錯誤，{warnings} 個警告，點此查看', { errors: errorCount, warnings: warningCount });
            }
            if (errorCount) return tr('{count} 個錯誤，點此查看', { count: errorCount });
            return tr('{count} 個警告，點此查看', { count: warningCount });
        },

        openIssueModal() {
            this.showIssueModal = true;
        },

        closeIssueModal() {
            this.showIssueModal = false;
        },

        canLocateIssue(err) {
            return !!(err && (err.widget_id || this.zoneIdFromIssue(err)));
        },

        zoneIdFromIssue(err) {
            const path = err && err.path ? String(err.path) : '';
            for (const zoneId of Object.keys(this.canvasMeta || {})) {
                if (path.includes(zoneId)) return zoneId;
            }
            return '';
        },

        selectIssueTarget(err) {
            if (!err) return;
            if (err.widget_id && this.findWidget(err.widget_id)) {
                this.selectWidget(err.widget_id);
                this.closeIssueModal();   // 不關的話 modal 正好蓋住剛選取的元件屬性
                return;
            }
            const zoneId = this.zoneIdFromIssue(err);
            if (zoneId && this.canvasMeta[zoneId]) {
                this.selectedZoneId = zoneId;
                this.selectedId = '';
                this.activeWidget = null;
                if (this.engine === 'free') this.refreshFreeFrameContents();
                this.closeIssueModal();
            }
        },
    };
}
