// Simple JSON-based user storage using GitHub Gist as a backend
// This works without PHP - pure JavaScript solution

const GIST_ID = '7f9e078242e1515e41b2c3b2e4cca2a7';
const GIST_TOKEN = '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';
const GIST_FILE = 'fuse-users.json';

// API wrapper
window.FuseAPI = {
    // Get all users
    getUsers: async function() {
        try {
            const response = await fetch(`https://gist.githubusercontent.com/AxioOG/${GIST_ID}/raw/${GIST_FILE}?t=${Date.now()}`);
            if (!response.ok) {
                // Gist doesn't exist yet, return empty
                return { users: [], banned: [] };
            }
            const data = await response.json();
            return data;
        } catch (err) {
            console.error('[API] Error fetching users:', err);
            return { users: [], banned: [] };
        }
    },

    // Register or update a user
    registerUser: async function(user) {
        try {
            // Get current data
            const data = await this.getUsers();
            
            // Update or add user
            const idx = data.users.findIndex(u => u.id === user.id);
            if (idx > -1) {
                data.users[idx] = user;
            } else {
                data.users.push(user);
            }

            // Write back to Gist
            const response = await fetch(`https://api.github.com/gists/${GIST_ID}`, {
                method: 'PATCH',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `token ${GIST_TOKEN}`
                },
                body: JSON.stringify({
                    files: {
                        [GIST_FILE]: {
                            content: JSON.stringify(data, null, 2)
                        }
                    }
                })
            });

            if (!response.ok) {
                const error = await response.json();
                console.error('[API] Gist write error:', error);
                return { success: false, error: error.message };
            }

            return { success: true };
        } catch (err) {
            console.error('[API] Register error:', err);
            return { success: false, error: err.message };
        }
    },

    // Ban a user
    banUser: async function(user) {
        try {
            const data = await this.getUsers();
            
            // Check if already banned
            if (!data.banned.find(u => u.id === user.id)) {
                data.banned.push(user);
            }

            // Write back
            const response = await fetch(`https://api.github.com/gists/${GIST_ID}`, {
                method: 'PATCH',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `token ${GIST_TOKEN}`
                },
                body: JSON.stringify({
                    files: {
                        [GIST_FILE]: {
                            content: JSON.stringify(data, null, 2)
                        }
                    }
                })
            });

            return { success: response.ok };
        } catch (err) {
            console.error('[API] Ban error:', err);
            return { success: false };
        }
    },

    // Unban a user
    unbanUser: async function(userId) {
        try {
            const data = await this.getUsers();
            data.banned = data.banned.filter(u => u.id !== userId);

            const response = await fetch(`https://api.github.com/gists/${GIST_ID}`, {
                method: 'PATCH',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `token ${GIST_TOKEN}`
                },
                body: JSON.stringify({
                    files: {
                        [GIST_FILE]: {
                            content: JSON.stringify(data, null, 2)
                        }
                    }
                })
            });

            return { success: response.ok };
        } catch (err) {
            console.error('[API] Unban error:', err);
            return { success: false };
        }
    },

    // Check if user is banned
    checkBan: async function(userId) {
        try {
            const data = await this.getUsers();
            return data.banned.some(u => u.id === userId);
        } catch (err) {
            return false;
        }
    }
};
