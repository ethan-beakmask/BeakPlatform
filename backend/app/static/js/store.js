/* store.js -- 內部商場 */

function storeManager() {
    return {
        items: [],
        filter: 'all',
        loading: false,
        installing: null,
        errorMsg: '',
        successMsg: '',

        async init() {
            await this.loadItems();
        },

        async loadItems() {
            this.loading = true;
            this.errorMsg = '';
            try {
                let url = window.__BP + '/api/store/items';
                if (this.filter !== 'all') {
                    url += '?type=' + this.filter;
                }
                const resp = await fetch(url);
                const data = await resp.json();
                if (data.success) {
                    this.items = data.data;
                } else {
                    this.errorMsg = data.message || '載入失敗';
                }
            } catch (e) {
                this.errorMsg = '載入失敗: ' + e.message;
            } finally {
                this.loading = false;
            }
        },

        async installItem(item) {
            if (this.installing) return;
            if (!confirm('確定要安裝「' + item.name + '」嗎？\n將匯入表單與流程範本到您的企業。')) return;

            this.installing = item.secure_code;
            this.errorMsg = '';
            this.successMsg = '';

            try {
                const resp = await fetch(window.__BP + '/api/store/items/' + item.secure_code + '/install', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content
                    }
                });
                const data = await resp.json();
                if (data.success) {
                    this.successMsg = data.message;
                    item.installed = true;
                    item.installed_version = item.version;
                    item.installed_by = '您';
                    item.upgradable = false;
                    // 3 秒後清除提示
                    setTimeout(() => { this.successMsg = ''; }, 3000);
                } else {
                    this.errorMsg = data.message || '安裝失敗';
                }
            } catch (e) {
                this.errorMsg = '安裝失敗: ' + e.message;
            } finally {
                this.installing = null;
            }
        },

        typeLabel(type) {
            const labels = {
                'workflow_bundle': '表單+流程',
                'form_template': '表單範本',
                'software': '軟體'
            };
            return labels[type] || type;
        }
    };
}
