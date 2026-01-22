-- Check if the unique constraint exists
SELECT 
    con.conname as constraint_name,
    con.contype as constraint_type,
    ARRAY(
        SELECT att.attname
        FROM unnest(con.conkey) AS u(attnum)
        JOIN pg_attribute AS att ON att.attnum = u.attnum AND att.attrelid = con.conrelid
    ) as columns
FROM pg_constraint con
JOIN pg_class rel ON rel.oid = con.conrelid
WHERE rel.relname = 'user_portfolio_chart_cache'
  AND con.contype = 'u';
