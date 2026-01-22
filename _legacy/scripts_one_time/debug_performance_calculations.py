#!/usr/bin/env python3
"""
Debug Performance Calculations
==============================

Investigate why:
1. 1D calculations return "No data or empty chart"
2. 5D calculations return 0.00% despite having 5 chart points

This will help us fix the root cause of the leaderboard issues.
"""

import os
import sys
from datetime import datetime, date, timedelta
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add the project root to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def debug_performance_calculations():
    """Debug why performance calculations are broken"""
    
    print("=" * 60)
    print("PERFORMANCE CALCULATION DEBUG")
    print("=" * 60)
    print(f"Starting at: {datetime.now().isoformat()}")
    print()
    
    try:
        from models import db, User, PortfolioSnapshot, PortfolioSnapshotIntraday, MarketData
        from portfolio_performance import PortfolioPerformanceCalculator
        from sqlalchemy import func, and_
        
        # Get a test user
        test_user = User.query.join(User.stocks).distinct().first()
        if not test_user:
            print("❌ No users with stocks found!")
            return
        
        print(f"🔍 Testing User: {test_user.id} ({test_user.username})")
        print()
        
        # Check portfolio snapshots
        print("1. PORTFOLIO SNAPSHOT DATA:")
        today = date.today()
        yesterday = today - timedelta(days=1)
        five_days_ago = today - timedelta(days=5)
        
        # Check regular snapshots
        total_snapshots = PortfolioSnapshot.query.filter_by(user_id=test_user.id).count()
        recent_snapshots = PortfolioSnapshot.query.filter(
            and_(
                PortfolioSnapshot.user_id == test_user.id,
                PortfolioSnapshot.date >= five_days_ago
            )
        ).order_by(PortfolioSnapshot.date.desc()).all()
        
        print(f"   Total snapshots: {total_snapshots}")
        print(f"   Recent snapshots (last 5 days): {len(recent_snapshots)}")
        
        for snapshot in recent_snapshots[:5]:
            print(f"      {snapshot.date}: ${snapshot.total_value:.2f}")
        
        # Check intraday snapshots
        intraday_count = PortfolioSnapshotIntraday.query.filter(
            and_(
                PortfolioSnapshotIntraday.user_id == test_user.id,
                func.date(PortfolioSnapshotIntraday.timestamp) == today
            )
        ).count()
        
        print(f"   Intraday snapshots today: {intraday_count}")
        print()
        
        # Check S&P 500 data
        print("2. S&P 500 DATA:")
        sp500_daily = MarketData.query.filter(
            and_(
                MarketData.ticker == 'SPY_SP500',
                MarketData.date >= five_days_ago
            )
        ).order_by(MarketData.date.desc()).all()
        
        sp500_intraday = MarketData.query.filter(
            and_(
                MarketData.ticker == 'SPY_INTRADAY',
                MarketData.date == today
            )
        ).count()
        
        print(f"   Daily S&P 500 data (last 5 days): {len(sp500_daily)}")
        for data in sp500_daily[:5]:
            print(f"      {data.date}: ${data.close_price:.2f}")
        
        print(f"   Intraday S&P 500 data today: {sp500_intraday}")
        print()
        
        # Test performance calculations
        print("3. PERFORMANCE CALCULATION TESTS:")
        calculator = PortfolioPerformanceCalculator()
        
        for period in ['1D', '5D']:
            print(f"   Testing {period}:")
            try:
                perf_data = calculator.get_performance_data(test_user.id, period)
                
                portfolio_return = perf_data.get('portfolio_return')
                sp500_return = perf_data.get('sp500_return')
                chart_data = perf_data.get('chart_data', [])
                
                print(f"      Portfolio return: {portfolio_return}%")
                print(f"      S&P 500 return: {sp500_return}%")
                print(f"      Chart data points: {len(chart_data)}")
                
                if chart_data:
                    print(f"      First point: {chart_data[0]}")
                    print(f"      Last point: {chart_data[-1]}")
                else:
                    print("      ❌ NO CHART DATA!")
                
                # Check for specific issues
                if period == '1D' and len(chart_data) == 0:
                    print("      🚨 1D ISSUE: No chart data - likely missing intraday snapshots")
                
                if period == '5D' and portfolio_return == 0.0 and len(chart_data) > 0:
                    print("      🚨 5D ISSUE: 0% return despite chart data - calculation problem")
                
            except Exception as e:
                print(f"      ❌ ERROR: {str(e)}")
            
            print()
        
        # Check specific calculation methods
        print("4. DETAILED CALCULATION ANALYSIS:")
        
        # Test Modified Dietz calculation for 5D
        try:
            print("   Testing Modified Dietz calculation (5D):")
            start_date = today - timedelta(days=5)
            end_date = today
            
            dietz_return = calculator.calculate_modified_dietz_return(test_user.id, start_date, end_date)
            print(f"      Modified Dietz return: {dietz_return * 100:.2f}%")
            
            # Check if snapshots exist for the period
            period_snapshots = PortfolioSnapshot.query.filter(
                and_(
                    PortfolioSnapshot.user_id == test_user.id,
                    PortfolioSnapshot.date >= start_date,
                    PortfolioSnapshot.date <= end_date
                )
            ).order_by(PortfolioSnapshot.date).all()
            
            print(f"      Snapshots in period: {len(period_snapshots)}")
            if len(period_snapshots) >= 2:
                start_value = period_snapshots[0].total_value
                end_value = period_snapshots[-1].total_value
                simple_return = ((end_value - start_value) / start_value) * 100
                print(f"      Simple return check: {simple_return:.2f}% (${start_value:.2f} → ${end_value:.2f})")
            
        except Exception as e:
            print(f"      ❌ Modified Dietz ERROR: {str(e)}")
        
        print()
        
        # Test S&P 500 calculation
        try:
            print("   Testing S&P 500 calculation (5D):")
            start_date = today - timedelta(days=5)
            end_date = today
            
            sp500_return = calculator.calculate_sp500_return(start_date, end_date)
            print(f"      S&P 500 return: {sp500_return * 100:.2f}%")
            
        except Exception as e:
            print(f"      ❌ S&P 500 calculation ERROR: {str(e)}")
        
        print()
        print("=" * 60)
        print("DEBUG COMPLETE")
        print("=" * 60)
        
    except Exception as e:
        print(f"CRITICAL ERROR: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    debug_performance_calculations()
