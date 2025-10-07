"""
Admin routes for Phase 1: Implementation & Verification

These routes implement the core cash tracking functionality:
- Update snapshot creation to populate cash fields
- Implement Modified Dietz performance calculation
- Verify all components work correctly

Each route includes comprehensive diagnostics and verification.
"""

from flask import jsonify, request
from flask_login import login_required, current_user
from models import User, Stock, Transaction, PortfolioSnapshot
from datetime import datetime, date, timedelta
from sqlalchemy import text, func, and_
import logging

logger = logging.getLogger(__name__)

def register_phase_1_routes(app, db):
    """Register Phase 1 implementation routes"""
    
    @app.route('/admin/phase1/dashboard')
    @login_required
    def phase1_dashboard():
        """Phase 1 implementation dashboard with status and diagnostics"""
        if not current_user.is_admin:
            return "Admin access required", 403
        
        try:
            from sqlalchemy import inspect
            
            # Check Phase 0 completion
            inspector = inspect(db.engine)
            user_cols = [col['name'] for col in inspector.get_columns('user')]
            snap_cols = [col['name'] for col in inspector.get_columns('portfolio_snapshot')]
            
            phase0_complete = (
                'max_cash_deployed' in user_cols and
                'cash_proceeds' in user_cols and
                'stock_value' in snap_cols and
                'cash_proceeds' in snap_cols and
                'max_cash_deployed' in snap_cols
            )
            
            # Check if users have MEANINGFUL cash data (not just default 0)
            result = db.session.execute(text("""
                SELECT id, username, max_cash_deployed, cash_proceeds
                FROM "user"
                ORDER BY username
            """))
            all_users = result.fetchall()
            
            # Debug: Count users with actual cash data
            users_with_cash = 0
            user_debug = []
            for u in all_users:
                has_cash = u.max_cash_deployed and float(u.max_cash_deployed) > 0
                user_debug.append({
                    'username': u.username,
                    'max_cash': u.max_cash_deployed,
                    'cash_proceeds': u.cash_proceeds,
                    'has_data': has_cash
                })
                if has_cash:
                    users_with_cash += 1
            
            # Check if any snapshots have MEANINGFUL cash data (stock_value > 0, not just defaults)
            result = db.session.execute(text("""
                SELECT COUNT(*) as count
                FROM portfolio_snapshot
                WHERE stock_value > 0
            """))
            snapshots_with_cash = result.scalar()
            
            # Check total snapshots
            total_snapshots = db.session.execute(text(
                "SELECT COUNT(*) FROM portfolio_snapshot"
            )).scalar()
            
            html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Phase 1: Implementation Dashboard</title>
                <style>
                    body {{ font-family: Arial, sans-serif; margin: 20px; }}
                    .status-box {{ border: 2px solid #ddd; padding: 20px; margin: 20px 0; border-radius: 8px; }}
                    .complete {{ border-color: #4CAF50; background: #f1f8f4; }}
                    .incomplete {{ border-color: #ff9800; background: #fff8f0; }}
                    .pending {{ border-color: #ccc; background: #f5f5f5; }}
                    .btn {{ padding: 10px 20px; background: #2196F3; color: white; text-decoration: none;
                           border-radius: 4px; display: inline-block; margin: 5px; }}
                    .btn:hover {{ background: #0b7dda; }}
                    .success {{ color: #4CAF50; font-weight: bold; }}
                    .warning {{ color: #ff9800; font-weight: bold; }}
                    .error {{ color: #f44336; font-weight: bold; }}
                    table {{ border-collapse: collapse; width: 100%; margin: 10px 0; }}
                    th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
                    th {{ background: #f2f2f2; }}
                    .metric {{ font-size: 24px; font-weight: bold; color: #2196F3; }}
                </style>
            </head>
            <body>
                <h1>🚀 Phase 1: Cash Tracking Implementation</h1>
                <p><a href="/admin">← Back to Admin</a> | <a href="/admin/cash-tracking/dashboard">Phase 0 Dashboard</a></p>
                
                <div class="status-box {'complete' if phase0_complete else 'incomplete'}">
                    <h2>Phase 0: Database Schema</h2>
                    <p><strong>Status:</strong> {'✅ Complete' if phase0_complete else '⚠️ Incomplete'}</p>
                    <ul>
                        <li>User.max_cash_deployed: {'✅' if 'max_cash_deployed' in user_cols else '❌'}</li>
                        <li>User.cash_proceeds: {'✅' if 'cash_proceeds' in user_cols else '❌'}</li>
                        <li>PortfolioSnapshot.stock_value: {'✅' if 'stock_value' in snap_cols else '❌'}</li>
                        <li>PortfolioSnapshot.cash_proceeds: {'✅' if 'cash_proceeds' in snap_cols else '❌'}</li>
                        <li>PortfolioSnapshot.max_cash_deployed: {'✅' if 'max_cash_deployed' in snap_cols else '❌'}</li>
                    </ul>
                    <p class="metric">{users_with_cash} / 5 users have cash data</p>
                </div>
                
                <div class="status-box {'complete' if snapshots_with_cash > 0 else 'incomplete'}">
                    <h2>Step 1: Snapshot Creation Update</h2>
                    <p><strong>Status:</strong> {'✅ Working' if snapshots_with_cash > 0 else '⚠️ Not Implemented'}</p>
                    <p class="metric">{snapshots_with_cash} / {total_snapshots} snapshots have cash data</p>
                    
                    {'<p class="success">Snapshot creation is populating cash fields!</p>' if snapshots_with_cash > 0 else '''
                    <p class="warning">Snapshots are not yet using cash tracking fields.</p>
                    <h3>Action Required:</h3>
                    <p>Test snapshot creation with cash tracking:</p>
                    <a href="/admin/phase1/test-snapshot-creation?user=witty-raven" class="btn">🧪 Test Snapshot Creation</a>
                    <a href="/admin/phase1/verify-snapshot-logic" class="btn">🔍 Verify Logic</a>
                    '''}
                </div>
                
                <div class="status-box pending">
                    <h2>Step 2: Modified Dietz Implementation</h2>
                    <p><strong>Status:</strong> ⏳ Pending</p>
                    <p>Performance calculation that accounts for capital deployment timing.</p>
                    <a href="/admin/phase1/test-modified-dietz?user=witty-raven" class="btn">🧪 Test Modified Dietz</a>
                    <a href="/admin/phase1/compare-calculations" class="btn">📊 Compare Old vs New</a>
                </div>
                
                <div class="status-box pending">
                    <h2>Step 3: Chart API Updates</h2>
                    <p><strong>Status:</strong> ⏳ Pending</p>
                    <p>Update chart APIs to use Modified Dietz and include cash in portfolio values.</p>
                    <a href="/admin/phase1/test-chart-api?period=1M" class="btn">🧪 Test Chart API</a>
                </div>
                
                <h2>📊 System Status</h2>
                <table>
                    <tr>
                        <th>Metric</th>
                        <th>Value</th>
                        <th>Status</th>
                    </tr>
                    <tr>
                        <td>Users with cash tracking</td>
                        <td>{users_with_cash}</td>
                        <td>{'✅' if users_with_cash > 0 else '❌'}</td>
                    </tr>
                    <tr>
                        <td>Total snapshots</td>
                        <td>{total_snapshots:,}</td>
                        <td>ℹ️</td>
                    </tr>
                    <tr>
                        <td>Snapshots with cash data</td>
                        <td>{snapshots_with_cash:,}</td>
                        <td>{'✅' if snapshots_with_cash > 0 else '⚠️'}</td>
                    </tr>
                    <tr>
                        <td>Cash data coverage</td>
                        <td>{(snapshots_with_cash / total_snapshots * 100 if total_snapshots > 0 else 0):.1f}%</td>
                        <td>{'✅' if snapshots_with_cash > 0 else '⚠️'}</td>
                    </tr>
                </table>
                
                <h2>👥 User Cash Tracking Data (Debug)</h2>
                <table>
                    <tr>
                        <th>Username</th>
                        <th>Max Cash Deployed</th>
                        <th>Cash Proceeds</th>
                        <th>Has Data?</th>
                        <th>Status</th>
                    </tr>
                    {''.join(f'''<tr>
                        <td>{d['username']}</td>
                        <td>{d['max_cash'] if d['max_cash'] is not None else 'NULL'} (${float(d['max_cash'] or 0):,.2f})</td>
                        <td>{d['cash_proceeds'] if d['cash_proceeds'] is not None else 'NULL'} (${float(d['cash_proceeds'] or 0):,.2f})</td>
                        <td>{'✅ YES' if d['has_data'] else '❌ NO'}</td>
                        <td>{'✅ Good' if d['has_data'] else '⚠️ No data'}</td>
                    </tr>''' for d in user_debug)}
                </table>
                <p><strong>Debug Info:</strong> Counting users where max_cash_deployed > 0</p>
                
                <h2>🎯 Next Actions</h2>
                <ol>
                    <li>Test snapshot creation with cash tracking</li>
                    <li>Verify Modified Dietz calculations</li>
                    <li>Update chart APIs</li>
                    <li>Proceed to Phase 2 (data cleanup)</li>
                </ol>
            </body>
            </html>
            """
            
            return html
            
        except Exception as e:
            import traceback
            return f"<h1>Error</h1><pre>{str(e)}\n\n{traceback.format_exc()}</pre>", 500
    
    @app.route('/admin/phase1/test-snapshot-creation')
    @login_required
    def test_snapshot_creation():
        """Test creating a snapshot with cash tracking fields"""
        if not current_user.is_admin:
            return jsonify({'error': 'Admin access required'}), 403
        
        username = request.args.get('user', 'witty-raven')
        
        try:
            from cash_tracking import calculate_portfolio_value_with_cash
            from sqlalchemy import text
            
            # Get user
            user_result = db.session.execute(text(
                f"SELECT id, username, max_cash_deployed, cash_proceeds FROM \"user\" WHERE username = :username"
            ), {'username': username})
            user_row = user_result.fetchone()
            
            if not user_row:
                return jsonify({'error': f'User {username} not found'}), 404
            
            user_id = user_row.id
            
            # Calculate current portfolio value with cash breakdown
            portfolio = calculate_portfolio_value_with_cash(user_id)
            
            # Create test snapshot for today
            test_date = date.today()
            
            # Check if snapshot already exists
            existing = PortfolioSnapshot.query.filter_by(
                user_id=user_id,
                date=test_date
            ).first()
            
            if existing:
                # Update it
                existing.stock_value = portfolio['stock_value']
                existing.cash_proceeds = portfolio['cash_proceeds']
                existing.max_cash_deployed = user_row.max_cash_deployed
                existing.total_value = portfolio['total_value']
                action = 'updated'
            else:
                # Create new
                new_snapshot = PortfolioSnapshot(
                    user_id=user_id,
                    date=test_date,
                    stock_value=portfolio['stock_value'],
                    cash_proceeds=portfolio['cash_proceeds'],
                    max_cash_deployed=user_row.max_cash_deployed,
                    total_value=portfolio['total_value'],
                    cash_flow=0
                )
                db.session.add(new_snapshot)
                action = 'created'
            
            db.session.commit()
            
            return jsonify({
                'success': True,
                'action': action,
                'username': username,
                'user_id': user_id,
                'date': test_date.isoformat(),
                'snapshot_data': {
                    'stock_value': portfolio['stock_value'],
                    'cash_proceeds': portfolio['cash_proceeds'],
                    'max_cash_deployed': float(user_row.max_cash_deployed),
                    'total_value': portfolio['total_value']
                },
                'verification': {
                    'total_matches': abs(portfolio['total_value'] - (portfolio['stock_value'] + portfolio['cash_proceeds'])) < 0.01,
                    'all_fields_populated': all([
                        portfolio['stock_value'] is not None,
                        portfolio['cash_proceeds'] is not None,
                        user_row.max_cash_deployed is not None
                    ])
                },
                'message': f'Snapshot {action} successfully with cash tracking!'
            })
            
        except Exception as e:
            db.session.rollback()
            import traceback
            return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500
    
    @app.route('/admin/phase1/verify-snapshot-logic')
    @login_required
    def verify_snapshot_logic():
        """Verify snapshot creation logic is correct"""
        if not current_user.is_admin:
            return jsonify({'error': 'Admin access required'}), 403
        
        try:
            from cash_tracking import calculate_portfolio_value_with_cash
            from sqlalchemy import text
            
            # Get all users with cash tracking
            users_result = db.session.execute(text("""
                SELECT id, username, max_cash_deployed, cash_proceeds
                FROM "user"
                WHERE max_cash_deployed > 0
                ORDER BY username
            """))
            
            results = []
            for user_row in users_result:
                # Calculate portfolio value
                portfolio = calculate_portfolio_value_with_cash(user_row.id)
                
                # Check math
                calculated_total = portfolio['stock_value'] + portfolio['cash_proceeds']
                matches = abs(portfolio['total_value'] - calculated_total) < 0.01
                
                results.append({
                    'username': user_row.username,
                    'stock_value': portfolio['stock_value'],
                    'cash_proceeds': portfolio['cash_proceeds'],
                    'max_cash_deployed': float(user_row.max_cash_deployed),
                    'total_value': portfolio['total_value'],
                    'calculated_total': calculated_total,
                    'math_correct': matches,
                    'ready_for_snapshot': matches and portfolio['total_value'] > 0
                })
            
            all_correct = all(r['math_correct'] for r in results)
            
            return jsonify({
                'success': True,
                'all_users_correct': all_correct,
                'users_checked': len(results),
                'details': results,
                'message': 'All calculations correct!' if all_correct else 'Some calculations have issues'
            })
            
        except Exception as e:
            import traceback
            return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500
    
    @app.route('/admin/phase1/create-todays-snapshots')
    @login_required
    def create_todays_snapshots_with_cash():
        """Create today's snapshots for all users with cash tracking"""
        if not current_user.is_admin:
            return jsonify({'error': 'Admin access required'}), 403
        
        try:
            from portfolio_performance import PortfolioPerformanceCalculator, get_market_date
            from sqlalchemy import text
            
            calculator = PortfolioPerformanceCalculator()
            
            # Get all users with cash tracking
            users_result = db.session.execute(text("""
                SELECT id, username, max_cash_deployed
                FROM "user"
                WHERE max_cash_deployed > 0
                ORDER BY username
            """))
            
            results = []
            snapshots_created = 0
            snapshots_updated = 0
            errors = []
            
            for user_row in users_result:
                try:
                    # Check if snapshot already exists for today (use ET date, not UTC)
                    today = get_market_date()
                    existing = PortfolioSnapshot.query.filter_by(
                        user_id=user_row.id,
                        date=today
                    ).first()
                    
                    action = 'updated' if existing else 'created'
                    
                    # Create/update snapshot
                    calculator.create_daily_snapshot(user_row.id)
                    
                    # Verify it was saved correctly
                    snapshot = PortfolioSnapshot.query.filter_by(
                        user_id=user_row.id,
                        date=today
                    ).first()
                    
                    if snapshot:
                        if action == 'created':
                            snapshots_created += 1
                        else:
                            snapshots_updated += 1
                        
                        results.append({
                            'username': user_row.username,
                            'action': action,
                            'date': today.isoformat(),
                            'snapshot': {
                                'total_value': float(snapshot.total_value),
                                'stock_value': float(snapshot.stock_value) if snapshot.stock_value else 0,
                                'cash_proceeds': float(snapshot.cash_proceeds) if snapshot.cash_proceeds else 0,
                                'max_cash_deployed': float(snapshot.max_cash_deployed) if snapshot.max_cash_deployed else 0,
                                'cash_flow': float(snapshot.cash_flow) if snapshot.cash_flow else 0
                            },
                            'verification': {
                                'has_stock_value': snapshot.stock_value is not None and snapshot.stock_value > 0,
                                'fields_populated': all([
                                    snapshot.stock_value is not None,
                                    snapshot.cash_proceeds is not None,
                                    snapshot.max_cash_deployed is not None
                                ])
                            }
                        })
                    else:
                        errors.append(f"{user_row.username}: Snapshot not found after creation")
                        
                except Exception as e:
                    error_msg = f"{user_row.username}: {str(e)}"
                    errors.append(error_msg)
                    logger.error(error_msg)
            
            return jsonify({
                'success': True,
                'snapshots_created': snapshots_created,
                'snapshots_updated': snapshots_updated,
                'users_processed': len(results),
                'errors': errors,
                'details': results,
                'message': f'Created {snapshots_created} and updated {snapshots_updated} snapshots with cash tracking!'
            })
            
        except Exception as e:
            import traceback
            return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500
    
    @app.route('/admin/phase1/test-modified-dietz')
    @login_required
    def test_modified_dietz():
        """Test Modified Dietz calculation for a user"""
        if not current_user.is_admin:
            return jsonify({'error': 'Admin access required'}), 403
        
        username = request.args.get('user', 'witty-raven')
        period = request.args.get('period', '1M')  # 1D, 1W, 1M, 3M, YTD, 1Y
        
        try:
            from portfolio_performance import PortfolioPerformanceCalculator, get_market_date
            from sqlalchemy import text
            
            calculator = PortfolioPerformanceCalculator()
            
            # Get user
            user_result = db.session.execute(text(
                "SELECT id, username, max_cash_deployed, cash_proceeds FROM \"user\" WHERE username = :username"
            ), {'username': username})
            user_row = user_result.fetchone()
            
            if not user_row:
                return jsonify({'error': f'User {username} not found'}), 404
            
            # Calculate date range
            end_date = get_market_date()
            
            if period == '1D':
                start_date = end_date - timedelta(days=1)
            elif period == '1W':
                start_date = end_date - timedelta(days=7)
            elif period == '1M':
                start_date = end_date - timedelta(days=30)
            elif period == '3M':
                start_date = end_date - timedelta(days=90)
            elif period == 'YTD':
                start_date = date(end_date.year, 1, 1)
            elif period == '1Y':
                start_date = end_date - timedelta(days=365)
            else:
                return jsonify({'error': f'Invalid period: {period}'}), 400
            
            # Get snapshots for the period
            snapshots = PortfolioSnapshot.query.filter(
                and_(
                    PortfolioSnapshot.user_id == user_row.id,
                    PortfolioSnapshot.date >= start_date,
                    PortfolioSnapshot.date <= end_date
                )
            ).order_by(PortfolioSnapshot.date).all()
            
            if len(snapshots) < 2:
                return jsonify({
                    'username': username,
                    'period': period,
                    'snapshots_found': len(snapshots),
                    'error': 'Need at least 2 snapshots for performance calculation',
                    'date_range': {
                        'start': start_date.isoformat(),
                        'end': end_date.isoformat()
                    }
                })
            
            # Calculate Modified Dietz return
            modified_dietz_return = calculator.calculate_modified_dietz_return(
                user_row.id, start_date, end_date
            )
            
            # Calculate simple ROI for comparison
            beginning_value = snapshots[0].total_value
            ending_value = snapshots[-1].total_value
            simple_roi = ((ending_value - beginning_value) / beginning_value) if beginning_value > 0 else 0
            
            # Get cash flow details
            total_cash_flow = sum(s.cash_flow for s in snapshots[1:])
            
            return jsonify({
                'success': True,
                'username': username,
                'period': period,
                'date_range': {
                    'start': start_date.isoformat(),
                    'end': end_date.isoformat(),
                    'days': (end_date - start_date).days
                },
                'snapshots_analyzed': len(snapshots),
                'portfolio_values': {
                    'beginning': float(beginning_value),
                    'ending': float(ending_value),
                    'change': float(ending_value - beginning_value)
                },
                'cash_flows': {
                    'total_net_cash_flow': float(total_cash_flow),
                    'transactions': len([s for s in snapshots if s.cash_flow != 0])
                },
                'returns': {
                    'modified_dietz': float(modified_dietz_return * 100),  # Convert to percentage
                    'simple_roi': float(simple_roi * 100),  # Convert to percentage
                    'difference': float((modified_dietz_return - simple_roi) * 100)
                },
                'explanation': {
                    'modified_dietz': 'Accounts for timing of cash flows (buys/sells)',
                    'simple_roi': 'Ignores timing - just (end - start) / start',
                    'why_different': 'Modified Dietz is more accurate when there are cash flows during the period'
                }
            })
            
        except Exception as e:
            import traceback
            return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500
    
    @app.route('/admin/phase1/compare-all-users')
    @login_required
    def compare_all_users_performance():
        """Compare performance calculations for all users"""
        if not current_user.is_admin:
            return jsonify({'error': 'Admin access required'}), 403
        
        period = request.args.get('period', '1M')
        
        try:
            from portfolio_performance import PortfolioPerformanceCalculator, get_market_date
            from sqlalchemy import text
            
            calculator = PortfolioPerformanceCalculator()
            
            # Calculate date range
            end_date = get_market_date()
            
            if period == '1M':
                start_date = end_date - timedelta(days=30)
            elif period == '3M':
                start_date = end_date - timedelta(days=90)
            elif period == 'YTD':
                start_date = date(end_date.year, 1, 1)
            elif period == '1Y':
                start_date = end_date - timedelta(days=365)
            else:
                start_date = end_date - timedelta(days=30)
            
            # Get all users with cash tracking
            users_result = db.session.execute(text("""
                SELECT id, username, max_cash_deployed, cash_proceeds
                FROM "user"
                WHERE max_cash_deployed > 0
                ORDER BY username
            """))
            
            results = []
            
            for user_row in users_result:
                snapshots = PortfolioSnapshot.query.filter(
                    and_(
                        PortfolioSnapshot.user_id == user_row.id,
                        PortfolioSnapshot.date >= start_date,
                        PortfolioSnapshot.date <= end_date
                    )
                ).order_by(PortfolioSnapshot.date).all()
                
                if len(snapshots) < 2:
                    results.append({
                        'username': user_row.username,
                        'snapshots': len(snapshots),
                        'status': 'insufficient_data'
                    })
                    continue
                
                # Calculate Modified Dietz
                modified_dietz = calculator.calculate_modified_dietz_return(
                    user_row.id, start_date, end_date
                )
                
                # Calculate simple ROI
                beginning = snapshots[0].total_value
                ending = snapshots[-1].total_value
                simple_roi = ((ending - beginning) / beginning) if beginning > 0 else 0
                
                results.append({
                    'username': user_row.username,
                    'invested': float(user_row.max_cash_deployed),
                    'current_value': float(ending),
                    'snapshots': len(snapshots),
                    'modified_dietz_return': float(modified_dietz * 100),
                    'simple_roi': float(simple_roi * 100),
                    'difference': float((modified_dietz - simple_roi) * 100),
                    'status': 'calculated'
                })
            
            return jsonify({
                'success': True,
                'period': period,
                'date_range': {
                    'start': start_date.isoformat(),
                    'end': end_date.isoformat()
                },
                'users_analyzed': len(results),
                'results': results,
                'summary': {
                    'calculated': len([r for r in results if r.get('status') == 'calculated']),
                    'insufficient_data': len([r for r in results if r.get('status') == 'insufficient_data'])
                }
            })
            
        except Exception as e:
            import traceback
            return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500
