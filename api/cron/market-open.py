"""
Market open cron job - runs at 9:30 AM ET daily via Vercel cron.
Initializes daily tracking and clears old cache data.
"""
import os
from datetime import datetime, timedelta
from flask import request, jsonify
from models import db, MarketData, SP500ChartCache
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def handler(request):
    """Vercel serverless function handler for market open"""
    try:
        # Verify this is a Vercel cron request
        cron_secret = request.headers.get('Authorization')
        expected_secret = os.environ.get('CRON_SECRET')
        
        if not expected_secret or cron_secret != f"Bearer {expected_secret}":
            logger.warning("Unauthorized market open cron attempt")
            return jsonify({'error': 'Unauthorized'}), 401
        
        current_time = datetime.now()
        logger.info(f"Market open initialization started at {current_time}")
        
        results = {
            'timestamp': current_time.isoformat(),
            'cache_cleared': False,
            'old_data_cleaned': False,
            'errors': []
        }
        
        # Clear expired chart cache
        try:
            expired_charts = SP500ChartCache.query.filter(
                SP500ChartCache.expires_at < current_time
            ).all()
            
            for chart in expired_charts:
                db.session.delete(chart)
            
            results['cache_cleared'] = len(expired_charts) > 0
            logger.info(f"Cleared {len(expired_charts)} expired chart cache entries")
        
        except Exception as e:
            error_msg = f"Error clearing chart cache: {str(e)}"
            results['errors'].append(error_msg)
            logger.error(error_msg)
        
        # Clean up old intraday data (keep only last 7 days)
        try:
            cutoff_date = current_time - timedelta(days=7)
            old_intraday = MarketData.query.filter(
                MarketData.ticker == 'SPY_INTRADAY',
                MarketData.timestamp < cutoff_date
            ).all()
            
            for data in old_intraday:
                db.session.delete(data)
            
            results['old_data_cleaned'] = len(old_intraday) > 0
            logger.info(f"Cleaned up {len(old_intraday)} old intraday data entries")
        
        except Exception as e:
            error_msg = f"Error cleaning old data: {str(e)}"
            results['errors'].append(error_msg)
            logger.error(error_msg)
        
        # Commit changes
        try:
            db.session.commit()
            logger.info("Market open initialization completed successfully")
        except Exception as e:
            db.session.rollback()
            error_msg = f"Database commit failed: {str(e)}"
            results['errors'].append(error_msg)
            logger.error(error_msg)
            return jsonify({'error': error_msg, 'results': results}), 500
        
        return jsonify({
            'success': True,
            'message': 'Market open initialization completed',
            'results': results
        }), 200
    
    except Exception as e:
        logger.error(f"Unexpected error in market open: {str(e)}")
        return jsonify({'error': f'Unexpected error: {str(e)}'}), 500
