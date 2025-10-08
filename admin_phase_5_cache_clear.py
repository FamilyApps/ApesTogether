"""
Phase 5: Clear Chart Caches and Verify Chart Generation

After fixing historical snapshots, we need to:
1. Clear all old chart caches (they have flat-line data)
2. Verify chart generation uses new historical snapshots
3. Test all chart periods work correctly
"""

from flask import jsonify, request
from flask_login import login_required, current_user
from sqlalchemy import text

def register_phase_5_cache_routes(app, db):
    """Register Phase 5 cache clearing routes"""
    
    @app.route('/admin/phase5/clear-chart-caches')
    @login_required
    def clear_chart_caches():
        """Clear all chart caches so they regenerate with new historical data"""
        if not current_user.is_admin:
            return jsonify({'error': 'Admin access required'}), 403
        
        execute = request.args.get('execute') == 'true'
        
        try:
            from models import UserPortfolioChartCache, LeaderboardCache
            
            # Count existing caches
            chart_cache_count = UserPortfolioChartCache.query.count()
            leaderboard_cache_count = LeaderboardCache.query.count()
            
            if not execute:
                return jsonify({
                    'success': True,
                    'preview': True,
                    'chart_caches_to_delete': chart_cache_count,
                    'leaderboard_caches_to_delete': leaderboard_cache_count,
                    'total_to_delete': chart_cache_count + leaderboard_cache_count,
                    'execute_url': '/admin/phase5/clear-chart-caches?execute=true',
                    'note': 'These caches contain old flat-line data and need to be regenerated'
                })
            
            # Execute deletion
            UserPortfolioChartCache.query.delete()
            LeaderboardCache.query.delete()
            db.session.commit()
            
            return jsonify({
                'success': True,
                'executed': True,
                'chart_caches_deleted': chart_cache_count,
                'leaderboard_caches_deleted': leaderboard_cache_count,
                'total_deleted': chart_cache_count + leaderboard_cache_count,
                'message': 'All chart caches cleared successfully. Charts will regenerate on next view with new historical data.',
                'next_step': 'Visit user dashboard to regenerate charts with correct data'
            })
            
        except Exception as e:
            db.session.rollback()
            import traceback
            return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500
    
    @app.route('/admin/phase5/verify-chart-data')
    @login_required
    def verify_chart_data():
        """Verify chart data for a specific user and period"""
        if not current_user.is_admin:
            return jsonify({'error': 'Admin access required'}), 403
        
        try:
            from models import PortfolioSnapshot
            from datetime import datetime, timedelta
            
            username = request.args.get('user', 'testing2')
            period = request.args.get('period', '1M')
            
            # Get user
            user_result = db.session.execute(text(
                "SELECT id, username FROM \"user\" WHERE username = :username"
            ), {'username': username}).fetchone()
            
            if not user_result:
                return jsonify({'error': f'User {username} not found'}), 404
            
            # Calculate date range
            end_date = datetime.now().date()
            
            period_days = {
                '1D': 1,
                '5D': 5,
                '1M': 30,
                '3M': 90,
                'YTD': (end_date - datetime(end_date.year, 1, 1).date()).days,
                '1Y': 365,
                'MAX': 365 * 10
            }
            
            days_back = period_days.get(period, 30)
            start_date = end_date - timedelta(days=days_back)
            
            # Get snapshots
            snapshots = PortfolioSnapshot.query.filter(
                PortfolioSnapshot.user_id == user_result.id,
                PortfolioSnapshot.date >= start_date,
                PortfolioSnapshot.date <= end_date
            ).order_by(PortfolioSnapshot.date.asc()).all()
            
            if not snapshots:
                return jsonify({
                    'success': True,
                    'user': username,
                    'period': period,
                    'snapshots_found': 0,
                    'message': 'No snapshots found for this period'
                })
            
            # Analyze data
            snapshot_data = []
            values = []
            
            for s in snapshots:
                snapshot_data.append({
                    'date': s.date.isoformat(),
                    'total_value': float(s.total_value),
                    'stock_value': float(s.stock_value) if s.stock_value else 0,
                    'cash_proceeds': float(s.cash_proceeds) if s.cash_proceeds else 0
                })
                values.append(float(s.total_value))
            
            # Calculate statistics
            unique_values = len(set(values))
            min_val = min(values)
            max_val = max(values)
            avg_val = sum(values) / len(values)
            
            # Check for flat-line data (old bug)
            is_flat = unique_values == 1
            
            return jsonify({
                'success': True,
                'user': username,
                'period': period,
                'date_range': {
                    'start': start_date.isoformat(),
                    'end': end_date.isoformat()
                },
                'snapshots_found': len(snapshots),
                'sample_snapshots': snapshot_data[:10],  # First 10 for preview
                'statistics': {
                    'unique_values': unique_values,
                    'min': round(min_val, 2),
                    'max': round(max_val, 2),
                    'avg': round(avg_val, 2),
                    'variation': round(max_val - min_val, 2),
                    'variation_pct': round(((max_val - min_val) / min_val * 100) if min_val > 0 else 0, 2)
                },
                'data_quality': {
                    'is_flat_line': is_flat,
                    'status': '🚨 FLAT LINE (old bug data)' if is_flat else '✅ Realistic variation',
                    'chart_ready': not is_flat
                }
            })
            
        except Exception as e:
            import traceback
            return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500
    
    @app.route('/admin/phase5/check-recent-snapshots')
    @login_required
    def check_recent_snapshots():
        """Check if recent snapshots exist for all users"""
        if not current_user.is_admin:
            return jsonify({'error': 'Admin access required'}), 403
        
        try:
            from models import PortfolioSnapshot
            from datetime import datetime, timedelta
            
            # Check last 5 days
            today = datetime.now().date()
            check_dates = [today - timedelta(days=i) for i in range(5)]
            
            # Get all users
            users_result = db.session.execute(text("""
                SELECT id, username FROM "user" WHERE max_cash_deployed > 0 ORDER BY username
            """)).fetchall()
            
            results = {}
            
            for user_row in users_result:
                user_snapshots = {}
                for check_date in check_dates:
                    snapshot = PortfolioSnapshot.query.filter_by(
                        user_id=user_row.id,
                        date=check_date
                    ).first()
                    
                    user_snapshots[check_date.isoformat()] = {
                        'exists': snapshot is not None,
                        'weekday': check_date.strftime('%A'),
                        'value': float(snapshot.total_value) if snapshot else None
                    }
                
                results[user_row.username] = user_snapshots
            
            return jsonify({
                'success': True,
                'check_dates': [d.isoformat() for d in check_dates],
                'snapshots': results
            })
            
        except Exception as e:
            import traceback
            return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500
