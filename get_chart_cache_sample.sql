-- Get sample chart cache data for witty-raven (user 5)
-- Run this in your database tool to see what's actually cached

-- 1M chart cache
SELECT 
    user_id,
    period,
    generated_at,
    LEFT(chart_data, 500) as chart_data_preview
FROM user_portfolio_chart_cache
WHERE user_id = 5 AND period = '1M';

-- Full 1M chart data (for detailed analysis)
SELECT chart_data
FROM user_portfolio_chart_cache
WHERE user_id = 5 AND period = '1M';

-- YTD chart cache
SELECT chart_data
FROM user_portfolio_chart_cache
WHERE user_id = 5 AND period = 'YTD';

-- 1D chart cache (to check timestamp format)
SELECT chart_data
FROM user_portfolio_chart_cache
WHERE user_id = 5 AND period = '1D';

-- Check all periods for user 5
SELECT 
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
        WHEN '5Y' THEN 7
        WHEN 'MAX' THEN 8
    END;
