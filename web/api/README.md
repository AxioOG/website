# Fuse User Management API

Simple PHP-based API for managing users and bans.

## Requirements

- PHP 7.0 or higher
- Web server with PHP support (Apache, Nginx, etc.)
- Write permissions for the `data/` directory

## Installation

1. Upload the `api/` folder to your web server
2. Make sure the `api/data/` directory is writable:
   ```bash
   chmod 755 api/data
   ```

3. The API will automatically create these files:
   - `api/data/users.json` - Stores all registered users
   - `api/data/banned.json` - Stores banned users

## Endpoints

### GET /api/users.php?action=users
Returns all registered users

### GET /api/users.php?action=banned
Returns all banned users

### GET /api/users.php?action=check-ban&id=USER_ID
Check if a specific user is banned

### POST /api/users.php?action=register
Register or update a user
```json
{
  "id": "123456789",
  "username": "user123",
  "global_name": "User Name",
  "avatar": "avatar_hash",
  "roles": ["role_id_1", "role_id_2"],
  "seenAt": 1234567890
}
```

### POST /api/users.php?action=ban
Ban a user
```json
{
  "id": "123456789",
  "username": "user123",
  "global_name": "User Name",
  "avatar": "avatar_hash",
  "bannedAt": 1234567890
}
```

### DELETE /api/users.php?action=unban&id=USER_ID
Unban a user

## Security Notes

- The `data/` directory should NOT be publicly accessible
- Consider adding authentication for admin endpoints
- For production, use a proper database (MySQL, PostgreSQL)
- Add rate limiting to prevent abuse

## Troubleshooting

If users aren't appearing:
1. Check PHP error logs
2. Verify `api/data/` directory exists and is writable
3. Check browser console for API errors
4. Test API directly: `https://yoursite.com/api/users.php?action=users`
