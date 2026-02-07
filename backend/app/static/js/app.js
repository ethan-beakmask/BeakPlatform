/**
 * BeakMask Frontend Application
 * Core JavaScript functionality
 */

// Global app state and functions
function app() {
    return {
        loading: false,
        toast: {
            show: false,
            message: '',
            type: 'info' // success, error, warning, info
        },

        init() {
            // Check for flash messages
            this.checkFlashMessages();
        },

        // Show toast notification
        showToast(message, type = 'info', duration = 3000) {
            this.toast.message = message;
            this.toast.type = type;
            this.toast.show = true;

            setTimeout(() => {
                this.toast.show = false;
            }, duration);
        },

        // Check for server-side flash messages
        checkFlashMessages() {
            const flashElement = document.getElementById('flash-messages');
            if (flashElement) {
                const messages = JSON.parse(flashElement.dataset.messages || '[]');
                messages.forEach(([type, message]) => {
                    this.showToast(message, type);
                });
            }
        },

        // Set loading state
        setLoading(state) {
            this.loading = state;
        }
    };
}

// API Helper
const API = {
    csrfToken: document.querySelector('meta[name="csrf-token"]')?.content,

    async request(url, options = {}) {
        const defaultOptions = {
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': this.csrfToken
            }
        };

        const mergedOptions = {
            ...defaultOptions,
            ...options,
            headers: {
                ...defaultOptions.headers,
                ...options.headers
            }
        };

        try {
            const response = await fetch(url, mergedOptions);

            // Handle unauthorized (redirect to login)
            if (response.status === 401) {
                window.location.href = '/auth/login';
                return null;
            }

            // Handle forbidden
            if (response.status === 403) {
                throw new Error('您沒有權限執行此操作');
            }

            return response;
        } catch (error) {
            console.error('API Error:', error);
            throw error;
        }
    },

    async get(url) {
        return this.request(url, { method: 'GET' });
    },

    async post(url, data) {
        return this.request(url, {
            method: 'POST',
            body: JSON.stringify(data)
        });
    },

    async put(url, data) {
        return this.request(url, {
            method: 'PUT',
            body: JSON.stringify(data)
        });
    },

    async delete(url) {
        return this.request(url, { method: 'DELETE' });
    }
};

// Utility functions
const Utils = {
    // Format date
    formatDate(dateString, options = {}) {
        const date = new Date(dateString);
        return date.toLocaleDateString('zh-TW', {
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            ...options
        });
    },

    // Format datetime
    formatDateTime(dateString) {
        const date = new Date(dateString);
        return date.toLocaleString('zh-TW');
    },

    // Debounce function
    debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    },

    // Copy to clipboard
    async copyToClipboard(text) {
        try {
            await navigator.clipboard.writeText(text);
            return true;
        } catch (err) {
            console.error('Failed to copy:', err);
            return false;
        }
    }
};

// Confirm dialog
function confirmDialog(message = '確定要執行此操作嗎？') {
    return new Promise((resolve) => {
        if (confirm(message)) {
            resolve(true);
        } else {
            resolve(false);
        }
    });
}

// Export for use in templates
window.API = API;
window.Utils = Utils;
window.confirmDialog = confirmDialog;
