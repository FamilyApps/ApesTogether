"""Find the gap in SPY_INTRADAY data"""
from datetime import date, timedelta
from models import MarketData, db
from sqlalchemy import and_, func
from app import app

with app.app_context():
    today = date.today()
    
    print(f"Checking SPY_INTRADAY data from {today} backwards...\n")
    
    # Check last 30 trading days
    results = []
    for days_back in range(30):
        check_date = today - timedelta(days=days_back)
        
        # Skip weekends
        if check_date.weekday() >= 5:
            continue
        
        # Count SPY_INTRADAY records for this date
        count = MarketData.query.filter(
            and_(
                MarketData.ticker == 'SPY_INTRADAY',
                MarketData.date == check_date
            )
        ).count()
        
        # Get sample timestamps if any exist
        sample = None
        if count > 0:
            first = MarketData.query.filter(
                and_(
                    MarketData.ticker == 'SPY_INTRADAY',
                    MarketData.date == check_date
                )
            ).order_by(MarketData.timestamp.asc()).first()
            
            last = MarketData.query.filter(
                and_(
                    MarketData.ticker == 'SPY_INTRADAY',
                    MarketData.date == check_date
                )
            ).order_by(MarketData.timestamp.desc()).first()
            
            sample = f"{first.timestamp.strftime('%H:%M')} to {last.timestamp.strftime('%H:%M')}"
        
        status = "✓" if count > 0 else "✗"
        results.append({
            'date': check_date,
            'count': count,
            'sample': sample,
            'status': status
        })
        
        print(f"{status} {check_date.isoformat()}: {count:3d} records {f'({sample})' if sample else ''}")
    
    # Find the gap
    print("\n" + "="*60)
    gap_start = None
    gap_end = None
    
    for r in results:
        if r['count'] == 0:
            if gap_end is None:
                gap_end = r['date']
            gap_start = r['date']
        elif gap_start and gap_end:
            break
    
    if gap_start and gap_end:
        trading_days = sum(1 for r in results if r['date'] >= gap_start and r['date'] <= gap_end and r['date'].weekday() < 5)
        print(f"\n🔴 GAP FOUND:")
        print(f"   From: {gap_start.isoformat()}")
        print(f"   To:   {gap_end.isoformat()}")
        print(f"   Trading Days Missing: {trading_days}")
    else:
        print("\n✅ No gaps found in last 30 days")
    
    # Total SPY_INTRADAY count
    total = MarketData.query.filter_by(ticker='SPY_INTRADAY').count()
    print(f"\n📊 Total SPY_INTRADAY records: {total}")
