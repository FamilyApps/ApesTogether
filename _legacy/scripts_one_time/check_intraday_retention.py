"""
Check intraday data retention and verify purging is working correctly.
"""

from datetime import datetime, timedelta, date
from models import db, PortfolioSnapshotIntraday, User
from sqlalchemy import func

def check_intraday_retention():
    """Check current state of intraday data retention"""
    
    results = {
        'total_intraday_snapshots': 0,
        'snapshots_by_user': {},
        'date_range': {},
        'snapshots_by_day': {},
        'estimated_daily_rate': 0,
        'retention_analysis': {}
    }
    
    # Total count
    results['total_intraday_snapshots'] = PortfolioSnapshotIntraday.query.count()
    
    # Count by user
    users = User.query.all()
    for user in users:
        count = PortfolioSnapshotIntraday.query.filter_by(user_id=user.id).count()
        results['snapshots_by_user'][user.username] = count
    
    # Date range
    oldest = PortfolioSnapshotIntraday.query.order_by(PortfolioSnapshotIntraday.timestamp.asc()).first()
    newest = PortfolioSnapshotIntraday.query.order_by(PortfolioSnapshotIntraday.timestamp.desc()).first()
    
    if oldest and newest:
        results['date_range'] = {
            'oldest': oldest.timestamp.isoformat(),
            'newest': newest.timestamp.isoformat(),
            'days_span': (newest.timestamp.date() - oldest.timestamp.date()).days
        }
        
        # Snapshots by day (last 20 days)
        for days_ago in range(20):
            check_date = date.today() - timedelta(days=days_ago)
            count = PortfolioSnapshotIntraday.query.filter(
                func.date(PortfolioSnapshotIntraday.timestamp) == check_date
            ).count()
            
            if count > 0:
                results['snapshots_by_day'][check_date.isoformat()] = count
        
        # Estimate daily collection rate
        if results['date_range']['days_span'] > 0:
            results['estimated_daily_rate'] = results['total_intraday_snapshots'] / results['date_range']['days_span']
    
    # Retention analysis
    cutoff_14_days = date.today() - timedelta(days=14)
    old_snapshots = PortfolioSnapshotIntraday.query.filter(
        PortfolioSnapshotIntraday.timestamp < datetime.combine(cutoff_14_days, datetime.min.time())
    ).count()
    
    results['retention_analysis'] = {
        'cutoff_date_14_days': cutoff_14_days.isoformat(),
        'snapshots_older_than_14_days': old_snapshots,
        'snapshots_within_14_days': results['total_intraday_snapshots'] - old_snapshots,
        'purging_working': old_snapshots == 0,
        'recommendation': 'Run /admin/cleanup-intraday-data if old_snapshots > 0' if old_snapshots > 0 else 'Purging is working correctly'
    }
    
    return results


if __name__ == "__main__":
    from app import app
    
    with app.app_context():
        results = check_intraday_retention()
        
        print("\n" + "="*80)
        print("INTRADAY DATA RETENTION CHECK")
        print("="*80)
        
        print(f"\nTotal Intraday Snapshots: {results['total_intraday_snapshots']}")
        
        print("\nSnapshots by User:")
        for username, count in results['snapshots_by_user'].items():
            print(f"  {username}: {count} snapshots")
        
        if results['date_range']:
            print(f"\nDate Range:")
            print(f"  Oldest: {results['date_range']['oldest']}")
            print(f"  Newest: {results['date_range']['newest']}")
            print(f"  Span: {results['date_range']['days_span']} days")
            print(f"  Estimated Daily Rate: {results['estimated_daily_rate']:.1f} snapshots/day")
        
        print(f"\nSnapshots by Day (last 20 days):")
        for day, count in sorted(results['snapshots_by_day'].items(), reverse=True):
            print(f"  {day}: {count} snapshots")
        
        print(f"\nRetention Analysis (14-day retention policy):")
        print(f"  Cutoff Date: {results['retention_analysis']['cutoff_date_14_days']}")
        print(f"  Snapshots older than 14 days: {results['retention_analysis']['snapshots_older_than_14_days']}")
        print(f"  Snapshots within 14 days: {results['retention_analysis']['snapshots_within_14_days']}")
        print(f"  ✅ Purging Working: {results['retention_analysis']['purging_working']}")
        print(f"  Recommendation: {results['retention_analysis']['recommendation']}")
        
        print("\n" + "="*80)
