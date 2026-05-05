<?php
header('Content-Type: application/json');
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: GET, POST, DELETE');
header('Access-Control-Allow-Headers: Content-Type');

// Simple JSON file database
$usersFile = __DIR__ . '/data/users.json';
$bannedFile = __DIR__ . '/data/banned.json';

// Create data directory if it doesn't exist
if (!file_exists(__DIR__ . '/data')) {
    mkdir(__DIR__ . '/data', 0755, true);
}

// Initialize files if they don't exist
if (!file_exists($usersFile)) {
    file_put_contents($usersFile, json_encode(['users' => []]));
}
if (!file_exists($bannedFile)) {
    file_put_contents($bannedFile, json_encode(['banned' => []]));
}

// Get request method
$method = $_SERVER['REQUEST_METHOD'];
$action = $_GET['action'] ?? '';

// Handle preflight requests
if ($method === 'OPTIONS') {
    http_response_code(200);
    exit;
}

// GET - Fetch users or banned list
if ($method === 'GET') {
    if ($action === 'users') {
        $data = json_decode(file_get_contents($usersFile), true);
        echo json_encode($data['users'] ?? []);
    } elseif ($action === 'banned') {
        $data = json_decode(file_get_contents($bannedFile), true);
        echo json_encode($data['banned'] ?? []);
    } elseif ($action === 'check-ban') {
        $userId = $_GET['id'] ?? '';
        $data = json_decode(file_get_contents($bannedFile), true);
        $banned = $data['banned'] ?? [];
        $isBanned = false;
        foreach ($banned as $user) {
            if ($user['id'] === $userId) {
                $isBanned = true;
                break;
            }
        }
        echo json_encode(['banned' => $isBanned]);
    }
    exit;
}

// POST - Register/update user
if ($method === 'POST' && $action === 'register') {
    $input = json_decode(file_get_contents('php://input'), true);
    
    if (!$input || !isset($input['id'])) {
        http_response_code(400);
        echo json_encode(['error' => 'Invalid data']);
        exit;
    }

    // Read current users
    $data = json_decode(file_get_contents($usersFile), true);
    $users = $data['users'] ?? [];

    // Update or add user
    $found = false;
    foreach ($users as $key => $user) {
        if ($user['id'] === $input['id']) {
            $users[$key] = $input;
            $found = true;
            break;
        }
    }
    
    if (!$found) {
        $users[] = $input;
    }

    // Save
    file_put_contents($usersFile, json_encode(['users' => $users]));
    echo json_encode(['success' => true]);
    exit;
}

// POST - Ban user
if ($method === 'POST' && $action === 'ban') {
    $input = json_decode(file_get_contents('php://input'), true);
    
    if (!$input || !isset($input['id'])) {
        http_response_code(400);
        echo json_encode(['error' => 'Invalid data']);
        exit;
    }

    // Read current banned list
    $data = json_decode(file_get_contents($bannedFile), true);
    $banned = $data['banned'] ?? [];

    // Check if already banned
    $alreadyBanned = false;
    foreach ($banned as $user) {
        if ($user['id'] === $input['id']) {
            $alreadyBanned = true;
            break;
        }
    }

    if (!$alreadyBanned) {
        $banned[] = $input;
        file_put_contents($bannedFile, json_encode(['banned' => $banned]));
    }

    echo json_encode(['success' => true]);
    exit;
}

// DELETE - Unban user
if ($method === 'DELETE' && $action === 'unban') {
    $userId = $_GET['id'] ?? '';
    
    if (!$userId) {
        http_response_code(400);
        echo json_encode(['error' => 'Missing user ID']);
        exit;
    }

    // Read current banned list
    $data = json_decode(file_get_contents($bannedFile), true);
    $banned = $data['banned'] ?? [];

    // Remove user from banned list
    $banned = array_filter($banned, function($user) use ($userId) {
        return $user['id'] !== $userId;
    });

    file_put_contents($bannedFile, json_encode(['banned' => array_values($banned)]));
    echo json_encode(['success' => true]);
    exit;
}

http_response_code(404);
echo json_encode(['error' => 'Not found']);
?>
