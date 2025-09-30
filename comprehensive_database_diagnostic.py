"""
COMPREHENSIVE DATABASE DIAGNOSTIC
Reveals actual database state to identify cache generation failure
"""
import os
import sys
from datetime import date, datetime, timedelta

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from api.index import app, db
from models import (PortfolioSnapshot, UserPortfolioChartCache, LeaderboardCache,
                   MarketData, User, Stock)

def diagnose_database():
    """Comprehensive database state analysis"""
    with app.app_context():
        print("\n" + "="*80)
        print("COMPREHENSIVE DATABASE DIAGNOSTIC")
        print("="*80)
        
        # SECTION 1: User and Stock Data
        print("\n📊 USER & PORTFOLIO DATA:")
        users = User.query.all()
        print(f"Total Users: {len(users)}")
        
        for user in users:
            stocks = Stock.query.filter_by(user_id=user.id).all()
            print(f"\n  User {user.id} ({user.username}):")
            print(f"    Email: {user.email}")
            print(f"    Stocks: {len(stocks)}")
            if stocks:
                earliest = min(stocks, key=lambda s: s.created_at)
                print(f"    Portfolio Start: {earliest.created_at.date()}")
                print(f"    Stock Symbols: {', '.join([s.symbol for s in stocks[:5]])}")
        
        # SECTION 2: Portfolio Snapshots
        print("\n\n📈 PORTFOLIO SNAPSHOTS:")
        total_snapshots = PortfolioSnapshot.query.count()
        print(f"Total Snapshots: {total_snapshots}")
        
        # Last 7 days of snapshots
        seven_days_ago = date.today() - timedelta(days=7)
        recent_snapshots = PortfolioSnapshot.query.filter(
            PortfolioSnapshot.date >= seven_days_ago
        ).order_by(PortfolioSnapshot.date.desc()).all()
        
        print(f"\n  Last 7 Days: {len(recent_snapshots)} snapshots")
        print(f"  Date Range: {seven_days_ago} to {date.today()}")
        
        # Group by date
        by_date = {}
        for snap in recent_snapshots:
            snap_date = snap.date
            if snap_date not in by_date:
                by_date[snap_date] = []
            by_date[snap_date].append(snap)
        
        print("\n  Recent Snapshots by Date:")
        for snap_date in sorted(by_date.keys(), reverse=True):
            snaps = by_date[snap_date]
            zero_count = sum(1 for s in snaps if s.total_value == 0)
            non_zero = [s for s in snaps if s.total_value > 0]
            
            print(f"    {snap_date} ({snap_date.strftime('%A')}): {len(snaps)} snapshots")
            print(f"      Zero values: {zero_count}")
            print(f"      Non-zero values: {len(non_zero)}")
            
            if non_zero:
                for s in non_zero[:3]:  # Show first 3
                    user = User.query.get(s.user_id)
                    print(f"        User {s.user_id} ({user.username if user else 'unknown'}): ${s.total_value:,.2f}")
        
        # SECTION 3: Intraday Snapshots (if table exists)
        print("\n\n⏱️ INTRADAY DATA:")
        try:
            # Check if IntradayPortfolioSnapshot table exists
            result = db.session.execute(db.text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'intraday_portfolio_snapshot'
                )
            """))
            table_exists = result.scalar()
            
            if table_exists:
                result = db.session.execute(db.text("""
                    SELECT COUNT(*) FROM intraday_portfolio_snapshot
                """))
                intraday_count = result.scalar()
                print(f"Intraday Snapshots: {intraday_count}")
                
                # Recent intraday data
                result = db.session.execute(db.text("""
                    SELECT date, COUNT(*) as count
                    FROM intraday_portfolio_snapshot
                    WHERE date >= CURRENT_DATE - INTERVAL '7 days'
                    GROUP BY date
                    ORDER BY date DESC
                """))
                
                print("\n  Recent Intraday Data:")
                for row in result:
                    print(f"    {row[0]}: {row[1]} snapshots")
            else:
                print("No intraday_portfolio_snapshot table found")
        except Exception as e:
            print(f"Error checking intraday data: {e}")
        
        # SECTION 4: S&P 500 Market Data
        print("\n\n📉 S&P 500 MARKET DATA:")
        sp500_count = MarketData.query.filter_by(ticker="SPY_SP500").count()
        print(f"Total S&P 500 Data Points: {sp500_count}")
        
        recent_sp500 = MarketData.query.filter(
            MarketData.ticker == "SPY_SP500",
            MarketData.date >= seven_days_ago
        ).order_by(MarketData.date.desc()).all()
        
        print(f"\n  Last 7 Days: {len(recent_sp500)} data points")
        print("\n  Recent S&P 500 Values:")
        for sp in recent_sp500[:10]:
            print(f"    {sp.date} ({sp.date.strftime('%A')}): {sp.close_price:,.2f}")
        
        # Check for problematic values
        low_values = MarketData.query.filter(
            MarketData.ticker == "SPY_SP500",
            MarketData.close_price < 1000
        ).all()
        
        if low_values:
            print(f"\n  ⚠️ WARNING: {len(low_values)} S&P 500 values < 1000 (likely SPY not S&P)")
            for sp in low_values[:5]:
                print(f"    {sp.date}: {sp.close_price}")
        
        # SECTION 5: Chart Caches
        print("\n\n💾 CHART CACHES:")
        cache_count = UserPortfolioChartCache.query.count()
        print(f"Total Chart Cache Entries: {cache_count}")
        
        # Sample a few caches
        import json
        for user in users[:2]:  # First 2 users
            caches = UserPortfolioChartCache.query.filter_by(user_id=user.id).all()
            print(f"\n  User {user.id} ({user.username}): {len(caches)} cached periods")
            
            for cache in caches[:3]:  # First 3 periods
                try:
                    data = json.loads(cache.chart_data)
                    data_points = len(data.get('chart_data', []))
                    print(f"    {cache.period}: {data_points} data points")
                    
                    if data_points > 0:
                        # Show first and last points
                        points = data.get('chart_data', [])
                        first = points[0]
                        last = points[-1]
                        print(f"      First: {first.get('date')} - Portfolio: ${first.get('portfolio', 0):,.2f}")
                        print(f"      Last: {last.get('date')} - Portfolio: ${last.get('portfolio', 0):,.2f}")
                except Exception as e:
                    print(f"    {cache.period}: Error parsing - {e}")
        
        # SECTION 6: Database Schema Check
        print("\n\n🗄️ DATABASE SCHEMA:")
        
        # Check PortfolioSnapshot columns
        result = db.session.execute(db.text("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'portfolio_snapshot'
            ORDER BY ordinal_position
        """))
        
        print("\n  PortfolioSnapshot table columns:")
        for row in result:
            print(f"    {row[0]}: {row[1]}")
        
        # Check UserPortfolioChartCache columns
        result = db.session.execute(db.text("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'user_portfolio_chart_cache'
            ORDER BY ordinal_position
        """))
        
        print("\n  UserPortfolioChartCache table columns:")
        for row in result:
            print(f"    {row[0]}: {row[1]}")
        
        # SECTION 7: Leaderboard Cache
        print("\n\n🏆 LEADERBOARD CACHES:")
        leaderboard_count = LeaderboardCache.query.count()
        print(f"Total Leaderboard Cache Entries: {leaderboard_count}")
        
        lb_caches = LeaderboardCache.query.all()
        for lb in lb_caches:
            try:
                data = json.loads(lb.leaderboard_data)
                print(f"\n  {lb.period}:")
                print(f"    Users: {len(data)}")
                print(f"    Generated: {lb.generated_at}")
                
                if data:
                    # Show top 3
                    for i, user_data in enumerate(data[:3]):
                        print(f"    {i+1}. {user_data.get('username')}: {user_data.get('performance_percentage', 0):.2f}%")
            except Exception as e:
                print(f"  {lb.period}: Error parsing - {e}")
        
        print("\n" + "="*80)
        print("DIAGNOSTIC COMPLETE")
        print("="*80)

if __name__ == "__main__":
    diagnose_database()
