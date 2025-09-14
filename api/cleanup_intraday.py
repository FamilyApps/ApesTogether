"""
Intraday data cleanup utility for the stock portfolio app.
Removes old intraday snapshots while preserving 4:00 PM market close data.
"""

from datetime import datetime, date, timedelta, time
from models import db, PortfolioSnapshotIntraday
import logging

logger = logging.getLogger(__name__)

def cleanup_old_intraday_data(days_to_keep=14):
    """
    Clean up old intraday snapshots while preserving 4:00 PM market close data.
    
    Args:
        days_to_keep (int): Number of days of intraday data to keep (default: 14)
    
    Returns:
        dict: Results of the cleanup operation
    """
    cutoff_date = date.today() - timedelta(days=days_to_keep)
    
    results = {
        'cutoff_date': cutoff_date.isoformat(),
        'snapshots_analyzed': 0,
        'snapshots_deleted': 0,
        'market_close_preserved': 0,
        'errors': []
    }
    
    try:
        # Get old intraday snapshots (older than cutoff date)
        old_snapshots = PortfolioSnapshotIntraday.query.filter(
            PortfolioSnapshotIntraday.timestamp < datetime.combine(cutoff_date, datetime.min.time())
        ).all()
        
        results['snapshots_analyzed'] = len(old_snapshots)
        
        for snapshot in old_snapshots:
            snapshot_time = snapshot.timestamp.time()
            
            # Preserve 4:00 PM snapshots (market close) - these serve as EOD snapshots
            if snapshot_time.hour == 16 and snapshot_time.minute == 0:
                results['market_close_preserved'] += 1
                continue
            
            # Delete non-market-close intraday snapshots
            try:
                db.session.delete(snapshot)
                results['snapshots_deleted'] += 1
            except Exception as e:
                error_msg = f"Error deleting snapshot {snapshot.id}: {str(e)}"
                results['errors'].append(error_msg)
                logger.error(error_msg)
        
        # Commit deletions
        db.session.commit()
        logger.info(f"Intraday cleanup completed: {results['snapshots_deleted']} deleted, {results['market_close_preserved']} preserved")
        
    except Exception as e:
        db.session.rollback()
        error_msg = f"Intraday cleanup failed: {str(e)}"
        results['errors'].append(error_msg)
        logger.error(error_msg)
    
    return results

if __name__ == "__main__":
    # Run cleanup when executed directly
    from app import app
    
    with app.app_context():
        results = cleanup_old_intraday_data()
        print(f"Cleanup Results: {results}")
