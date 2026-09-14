/* icon-picker.js - Remix Icon 精選圖示選擇器 */

var ICON_CATEGORIES = [
    {
        name: 'business',
        label: __('商業'),
        icons: [
            'ri-briefcase-line', 'ri-building-line', 'ri-building-2-line',
            'ri-store-line', 'ri-bank-line', 'ri-money-dollar-circle-line',
            'ri-shopping-cart-line', 'ri-wallet-line', 'ri-coin-line',
            'ri-hand-coin-line', 'ri-pie-chart-line', 'ri-bar-chart-line',
            'ri-line-chart-line', 'ri-funds-line', 'ri-exchange-dollar-line',
            'ri-trophy-line', 'ri-gift-line', 'ri-auction-line'
        ]
    },
    {
        name: 'people',
        label: __('人員'),
        icons: [
            'ri-user-line', 'ri-user-3-line', 'ri-team-line',
            'ri-group-line', 'ri-group-2-line', 'ri-admin-line',
            'ri-user-settings-line', 'ri-user-star-line', 'ri-user-search-line',
            'ri-contacts-line', 'ri-account-circle-line', 'ri-user-add-line'
        ]
    },
    {
        name: 'tech',
        label: __('資訊'),
        icons: [
            'ri-database-line', 'ri-database-2-line', 'ri-server-line',
            'ri-code-line', 'ri-terminal-box-line', 'ri-cpu-line',
            'ri-hard-drive-line', 'ri-wifi-line', 'ri-cloud-line',
            'ri-settings-3-line', 'ri-tools-line', 'ri-bug-line',
            'ri-git-branch-line', 'ri-code-s-slash-line', 'ri-braces-line',
            'ri-terminal-line', 'ri-global-line', 'ri-apps-line'
        ]
    },
    {
        name: 'security',
        label: __('安全'),
        icons: [
            'ri-shield-line', 'ri-shield-check-line', 'ri-shield-keyhole-line',
            'ri-lock-line', 'ri-lock-2-line', 'ri-key-line',
            'ri-key-2-line', 'ri-spy-line', 'ri-fingerprint-line',
            'ri-alarm-warning-line', 'ri-eye-line', 'ri-eye-off-line',
            'ri-shield-user-line', 'ri-shield-star-line', 'ri-door-lock-line'
        ]
    },
    {
        name: 'document',
        label: __('文件'),
        icons: [
            'ri-file-line', 'ri-file-text-line', 'ri-file-list-line',
            'ri-file-copy-line', 'ri-folder-line', 'ri-folder-open-line',
            'ri-clipboard-line', 'ri-book-line', 'ri-book-open-line',
            'ri-newspaper-line', 'ri-archive-line', 'ri-draft-line',
            'ri-file-chart-line', 'ri-file-excel-line', 'ri-file-pdf-line',
            'ri-article-line', 'ri-pages-line', 'ri-survey-line'
        ]
    },
    {
        name: 'communication',
        label: __('通訊'),
        icons: [
            'ri-mail-line', 'ri-mail-send-line', 'ri-chat-3-line',
            'ri-message-2-line', 'ri-phone-line', 'ri-notification-line',
            'ri-megaphone-line', 'ri-discuss-line', 'ri-questionnaire-line',
            'ri-feedback-line', 'ri-at-line', 'ri-send-plane-line'
        ]
    },
    {
        name: 'general',
        label: __('一般'),
        icons: [
            'ri-home-line', 'ri-dashboard-line', 'ri-star-line',
            'ri-heart-line', 'ri-flag-line', 'ri-calendar-line',
            'ri-time-line', 'ri-alarm-line', 'ri-search-line',
            'ri-menu-line', 'ri-list-check', 'ri-checkbox-circle-line',
            'ri-add-circle-line', 'ri-information-line', 'ri-question-line',
            'ri-error-warning-line', 'ri-check-double-line', 'ri-close-circle-line',
            'ri-arrow-right-circle-line', 'ri-link', 'ri-external-link-line',
            'ri-download-line', 'ri-upload-line', 'ri-refresh-line',
            'ri-edit-line', 'ri-delete-bin-line', 'ri-save-line',
            'ri-printer-line', 'ri-filter-line', 'ri-sort-asc'
        ]
    },
    {
        name: 'layout',
        label: __('介面'),
        icons: [
            'ri-layout-line', 'ri-layout-grid-line', 'ri-table-line',
            'ri-gallery-view', 'ri-kanban-view', 'ri-mind-map',
            'ri-organization-chart', 'ri-flow-chart', 'ri-node-tree',
            'ri-grid-line', 'ri-collage-line', 'ri-window-line'
        ]
    }
];

function iconPickerMixin() {
    return {
        _ip_show: false,
        _ip_activeCategory: 'business',
        _ip_search: '',
        _ip_selectedIcon: '',

        ipInit(currentValue) {
            this._ip_selectedIcon = currentValue || '';
        },

        ipOpen() {
            this._ip_show = true;
            this._ip_search = '';
        },

        ipClose() {
            this._ip_show = false;
        },

        ipSelect(iconClass) {
            this._ip_selectedIcon = iconClass;
            this.$refs.iconField.value = iconClass;
            this.ipClose();
        },

        ipClear() {
            this._ip_selectedIcon = '';
            this.$refs.iconField.value = '';
            this.ipClose();
        },

        ipGetCategories() {
            return ICON_CATEGORIES;
        },

        ipGetIcons() {
            var cat = ICON_CATEGORIES.find(function(c) { return c.name === this._ip_activeCategory; }.bind(this));
            var icons = cat ? cat.icons : [];
            var search = this._ip_search.trim().toLowerCase();
            if (!search) return icons;
            return icons.filter(function(ic) {
                return ic.toLowerCase().indexOf(search) >= 0;
            });
        },

        ipSetCategory(name) {
            this._ip_activeCategory = name;
        }
    };
}
