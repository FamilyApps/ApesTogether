"""
Quick admin route to force chart cache refresh
Bypasses the market close cron complexity
"""

from flask import Blueprint, jsonify
from models import db, UserPortfolioChartCache, User
from performance_calculator import calculate_portfolio_performance, get_period_dates
import json
from datetime import datetime

force_refresh_bp = Blueprint('force_refresh', __name__)


@force_refresh_bp.route('/admin/force-chart-refresh', methods=['POST'])
def force_chart_refresh():
    """
    Nuclear option: Delete ALL chart caches and regenerate from scratch
    This ensures we start fresh without any stale data
    """
    try:
        # Get all users
        users = User.query.all()
        periods = ['1D', '5D', '1M', '3M', 'YTD', '1Y', '5Y', 'MAX']
        
        results = {
            'deleted': 0,
            'created': 0,
            'errors': []
        }
        
        # STEP 1: Nuclear delete - remove ALL existing caches
        deleted_count = UserPortfolioChartCache.query.delete()
        db.session.commit()  # Commit the deletes immediately
        results['deleted'] = deleted_count
        
        # STEP 2: Generate fresh caches for all users
        for user in users:
            for period in periods:
                try:
                    # Get date range
                    start_date, end_date = get_period_dates(period, user_id=user.id)
                    
                    # Calculate performance with chart data
                    result = calculate_portfolio_performance(
                        user.id,
                        start_date,
                        end_date,
                        include_chart_data=True
                    )
                    
                    if not result or not result.get('chart_data'):
                        continue
                    
                    # Transform to Chart.js format
                    raw_chart_data = result['chart_data']
                    labels = [point['date'] for point in raw_chart_data]
                    portfolio_data = [point['portfolio'] for point in raw_chart_data]
                    sp500_data = [point['sp500'] for point in raw_chart_data]
                    
                    chart_data = {
                        'labels': labels,
                        'datasets': [
                            {
                                'label': 'Your Portfolio',
                                'data': portfolio_data,
                                'borderColor': 'rgb(40, 167, 69)',
                                'backgroundColor': 'rgba(40, 167, 69, 0.1)',
                                'tension': 0.1,
                                'fill': False
                            },
                            {
                                'label': 'S&P 500',
                                'data': sp500_data,
                                'borderColor': 'rgb(108, 117, 125)',
                                'backgroundColor': 'rgba(108, 117, 125, 0.1)',
                                'tension': 0.1,
                                'fill': False,
                                'borderDash': [5, 5]
                            }
                        ],
                        'portfolio_return': result.get('portfolio_return'),
                        'sp500_return': result.get('sp500_return')
                    }
                    
                    # Create brand new cache entry
                    new_cache = UserPortfolioChartCache(
                        user_id=user.id,
                        period=period,
                        chart_data=json.dumps(chart_data),
                        generated_at=datetime.now()
                    )
                    db.session.add(new_cache)
                    results['created'] += 1
                    
                except Exception as e:
                    results['errors'].append(f"User {user.id}, period {period}: {str(e)}")
        
        # STEP 3: Commit all new caches
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Deleted {results["deleted"]} old caches, created {results["created"]} new caches',
            'results': results
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
