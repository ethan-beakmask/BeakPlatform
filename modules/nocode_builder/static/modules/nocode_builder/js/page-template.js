/* global __ */
(function () {
    const BP = window.__BP || '';
    const VIEW_W = 160;
    const VIEW_H = 100;
    const MAX_SVG_LEN = 8000;

    function tr(text, params) {
        return window.__ ? window.__(text, params) : text;
    }

    function num(value, fallback) {
        const n = Number(value);
        return Number.isFinite(n) ? n : fallback;
    }

    function clamp(value, min, max) {
        return Math.max(min, Math.min(max, value));
    }

    function getPage(layoutJson) {
        return layoutJson && layoutJson.page ? layoutJson.page : {};
    }

    function svgWrap(body) {
        return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${VIEW_W} ${VIEW_H}" preserveAspectRatio="xMidYMid meet"><rect x="0" y="0" width="${VIEW_W}" height="${VIEW_H}" fill="#f5f5f5"/>${body}</svg>`;
    }

    function fallbackSvg(layoutJson) {
        const count = ((getPage(layoutJson).widgets || []).length || 0);
        const bars = Math.max(1, Math.min(6, count || 3));
        const gap = 6;
        const h = (VIEW_H - gap * (bars + 1)) / bars;
        let body = '';
        for (let i = 0; i < bars; i += 1) {
            const y = gap + i * (h + gap);
            body += `<rect x="12" y="${y.toFixed(2)}" width="136" height="${h.toFixed(2)}" fill="#dcdcdc"/>`;
        }
        return svgWrap(body);
    }

    function finishSvg(layoutJson, body) {
        const svg = svgWrap(body);
        return svg.length <= MAX_SVG_LEN ? svg : fallbackSvg(layoutJson);
    }

    function cumulative(values, total) {
        const clean = (values || []).map((v) => Math.max(0.1, num(v, 1)));
        const sum = clean.reduce((acc, v) => acc + v, 0) || 1;
        let pos = 0;
        return clean.map((v) => {
            const size = (v / sum) * total;
            const item = { start: pos, size };
            pos += size;
            return item;
        });
    }

    function gridSvg(layoutJson, page) {
        const canvas = page.canvas || layoutJson.canvas || {};
        const cols = cumulative(canvas.col_widths && canvas.col_widths.length ? canvas.col_widths : [1, 1, 1], VIEW_W);
        const rows = cumulative(canvas.row_heights && canvas.row_heights.length ? canvas.row_heights : [1, 1], VIEW_H);
        let body = '';
        for (let i = 1; i < cols.length; i += 1) {
            body += `<line x1="${cols[i].start.toFixed(2)}" y1="0" x2="${cols[i].start.toFixed(2)}" y2="${VIEW_H}" stroke="#dcdcdc" stroke-width="1"/>`;
        }
        for (let i = 1; i < rows.length; i += 1) {
            body += `<line x1="0" y1="${rows[i].start.toFixed(2)}" x2="${VIEW_W}" y2="${rows[i].start.toFixed(2)}" stroke="#dcdcdc" stroke-width="1"/>`;
        }
        for (const zone of (canvas.zones || [])) {
            // IR 的 row / col 是 1-based（schema minimum: 1），陣列索引要減 1。
            // 當成 0-based 用的話所有 zone 會擠到同一格互相蓋掉，
            // 縮圖看起來只剩右下一塊。
            const r = clamp(Math.floor(num(zone.row, 1)) - 1, 0, rows.length - 1);
            const c = clamp(Math.floor(num(zone.col, 1)) - 1, 0, cols.length - 1);
            const rs = clamp(Math.floor(num(zone.row_span || zone.rowSpan, 1)), 1, rows.length - r);
            const cs = clamp(Math.floor(num(zone.col_span || zone.colSpan, 1)), 1, cols.length - c);
            const x = cols[c].start + 3;
            const y = rows[r].start + 3;
            const w = cols.slice(c, c + cs).reduce((acc, item) => acc + item.size, 0) - 6;
            const h = rows.slice(r, r + rs).reduce((acc, item) => acc + item.size, 0) - 6;
            const fill = (zone.widget_ids || []).length ? '#b8c4d0' : '#e6e6e6';
            body += `<rect x="${x.toFixed(2)}" y="${y.toFixed(2)}" width="${Math.max(2, w).toFixed(2)}" height="${Math.max(2, h).toFixed(2)}" fill="${fill}" stroke="#9aa7b3" stroke-width="1"/>`;
        }
        return finishSvg(layoutJson, body);
    }

    function freeSvg(layoutJson, page) {
        const canvas = page.canvas || layoutJson.canvas || {};
        const rowUnit = Math.max(1, num(canvas.row_unit, 60));
        const frames = canvas.frames || [];
        const maxRows = Math.max(1, ...frames.map((frame) => num(frame.y, 0) + num(frame.h, 1)));
        const yScale = VIEW_H / Math.max(rowUnit, maxRows * rowUnit);
        let body = '';
        for (const frame of frames) {
            const x = (clamp(num(frame.x, 0), 0, 12) / 12) * VIEW_W + 3;
            const w = (clamp(num(frame.w, 1), 1, 12) / 12) * VIEW_W - 6;
            const y = num(frame.y, 0) * rowUnit * yScale + 3;
            const h = Math.max(1, num(frame.h, 1) * rowUnit * yScale - 6);
            const fill = (frame.widget_ids || []).length ? '#b8c4d0' : '#e6e6e6';
            body += `<rect x="${x.toFixed(2)}" y="${y.toFixed(2)}" width="${Math.max(2, w).toFixed(2)}" height="${Math.max(2, h).toFixed(2)}" fill="${fill}" stroke="#9aa7b3" stroke-width="1"/>`;
        }
        return finishSvg(layoutJson, body);
    }

    function flowSvg(layoutJson, page) {
        const widgets = page.widgets || [];
        const visible = widgets.slice(0, 6);
        const gap = 6;
        const h = visible.length ? (VIEW_H - gap * (visible.length + 1)) / visible.length : 18;
        let body = '';
        for (let i = 0; i < visible.length; i += 1) {
            const y = gap + i * (h + gap);
            body += `<rect x="12" y="${y.toFixed(2)}" width="136" height="${Math.max(4, h).toFixed(2)}" fill="#b8c4d0" stroke="#9aa7b3" stroke-width="1"/>`;
        }
        if (widgets.length > 6) {
            body += '<path d="M 14 92 H 146" stroke="#9aa7b3" stroke-width="2" stroke-dasharray="5 4" fill="none"/>';
        }
        return finishSvg(layoutJson, body || '<rect x="20" y="32" width="120" height="36" fill="#dcdcdc" stroke="#9aa7b3" stroke-width="1"/>');
    }

    function buildThumbnailSvg(layoutJson) {
        const page = getPage(layoutJson || {});
        const engine = page.engine === 'grid' || page.engine === 'free' ? page.engine : 'flow';
        if (engine === 'grid') return gridSvg(layoutJson || {}, page);
        if (engine === 'free') return freeSvg(layoutJson || {}, page);
        return flowSvg(layoutJson || {}, page);
    }

    function isSupported(layoutJson) {
        return !!layoutJson && layoutJson.ir_version === 3;
    }

    function describeReport(report) {
        const lines = [];
        const removedType = {
            table: tr('表格'),
            detail: tr('明細'),
            master_detail: tr('主從表'),
        };
        const warningKind = {
            action_ref: tr('動作'),
            permission: tr('按鈕權限'),
            submit_action_ref: tr('表單送出動作'),
            access_matrix: tr('元件存取權限'),
        };
        for (const item of ((report && report.removed_widgets) || [])) {
            if (item.reason === 'binding_unavailable') {
                const type = removedType[item.type] || item.type || tr('元件');
                lines.push(`${type}${item.id ? ` ${item.id} ` : ' '}${tr('因資料來源不屬於此子系統而移除')}`);
            }
        }
        const cleared = (report && report.cleared) || {};
        const clearedMap = [
            ['menu_nodes', tr('已移除 {count} 個選單項目（指向其他子系統的網頁）')],
            ['menu_nav_sources', tr('已取消 {count} 個選單的聯動設定（來源選單項目已不存在）')],
            ['background_files', tr('已清除 {count} 張選單底圖（來自其他企業）')],
            ['mapping_refs', tr('已清除 {count} 個表單流程綁定')],
            ['row_link_refs', tr('已清除 {count} 個列連結設定')],
            ['row_actions_refs', tr('已清除 {count} 個列動作設定')],
        ];
        for (const [key, template] of clearedMap) {
            const count = Number(cleared[key] || 0);
            if (count > 0) lines.push(template.replace('{count}', count));
        }
        for (const warning of ((report && report.warnings) || [])) {
            const kind = warningKind[warning.kind] || warning.kind || tr('設定');
            lines.push(`${kind}${tr('請確認此子系統有權限碼『{value}』', { value: warning.value || '' })}`);
        }
        return { lines, hasIssue: lines.length > 0 };
    }

    async function fetchTemplates(subSystemSc) {
        const url = new URL(`${BP}/api/nocode-builder/templates`, window.location.origin);
        if (subSystemSc) url.searchParams.set('sub_system', subSystemSc);
        const res = await fetch(url.toString());
        const data = await res.json();
        if (!res.ok || !data.success) throw new Error(data.error || tr('載入樣板失敗'));
        return data.data || [];
    }

    window.BkPageTemplate = {
        buildThumbnailSvg,
        isSupported,
        describeReport,
        fetchTemplates,
    };
}());
