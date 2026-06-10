// Netlify function — stores users who sign in
// Uses a simple in-memory + file approach

const { createClient } = require('@netlify/blobs');

exports.handler = async function(event, context) {
    const headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Content-Type',
        'Access-Control-Allow-Methods': 'GET, POST, DELETE, OPTIONS',
        'Content-Type': 'application/json'
    };

    if (event.httpMethod === 'OPTIONS') {
        return { statusCode: 200, headers, body: '' };
    }

    const action = event.queryStringParameters && event.queryStringParameters.action;

    try {
        const store = createClient({ name: 'fuse-data', consistency: 'strong' });

        // ── GET users ──
        if (event.httpMethod === 'GET' && action === 'users') {
            let data = { users: [], banned: [] };
            try {
                const raw = await store.get('data', { type: 'json' });
                if (raw) data = raw;
            } catch(e) {}
            return { statusCode: 200, headers, body: JSON.stringify(data.users || []) };
        }

        // ── GET banned ──
        if (event.httpMethod === 'GET' && action === 'banned') {
            let data = { users: [], banned: [] };
            try {
                const raw = await store.get('data', { type: 'json' });
                if (raw) data = raw;
            } catch(e) {}
            return { statusCode: 200, headers, body: JSON.stringify(data.banned || []) };
        }

        // ── GET check-ban ──
        if (event.httpMethod === 'GET' && action === 'check-ban') {
            const userId = event.queryStringParameters.id;
            let data = { users: [], banned: [] };
            try {
                const raw = await store.get('data', { type: 'json' });
                if (raw) data = raw;
            } catch(e) {}
            const isBanned = (data.banned || []).some(b => b.id === userId);
            return { statusCode: 200, headers, body: JSON.stringify({ banned: isBanned }) };
        }

        // ── POST register ──
        if (event.httpMethod === 'POST' && action === 'register') {
            const user = JSON.parse(event.body || '{}');
            if (!user.id) return { statusCode: 400, headers, body: JSON.stringify({ error: 'Missing user id' }) };

            let data = { users: [], banned: [] };
            try {
                const raw = await store.get('data', { type: 'json' });
                if (raw) data = raw;
            } catch(e) {}

            if ((data.banned || []).some(b => b.id === user.id)) {
                return { statusCode: 403, headers, body: JSON.stringify({ error: 'User is banned' }) };
            }

            const idx = data.users.findIndex(u => u.id === user.id);
            if (idx > -1) { data.users[idx] = user; } else { data.users.push(user); }

            await store.setJSON('data', data);
            return { statusCode: 200, headers, body: JSON.stringify({ success: true }) };
        }

        // ── POST ban ──
        if (event.httpMethod === 'POST' && action === 'ban') {
            const user = JSON.parse(event.body || '{}');
            if (!user.id) return { statusCode: 400, headers, body: JSON.stringify({ error: 'Missing user id' }) };

            let data = { users: [], banned: [] };
            try {
                const raw = await store.get('data', { type: 'json' });
                if (raw) data = raw;
            } catch(e) {}

            if (!data.banned.some(b => b.id === user.id)) {
                data.banned.push(user);
                await store.setJSON('data', data);
            }
            return { statusCode: 200, headers, body: JSON.stringify({ success: true }) };
        }

        // ── DELETE unban ──
        if (event.httpMethod === 'DELETE' && action === 'unban') {
            const userId = event.queryStringParameters.id;

            let data = { users: [], banned: [] };
            try {
                const raw = await store.get('data', { type: 'json' });
                if (raw) data = raw;
            } catch(e) {}

            data.banned = data.banned.filter(b => b.id !== userId);
            await store.setJSON('data', data);
            return { statusCode: 200, headers, body: JSON.stringify({ success: true }) };
        }

        return { statusCode: 400, headers, body: JSON.stringify({ error: 'Unknown action' }) };

    } catch(err) {
        console.error('Function error:', err);
        return { statusCode: 500, headers, body: JSON.stringify({ error: err.message }) };
    }
};
