"""
Timezone utilities for handling DST transitions and market hours
"""
from datetime import datetime, timezone
import pytz

def get_market_timezone():
    """Get the US/Eastern timezone with DST handling"""
    return pytz.timezone('US/Eastern')

def get_current_market_offset():
    """Get current UTC offset for US/Eastern (handles DST automatically)"""
    eastern = get_market_timezone()
    now = datetime.now(eastern)
    return now.utcoffset().total_seconds() / 3600  # Returns -4 (EDT) or -5 (EST)

def convert_market_time_to_utc(hour, minute=0):
    """Convert market time (Eastern) to UTC, accounting for DST"""
    eastern = get_market_timezone()
    # Use today's date to get correct DST offset
    today = datetime.now(eastern).date()
    market_time = eastern.localize(datetime.combine(today, datetime.min.time().replace(hour=hour, minute=minute)))
    return market_time.astimezone(timezone.utc)

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
    """Check if given datetime (or now) is during market hours"""
    if dt is None:
        dt = datetime.now(timezone.utc)
    elif dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    
    # Convert to Eastern time
    eastern = get_market_timezone()
    eastern_time = dt.astimezone(eastern)
    
    # Check if it's a weekday and within market hours
    if eastern_time.weekday() >= 5:  # Saturday = 5, Sunday = 6
        return False
    
    market_open = eastern_time.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = eastern_time.replace(hour=16, minute=0, second=0, microsecond=0)
    
    return market_open <= eastern_time <= market_close

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
