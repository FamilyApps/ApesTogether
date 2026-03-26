"""
Admin endpoint to test intraday data collection system manually.
"""
import os
from datetime import datetime
from flask import request, jsonify
from models import db, User, PortfolioSnapshotIntraday, MarketData
from portfolio_performance import PortfolioPerformanceCalculator
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def handler(request):
    """Test the intraday data collection system"""
    try:
        current_time = datetime.now()
        
        results = {
            'timestamp': current_time.isoformat(),
            'environment_check': {},
            'spy_data_test': {},
            'user_count': 0,
            'sample_snapshots': [],
            'chart_generation_test': {},
            'errors': []
        }
        
        # Check environment variables
        try:
            intraday_token = os.environ.get('INTRADAY_CRON_TOKEN')
            cron_secret = os.environ.get('CRON_SECRET')
            alpha_key = os.environ.get('ALPHA_VANTAGE_API_KEY')
            
            results['environment_check'] = {
                'intraday_token_exists': bool(intraday_token),
                'cron_secret_exists': bool(cron_secret),
                'alpha_vantage_key_exists': bool(alpha_key),
                'intraday_token_length': len(intraday_token) if intraday_token else 0
            }
        except Exception as e:
            results['errors'].append(f"Environment check error: {str(e)}")
        
        # Test SPY data collection
        try:
            calculator = PortfolioPerformanceCalculator()
            spy_data = calculator.get_stock_data('SPY')
            
            if spy_data and spy_data.get('price'):
                spy_price = spy_data['price']
                sp500_value = spy_price * 10
                
                results['spy_data_test'] = {
                    'success': True,
                    'spy_price': spy_price,
                    'sp500_equivalent': sp500_value,
                    'data_source': 'AlphaVantage'
                }
            else:
                results['spy_data_test'] = {
                    'success': False,
                    'error': 'Failed to fetch SPY data'
                }
        except Exception as e:
            results['spy_data_test'] = {
                'success': False,
                'error': str(e)
            }
            results['errors'].append(f"SPY data test error: {str(e)}")
        
        # Check user count and create sample snapshots
        try:
            users = User.query.all()
            results['user_count'] = len(users)
            
            # Create sample intraday snapshots for first 3 users
            for i, user in enumerate(users[:3]):
                try:
                    portfolio_value = calculator.calculate_portfolio_value(user.id)
                    
                    # Create test snapshot
                    test_snapshot = PortfolioSnapshotIntraday(
                        user_id=user.id,
                        timestamp=current_time,
                        total_value=portfolio_value
                    )
                    db.session.add(test_snapshot)
                    
                    results['sample_snapshots'].append({
                        'user_id': user.id,
                        'portfolio_value': portfolio_value,
                        'timestamp': current_time.isoformat()
                    })
                    
                except Exception as e:
                    results['errors'].append(f"Error creating snapshot for user {user.id}: {str(e)}")
        
        except Exception as e:
            results['errors'].append(f"User processing error: {str(e)}")
        
        # Test S&P 500 MarketData availability
        try:
            from datetime import timedelta
            today = current_time.date()
            week_ago = today - timedelta(days=7)
            
            sp500_records = MarketData.query.filter(
                MarketData.ticker == 'SPY_SP500',
                MarketData.date >= week_ago,
                MarketData.date <= today
            ).order_by(MarketData.date.desc()).all()
            
            if sp500_records:
                results['chart_generation_test'] = {
                    'success': True,
                    'source': 'MarketData (SPY_SP500)',
                    'data_points': len(sp500_records),
                    'latest_date': sp500_records[0].date.isoformat(),
                    'latest_value': float(sp500_records[0].close_price)
                }
            else:
                results['chart_generation_test'] = {
                    'success': False,
                    'error': 'No SPY_SP500 MarketData records found in last 7 days'
                }
        
        except Exception as e:
            results['chart_generation_test'] = {
                'success': False,
                'error': str(e)
            }
            results['errors'].append(f"S&P 500 data test error: {str(e)}")
        
        # Commit test data
        try:
            db.session.commit()
            logger.info("Test intraday collection completed successfully")
        except Exception as e:
            db.session.rollback()
            error_msg = f"Database commit failed: {str(e)}"
            results['errors'].append(error_msg)
            logger.error(error_msg)
        
        return jsonify({
            'success': len(results['errors']) == 0,
            'message': 'Intraday collection test completed',
            'results': results
        }), 200
    
    except Exception as e:
        logger.error(f"Unexpected error in intraday test: {str(e)}")
        return jsonify({'error': f'Unexpected error: {str(e)}'}), 500
