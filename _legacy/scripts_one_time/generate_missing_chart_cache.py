#!/usr/bin/env python3
"""
Generate Missing Chart Cache
============================
Generate missing 1D/5D chart cache for users who have snapshot data but no chart cache.
This explains why 1M/3M/YTD/1Y leaderboards work (all 5 users) but 1D/5D don't (missing cache).
"""

def generate_missing_chart_cache():
    """Generate missing 1D/5D chart cache for all users"""
    from datetime import datetime, date, timedelta
    from models import db, User, UserPortfolioChartCache
    from portfolio_performance import PortfolioPerformanceCalculator
    import json
    
    print("Generating missing chart cache for 1D/5D periods...")
    
    results = {
        'timestamp': datetime.now().isoformat(),
        'generated_cache': {},
        'errors': []
    }
    
    # Get all users with stocks
    users_with_stocks = User.query.join(User.stocks).distinct().all()
    print(f"Found {len(users_with_stocks)} users with stocks")
    
    for period in ['1D', '5D']:
        print(f"\nProcessing {period} period...")
        results['generated_cache'][period] = {
            'attempted': 0,
            'successful': 0,
            'already_cached': 0,
            'errors': []
        }
        
        for user in users_with_stocks:
            results['generated_cache'][period]['attempted'] += 1
            
            # Check if user already has cache for this period
            existing_cache = UserPortfolioChartCache.query.filter_by(
                user_id=user.id, 
                period=period
            ).first()
            
            if existing_cache:
                results['generated_cache'][period]['already_cached'] += 1
                print(f"  User {user.username} already has {period} cache")
                continue
            
            try:
                print(f"  Generating {period} cache for {user.username}...")
                
                # Generate chart data using PortfolioPerformanceCalculator
                calculator = PortfolioPerformanceCalculator(user.id)
                chart_data = calculator.get_performance_data(period)
                
                if chart_data and 'datasets' in chart_data and len(chart_data['datasets']) > 0:
                    # Create cache entry
                    cache_entry = UserPortfolioChartCache(
                        user_id=user.id,
                        period=period,
                        chart_data=json.dumps(chart_data),
                        generated_at=datetime.now()
                    )
                    db.session.add(cache_entry)
                    db.session.commit()
                    
                    results['generated_cache'][period]['successful'] += 1
                    print(f"    ✅ Generated {period} chart cache for {user.username}")
                else:
                    error_msg = f"No chart data generated for {user.username}"
                    results['generated_cache'][period]['errors'].append(error_msg)
                    print(f"    ❌ {error_msg}")
                    
            except Exception as e:
                error_msg = f"Failed to generate {period} cache for {user.username}: {str(e)}"
                results['generated_cache'][period]['errors'].append(error_msg)
                print(f"    ❌ {error_msg}")
                db.session.rollback()
    
    # Summary
    total_generated = sum(results['generated_cache'][p]['successful'] for p in ['1D', '5D'])
    print(f"\n✅ Generated {total_generated} missing chart cache entries")
    
    return results

def run_and_return_json():
    """API-friendly wrapper"""
    try:
        results = generate_missing_chart_cache()
        total_generated = sum(results['generated_cache'][p]['successful'] for p in ['1D', '5D'])
        
        return {
            'success': total_generated > 0,
            'message': f"Generated {total_generated} missing chart cache entries",
            'results': results
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'message': 'Failed to generate missing chart cache'
        }

if __name__ == '__main__':
    from app import app
    with app.app_context():
        result = run_and_return_json()
        print(f"\nFinal result: {result}")
