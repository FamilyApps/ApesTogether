"""
Admin routes for Phase 4: Backfill Missing Historical Snapshots

These routes identify and fill gaps in historical snapshot data:
- Detect missing date ranges (between first transaction and earliest snapshot)
- Backfill missing snapshots per user (to avoid timeouts)
- Verify complete historical coverage

Each route includes progress tracking and batch processing.
"""

from flask import jsonify, request, render_template_string
from flask_login import login_required, current_user
from models import User, Stock, Transaction, PortfolioSnapshot
from datetime import datetime, date, timedelta
from sqlalchemy import text, func, and_
import logging

logger = logging.getLogger(__name__)

def register_phase_4_routes(app, db):
    """Register Phase 4 historical backfill routes"""
    
    @app.route('/admin/phase4/dashboard')
    @login_required
    def phase4_dashboard():
        """Dashboard showing historical data gaps and backfill progress"""
        if not current_user.is_admin:
            return jsonify({'error': 'Admin access required'}), 403
        
        try:
            from portfolio_performance import get_market_date
            
            # Get all users with transactions
            users_result = db.session.execute(text("""
                SELECT u.id, u.username, u.max_cash_deployed
                FROM "user" u
                WHERE u.max_cash_deployed > 0
                ORDER BY u.username
            """))
            
            users_data = []
            
            for user_row in users_result:
                # Get first transaction date
                first_txn = Transaction.query.filter_by(user_id=user_row.id).order_by(Transaction.timestamp).first()
                first_date = first_txn.timestamp.date() if first_txn else None
                
                # Get snapshot date range
                snapshots_result = db.session.execute(text("""
                    SELECT MIN(date) as earliest, MAX(date) as latest, COUNT(*) as count
                    FROM portfolio_snapshot
                    WHERE user_id = :user_id
                """), {'user_id': user_row.id})
                snapshot_row = snapshots_result.fetchone()
                
                earliest_snapshot = snapshot_row.earliest if snapshot_row else None
                latest_snapshot = snapshot_row.latest if snapshot_row else None
                snapshot_count = snapshot_row.count if snapshot_row else 0
                
                # Calculate gap
                if first_date and earliest_snapshot:
                    gap_days = (earliest_snapshot - first_date).days
                    has_gap = gap_days > 1  # More than 1 day gap
                else:
                    gap_days = 0
                    has_gap = False
                
                # Calculate expected vs actual snapshots (weekdays only)
                if first_date and latest_snapshot:
                    total_days = (latest_snapshot - first_date).days + 1
                    # Rough estimate: 5/7 days are weekdays
                    expected_snapshots = int(total_days * 5 / 7)
                    coverage_pct = (snapshot_count / expected_snapshots * 100) if expected_snapshots > 0 else 0
                else:
                    expected_snapshots = 0
                    coverage_pct = 0
                
                users_data.append({
                    'id': user_row.id,
                    'username': user_row.username,
                    'first_transaction': first_date.isoformat() if first_date else None,
                    'earliest_snapshot': earliest_snapshot.isoformat() if earliest_snapshot else None,
                    'latest_snapshot': latest_snapshot.isoformat() if latest_snapshot else None,
                    'snapshot_count': snapshot_count,
                    'gap_days': gap_days,
                    'has_gap': has_gap,
                    'expected_snapshots': expected_snapshots,
                    'coverage_percent': round(coverage_pct, 1),
                    'status': '✅ Complete' if not has_gap and coverage_pct > 90 else ('⚠️ Has Gap' if has_gap else '📊 Partial')
                })
            
            # HTML Dashboard
            html = f'''
            <!DOCTYPE html>
            <html>
            <head>
                <title>Phase 4: Historical Data Backfill</title>
                <style>
                    body {{ font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }}
                    .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; }}
                    h1 {{ color: #333; }}
                    table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
                    th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }}
                    th {{ background: #4CAF50; color: white; }}
                    tr:hover {{ background: #f5f5f5; }}
                    .gap {{ color: #f44336; font-weight: bold; }}
                    .complete {{ color: #4CAF50; font-weight: bold; }}
                    .partial {{ color: #ff9800; font-weight: bold; }}
                    .button {{ 
                        background: #2196F3; color: white; padding: 8px 16px; 
                        text-decoration: none; border-radius: 4px; display: inline-block;
                        margin: 4px;
                    }}
                    .button:hover {{ background: #0b7dda; }}
                    .danger {{ background: #f44336; }}
                    .danger:hover {{ background: #da190b; }}
                    .success {{ background: #4CAF50; }}
                    .summary {{ background: #e3f2fd; padding: 15px; border-radius: 4px; margin: 20px 0; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>📊 Phase 4: Historical Data Backfill Dashboard</h1>
                    
                    <div class="summary">
                        <h3>Summary</h3>
                        <p><strong>Users with gaps:</strong> {len([u for u in users_data if u['has_gap']])}</p>
                        <p><strong>Total missing days:</strong> {sum(u['gap_days'] for u in users_data)}</p>
                        <p><strong>Average coverage:</strong> {round(sum(u['coverage_percent'] for u in users_data) / len(users_data), 1) if users_data else 0}%</p>
                    </div>
                    
                    <h2>Users & Data Gaps</h2>
                    <table>
                        <tr>
                            <th>User</th>
                            <th>First Transaction</th>
                            <th>Earliest Snapshot</th>
                            <th>Gap (Days)</th>
                            <th>Snapshots</th>
                            <th>Coverage</th>
                            <th>Status</th>
                            <th>Actions</th>
                        </tr>
                        {''.join(f'''<tr>
                            <td><strong>{u['username']}</strong></td>
                            <td>{u['first_transaction'] or 'N/A'}</td>
                            <td>{u['earliest_snapshot'] or 'N/A'}</td>
                            <td class="{'gap' if u['has_gap'] else ''}">{u['gap_days']} days</td>
                            <td>{u['snapshot_count']} / {u['expected_snapshots']}</td>
                            <td>{u['coverage_percent']}%</td>
                            <td class="{'complete' if u['status'].startswith('✅') else ('gap' if u['status'].startswith('⚠️') else 'partial')}">{u['status']}</td>
                            <td>
                                <a href="/admin/phase4/backfill-user?user={u['username']}" class="button">📥 Preview</a>
                                <a href="/admin/phase4/backfill-user?user={u['username']}&execute=true" class="button success" onclick="return confirm('Backfill {u['gap_days']} days for {u['username']}?')">▶️ Execute</a>
                            </td>
                        </tr>''' for u in users_data)}
                    </table>
                    
                    <h2>Batch Actions</h2>
                    <p>
                        <a href="/admin/phase4/backfill-all-users" class="button">📋 Preview All Users</a>
                        <a href="/admin/phase3/rebuild-snapshots?execute=true" class="button success">🔧 Rebuild Existing (172 snapshots)</a>
                    </p>
                    
                    <h2>Next Steps</h2>
                    <ol>
                        <li>Click <strong>Preview</strong> for each user to see what will be created</li>
                        <li>Click <strong>Execute</strong> to backfill missing snapshots (one user at a time)</li>
                        <li>After all users backfilled, run <strong>Rebuild Existing</strong> to update cash tracking</li>
                        <li>Verify with <a href="/admin/phase3/verify-rebuild" class="button">✅ Verify All</a></li>
                    </ol>
                </div>
            </body>
            </html>
            '''
            
            return html
            
        except Exception as e:
            import traceback
            return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500
    
    @app.route('/admin/phase4/backfill-user')
    @login_required
    def backfill_user():
        """Backfill missing historical snapshots for a single user"""
        if not current_user.is_admin:
            return jsonify({'error': 'Admin access required'}), 403
        
        username = request.args.get('user')
        execute = request.args.get('execute') == 'true'
        
        if not username:
            return jsonify({'error': 'Missing ?user=username parameter'}), 400
        
        try:
            from portfolio_performance import PortfolioPerformanceCalculator, get_market_date
            
            # Get user
            user_result = db.session.execute(text(
                "SELECT id, username, max_cash_deployed FROM \"user\" WHERE username = :username"
            ), {'username': username})
            user_row = user_result.fetchone()
            
            if not user_row:
                return jsonify({'error': f'User {username} not found'}), 404
            
            # Get first transaction date
            first_txn = Transaction.query.filter_by(user_id=user_row.id).order_by(Transaction.timestamp).first()
            if not first_txn:
                return jsonify({'error': f'No transactions found for {username}'}), 404
            
            first_date = first_txn.timestamp.date()
            
            # Get earliest existing snapshot
            earliest_result = db.session.execute(text("""
                SELECT MIN(date) as earliest
                FROM portfolio_snapshot
                WHERE user_id = :user_id
            """), {'user_id': user_row.id})
            earliest_row = earliest_result.fetchone()
            earliest_snapshot = earliest_row.earliest if earliest_row and earliest_row.earliest else get_market_date()
            
            # Calculate missing date range
            current_date = first_date
            missing_dates = []
            
            while current_date < earliest_snapshot:
                # Check if snapshot already exists
                existing = PortfolioSnapshot.query.filter_by(
                    user_id=user_row.id,
                    date=current_date
                ).first()
                
                if not existing:
                    # Skip weekends (Saturday=5, Sunday=6)
                    if current_date.weekday() < 5:
                        missing_dates.append(current_date)
                
                current_date += timedelta(days=1)
            
            if not missing_dates:
                return jsonify({
                    'username': username,
                    'status': 'complete',
                    'message': 'No missing snapshots found',
                    'first_transaction': first_date.isoformat(),
                    'earliest_snapshot': earliest_snapshot.isoformat()
                })
            
            # Execute or preview
            if execute:
                calculator = PortfolioPerformanceCalculator()
                created = 0
                errors = []
                
                for snapshot_date in missing_dates:
                    try:
                        # Create snapshot for this date
                        calculator.create_daily_snapshot(user_row.id, snapshot_date)
                        created += 1
                    except Exception as e:
                        errors.append(f"{snapshot_date}: {str(e)}")
                        logger.error(f"Error creating snapshot for {username} on {snapshot_date}: {e}")
                
                return jsonify({
                    'success': True,
                    'username': username,
                    'snapshots_created': created,
                    'errors': errors,
                    'date_range': {
                        'start': missing_dates[0].isoformat(),
                        'end': missing_dates[-1].isoformat()
                    }
                })
            else:
                # Preview mode
                return jsonify({
                    'username': username,
                    'missing_snapshots': len(missing_dates),
                    'date_range': {
                        'start': missing_dates[0].isoformat(),
                        'end': missing_dates[-1].isoformat()
                    },
                    'first_transaction': first_date.isoformat(),
                    'earliest_existing_snapshot': earliest_snapshot.isoformat(),
                    'gap_days': (earliest_snapshot - first_date).days,
                    'execute_url': f'/admin/phase4/backfill-user?user={username}&execute=true',
                    'sample_dates': [d.isoformat() for d in missing_dates[:10]]
                })
            
        except Exception as e:
            import traceback
            return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500
    
    @app.route('/admin/phase4/inspect-snapshots')
    @login_required
    def inspect_snapshots():
        """Inspect snapshot values to check for aberrations"""
        if not current_user.is_admin:
            return jsonify({'error': 'Admin access required'}), 403
        
        username = request.args.get('user', 'witty-raven')
        
        try:
            # Get user
            user_result = db.session.execute(text(
                "SELECT id, username FROM \"user\" WHERE username = :username"
            ), {'username': username})
            user_row = user_result.fetchone()
            
            if not user_row:
                return jsonify({'error': f'User {username} not found'}), 404
            
            # Get all snapshots ordered by date
            snapshots = PortfolioSnapshot.query.filter_by(
                user_id=user_row.id
            ).order_by(PortfolioSnapshot.date).all()
            
            if not snapshots:
                return jsonify({'error': 'No snapshots found'}), 404
            
            # Analyze snapshots
            snapshot_data = []
            for i, s in enumerate(snapshots):
                # Calculate day-over-day change
                if i > 0:
                    prev = snapshots[i-1]
                    value_change = s.total_value - prev.total_value
                    pct_change = (value_change / prev.total_value * 100) if prev.total_value > 0 else 0
                else:
                    value_change = 0
                    pct_change = 0
                
                snapshot_data.append({
                    'date': s.date.isoformat(),
                    'weekday': s.date.strftime('%A'),
                    'total_value': round(float(s.total_value), 2),
                    'stock_value': round(float(s.stock_value), 2) if s.stock_value else 0,
                    'cash_proceeds': round(float(s.cash_proceeds), 2) if s.cash_proceeds else 0,
                    'max_cash_deployed': round(float(s.max_cash_deployed), 2) if s.max_cash_deployed else 0,
                    'day_change': round(value_change, 2),
                    'day_change_pct': round(pct_change, 2),
                    'flag': '🚨' if abs(pct_change) > 20 else ('⚠️' if abs(pct_change) > 10 else '')
                })
            
            # Calculate statistics
            values = [s.total_value for s in snapshots]
            changes = [d['day_change_pct'] for d in snapshot_data if d['day_change_pct'] != 0]
            
            stats = {
                'total_snapshots': len(snapshots),
                'date_range': {
                    'start': snapshots[0].date.isoformat(),
                    'end': snapshots[-1].date.isoformat(),
                    'days': (snapshots[-1].date - snapshots[0].date).days
                },
                'portfolio_value': {
                    'start': round(float(snapshots[0].total_value), 2),
                    'end': round(float(snapshots[-1].total_value), 2),
                    'min': round(min(values), 2),
                    'max': round(max(values), 2),
                    'current': round(float(snapshots[-1].total_value), 2)
                },
                'daily_changes': {
                    'avg_pct': round(sum(changes) / len(changes), 2) if changes else 0,
                    'max_gain_pct': round(max(changes), 2) if changes else 0,
                    'max_loss_pct': round(min(changes), 2) if changes else 0,
                    'large_moves': len([c for c in changes if abs(c) > 10])
                },
                'total_return': {
                    'amount': round(float(snapshots[-1].total_value - snapshots[0].total_value), 2),
                    'percent': round((snapshots[-1].total_value - snapshots[0].total_value) / snapshots[0].total_value * 100, 2) if snapshots[0].total_value > 0 else 0
                }
            }
            
            # Flag potential issues
            issues = []
            if stats['daily_changes']['large_moves'] > len(snapshots) * 0.2:
                issues.append(f"⚠️ Many large daily moves ({stats['daily_changes']['large_moves']} days with >10% change)")
            
            if stats['portfolio_value']['min'] == stats['portfolio_value']['max']:
                issues.append("🚨 All snapshots have identical values - likely using current prices!")
            
            # Check for flat periods
            flat_periods = 0
            for i in range(1, len(snapshot_data)):
                if snapshot_data[i]['total_value'] == snapshot_data[i-1]['total_value']:
                    flat_periods += 1
            
            if flat_periods > len(snapshots) * 0.5:
                issues.append(f"🚨 Too many identical values ({flat_periods}/{len(snapshots)}) - possibly using current prices for historical dates")
            
            return jsonify({
                'success': True,
                'username': username,
                'statistics': stats,
                'issues': issues if issues else ['✅ No obvious issues detected'],
                'snapshots': snapshot_data,
                'warning': 'Check if historical values show realistic daily variations. If all values are similar, we may be using current prices instead of historical prices.'
            })
            
        except Exception as e:
            import traceback
            return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500
