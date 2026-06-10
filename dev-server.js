// Local dev server — serves static files and Netlify function API routes.
// Usage: node dev-server.js

const http = require('http');
const fs = require('fs');
const path = require('path');
const url = require('url');

const PORT = process.env.PORT || 8888;
const ROOT = __dirname;

const usersFn = require('./netlify/functions/users');
const membersFn = require('./netlify/functions/members');
const banFn = require('./netlify/functions/ban');

const MIME = {
    '.html': 'text/html',
    '.css': 'text/css',
    '.js': 'application/javascript',
    '.json': 'application/json',
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.svg': 'image/svg+xml',
    '.ico': 'image/x-icon'
};

function toNetlifyEvent(req, body) {
    const parsed = url.parse(req.url, true);
    const headers = {};
    Object.keys(req.headers).forEach(function(k) {
        headers[k] = req.headers[k];
    });

    return {
        httpMethod: req.method,
        path: parsed.pathname,
        queryStringParameters: parsed.query,
        headers: headers,
        body: body || null,
        isBase64Encoded: false
    };
}

function invokeFunction(handler, event) {
    return Promise.resolve(handler(event, {}));
}

function readBody(req) {
    return new Promise(function(resolve) {
        var chunks = [];
        req.on('data', function(c) { chunks.push(c); });
        req.on('end', function() { resolve(Buffer.concat(chunks).toString('utf8')); });
    });
}

function serveStatic(filePath, res) {
    fs.readFile(filePath, function(err, data) {
        if (err) {
            res.writeHead(404);
            res.end('Not found');
            return;
        }
        var ext = path.extname(filePath);
        res.writeHead(200, { 'Content-Type': MIME[ext] || 'application/octet-stream' });
        res.end(data);
    });
}

var server = http.createServer(function(req, res) {
    var parsed = url.parse(req.url, true);
    var pathname = parsed.pathname;

    if (pathname === '/api/users' || pathname === '/api/members' || pathname === '/api/ban') {
        readBody(req).then(function(body) {
            var event = toNetlifyEvent(req, body);
            var handler = pathname === '/api/users' ? usersFn.handler
                : pathname === '/api/members' ? membersFn.handler
                : banFn.handler;

            return invokeFunction(handler, event);
        }).then(function(result) {
            var headers = result.headers || {};
            res.writeHead(result.statusCode || 200, headers);
            res.end(result.body || '');
        }).catch(function(err) {
            res.writeHead(500, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ error: err.message }));
        });
        return;
    }

    var filePath = path.join(ROOT, pathname === '/' ? 'index.html' : pathname);
    if (fs.existsSync(filePath) && fs.statSync(filePath).isFile()) {
        serveStatic(filePath, res);
        return;
    }

    if (pathname === '/dashboard' || pathname === '/dashboard/') {
        serveStatic(path.join(ROOT, 'dashboard.html'), res);
        return;
    }

    if (pathname === '/tickets' || pathname === '/tickets/') {
        serveStatic(path.join(ROOT, 'tickets.html'), res);
        return;
    }

    serveStatic(path.join(ROOT, 'index.html'), res);
});

server.listen(PORT, function() {
    console.log('Fuse dev server running at http://localhost:' + PORT);
    console.log('Dashboard: http://localhost:' + PORT + '/dashboard');
});
