"""
COMPREHENSIVE DIAGNOSTIC: Trace entire data flow from raw data to chart display

Add this to api/index.py as @app.route('/admin/diagnose-full-chart-flow/<username>/<period>')
"""

from flask import jsonify
from datetime import datetime
import json

def diagnose_full_chart_flow(username, period):
    """Trace the complete data flow for chart generation"""
    
    from models import User, PortfolioSnapshot, MarketData, UserPortfolioChartCache
    from leaderboard_utils import generate_chart_from_snapshots
    from performance_calculator import calculate_portfolio_performance, get_period_dates
    from sqlalchemy import text
    
    results = {
        'timestamp': datetime.now().isoformat(),
        'username': username,
        'period': period.upper(),
        'steps': []
    }
    
    try:
        # STEP 1: Find user
        user = User.query.filter_by(username=username).first()
        if not user:
            return jsonify({'error': f'User {username} not found'}), 404
        
        results['user_id'] = user.id
        results['steps'].append({'step': 1, 'name': 'User lookup', 'status': 'OK'})
        
        # STEP 2: Check raw portfolio snapshots
        snapshots = PortfolioSnapshot.query.filter_by(user_id=user.id).order_by(
            PortfolioSnapshot.date.desc()
        ).limit(10).all()
        
        snapshot_dates = [s.date.isoformat() for s in snapshots]
        results['steps'].append({
            'step': 2,
            'name': 'Portfolio snapshots',
            'count': len(snapshots),
            'latest_date': snapshot_dates[0] if snapshot_dates else None,
            'recent_dates': snapshot_dates[:5],
            'has_oct_27': '2025-10-27' in snapshot_dates,
            'status': 'OK' if '2025-10-27' in snapshot_dates else 'MISSING_OCT_27'
        })
        
        # STEP 3: Check S&P 500 data for period
        start_date, end_date = get_period_dates(period.upper(), user_id=user.id)
        sp500_data = MarketData.query.filter(
            MarketData.ticker == 'SPY_SP500',
            MarketData.date >= start_date,
            MarketData.date <= end_date
        ).order_by(MarketData.date).all()
        
        sp500_dates = [s.date.isoformat() for s in sp500_data]
        results['steps'].append({
            'step': 3,
            'name': 'S&P 500 data',
            'period_start': start_date.isoformat(),
            'period_end': end_date.isoformat(),
            'count': len(sp500_data),
            'latest_date': sp500_dates[-1] if sp500_dates else None,
            'has_oct_27': '2025-10-27' in sp500_dates,
            'status': 'OK' if '2025-10-27' in sp500_dates else 'MISSING_OCT_27'
        })
        
        # STEP 4: Call generate_chart_from_snapshots (what cron uses)
        chart_data_generated = generate_chart_from_snapshots(user.id, period.upper())
        
        if chart_data_generated:
            labels = chart_data_generated.get('labels', [])
            datasets = chart_data_generated.get('datasets', [])
            
            results['steps'].append({
                'step': 4,
                'name': 'generate_chart_from_snapshots',
                'labels_count': len(labels),
                'first_label': labels[0] if labels else None,
                'last_label': labels[-1] if labels else None,
                'all_labels': labels,
                'has_oct_27': 'Oct 27' in labels,
                'datasets_count': len(datasets),
                'status': 'OK' if 'Oct 27' in labels else 'MISSING_OCT_27_IN_OUTPUT'
            })
        else:
            results['steps'].append({
                'step': 4,
                'name': 'generate_chart_from_snapshots',
                'result': None,
                'status': 'FAILED'
            })
        
        # STEP 5: Check what's in cache (query PRIMARY directly)
        with db.engine.connect() as primary_conn:
            cache_result = primary_conn.execute(text("""
                SELECT chart_data, generated_at
                FROM user_portfolio_chart_cache
                WHERE user_id = :user_id AND period = :period
            """), {'user_id': user.id, 'period': period.upper()})
            cache_row = cache_result.fetchone()
            
            if cache_row:
                cached_chart_data = json.loads(cache_row[0])
                cached_labels = cached_chart_data.get('labels', [])
                
                results['steps'].append({
                    'step': 5,
                    'name': 'Cache query (PRIMARY)',
                    'generated_at': cache_row[1].isoformat() if cache_row[1] else None,
                    'labels_count': len(cached_labels),
                    'first_label': cached_labels[0] if cached_labels else None,
                    'last_label': cached_labels[-1] if cached_labels else None,
                    'all_labels': cached_labels,
                    'has_oct_27': 'Oct 27' in cached_labels,
                    'status': 'OK' if 'Oct 27' in cached_labels else 'MISSING_OCT_27_IN_CACHE'
                })
            else:
                results['steps'].append({
                    'step': 5,
                    'name': 'Cache query (PRIMARY)',
                    'result': 'NOT_FOUND',
                    'status': 'NO_CACHE'
                })
        
        # STEP 6: Call the actual API endpoint
        from flask import url_for
        with app.test_client() as client:
            # Simulate logged-in user
            with client.session_transaction() as sess:
                sess['user_id'] = user.id
            
            api_response = client.get(f'/api/portfolio/performance/{period.upper()}')
            api_data = json.loads(api_response.data) if api_response.data else {}
            
            if api_data and 'chart_data' in api_data:
                api_chart_data = api_data['chart_data']
                api_dates = [point['date'] for point in api_chart_data]
                
                results['steps'].append({
                    'step': 6,
                    'name': 'API endpoint response',
                    'status_code': api_response.status_code,
                    'from_cache': api_data.get('from_cache'),
                    'portfolio_return': api_data.get('portfolio_return'),
                    'sp500_return': api_data.get('sp500_return'),
                    'chart_points': len(api_chart_data),
                    'first_date': api_dates[0] if api_dates else None,
                    'last_date': api_dates[-1] if api_dates else None,
                    'all_dates': api_dates,
                    'has_oct_27': 'Oct 27' in api_dates,
                    'status': 'OK' if 'Oct 27' in api_dates else 'MISSING_OCT_27_IN_API'
                })
            else:
                results['steps'].append({
                    'step': 6,
                    'name': 'API endpoint response',
                    'status_code': api_response.status_code,
                    'error': api_data.get('error'),
                    'status': 'FAILED'
                })
        
        # SUMMARY
        oct_27_status = {}
        for step in results['steps']:
            step_name = step['name']
            has_oct_27 = step.get('has_oct_27', False)
            oct_27_status[step_name] = has_oct_27
        
        results['oct_27_summary'] = oct_27_status
        results['diagnosis'] = _diagnose_issue(results['steps'])
        
        return jsonify({
            'success': True,
            'results': results
        })
        
    except Exception as e:
        import traceback
        return jsonify({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc(),
            'partial_results': results
        }), 500


def _diagnose_issue(steps):
    """Analyze steps to determine where data is getting lost"""
    
    diagnoses = []
    
    # Check each step
    for i, step in enumerate(steps):
        if step.get('status') == 'MISSING_OCT_27':
            diagnoses.append(f"FAILURE AT STEP {step['step']}: {step['name']} - Oct 27 data not present in source")
            break
        elif step.get('status') == 'MISSING_OCT_27_IN_OUTPUT':
            diagnoses.append(f"DATA LOSS AT STEP {step['step']}: {step['name']} - Input has Oct 27 but output doesn't")
            break
        elif step.get('status') == 'MISSING_OCT_27_IN_CACHE':
            diagnoses.append(f"CACHE STALE AT STEP {step['step']}: {step['name']} - Generated data has Oct 27 but cache doesn't")
            break
        elif step.get('status') == 'MISSING_OCT_27_IN_API':
            diagnoses.append(f"API ISSUE AT STEP {step['step']}: {step['name']} - Cache has Oct 27 but API doesn't return it")
            break
    
    if not diagnoses:
        diagnoses.append("ALL STEPS OK - Oct 27 data present throughout pipeline")
    
    return diagnoses
