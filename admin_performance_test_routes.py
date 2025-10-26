"""
Admin routes for testing the new unified performance calculator.

These GET endpoints allow easy browser-based testing and verification.
"""

from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
from datetime import datetime
import json
import traceback

# Create blueprint
admin_perf_bp = Blueprint('admin_performance', __name__)

# Admin email (should match your config)
ADMIN_EMAIL = "catalystcatalyst101@gmail.com"


def require_admin():
    """Check if current user is admin"""
    from flask import session
    email = session.get('email', '')
    if email != ADMIN_EMAIL:
        return jsonify({'error': 'Admin access required'}), 403
    return None


@admin_perf_bp.route('/admin/test-unified-calculator')
@login_required
def test_unified_calculator():
    """
    Test the new unified performance calculator with real user data.
    
    Usage: /admin/test-unified-calculator?username=witty-raven&period=YTD
    
    Compares:
    - New unified calculator result
    - Current cached data (if exists)
    - Shows formula details for verification
    """
    admin_check = require_admin()
    if admin_check:
        return admin_check
    
    try:
        from models import User
        from performance_calculator import calculate_portfolio_performance, get_period_dates
        from models import UserPortfolioChartCache
        
        # Get parameters
        username = request.args.get('username', 'witty-raven')
        period = request.args.get('period', 'YTD').upper()
        
        # Find user
        user = User.query.filter_by(username=username).first()
        if not user:
            return jsonify({'error': f'User {username} not found'}), 404
        
        # Calculate with new unified calculator
        start_date, end_date = get_period_dates(period, user_id=user.id)
        result = calculate_portfolio_performance(
            user.id, start_date, end_date, include_chart_data=True
        )
        
        # Get current cached data for comparison
        chart_cache = UserPortfolioChartCache.query.filter_by(
            user_id=user.id, period=period
        ).first()
        
        cached_data = None
        if chart_cache:
            try:
                cached_chart = json.loads(chart_cache.chart_data)
                # Try to extract return from old format
                if isinstance(cached_chart, dict):
                    if 'datasets' in cached_chart:
                        # Old Chart.js format
                        datasets = cached_chart.get('datasets', [])
                        portfolio_data = datasets[0].get('data', []) if datasets else []
                        cached_data = {
                            'format': 'old_chartjs',
                            'last_value': portfolio_data[-1] if portfolio_data else None,
                            'generated_at': chart_cache.generated_at.isoformat()
                        }
                    elif 'portfolio_return' in cached_chart:
                        # New unified format
                        cached_data = {
                            'format': 'new_unified',
                            'portfolio_return': cached_chart.get('portfolio_return'),
                            'sp500_return': cached_chart.get('sp500_return'),
                            'generated_at': chart_cache.generated_at.isoformat()
                        }
            except Exception as e:
                cached_data = {'error': str(e)}
        
        return jsonify({
            'success': True,
            'test_info': {
                'username': username,
                'user_id': user.id,
                'period': period,
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat()
            },
            'new_calculator_result': {
                'portfolio_return': result['portfolio_return'],
                'sp500_return': result['sp500_return'],
                'metadata': result['metadata'],
                'chart_points': len(result['chart_data']) if result['chart_data'] else 0,
                'sample_chart_data': result['chart_data'][:3] if result['chart_data'] else []
            },
            'current_cached_data': cached_data,
            'comparison': {
                'cache_exists': chart_cache is not None,
                'match': (
                    cached_data.get('portfolio_return') == result['portfolio_return']
                    if cached_data and 'portfolio_return' in cached_data else None
                )
            },
            'expected_behavior': {
                'message': 'New calculator should show ~28.57% for witty-raven YTD',
                'formula': 'Modified Dietz: (V_end - V_start - CF_net) / (V_start + W * CF_net)',
                'note': 'Old cache may show 25.87% (wrong) until regenerated'
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }), 500


@admin_perf_bp.route('/admin/compare-all-users-ytd')
@login_required
def compare_all_users_ytd():
    """
    Compare YTD performance for all users using new calculator.
    
    Usage: /admin/compare-all-users-ytd
    
    Shows:
    - Each user's YTD return (new calculator)
    - Current cached value
    - Highlights discrepancies
    """
    admin_check = require_admin()
    if admin_check:
        return admin_check
    
    try:
        from models import User
        from performance_calculator import calculate_portfolio_performance, get_period_dates
        from models import UserPortfolioChartCache
        
        period = 'YTD'
        start_date, end_date = get_period_dates(period)
        
        results = []
        users = User.query.all()
        
        for user in users:
            try:
                # Calculate with new calculator
                result = calculate_portfolio_performance(
                    user.id, start_date, end_date, include_chart_data=False
                )
                
                # Get cached value
                chart_cache = UserPortfolioChartCache.query.filter_by(
                    user_id=user.id, period=period
                ).first()
                
                cached_return = None
                if chart_cache:
                    try:
                        cached_chart = json.loads(chart_cache.chart_data)
                        if isinstance(cached_chart, dict) and 'datasets' in cached_chart:
                            datasets = cached_chart.get('datasets', [])
                            portfolio_data = datasets[0].get('data', []) if datasets else []
                            cached_return = portfolio_data[-1] if portfolio_data else None
                        elif isinstance(cached_chart, dict) and 'portfolio_return' in cached_chart:
                            cached_return = cached_chart.get('portfolio_return')
                    except:
                        pass
                
                discrepancy = None
                if cached_return is not None:
                    discrepancy = abs(result['portfolio_return'] - cached_return)
                
                results.append({
                    'username': user.username,
                    'user_id': user.id,
                    'new_calculator': result['portfolio_return'],
                    'cached_value': cached_return,
                    'discrepancy': round(discrepancy, 2) if discrepancy else None,
                    'needs_update': discrepancy > 0.1 if discrepancy else False,
                    'snapshots': result['metadata']['snapshots_count'],
                    'capital_deployed': result['metadata']['net_capital_deployed']
                })
            except Exception as e:
                results.append({
                    'username': user.username,
                    'user_id': user.id,
                    'error': str(e)
                })
        
        # Summary
        needs_update = sum(1 for r in results if r.get('needs_update'))
        has_discrepancy = sum(1 for r in results if r.get('discrepancy'))
        
        return jsonify({
            'success': True,
            'period': period,
            'date_range': f"{start_date.isoformat()} to {end_date.isoformat()}",
            'total_users': len(users),
            'summary': {
                'users_with_discrepancy': has_discrepancy,
                'users_needing_cache_update': needs_update,
                'message': (
                    f'{needs_update}/{len(users)} users need cache regeneration'
                    if needs_update > 0 else 'All caches match new calculator!'
                )
            },
            'results': results,
            'next_step': (
                'Visit /admin/update-single-user-cache?username=USERNAME to update one user, '
                'or /admin/regenerate-all-performance-caches to update all'
            )
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }), 500


@admin_perf_bp.route('/admin/update-single-user-cache')
@login_required
def update_single_user_cache():
    """
    Update performance cache for a single user using new calculator.
    
    Usage: /admin/update-single-user-cache?username=witty-raven&period=YTD
    
    Updates the UserPortfolioChartCache with new calculator results.
    """
    admin_check = require_admin()
    if admin_check:
        return admin_check
    
    try:
        from models import User, db
        from performance_calculator import calculate_portfolio_performance, get_period_dates
        from models import UserPortfolioChartCache
        
        # Get parameters
        username = request.args.get('username')
        period = request.args.get('period', 'YTD').upper()
        
        if not username:
            return jsonify({'error': 'username parameter required'}), 400
        
        # Find user
        user = User.query.filter_by(username=username).first()
        if not user:
            return jsonify({'error': f'User {username} not found'}), 404
        
        # Calculate with new calculator
        start_date, end_date = get_period_dates(period, user_id=user.id)
        result = calculate_portfolio_performance(
            user.id, start_date, end_date, include_chart_data=True
        )
        
        # Update cache
        chart_cache = UserPortfolioChartCache.query.filter_by(
            user_id=user.id, period=period
        ).first()
        
        if chart_cache:
            old_data = chart_cache.chart_data
            chart_cache.chart_data = json.dumps(result)
            chart_cache.generated_at = datetime.now()
            action = 'updated'
        else:
            chart_cache = UserPortfolioChartCache(
                user_id=user.id,
                period=period,
                chart_data=json.dumps(result),
                generated_at=datetime.now()
            )
            db.session.add(chart_cache)
            old_data = None
            action = 'created'
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'action': action,
            'user': username,
            'period': period,
            'new_return': result['portfolio_return'],
            'sp500_return': result['sp500_return'],
            'updated_at': datetime.now().isoformat(),
            'message': f'Cache {action} successfully with new calculator'
        })
        
    except Exception as e:
        from models import db
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }), 500


@admin_perf_bp.route('/admin/regenerate-all-performance-caches')
@login_required
def regenerate_all_performance_caches():
    """
    Regenerate ALL performance caches for ALL users and ALL periods using new calculator.
    
    Usage: /admin/regenerate-all-performance-caches
    
    WARNING: This updates all 40 UserPortfolioChartCache entries.
    Takes 1-2 minutes to complete.
    """
    admin_check = require_admin()
    if admin_check:
        return admin_check
    
    try:
        from models import User, db
        from performance_calculator import calculate_portfolio_performance, get_period_dates
        from models import UserPortfolioChartCache
        
        periods = ['1D', '5D', '1M', '3M', 'YTD', '1Y', '5Y', 'MAX']
        users = User.query.all()
        
        results = {
            'updated': 0,
            'created': 0,
            'errors': 0,
            'details': []
        }
        
        for user in users:
            for period in periods:
                try:
                    # Calculate with new calculator
                    start_date, end_date = get_period_dates(period, user_id=user.id)
                    result = calculate_portfolio_performance(
                        user.id, start_date, end_date, include_chart_data=True
                    )
                    
                    # Update cache
                    chart_cache = UserPortfolioChartCache.query.filter_by(
                        user_id=user.id, period=period
                    ).first()
                    
                    if chart_cache:
                        chart_cache.chart_data = json.dumps(result)
                        chart_cache.generated_at = datetime.now()
                        results['updated'] += 1
                        action = 'updated'
                    else:
                        chart_cache = UserPortfolioChartCache(
                            user_id=user.id,
                            period=period,
                            chart_data=json.dumps(result),
                            generated_at=datetime.now()
                        )
                        db.session.add(chart_cache)
                        results['created'] += 1
                        action = 'created'
                    
                    results['details'].append({
                        'user': user.username,
                        'period': period,
                        'action': action,
                        'return': result['portfolio_return']
                    })
                    
                except Exception as e:
                    results['errors'] += 1
                    results['details'].append({
                        'user': user.username,
                        'period': period,
                        'error': str(e)
                    })
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'summary': {
                'total_users': len(users),
                'total_periods': len(periods),
                'total_caches': len(users) * len(periods),
                'updated': results['updated'],
                'created': results['created'],
                'errors': results['errors']
            },
            'results': results['details'],
            'message': (
                f"Regenerated {results['updated'] + results['created']} caches "
                f"({results['updated']} updated, {results['created']} created, "
                f"{results['errors']} errors)"
            ),
            'next_steps': [
                'Check /admin/compare-all-users-ytd to verify consistency',
                'Visit dashboard and leaderboard to verify values match',
                'Expected: witty-raven YTD ~28.57% everywhere'
            ]
        })
        
    except Exception as e:
        from models import db
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }), 500


@admin_perf_bp.route('/admin/verify-calculator-consistency')
@login_required
def verify_calculator_consistency():
    """
    Verify that dashboard, leaderboard, and new calculator all show consistent values.
    
    Usage: /admin/verify-calculator-consistency?username=witty-raven
    
    Checks:
    - New calculator result
    - Dashboard cache
    - Leaderboard cache
    - Highlights any discrepancies
    """
    admin_check = require_admin()
    if admin_check:
        return admin_check
    
    try:
        from models import User
        from performance_calculator import calculate_portfolio_performance, get_period_dates
        from models import UserPortfolioChartCache, LeaderboardCache
        
        # Get parameters
        username = request.args.get('username', 'witty-raven')
        period = request.args.get('period', 'YTD').upper()
        
        # Find user
        user = User.query.filter_by(username=username).first()
        if not user:
            return jsonify({'error': f'User {username} not found'}), 404
        
        # 1. New calculator result
        start_date, end_date = get_period_dates(period, user_id=user.id)
        new_calc_result = calculate_portfolio_performance(
            user.id, start_date, end_date, include_chart_data=False
        )
        
        # 2. Dashboard cache
        dashboard_cache = UserPortfolioChartCache.query.filter_by(
            user_id=user.id, period=period
        ).first()
        
        dashboard_value = None
        if dashboard_cache:
            try:
                cached_data = json.loads(dashboard_cache.chart_data)
                if 'portfolio_return' in cached_data:
                    dashboard_value = cached_data['portfolio_return']
            except:
                pass
        
        # 3. Leaderboard cache
        leaderboard_value = None
        leaderboard_cache = LeaderboardCache.query.filter_by(
            period=f"{period}_all_auth"
        ).first()
        
        if leaderboard_cache:
            try:
                leaderboard_data = json.loads(leaderboard_cache.leaderboard_data)
                user_entry = next((e for e in leaderboard_data if e.get('username') == username), None)
                if user_entry:
                    # Try different possible field names
                    leaderboard_value = (
                        user_entry.get('portfolio_return') or
                        user_entry.get('performance_percent') or
                        user_entry.get('return')
                    )
            except:
                pass
        
        # Compare
        all_values = [
            new_calc_result['portfolio_return'],
            dashboard_value,
            leaderboard_value
        ]
        non_none_values = [v for v in all_values if v is not None]
        
        consistent = (
            len(set(non_none_values)) == 1
            if non_none_values else False
        )
        
        return jsonify({
            'success': True,
            'username': username,
            'period': period,
            'values': {
                'new_calculator': new_calc_result['portfolio_return'],
                'dashboard_cache': dashboard_value,
                'leaderboard_cache': leaderboard_value
            },
            'consistency_check': {
                'consistent': consistent,
                'message': (
                    '✅ All values match!' if consistent
                    else '❌ Discrepancies found - caches need regeneration'
                ),
                'max_discrepancy': (
                    round(max(non_none_values) - min(non_none_values), 2)
                    if len(non_none_values) > 1 else 0
                )
            },
            'cache_status': {
                'dashboard_cache_exists': dashboard_cache is not None,
                'leaderboard_cache_exists': leaderboard_cache is not None
            },
            'expected': {
                'witty_raven_ytd': '~28.57%',
                'formula': 'Modified Dietz with max_cash_deployed',
                'baseline': 'Jan 1 for YTD (not first snapshot)'
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }), 500
