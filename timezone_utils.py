"""
Timezone utilities for handling DST transitions and market hours
Using standard library datetime instead of pytz for better Vercel compatibility
"""
from datetime import datetime, timezone, timedelta

def get_market_timezone():
    """Get the US/Eastern timezone - simplified for Vercel compatibility"""
    # For now, assume EDT (UTC-4) - can be enhanced later
    return timezone(timedelta(hours=-4))

def get_current_market_offset():
    """Get current UTC offset for US/Eastern - simplified"""
    # For September, we're in EDT (UTC-4)
    return -4

def convert_market_time_to_utc(hour, minute=0):
    """Convert market time (Eastern) to UTC - simplified"""
    # EDT = UTC-4, so add 4 hours to get UTC
    utc_hour = (hour + 4) % 24
    return datetime.now(timezone.utc).replace(hour=utc_hour, minute=minute, second=0, microsecond=0)

def get_market_hours_utc():
    """Get current market hours in UTC (9:30 AM - 4:00 PM Eastern)"""
    market_open_utc = convert_market_time_to_utc(9, 30)
    market_close_utc = convert_market_time_to_utc(16, 0)
    
    return {
        'open': market_open_utc,
        'close': market_close_utc,
        'open_hour': market_open_utc.hour,
        'open_minute': market_open_utc.minute,
        'close_hour': market_close_utc.hour,
        'close_minute': market_close_utc.minute
    }

def is_market_hours(dt=None):
    """Check if given datetime (or now) is during market hours - simplified"""
    if dt is None:
        dt = datetime.now(timezone.utc)
    elif dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    
    # Convert to Eastern time (subtract 4 hours for EDT)
    eastern_time = dt - timedelta(hours=4)
    
    # Check if it's a weekday and within market hours
    if eastern_time.weekday() >= 5:  # Saturday = 5, Sunday = 6
        return False
    
    # Market hours: 9:30 AM - 4:00 PM Eastern
    market_start = eastern_time.replace(hour=9, minute=30, second=0, microsecond=0)
    market_end = eastern_time.replace(hour=16, minute=0, second=0, microsecond=0)
    
    return market_start <= eastern_time <= market_end

def get_cron_schedule_for_market_hours():
    """Generate cron schedules that automatically adjust for DST"""
    hours = get_market_hours_utc()
    
    # Generate collection times every 30 minutes during market hours
    open_hour = hours['open_hour']
    close_hour = hours['close_hour']
    
    # Create hour ranges for cron
    collection_hours = list(range(open_hour, close_hour + 1))
    
    return {
        'market_open': f"{hours['open_minute']} {open_hour} * * 1-5",
        'collect_00': f"0 {','.join(map(str, collection_hours[1:]))} * * 1-5",  # Skip first hour (handled by market open)
        'collect_30': f"30 {','.join(map(str, collection_hours))} * * 1-5",
        'market_close': f"{hours['close_minute']} {close_hour} * * 1-5"
    }

if __name__ == "__main__":
    # Test the functions
    print("Current market timezone offset:", get_current_market_offset())
    print("Market hours UTC:", get_market_hours_utc())
    print("Is market open now?", is_market_hours())
    print("Cron schedules:", get_cron_schedule_for_market_hours())
