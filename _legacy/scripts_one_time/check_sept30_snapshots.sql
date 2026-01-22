-- Check if Sept 30, 2025 snapshots exist
-- Run this in your database query tool (pgAdmin, DBeaver, etc.)

-- 1. Check for today's snapshots (Sept 30, 2025)
SELECT 
    ps.user_id,
    u.username,
    ps.date,
    ps.total_value,
    ps.created_at
FROM portfolio_snapshot ps
JOIN "user" u ON u.id = ps.user_id
WHERE ps.date = '2025-09-30'
ORDER BY ps.user_id;

-- Expected: 5 rows (one per user)
-- If 0 rows: Cron job didn't create snapshots

-- 2. Check yesterday's snapshots for comparison (Sept 29, 2025)
SELECT 
    ps.user_id,
    u.username,
    ps.date,
    ps.total_value,
    ps.created_at
FROM portfolio_snapshot ps
JOIN "user" u ON u.id = ps.user_id
WHERE ps.date = '2025-09-29'
ORDER BY ps.user_id;

-- 3. Check latest snapshot date
SELECT 
    MAX(date) as latest_date,
    COUNT(*) as total_snapshots,
    COUNT(DISTINCT user_id) as user_count
FROM portfolio_snapshot;

-- 4. Check for zero-value snapshots (corrupted data)
SELECT COUNT(*) as zero_value_count
FROM portfolio_snapshot
WHERE total_value = 0;

-- 5. Check chart cache status for user 5 (witty-raven)
SELECT 
    user_id,
    period,
    generated_at,
    LENGTH(chart_data) as data_size_bytes
FROM user_portfolio_chart_cache
WHERE user_id = 5
ORDER BY 
    CASE period
        WHEN '1D' THEN 1
        WHEN '5D' THEN 2
        WHEN '1M' THEN 3
        WHEN '3M' THEN 4
        WHEN 'YTD' THEN 5
        WHEN '1Y' THEN 6
    END;

-- 6. Check users with stocks
SELECT 
    u.id,
    u.username,
    COUNT(s.id) as stock_count,
    SUM(s.quantity) as total_shares
FROM "user" u
LEFT JOIN stock s ON s.user_id = u.id
GROUP BY u.id, u.username
ORDER BY u.id;
