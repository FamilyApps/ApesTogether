-- Cleanup bogus $0 portfolio snapshots created before users had any holdings
-- Run this in Vercel Postgres console or pgAdmin

-- First, let's see what we're dealing with (PREVIEW)
SELECT 
    u.username,
    COUNT(*) as zero_snapshots,
    MIN(ps.date) as first_zero_date,
    MAX(ps.date) as last_zero_date
FROM portfolio_snapshot ps
JOIN "user" u ON ps.user_id = u.id
WHERE ps.total_value = 0.0
GROUP BY u.username
ORDER BY zero_snapshots DESC;

-- For witty-raven specifically, show first real transaction date
SELECT 
    u.username,
    MIN(t.timestamp) as first_transaction_date,
    MIN(DATE(t.timestamp)) as first_transaction_date_only
FROM "user" u
LEFT JOIN transaction t ON u.id = t.user_id
WHERE u.username = 'witty-raven'
GROUP BY u.username;

-- DELETE bogus snapshots for witty-raven (before 6/13/2025)
-- ⚠️ VERIFY first_transaction_date above matches ~6/13/2025 before running!
DELETE FROM portfolio_snapshot 
WHERE user_id = (SELECT id FROM "user" WHERE username = 'witty-raven')
  AND total_value = 0.0 
  AND date < '2025-06-13';

-- Verify cleanup worked
SELECT 
    u.username,
    COUNT(*) as total_snapshots,
    MIN(ps.date) as first_snapshot,
    MAX(ps.date) as last_snapshot,
    MIN(ps.total_value) as min_value,
    MAX(ps.total_value) as max_value
FROM portfolio_snapshot ps
JOIN "user" u ON ps.user_id = u.id
WHERE u.username = 'witty-raven'
GROUP BY u.username;

-- If other users also have bogus $0 snapshots, clean them up too:
-- (Adjust date threshold per user's first transaction)
/*
DELETE FROM portfolio_snapshot ps
WHERE ps.total_value = 0.0
  AND ps.date < (
    SELECT MIN(DATE(t.timestamp))
    FROM transaction t
    WHERE t.user_id = ps.user_id
  );
*/
