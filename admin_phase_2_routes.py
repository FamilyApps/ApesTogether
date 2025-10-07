"""
Admin routes for Phase 2: Data Cleanup & Historical Rebuild

These routes help identify and fix data integrity issues:
- Find first real holdings date for each user
- Audit corrupted snapshots (before holdings, $0 values)
- Delete bad snapshots
- Prepare for historical data backfill

Each route includes comprehensive diagnostics and verification.
"""

from flask import jsonify, request
from flask_login import login_required, current_user
from models import User, Stock, Transaction, PortfolioSnapshot
from datetime import datetime, date, timedelta
from sqlalchemy import text, func, and_, or_
import logging

logger = logging.getLogger(__name__)

def register_phase_2_routes(app, db):
    """Register Phase 2 data cleanup routes"""
    
    @app.route('/admin/phase2/find-first-holdings')
    @login_required
    def find_first_holdings():
        """Find the first date each user had actual stock holdings"""
        if not current_user.is_admin:
            return jsonify({'error': 'Admin access required'}), 403
        
        try:
            from portfolio_performance import get_market_date
            
            # Get all users with stocks
            users_result = db.session.execute(text("""
                SELECT DISTINCT u.id, u.username
                FROM "user" u
                INNER JOIN stock s ON s.user_id = u.id
                ORDER BY u.username
            """))
            
            results = []
            
            for user_row in users_result:
                # Find earliest transaction
                earliest_txn = Transaction.query.filter_by(
                    user_id=user_row.id
                ).order_by(Transaction.timestamp).first()
                
                # Find earliest stock purchase_date
                earliest_stock = Stock.query.filter_by(
                    user_id=user_row.id
                ).order_by(Stock.purchase_date).first()
                
                # Count snapshots before first transaction
                if earliest_txn:
                    txn_date = earliest_txn.timestamp.date()
                    snapshots_before_txn = PortfolioSnapshot.query.filter(
                        and_(
                            PortfolioSnapshot.user_id == user_row.id,
                            PortfolioSnapshot.date < txn_date
                        )
                    ).count()
                else:
                    txn_date = None
                    snapshots_before_txn = 0
                
                # Count total snapshots
                total_snapshots = PortfolioSnapshot.query.filter_by(
                    user_id=user_row.id
                ).count()
                
                # Count snapshots with $0 values
                zero_snapshots = PortfolioSnapshot.query.filter(
                    and_(
                        PortfolioSnapshot.user_id == user_row.id,
                        or_(
                            PortfolioSnapshot.total_value == 0,
                            PortfolioSnapshot.total_value == None
                        )
                    )
                ).count()
                
                results.append({
                    'username': user_row.username,
                    'user_id': user_row.id,
                    'first_transaction_date': txn_date.isoformat() if txn_date else None,
                    'first_stock_date': earliest_stock.purchase_date.isoformat() if earliest_stock and earliest_stock.purchase_date else None,
                    'recommended_first_holdings_date': txn_date.isoformat() if txn_date else (earliest_stock.purchase_date.isoformat() if earliest_stock and earliest_stock.purchase_date else None),
                    'snapshots': {
                        'total': total_snapshots,
                        'before_first_transaction': snapshots_before_txn,
                        'with_zero_value': zero_snapshots,
                        'corrupted_estimate': snapshots_before_txn + zero_snapshots
                    }
                })
            
            return jsonify({
                'success': True,
                'users_analyzed': len(results),
                'results': results,
                'summary': {
                    'total_snapshots': sum(r['snapshots']['total'] for r in results),
                    'corrupted_estimate': sum(r['snapshots']['corrupted_estimate'] for r in results),
                    'users_with_issues': len([r for r in results if r['snapshots']['corrupted_estimate'] > 0])
                }
            })
            
        except Exception as e:
            import traceback
            return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500
    
    @app.route('/admin/phase2/audit-snapshots')
    @login_required
    def audit_snapshots():
        """Detailed audit of all snapshots to identify issues"""
        if not current_user.is_admin:
            return jsonify({'error': 'Admin access required'}), 403
        
        username = request.args.get('user')
        
        try:
            from portfolio_performance import get_market_date
            
            # Build query
            if username:
                user_result = db.session.execute(text(
                    "SELECT id, username FROM \"user\" WHERE username = :username"
                ), {'username': username})
                user_row = user_result.fetchone()
                if not user_row:
                    return jsonify({'error': f'User {username} not found'}), 404
                user_ids = [user_row.id]
            else:
                users_result = db.session.execute(text(
                    "SELECT id, username FROM \"user\" WHERE max_cash_deployed > 0 ORDER BY username"
                ))
                user_ids = [row.id for row in users_result]
            
            all_issues = []
            
            for user_id in user_ids:
                # Get user info
                user = User.query.get(user_id)
                
                # Get first transaction date
                first_txn = Transaction.query.filter_by(user_id=user_id).order_by(Transaction.timestamp).first()
                first_date = first_txn.timestamp.date() if first_txn else None
                
                # Get all snapshots
                snapshots = PortfolioSnapshot.query.filter_by(user_id=user_id).order_by(PortfolioSnapshot.date).all()
                
                issues = []
                
                for snapshot in snapshots:
                    snapshot_issues = []
                    
                    # Check if before first transaction
                    if first_date and snapshot.date < first_date:
                        snapshot_issues.append('before_first_transaction')
                    
                    # Check if zero value
                    if snapshot.total_value == 0 or snapshot.total_value is None:
                        snapshot_issues.append('zero_total_value')
                    
                    # Check if missing cash tracking fields
                    if snapshot.stock_value is None or snapshot.stock_value == 0:
                        snapshot_issues.append('missing_stock_value')
                    
                    # Check if weekend (Saturday = 5, Sunday = 6)
                    if snapshot.date.weekday() >= 5:
                        snapshot_issues.append('weekend_date')
                    
                    if snapshot_issues:
                        issues.append({
                            'date': snapshot.date.isoformat(),
                            'weekday': snapshot.date.strftime('%A'),
                            'total_value': float(snapshot.total_value) if snapshot.total_value else 0,
                            'stock_value': float(snapshot.stock_value) if snapshot.stock_value else 0,
                            'cash_proceeds': float(snapshot.cash_proceeds) if snapshot.cash_proceeds else 0,
                            'issues': snapshot_issues,
                            'severity': 'critical' if 'before_first_transaction' in snapshot_issues or 'zero_total_value' in snapshot_issues else 'warning'
                        })
                
                if issues:
                    all_issues.append({
                        'username': user.username,
                        'user_id': user_id,
                        'first_transaction_date': first_date.isoformat() if first_date else None,
                        'total_snapshots': len(snapshots),
                        'problematic_snapshots': len(issues),
                        'issues': issues
                    })
            
            return jsonify({
                'success': True,
                'users_audited': len(all_issues),
                'users_with_issues': all_issues,
                'summary': {
                    'total_snapshots_audited': sum(u['total_snapshots'] for u in all_issues),
                    'total_problematic': sum(u['problematic_snapshots'] for u in all_issues),
                    'by_severity': {
                        'critical': sum(len([i for i in u['issues'] if i['severity'] == 'critical']) for u in all_issues),
                        'warning': sum(len([i for i in u['issues'] if i['severity'] == 'warning']) for u in all_issues)
                    }
                }
            })
            
        except Exception as e:
            import traceback
            return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500
    
    @app.route('/admin/phase2/delete-corrupted-snapshots')
    @login_required
    def delete_corrupted_snapshots():
        """Delete snapshots that are corrupted (before holdings or zero value)"""
        if not current_user.is_admin:
            return jsonify({'error': 'Admin access required'}), 403
        
        execute = request.args.get('execute') == 'true'
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
            total_deleted = 0
            
            for user in users:
                # Get first transaction date
                first_txn = Transaction.query.filter_by(user_id=user['id']).order_by(Transaction.timestamp).first()
                
                if not first_txn:
                    results.append({
                        'username': user['username'],
                        'status': 'skipped',
                        'reason': 'No transactions found'
                    })
                    continue
                
                first_date = first_txn.timestamp.date()
                
                # Find snapshots to delete (before first transaction OR zero value)
                snapshots_to_delete = PortfolioSnapshot.query.filter(
                    and_(
                        PortfolioSnapshot.user_id == user['id'],
                        or_(
                            PortfolioSnapshot.date < first_date,
                            PortfolioSnapshot.total_value == 0,
                            PortfolioSnapshot.total_value == None
                        )
                    )
                ).all()
                
                if execute:
                    for snapshot in snapshots_to_delete:
                        db.session.delete(snapshot)
                    db.session.commit()
                    action = 'deleted'
                else:
                    action = 'would_delete'
                
                results.append({
                    'username': user['username'],
                    'first_transaction_date': first_date.isoformat(),
                    'snapshots_identified': len(snapshots_to_delete),
                    'action': action,
                    'date_range': {
                        'earliest': snapshots_to_delete[0].date.isoformat() if snapshots_to_delete else None,
                        'latest': snapshots_to_delete[-1].date.isoformat() if snapshots_to_delete else None
                    } if snapshots_to_delete else None
                })
                
                total_deleted += len(snapshots_to_delete)
            
            return jsonify({
                'success': True,
                'executed': execute,
                'users_processed': len(results),
                'total_snapshots_affected': total_deleted,
                'details': results,
                'message': f'{"Deleted" if execute else "Would delete"} {total_deleted} corrupted snapshots',
                'execute_url': '/admin/phase2/delete-corrupted-snapshots?execute=true' + (f'&user={username}' if username else '')
            })
            
        except Exception as e:
            db.session.rollback()
            import traceback
            return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500
