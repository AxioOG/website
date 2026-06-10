// Fuse API connection — loads fuse-api.json, then connects to the backend.
(function() {
    var STORAGE_KEY = 'fuse_api_base';
    var PROBE_PATH = '/api/users?action=banned';
    var remoteConfig = null;
    var cachedBase = null;
    var readyPromise = null;

    function trimBase(value) {
        return String(value || '').replace(/\/$/, '');
    }

    function readMeta(name) {
        var el = document.querySelector('meta[name="' + name + '"]');
        return el && el.content ? trimBase(el.content) : '';
    }

    function readStoredBase() {
        try {
            var params = new URLSearchParams(window.location.search);
            var fromQuery = params.get('fuse_api');
            if (fromQuery) {
                var normalized = trimBase(fromQuery);
                localStorage.setItem(STORAGE_KEY, normalized);
                return normalized;
            }
        } catch (e) {}

        try {
            var stored = localStorage.getItem(STORAGE_KEY);
            if (stored) return trimBase(stored);
        } catch (e) {}

        return '';
    }

    function loadRemoteConfig() {
        if (remoteConfig) return Promise.resolve(remoteConfig);
        return fetch('/fuse-api.json?t=' + Date.now(), { cache: 'no-store', credentials: 'omit' })
            .then(function(res) {
                if (!res.ok) return {};
                return res.json();
            })
            .catch(function() { return {}; })
            .then(function(cfg) {
                remoteConfig = cfg || {};
                return remoteConfig;
            });
    }

    function readConfiguredBase() {
        if (typeof window.FUSE_API_BASE === 'string' && window.FUSE_API_BASE) {
            return trimBase(window.FUSE_API_BASE);
        }

        var stored = readStoredBase();
        if (stored) return stored;

        var metaBase = readMeta('fuse-api-base');
        if (metaBase) return metaBase;

        if (remoteConfig && remoteConfig.apiBase) {
            return trimBase(remoteConfig.apiBase);
        }

        return '';
    }

    function readFallbacks() {
        var list = [];
        var metaFallback = readMeta('fuse-api-fallback');
        if (metaFallback) list.push(metaFallback);

        if (remoteConfig && Array.isArray(remoteConfig.fallbacks)) {
            remoteConfig.fallbacks.forEach(function(url) {
                var base = trimBase(url);
                if (base && list.indexOf(base) === -1) list.push(base);
            });
        }

        return list;
    }

    function looksLikeJsonApiResponse(text) {
        if (!text) return false;
        var trimmed = text.trim();
        if (trimmed.charAt(0) !== '{' && trimmed.charAt(0) !== '[') return false;
        try {
            JSON.parse(trimmed);
            return true;
        } catch (e) {
            return false;
        }
    }

    function probeBase(base) {
        return fetch(base + PROBE_PATH, { method: 'GET', credentials: 'omit' })
            .then(function(res) {
                return res.text().then(function(text) {
                    if (looksLikeJsonApiResponse(text)) return base;
                    throw new Error('invalid');
                });
            });
    }

    function detectApiBase() {
        if (cachedBase) return Promise.resolve(cachedBase);

        return loadRemoteConfig().then(function() {
            var configured = readConfiguredBase();
            if (configured) {
                cachedBase = configured;
                return configured;
            }

            var candidates = [window.location.origin].concat(readFallbacks());
            var seen = {};
            candidates = candidates.filter(function(base) {
                if (!base || seen[base]) return false;
                seen[base] = true;
                return true;
            });

            function tryNext(index) {
                if (index >= candidates.length) {
                    return Promise.reject(new Error(
                        'Could not connect to Fuse API. Set apiBase in fuse-api.json, or deploy with Netlify/Cloudflare Pages functions and add DISCORD_BOT_TOKEN.'
                    ));
                }
                return probeBase(candidates[index]).catch(function() {
                    return tryNext(index + 1);
                });
            }

            return tryNext(0).then(function(base) {
                cachedBase = base;
                try { localStorage.setItem(STORAGE_KEY, base); } catch (e) {}
                return base;
            });
        });
    }

    window.fuseApiReady = function() {
        if (!readyPromise) readyPromise = detectApiBase();
        return readyPromise;
    };

    window.fuseApiConnect = window.fuseApiReady;

    window.getFuseApiBase = function() {
        return cachedBase || readConfiguredBase() || window.location.origin;
    };

    window.fuseApiUrl = function(path) {
        path = path.charAt(0) === '/' ? path : '/' + path;
        return getFuseApiBase() + path;
    };

    window.fuseApiFetch = function(path, options) {
        options = options || {};
        return fuseApiReady().then(function(base) {
            var url = base + (path.charAt(0) === '/' ? path : '/' + path);
            return fetch(url, options);
        });
    };

    window.fuseApiJson = function(path, options) {
        return fuseApiFetch(path, options).then(function(res) {
            return res.text().then(function(text) {
                var data = null;
                try {
                    data = text ? JSON.parse(text) : null;
                } catch (e) {
                    var preview = (text || '').trim().slice(0, 80).toLowerCase();
                    if (preview.indexOf('<!doctype') === 0 || preview.indexOf('<html') === 0) {
                        throw new Error('API returned HTML instead of JSON — check fuse-api.json apiBase points to your Netlify/Cloudflare API host.');
                    }
                    throw new Error('API returned invalid JSON.');
                }
                return { response: res, data: data };
            });
        });
    };

    window.fuseApiReady().catch(function() {});
})();
