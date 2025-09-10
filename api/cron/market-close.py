"""
Market close cron job - runs at 4:00 PM ET daily via Vercel cron.
Performs final calculations and generates daily summaries.
"""
import os
from datetime import datetime, date
from flask import request, jsonify
from models import db, User, PortfolioSnapshot
from portfolio_performance import PortfolioPerformanceCalculator
from leaderboard_utils import update_all_user_leaderboards
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def handler(request):
    """Vercel serverless function handler for market close"""
    try:
        # Verify this is a Vercel cron request
        cron_secret = request.headers.get('Authorization')
        expected_secret = os.environ.get('CRON_SECRET')
        
        if not expected_secret or cron_secret != f"Bearer {expected_secret}":
            logger.warning("Unauthorized market close cron attempt")
            return jsonify({'error': 'Unauthorized'}), 401
        
        current_time = datetime.now()
        today = date.today()
        logger.info(f"Market close processing started at {current_time}")
        
        results = {
            'timestamp': current_time.isoformat(),
            'daily_snapshots_created': 0,
            'users_processed': 0,
            'leaderboard_entries_updated': 0,
            'errors': []
        }
        
        # Create daily snapshots for all users
        try:
            calculator = PortfolioPerformanceCalculator()
            users = User.query.all()
            results['users_processed'] = len(users)
            
            for user in users:
                try:
                    # Create or update daily snapshot
                    calculator.create_daily_snapshot(user.id, today)
                    results['daily_snapshots_created'] += 1
                    logger.info(f"Created daily snapshot for user {user.id}")
                
                except Exception as e:
                    error_msg = f"Error creating daily snapshot for user {user.id}: {str(e)}"
                    results['errors'].append(error_msg)
                    logger.error(error_msg)
        
        except Exception as e:
            error_msg = f"Error processing daily snapshots: {str(e)}"
            results['errors'].append(error_msg)
            logger.error(error_msg)
        
        # Update leaderboard cache for all periods
        try:
            logger.info("Starting leaderboard cache refresh after market close")
            from leaderboard_utils import update_leaderboard_cache
            updated_count = update_leaderboard_cache()
            results['leaderboard_cache_updated'] = updated_count
            logger.info(f"Leaderboard cache refresh completed: {updated_count} periods updated")
        except Exception as e:
            error_msg = f"Error updating leaderboard cache: {str(e)}"
            results['errors'].append(error_msg)
            logger.error(error_msg)
        
        # Update daily platform metrics
        try:
            logger.info("Starting daily platform metrics update")
            from admin_metrics import update_daily_metrics
            metrics_success = update_daily_metrics()
            results['metrics_updated'] = metrics_success
            logger.info(f"Platform metrics update completed: {'success' if metrics_success else 'failed'}")
        except Exception as e:
            error_msg = f"Error updating platform metrics: {str(e)}"
            results['errors'].append(error_msg)
            logger.error(error_msg)
        
        # Commit changes
        try:
            db.session.commit()
            logger.info("Market close processing completed successfully")
        except Exception as e:
            db.session.rollback()
            error_msg = f"Database commit failed: {str(e)}"
            results['errors'].append(error_msg)
            logger.error(error_msg)
            return jsonify({'error': error_msg, 'results': results}), 500
        
        return jsonify({
            'success': True,
            'message': 'Market close processing completed',
            'results': results
        }), 200
    
    except Exception as e:
        logger.error(f"Unexpected error in market close: {str(e)}")
        return jsonify({'error': f'Unexpected error: {str(e)}'}), 500
