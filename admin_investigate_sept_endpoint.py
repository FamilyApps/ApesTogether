"""
Admin endpoint code to add to api/index.py

Add this endpoint anywhere in the admin routes section:
"""

ENDPOINT_CODE = '''
@app.route('/admin/investigate-sept-snapshots')
@login_required
def admin_investigate_sept_snapshots():
    """Investigate witty-raven's snapshots from Sept 2-10, 2025"""
    try:
        if not current_user.is_admin:
            return jsonify({'error': 'Admin access required'}), 403
        
        from datetime import date
        from models import PortfolioSnapshot, Transaction, Stock, MarketData, User
        from sqlalchemy import and_
        import json as json_module
        
        USER_ID = 5  # witty-raven
        START_DATE = date(2025, 9, 2)
        END_DATE = date(2025, 9, 11)
        
        results = {
            'user_id': USER_ID,
            'date_range': f"{START_DATE} to {END_DATE}",
            'snapshots': [],
            'transactions': [],
            'market_data_check': {},
            'user_info': {}
        }
        
        # Get user info
        user = User.query.get(USER_ID)
        if user:
            results['user_info'] = {
                'username': user.username,
                'email': user.email,
                'created_at': str(user.created_at)
            }
        
        # Get snapshots
        snapshots = PortfolioSnapshot.query.filter(
            and_(
                PortfolioSnapshot.user_id == USER_ID,
                PortfolioSnapshot.date >= START_DATE,
                PortfolioSnapshot.date <= END_DATE
            )
        ).order_by(PortfolioSnapshot.date).all()
        
        if snapshots:
            baseline = snapshots[0].total_value
            results['baseline_value'] = baseline
            
            for snapshot in snapshots:
                change = snapshot.total_value - baseline
                pct_change = (change / baseline * 100) if baseline > 0 else 0
                
                results['snapshots'].append({
                    'date': str(snapshot.date),
                    'total_value': round(snapshot.total_value, 2),
                    'change_from_baseline': round(change, 2),
                    'pct_change': round(pct_change, 2),
                    'holdings': str(snapshot.holdings) if snapshot.holdings else 'None'
                })
        
        # Get transactions
        transactions = Transaction.query.filter(
            and_(
                Transaction.user_id == USER_ID,
                Transaction.date >= START_DATE,
                Transaction.date <= END_DATE
            )
        ).order_by(Transaction.date).all()
        
        for txn in transactions:
            stock = Stock.query.get(txn.stock_id)
            results['transactions'].append({
                'date': str(txn.date),
                'type': txn.transaction_type,
                'symbol': stock.symbol if stock else 'Unknown',
                'shares': txn.shares,
                'price': txn.price,
                'total': round(txn.shares * txn.price, 2)
            })
        
        # Check market data availability
        all_stocks = set()
        for snapshot in snapshots:
            if snapshot.holdings:
                try:
                    holdings_dict = snapshot.holdings if isinstance(snapshot.holdings, dict) else json_module.loads(str(snapshot.holdings).replace("'", '"'))
                    all_stocks.update(holdings_dict.keys())
                except Exception as e:
                    logger.warning(f"Could not parse holdings for {snapshot.date}: {e}")
        
        results['stocks_in_portfolio'] = sorted(list(all_stocks))
        
        for symbol in all_stocks:
            stock = Stock.query.filter_by(symbol=symbol).first()
            if stock:
                market_data = MarketData.query.filter(
                    and_(
                        MarketData.stock_id == stock.id,
                        MarketData.date >= START_DATE,
                        MarketData.date <= END_DATE
                    )
                ).order_by(MarketData.date).all()
                
                results['market_data_check'][symbol] = {
                    'stock_id': stock.id,
                    'data_points_found': len(market_data),
                    'dates': [str(md.date) for md in market_data],
                    'prices': [round(md.close_price, 2) for md in market_data]
                }
            else:
                results['market_data_check'][symbol] = {
                    'error': 'Stock not found in database'
                }
        
        # Summary analysis
        if snapshots:
            results['summary'] = {
                'total_snapshots': len(snapshots),
                'total_transactions': len(transactions),
                'baseline_date': str(snapshots[0].date),
                'baseline_value': round(snapshots[0].total_value, 2),
                'end_date': str(snapshots[-1].date),
                'end_value': round(snapshots[-1].total_value, 2),
                'total_change_dollars': round(snapshots[-1].total_value - snapshots[0].total_value, 2),
                'total_change_percent': round(((snapshots[-1].total_value - snapshots[0].total_value) / snapshots[0].total_value * 100) if snapshots[0].total_value > 0 else 0, 2)
            }
        
        return jsonify(results)
        
    except Exception as e:
        logger.error(f"Error investigating Sept snapshots: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500
'''

print("Copy the code above and add it to api/index.py in the admin routes section")
print("\nOr visit this URL after adding the endpoint:")
print("https://apestogether.ai/admin/investigate-sept-snapshots")
