#!/usr/bin/env python3
"""
Test script to verify cron job execution and snapshot creation for today.
Checks intraday snapshots, end-of-day snapshots, chart data, and leaderboard updates.
"""

import os
import sys
from datetime import datetime, timedelta
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import json

# Add the project root to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from models import db, User, Transaction, PortfolioSnapshot, IntradaySnapshot, LeaderboardEntry
from portfolio_performance import PortfolioPerformanceCalculator

def get_db_connection():
    """Get database connection using environment variables."""
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        print("ERROR: DATABASE_URL environment variable not set")
        return None
    
    # Handle postgres:// vs postgresql:// URL format
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    
    engine = create_engine(database_url)
    Session = sessionmaker(bind=engine)
    return Session(), engine

def test_cron_execution():
    """Test that cron jobs executed properly today."""
    print("=== CRON JOB EXECUTION TEST ===")
    print(f"Testing for date: {datetime.now().strftime('%Y-%m-%d')}")
    print()
    
    session, engine = get_db_connection()
    if not session:
        return False
    
    try:
        today = datetime.now().date()
        yesterday = today - timedelta(days=1)
        
        # Get all users with portfolios
        users = session.query(User).join(Transaction).distinct().all()
        print(f"Found {len(users)} users with portfolios")
        
        results = {
            'users_tested': len(users),
            'intraday_snapshots_today': 0,
            'eod_snapshots_today': 0,
            'users_with_intraday_today': 0,
            'users_with_eod_today': 0,
            'portfolio_values_varying': 0,
            'leaderboard_updated': False,
            'chart_data_available': 0,
            'issues': []
        }
        
        print("\n--- CHECKING INTRADAY SNAPSHOTS ---")
        for user in users:
            # Check intraday snapshots for today
            intraday_today = session.query(IntradaySnapshot).filter(
                IntradaySnapshot.user_id == user.id,
                IntradaySnapshot.date == today
            ).all()
            
            if intraday_today:
                results['users_with_intraday_today'] += 1
                results['intraday_snapshots_today'] += len(intraday_today)
                
                # Check for varying values
                values = [snap.portfolio_value for snap in intraday_today]
                if len(set(values)) > 1:
                    results['portfolio_values_varying'] += 1
                    print(f"✓ User {user.username}: {len(intraday_today)} intraday snapshots with varying values")
                else:
                    print(f"⚠ User {user.username}: {len(intraday_today)} intraday snapshots but all same value: ${values[0] if values else 0}")
                    results['issues'].append(f"User {user.username} has identical intraday values")
            else:
                print(f"✗ User {user.username}: No intraday snapshots for today")
                results['issues'].append(f"User {user.username} missing intraday snapshots for today")
        
        print(f"\nIntraday Summary: {results['users_with_intraday_today']}/{len(users)} users have intraday snapshots today")
        print(f"Total intraday snapshots today: {results['intraday_snapshots_today']}")
        
        print("\n--- CHECKING END-OF-DAY SNAPSHOTS ---")
        for user in users:
            # Check end-of-day snapshots for today
            eod_today = session.query(PortfolioSnapshot).filter(
                PortfolioSnapshot.user_id == user.id,
                PortfolioSnapshot.date == today
            ).all()
            
            if eod_today:
                results['users_with_eod_today'] += 1
                results['eod_snapshots_today'] += len(eod_today)
                print(f"✓ User {user.username}: End-of-day snapshot created (${eod_today[0].portfolio_value})")
            else:
                print(f"✗ User {user.username}: No end-of-day snapshot for today")
                results['issues'].append(f"User {user.username} missing end-of-day snapshot for today")
        
        print(f"\nEOD Summary: {results['users_with_eod_today']}/{len(users)} users have end-of-day snapshots today")
        
        print("\n--- CHECKING LEADERBOARD UPDATES ---")
        # Check if leaderboard has recent entries
        recent_leaderboard = session.query(LeaderboardEntry).filter(
            LeaderboardEntry.date >= yesterday
        ).all()
        
        if recent_leaderboard:
            results['leaderboard_updated'] = True
            print(f"✓ Leaderboard has {len(recent_leaderboard)} recent entries")
            
            # Show top performers
            top_performers = sorted(recent_leaderboard, key=lambda x: x.performance_percentage, reverse=True)[:5]
            print("Top performers:")
            for i, entry in enumerate(top_performers, 1):
                user = session.query(User).get(entry.user_id)
                print(f"  {i}. {user.username if user else 'Unknown'}: {entry.performance_percentage:.2f}%")
        else:
            print("✗ No recent leaderboard entries found")
            results['issues'].append("Leaderboard not updated recently")
        
        print("\n--- CHECKING CHART DATA AVAILABILITY ---")
        for user in users:
            # Check if user has sufficient data for charts (at least 2 data points)
            total_snapshots = session.query(PortfolioSnapshot).filter(
                PortfolioSnapshot.user_id == user.id
            ).count()
            
            if total_snapshots >= 2:
                results['chart_data_available'] += 1
                print(f"✓ User {user.username}: {total_snapshots} total snapshots (chart ready)")
            else:
                print(f"⚠ User {user.username}: Only {total_snapshots} snapshots (insufficient for chart)")
        
        print(f"\nChart Data Summary: {results['chart_data_available']}/{len(users)} users have sufficient chart data")
        
        print("\n--- TESTING PORTFOLIO CALCULATION ---")
        # Test current portfolio calculation for one user
        test_user = users[0] if users else None
        if test_user:
            try:
                calculator = PortfolioPerformanceCalculator()
                current_value = calculator.calculate_current_portfolio_value(test_user.id)
                print(f"✓ Portfolio calculation working - User {test_user.username}: ${current_value}")
            except Exception as e:
                print(f"✗ Portfolio calculation failed: {str(e)}")
                results['issues'].append(f"Portfolio calculation error: {str(e)}")
        
        print("\n=== FINAL RESULTS ===")
        print(f"Users tested: {results['users_tested']}")
        print(f"Intraday snapshots today: {results['intraday_snapshots_today']}")
        print(f"End-of-day snapshots today: {results['eod_snapshots_today']}")
        print(f"Users with varying portfolio values: {results['portfolio_values_varying']}")
        print(f"Leaderboard updated: {'Yes' if results['leaderboard_updated'] else 'No'}")
        print(f"Users with chart data: {results['chart_data_available']}")
        
        if results['issues']:
            print(f"\n⚠ ISSUES FOUND ({len(results['issues'])}):")
            for issue in results['issues']:
                print(f"  - {issue}")
        else:
            print("\n✓ ALL TESTS PASSED - Cron jobs executed successfully!")
        
        return len(results['issues']) == 0
        
    except Exception as e:
        print(f"ERROR during testing: {str(e)}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        session.close()

if __name__ == "__main__":
    success = test_cron_execution()
    sys.exit(0 if success else 1)
