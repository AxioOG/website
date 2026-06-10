// Netlify serverless function — fetches guild members for admin dashboard
// Prefers the logged-in admin's OAuth token (guilds.members.read scope).
// Falls back to DISCORD_BOT_TOKEN + Server Members Intent if set in Netlify.

const GUILD_ID    = '1305642236880617482';
const DISCORD_API = 'https://discord.com/api/v10';
const ROLE_OWNER  = '1507374058247815218';
const ROLE_ADMIN  = '1510902432681689128';

function isPrivilegedRoles(roles) {
    return roles.includes(ROLE_OWNER) || roles.includes(ROLE_ADMIN);
}

async function isPrivilegedBotMember(botToken, userId) {
    if (!userId) return false;
    const res = await fetch(`${DISCORD_API}/guilds/${GUILD_ID}/members/${userId}`, {
        headers: { 'Authorization': `Bot ${botToken}` }
    });
    if (!res.ok) return false;
    const member = await res.json();
    return isPrivilegedRoles(member.roles || []);
}

async function verifyOAuthAdmin(accessToken) {
    const meRes = await fetch(`${DISCORD_API}/users/@me`, {
        headers: { 'Authorization': `Bearer ${accessToken}` }
    });
    if (!meRes.ok) return { ok: false, error: 'Discord login expired — sign out and sign in again.' };

    const memberRes = await fetch(`${DISCORD_API}/users/@me/guilds/${GUILD_ID}/member`, {
        headers: { 'Authorization': `Bearer ${accessToken}` }
    });
    if (!memberRes.ok) {
        return { ok: false, error: 'Could not read your server roles. Re-login with Discord (needs guilds.members.read scope).' };
    }

    const member = await memberRes.json();
    if (!isPrivilegedRoles(member.roles || [])) {
        return { ok: false, error: 'Only Owner or Administrator can list server members' };
    }

    return { ok: true, authorization: `Bearer ${accessToken}` };
}

async function fetchAllMembers(authorization) {
    let allMembers = [];
    let after = '0';

    while (true) {
        const url = `${DISCORD_API}/guilds/${GUILD_ID}/members?limit=1000&after=${after}`;
        const res = await fetch(url, { headers: { 'Authorization': authorization } });

        if (!res.ok) {
            let err = {};
            try { err = await res.json(); } catch (e) {}
            const message = err.message || 'Discord API error';
            if (authorization.startsWith('Bot ') && (res.status === 403 || /intent/i.test(message))) {
                return {
                    ok: false,
                    status: res.status,
                    error: 'Bot needs Server Members Intent in Discord Developer Portal → Bot → Privileged Gateway Intents. Or sign in again so your admin OAuth token is used instead.'
                };
            }
            return { ok: false, status: res.status, error: message };
        }

        const batch = await res.json();
        if (!batch.length) break;

        allMembers = allMembers.concat(batch);
        if (batch.length < 1000) break;
        after = batch[batch.length - 1].user.id;
    }

    const members = allMembers
        .filter(m => m.user && !m.user.bot)
        .map(m => ({
            id: m.user.id,
            username: m.user.username,
            global_name: m.user.global_name || m.nick || m.user.username,
            avatar: m.user.avatar,
            discriminator: m.user.discriminator || '0',
            roles: m.roles || [],
            joined_at: m.joined_at
        }));

    return { ok: true, members };
}

exports.handler = async function(event, context) {
    const headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Content-Type, Authorization',
        'Access-Control-Allow-Methods': 'GET, OPTIONS',
        'Content-Type': 'application/json'
    };

    if (event.httpMethod === 'OPTIONS') {
        return { statusCode: 200, headers, body: '' };
    }

    const action = event.queryStringParameters && event.queryStringParameters.action;

    try {
        if (action !== 'list') {
            return { statusCode: 400, headers, body: JSON.stringify({ error: 'Use ?action=list' }) };
        }

        const authHeader = event.headers.authorization || event.headers.Authorization || '';
        const customToken = event.headers['x-discord-access-token'] || event.headers['X-Discord-Access-Token'] || '';
        const queryToken = event.queryStringParameters && event.queryStringParameters.access_token;
        const oauthToken =
            (authHeader.startsWith('Bearer ') ? authHeader.slice(7) : null) ||
            customToken ||
            queryToken ||
            null;

        if (oauthToken) {
            const check = await verifyOAuthAdmin(oauthToken);
            if (!check.ok) {
                return { statusCode: 403, headers, body: JSON.stringify({ error: check.error }) };
            }
            const result = await fetchAllMembers(check.authorization);
            if (!result.ok) {
                return { statusCode: result.status || 500, headers, body: JSON.stringify({ error: result.error }) };
            }
            return { statusCode: 200, headers, body: JSON.stringify({ members: result.members }) };
        }

        const BOT_TOKEN = process.env.DISCORD_BOT_TOKEN;
        if (!BOT_TOKEN) {
            return {
                statusCode: 500,
                headers,
                body: JSON.stringify({
                    error: 'No Discord auth available. Sign in again on the dashboard, or set DISCORD_BOT_TOKEN in Netlify with Server Members Intent enabled.'
                })
            };
        }

        const requesterId = event.queryStringParameters && event.queryStringParameters.userid;
        const privileged = await isPrivilegedBotMember(BOT_TOKEN, requesterId);
        if (!privileged) {
            return {
                statusCode: 403,
                headers,
                body: JSON.stringify({ error: 'Only Owner or Administrator can list server members' })
            };
        }

        const result = await fetchAllMembers(`Bot ${BOT_TOKEN}`);
        if (!result.ok) {
            return { statusCode: result.status || 500, headers, body: JSON.stringify({ error: result.error }) };
        }
        return { statusCode: 200, headers, body: JSON.stringify({ members: result.members }) };

    } catch (err) {
        return { statusCode: 500, headers, body: JSON.stringify({ error: err.message }) };
    }
};
