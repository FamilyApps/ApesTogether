"""
Admin routes for Phase 5: Delete Invalid Snapshots & Re-backfill

These routes handle cleanup of snapshots created with current prices
and re-creation with proper historical prices.
"""

from flask import jsonify, request
from flask_login import login_required, current_user
from models import User, PortfolioSnapshot
from datetime import datetime, date
from sqlalchemy import text
import logging

logger = logging.getLogger(__name__)

def register_phase_5_routes(app, db):
    """Register Phase 5 cleanup and re-backfill routes"""
    
    @app.route('/admin/phase5/delete-invalid-snapshots')
    @login_required
    def delete_invalid_snapshots():
        """Delete all snapshots that were created with current prices instead of historical"""
        if not current_user.is_admin:
            return jsonify({'error': 'Admin access required'}), 403
        
        execute = request.args.get('execute') == 'true'
        
        try:
            from portfolio_performance import get_market_date
            
            today = get_market_date()
            
            # Get all users
            users_result = db.session.execute(text("""
                SELECT id, username FROM "user" WHERE max_cash_deployed > 0 ORDER BY username
            """))
            
            results = []
            total_deleted = 0
            
            for user_row in users_result:
                # Count snapshots before today (these were created with historical backfill but used current prices)
                count_result = db.session.execute(text("""
                    SELECT COUNT(*) as count,
                           MIN(date) as earliest,
                           MAX(date) as latest
                    FROM portfolio_snapshot
                    WHERE user_id = :user_id AND date < :today
                """), {'user_id': user_row.id, 'today': today})
                count_row = count_result.fetchone()
                
                snapshot_count = count_row.count if count_row else 0
                
                if snapshot_count == 0:
                    results.append({
                        'username': user_row.username,
                        'action': 'none',
                        'reason': 'No historical snapshots to delete'
                    })
                    continue
                
                if execute:
                    # Delete all snapshots before today
                    db.session.execute(text("""
                        DELETE FROM portfolio_snapshot
                        WHERE user_id = :user_id AND date < :today
                    """), {'user_id': user_row.id, 'today': today})
                    db.session.commit()
                    action = 'deleted'
                else:
                    action = 'would_delete'
                
                results.append({
                    'username': user_row.username,
                    'snapshots_affected': snapshot_count,
                    'action': action,
                    'date_range': {
                        'earliest': count_row.earliest.isoformat() if count_row and count_row.earliest else None,
                        'latest': count_row.latest.isoformat() if count_row and count_row.latest else None
                    } if count_row and count_row.earliest else None
                })
                
                total_deleted += snapshot_count
            
            return jsonify({
                'success': True,
                'executed': execute,
                'users_processed': len(results),
                'total_snapshots_affected': total_deleted,
                'details': results,
                'message': f'{"Deleted" if execute else "Would delete"} {total_deleted} invalid snapshots (created with current prices)',
                'execute_url': '/admin/phase5/delete-invalid-snapshots?execute=true'
            })
            
        except Exception as e:
            db.session.rollback()
            import traceback
            return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500
    
    @app.route('/admin/phase5/status')
    @login_required
    def phase5_status():
        """Show current status of historical data quality"""
        if not current_user.is_admin:
            return jsonify({'error': 'Admin access required'}), 403
        
        try:
            from portfolio_performance import get_market_date
            
            today = get_market_date()
            
            # Get all users with snapshot counts
            users_result = db.session.execute(text("""
                SELECT u.id, u.username,
                       COUNT(ps.id) as total_snapshots,
                       COUNT(CASE WHEN ps.date < :today THEN 1 END) as historical_snapshots,
                       COUNT(CASE WHEN ps.date >= :today THEN 1 END) as current_snapshots,
                       MIN(ps.date) as earliest_snapshot,
                       MAX(ps.date) as latest_snapshot
                FROM "user" u
                LEFT JOIN portfolio_snapshot ps ON ps.user_id = u.id
                WHERE u.max_cash_deployed > 0
                GROUP BY u.id, u.username
                ORDER BY u.username
            """), {'today': today})
            
            results = []
            total_historical = 0
            
            for row in users_result:
                # Get first transaction date
                first_txn_result = db.session.execute(text("""
                    SELECT MIN(DATE(timestamp)) as first_date
                    FROM stock_transaction
                    WHERE user_id = :user_id
                """), {'user_id': row.id})
                first_txn_row = first_txn_result.fetchone()
                first_date = first_txn_row.first_date if first_txn_row else None
                
                # Calculate coverage
                if first_date and row.latest_snapshot:
                    total_days = (row.latest_snapshot - first_date).days + 1
                    weekdays = int(total_days * 5 / 7)  # Rough estimate
                    coverage_pct = (row.total_snapshots / weekdays * 100) if weekdays > 0 else 0
                else:
                    coverage_pct = 0
                
                results.append({
                    'username': row.username,
                    'first_transaction': first_date.isoformat() if first_date else None,
                    'snapshots': {
                        'total': row.total_snapshots or 0,
                        'historical': row.historical_snapshots or 0,
                        'current': row.current_snapshots or 0
                    },
                    'date_range': {
                        'earliest': row.earliest_snapshot.isoformat() if row.earliest_snapshot else None,
                        'latest': row.latest_snapshot.isoformat() if row.latest_snapshot else None
                    },
                    'coverage_percent': round(coverage_pct, 1),
                    'status': '✅ Ready' if row.current_snapshots and not row.historical_snapshots else '⚠️ Has Invalid Historical Data'
                })
                
                total_historical += (row.historical_snapshots or 0)
            
            return jsonify({
                'success': True,
                'today': today.isoformat(),
                'summary': {
                    'total_invalid_snapshots': total_historical,
                    'users_with_invalid_data': len([r for r in results if r['snapshots']['historical'] > 0])
                },
                'users': results,
                'next_steps': [
                    'Delete invalid historical snapshots: /admin/phase5/delete-invalid-snapshots?execute=true',
                    'Re-backfill with historical prices: /admin/phase4/dashboard'
                ]
            })
            
        except Exception as e:
            import traceback
            return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500
    
    @app.route('/admin/phase5/historical-prices-dashboard')
    @login_required
    def historical_prices_dashboard():
        """Dashboard for fetching historical prices with per-ticker control"""
        if not current_user.is_admin:
            return jsonify({'error': 'Admin access required'}), 403
        
        from flask import render_template
        return render_template('admin_historical_prices_dashboard.html')
    
    @app.route('/admin/phase5/fetch-historical-prices')
    @login_required
    def fetch_historical_prices_route():
        """Fetch historical prices for all tickers to populate MarketData cache"""
        if not current_user.is_admin:
            return jsonify({'error': 'Admin access required'}), 403
        
        execute = request.args.get('execute') == 'true'
        single_ticker = request.args.get('ticker')  # Optional: fetch single ticker
        
        try:
            from portfolio_performance import PortfolioPerformanceCalculator, get_market_date
            from models import Transaction, MarketData
            from datetime import timedelta
            
            # Get date range
            end_date = get_market_date()
            
            earliest_result = db.session.execute(text("""
                SELECT MIN(DATE(timestamp)) as earliest
                FROM stock_transaction
            """))
            earliest_row = earliest_result.fetchone()
            start_date = earliest_row.earliest if earliest_row and earliest_row.earliest else end_date - timedelta(days=120)
            
            # Get unique tickers
            if single_ticker:
                tickers = [single_ticker.upper()]
            else:
                tickers_result = db.session.execute(text("""
                    SELECT DISTINCT ticker FROM stock_transaction ORDER BY ticker
                """))
                tickers = [row.ticker.upper() for row in tickers_result]
            
            if not tickers:
                return jsonify({'error': 'No tickers found'}), 404
            
            results = []
            
            for ticker in tickers:
                cached_count = MarketData.query.filter(
                    MarketData.ticker == ticker,
                    MarketData.date >= start_date,
                    MarketData.date <= end_date
                ).count()
                
                days_span = (end_date - start_date).days
                already_cached = cached_count >= days_span * 0.7
                
                if already_cached:
                    results.append({
                        'ticker': ticker,
                        'status': 'cached',
                        'cached_days': cached_count,
                        'message': f'Already have {cached_count} days'
                    })
                    continue
                
                if execute:
                    try:
                        calculator = PortfolioPerformanceCalculator()
                        # Force fetch to populate ALL dates even if some exist
                        price = calculator.get_historical_price(ticker, start_date, force_fetch=True)
                        
                        if price:
                            new_cached_count = MarketData.query.filter(
                                MarketData.ticker == ticker,
                                MarketData.date >= start_date,
                                MarketData.date <= end_date
                            ).count()
                            
                            results.append({
                                'ticker': ticker,
                                'status': 'fetched',
                                'cached_days': new_cached_count,
                                'message': f'Fetched {new_cached_count} days'
                            })
                        else:
                            results.append({
                                'ticker': ticker,
                                'status': 'error',
                                'message': 'API returned no data'
                            })
                    except Exception as e:
                        results.append({
                            'ticker': ticker,
                            'status': 'error',
                            'message': str(e)
                        })
                else:
                    results.append({
                        'ticker': ticker,
                        'status': 'will_fetch',
                        'cached_days': cached_count,
                        'message': f'Need to fetch (have {cached_count}/{days_span} days)'
                    })
            
            return jsonify({
                'success': True,
                'executed': execute,
                'date_range': {
                    'start': start_date.isoformat(),
                    'end': end_date.isoformat(),
                    'days': (end_date - start_date).days
                },
                'tickers': len(tickers),
                'results': results,
                'summary': {
                    'cached': len([r for r in results if r['status'] == 'cached']),
                    'fetched': len([r for r in results if r['status'] == 'fetched']),
                    'errors': len([r for r in results if r['status'] == 'error']),
                    'will_fetch': len([r for r in results if r['status'] == 'will_fetch'])
                },
                'execute_url': '/admin/phase5/fetch-historical-prices?execute=true',
                'note': 'With 150 calls/min limit, can fetch prices for all tickers in under 1 minute. Each call fetches 100+ days.'
            })
            
        except Exception as e:
            import traceback
            return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500
    
    @app.route('/admin/phase5/verify-prices')
    @login_required
    def verify_prices():
        """Verify that cached prices actually vary day-to-day"""
        if not current_user.is_admin:
            return jsonify({'error': 'Admin access required'}), 403
        
        try:
            from models import MarketData
            
            # Get a sample ticker
            sample_ticker = request.args.get('ticker', 'AAPL')
            
            # Get all prices (or limit if specified)
            limit = request.args.get('limit', 200)  # Default to 200 days (covers full range)
            try:
                limit = int(limit)
            except:
                limit = 200
            
            prices = MarketData.query.filter_by(
                ticker=sample_ticker.upper()
            ).order_by(MarketData.date.desc()).limit(limit).all()
            
            if not prices:
                return jsonify({'error': f'No prices found for {sample_ticker}'}), 404
            
            price_data = []
            price_values = []
            
            for p in prices:
                price_data.append({
                    'date': p.date.isoformat(),
                    'price': float(p.close_price)
                })
                price_values.append(float(p.close_price))
            
            # Calculate statistics
            unique_prices = len(set(price_values))
            min_price = min(price_values)
            max_price = max(price_values)
            avg_price = sum(price_values) / len(price_values)
            
            # Check total count and date range
            total_count = MarketData.query.filter_by(ticker=sample_ticker.upper()).count()
            
            # Get actual date range
            date_range = db.session.execute(text("""
                SELECT MIN(date) as earliest, MAX(date) as latest
                FROM market_data
                WHERE ticker = :ticker
            """), {'ticker': sample_ticker.upper()}).fetchone()
            
            return jsonify({
                'success': True,
                'ticker': sample_ticker.upper(),
                'total_cached_days': total_count,
                'date_range': {
                    'earliest': date_range.earliest.isoformat() if date_range and date_range.earliest else None,
                    'latest': date_range.latest.isoformat() if date_range and date_range.latest else None
                },
                'sample_size': len(prices),
                'prices': price_data,
                'statistics': {
                    'unique_prices': unique_prices,
                    'min': round(min_price, 2),
                    'max': round(max_price, 2),
                    'avg': round(avg_price, 2),
                    'variation': round(max_price - min_price, 2),
                    'status': '✅ Prices vary correctly' if unique_prices > 1 else '🚨 ERROR: All prices identical!'
                }
            })
            
        except Exception as e:
            import traceback
            return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500
