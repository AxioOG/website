// Netlify serverless function — ban/unban users (legacy endpoint)
// Bot token: Netlify env var DISCORD_BOT_TOKEN (see members.js for Discord API usage)

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
    const userId = event.queryStringParameters && event.queryStringParameters.id;

    try {
        // ── GET ?action=list ── get all fuse-banned users
        if (event.httpMethod === 'GET' && action === 'list') {
            // Read from environment variable or return empty
            let banned = [];
            try {
                banned = JSON.parse(process.env.FUSE_BANNED || '[]');
            } catch(e) { banned = []; }
            return { statusCode: 200, headers, body: JSON.stringify({ banned }) };
        }

        // ── GET ?action=check&id=USER_ID ── check if user is banned
        if (event.httpMethod === 'GET' && action === 'check' && userId) {
            let banned = [];
            try { banned = JSON.parse(process.env.FUSE_BANNED || '[]'); } catch(e) {}
            const isBanned = banned.some(b => b.id === userId);
            return { statusCode: 200, headers, body: JSON.stringify({ banned: isBanned }) };
        }

        // ── POST ?action=ban ── ban a user
        if (event.httpMethod === 'POST' && action === 'ban') {
            const body = JSON.parse(event.body || '{}');
            return { statusCode: 200, headers, body: JSON.stringify({ success: true, user: body }) };
        }

        // ── DELETE ?action=unban&id=USER_ID ── unban a user
        if (event.httpMethod === 'DELETE' && action === 'unban' && userId) {
            return { statusCode: 200, headers, body: JSON.stringify({ success: true }) };
        }

        return { statusCode: 400, headers, body: JSON.stringify({ error: 'Unknown action' }) };

    } catch(err) {
        return { statusCode: 500, headers, body: JSON.stringify({ error: err.message }) };
    }
};
