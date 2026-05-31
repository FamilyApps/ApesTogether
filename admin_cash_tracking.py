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
from flask_login import current_user
from admin_auth import admin_required
from mobile_api import with_db_retry
from models import User, Stock, Transaction, PortfolioSnapshot
from datetime import datetime, date, time, timedelta
from zoneinfo import ZoneInfo
import logging
import os

logger = logging.getLogger(__name__)


def _find_admin_user_for_persistence():
    """Locate the models.User row to attach admin-persisted JSON
    (last_drift_check, last_snapshot_audit) to.

    Why this helper exists:
      The codebase has THREE different `User` classes mapped to the same
      `"user"` DB table — `models.User`, `app.User`, and `api.index.User`.
      Only `models.User` exposes the `extra_data` JSON column (mapped to the
      `metadata` SQL column). `flask_login.current_user` is hydrated by the
      LoginManager.user_loader, which on the Vercel handler returns an
      `api.index.User` instance that does NOT have `extra_data`. Writing
      `admin.extra_data = ...` against that instance raises AttributeError
      and the persistence block aborts.

      Additionally, on warm Vercel instances SQLAlchemy's identity-map can
      hand back a CACHED `models.User` row from a prior request whose
      `extra_data` reflects a stale snapshot. If two admin endpoints write
      to `extra_data` in quick succession, the second one's read-modify-
      write loop reads the stale dict and silently overwrites the first
      one's commit (witnessed: `last_drift_check` getting clobbered by a
      subsequent `last_snapshot_audit` write even though both writers
      reported `persisted: true, persisted_user_id: 1`).

    Strategy (in order):
      1. Take `current_user.id` and re-query `models.User` with
         `populate_existing()` so we re-read the row from the DB instead
         of getting a stale identity-map hit.
      2. Case-insensitive email match against ADMIN_EMAIL env var. Used by
         cron-driven requests where there is no Flask-Login context.
      3. Exact env-var match (legacy behavior, kept as last resort).

    Before any lookup we call `db.session.expire_all()` so any objects the
    session is already tracking get re-fetched on next access. This belt-
    and-suspenders approach makes the read-modify-write pattern safe even
    if the same User instance is touched twice in one request.

    All returns are validated with `hasattr(admin, 'extra_data')` so we
    never hand back a User-shaped object that can't actually be persisted.

    Returns the row or None. Logs WARNING on full miss so the failure is
    visible in Vercel logs instead of being silent.
    """
    # Belt-and-suspenders: invalidate any cached state in the current
    # session so the lookup below truly re-reads from the DB. Cheap.
    try:
        from models import db as _db
        _db.session.expire_all()
    except Exception:
        pass

    # Path 1: current_user.id → models.User (NOT current_user directly —
    # the Flask-Login proxy may resolve to api.index.User which lacks
    # extra_data). populate_existing() bypasses the identity-map cache.
    try:
        if current_user and current_user.is_authenticated:
            cur_id = getattr(current_user, 'id', None)
            if cur_id:
                admin = User.query.populate_existing().get(cur_id)
                if admin is not None and hasattr(admin, 'extra_data'):
                    return admin
    except Exception:
        pass  # Falls through to env-var lookup

    admin_email = os.environ.get('ADMIN_EMAIL', 'admin@apestogether.ai')

    # Path 2: case-insensitive match (handles DB-vs-env casing drift)
    from sqlalchemy import func
    admin = User.query.populate_existing().filter(
        func.lower(User.email) == admin_email.lower()
    ).first()
    if admin is not None and hasattr(admin, 'extra_data'):
        return admin

    # Path 3: legacy exact match
    admin = User.query.populate_existing().filter_by(email=admin_email).first()
    if admin is not None and hasattr(admin, 'extra_data'):
        return admin

    logger.warning(
        f"_find_admin_user_for_persistence: no models.User row found for "
        f"current_user.id or ADMIN_EMAIL={admin_email!r} (case-insensitive). "
        f"last_drift_check / last_snapshot_audit will not be persisted."
    )
    return None

def register_cash_tracking_routes(app, db):
    """Register all cash tracking admin routes"""
    
    @app.route('/admin/cash-tracking/status')
    @admin_required
    @with_db_retry
    def cash_tracking_status():
        """Quick JSON status check of all phases"""
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
    @admin_required  
    def cash_tracking_dashboard():
        """Comprehensive HTML dashboard for cash tracking implementation"""
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
            logger.error(f"Cash tracking error: {traceback.format_exc()}")
            return f"<h1>Error</h1><pre>{str(e)}</pre>", 500
    
    @app.route('/admin/cash-tracking/create-transactions')
    @admin_required
    def create_missing_transactions():
        """Create missing transaction records for stocks"""
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
            logger.error(f"Cash tracking error: {e}", exc_info=True)
            return jsonify({'error': str(e)}), 500
    
    @app.route('/admin/cash-tracking/fix-transaction-type-column')
    @admin_required
    def fix_transaction_type_column():
        """Widen transaction_type column to support 'initial' (7 chars)"""
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
            logger.error(f"Cash tracking error: {e}", exc_info=True)
            return jsonify({'error': str(e)}), 500
    
    @app.route('/admin/cash-tracking/add-user-columns')
    @admin_required
    def add_user_cash_columns():
        """Add max_cash_deployed and cash_proceeds columns to User table"""
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
            logger.error(f"Cash tracking error: {e}", exc_info=True)
            return jsonify({'error': str(e)}), 500
    
    @app.route('/admin/cash-tracking/add-snapshot-columns')
    @admin_required
    def add_snapshot_cash_columns():
        """Add stock_value, cash_proceeds, max_cash_deployed to PortfolioSnapshot"""
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
            logger.error(f"Cash tracking error: {e}", exc_info=True)
            return jsonify({'error': str(e)}), 500
    
    @app.route('/admin/cash-tracking/backfill-single-user')
    @admin_required
    def backfill_single_user():
        """Backfill a single user with direct SQL (fast, no timeout)"""
        username = request.args.get('user')
        if not username:
            return jsonify({'error': 'Missing ?user=username parameter'}), 400
        
        try:
            from sqlalchemy import text
            
            # Get user
            user_result = db.session.execute(text(
                "SELECT id, username FROM \"user\" WHERE username = :username"
            ), {'username': username})
            user = user_result.fetchone()
            
            if not user:
                return jsonify({'error': f'User {username} not found'}), 404
            
            # Get all transactions
            txns_result = db.session.execute(text("""
                SELECT ticker, quantity, price, transaction_type, timestamp
                FROM stock_transaction
                WHERE user_id = :user_id
                ORDER BY timestamp
            """), {'user_id': user.id})
            
            txns = list(txns_result)
            
            if not txns:
                return jsonify({
                    'username': username,
                    'transactions': 0,
                    'max_cash_deployed': 0,
                    'cash_proceeds': 0,
                    'message': 'No transactions found, skipped'
                })
            
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
            
            # Direct SQL UPDATE
            db.session.execute(text("""
                UPDATE "user"
                SET max_cash_deployed = :max_cash,
                    cash_proceeds = :cash_proc
                WHERE id = :user_id
            """), {
                'max_cash': max_cash_deployed,
                'cash_proc': cash_proceeds,
                'user_id': user.id
            })
            db.session.commit()
            
            return jsonify({
                'success': True,
                'username': username,
                'transactions': len(txns),
                'max_cash_deployed': max_cash_deployed,
                'cash_proceeds': cash_proceeds,
                'message': 'Successfully backfilled!'
            })
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Cash tracking error: {e}", exc_info=True)
            return jsonify({'error': str(e)}), 500
    
    @app.route('/admin/cash-tracking/test-direct-update')
    @admin_required
    def test_direct_update():
        """Test writing directly to user cash columns"""
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
            logger.error(f"Cash tracking error: {e}", exc_info=True)
            return jsonify({'error': str(e)}), 500
    
    @app.route('/admin/cash-tracking/backfill-users-v2')
    @admin_required
    def backfill_user_cash_v2():
        """Backfill with direct SQL UPDATE (more reliable)"""
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
            logger.error(f"Cash tracking error: {e}", exc_info=True)
            return jsonify({'error': str(e)}), 500
    
    @app.route('/admin/cash-tracking/reconcile')
    @admin_required
    @with_db_retry
    def reconcile_cash_tracking():
        """
        Fix max_cash_deployed drift caused by race conditions in concurrent trades.
        
        For a given user (or all users):
        1. Replay ALL transactions chronologically to get the correct max_cash_deployed
        2. Fix the user model if it has drifted
        3. Rebuild snapshot max_cash_deployed values (per-date replay)
        
        Usage:
          /admin/cash-tracking/reconcile?username=chart1658          (preview)
          /admin/cash-tracking/reconcile?username=chart1658&execute=true  (fix)
          /admin/cash-tracking/reconcile?all=true&execute=true       (fix all users)
        """
        username = request.args.get('username')
        fix_all = request.args.get('all') == 'true'
        execute = request.args.get('execute') == 'true'
        
        try:
            from sqlalchemy import text
            
            if username:
                user = User.query.filter_by(username=username).first()
                if not user:
                    return jsonify({'error': f'User {username} not found'}), 404
                users = [user]
            elif fix_all:
                users = User.query.all()
            else:
                return jsonify({'error': 'Provide username or all=true'}), 400
            
            results = []
            
            for user in users:
                # Get ALL transactions chronologically
                txns = Transaction.query.filter_by(user_id=user.id).order_by(Transaction.timestamp).all()
                
                if not txns:
                    continue
                
                # Replay to get correct final values
                replay_cash = 0.0
                replay_max_cash = 0.0
                
                # Also build per-date max_cash_deployed for snapshot correction
                per_date_max_cash = {}
                per_date_cash_proceeds = {}
                
                for txn in txns:
                    val = txn.quantity * txn.price
                    if txn.transaction_type in ('buy', 'initial'):
                        if replay_cash >= val:
                            replay_cash -= val
                        else:
                            new_cap = val - replay_cash
                            replay_cash = 0
                            replay_max_cash += new_cap
                    elif txn.transaction_type in ('sell', 'dividend'):
                        replay_cash += val
                    
                    txn_date = txn.timestamp.date() if txn.timestamp else None
                    if txn_date:
                        per_date_max_cash[txn_date] = replay_max_cash
                        per_date_cash_proceeds[txn_date] = replay_cash
                
                # Check for drift
                user_drift = round(user.max_cash_deployed - replay_max_cash, 2)
                cash_drift = round(user.cash_proceeds - replay_cash, 2)
                
                result = {
                    'username': user.username,
                    'user_max_cash_current': round(user.max_cash_deployed, 2),
                    'user_max_cash_correct': round(replay_max_cash, 2),
                    'user_cash_current': round(user.cash_proceeds, 2),
                    'user_cash_correct': round(replay_cash, 2),
                    'max_cash_drift': user_drift,
                    'cash_drift': cash_drift,
                    'has_drift': abs(user_drift) > 0.01 or abs(cash_drift) > 0.01,
                    'transactions': len(txns),
                }
                
                if execute:
                    # 1. Fix user model
                    db.session.execute(text("""
                        UPDATE "user"
                        SET max_cash_deployed = :max_cash,
                            cash_proceeds = :cash_proc
                        WHERE id = :user_id
                    """), {
                        'max_cash': replay_max_cash,
                        'cash_proc': replay_cash,
                        'user_id': user.id
                    })

                    # 2. Fix snapshots via raw SQL UPDATE (per snapshot).
                    # We previously mutated ORM objects and relied on db.session.commit()
                    # to flush them, but those flushes did not persist reliably (likely a
                    # session/identity-map edge case), causing snapshots_fixed > 0 but no
                    # actual DB changes. Raw UPDATE returns rowcount so we know each
                    # statement persisted.
                    from models import PortfolioSnapshot
                    snapshots = PortfolioSnapshot.query.filter_by(user_id=user.id).order_by(PortfolioSnapshot.date).all()

                    snapshots_fixed = 0
                    sorted_dates = sorted(per_date_max_cash.keys())

                    for snap in snapshots:
                        correct_max_cash = 0.0
                        correct_cash_proceeds = 0.0
                        for d in sorted_dates:
                            if d <= snap.date:
                                correct_max_cash = per_date_max_cash[d]
                                correct_cash_proceeds = per_date_cash_proceeds[d]
                            else:
                                break

                        upd = db.session.execute(text("""
                            UPDATE portfolio_snapshot
                            SET max_cash_deployed = :max_cash,
                                cash_proceeds = :cash_proc,
                                total_value = COALESCE(stock_value, 0) + :cash_proc
                            WHERE user_id = :user_id
                              AND date = :snap_date
                              AND (
                                  ABS(COALESCE(max_cash_deployed, 0) - :max_cash) > 0.01
                                  OR ABS(COALESCE(cash_proceeds, 0) - :cash_proc) > 0.01
                                  OR ABS(COALESCE(total_value, 0) - (COALESCE(stock_value, 0) + :cash_proc)) > 0.01
                              )
                        """), {
                            'max_cash': correct_max_cash,
                            'cash_proc': correct_cash_proceeds,
                            'user_id': user.id,
                            'snap_date': snap.date,
                        })
                        if upd.rowcount > 0:
                            snapshots_fixed += 1

                    result['snapshots_fixed'] = snapshots_fixed
                    result['fixed'] = True
                
                results.append(result)
            
            if execute:
                db.session.commit()
            
            drifted = [r for r in results if r.get('has_drift')]
            return jsonify({
                'execute': execute,
                'users_checked': len(results),
                'users_with_drift': len(drifted),
                'results': results if len(results) <= 20 else drifted,
            })
        
        except Exception as e:
            db.session.rollback()
            logger.error(f"Reconciliation error: {e}", exc_info=True)
            return jsonify({'error': str(e)}), 500
    
    @app.route('/admin/cash-tracking/fix-seeded-bot')
    @admin_required
    @with_db_retry
    def fix_seeded_bot_cash():
        """
        Fix max_cash_deployed for bots whose stocks were seeded directly without
        corresponding 'buy'/'initial' transactions.

        These users have replay max_cash_deployed = 0 (because there are no buys
        in their transaction history) even though they hold real stock positions.

        Sets:
            user.max_cash_deployed = current_cost_basis + current_cash_proceeds
        and propagates that value to every PortfolioSnapshot for the user, then
        recalculates total_value = stock_value + cash_proceeds for each snapshot.

        Usage:
            /admin/cash-tracking/fix-seeded-bot?username=fund.finance2024            (preview)
            /admin/cash-tracking/fix-seeded-bot?username=fund.finance2024&execute=true (apply)
        """
        username = request.args.get('username')
        execute = request.args.get('execute') == 'true'

        if not username:
            return jsonify({'error': 'username required'}), 400

        try:
            from sqlalchemy import text

            user = User.query.filter_by(username=username).first()
            if not user:
                return jsonify({'error': f'User {username} not found'}), 404

            # Compute current cost basis from holdings
            stocks = Stock.query.filter_by(user_id=user.id).all()
            cost_basis = round(sum((s.quantity or 0) * (s.purchase_price or 0) for s in stocks), 2)

            # Replay transactions to compute correct cash_proceeds
            txns = Transaction.query.filter_by(user_id=user.id).order_by(Transaction.timestamp).all()
            replay_cash = 0.0
            replay_max_cash = 0.0
            buy_count = 0
            sell_count = 0
            for txn in txns:
                val = (txn.quantity or 0) * (txn.price or 0)
                if txn.transaction_type in ('buy', 'initial'):
                    buy_count += 1
                    if replay_cash >= val:
                        replay_cash -= val
                    else:
                        new_cap = val - replay_cash
                        replay_cash = 0
                        replay_max_cash += new_cap
                elif txn.transaction_type in ('sell', 'dividend'):
                    sell_count += 1
                    replay_cash += val

            target_max_cash = round(cost_basis + replay_cash, 2)

            # Safety check: only fix users whose recorded transactions can't fully account
            # for their current holdings. If replay_max_cash already >= cost_basis, the
            # transaction history is sufficient and reconcile is the right tool.
            if replay_max_cash >= cost_basis - 0.01:
                return jsonify({
                    'error': 'use_reconcile_instead',
                    'message': (
                        f'{username}\'s replay max_cash_deployed (${replay_max_cash:.2f}) '
                        f'covers their current cost basis (${cost_basis:.2f}). '
                        'Transaction history is sufficient — use '
                        '/admin/cash-tracking/reconcile instead.'
                    ),
                    'replay_max_cash': round(replay_max_cash, 2),
                    'cost_basis': cost_basis,
                    'buy_count': buy_count,
                    'sell_count': sell_count,
                }), 400

            preview = {
                'username': user.username,
                'user_id': user.id,
                'stocks_held': len(stocks),
                'cost_basis': cost_basis,
                'replayed_max_cash_deployed': round(replay_max_cash, 2),
                'replayed_cash_proceeds': round(replay_cash, 2),
                'target_max_cash_deployed': target_max_cash,
                'current_user_max_cash_deployed': round(user.max_cash_deployed or 0, 2),
                'current_user_cash_proceeds': round(user.cash_proceeds or 0, 2),
                'transactions': len(txns),
                'buy_count': buy_count,
                'sell_count': sell_count,
            }

            if not execute:
                preview['execute_url'] = (
                    f'/admin/cash-tracking/fix-seeded-bot?username={username}&execute=true'
                )
                return jsonify({'preview': True, 'plan': preview})

            # APPLY: update user model via raw SQL (so it commits even if ORM hiccups)
            db.session.execute(text("""
                UPDATE "user"
                SET max_cash_deployed = :max_cash,
                    cash_proceeds = :cash_proc
                WHERE id = :user_id
            """), {
                'max_cash': target_max_cash,
                'cash_proc': replay_cash,
                'user_id': user.id,
            })

            # APPLY: update all historical snapshots via raw SQL UPDATE
            # (avoids ORM session edge cases that may have prevented earlier reconciles
            #  from persisting)
            snap_update_result = db.session.execute(text("""
                UPDATE portfolio_snapshot
                SET max_cash_deployed = :max_cash,
                    cash_proceeds = :cash_proc,
                    total_value = COALESCE(stock_value, 0) + :cash_proc
                WHERE user_id = :user_id
            """), {
                'max_cash': target_max_cash,
                'cash_proc': replay_cash,
                'user_id': user.id,
            })
            snapshots_updated = snap_update_result.rowcount

            db.session.commit()

            preview['snapshots_updated'] = snapshots_updated
            preview['committed'] = True
            return jsonify({'success': True, 'applied': preview})

        except Exception as e:
            db.session.rollback()
            logger.error(f"fix-seeded-bot error: {e}", exc_info=True)
            return jsonify({'error': str(e)}), 500

    def _full_rebuild_for_user(user, execute=False):
        """Run the full-rebuild logic for ONE user. Returns the preview/applied dict.

        Caller is responsible for db.session.commit() (or rollback on error). When
        called from the ?all=true loop, we commit once per user so a failure
        midway doesn't lose progress for already-corrected users.
        """
        from sqlalchemy import text
        from models import PortfolioSnapshot, PortfolioSnapshotIntraday
        from zoneinfo import ZoneInfo
        from datetime import time as _dt_time, timedelta as _td

        _MARKET_TZ = ZoneInfo('America/New_York')
        _UTC_TZ = ZoneInfo('UTC')

        def _snapshot_effective_date(ts):
            """
            For EOD daily snapshots: a transaction applies to the snapshot
            written by the next EOD cron firing AFTER the transaction commits.

            The EOD market-close cron (`5 20 * * 1-5` in vercel.json) fires at
            **20:05 UTC** every weekday. So:
              - trade at ts <  20:05 UTC on date D  -> applies to D's snapshot
                  (the cron at D's 20:05 UTC saw the committed trade)
              - trade at ts >= 20:05 UTC on date D  -> applies to D+1's snapshot
                  (the cron at D's 20:05 UTC ran before the trade committed,
                   so the trade waits for the next day's cron)

            UTC anchoring handles DST automatically (the cron always fires at
            the same UTC moment regardless of EDT/EST).

            This matches the actual behavior of the EOD market-close cron in
            `api/index.py:market_close_cron`, which:
              - reads stock_value from live `Stock` holdings (whatever state
                exists at 20:05 UTC)
              - reads cash_proceeds via replay through `today_et` (which
                includes any transaction whose UTC date <= today_et)
            For trades < 20:05 UTC, both fields reflect post-trade state.
            For trades >= 20:05 UTC, both fields reflect pre-trade state on D
            and post-trade state on D+1.

            The previous 16:00 ET cutoff was 5 minutes too early — it
            misclassified trades at 16:00-16:04 ET (which the cron at 16:05 ET
            DID see) as next-day trades, causing snapshot.cash_proceeds to
            disagree with snapshot.stock_value on after-close-sell days.
            That mismatch produced phantom chart drops.

            Intraday snapshots use TIMESTAMP-granular replay further below
            (txn_timeline + snap_ts comparison) — unaffected by this logic.
            """
            if ts is None:
                return None
            # Normalize to naive UTC for direct comparison with the cron time.
            if ts.tzinfo is not None:
                ts_utc = ts.astimezone(_UTC_TZ).replace(tzinfo=None)
            else:
                ts_utc = ts
            # Cron fires at 20:05 UTC each weekday (see vercel.json: "5 20 * * 1-5")
            cron_firing = datetime.combine(ts_utc.date(), _dt_time(20, 5))
            if ts_utc < cron_firing:
                return ts_utc.date()
            return ts_utc.date() + _td(days=1)

        # 1. Compute current cost basis from holdings
        stocks = Stock.query.filter_by(user_id=user.id).all()
        cost_basis = round(sum((s.quantity or 0) * (s.purchase_price or 0) for s in stocks), 2)

        # 2. Replay transactions chronologically; build per-date dictionaries
        # AND a per-timestamp timeline so we can do timestamp-granular replay
        # for intraday snapshots (so a 9:30 AM snapshot doesn't get the EOD
        # state of transactions that happened at 9:43 AM).
        txns = Transaction.query.filter_by(user_id=user.id).order_by(Transaction.timestamp).all()
        replay_max_cash = 0.0
        replay_cash = 0.0
        per_date_max_cash = {}
        per_date_cash = {}
        txn_timeline = []  # list of (txn_ts_naive_utc, running_max_cash, running_cash)
        buy_count = 0
        sell_count = 0
        after_close_count = 0

        def _to_naive_utc(ts):
            """Normalize aware/naive timestamps to naive UTC for direct comparison."""
            if ts is None:
                return None
            if ts.tzinfo is not None:
                return ts.astimezone(_UTC_TZ).replace(tzinfo=None)
            return ts

        for txn in txns:
            val = (txn.quantity or 0) * (txn.price or 0)
            if txn.transaction_type in ('buy', 'initial'):
                buy_count += 1
                if replay_cash >= val:
                    replay_cash -= val
                else:
                    replay_max_cash += val - replay_cash
                    replay_cash = 0
            elif txn.transaction_type in ('sell', 'dividend'):
                sell_count += 1
                replay_cash += val
            eff_date = _snapshot_effective_date(txn.timestamp)
            if eff_date:
                raw_date = txn.timestamp.date() if txn.timestamp else None
                if raw_date and eff_date != raw_date:
                    after_close_count += 1
                per_date_max_cash[eff_date] = replay_max_cash
                per_date_cash[eff_date] = replay_cash
            ts_naive = _to_naive_utc(txn.timestamp)
            if ts_naive is not None:
                txn_timeline.append((ts_naive, replay_max_cash, replay_cash))

        replay_max_cash = round(replay_max_cash, 2)
        replay_cash = round(replay_cash, 2)

        # 3. Detect seeded baseline
        first_snap = PortfolioSnapshot.query.filter_by(user_id=user.id).order_by(
            PortfolioSnapshot.date.asc()
        ).first()

        seeded_baseline = 0.0
        seeded_source = 'none'

        if first_snap:
            replay_max_at_first = 0.0
            for d in sorted(per_date_max_cash.keys()):
                if d <= first_snap.date:
                    replay_max_at_first = per_date_max_cash[d]
                else:
                    break

            first_snap_max = float(first_snap.max_cash_deployed or 0)
            if first_snap_max > replay_max_at_first + 0.01:
                seeded_baseline = round(first_snap_max - replay_max_at_first, 2)
                seeded_source = (
                    f'first_snapshot_preserved (first_snap={first_snap.date}, '
                    f'max={first_snap_max:.2f}, replay_max_at_date={replay_max_at_first:.2f})'
                )

        if seeded_baseline < 0.01:
            derived = max(0.0, cost_basis - replay_max_cash)
            if derived > 0.01:
                seeded_baseline = round(derived, 2)
                seeded_source = f'cost_basis_derived (cost_basis={cost_basis:.2f}, replay_max={replay_max_cash:.2f})'
            else:
                seeded_source = 'none (regular user, no seeded baseline)'

        target_user_max_cash = round(seeded_baseline + replay_max_cash, 2)
        target_user_cash = replay_cash

        result = {
            'username': user.username,
            'user_id': user.id,
            'transactions': len(txns),
            'buy_count': buy_count,
            'sell_count': sell_count,
            'after_close_count': after_close_count,
            'cost_basis': cost_basis,
            'replay_max_cash': replay_max_cash,
            'replay_cash_proceeds': replay_cash,
            'seeded_baseline': seeded_baseline,
            'seeded_source': seeded_source,
            'target_user_max_cash_deployed': target_user_max_cash,
            'target_user_cash_proceeds': target_user_cash,
            'current_user_max_cash_deployed': round(user.max_cash_deployed or 0, 2),
            'current_user_cash_proceeds': round(user.cash_proceeds or 0, 2),
            'snapshots_updated': 0,
            'intraday_updated': 0,
            'committed': False,
        }

        if not execute:
            result['preview'] = True
            return result

        # 4. Update user model
        db.session.execute(text("""
            UPDATE "user"
            SET max_cash_deployed = :max_cash,
                cash_proceeds = :cash_proc
            WHERE id = :user_id
        """), {
            'max_cash': target_user_max_cash,
            'cash_proc': target_user_cash,
            'user_id': user.id,
        })

        # 5. Daily snapshots
        snapshots = PortfolioSnapshot.query.filter_by(user_id=user.id).order_by(
            PortfolioSnapshot.date.asc()
        ).all()
        sorted_dates = sorted(per_date_max_cash.keys())

        def replay_at(target_date):
            rmax = 0.0
            rcash = 0.0
            for d in sorted_dates:
                if d <= target_date:
                    rmax = per_date_max_cash[d]
                    rcash = per_date_cash[d]
                else:
                    break
            return rmax, rcash

        snapshots_updated = 0
        for snap in snapshots:
            rmax, rcash = replay_at(snap.date)
            new_max = round(seeded_baseline + rmax, 2)
            new_cash = round(rcash, 2)

            upd = db.session.execute(text("""
                UPDATE portfolio_snapshot
                SET max_cash_deployed = :max_cash,
                    cash_proceeds = :cash_proc,
                    total_value = COALESCE(stock_value, 0) + :cash_proc
                WHERE user_id = :user_id
                  AND date = :snap_date
                  AND (
                      ABS(COALESCE(max_cash_deployed, 0) - :max_cash) > 0.01
                      OR ABS(COALESCE(cash_proceeds, 0) - :cash_proc) > 0.01
                      OR ABS(COALESCE(total_value, 0) - (COALESCE(stock_value, 0) + :cash_proc)) > 0.01
                  )
            """), {
                'max_cash': new_max,
                'cash_proc': new_cash,
                'user_id': user.id,
                'snap_date': snap.date,
            })
            if upd.rowcount > 0:
                snapshots_updated += 1

        # 6. Intraday snapshots — TIMESTAMP-GRANULAR replay
        #
        # The previous (buggy) version used `replay_at(snap_date)` which returned
        # the END-OF-DAY state for the snapshot's date. That meant a 9:30 AM
        # snapshot got the post-EOD values of transactions that hadn't happened
        # yet at 9:30 (e.g. trades at 9:43). The chart's Modified Dietz formula
        # then read those snapshot's max_cash_deployed as new capital deployed
        # before 9:30, producing a phantom -20% spike.
        #
        # Fix: walk transactions and snapshots in chronological order. For each
        # snapshot at timestamp T, apply only transactions with txn_ts <= T.
        intraday_snapshots = PortfolioSnapshotIntraday.query.filter_by(
            user_id=user.id
        ).order_by(PortfolioSnapshotIntraday.timestamp.asc()).all()

        intraday_updated = 0
        # txn_timeline is already sorted chronologically (insertion order).
        # Walk it via an index pointer that advances monotonically.
        timeline_idx = 0
        running_rmax = 0.0
        running_rcash = 0.0
        for isnap in intraday_snapshots:
            snap_ts = _to_naive_utc(isnap.timestamp)
            if snap_ts is None:
                continue
            # Advance the timeline pointer past every txn at or before snap_ts.
            # txn at timestamp == snap_ts is treated as "already applied" (the
            # cron at T reads user.* fields after any txn at T that committed
            # before the cron ran).
            while timeline_idx < len(txn_timeline) and txn_timeline[timeline_idx][0] <= snap_ts:
                _ts, _max, _cash = txn_timeline[timeline_idx]
                running_rmax = _max
                running_rcash = _cash
                timeline_idx += 1

            new_max = round(seeded_baseline + running_rmax, 2)
            new_cash = round(running_rcash, 2)

            upd = db.session.execute(text("""
                UPDATE portfolio_snapshot_intraday
                SET max_cash_deployed = :max_cash,
                    cash_proceeds = :cash_proc,
                    total_value = COALESCE(stock_value, 0) + :cash_proc
                WHERE id = :snap_id
                  AND (
                      ABS(COALESCE(max_cash_deployed, 0) - :max_cash) > 0.01
                      OR ABS(COALESCE(cash_proceeds, 0) - :cash_proc) > 0.01
                      OR ABS(COALESCE(total_value, 0) - (COALESCE(stock_value, 0) + :cash_proc)) > 0.01
                  )
            """), {
                'max_cash': new_max,
                'cash_proc': new_cash,
                'snap_id': isnap.id,
            })
            if upd.rowcount > 0:
                intraday_updated += 1

        result['snapshots_total'] = len(snapshots)
        result['snapshots_updated'] = snapshots_updated
        result['intraday_total'] = len(intraday_snapshots)
        result['intraday_updated'] = intraday_updated
        return result

    @app.route('/admin/cash-tracking/full-rebuild')
    @admin_required
    @with_db_retry
    def full_rebuild_cash_tracking():
        """
        Comprehensive per-date snapshot rebuild that handles seeded bots correctly.

        Single user:
          /admin/cash-tracking/full-rebuild?username=USERNAME              (preview)
          /admin/cash-tracking/full-rebuild?username=USERNAME&execute=true (apply)

        All users (use after=USERNAME to resume mid-run if Vercel times out):
          /admin/cash-tracking/full-rebuild?all=true                        (preview all)
          /admin/cash-tracking/full-rebuild?all=true&execute=true           (apply all)
          /admin/cash-tracking/full-rebuild?all=true&role=agent&execute=true (bots only)
          /admin/cash-tracking/full-rebuild?all=true&after=foo&execute=true (resume after user 'foo')

        Behavior:
          - Replays all transactions chronologically
          - Daily snapshots: trades on date D apply to D's snapshot
            (Option B — matches EOD market-close cron's `func.date(timestamp)
            <= target_date` filter and the live-Stock-holdings basis for
            stock_value, so both fields are consistent post-trade state)
          - Intraday snapshots: timestamp-granular replay (a snapshot at T
            includes only transactions whose timestamp <= T)
          - Detects seeded baseline (preserved or cost_basis-derived)
          - Updates user.max_cash_deployed and user.cash_proceeds
          - Updates ALL daily AND intraday snapshots to match
          - Idempotent: only writes rows where values actually differ
        """
        import time as _t
        username = request.args.get('username')
        do_all = request.args.get('all') == 'true'
        role_filter = request.args.get('role')
        after_username = request.args.get('after')
        execute = request.args.get('execute') == 'true'

        if not username and not do_all:
            return jsonify({'error': 'username or all=true required'}), 400

        # Single-user path
        if username:
            try:
                user = User.query.filter_by(username=username).first()
                if not user:
                    return jsonify({'error': f'User {username} not found'}), 404
                result = _full_rebuild_for_user(user, execute=execute)
                if execute:
                    db.session.commit()
                    result['committed'] = True
                    return jsonify({'success': True, 'applied': result})
                else:
                    result['execute_url'] = (
                        f'/admin/cash-tracking/full-rebuild?username={username}&execute=true'
                    )
                    return jsonify({'preview': True, 'plan': result})
            except Exception as e:
                db.session.rollback()
                logger.error(f"full-rebuild error: {e}", exc_info=True)
                return jsonify({'error': str(e)}), 500

        # All-users path (?all=true)
        try:
            q = User.query.order_by(User.username.asc())
            if role_filter:
                q = q.filter(User.role == role_filter)
            if after_username:
                q = q.filter(User.username > after_username)

            users = q.all()
            start = _t.time()
            timeout_seconds = 50  # leave 10s buffer before Vercel 60s kill

            results = []
            users_with_changes = 0
            users_without_changes = 0
            users_with_drift_only = 0  # preview mode: had changes if executed
            errors = []
            stopped_early = False
            last_username_processed = None

            for user in users:
                if _t.time() - start > timeout_seconds:
                    stopped_early = True
                    break
                try:
                    res = _full_rebuild_for_user(user, execute=execute)
                    last_username_processed = user.username

                    if execute:
                        # Drift exists if user values changed OR any snapshots updated
                        had_changes = (
                            abs(res['target_user_max_cash_deployed'] - res['current_user_max_cash_deployed']) > 0.01
                            or abs(res['target_user_cash_proceeds'] - res['current_user_cash_proceeds']) > 0.01
                            or res['snapshots_updated'] > 0
                            or res['intraday_updated'] > 0
                        )
                        if had_changes:
                            users_with_changes += 1
                            db.session.commit()
                            res['committed'] = True
                            # Only include changed users in detailed results to keep response small
                            results.append({
                                'username': res['username'],
                                'user_id': res['user_id'],
                                'snapshots_updated': res['snapshots_updated'],
                                'intraday_updated': res['intraday_updated'],
                                'after_close_count': res['after_close_count'],
                                'seeded_source': res['seeded_source'],
                                'max_cash_drift': round(
                                    res['target_user_max_cash_deployed'] - res['current_user_max_cash_deployed'], 2
                                ),
                                'cash_proceeds_drift': round(
                                    res['target_user_cash_proceeds'] - res['current_user_cash_proceeds'], 2
                                ),
                            })
                        else:
                            users_without_changes += 1
                            db.session.rollback()  # nothing to commit, clear session
                    else:
                        # Preview: detect drift without writing
                        max_drift = abs(res['target_user_max_cash_deployed'] - res['current_user_max_cash_deployed'])
                        cash_drift = abs(res['target_user_cash_proceeds'] - res['current_user_cash_proceeds'])
                        if max_drift > 0.01 or cash_drift > 0.01:
                            users_with_drift_only += 1
                            results.append({
                                'username': res['username'],
                                'user_id': res['user_id'],
                                'transactions': res['transactions'],
                                'after_close_count': res['after_close_count'],
                                'seeded_source': res['seeded_source'],
                                'current_max_cash': res['current_user_max_cash_deployed'],
                                'target_max_cash': res['target_user_max_cash_deployed'],
                                'current_cash_proceeds': res['current_user_cash_proceeds'],
                                'target_cash_proceeds': res['target_user_cash_proceeds'],
                                'max_cash_drift': round(
                                    res['target_user_max_cash_deployed'] - res['current_user_max_cash_deployed'], 2
                                ),
                                'cash_proceeds_drift': round(
                                    res['target_user_cash_proceeds'] - res['current_user_cash_proceeds'], 2
                                ),
                            })
                except Exception as ue:
                    db.session.rollback()
                    logger.error(f"full-rebuild user {user.username}: {ue}", exc_info=True)
                    errors.append({'username': user.username, 'error': str(ue)})

            elapsed = round(_t.time() - start, 2)
            response = {
                'success': True,
                'mode': 'all',
                'execute': execute,
                'role_filter': role_filter,
                'after': after_username,
                'users_total': len(users),
                'users_processed': (users_with_changes + users_without_changes
                                    if execute else users_with_drift_only +
                                    (len(users) - users_with_drift_only)),
                'users_with_changes': users_with_changes if execute else users_with_drift_only,
                'users_without_changes': users_without_changes if execute else None,
                'errors': errors,
                'elapsed_seconds': elapsed,
                'stopped_early': stopped_early,
                'last_username_processed': last_username_processed,
                'results': results,
            }
            if stopped_early and last_username_processed:
                resume_url = f'/admin/cash-tracking/full-rebuild?all=true&after={last_username_processed}'
                if execute:
                    resume_url += '&execute=true'
                if role_filter:
                    resume_url += f'&role={role_filter}'
                response['resume_url'] = resume_url
            return jsonify(response)
        except Exception as e:
            db.session.rollback()
            logger.error(f"full-rebuild all-users error: {e}", exc_info=True)
            return jsonify({'error': str(e)}), 500

    @app.route('/admin/cash-tracking/drift-check', methods=['GET', 'POST'])
    @app.route('/api/cron/drift-check', methods=['GET', 'POST'])
    @with_db_retry
    def drift_check_cash_tracking():
        """
        Detect drift between user.max_cash_deployed/cash_proceeds and replay-derived
        target values across all users. Sends an email alert if drift is detected.

        Auth (one of):
          - Cron secret header: Authorization: Bearer $CRON_SECRET   (for Vercel cron)
          - Admin session   (browser navigation by admin)

        Query params:
          ?email=true       Send email alert if drift found (default for cron path)
          ?email=false      Skip email (default for /admin/... path)
          ?threshold=10.00  Min |drift| in $ to consider significant (default 1.00)
          ?role=agent       Restrict to bot accounts only

        Response includes a `prompt` field — a copy-pasteable string you can hand
        to me to investigate. Includes affected usernames, drift amounts, and
        suggested URLs to fix.
        """
        import os as _os
        from flask import session as _flask_session
        from sqlalchemy import text

        # ---- Auth ----
        # Cron path: verify CRON_SECRET.
        # Admin path: require admin email (case-insensitive) AND 2FA flag.
        # This matches cron_snapshot_audit's posture — same endpoint class,
        # same auth contract. Without the 2FA check a partially-authenticated
        # admin session could disclose drift data, trigger the admin email
        # alert, and write to admin.extra_data.
        is_cron_path = request.path.startswith('/api/cron/')
        if is_cron_path:
            cron_secret = _os.environ.get('CRON_SECRET', '')
            auth_header = request.headers.get('Authorization', '')
            provided = auth_header.replace('Bearer ', '').strip() if auth_header else ''
            if not cron_secret or provided != cron_secret:
                return jsonify({'error': 'unauthorized'}), 401
        else:
            admin_email = _os.environ.get('ADMIN_EMAIL', 'admin@apestogether.ai')
            session_email = _flask_session.get('email', '')
            # Fall back to current_user.email when session.email is empty
            # (Flask-Login OAuth flows sometimes don't populate session['email']).
            if not session_email:
                try:
                    from flask_login import current_user as _cu
                    if _cu and _cu.is_authenticated:
                        session_email = getattr(_cu, 'email', '') or ''
                except Exception:
                    session_email = ''
            if session_email.lower() != admin_email.lower():
                return jsonify({'error': 'admin_access_required'}), 403
            if not _flask_session.get('admin_2fa_verified'):
                return jsonify({
                    'error': '2fa_required',
                    'message': 'Complete 2FA at /admin-panel before triggering drift-check.',
                }), 401

        # ---- Params ----
        send_email = request.args.get('email', 'true' if is_cron_path else 'false') == 'true'
        try:
            threshold = float(request.args.get('threshold', '1.00'))
        except (TypeError, ValueError):
            threshold = 1.00
        role_filter = request.args.get('role')

        from zoneinfo import ZoneInfo
        from datetime import time as _dt_time, timedelta as _td

        _MARKET_TZ = ZoneInfo('America/New_York')
        _UTC_TZ = ZoneInfo('UTC')

        def _eff_date(ts):
            if ts is None:
                return None
            ts_et = (ts.replace(tzinfo=_UTC_TZ) if ts.tzinfo is None else ts).astimezone(_MARKET_TZ)
            if ts_et.time() >= _dt_time(16, 0):
                return ts_et.date() + _td(days=1)
            return ts_et.date()

        # ---- Query users ----
        try:
            q = User.query.order_by(User.username.asc())
            if role_filter:
                q = q.filter(User.role == role_filter)
            users = q.all()

            drift_users = []
            scanned = 0
            skipped_copytrade = 0

            try:
                from mobile_api import _is_copytrade_bot
            except Exception:
                def _is_copytrade_bot(_u):
                    return False

            for user in users:
                # Copytrade bots (CoastHillBear, marblethehill72) derive cash/holdings
                # from brokerage-screenshot migrations (price_source='phase_c_migration')
                # that a transaction replay cannot reproduce, so they always show
                # false-positive drift. Skip them so alerts stay trustworthy.
                if _is_copytrade_bot(user):
                    skipped_copytrade += 1
                    continue
                txns = Transaction.query.filter_by(user_id=user.id).order_by(Transaction.timestamp).all()
                if not txns:
                    continue  # users with no transactions can't drift
                scanned += 1

                replay_max_cash = 0.0
                replay_cash = 0.0
                for txn in txns:
                    val = (txn.quantity or 0) * (txn.price or 0)
                    if txn.transaction_type in ('buy', 'initial'):
                        if replay_cash >= val:
                            replay_cash -= val
                        else:
                            replay_max_cash += val - replay_cash
                            replay_cash = 0
                    elif txn.transaction_type in ('sell', 'dividend'):
                        replay_cash += val

                # Detect seeded baseline (same logic as full-rebuild)
                first_snap = PortfolioSnapshot.query.filter_by(user_id=user.id).order_by(
                    PortfolioSnapshot.date.asc()
                ).first()
                seeded_baseline = 0.0
                if first_snap:
                    fsm = float(first_snap.max_cash_deployed or 0)
                    # Replay max at first snapshot date
                    rmf = 0.0
                    rcf = 0.0
                    for txn in txns:
                        eff = _eff_date(txn.timestamp)
                        if eff and eff > first_snap.date:
                            break
                        v = (txn.quantity or 0) * (txn.price or 0)
                        if txn.transaction_type in ('buy', 'initial'):
                            if rcf >= v:
                                rcf -= v
                            else:
                                rmf += v - rcf
                                rcf = 0
                        elif txn.transaction_type in ('sell', 'dividend'):
                            rcf += v
                    if fsm > rmf + 0.01:
                        seeded_baseline = round(fsm - rmf, 2)

                if seeded_baseline < 0.01:
                    stocks = Stock.query.filter_by(user_id=user.id).all()
                    cb = sum((s.quantity or 0) * (s.purchase_price or 0) for s in stocks)
                    derived = max(0.0, cb - replay_max_cash)
                    if derived > 0.01:
                        seeded_baseline = round(derived, 2)

                target_max = round(seeded_baseline + replay_max_cash, 2)
                target_cash = round(replay_cash, 2)
                cur_max = round(user.max_cash_deployed or 0, 2)
                cur_cash = round(user.cash_proceeds or 0, 2)

                max_drift = round(target_max - cur_max, 2)
                cash_drift = round(target_cash - cur_cash, 2)

                if abs(max_drift) >= threshold or abs(cash_drift) >= threshold:
                    drift_users.append({
                        'username': user.username,
                        'user_id': user.id,
                        'role': user.role,
                        'transactions': len(txns),
                        'current_max_cash': cur_max,
                        'target_max_cash': target_max,
                        'max_cash_drift': max_drift,
                        'current_cash_proceeds': cur_cash,
                        'target_cash_proceeds': target_cash,
                        'cash_drift': cash_drift,
                        'seeded_baseline': seeded_baseline,
                        'fix_url': f'/admin/cash-tracking/full-rebuild?username={user.username}&execute=true',
                    })

            # ---- Build prompt-ready summary ----
            timestamp_str = datetime.now(ZoneInfo('America/New_York')).strftime('%Y-%m-%d %H:%M ET')
            if drift_users:
                prompt_lines = [
                    f"# Cash-tracking drift detected ({len(drift_users)} users) — {timestamp_str}",
                    f"# Threshold: ${threshold:.2f}",
                    "",
                    "Users with drift (paste this to your AI assistant for investigation):",
                    "",
                ]
                for d in drift_users:
                    prompt_lines.append(
                        f"- {d['username']} (id={d['user_id']}, role={d['role']}, txns={d['transactions']}): "
                        f"max_cash_drift=${d['max_cash_drift']:.2f}, cash_drift=${d['cash_drift']:.2f}"
                    )
                prompt_lines.append("")
                prompt_lines.append("To fix all in one shot:")
                prompt_lines.append("  GET /admin/cash-tracking/full-rebuild?all=true&execute=true")
                prompt_lines.append("")
                prompt_lines.append("To fix individually:")
                for d in drift_users[:10]:
                    prompt_lines.append(f"  GET https://apestogether.ai{d['fix_url']}")
                if len(drift_users) > 10:
                    prompt_lines.append(f"  ... and {len(drift_users) - 10} more (see full list above)")
                prompt = '\n'.join(prompt_lines)
            else:
                prompt = f"# No drift detected ({timestamp_str}) — {scanned} users scanned, all clean."

            response = {
                'success': True,
                'timestamp': timestamp_str,
                'users_scanned': scanned,
                'copytrade_bots_skipped': skipped_copytrade,
                'drift_count': len(drift_users),
                'threshold': threshold,
                'drift_users': drift_users,
                'prompt': prompt,
            }

            # ---- Persist last drift-check result on admin user (no SMTP required) ----
            # Uses raw SQL with jsonb_set rather than the SQLAlchemy ORM.
            # Three reasons:
            #   1. The codebase has TWO separate SQLAlchemy instances bound
            #      to the same DB — `models.db` (from models.py) and the
            #      one created in api/index.py. `models.User` rows are
            #      tracked by `models.db.session`, but
            #      register_cash_tracking_routes(app, db) is called with
            #      api/index.py's db. So a `db.session.commit()` inside
            #      this closure commits the WRONG session and the change
            #      to `admin.extra_data` is silently dropped. Witnessed:
            #      writer reported persisted=true with the new key in
            #      `post_commit_extra_data_keys`, but the next request's
            #      read showed pre_existing_extra_data_keys still missing
            #      that key.
            #   2. Atomic merge: jsonb_set on the row eliminates the
            #      read-modify-write race where two writers (drift-check
            #      and snapshot-audit) clobber each other's keys.
            #   3. Raw SQL goes straight to the DB connection regardless
            #      of which SQLAlchemy instance is in scope, so this
            #      works no matter how the route is registered.
            try:
                from sqlalchemy import text as _sql_text
                import json as _json_lib
                admin = _find_admin_user_for_persistence()
                if admin:
                    payload = {
                        'timestamp': timestamp_str,
                        'users_scanned': scanned,
                        'drift_count': len(drift_users),
                        'threshold': threshold,
                        'drift_users': drift_users,
                        'prompt': prompt,
                    }
                    db.session.execute(_sql_text("""
                        UPDATE "user"
                        SET metadata = jsonb_set(
                            COALESCE(metadata::jsonb, '{}'::jsonb),
                            '{last_drift_check}',
                            CAST(:payload AS jsonb)
                        )
                        WHERE id = :user_id
                    """), {
                        'payload': _json_lib.dumps(payload),
                        'user_id': admin.id,
                    })
                    db.session.commit()
                    response['persisted'] = True
                    response['persisted_user_id'] = admin.id
                else:
                    response['persisted'] = False
                    response['persisted_error'] = 'admin_user_not_found'
            except Exception as pe:
                logger.warning(f"Could not persist drift-check result: {pe}", exc_info=True)
                response['persisted'] = False
                response['persisted_error'] = str(pe)
                try:
                    db.session.rollback()
                except Exception:
                    pass

            # ---- Email if drift found ----
            if drift_users and send_email:
                try:
                    import smtplib
                    from email.mime.text import MIMEText

                    notify_email = _os.environ.get('ADMIN_NOTIFY_EMAIL', 'bobford00@gmail.com')
                    smtp_user = _os.environ.get('SMTP_USER')
                    smtp_pass = _os.environ.get('SMTP_PASS')

                    if smtp_user and smtp_pass:
                        body = (
                            f"Cash-tracking drift detected on {timestamp_str}.\n\n"
                            f"{len(drift_users)} of {scanned} users have drift > ${threshold:.2f} "
                            f"between user.max_cash_deployed/cash_proceeds and replay-derived "
                            f"target values.\n\n"
                            "===== Prompt-ready summary (paste to AI) =====\n\n"
                            f"{prompt}\n\n"
                            "===== Full JSON =====\n"
                            f"{drift_users}\n"
                        )
                        msg = MIMEText(body)
                        msg['Subject'] = f'[ApesTogether] Cash-tracking drift: {len(drift_users)} users affected'
                        msg['From'] = smtp_user
                        msg['To'] = notify_email

                        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
                            server.login(smtp_user, smtp_pass)
                            server.send_message(msg)
                        response['email_sent'] = True
                        logger.info(f"Drift alert email sent to {notify_email}: {len(drift_users)} users")
                    else:
                        response['email_sent'] = False
                        response['email_error'] = 'SMTP not configured'
                        logger.warning("Drift detected but SMTP_USER/SMTP_PASS not set")
                except Exception as ee:
                    response['email_sent'] = False
                    response['email_error'] = str(ee)
                    logger.error(f"Failed to send drift email: {ee}")

            return jsonify(response)
        except Exception as e:
            logger.error(f"drift-check error: {e}", exc_info=True)
            return jsonify({'error': str(e)}), 500

    @app.route('/admin/cash-tracking/inspect-snapshots')
    @admin_required
    def inspect_snapshots():
        """Dump daily + intraday snapshots for a user over the last N days.

        Useful for diagnosing chart anomalies (data spikes, missing points,
        max_cash_deployed jumps, etc.).

        Usage:
          /admin/cash-tracking/inspect-snapshots?username=USER             (last 7 days)
          /admin/cash-tracking/inspect-snapshots?username=USER&days=14     (last 14 days)
          /admin/cash-tracking/inspect-snapshots?username=USER&date=2026-05-04   (just one day)

        Response:
          - user: current max_cash_deployed and cash_proceeds
          - daily_snapshots: every daily snapshot in window with all fields
          - intraday_snapshots: every intraday snapshot in window (ET-converted)
          - anomalies: pairs of consecutive intraday snapshots with > 5% total_value swing
          - transactions: any transactions in window
        """
        from datetime import datetime as _dt, date as _date, time as _t, timedelta as _td
        from zoneinfo import ZoneInfo as _ZI
        from models import PortfolioSnapshot, PortfolioSnapshotIntraday, Transaction

        username = request.args.get('username')
        if not username:
            return jsonify({'error': 'username required'}), 400

        try:
            days = int(request.args.get('days', '7'))
        except (TypeError, ValueError):
            days = 7

        single_date_str = request.args.get('date')
        single_date = None
        if single_date_str:
            try:
                single_date = _dt.strptime(single_date_str, '%Y-%m-%d').date()
            except ValueError:
                return jsonify({'error': 'date must be YYYY-MM-DD'}), 400

        user = User.query.filter_by(username=username).first()
        if not user:
            return jsonify({'error': f'user {username} not found'}), 404

        ET = _ZI('America/New_York')
        UTC = _ZI('UTC')

        # Determine date window
        today_et = _dt.now(ET).date()
        if single_date:
            start_date = single_date
            end_date = single_date
        else:
            end_date = today_et
            start_date = end_date - _td(days=days)

        # 1. Daily snapshots
        daily_q = PortfolioSnapshot.query.filter(
            PortfolioSnapshot.user_id == user.id,
            PortfolioSnapshot.date >= start_date,
            PortfolioSnapshot.date <= end_date,
        ).order_by(PortfolioSnapshot.date.asc()).all()

        daily_rows = []
        prev_total = None
        prev_max_cash_d = None
        for s in daily_q:
            tot = float(s.total_value or 0)
            stock = float(s.stock_value or 0)
            cash = float(s.cash_proceeds or 0)
            max_cash = float(s.max_cash_deployed or 0)
            pct_change = None
            capital_change = None
            if prev_total and prev_total > 0:
                # Capital-deployment-aware pct change: subtract any new capital
                # deployed between snapshots from the value delta, so the metric
                # reflects ONLY market-driven movement (not cash injections).
                cap_delta = max_cash - (prev_max_cash_d or 0.0)
                capital_change = round(cap_delta, 2)
                pct_change = round((tot - prev_total - cap_delta) / prev_total * 100, 2)
            daily_rows.append({
                'date': s.date.isoformat(),
                'total_value': round(tot, 2),
                'stock_value': round(stock, 2),
                'cash_proceeds': round(cash, 2),
                'max_cash_deployed': round(max_cash, 2),
                'sum_check': round(stock + cash - tot, 2),  # Should be 0
                'pct_change_from_prev_day': pct_change,
                'capital_deployed_since_prev': capital_change,
            })
            prev_total = tot
            prev_max_cash_d = max_cash

        # 2. Intraday snapshots
        start_dt = _dt.combine(start_date, _t.min)
        end_dt = _dt.combine(end_date, _t.max)

        intraday_q = PortfolioSnapshotIntraday.query.filter(
            PortfolioSnapshotIntraday.user_id == user.id,
            PortfolioSnapshotIntraday.timestamp >= start_dt,
            PortfolioSnapshotIntraday.timestamp <= end_dt,
        ).order_by(PortfolioSnapshotIntraday.timestamp.asc()).all()

        intraday_rows = []
        anomalies = []
        prev_tot = None
        prev_ts_et = None
        prev_max_cash_i = None
        for s in intraday_q:
            ts = s.timestamp
            ts_et = (ts.replace(tzinfo=UTC) if ts.tzinfo is None else ts).astimezone(ET)
            tot = float(s.total_value or 0)
            stock = float(s.stock_value or 0)
            cash = float(s.cash_proceeds or 0)
            max_cash = float(s.max_cash_deployed or 0)

            pct_change = None
            capital_change = None
            if prev_tot and prev_tot > 0:
                # Capital-deployment-aware pct change: subtract any new capital
                # deployed between snapshots from the value delta, so the metric
                # reflects ONLY market-driven movement. A 23% jump caused by a
                # mid-day capital injection should NOT be flagged as an anomaly.
                cap_delta = max_cash - (prev_max_cash_i or 0.0)
                capital_change = round(cap_delta, 2)
                pct_change = round((tot - prev_tot - cap_delta) / prev_tot * 100, 2)
                if abs(pct_change) >= 5.0:
                    anomalies.append({
                        'from': prev_ts_et.strftime('%Y-%m-%d %H:%M ET') if prev_ts_et else None,
                        'to': ts_et.strftime('%Y-%m-%d %H:%M ET'),
                        'prev_total': round(prev_tot, 2),
                        'curr_total': round(tot, 2),
                        'capital_deployed_between': capital_change,
                        'pct_change_market_only': pct_change,
                        'curr_stock_value': round(stock, 2),
                        'curr_cash_proceeds': round(cash, 2),
                    })

            intraday_rows.append({
                'ts_et': ts_et.strftime('%Y-%m-%d %H:%M ET'),
                'date_et': ts_et.date().isoformat(),
                'time_et': ts_et.strftime('%H:%M'),
                'total_value': round(tot, 2),
                'stock_value': round(stock, 2),
                'cash_proceeds': round(cash, 2),
                'max_cash_deployed': round(max_cash, 2),
                'sum_check': round(stock + cash - tot, 2),
                'pct_change_from_prev': pct_change,
                'capital_deployed_since_prev': capital_change,
            })
            prev_tot = tot
            prev_ts_et = ts_et
            prev_max_cash_i = max_cash

        # Coverage analysis: count intraday per ET date
        coverage = {}
        for r in intraday_rows:
            coverage[r['date_et']] = coverage.get(r['date_et'], 0) + 1

        # 3. Transactions in window
        txn_q = Transaction.query.filter(
            Transaction.user_id == user.id,
            Transaction.timestamp >= start_dt,
            Transaction.timestamp <= end_dt,
        ).order_by(Transaction.timestamp.asc()).all()

        txn_rows = []
        for t in txn_q:
            ts = t.timestamp
            ts_et = (ts.replace(tzinfo=UTC) if ts.tzinfo is None else ts).astimezone(ET)
            txn_rows.append({
                'ts_et': ts_et.strftime('%Y-%m-%d %H:%M ET'),
                'type': t.transaction_type,
                'ticker': t.ticker,
                'quantity': float(t.quantity or 0),
                'price': float(t.price or 0),
                'value': round(float(t.quantity or 0) * float(t.price or 0), 2),
            })

        return jsonify({
            'user': {
                'username': user.username,
                'id': user.id,
                'role': user.role,
                'max_cash_deployed': round(float(user.max_cash_deployed or 0), 2),
                'cash_proceeds': round(float(user.cash_proceeds or 0), 2),
            },
            'window': {
                'start': start_date.isoformat(),
                'end': end_date.isoformat(),
                'today_et': today_et.isoformat(),
            },
            'counts': {
                'daily': len(daily_rows),
                'intraday': len(intraday_rows),
                'transactions': len(txn_rows),
                'anomalies_5pct': len(anomalies),
            },
            'intraday_coverage_per_day': coverage,
            'anomalies': anomalies,
            'transactions': txn_rows,
            'daily_snapshots': daily_rows,
            'intraday_snapshots': intraday_rows,
        })

    @app.route('/admin/cash-tracking/last-drift-check')
    @admin_required
    def last_drift_check():
        """Return the most recently persisted drift-check result.

        The weekly cron writes its result to admin.extra_data['last_drift_check'].
        This endpoint reads it back so you can see the drift status without
        needing SMTP configured. The 'prompt' field is paste-ready for me.

        Uses _find_admin_user_for_persistence so the reader looks at the same
        User row the writer wrote to. Previously a casing mismatch between the
        DB and ADMIN_EMAIL could make this endpoint report 'never run' even
        after a successful drift-check run.
        """
        admin = _find_admin_user_for_persistence()
        if not admin:
            return jsonify({
                'error': 'admin user not found',
                'hint': 'No User row matches the ADMIN_EMAIL env var. Check ADMIN_EMAIL on Vercel matches the admin User.email exactly (case-sensitive lookup falls back to case-insensitive).',
            }), 404
        result = (admin.extra_data or {}).get('last_drift_check')
        if not result:
            return jsonify({
                'never_run': True,
                'hint': 'Run /admin/cash-tracking/drift-check first to populate.',
            })
        return jsonify(result)

    @app.route('/admin/cash-tracking/backfill-users')
    @admin_required
    def backfill_user_cash():
        """Backfill max_cash_deployed and cash_proceeds for all users"""
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
            logger.error(f"Cash tracking error: {e}", exc_info=True)
            return jsonify({'error': str(e)}), 500
