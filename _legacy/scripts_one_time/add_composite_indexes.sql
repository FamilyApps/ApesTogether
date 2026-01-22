-- Add composite indexes recommended by Grok for performance
-- These indexes speed up the filter_by(user_id=X, date=Y) queries significantly

-- Index for PortfolioSnapshot queries (most critical)
CREATE INDEX IF NOT EXISTS idx_portfolio_snapshot_user_date 
ON portfolio_snapshot (user_id, date);

-- Index for Stock queries (user's holdings lookup)
CREATE INDEX IF NOT EXISTS idx_stock_user_ticker 
ON stock (user_id, ticker);

-- Index for MarketData queries (ticker + date range lookups)
CREATE INDEX IF NOT EXISTS idx_market_data_ticker_date 
ON market_data (ticker, date);

-- Refresh statistics for query planner
ANALYZE portfolio_snapshot;
ANALYZE stock;
ANALYZE market_data;

-- Verify indexes were created
SELECT 
    tablename, 
    indexname, 
    indexdef 
FROM pg_indexes 
WHERE tablename IN ('portfolio_snapshot', 'stock', 'market_data')
ORDER BY tablename, indexname;
