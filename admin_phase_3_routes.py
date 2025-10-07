"""
Admin routes for Phase 3: Rebuild Historical Snapshots

These routes rebuild all existing snapshots with proper cash tracking fields:
- Recalculate stock_value, cash_proceeds, max_cash_deployed for each date
- Update snapshots in place (no deletion/recreation)
- Verify data integrity after rebuild

Each route includes comprehensive diagnostics and progress tracking.
"""

from flask import jsonify, request
from flask_login import login_required, current_user
from models import User, Stock, Transaction, PortfolioSnapshot
from datetime import datetime, date, timedelta
from sqlalchemy import text, func, and_
import logging

logger = logging.getLogger(__name__)

def register_phase_3_routes(app, db):
    """Register Phase 3 snapshot rebuild routes"""
    
    @app.route('/admin/phase3/preview-rebuild')
    @login_required
    def preview_snapshot_rebuild():
        """Preview which snapshots will be rebuilt"""
        if not current_user.is_admin:
            return jsonify({'error': 'Admin access required'}), 403
        
        username = request.args.get('user')
        
        try:
            from portfolio_performance import get_market_date
            
            # Build user list
            if username:
                user_result = db.session.execute(text(
                    "SELECT id, username FROM \"user\" WHERE username = :username"
                ), {'username': username})
                user_row = user_result.fetchone()
                if not user_row:
                    return jsonify({'error': f'User {username} not found'}), 404
                users = [{'id': user_row.id, 'username': user_row.username}]
            else:
                users_result = db.session.execute(text(
                    "SELECT id, username FROM \"user\" WHERE max_cash_deployed > 0 ORDER BY username"
                ))
                users = [{'id': row.id, 'username': row.username} for row in users_result]
            
            results = []
            
            for user in users:
                # Get all snapshots for this user
                snapshots = PortfolioSnapshot.query.filter_by(
                    user_id=user['id']
                ).order_by(PortfolioSnapshot.date).all()
                
                # Count snapshots needing rebuild (missing cash tracking)
                needs_rebuild = len([s for s in snapshots if s.stock_value is None or s.stock_value == 0])
                
                results.append({
                    'username': user['username'],
                    'total_snapshots': len(snapshots),
                    'needs_rebuild': needs_rebuild,
                    'date_range': {
                        'earliest': snapshots[0].date.isoformat() if snapshots else None,
                        'latest': snapshots[-1].date.isoformat() if snapshots else None
                    } if snapshots else None
                })
            
            return jsonify({
                'success': True,
                'users_analyzed': len(results),
                'results': results,
                'summary': {
                    'total_snapshots': sum(r['total_snapshots'] for r in results),
                    'needs_rebuild': sum(r['needs_rebuild'] for r in results)
                }
            })
            
        except Exception as e:
            import traceback
            return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500
    
    @app.route('/admin/phase3/rebuild-snapshots')
    @login_required
    def rebuild_snapshots():
        """Rebuild all historical snapshots with cash tracking"""
        if not current_user.is_admin:
            return jsonify({'error': 'Admin access required'}), 403
        
        execute = request.args.get('execute') == 'true'
        username = request.args.get('user')
        
        try:
            from cash_tracking import calculate_portfolio_value_with_cash
            from portfolio_performance import get_market_date
            
            # Build user list
            if username:
                user_result = db.session.execute(text(
                    "SELECT id, username, max_cash_deployed FROM \"user\" WHERE username = :username"
                ), {'username': username})
                user_row = user_result.fetchone()
                if not user_row:
                    return jsonify({'error': f'User {username} not found'}), 404
                users = [{'id': user_row.id, 'username': user_row.username, 'max_cash': user_row.max_cash_deployed}]
            else:
                users_result = db.session.execute(text(
                    "SELECT id, username, max_cash_deployed FROM \"user\" WHERE max_cash_deployed > 0 ORDER BY username"
                ))
                users = [{'id': row.id, 'username': row.username, 'max_cash': row.max_cash_deployed} for row in users_result]
            
            results = []
            total_rebuilt = 0
            errors = []
            
            for user in users:
                # Get all snapshots for this user
                snapshots = PortfolioSnapshot.query.filter_by(
                    user_id=user['id']
                ).order_by(PortfolioSnapshot.date).all()
                
                if not snapshots:
                    results.append({
                        'username': user['username'],
                        'status': 'skipped',
                        'reason': 'No snapshots found'
                    })
                    continue
                
                snapshots_rebuilt = 0
                snapshot_errors = []
                
                for snapshot in snapshots:
                    try:
                        # Calculate portfolio value with cash tracking for this date
                        portfolio_breakdown = calculate_portfolio_value_with_cash(
                            user['id'], 
                            snapshot.date
                        )
                        
                        if execute:
                            # Update snapshot with direct SQL to avoid session issues
                            db.session.execute(text("""
                                UPDATE portfolio_snapshot
                                SET stock_value = :stock_value,
                                    cash_proceeds = :cash_proceeds,
                                    max_cash_deployed = :max_cash_deployed,
                                    total_value = :total_value
                                WHERE id = :snapshot_id
                            """), {
                                'stock_value': portfolio_breakdown['stock_value'],
                                'cash_proceeds': portfolio_breakdown['cash_proceeds'],
                                'max_cash_deployed': user['max_cash'],
                                'total_value': portfolio_breakdown['total_value'],
                                'snapshot_id': snapshot.id
                            })
                            snapshots_rebuilt += 1
                        else:
                            # Preview mode - just count what would be updated
                            snapshots_rebuilt += 1
                            
                    except Exception as e:
                        error_msg = f"Date {snapshot.date}: {str(e)}"
                        snapshot_errors.append(error_msg)
                        logger.error(f"Error rebuilding snapshot for {user['username']} on {snapshot.date}: {e}")
                
                if execute:
                    db.session.commit()
                
                results.append({
                    'username': user['username'],
                    'total_snapshots': len(snapshots),
                    'snapshots_rebuilt': snapshots_rebuilt,
                    'errors': snapshot_errors,
                    'date_range': {
                        'earliest': snapshots[0].date.isoformat(),
                        'latest': snapshots[-1].date.isoformat()
                    }
                })
                
                total_rebuilt += snapshots_rebuilt
                errors.extend(snapshot_errors)
            
            return jsonify({
                'success': True,
                'executed': execute,
                'users_processed': len(results),
                'total_snapshots_rebuilt': total_rebuilt,
                'errors': errors,
                'details': results,
                'message': f'{"Rebuilt" if execute else "Would rebuild"} {total_rebuilt} snapshots with cash tracking',
                'execute_url': '/admin/phase3/rebuild-snapshots?execute=true' + (f'&user={username}' if username else '')
            })
            
        except Exception as e:
            db.session.rollback()
            import traceback
            return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500
    
    @app.route('/admin/phase3/verify-rebuild')
    @login_required
    def verify_snapshot_rebuild():
        """Verify that snapshots were rebuilt correctly"""
        if not current_user.is_admin:
            return jsonify({'error': 'Admin access required'}), 403
        
        username = request.args.get('user')
        
        try:
            # Build user list
            if username:
                user_result = db.session.execute(text(
                    "SELECT id, username FROM \"user\" WHERE username = :username"
                ), {'username': username})
                user_row = user_result.fetchone()
                if not user_row:
                    return jsonify({'error': f'User {username} not found'}), 404
                users = [{'id': user_row.id, 'username': user_row.username}]
            else:
                users_result = db.session.execute(text(
                    "SELECT id, username FROM \"user\" WHERE max_cash_deployed > 0 ORDER BY username"
                ))
                users = [{'id': row.id, 'username': row.username} for row in users_result]
            
            results = []
            
            for user in users:
                # Get all snapshots
                snapshots = PortfolioSnapshot.query.filter_by(
                    user_id=user['id']
                ).order_by(PortfolioSnapshot.date).all()
                
                # Check for issues
                missing_stock_value = len([s for s in snapshots if s.stock_value is None or s.stock_value == 0])
                missing_cash_proceeds = len([s for s in snapshots if s.cash_proceeds is None])
                missing_max_cash = len([s for s in snapshots if s.max_cash_deployed is None or s.max_cash_deployed == 0])
                
                # Check math (total_value should equal stock_value + cash_proceeds)
                math_errors = []
                for s in snapshots:
                    if s.stock_value is not None and s.cash_proceeds is not None:
                        calculated_total = s.stock_value + s.cash_proceeds
                        if abs(s.total_value - calculated_total) > 0.01:
                            math_errors.append({
                                'date': s.date.isoformat(),
                                'total_value': float(s.total_value),
                                'calculated': float(calculated_total),
                                'difference': float(s.total_value - calculated_total)
                            })
                
                all_good = (missing_stock_value == 0 and 
                           missing_cash_proceeds == 0 and 
                           missing_max_cash == 0 and 
                           len(math_errors) == 0)
                
                results.append({
                    'username': user['username'],
                    'total_snapshots': len(snapshots),
                    'issues': {
                        'missing_stock_value': missing_stock_value,
                        'missing_cash_proceeds': missing_cash_proceeds,
                        'missing_max_cash_deployed': missing_max_cash,
                        'math_errors': len(math_errors)
                    },
                    'math_error_details': math_errors[:5] if math_errors else [],  # Show first 5
                    'status': '✅ Perfect' if all_good else '⚠️ Has Issues'
                })
            
            all_users_good = all(r['status'] == '✅ Perfect' for r in results)
            
            return jsonify({
                'success': True,
                'all_users_verified': all_users_good,
                'users_checked': len(results),
                'results': results,
                'message': 'All snapshots verified!' if all_users_good else 'Some snapshots have issues'
            })
            
        except Exception as e:
            import traceback
            return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500
