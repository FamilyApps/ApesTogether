#!/usr/bin/env python3
"""
Comprehensive S&P 500 Data Population Script
============================================
One-time script to populate ALL S&P 500 related caches:
1. MarketData - Raw daily S&P 500 prices
2. SP500ChartCache - Pre-generated S&P 500 charts for all periods
3. UserPortfolioChartCache - Regenerate user charts with S&P 500 data
4. LeaderboardCache - Regenerate leaderboards with S&P 500 comparisons

This ensures all chart periods (1D, 5D, 1M, 3M, YTD, 1Y) have complete S&P 500 benchmark data.
"""

import os
import sys
import requests
import time
import json
from datetime import datetime, date, timedelta
from decimal import Decimal

def populate_all_sp500_caches():
    """Populate ALL S&P 500 caches comprehensively"""
    
    print("🚀 Comprehensive S&P 500 Cache Population")
    print("=" * 60)
    
    results = {
        'step1_market_data': {},
        'step2_sp500_chart_cache': {},
        'step3_user_portfolio_charts': {},
        'step4_leaderboard_cache': {},
        'summary': {}
    }
    
    # Step 1: Populate raw MarketData
    print("\n📊 STEP 1: Populating MarketData (Raw S&P 500 prices)")
    print("-" * 50)
    
    step1_result = populate_market_data()
    results['step1_market_data'] = step1_result
    
    if not step1_result.get('success', False):
        print("❌ Step 1 failed - cannot continue")
        return results
    
    # Step 2: Generate SP500ChartCache
    print("\n📈 STEP 2: Generating SP500ChartCache (Pre-generated charts)")
    print("-" * 50)
    
    step2_result = populate_sp500_chart_cache()
    results['step2_sp500_chart_cache'] = step2_result
    
    # Step 3: Regenerate UserPortfolioChartCache with S&P 500 data
    print("\n👥 STEP 3: Regenerating UserPortfolioChartCache (User charts with S&P 500)")
    print("-" * 50)
    
    step3_result = regenerate_user_portfolio_charts()
    results['step3_user_portfolio_charts'] = step3_result
    
    # Step 4: Regenerate LeaderboardCache with S&P 500 comparisons
    print("\n🏆 STEP 4: Regenerating LeaderboardCache (Leaderboards with S&P 500)")
    print("-" * 50)
    
    step4_result = regenerate_leaderboard_cache()
    results['step4_leaderboard_cache'] = step4_result
    
    # Summary
    print("\n📋 SUMMARY")
    print("=" * 60)
    
    total_success = sum(1 for step in [step1_result, step2_result, step3_result, step4_result] 
                       if step.get('success', False))
    
    print(f"✅ Successful steps: {total_success}/4")
    
    for i, (step_name, result) in enumerate([
        ("MarketData Population", step1_result),
        ("SP500ChartCache Generation", step2_result), 
        ("UserPortfolioChartCache Regeneration", step3_result),
        ("LeaderboardCache Regeneration", step4_result)
    ], 1):
        status = "✅" if result.get('success', False) else "❌"
        print(f"  {status} Step {i}: {step_name}")
        if result.get('message'):
            print(f"      {result['message']}")
    
    results['summary'] = {
        'total_steps': 4,
        'successful_steps': total_success,
        'overall_success': total_success >= 3  # At least 3/4 steps must succeed
    }
    
    return results

def populate_market_data():
    """Step 1: Analyze existing S&P 500 data and only fill critical gaps (SAFE MODE)"""
    
    try:
        from models import db, MarketData
        
        # Check existing S&P 500 data
        sp500_ticker = "SPY_SP500"
        existing_count = MarketData.query.filter_by(ticker=sp500_ticker).count()
        print(f"📊 Existing S&P 500 data points: {existing_count}")
        
        if existing_count == 0:
            print("❌ No existing S&P 500 data found!")
            print("🚨 CRITICAL: You mentioned you already have clean S&P 500 data.")
            print("🚨 This suggests the data might be stored under a different ticker.")
            print("🔍 Let me check for alternative S&P 500 tickers...")
            
            # Check for alternative tickers
            alternative_tickers = ['SPY', 'SP500', 'SPX', 'SPY_INTRADAY']
            for ticker in alternative_tickers:
                count = MarketData.query.filter_by(ticker=ticker).count()
                if count > 0:
                    latest_date = db.session.query(MarketData.date).filter_by(ticker=ticker).order_by(MarketData.date.desc()).first()
                    print(f"  📈 Found {count} records under ticker '{ticker}' (latest: {latest_date[0] if latest_date else 'None'})")
            
            return {
                'success': False,
                'error': 'No SPY_SP500 data found. Please check existing data first.',
                'recommendation': 'Run data audit to identify existing S&P 500 data location'
            }
        
        # Analyze existing data quality
        print(f"\n🔍 ANALYZING EXISTING S&P 500 DATA QUALITY")
        print("-" * 50)
        
        # Get date range of existing data
        earliest_date = db.session.query(MarketData.date).filter_by(ticker=sp500_ticker).order_by(MarketData.date.asc()).first()
        latest_date = db.session.query(MarketData.date).filter_by(ticker=sp500_ticker).order_by(MarketData.date.desc()).first()
        
        if earliest_date and latest_date:
            print(f"📅 Existing data range: {earliest_date[0]} to {latest_date[0]}")
            print(f"📊 Total span: {(latest_date[0] - earliest_date[0]).days} days")
        
        # Check for data quality issues (same logic as debug_ytd_sp500.py)
        zero_prices = MarketData.query.filter(
            MarketData.ticker == sp500_ticker,
            MarketData.close_price == 0
        ).count()
        
        low_prices = MarketData.query.filter(
            MarketData.ticker == sp500_ticker,
            MarketData.close_price < 100,
            MarketData.close_price > 0
        ).count()
        
        print(f"✅ Data quality check:")
        print(f"  Zero prices: {zero_prices}")
        print(f"  Suspiciously low prices (< $100): {low_prices}")
        
        if zero_prices > 0 or low_prices > 0:
            print(f"⚠️  WARNING: Found {zero_prices + low_prices} potentially problematic records")
            print(f"🚨 RECOMMENDATION: Review and clean data manually before proceeding")
            
            return {
                'success': False,
                'error': f'Data quality issues detected: {zero_prices} zero prices, {low_prices} low prices',
                'recommendation': 'Clean existing data before populating caches'
            }
        
        # Check coverage for key chart periods
        today = date.today()
        periods_to_check = {
            '1M': today - timedelta(days=30),
            '3M': today - timedelta(days=90), 
            'YTD': date(today.year, 1, 1),
            '1Y': today - timedelta(days=365)
        }
        
        print(f"\n📈 CHECKING COVERAGE FOR CHART PERIODS")
        print("-" * 50)
        
        all_good = True
        for period_name, start_date in periods_to_check.items():
            period_count = MarketData.query.filter(
                MarketData.ticker == sp500_ticker,
                MarketData.date >= start_date,
                MarketData.date <= today
            ).count()
            
            # Estimate expected business days
            total_days = (today - start_date).days
            expected_business_days = total_days * 5 // 7  # Rough estimate
            coverage = (period_count / expected_business_days * 100) if expected_business_days > 0 else 0
            
            status = "✅" if coverage > 80 else "⚠️" if coverage > 50 else "❌"
            print(f"  {status} {period_name}: {period_count} points ({coverage:.1f}% coverage)")
            
            if coverage < 80:
                all_good = False
        
        if all_good:
            print(f"\n🎉 EXCELLENT! Your existing S&P 500 data looks clean and comprehensive.")
            print(f"📈 No need to fetch new data - we can use what you have!")
            
            return {
                'success': True,
                'new_records': 0,
                'updated_records': 0,
                'total_processed': existing_count,
                'message': 'Using existing clean S&P 500 data',
                'data_source': 'existing_clean_data'
            }
        else:
            print(f"\n🔍 Some chart periods have low coverage.")
            print(f"💡 RECOMMENDATION: Use existing data and only fill critical gaps if needed.")
            
            return {
                'success': True,
                'new_records': 0,
                'updated_records': 0,
                'total_processed': existing_count,
                'message': 'Using existing data with some gaps',
                'data_source': 'existing_data_with_gaps',
                'recommendation': 'Consider filling gaps for periods with <80% coverage'
            }
        
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        return {'success': False, 'error': str(e)}

def populate_sp500_chart_cache():
    """Step 2: Generate SP500ChartCache for all periods"""
    try:
        from models import db, SP500ChartCache, MarketData
        import json
        
        print("Generating S&P 500 chart cache...")
        
        periods = ['1D', '5D', '1M', '3M', 'YTD', '1Y']
        generated_count = 0
        
        for period in periods:
            try:
                # Generate chart data for this period
                chart_data = generate_sp500_chart_data(period)
                
                if chart_data:
                    # Update or create cache entry
                    cache_entry = SP500ChartCache.query.filter_by(period=period).first()
                    if cache_entry:
                        cache_entry.chart_data = json.dumps(chart_data)
                        cache_entry.generated_at = datetime.now()
                        cache_entry.expires_at = datetime.now() + timedelta(hours=24)
                    else:
                        cache_entry = SP500ChartCache(
                            period=period,
                            chart_data=json.dumps(chart_data),
                            generated_at=datetime.now(),
                            expires_at=datetime.now() + timedelta(hours=24)
                        )
                        db.session.add(cache_entry)
                    
                    generated_count += 1
                    print(f"  ✅ Generated {period} chart cache")
                else:
                    print(f"  ⚠️ No data for {period} chart")
                    
            except Exception as e:
                print(f"  ❌ Error generating {period} chart: {str(e)}")
                continue
        
        db.session.commit()
        
        return {
            'success': True,
            'generated_count': generated_count,
            'message': f'Generated {generated_count} S&P 500 chart caches'
        }
        
    except Exception as e:
        return {'success': False, 'error': str(e)}

def generate_sp500_chart_data(period):
    """Generate chart data for a specific period"""
    from models import MarketData
    
    # Calculate date range
    today = date.today()
    
    if period == '1D':
        start_date = today - timedelta(days=1)
    elif period == '5D':
        start_date = today - timedelta(days=7)  # Get a week to ensure 5 business days
    elif period == '1M':
        start_date = today - timedelta(days=30)
    elif period == '3M':
        start_date = today - timedelta(days=90)
    elif period == 'YTD':
        start_date = date(today.year, 1, 1)
    elif period == '1Y':
        start_date = today - timedelta(days=365)
    else:
        return None
    
    # Get S&P 500 data for the period
    sp500_data = MarketData.query.filter(
        MarketData.ticker == 'SPY_SP500',
        MarketData.date >= start_date,
        MarketData.date <= today
    ).order_by(MarketData.date.asc()).all()
    
    if not sp500_data:
        return None
    
    # Convert to chart format
    chart_points = []
    start_value = sp500_data[0].close_price
    
    for data_point in sp500_data:
        pct_change = ((data_point.close_price - start_value) / start_value) * 100
        chart_points.append({
            'date': data_point.date.isoformat(),
            'value': data_point.close_price,
            'pct_change': round(pct_change, 2)
        })
    
    return {
        'period': period,
        'data': chart_points,
        'start_value': start_value,
        'end_value': sp500_data[-1].close_price,
        'total_return': round(((sp500_data[-1].close_price - start_value) / start_value) * 100, 2)
    }

def regenerate_user_portfolio_charts():
    """Step 3: Regenerate UserPortfolioChartCache with S&P 500 data"""
    try:
        from leaderboard_utils import update_leaderboard_cache
        
        print("Regenerating user portfolio charts...")
        
        # This will regenerate charts for leaderboard users with S&P 500 data
        updated_count = update_leaderboard_cache()
        
        return {
            'success': True,
            'updated_count': updated_count,
            'message': f'Regenerated {updated_count} user portfolio charts'
        }
        
    except Exception as e:
        return {'success': False, 'error': str(e)}

def regenerate_leaderboard_cache():
    """Step 4: Regenerate LeaderboardCache with S&P 500 comparisons"""
    try:
        from leaderboard_utils import update_leaderboard_cache
        
        print("Regenerating leaderboard cache...")
        
        # Force regeneration of all leaderboard data
        updated_count = update_leaderboard_cache()
        
        return {
            'success': True,
            'updated_count': updated_count,
            'message': f'Regenerated {updated_count} leaderboard cache entries'
        }
        
    except Exception as e:
        return {'success': False, 'error': str(e)}

def run_fix_and_return_json():
    """API-friendly wrapper for admin endpoint"""
    try:
        results = populate_all_sp500_caches()
        
        if results['summary'].get('overall_success', False):
            return {
                'success': True,
                'message': 'S&P 500 data population completed successfully',
                'results': results
            }
        else:
            return {
                'success': False,
                'error': 'S&P 500 data population failed',
                'results': results
            }
    
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'message': 'Failed to populate S&P 500 data'
        }

if __name__ == '__main__':
    # Load environment if running standalone
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    
    # Set up Flask app context if running standalone
    try:
        from app import app
        with app.app_context():
            results = populate_all_sp500_caches()
            print(f"\nFinal Results: {results}")
            sys.exit(0 if results['summary'].get('overall_success', False) else 1)
    except ImportError:
        # Try api/index.py context
        try:
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'api'))
            from index import app
            with app.app_context():
                results = populate_all_sp500_caches()
                print(f"\nFinal Results: {results}")
                sys.exit(0 if results['summary'].get('overall_success', False) else 1)
        except ImportError:
            print("❌ Error: Could not import Flask app. Run this script from the project root.")
            sys.exit(1)
