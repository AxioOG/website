-- Fuse User Management System - Supabase Setup
-- Run this in Supabase SQL Editor: https://supabase.com/dashboard/project/YOUR_PROJECT/sql

-- 1. Create users table (if not already created)
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    username TEXT,
    global_name TEXT,
    avatar TEXT,
    roles JSONB DEFAULT '[]'::jsonb,
    seen_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 2. Create banned_users table
CREATE TABLE IF NOT EXISTS banned_users (
    id TEXT PRIMARY KEY,
    username TEXT,
    global_name TEXT,
    avatar TEXT,
    banned_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    banned_by TEXT,
    reason TEXT
);

-- 3. Create index for faster queries
CREATE INDEX IF NOT EXISTS idx_users_seen_at ON users(seen_at DESC);
CREATE INDEX IF NOT EXISTS idx_banned_users_banned_at ON banned_users(banned_at DESC);

-- 4. Enable realtime (optional - for live updates)
ALTER PUBLICATION supabase_realtime ADD TABLE users;
ALTER PUBLICATION supabase_realtime ADD TABLE banned_users;
