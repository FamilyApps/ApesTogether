"""
Admin routes for cash tracking implementation - Phase 0

These routes provide web-based admin interface for:
1. Creating missing transaction records
2. Adding cash tracking columns to database
3. Backfilling user cash tracking data
4. Verifying each step with comprehensive diagnostics

Import these routes in api/index.py:
    from admin_cash_tracking import register_cash_tracking_routes
    register_cash_tracking_routes(app, db)
"""

from flask import jsonify, request
from flask_login import login_required, current_user
from models import User, Stock, Transaction, PortfolioSnapshot
from datetime import datetime, date, time, timedelta
from zoneinfo import ZoneInfo
import logging

logger = logging.getLogger(__name__)

def register_cash_tracking_routes(app, db):
    """Register all cash tracking admin routes"""
    
    @app.route('/admin/cash-tracking/status')
    @login_required
    def cash_tracking_status():
        """Quick JSON status check of all phases"""
        if not current_user.is_admin:
            return jsonify({'error': 'Admin access required'}), 403
        
        try:
            from sqlalchemy import inspect, text
            
            # Check User columns
            inspector = inspect(db.engine)
            user_columns = [col['name'] for col in inspector.get_columns('user')]
            has_user_cash = 'max_cash_deployed' in user_columns and 'cash_proceeds' in user_columns
            
            # Check PortfolioSnapshot columns
            snapshot_columns = [col['name'] for col in inspector.get_columns('portfolio_snapshot')]
            has_snapshot_cash = all(col in snapshot_columns for col in ['stock_value', 'cash_proceeds', 'max_cash_deployed'])
            
            # Check for missing transactions (use raw SQL to avoid model issues)
            result = db.session.execute(text("""
                SELECT COUNT(*) as count
                FROM "user" u
                WHERE (SELECT COUNT(*) FROM stock WHERE user_id = u.id) > 0
                  AND (SELECT COUNT(*) FROM stock_transaction WHERE user_id = u.id) = 0
            """))
            missing_txn_count = result.scalar()
            
            return jsonify({
                'phase_01_transactions': 'complete' if missing_txn_count == 0 else f'{missing_txn_count} users need transactions',
                'phase_02_user_columns': 'complete' if has_user_cash else 'incomplete',
                'phase_03_user_backfill': 'pending',
                'phase_04_snapshot_columns': 'complete' if has_snapshot_cash else 'incomplete',
                'dashboard_url': '/admin/cash-tracking/dashboard'
            })
            
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    @app.route('/admin/cash-tracking/dashboard')
    @login_required  
    def cash_tracking_dashboard():
        """Comprehensive HTML dashboard for cash tracking implementation"""
        if not current_user.is_admin:
            return "Admin access required", 403
        
        try:
            from sqlalchemy import inspect, text
            
            # Get status of all phases
            inspector = inspect(db.engine)
            
            # Phase 0.2: Check User cash columns FIRST (before trying to query User model)
            user_cols = [col['name'] for col in inspector.get_columns('user')]
            has_user_cash = 'max_cash_deployed' in user_cols and 'cash_proceeds' in user_cols
            
            # Phase 0.4: Snapshot cash columns
            snap_cols = [col['name'] for col in inspector.get_columns('portfolio_snapshot')]
            has_snap_cash = all(c in snap_cols for c in ['stock_value', 'cash_proceeds', 'max_cash_deployed'])
            
            # Phase 0.1: Transaction records (use raw SQL to avoid model field issues)
            users_missing_txns = []
            result = db.session.execute(text("""
                SELECT u.id, u.username,
                       (SELECT COUNT(*) FROM stock WHERE user_id = u.id) as stock_count,
                       (SELECT COUNT(*) FROM stock_transaction WHERE user_id = u.id) as txn_count
                FROM "user" u
            """))
            
            for row in result:
                if row.stock_count > 0 and row.txn_count == 0:
                    users_missing_txns.append({
                        'username': row.username,
                        'stocks': row.stock_count,
                        'transactions': row.txn_count
                    })
            
            # Build HTML
            html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Cash Tracking Dashboard</title>
                <style>
                    body {{ font-family: Arial; margin: 20px; }}
                    .phase {{ border: 2px solid #ddd; padding: 15px; margin: 20px 0; border-radius: 8px; }}
                    .complete {{ border-color: #4CAF50; background: #f1f8f4; }}
                    .incomplete {{ border-color: #ff9800; background: #fff8f0; }}
                    .btn {{ padding: 10px 20px; background: #2196F3; color: white; text-decoration: none;
                           border-radius: 4px; display: inline-block; margin: 5px; }}
                    .btn:hover {{ background: #0b7dda; }}
                    .warning {{ color: #ff9800; font-weight: bold; }}
                    .success {{ color: #4CAF50; font-weight: bold; }}
                    table {{ border-collapse: collapse; width: 100%; margin: 10px 0; }}
                    th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
                    th {{ background: #f2f2f2; }}
                </style>
            </head>
            <body>
                <h1>💰 Cash Tracking Implementation Dashboard</h1>
                <p><a href="/admin">← Back to Admin</a> | <a href="/admin/cash-tracking/status">📊 JSON Status</a></p>
                
                <div class="phase {'complete' if len(users_missing_txns) == 0 else 'incomplete'}">
                    <h2>Phase 0.1: Transaction Records</h2>
                    <p><strong>Status:</strong> {'✅ Complete' if len(users_missing_txns) == 0 else f'⚠️ {len(users_missing_txns)} users need transactions'}</p>
                    
                    {f'<p class="success">All users have transaction records!</p>' if len(users_missing_txns) == 0 else f'''
                    <p class="warning">Users without transactions:</p>
                    <table>
                        <tr><th>Username</th><th>Stocks</th><th>Transactions</th></tr>
                        {''.join(f"<tr><td>{u['username']}</td><td>{u['stocks']}</td><td>{u['transactions']}</td></tr>" for u in users_missing_txns[:10])}
                    </table>
                    <a href="/admin/cash-tracking/create-transactions?preview=true" class="btn">🔍 Preview</a>
                    <a href="/admin/cash-tracking/create-transactions?execute=true" class="btn" 
                       onclick="return confirm('Create transaction records?')">✅ Execute</a>
                    '''}
                </div>
                
                <div class="phase {'complete' if has_user_cash else 'incomplete'}">
                    <h2>Phase 0.2: User Cash Columns</h2>
                    <p><strong>Status:</strong> {'✅ Complete' if has_user_cash else '⚠️ Incomplete'}</p>
                    
                    <ul>
                        <li>max_cash_deployed: {'✅' if 'max_cash_deployed' in user_cols else '❌'}</li>
                        <li>cash_proceeds: {'✅' if 'cash_proceeds' in user_cols else '❌'}</li>
                    </ul>
                    
                    {'''<p class="success">Columns exist!</p>''' if has_user_cash else '''
                    <a href="/admin/cash-tracking/add-user-columns?execute=true" class="btn"
                       onclick="return confirm('Add columns to User table?')">✅ Add Columns</a>
                    '''}
                </div>
                
                <div class="phase {'complete' if has_user_cash else 'incomplete'}">
                    <h2>Phase 0.3: Backfill User Cash</h2>
                    <p><strong>Status:</strong> {'⏳ Ready' if has_user_cash else '⚠️ Blocked (complete Phase 0.2 first)'}</p>
                    
                    {f'''
                    <a href="/admin/cash-tracking/backfill-users?preview=true" class="btn">🔍 Preview</a>
                    <a href="/admin/cash-tracking/backfill-users?execute=true" class="btn"
                       onclick="return confirm('Backfill cash tracking for all users?')">✅ Execute</a>
                    ''' if has_user_cash else '<p class="warning">Complete Phase 0.2 first</p>'}
                </div>
                
                <div class="phase {'complete' if has_snap_cash else 'incomplete'}">
                    <h2>Phase 0.4: Snapshot Cash Columns</h2>
                    <p><strong>Status:</strong> {'✅ Complete' if has_snap_cash else '⚠️ Incomplete'}</p>
                    
                    <ul>
                        <li>stock_value: {'✅' if 'stock_value' in snap_cols else '❌'}</li>
                        <li>cash_proceeds: {'✅' if 'cash_proceeds' in snap_cols else '❌'}</li>
                        <li>max_cash_deployed: {'✅' if 'max_cash_deployed' in snap_cols else '❌'}</li>
                    </ul>
                    
                    {'''<p class="success">Columns exist!</p>''' if has_snap_cash else '''
                    <a href="/admin/cash-tracking/add-snapshot-columns?execute=true" class="btn"
                       onclick="return confirm('Add columns to PortfolioSnapshot table?')">✅ Add Columns</a>
                    '''}
                </div>
                
                <h2>📋 Documentation</h2>
                <ul>
                    <li><a href="/admin/cash-tracking/docs">Complete Task List</a></li>
                    <li><a href="/admin/investigate-first-assets?username=witty-raven">Investigate witty-raven Data</a></li>
                </ul>
            </body>
            </html>
            """
            
            return html
            
        except Exception as e:
            import traceback
            return f"<h1>Error</h1><pre>{str(e)}\n\n{traceback.format_exc()}</pre>", 500
    
    @app.route('/admin/cash-tracking/create-transactions')
    @login_required
    def create_missing_transactions():
        """Create missing transaction records for stocks"""
        if not current_user.is_admin:
            return jsonify({'error': 'Admin access required'}), 403
        
        preview = request.args.get('preview') == 'true'
        execute = request.args.get('execute') == 'true'
        
        try:
            from sqlalchemy import text
            
            results = []
            transactions_created = 0
            
            # Get all users (use raw SQL to get just id and username, avoiding new fields)
            users_result = db.session.execute(text("SELECT id, username FROM \"user\""))
            users = [{'id': row.id, 'username': row.username} for row in users_result]
            
            for user in users:
                stocks = Stock.query.filter_by(user_id=user['id']).all()
                existing_txns = Transaction.query.filter_by(user_id=user['id']).all()
                
                # Build map of existing transaction quantities
                txn_map = {}
                for txn in existing_txns:
                    if txn.ticker not in txn_map:
                        txn_map[txn.ticker] = 0
                    if txn.transaction_type in ('buy', 'initial'):
                        txn_map[txn.ticker] += txn.quantity
                    elif txn.transaction_type == 'sell':
                        txn_map[txn.ticker] -= txn.quantity
                
                # Find stocks with missing transactions
                user_results = []
                for stock in stocks:
                    existing_qty = txn_map.get(stock.ticker, 0)
                    missing_qty = stock.quantity - existing_qty
                    
                    if missing_qty > 0:
                        # Determine timestamp
                        if stock.purchase_date:
                            stock_dt = stock.purchase_date
                            # If midnight, assume 4 PM EST
                            if stock_dt.hour == 0 and stock_dt.minute == 0:
                                ET = ZoneInfo('America/New_York')
                                timestamp = datetime.combine(
                                    stock_dt.date(),
                                    time(16, 0, 0),
                                    tzinfo=ET
                                )
                            else:
                                timestamp = stock_dt
                        else:
                            # Default to today 4 PM
                            ET = ZoneInfo('America/New_York')
                            timestamp = datetime.now(ET).replace(hour=16, minute=0, second=0, microsecond=0)
                        
                        user_results.append({
                            'ticker': stock.ticker,
                            'quantity': missing_qty,
                            'price': stock.purchase_price,
                            'timestamp': timestamp.isoformat()
                        })
                        
                        if execute:
                            new_txn = Transaction(
                                user_id=user['id'],
                                ticker=stock.ticker,
                                quantity=missing_qty,
                                price=stock.purchase_price,
                                transaction_type='initial',
                                timestamp=timestamp
                            )
                            db.session.add(new_txn)
                            transactions_created += 1
                
                if user_results:
                    results.append({
                        'username': user['username'],
                        'user_id': user['id'],
                        'transactions_to_create': user_results
                    })
            
            if execute:
                db.session.commit()
                return jsonify({
                    'success': True,
                    'transactions_created': transactions_created,
                    'users_affected': len(results),
                    'details': results
                })
            else:
                return jsonify({
                    'preview': True,
                    'transactions_would_create': sum(len(r['transactions_to_create']) for r in results),
                    'users_affected': len(results),
                    'details': results,
                    'execute_url': '/admin/cash-tracking/create-transactions?execute=true'
                })
                
        except Exception as e:
            db.session.rollback()
            import traceback
            return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500
    
    @app.route('/admin/cash-tracking/fix-transaction-type-column')
    @login_required
    def fix_transaction_type_column():
        """Widen transaction_type column to support 'initial' (7 chars)"""
        if not current_user.is_admin:
            return jsonify({'error': 'Admin access required'}), 403
        
        try:
            from sqlalchemy import text
            
            # Widen the column from VARCHAR(4) to VARCHAR(10)
            db.session.execute(text(
                "ALTER TABLE stock_transaction ALTER COLUMN transaction_type TYPE VARCHAR(10)"
            ))
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': 'transaction_type column widened to VARCHAR(10)',
                'note': 'Can now support buy, sell, and initial transaction types'
            })
            
        except Exception as e:
            db.session.rollback()
            import traceback
            return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500
    
    @app.route('/admin/cash-tracking/add-user-columns')
    @login_required
    def add_user_cash_columns():
        """Add max_cash_deployed and cash_proceeds columns to User table"""
        if not current_user.is_admin:
            return jsonify({'error': 'Admin access required'}), 403
        
        execute = request.args.get('execute') == 'true'
        
        try:
            from sqlalchemy import text
            
            # Check if columns already exist
            from sqlalchemy import inspect
            inspector = inspect(db.engine)
            user_cols = [col['name'] for col in inspector.get_columns('user')]
            
            has_max_cash = 'max_cash_deployed' in user_cols
            has_cash_proceeds = 'cash_proceeds' in user_cols
            
            if has_max_cash and has_cash_proceeds:
                return jsonify({
                    'success': True,
                    'message': 'Columns already exist',
                    'max_cash_deployed': True,
                    'cash_proceeds': True
                })
            
            if execute:
                # Add columns (quote "user" because it's a PostgreSQL reserved keyword)
                if not has_max_cash:
                    db.session.execute(text(
                        'ALTER TABLE "user" ADD COLUMN max_cash_deployed FLOAT DEFAULT 0.0 NOT NULL'
                    ))
                
                if not has_cash_proceeds:
                    db.session.execute(text(
                        'ALTER TABLE "user" ADD COLUMN cash_proceeds FLOAT DEFAULT 0.0 NOT NULL'
                    ))
                
                db.session.commit()
                
                return jsonify({
                    'success': True,
                    'columns_added': {
                        'max_cash_deployed': not has_max_cash,
                        'cash_proceeds': not has_cash_proceeds
                    },
                    'message': 'Columns added successfully'
                })
            else:
                return jsonify({
                    'preview': True,
                    'will_add': {
                        'max_cash_deployed': not has_max_cash,
                        'cash_proceeds': not has_cash_proceeds
                    },
                    'execute_url': '/admin/cash-tracking/add-user-columns?execute=true'
                })
                
        except Exception as e:
            db.session.rollback()
            import traceback
            return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500
    
    @app.route('/admin/cash-tracking/add-snapshot-columns')
    @login_required
    def add_snapshot_cash_columns():
        """Add stock_value, cash_proceeds, max_cash_deployed to PortfolioSnapshot"""
        if not current_user.is_admin:
            return jsonify({'error': 'Admin access required'}), 403
        
        execute = request.args.get('execute') == 'true'
        
        try:
            from sqlalchemy import text, inspect
            
            inspector = inspect(db.engine)
            snap_cols = [col['name'] for col in inspector.get_columns('portfolio_snapshot')]
            
            has_stock_value = 'stock_value' in snap_cols
            has_cash_proceeds = 'cash_proceeds' in snap_cols
            has_max_deployed = 'max_cash_deployed' in snap_cols
            
            if has_stock_value and has_cash_proceeds and has_max_deployed:
                return jsonify({
                    'success': True,
                    'message': 'Columns already exist',
                    'columns': {'stock_value': True, 'cash_proceeds': True, 'max_cash_deployed': True}
                })
            
            if execute:
                if not has_stock_value:
                    db.session.execute(text(
                        "ALTER TABLE portfolio_snapshot ADD COLUMN stock_value FLOAT DEFAULT 0.0"
                    ))
                
                if not has_cash_proceeds:
                    db.session.execute(text(
                        "ALTER TABLE portfolio_snapshot ADD COLUMN cash_proceeds FLOAT DEFAULT 0.0"
                    ))
                
                if not has_max_deployed:
                    db.session.execute(text(
                        "ALTER TABLE portfolio_snapshot ADD COLUMN max_cash_deployed FLOAT DEFAULT 0.0"
                    ))
                
                db.session.commit()
                
                return jsonify({
                    'success': True,
                    'columns_added': {
                        'stock_value': not has_stock_value,
                        'cash_proceeds': not has_cash_proceeds,
                        'max_cash_deployed': not has_max_deployed
                    }
                })
            else:
                return jsonify({
                    'preview': True,
                    'will_add': {
                        'stock_value': not has_stock_value,
                        'cash_proceeds': not has_cash_proceeds,
                        'max_cash_deployed': not has_max_deployed
                    },
                    'execute_url': '/admin/cash-tracking/add-snapshot-columns?execute=true'
                })
                
        except Exception as e:
            db.session.rollback()
            import traceback
            return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500
    
    @app.route('/admin/cash-tracking/test-direct-update')
    @login_required
    def test_direct_update():
        """Test writing directly to user cash columns"""
        if not current_user.is_admin:
            return jsonify({'error': 'Admin access required'}), 403
        
        try:
            from sqlalchemy import text
            
            # Try direct SQL UPDATE
            db.session.execute(text("""
                UPDATE "user" 
                SET max_cash_deployed = 999.99,
                    cash_proceeds = 111.11
                WHERE username = 'witty-raven'
            """))
            db.session.commit()
            
            # Read it back
            result = db.session.execute(text("""
                SELECT username, max_cash_deployed, cash_proceeds
                FROM "user"
                WHERE username = 'witty-raven'
            """))
            row = result.fetchone()
            
            return jsonify({
                'success': True,
                'test': 'Direct SQL UPDATE',
                'username': row.username,
                'max_cash_deployed': float(row.max_cash_deployed),
                'cash_proceeds': float(row.cash_proceeds),
                'message': 'If you see 999.99 and 111.11, database writes work!'
            })
            
        except Exception as e:
            db.session.rollback()
            import traceback
            return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500
    
    @app.route('/admin/cash-tracking/backfill-users-v2')
    @login_required
    def backfill_user_cash_v2():
        """Backfill with direct SQL UPDATE (more reliable)"""
        if not current_user.is_admin:
            return jsonify({'error': 'Admin access required'}), 403
        
        execute = request.args.get('execute') == 'true'
        
        try:
            from sqlalchemy import text
            
            # Get all users
            users_result = db.session.execute(text("SELECT id, username FROM \"user\" ORDER BY username"))
            users = [{'id': row.id, 'username': row.username} for row in users_result]
            
            results = []
            
            for user in users:
                # Get all transactions for this user
                txns_result = db.session.execute(text("""
                    SELECT ticker, quantity, price, transaction_type, timestamp
                    FROM stock_transaction
                    WHERE user_id = :user_id
                    ORDER BY timestamp
                """), {'user_id': user['id']})
                
                txns = list(txns_result)
                
                if not txns:
                    results.append({
                        'username': user['username'],
                        'max_cash_deployed': 0,
                        'cash_proceeds': 0,
                        'transactions': 0,
                        'skipped': True
                    })
                    continue
                
                # Replay transactions
                max_cash_deployed = 0.0
                cash_proceeds = 0.0
                
                for txn in txns:
                    value = txn.quantity * txn.price
                    
                    if txn.transaction_type in ('buy', 'initial'):
                        if cash_proceeds >= value:
                            cash_proceeds -= value
                        else:
                            new_capital = value - cash_proceeds
                            cash_proceeds = 0
                            max_cash_deployed += new_capital
                    
                    elif txn.transaction_type == 'sell':
                        cash_proceeds += value
                
                results.append({
                    'username': user['username'],
                    'max_cash_deployed': max_cash_deployed,
                    'cash_proceeds': cash_proceeds,
                    'transactions': len(txns)
                })
                
                if execute:
                    # Direct SQL UPDATE
                    db.session.execute(text("""
                        UPDATE "user"
                        SET max_cash_deployed = :max_cash,
                            cash_proceeds = :cash_proc
                        WHERE id = :user_id
                    """), {
                        'max_cash': max_cash_deployed,
                        'cash_proc': cash_proceeds,
                        'user_id': user['id']
                    })
            
            if execute:
                db.session.commit()
                return jsonify({
                    'success': True,
                    'method': 'Direct SQL UPDATE',
                    'users_processed': len([r for r in results if not r.get('skipped')]),
                    'details': results
                })
            else:
                return jsonify({
                    'preview': True,
                    'method': 'Would use direct SQL UPDATE',
                    'details': results,
                    'execute_url': '/admin/cash-tracking/backfill-users-v2?execute=true'
                })
                
        except Exception as e:
            db.session.rollback()
            import traceback
            return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500
    
    @app.route('/admin/cash-tracking/backfill-users')
    @login_required
    def backfill_user_cash():
        """Backfill max_cash_deployed and cash_proceeds for all users"""
        if not current_user.is_admin:
            return jsonify({'error': 'Admin access required'}), 403
        
        preview = request.args.get('preview') == 'true'
        execute = request.args.get('execute') == 'true'
        
        try:
            from cash_tracking import backfill_cash_tracking_for_user
            from sqlalchemy import text
            
            results = []
            
            # Get all users (use raw SQL to avoid querying new fields)
            users_result = db.session.execute(text("SELECT id, username FROM \"user\""))
            users = [{'id': row.id, 'username': row.username} for row in users_result]
            
            for user in users:
                try:
                    if execute:
                        result = backfill_cash_tracking_for_user(db, user['id'])
                        results.append({
                            'username': user['username'],
                            'success': True,
                            **result
                        })
                    else:
                        # Preview: just show what would be calculated
                        txns = Transaction.query.filter_by(user_id=user['id']).count()
                        results.append({
                            'username': user['username'],
                            'transactions': txns,
                            'would_process': txns > 0
                        })
                except Exception as e:
                    results.append({
                        'username': user['username'],
                        'success': False,
                        'error': str(e)
                    })
            
            if execute:
                db.session.commit()
                return jsonify({
                    'success': True,
                    'users_processed': len([r for r in results if r.get('success')]),
                    'users_failed': len([r for r in results if not r.get('success')]),
                    'details': results
                })
            else:
                return jsonify({
                    'preview': True,
                    'users_to_process': len([r for r in results if r.get('would_process')]),
                    'details': results,
                    'execute_url': '/admin/cash-tracking/backfill-users?execute=true'
                })
                
        except Exception as e:
            db.session.rollback()
            import traceback
            return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500
