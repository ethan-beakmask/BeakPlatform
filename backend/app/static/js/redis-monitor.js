/**
 * redis-monitor.js - Redis 監看頁面
 */

function redisMonitor() {
    return {
        // State
        tab: 'overview',
        loading: false,
        connected: false,
        errorMsg: '',
        lastRefresh: '',
        info: null,
        rawInfo: {},

        // Keys tab
        keyDb: 0,
        keyPattern: '*',
        keyCursor: 0,
        keysResult: [],
        keysLoading: false,
        keysLoaded: false,
        keysHasMore: false,
        keyDetail: null,

        // Slowlog tab
        slowlogEntries: [],
        slowlogLoading: false,
        slowlogLoaded: false,

        // Auto-refresh timer
        _timer: null,

        init: function() {
            this.loadInfo();
            // 每 30 秒自動刷新總覽
            var self = this;
            this._timer = setInterval(function() {
                if (self.tab === 'overview') {
                    self.loadInfo();
                }
            }, 30000);
        },

        destroy: function() {
            if (this._timer) clearInterval(this._timer);
        },

        loadInfo: function() {
            var self = this;
            self.loading = true;
            fetch('/bp/server-manage/api/redis/info')
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    if (data.ok) {
                        self.info = data.data;
                        self.connected = true;
                        self.errorMsg = '';
                        self.rawInfo = data.data;
                    } else {
                        self.connected = false;
                        self.errorMsg = data.error || 'Unknown error';
                    }
                })
                .catch(function(err) {
                    self.connected = false;
                    self.errorMsg = 'Fetch failed: ' + err.message;
                })
                .finally(function() {
                    self.loading = false;
                    self.lastRefresh = new Date().toLocaleTimeString('zh-TW', { hour12: false });
                });
        },

        // ── Key 瀏覽 ──

        scanKeys: function(reset) {
            if (reset) {
                this.keyCursor = 0;
                this.keysResult = [];
                this.keyDetail = null;
            }
            var self = this;
            self.keysLoading = true;

            var params = new URLSearchParams({
                cursor: self.keyCursor,
                pattern: self.keyPattern || '*',
                count: 50,
                db: self.keyDb
            });

            fetch('/bp/server-manage/api/redis/keys?' + params.toString())
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    if (data.ok) {
                        self.keysResult = self.keysResult.concat(data.keys);
                        self.keyCursor = data.cursor;
                        self.keysHasMore = data.has_more;
                        self.keysLoaded = true;
                    } else {
                        self.errorMsg = data.error;
                    }
                })
                .catch(function(err) {
                    self.errorMsg = 'Fetch keys failed: ' + err.message;
                })
                .finally(function() {
                    self.keysLoading = false;
                });
        },

        viewKey: function(keyName) {
            var self = this;
            var params = new URLSearchParams({ db: self.keyDb });
            fetch('/bp/server-manage/api/redis/key/' + encodeURIComponent(keyName) + '?' + params.toString())
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    if (data.ok) {
                        self.keyDetail = data;
                    } else {
                        self.keyDetail = { key: keyName, type: '-', ttl: 0, memory: 0, value: data.error, truncated: false };
                    }
                })
                .catch(function(err) {
                    self.keyDetail = { key: keyName, type: '-', ttl: 0, memory: 0, value: 'Error: ' + err.message, truncated: false };
                });
        },

        // ── 慢查詢 ──

        loadSlowlog: function() {
            var self = this;
            self.slowlogLoading = true;
            fetch('/bp/server-manage/api/redis/slowlog')
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    if (data.ok) {
                        self.slowlogEntries = data.entries;
                        self.slowlogLoaded = true;
                    } else {
                        self.errorMsg = data.error;
                    }
                })
                .catch(function(err) {
                    self.errorMsg = 'Fetch slowlog failed: ' + err.message;
                })
                .finally(function() {
                    self.slowlogLoading = false;
                });
        },

        // ── 完整 INFO (分兩欄) ──

        infoLeft: function() {
            var result = {};
            var keys = Object.keys(this.rawInfo);
            var half = Math.ceil(keys.length / 2);
            for (var i = 0; i < half; i++) {
                var k = keys[i];
                if (k !== 'databases' && typeof this.rawInfo[k] !== 'object') {
                    result[k] = this.rawInfo[k];
                }
            }
            return result;
        },

        infoRight: function() {
            var result = {};
            var keys = Object.keys(this.rawInfo);
            var half = Math.ceil(keys.length / 2);
            for (var i = half; i < keys.length; i++) {
                var k = keys[i];
                if (k !== 'databases' && typeof this.rawInfo[k] !== 'object') {
                    result[k] = this.rawInfo[k];
                }
            }
            return result;
        },

        // ── 格式化工具 ──

        formatUptime: function(seconds) {
            if (!seconds) return '-';
            var d = Math.floor(seconds / 86400);
            var h = Math.floor((seconds % 86400) / 3600);
            var m = Math.floor((seconds % 3600) / 60);
            if (d > 0) return d + 'd ' + h + 'h';
            if (h > 0) return h + 'h ' + m + 'm';
            return m + 'm';
        },

        formatBytes: function(bytes) {
            if (bytes === null || bytes === undefined) return '-';
            if (bytes < 1024) return bytes + ' B';
            if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
            if (bytes < 1073741824) return (bytes / 1048576).toFixed(1) + ' MB';
            return (bytes / 1073741824).toFixed(2) + ' GB';
        },

        formatDuration: function(us) {
            if (!us && us !== 0) return '-';
            if (us < 1000) return us + ' us';
            if (us < 1000000) return (us / 1000).toFixed(1) + ' ms';
            return (us / 1000000).toFixed(2) + ' s';
        },

        formatValue: function(value, type) {
            if (value === null || value === undefined) return '(nil)';
            if (typeof value === 'string') return value;
            try {
                return JSON.stringify(value, null, 2);
            } catch (e) {
                return String(value);
            }
        }
    };
}
