// Fuse Storage API - Pure client-side, no external services
// Uses hidden iframe for cross-tab communication

(function() {
    let storageFrame = null;
    let isReady = false;
    let pendingCallbacks = [];

    // Create hidden iframe for shared storage
    function initStorage() {
        if (storageFrame) return;

        storageFrame = document.createElement('iframe');
        storageFrame.src = '/shared-storage.html';
        storageFrame.style.display = 'none';
        document.body.appendChild(storageFrame);

        // Listen for messages from storage iframe
        window.addEventListener('message', function(event) {
            if (event.origin !== window.location.origin) return;

            const { action } = event.data;

            if (action === 'STORAGE_READY') {
                isReady = true;
                // Execute pending callbacks
                pendingCallbacks.forEach(cb => cb());
                pendingCallbacks = [];
            }

            // Handle responses
            if (window.FuseStorageCallbacks && window.FuseStorageCallbacks[action]) {
                window.FuseStorageCallbacks[action](event.data);
            }
        });
    }

    // Wait for storage to be ready
    function whenReady(callback) {
        if (isReady) {
            callback();
        } else {
            pendingCallbacks.push(callback);
        }
    }

    // Send message to storage iframe
    function sendMessage(action, data) {
        return new Promise(function(resolve) {
            whenReady(function() {
                storageFrame.contentWindow.postMessage({ action, data }, window.location.origin);
                
                // Set up one-time callback
                const responseAction = action.replace('GET_', '').replace('REGISTER_', 'REGISTER_').replace('BAN_', 'BAN_').replace('UNBAN_', 'UNBAN_').replace('CHECK_', '') + '_';
                
                window.FuseStorageCallbacks = window.FuseStorageCallbacks || {};
                
                if (action === 'GET_USERS') {
                    window.FuseStorageCallbacks['USERS_DATA'] = function(data) {
                        resolve({ users: data.users, banned: data.banned });
                        delete window.FuseStorageCallbacks['USERS_DATA'];
                    };
                } else if (action === 'CHECK_BAN') {
                    window.FuseStorageCallbacks['BAN_STATUS'] = function(data) {
                        resolve(data.banned);
                        delete window.FuseStorageCallbacks['BAN_STATUS'];
                    };
                } else {
                    // For other actions, just resolve immediately
                    setTimeout(function() { resolve({ success: true }); }, 100);
                }
            });
        });
    }

    // Public API
    window.FuseAPI = {
        init: function() {
            if (document.readyState === 'loading') {
                document.addEventListener('DOMContentLoaded', initStorage);
            } else {
                initStorage();
            }
        },

        getUsers: function() {
            return sendMessage('GET_USERS', null);
        },

        registerUser: function(user) {
            console.log('[FuseAPI] Registering user:', user.username);
            return sendMessage('REGISTER_USER', user);
        },

        banUser: function(user) {
            console.log('[FuseAPI] Banning user:', user.username);
            return sendMessage('BAN_USER', user);
        },

        unbanUser: function(userId) {
            console.log('[FuseAPI] Unbanning user:', userId);
            return sendMessage('UNBAN_USER', { id: userId });
        },

        checkBan: function(userId) {
            return sendMessage('CHECK_BAN', { id: userId });
        }
    };

    // Auto-initialize
    window.FuseAPI.init();

    // Listen for storage changes from other tabs
    window.addEventListener('storage', function(e) {
        if (e.key === 'fuse_update_trigger' && window.onFuseStorageUpdate) {
            window.onFuseStorageUpdate();
        }
    });
})();
