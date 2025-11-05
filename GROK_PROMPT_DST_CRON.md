# Grok Prompt: DST-Aware Cron Scheduling for Stock Market Hours

## Context

I have a stock portfolio tracking app deployed on Vercel that needs to collect intraday snapshots every 15 minutes during US stock market hours (9:30 AM - 4:00 PM Eastern Time).

**The Problem:**
- Vercel cron schedules use UTC time and don't adjust for Daylight Saving Time (DST)
- US Eastern Time switches between EDT (UTC-4) and EST (UTC-5) twice a year
- Stock market hours are ALWAYS 9:30 AM - 4:00 PM Eastern Time, regardless of DST

**Current Situation:**
- When DST ended on November 3, 2025, my cron schedule broke
- Collections were happening at 8:30 AM - 3:00 PM EST instead of 9:30 AM - 4:00 PM EST
- I had to manually update the UTC times in vercel.json

## Requirements

1. **Market Hours (Eastern Time):**
   - 9:30 AM ET (market open)
   - 9:45 AM ET
   - 10:00 AM - 3:45 PM ET (every 15 minutes)
   - 4:00 PM ET (market close)

2. **UTC Equivalents:**
   - **During EDT (March-November):** 13:30 - 20:00 UTC
   - **During EST (November-March):** 14:30 - 21:00 UTC

3. **Vercel Cron Format:**
   - Standard cron syntax: `minute hour day month dayofweek`
   - Multiple schedules allowed for the same endpoint

## Possible Approaches

### Option 1: Manual Update (Current - REJECTED)
Update `vercel.json` twice a year when DST changes.
- ❌ **REJECTED:** User refuses to manually update twice a year

### Option 2: Frequent Cron with Smart Filtering
```json
{
  "path": "/api/cron/collect-intraday-data",
  "schedule": "*/15 * * * 1-5"
}
```
Run every 15 minutes all day, let the Flask endpoint check Eastern Time and skip if outside market hours.

**Pros:**
- Fully automatic DST handling
- Simple schedule
- All logic in one place (Flask endpoint)

**Cons:**
- ~96 cron executions per weekday (most get skipped)
- May hit Vercel's cron execution limits
- More resource usage

### Option 3: Dual Schedule with Time Validation
```json
{
  "path": "/api/cron/collect-intraday-data",
  "schedule": "30,45 13-14 * * 1-5"
},
{
  "path": "/api/cron/collect-intraday-data",
  "schedule": "0,15,30,45 14-20 * * 1-5"
},
{
  "path": "/api/cron/collect-intraday-data",
  "schedule": "0 20-21 * * 1-5"
}
```
Trigger at both EDT and EST times, Flask endpoint validates actual Eastern Time.

**Pros:**
- Automatic DST handling
- Fewer executions than Option 2 (~54 per weekday)
- Redundancy built in

**Cons:**
- More complex schedule
- Still runs unnecessary crons that get skipped
- Schedule is harder to understand

### Option 4: Your Suggestion
What's the best practice for handling DST in production cron schedules?

## Questions for Grok

1. **What's the industry best practice** for handling DST in UTC-based cron schedules for time-sensitive operations like stock market data collection?

2. **Should I optimize for:**
   - Simplicity (fewer cron executions, more manual management)?
   - Automation (more cron executions, zero manual work)?
   - A hybrid approach?

3. **Are there any Vercel-specific limits or gotchas** I should know about when running crons every 15 minutes vs. running them at specific times?

4. **Is there a better architecture** I'm missing? (e.g., self-hosted scheduler, AWS Lambda with EventBridge, etc.)

5. **For Option 2 (frequent cron):** Is running ~96 cron executions per weekday acceptable on Vercel's Hobby/Pro plans? Will most of them being quick skips (200ms, no DB writes) cause issues?

6. **Security concern:** The Flask endpoint currently checks if it's market hours and skips if not. Is this sufficient, or should I add additional safeguards against accidental data collection outside market hours?

## Current Implementation

**Flask Endpoint Logic (api/index.py):**
```python
# Get current Eastern Time (auto-handles DST via zoneinfo)
current_time = get_market_time()  # Uses ZoneInfo('America/New_York')

# Check if weekday
if current_time.weekday() >= 5:
    return skip_response('weekend')

# Check if valid 15-minute interval during market hours
hour = current_time.hour
minute = current_time.minute
valid_intervals = {(9,30), (9,45), (10,0), (10,15), ..., (16,0)}

# Allow +/- 2 minutes tolerance for cron timing variance
if (hour, minute) not in valid_intervals (with tolerance):
    return skip_response('outside_market_hours')

# Proceed with data collection...
```

**Vercel Plan:** [Hobby/Pro - please specify which limits apply]

## What I Need

A recommendation on the best approach that:
- ✅ Automatically handles DST transitions
- ✅ Doesn't require manual updates to vercel.json twice a year
- ✅ Is reliable and won't miss collections during market hours
- ✅ Is production-ready and maintainable
- ✅ Doesn't violate Vercel's resource limits or best practices

Please provide a detailed analysis of the tradeoffs and your recommended approach with reasoning.
