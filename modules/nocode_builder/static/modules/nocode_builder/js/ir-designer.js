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
        previewGroup: '',
        previewLevel: '',
        portalOrgLoaded: false,
        portalOrgScope: '',
        portalGroups: [],
        portalLevels: [],
        selectedId: '',
        activeWidget: null,
        errors: [],
        dirty: false,
        savedSnapshot: '',
        dragType: '',
        counters: {},
        showFormModal: false,
        formBuilder: null,
        formBuilderWidget: null,
        palette: [
            { type: 'layout', label: tr('版面') },
            { type: 'text', label: tr('文字') },
            { type: 'table', label: tr('表格') },
            { type: 'detail', label: tr('明細') },
            { type: 'master_detail', label: tr('主細表') },
            { type: 'actions', label: tr('動作') },
            { type: 'form', label: tr('表單') },
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

        async init() {
            const cfg = window.__IR_DESIGNER_CONFIG || {};
            this.secureCode = cfg.secureCode || '';
            this.designerUrl = cfg.designerUrl || '';
            this.previewUrl = cfg.previewUrl || '';
            await Promise.all([this.loadPage(), this.loadSubSystems(), this.loadMeta(this.dataScope), this.loadFormMappings()]);
            await this.detectPortalScope();
            await this.ensurePortalOrg();
            this.syncCounters();
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
                if (widget.type === 'table' && !widget.default_sort) {
                    const first = (widget.binding && widget.binding.fields && widget.binding.fields[0]) || '';
                    widget.default_sort = { field: first, dir: 'asc' };
                }
                if (widget.type === 'table') this.normalizeMasks(widget.columns || []);
                if (widget.type === 'detail') this.normalizeMasks(widget.fields || []);
                if (widget.type === 'master_detail') this.normalizeMasterDetailWidget(widget);
                if (widget.type === 'layout') this.normalizeWidgets(widget.children || []);
            }
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
                    for (const action of ['read', 'create', 'update', 'delete']) {
                        if (matrix[action] && Array.isArray(matrix[action].groups) && matrix[action].groups.length === 0) {
                            matrix[action].groups = null;
                        }
                    }
                    for (const action of Object.keys(matrix)) {
                        if (!matrix[action] || Object.keys(matrix[action]).length === 0) {
                            delete matrix[action];
                        }
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
                if (widget.type === 'table') this.normalizeMasks(widget.columns || []);
                if (widget.type === 'detail') this.normalizeMasks(widget.fields || []);
                if (widget.type === 'master_detail') this.normalizeMasterDetailWidget(widget);
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
            this.previewGroup = '';
            this.previewLevel = '';
            await this.loadMeta(this.dataScope);
            await this.ensurePortalOrg();
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
                    this.portalOrgScope = '';
                    this.portalOrgLoaded = false;
                    console.warn('[IR Designer] portal org load failed:', data.error || data);
                    return;
                }
                const orgData = data.data || {};
                this.portalGroups = orgData.groups || [];
                this.portalLevels = orgData.levels || [];
                this.portalOrgScope = this.dataScope;
                this.portalOrgLoaded = true;
                this.syncPreviewIdentity();
            } catch (err) {
                this.portalGroups = [];
                this.portalLevels = [];
                this.portalOrgScope = '';
                this.portalOrgLoaded = false;
                console.warn('[IR Designer] portal org load failed:', err);
            }
        },

        activePortalGroups() {
            return (this.portalGroups || []).filter((group) => group && group.code && group.is_active !== false);
        },

        sortedPortalLevels() {
            return [...(this.portalLevels || [])]
                .filter((level) => level && level.code && level.is_active !== false)
                .sort((a, b) => Number(a.rank || 0) - Number(b.rank || 0));
        },

        defaultWidgetMinLevel() {
            const levels = this.sortedPortalLevels();
            if (levels.some((level) => level.code === 'GUEST')) return 'GUEST';
            return (levels[0] && levels[0].code) || 'GUEST';
        },

        syncPreviewIdentity() {
            if (this.previewGroup && !this.activePortalGroups().some((group) => group.code === this.previewGroup)) {
                this.previewGroup = '';
            }
            const levels = this.sortedPortalLevels();
            if (!levels.some((level) => level.code === this.previewLevel)) {
                this.previewLevel = this.defaultWidgetMinLevel();
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
                    widget.access_matrix[action] = { groups: null, min_level: this.defaultWidgetMinLevel() };
                }
            } else if (widget.access_matrix) {
                delete widget.access_matrix[action];
                if (Object.keys(widget.access_matrix).length === 0) {
                    delete widget.access_matrix;
                }
            }
            this.markDirty();
        },

        widgetGroupMode(action) {
            const widget = this.selectedWidget;
            const rule = widget && widget.access_matrix && widget.access_matrix[action];
            return rule && Array.isArray(rule.groups) ? 'limited' : 'all';
        },

        setWidgetGroupMode(action, mode) {
            const widget = this.selectedWidget;
            const rule = widget && widget.access_matrix && widget.access_matrix[action];
            if (!rule) return;
            rule.groups = mode === 'limited' ? (Array.isArray(rule.groups) ? rule.groups : []) : null;
            this.markDirty();
        },

        toggleWidgetGroup(action, code) {
            const widget = this.selectedWidget;
            const rule = widget && widget.access_matrix && widget.access_matrix[action];
            if (!rule || !code) return;
            if (!Array.isArray(rule.groups)) rule.groups = [];
            const index = rule.groups.indexOf(code);
            if (index >= 0) {
                rule.groups.splice(index, 1);
            } else {
                rule.groups.push(code);
            }
            this.markDirty();
        },

        widgetActionGroups(action) {
            const widget = this.selectedWidget;
            const rule = widget && widget.access_matrix && widget.access_matrix[action];
            return rule && Array.isArray(rule.groups) ? rule.groups : [];
        },

        widgetActionMinLevel(action) {
            const widget = this.selectedWidget;
            const rule = widget && widget.access_matrix && widget.access_matrix[action];
            return (rule && rule.min_level) || this.defaultWidgetMinLevel();
        },

        setWidgetActionMinLevel(action, code) {
            const widget = this.selectedWidget;
            const rule = widget && widget.access_matrix && widget.access_matrix[action];
            if (!rule || !code) return;
            rule.min_level = code;
            this.markDirty();
        },

        get selectedWidget() {
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
            const widget = this.newWidget(type);
            const selected = this.selectedWidget;
            if (selected && selected.type === 'layout') {
                selected.children.push(widget);
            } else {
                this.doc.page.widgets.push(widget);
            }
            this.selectedId = widget.id;
            this.activeWidget = widget;
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

        selectWidget(id) {
            this.selectedId = id;
            this.activeWidget = this.findWidget(id);
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
            if (this.selectedId === id) {
                this.selectedId = '';
                this.activeWidget = null;
            }
            this.markDirty();
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
            this.normalizeWidgetMasks(doc.page.widgets || []);
            this.normalizeAccessMatrix(doc.page.widgets || []);
            this.normalizeActionButtons(doc.page.widgets || []);
            return doc;
        },

        async savePage() {
            this.errors = [];
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
                    return;
                }
                this.pageName = data.data.name || body.name;
                this.dirty = false;
                this.savedSnapshot = this.snapshot();
                alert(tr('已儲存'));
            } catch (err) {
                this.errors = [{ path: '', message: err.message || tr('儲存失敗') }];
            }
        },

        previewPage() {
            if (this.dirty || this.snapshot() !== this.savedSnapshot) {
                alert(tr('請先儲存'));
                return;
            }
            if (!this.dataScope) {
                window.open(this.previewUrl, '_blank');
                return;
            }
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
            window.open(url.toString(), '_blank');
        },

        markDirty() {
            this.dirty = true;
        },

        snapshot() {
            return JSON.stringify(this.buildDoc());
        },

        formatError(err) {
            const path = err.path ? `${err.path}: ` : '';
            return `${path}${err.message || tr('驗證失敗')}`;
        },
    };
}
