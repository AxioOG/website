// Netlify serverless function — fetches all guild members using bot token
// Bot token stays server-side, never exposed to the browser

const GUILD_ID    = '1305642236880617482';
const BOT_TOKEN   = 'MTQ2MDM0MDY5NTU3ODU3NTA0MQ.GVVO7O.zwHCmRVyA9KDp0MQiMx9uyElWNwhQL6tdfKD84';
const DISCORD_API = 'https://discord.com/api/v10';

exports.handler = async function(event, context) {
    // CORS headers
    const headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Content-Type',
        'Access-Control-Allow-Methods': 'GET, OPTIONS',
        'Content-Type': 'application/json'
    };

    // Handle preflight
    if (event.httpMethod === 'OPTIONS') {
        return { statusCode: 200, headers, body: '' };
    }

    const action = event.queryStringParameters && event.queryStringParameters.action;

    try {
        // ── GET /members?action=list ──────────────────────────────────────
        if (action === 'list') {
            let allMembers = [];
            let after = '0';
            let keepFetching = true;

            // Discord returns max 1000 per request, paginate through all
            while (keepFetching) {
                const url = `${DISCORD_API}/guilds/${GUILD_ID}/members?limit=1000&after=${after}`;
                const res = await fetch(url, {
                    headers: {
                        'Authorization': `Bot ${BOT_TOKEN}`,
                        'Content-Type': 'application/json'
                    }
                });

                if (!res.ok) {
                    const err = await res.json();
                    return {
                        statusCode: res.status,
                        headers,
                        body: JSON.stringify({ error: err.message || 'Discord API error', status: res.status })
                    };
                }

                const batch = await res.json();
                if (!batch.length) break;

                allMembers = allMembers.concat(batch);

                if (batch.length < 1000) {
                    keepFetching = false;
                } else {
                    after = batch[batch.length - 1].user.id;
                }
            }

            // Map to clean format
            const members = allMembers
                .filter(m => m.user && !m.user.bot) // exclude bots
                .map(m => ({
                    id: m.user.id,
                    username: m.user.username,
                    global_name: m.user.global_name || m.nick || m.user.username,
                    avatar: m.user.avatar,
                    discriminator: m.user.discriminator || '0',
                    roles: m.roles || [],
                    joined_at: m.joined_at
                }));

            return {
                statusCode: 200,
                headers,
                body: JSON.stringify({ members })
            };
        }

        // ── GET /members?action=banned ────────────────────────────────────
        if (action === 'banned') {
            const res = await fetch(`${DISCORD_API}/guilds/${GUILD_ID}/bans`, {
                headers: { 'Authorization': `Bot ${BOT_TOKEN}` }
            });

            if (!res.ok) {
                return { statusCode: res.status, headers, body: JSON.stringify({ banned: [] }) };
            }

            const bans = await res.json();
            return {
                statusCode: 200,
                headers,
                body: JSON.stringify({ banned: bans.map(b => ({ id: b.user.id, username: b.user.username, reason: b.reason })) })
            };
        }

        return {
            statusCode: 400,
            headers,
            body: JSON.stringify({ error: 'Unknown action. Use ?action=list or ?action=banned' })
        };

    } catch (err) {
        return {
            statusCode: 500,
            headers,
            body: JSON.stringify({ error: err.message })
        };
    }
};
