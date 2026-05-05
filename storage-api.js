// Fuse Storage API - Pure client-side, no external services
// Uses hidden iframe for cross-tab communication

(function() {
    let storageFrame = null;
    let isReady = false;
    let pendingCallbacks = [];

    // Create hidden iframe for shared storage
    function initStorage() {
        if (storageFrame) return;

        console.log('[FuseAPI] Initializing storage iframe...');

        storageFrame = document.createElement('iframe');
        storageFrame.src = '/shared-storage.html';
        storageFrame.style.display = 'none';
        
        storageFrame.onload = function() {
            console.log('[FuseAPI] Storage iframe loaded');
        };
        
        storageFrame.onerror = function(err) {
            console.error('[FuseAPI] Storage iframe failed to load:', err);
        };
        
        document.body.appendChild(storageFrame);

        // Listen for messages from storage iframe
        window.addEventListener('message', function(event) {
            if (event.origin !== window.location.origin) {
                console.warn('[FuseAPI] Ignored message from different origin:', event.origin);
                return;
            }

            const { action } = event.data;
            console.log('[FuseAPI] Received message:', action);

            if (action === 'STORAGE_READY') {
                console.log('[FuseAPI] ✓ Storage is ready');
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
        
        // Timeout fallback
        setTimeout(function() {
            if (!isReady) {
                console.error('[FuseAPI] Storage iframe did not respond within 5 seconds');
            }
        }, 5000);
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
        return new Promise(function(resolve, reject) {
            console.log('[FuseAPI] Sending message:', action, data);
            
            whenReady(function() {
                if (!storageFrame || !storageFrame.contentWindow) {
                    console.error('[FuseAPI] Storage iframe not available');
                    reject(new Error('Storage iframe not available'));
                    return;
                }
                
                storageFrame.contentWindow.postMessage({ action, data }, window.location.origin);
                
                // Set up one-time callback
                window.FuseStorageCallbacks = window.FuseStorageCallbacks || {};
                
                if (action === 'GET_USERS') {
                    window.FuseStorageCallbacks['USERS_DATA'] = function(data) {
                        console.log('[FuseAPI] Received users data:', data.users.length, 'users');
                        resolve({ users: data.users, banned: data.banned });
                        delete window.FuseStorageCallbacks['USERS_DATA'];
                    };
                } else if (action === 'CHECK_BAN') {
                    window.FuseStorageCallbacks['BAN_STATUS'] = function(data) {
                        console.log('[FuseAPI] Ban status for', data.userId, ':', data.banned);
                        resolve(data.banned);
                        delete window.FuseStorageCallbacks['BAN_STATUS'];
                    };
                } else {
                    // For other actions, wait for success response
                    const successAction = action.replace('_USER', '_SUCCESS');
                    window.FuseStorageCallbacks[successAction] = function() {
                        console.log('[FuseAPI] Action completed:', action);
                        resolve({ success: true });
                        delete window.FuseStorageCallbacks[successAction];
                    };
                }
                
                // Timeout after 3 seconds
                setTimeout(function() {
                    if (action === 'GET_USERS' && window.FuseStorageCallbacks['USERS_DATA']) {
                        console.error('[FuseAPI] Timeout waiting for response to:', action);
                        reject(new Error('Timeout'));
                    }
                }, 3000);
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
