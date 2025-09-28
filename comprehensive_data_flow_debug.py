#!/usr/bin/env python3
"""
Comprehensive Data Flow Debug
=============================
Trace the complete data flow from snapshots → calculations → cache → display
to identify where Friday 9/26/2025 data is missing.

Flow: UserPortfolioSnapshot → calculate_leaderboard_data() → LeaderboardCache → get_leaderboard_data() → Homepage
"""

def comprehensive_data_flow_debug():
    """Debug the complete data flow for leaderboards, charts, and portfolio features with performance timing"""
    from datetime import datetime, date, timedelta
    from models import db, User, PortfolioSnapshot, LeaderboardCache, UserPortfolioChartCache
    from leaderboard_utils import calculate_leaderboard_data, get_leaderboard_data
    import json
    import time
    
    print("🔍 COMPREHENSIVE DATA FLOW & PERFORMANCE DEBUG")
    print("=" * 80)
    
    # Key dates
    friday_date = date(2025, 9, 26)  # The missing Friday
    today = date.today()
    
    print(f"Target Friday: {friday_date}")
    print(f"Today: {today}")
    print(f"Days since Friday: {(today - friday_date).days}")
    
    results = {
        'friday_date': str(friday_date),
        'today': str(today),
        'step1_snapshots': {},
        'step2_leaderboard_calculations': {},
        'step3_leaderboard_cache_storage': {},
        'step4_leaderboard_cache_retrieval': {},
        'step5_chart_data_generation': {},
        'step6_chart_cache_storage': {},
        'step7_chart_display': {},
        'step8_portfolio_summary_flow': {},
        'step9_portfolio_allocation_flow': {},
        'step10_performance_timing': {},
        'step11_comparison_analysis': {}
    }
    
    # Get all users with stocks
    users_with_stocks = User.query.join(User.stocks).distinct().all()
    print(f"\n👥 Found {len(users_with_stocks)} users with stocks")
    
    # STEP 1: Check UserPortfolioSnapshot data
    print(f"\n📊 STEP 1: UserPortfolioSnapshot Analysis")
    print("-" * 50)
    
    for user in users_with_stocks:
        print(f"\n  User: {user.username} (ID: {user.id})")
        
        # Check snapshots for last 10 days
        snapshots = {}
        for i in range(10):
            check_date = today - timedelta(days=i)
            snapshot = PortfolioSnapshot.query.filter_by(
                user_id=user.id,
                date=check_date
            ).first()
            
            if snapshot:
                snapshots[str(check_date)] = {
                    'exists': True,
                    'total_value': float(snapshot.total_value),
                    'is_friday': check_date == friday_date
                }
                status = "🟢" if check_date != friday_date else "🔴 FRIDAY"
                print(f"    {check_date}: ${snapshot.total_value:.2f} {status}")
            else:
                snapshots[str(check_date)] = {
                    'exists': False,
                    'total_value': None,
                    'is_friday': check_date == friday_date
                }
                status = "❌" if check_date == friday_date else "⚪"
                print(f"    {check_date}: No snapshot {status}")
        
        results['step1_snapshots'][user.username] = snapshots
    
    # STEP 2: Test calculate_leaderboard_data() for each period
    print(f"\n🧮 STEP 2: Leaderboard Calculations (calculate_leaderboard_data)")
    print("-" * 50)
    
    for period in ['1D', '5D', '1M', 'YTD']:
        print(f"\n  Testing {period} period calculation...")
        
        try:
            # Time the calculation
            start_time = time.time()
            leaderboard_data = calculate_leaderboard_data(period, 10, 'all')
            calc_time = time.time() - start_time
            
            print(f"    ✅ {period}: {len(leaderboard_data)} entries calculated in {calc_time:.2f}s")
            
            # Show top 3 entries
            for i, entry in enumerate(leaderboard_data[:3]):
                print(f"      {i+1}. {entry['username']}: {entry['performance_percent']:.2f}%")
            
            results['step2_leaderboard_calculations'][period] = {
                'success': True,
                'entries_count': len(leaderboard_data),
                'calculation_time_seconds': calc_time,
                'top_3': leaderboard_data[:3] if leaderboard_data else []
            }
            
        except Exception as e:
            print(f"    ❌ {period}: Error - {str(e)}")
            results['step2_leaderboard_calculations'][period] = {
                'success': False,
                'error': str(e),
                'entries_count': 0
            }
    
    # STEP 3: Check LeaderboardCache storage
    print(f"\n💾 STEP 3: LeaderboardCache Storage Analysis")
    print("-" * 50)
    
    for period in ['1D', '5D', '1M', 'YTD']:
        for category in ['all', 'small_cap', 'large_cap']:
            cache_key = f"{period}_{category}"
            
            cache_entry = LeaderboardCache.query.filter_by(period=cache_key).first()
            
            if cache_entry:
                try:
                    cached_data = json.loads(cache_entry.leaderboard_data)
                    print(f"    ✅ {cache_key}: {len(cached_data)} entries (generated: {cache_entry.generated_at})")
                    
                    results['step3_leaderboard_cache_storage'][cache_key] = {
                        'exists': True,
                        'entries_count': len(cached_data),
                        'generated_at': str(cache_entry.generated_at),
                        'top_entry': cached_data[0] if cached_data else None
                    }
                    
                except Exception as e:
                    print(f"    ⚠️ {cache_key}: Exists but parse error - {str(e)}")
                    results['step3_leaderboard_cache_storage'][cache_key] = {
                        'exists': True,
                        'parse_error': str(e)
                    }
            else:
                print(f"    ❌ {cache_key}: No cache entry")
                results['step3_leaderboard_cache_storage'][cache_key] = {
                    'exists': False
                }
    
    # STEP 4: Test get_leaderboard_data() retrieval
    print(f"\n📤 STEP 4: get_leaderboard_data() Retrieval Testing")
    print("-" * 50)
    
    for period in ['1D', '5D', '1M', 'YTD']:
        try:
            retrieved_data = get_leaderboard_data(period, 10, 'all')
            
            print(f"    ✅ {period}: Retrieved {len(retrieved_data)} entries")
            
            # Show top 3
            for i, entry in enumerate(retrieved_data[:3]):
                print(f"      {i+1}. {entry['username']}: {entry['performance_percent']:.2f}%")
            
            results['step4_leaderboard_cache_retrieval'][period] = {
                'success': True,
                'entries_count': len(retrieved_data),
                'top_3': retrieved_data[:3] if retrieved_data else []
            }
            
        except Exception as e:
            print(f"    ❌ {period}: Error - {str(e)}")
            results['step4_leaderboard_cache_retrieval'][period] = {
                'success': False,
                'error': str(e)
            }
    
    # STEP 5: Test chart data generation (PortfolioPerformanceCalculator)
    print(f"\n📈 STEP 5: Chart Data Generation (PortfolioPerformanceCalculator)")
    print("-" * 50)
    
    from portfolio_performance import PortfolioPerformanceCalculator
    
    # Test chart generation for a sample user
    sample_user = users_with_stocks[0] if users_with_stocks else None
    if sample_user:
        print(f"\n  Testing chart generation for {sample_user.username}...")
        
        for period in ['1D', '5D', '1M', 'YTD']:
            try:
                # Time the chart generation
                start_time = time.time()
                calculator = PortfolioPerformanceCalculator(sample_user.id)
                chart_data = calculator.get_performance_data(period)
                gen_time = time.time() - start_time
                
                if chart_data and 'datasets' in chart_data:
                    labels = chart_data.get('labels', [])
                    datasets = chart_data.get('datasets', [])
                    
                    # Check if Friday is in generated chart data
                    friday_str = friday_date.strftime('%Y-%m-%d')
                    friday_in_chart = friday_str in labels
                    
                    print(f"    ✅ {period}: Generated {len(labels)} data points in {gen_time:.2f}s, Friday included: {friday_in_chart}")
                    
                    if not friday_in_chart and len(labels) > 0:
                        print(f"      Last data point: {labels[-1]}")
                    
                    # Get performance data
                    portfolio_data = datasets[0].get('data', []) if datasets else []
                    performance = 0.0
                    if len(portfolio_data) >= 2:
                        start_val = portfolio_data[0]
                        end_val = portfolio_data[-1]
                        if start_val > 0:
                            performance = ((end_val - start_val) / start_val) * 100
                    
                    results['step5_chart_data_generation'][period] = {
                        'success': True,
                        'generation_time_seconds': gen_time,
                        'data_points': len(labels),
                        'friday_included': friday_in_chart,
                        'last_data_point': labels[-1] if labels else None,
                        'calculated_performance': performance
                    }
                    
                else:
                    print(f"    ❌ {period}: No chart data generated")
                    results['step5_chart_data_generation'][period] = {
                        'success': False,
                        'error': 'No chart data generated'
                    }
                    
            except Exception as e:
                print(f"    ❌ {period}: Error - {str(e)}")
                results['step5_chart_data_generation'][period] = {
                    'success': False,
                    'error': str(e)
                }
    
    # STEP 6: Check UserPortfolioChartCache storage
    print(f"\n💾 STEP 6: UserPortfolioChartCache Storage Analysis")
    print("-" * 50)
    
    for period in ['1D', '5D', '1M', 'YTD']:
        cached_users = UserPortfolioChartCache.query.filter_by(period=period).all()
        
        print(f"\n  {period} Chart Cache: {len(cached_users)}/{len(users_with_stocks)} users")
        
        results['step6_chart_cache_storage'][period] = {
            'cached_users_count': len(cached_users),
            'total_users': len(users_with_stocks),
            'users_with_cache': []
        }
        
        for cache_entry in cached_users:
            user = User.query.get(cache_entry.user_id)
            if user:
                try:
                    chart_data = json.loads(cache_entry.chart_data)
                    labels = chart_data.get('labels', [])
                    
                    # Check if Friday is in the cached chart data
                    friday_str = friday_date.strftime('%Y-%m-%d')
                    friday_in_chart = friday_str in labels
                    
                    print(f"    {user.username}: {len(labels)} data points, Friday included: {friday_in_chart}")
                    
                    if not friday_in_chart and len(labels) > 0:
                        print(f"      Last data point: {labels[-1]}")
                    
                    # Get performance from cached data
                    datasets = chart_data.get('datasets', [])
                    portfolio_data = datasets[0].get('data', []) if datasets else []
                    cached_performance = 0.0
                    if len(portfolio_data) >= 2:
                        start_val = portfolio_data[0]
                        end_val = portfolio_data[-1]
                        if start_val > 0:
                            cached_performance = ((end_val - start_val) / start_val) * 100
                    
                    results['step6_chart_cache_storage'][period]['users_with_cache'].append({
                        'username': user.username,
                        'data_points': len(labels),
                        'friday_included': friday_in_chart,
                        'last_data_point': labels[-1] if labels else None,
                        'cached_performance': cached_performance
                    })
                    
                except Exception as e:
                    print(f"    {user.username}: Chart parse error - {str(e)}")
    
    # STEP 7: Test chart display endpoints
    print(f"\n🖥️ STEP 7: Chart Display Endpoint Testing")
    print("-" * 50)
    
    if sample_user:
        print(f"\n  Testing chart endpoints for {sample_user.username}...")
        
        # This would test the actual chart endpoints that the frontend calls
        # For now, we'll just verify the cached data matches what would be displayed
        for period in ['1D', '5D', '1M', 'YTD']:
            cache_entry = UserPortfolioChartCache.query.filter_by(
                user_id=sample_user.id,
                period=period
            ).first()
            
            if cache_entry:
                try:
                    chart_data = json.loads(cache_entry.chart_data)
                    labels = chart_data.get('labels', [])
                    datasets = chart_data.get('datasets', [])
                    
                    print(f"    ✅ {period}: Chart endpoint would show {len(labels)} data points")
                    
                    results['step7_chart_display'][period] = {
                        'available': True,
                        'data_points': len(labels),
                        'datasets_count': len(datasets)
                    }
                    
                except Exception as e:
                    print(f"    ⚠️ {period}: Chart data parse error - {str(e)}")
                    results['step7_chart_display'][period] = {
                        'available': True,
                        'parse_error': str(e)
                    }
            else:
                print(f"    ❌ {period}: No cached chart data")
                results['step7_chart_display'][period] = {
                    'available': False
                }
    
    # STEP 8: Portfolio Summary Flow Analysis
    print(f"\n📋 STEP 8: Portfolio Summary Flow Analysis")
    print("-" * 50)
    
    if sample_user:
        print(f"\n  Testing Portfolio Summary for {sample_user.username}...")
        
        try:
            # Test portfolio summary calculation (should use same snapshots)
            start_time = time.time()
            
            # Get current portfolio value from latest snapshot
            latest_snapshot = PortfolioSnapshot.query.filter_by(
                user_id=sample_user.id
            ).order_by(PortfolioSnapshot.date.desc()).first()
            
            summary_time = time.time() - start_time
            
            if latest_snapshot:
                friday_str = friday_date.strftime('%Y-%m-%d')
                is_friday_data = str(latest_snapshot.date) == friday_str
                
                print(f"    ✅ Portfolio Summary: ${latest_snapshot.total_value:.2f} (calculated in {summary_time:.3f}s)")
                print(f"    Latest data from: {latest_snapshot.date} (is Friday: {is_friday_data})")
                
                results['step8_portfolio_summary_flow'] = {
                    'success': True,
                    'calculation_time_seconds': summary_time,
                    'current_value': float(latest_snapshot.total_value),
                    'latest_date': str(latest_snapshot.date),
                    'uses_friday_data': is_friday_data
                }
            else:
                print(f"    ❌ Portfolio Summary: No snapshot data found")
                results['step8_portfolio_summary_flow'] = {
                    'success': False,
                    'error': 'No snapshot data found'
                }
                
        except Exception as e:
            print(f"    ❌ Portfolio Summary: Error - {str(e)}")
            results['step8_portfolio_summary_flow'] = {
                'success': False,
                'error': str(e)
            }
    
    # STEP 9: Portfolio Allocation Flow Analysis  
    print(f"\n🥧 STEP 9: Portfolio Allocation Flow Analysis")
    print("-" * 50)
    
    if sample_user:
        print(f"\n  Testing Portfolio Allocation for {sample_user.username}...")
        
        try:
            # Test portfolio allocation calculation (should use current holdings + stock info)
            start_time = time.time()
            
            from models import UserStock, StockInfo
            
            # Get user's current stock holdings
            user_stocks = UserStock.query.filter_by(user_id=sample_user.id).all()
            
            allocation_data = {}
            total_value = 0
            
            for user_stock in user_stocks:
                stock_info = StockInfo.query.filter_by(ticker=user_stock.ticker).first()
                if stock_info and user_stock.current_price:
                    position_value = user_stock.shares * user_stock.current_price
                    total_value += position_value
                    
                    allocation_data[user_stock.ticker] = {
                        'shares': user_stock.shares,
                        'current_price': user_stock.current_price,
                        'position_value': position_value,
                        'cap_classification': stock_info.cap_classification if stock_info else 'unknown'
                    }
            
            allocation_time = time.time() - start_time
            
            # Calculate cap allocation percentages
            small_cap_value = sum(data['position_value'] for data in allocation_data.values() 
                                if data['cap_classification'] == 'small')
            large_cap_value = sum(data['position_value'] for data in allocation_data.values() 
                                if data['cap_classification'] == 'large')
            
            small_cap_percent = (small_cap_value / total_value * 100) if total_value > 0 else 0
            large_cap_percent = (large_cap_value / total_value * 100) if total_value > 0 else 0
            
            print(f"    ✅ Portfolio Allocation: {len(user_stocks)} positions (calculated in {allocation_time:.3f}s)")
            print(f"    Total Value: ${total_value:.2f}")
            print(f"    Small Cap: {small_cap_percent:.1f}%, Large Cap: {large_cap_percent:.1f}%")
            
            results['step9_portfolio_allocation_flow'] = {
                'success': True,
                'calculation_time_seconds': allocation_time,
                'positions_count': len(user_stocks),
                'total_value': total_value,
                'small_cap_percent': small_cap_percent,
                'large_cap_percent': large_cap_percent,
                'allocation_data': allocation_data
            }
            
        except Exception as e:
            print(f"    ❌ Portfolio Allocation: Error - {str(e)}")
            results['step9_portfolio_allocation_flow'] = {
                'success': False,
                'error': str(e)
            }
    
    # STEP 10: Performance Timing Analysis
    print(f"\n⏱️ STEP 10: Performance Timing Analysis")
    print("-" * 50)
    
    print("\n  Timing Summary:")
    timing_data = {}
    
    # Collect timing data from previous steps
    for period in ['1D', '5D', '1M', 'YTD']:
        leaderboard_time = results['step2_leaderboard_calculations'][period].get('calculation_time_seconds', 0)
        chart_time = results['step5_chart_data_generation'].get(period, {}).get('generation_time_seconds', 0)
        
        timing_data[period] = {
            'leaderboard_calculation': leaderboard_time,
            'chart_generation': chart_time,
            'total_time': leaderboard_time + chart_time
        }
        
        print(f"    {period}: Leaderboard {leaderboard_time:.2f}s + Chart {chart_time:.2f}s = {leaderboard_time + chart_time:.2f}s total")
    
    # Portfolio feature timing
    summary_time = results['step8_portfolio_summary_flow'].get('calculation_time_seconds', 0)
    allocation_time = results['step9_portfolio_allocation_flow'].get('calculation_time_seconds', 0)
    
    print(f"    Portfolio Summary: {summary_time:.3f}s")
    print(f"    Portfolio Allocation: {allocation_time:.3f}s")
    
    # Identify bottlenecks
    slowest_operations = []
    for period, times in timing_data.items():
        if times['total_time'] > 1.0:  # Operations taking more than 1 second
            slowest_operations.append(f"{period} ({times['total_time']:.2f}s)")
    
    if slowest_operations:
        print(f"\n    🐌 Slow Operations (>1s): {', '.join(slowest_operations)}")
    else:
        print(f"\n    ⚡ All operations under 1 second")
    
    results['step10_performance_timing'] = {
        'period_timing': timing_data,
        'portfolio_summary_time': summary_time,
        'portfolio_allocation_time': allocation_time,
        'slow_operations': slowest_operations
    }
    
    # STEP 11: Comprehensive Comparison Analysis
    print(f"\n🔄 STEP 11: Comprehensive Comparison Analysis")
    print("-" * 50)
    
    print("\n  Data Consistency Check:")
    
    for period in ['1D', '5D', '1M', 'YTD']:
        leaderboard_success = results['step2_leaderboard_calculations'][period]['success']
        leaderboard_entries = results['step2_leaderboard_calculations'][period]['entries_count']
        
        chart_success = results['step5_chart_data_generation'].get(period, {}).get('success', False)
        chart_points = results['step5_chart_data_generation'].get(period, {}).get('data_points', 0)
        
        cache_users = results['step6_chart_cache_storage'][period]['cached_users_count']
        
        # Check Friday data consistency
        leaderboard_friday = "Unknown"
        chart_friday = results['step5_chart_data_generation'].get(period, {}).get('friday_included', False)
        
        print(f"    {period}:")
        print(f"      Leaderboard: {'✅' if leaderboard_success else '❌'} ({leaderboard_entries} entries)")
        print(f"      Chart Gen: {'✅' if chart_success else '❌'} ({chart_points} points, Friday: {chart_friday})")
        print(f"      Chart Cache: {cache_users}/{len(users_with_stocks)} users")
        
        # Identify inconsistencies
        inconsistencies = []
        if leaderboard_success and chart_success:
            if leaderboard_entries != len(users_with_stocks):
                inconsistencies.append("Missing leaderboard entries")
            if cache_users != len(users_with_stocks):
                inconsistencies.append("Incomplete chart cache")
            if not chart_friday:
                inconsistencies.append("Missing Friday data")
        
        if inconsistencies:
            print(f"      ⚠️ Issues: {', '.join(inconsistencies)}")
        else:
            print(f"      ✅ Consistent")
    
    # Overall system health
    total_issues = 0
    critical_issues = []
    
    # Check for critical issues
    friday_snapshots = sum(1 for user in users_with_stocks 
                          if results['step1_snapshots'][user.username].get(str(friday_date), {}).get('exists', False))
    
    if friday_snapshots < len(users_with_stocks):
        critical_issues.append(f"Missing Friday snapshots ({friday_snapshots}/{len(users_with_stocks)})")
        total_issues += 1
    
    # Check for slow operations
    if results['step10_performance_timing']['slow_operations']:
        critical_issues.append(f"Slow operations: {', '.join(results['step10_performance_timing']['slow_operations'])}")
        total_issues += 1
    
    print(f"\n  🏥 System Health:")
    if total_issues == 0:
        print(f"    ✅ All systems operational")
    else:
        print(f"    ⚠️ {total_issues} critical issues found:")
        for issue in critical_issues:
            print(f"      - {issue}")
    
    results['step11_comparison_analysis'] = {
        'friday_snapshots': f"{friday_snapshots}/{len(users_with_stocks)}",
        'critical_issues': critical_issues,
        'total_issues': total_issues,
        'system_health': 'healthy' if total_issues == 0 else 'degraded'
    }
    
    # SUMMARY
    print(f"\n📋 SUMMARY")
    print("=" * 80)
    
    # Check if Friday snapshots exist for all users
    friday_snapshots = sum(1 for user in users_with_stocks 
                          if results['step1_snapshots'][user.username].get(str(friday_date), {}).get('exists', False))
    
    print(f"Friday Snapshots: {friday_snapshots}/{len(users_with_stocks)} users")
    
    # Check calculation success
    calc_success = sum(1 for period in ['1D', '5D', '1M', 'YTD'] 
                      if results['step2_calculations'][period]['success'])
    
    print(f"Calculation Success: {calc_success}/4 periods")
    
    # Check cache storage
    cache_stored = sum(1 for period in ['1D', '5D', '1M', 'YTD'] 
                      if results['step3_cache_storage'].get(f"{period}_all", {}).get('exists', False))
    
    print(f"Cache Storage: {cache_stored}/4 periods")
    
    # Check retrieval success
    retrieval_success = sum(1 for period in ['1D', '5D', '1M', 'YTD'] 
                           if results['step4_cache_retrieval'][period]['success'])
    
    print(f"Cache Retrieval: {retrieval_success}/4 periods")
    
    return results

def run_and_return_json():
    """API-friendly wrapper"""
    try:
        results = comprehensive_data_flow_debug()
        return {
            'success': True,
            'message': 'Comprehensive data flow analysis completed',
            'results': results
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'message': 'Failed to complete data flow analysis'
        }

if __name__ == '__main__':
    from app import app
    with app.app_context():
        result = run_and_return_json()
        print(f"\nAnalysis completed: {result['success']}")
