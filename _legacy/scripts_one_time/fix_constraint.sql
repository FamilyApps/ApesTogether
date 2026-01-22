-- Add the missing unique constraint if it doesn't exist
DO $$
BEGIN
    -- Check if constraint exists
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint con
        JOIN pg_class rel ON rel.oid = con.conrelid
        WHERE rel.relname = 'user_portfolio_chart_cache'
          AND con.conname = 'unique_user_period_chart'
    ) THEN
        -- Add the constraint
        ALTER TABLE user_portfolio_chart_cache
        ADD CONSTRAINT unique_user_period_chart UNIQUE (user_id, period);
        
        RAISE NOTICE 'Added unique constraint unique_user_period_chart';
    ELSE
        RAISE NOTICE 'Constraint unique_user_period_chart already exists';
    END IF;
END $$;
