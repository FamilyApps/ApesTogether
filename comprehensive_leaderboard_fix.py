#!/usr/bin/env python3
"""
Comprehensive Leaderboard Fix Script
====================================

This script diagnoses and fixes the core leaderboard data population issues:
1. Schema verification (should already be fixed)
2. Data availability check
3. Live calculation testing
4. Clear broken data
5. Regenerate leaderboard cache
6. Verify the fix

Can be run standalone or imported and called from admin endpoints.
"""

import os
import sys
from datetime import datetime, date, timedelta
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add the project root to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def comprehensive_leaderboard_fix():
    """
    Main function to diagnose and fix leaderboard data issues
    Returns: (success: bool, results: dict)
    """
    
    print("=" * 50)
    print("COMPREHENSIVE LEADERBOARD FIX")
    print("=" * 50)
    print(f"Starting at: {datetime.now().isoformat()}")
    print()
    
    results = {
        'timestamp': datetime.now().isoformat(),
        'steps': [],
        'errors': [],
        'final_status': {},
        'summary': {}
    }
    
    try:
        # Import required modules
        from models import db, User, LeaderboardCache, LeaderboardEntry, PortfolioSnapshot
        from leaderboard_utils import update_leaderboard_cache, calculate_leaderboard_data
        from sqlalchemy import inspect
        import json
        
        # Step 1: Verify schema is fixed
        print("STEP 1: VERIFYING SCHEMA...")
        results['steps'].append("1. Verifying schema...")
        
        try:
            inspector = inspect(db.engine)
            leaderboard_columns = [col['name'] for col in inspector.get_columns('leaderboard_entry')]
            required_columns = ['period', 'performance_percent', 'small_cap_percent', 'large_cap_percent', 'avg_trades_per_week']
            
            missing_columns = [col for col in required_columns if col not in leaderboard_columns]
            if missing_columns:
                error_msg = f"Missing columns in leaderboard_entry: {missing_columns}"
                results['errors'].append(error_msg)
                results['steps'].append(f"   ❌ CRITICAL: {error_msg}")
                print(f"   ❌ CRITICAL: {error_msg}")
                print("   Run the schema fix endpoint first!")
                return False, results
            else:
                success_msg = "Schema is correct - all required columns exist"
                results['steps'].append(f"   ✅ {success_msg}")
                print(f"   ✅ {success_msg}")
        except Exception as e:
            error_msg = f"Schema check failed: {str(e)}"
            results['errors'].append(error_msg)
            results['steps'].append(f"   ❌ {error_msg}")
            print(f"   ❌ {error_msg}")
        
        print()
        
        # Step 2: Check data availability
        print("STEP 2: CHECKING DATA AVAILABILITY...")
        results['steps'].append("2. Checking data availability...")
        
        try:
            total_users = User.query.count()
            users_with_stocks = User.query.join(User.stocks).distinct().all()
            total_snapshots = PortfolioSnapshot.query.count()
            
            print(f"   Total users: {total_users}")
            print(f"   Users with stocks: {len(users_with_stocks)}")
            print(f"   Total portfolio snapshots: {total_snapshots}")
            
            results['steps'].append(f"   Total users: {total_users}")
            results['steps'].append(f"   Users with stocks: {len(users_with_stocks)}")
            results['steps'].append(f"   Total portfolio snapshots: {total_snapshots}")
            
            if len(users_with_stocks) == 0:
                error_msg = "No users have stocks!"
                results['errors'].append(error_msg)
                results['steps'].append(f"   ❌ CRITICAL: {error_msg}")
                print(f"   ❌ CRITICAL: {error_msg}")
                return False, results
            
            if total_snapshots == 0:
                error_msg = "No portfolio snapshots exist!"
                results['errors'].append(error_msg)
                results['steps'].append(f"   ❌ CRITICAL: {error_msg}")
                results['steps'].append("   Need to create snapshots first")
                print(f"   ❌ CRITICAL: {error_msg}")
                print("   Need to create snapshots first")
                return False, results
            
            success_msg = "Basic data is available"
            results['steps'].append(f"   ✅ {success_msg}")
            print(f"   ✅ {success_msg}")
            
        except Exception as e:
            error_msg = f"Data availability check failed: {str(e)}"
            results['errors'].append(error_msg)
            results['steps'].append(f"   ❌ {error_msg}")
            print(f"   ❌ {error_msg}")
        
        print()
        
        # Step 3: Check current leaderboard status (before fix)
        print("STEP 3: CURRENT LEADERBOARD STATUS (BEFORE FIX)...")
        results['steps'].append("3. Current leaderboard status...")
        
        current_status = {}
        for period in ['1D', '5D']:
            try:
                # Check cache
                cache_entry = LeaderboardCache.query.filter_by(period=period).first()
                cache_count = 0
                if cache_entry:
                    try:
                        cache_data = json.loads(cache_entry.leaderboard_data)
                        cache_count = len(cache_data)
                    except:
                        cache_count = 0
                
                # Check entries
                entry_count = LeaderboardEntry.query.filter_by(period=period).count()
                
                current_status[period] = {
                    'cache_count': cache_count,
                    'entry_count': entry_count
                }
                
                status_msg = f"{period}: Cache={cache_count} entries, DB entries={entry_count}"
                results['steps'].append(f"   {status_msg}")
                print(f"   {status_msg}")
                
                if cache_count == 0 and entry_count == 0:
                    problem_msg = f"No data for {period}"
                    results['steps'].append(f"      ❌ {problem_msg}")
                    print(f"      ❌ {problem_msg}")
                elif cache_count == 1 or entry_count == 1:
                    problem_msg = f"Only 1 entry for {period} (should be {len(users_with_stocks)})"
                    results['steps'].append(f"      ⚠ {problem_msg}")
                    print(f"      ⚠ {problem_msg}")
                    
            except Exception as e:
                error_msg = f"Status check for {period} failed: {str(e)}"
                results['errors'].append(error_msg)
                results['steps'].append(f"   {period}: ERROR - {str(e)}")
                print(f"   {period}: ERROR - {str(e)}")
        
        print()
        
        # Step 4: Test snapshot-based calculations (NEW APPROACH)
        print("STEP 4: TESTING SNAPSHOT-BASED CALCULATIONS...")
        results['steps'].append("4. Testing snapshot-based calculations...")
        
        working_users = []
        
        for period in ['1D', '5D']:
            try:
                # Test the working snapshot-based calculation approach
                leaderboard_entries = calculate_leaderboard_data(period)
                
                if leaderboard_entries and len(leaderboard_entries) > 0:
                    calc_msg = f"{period}: Generated {len(leaderboard_entries)} entries using snapshots ✅"
                    results['steps'].append(f"   {calc_msg}")
                    print(f"   {calc_msg}")
                    
                    # Show top 3 entries
                    for i, entry in enumerate(leaderboard_entries[:3]):
                        if hasattr(entry, 'username') and hasattr(entry, 'performance_percent'):
                            entry_msg = f"      {i+1}. {entry.username}: {entry.performance_percent:.2f}%"
                            results['steps'].append(entry_msg)
                            print(entry_msg)
                    
                    # Mark as working if we have entries
                    if period == '5D':  # Use 5D as the test period
                        working_users = [entry for entry in leaderboard_entries if hasattr(entry, 'user_id')]
                        
                else:
                    calc_msg = f"{period}: No entries generated ❌"
                    results['steps'].append(f"   {calc_msg}")
                    print(f"   {calc_msg}")
                    
            except Exception as e:
                calc_msg = f"{period}: ERROR - {str(e)} ❌"
                results['steps'].append(f"   {calc_msg}")
                print(f"   {calc_msg}")
        
        working_msg = f"Snapshot-based calculations: {'WORKING' if len(working_users) > 0 else 'FAILED'}"
        results['steps'].append(f"   {working_msg}")
        print(f"   {working_msg}")
        
        if len(working_users) == 0:
            error_msg = "Snapshot-based calculations failed - checking if we can still proceed with cache regeneration"
            results['steps'].append(f"   ⚠️  WARNING: {error_msg}")
            print(f"   ⚠️  WARNING: {error_msg}")
            # Don't return False here - let's try to regenerate anyway
        
        print()
        
        # Step 5: Clear broken data and regenerate
        print("STEP 5: FIXING LEADERBOARD DATA...")
        results['steps'].append("5. Fixing leaderboard data...")
        
        # Clear existing broken data
        clear_msg = "Clearing existing leaderboard data..."
        results['steps'].append(f"   {clear_msg}")
        print(f"   {clear_msg}")
        
        try:
            deleted_entries = LeaderboardEntry.query.filter(LeaderboardEntry.period.in_(['1D', '5D'])).delete()
            deleted_cache = LeaderboardCache.query.filter(LeaderboardCache.period.in_(['1D', '5D'])).delete()
            db.session.commit()
            
            clear_success = f"Cleared {deleted_entries} entries and {deleted_cache} cache records"
            results['steps'].append(f"   ✅ {clear_success}")
            print(f"   ✅ {clear_success}")
            
        except Exception as e:
            db.session.rollback()
            error_msg = f"Failed to clear old data: {str(e)}"
            results['errors'].append(error_msg)
            results['steps'].append(f"   ❌ {error_msg}")
            print(f"   ❌ {error_msg}")
        
        # Regenerate leaderboard cache
        regen_msg = "Regenerating leaderboard cache..."
        results['steps'].append(f"   {regen_msg}")
        print(f"   {regen_msg}")
        
        try:
            updated_count = update_leaderboard_cache(['1D', '5D'])
            regen_success = f"Updated {updated_count} cache entries"
            results['steps'].append(f"   ✅ {regen_success}")
            print(f"   ✅ {regen_success}")
            
        except Exception as e:
            error_msg = f"Cache update failed: {str(e)}"
            results['errors'].append(error_msg)
            results['steps'].append(f"   ❌ {error_msg}")
            print(f"   ❌ {error_msg}")
            return False, results
        
        print()
        
        # Step 6: Verify the fix
        print("STEP 6: VERIFYING FIX...")
        results['steps'].append("6. Verifying fix...")
        
        final_status = {}
        for period in ['1D', '5D']:
            try:
                cache_entry = LeaderboardCache.query.filter_by(period=period).first()
                entry_count = LeaderboardEntry.query.filter_by(period=period).count()
                
                cache_count = 0
                sample_data = None
                if cache_entry:
                    try:
                        cache_data = json.loads(cache_entry.leaderboard_data)
                        cache_count = len(cache_data)
                        
                        # Show sample data
                        if cache_data:
                            sample_data = cache_data[0]
                            verify_msg = f"{period}: {cache_count} cache entries, {entry_count} DB entries"
                            sample_msg = f"Sample: User {sample_data.get('user_id')} = {sample_data.get('performance_percent', 'N/A')}%"
                            
                            results['steps'].append(f"   {verify_msg}")
                            results['steps'].append(f"      {sample_msg}")
                            print(f"   {verify_msg}")
                            print(f"      {sample_msg}")
                        
                    except Exception as e:
                        parse_msg = f"{period}: Cache parse error - {str(e)}"
                        results['steps'].append(f"   {parse_msg}")
                        print(f"   {parse_msg}")
                else:
                    no_cache_msg = f"{period}: No cache entry created"
                    results['steps'].append(f"   {no_cache_msg}")
                    print(f"   {no_cache_msg}")
                
                final_status[period] = {
                    'cache_count': cache_count,
                    'entry_count': entry_count,
                    'sample_data': sample_data
                }
                
            except Exception as e:
                error_msg = f"Verification for {period} failed: {str(e)}"
                results['errors'].append(error_msg)
                results['steps'].append(f"   {period}: ERROR - {str(e)}")
                print(f"   {period}: ERROR - {str(e)}")
        
        results['final_status'] = final_status
        results['steps'].append("=== FIX COMPLETE ===")
        
        print()
        print("=" * 50)
        print("FIX COMPLETE")
        print("=" * 50)
        
        # Determine success
        success = len(results['errors']) == 0
        total_entries = sum(status.get('cache_count', 0) for status in final_status.values())
        
        results['summary'] = {
            'success': success,
            'total_errors': len(results['errors']),
            'total_cache_entries': total_entries,
            'working_users': len(working_users),
            'periods_fixed': list(final_status.keys())
        }
        
        if success:
            print(f"✅ SUCCESS: Leaderboard fix completed with {total_entries} total entries")
        else:
            print(f"⚠ PARTIAL SUCCESS: Leaderboard fix completed with {len(results['errors'])} errors")
        
        print(f"Working users: {len(working_users)}")
        print(f"Periods fixed: {list(final_status.keys())}")
        print()
        
        return success, results
        
    except Exception as e:
        error_msg = f"CRITICAL ERROR: {str(e)}"
        results['errors'].append(error_msg)
        results['steps'].append(error_msg)
        print(error_msg)
        
        import traceback
        traceback.print_exc()
        return False, results

def run_fix_and_return_json():
    """Run the fix and return results as JSON (for API endpoints)"""
    success, results = comprehensive_leaderboard_fix()
    
    return {
        'success': success,
        'message': f'Leaderboard fix completed with {results["summary"].get("total_cache_entries", 0)} total entries' if success else 'Leaderboard fix completed with errors',
        'results': results,
        'summary': results.get('summary', {})
    }

if __name__ == "__main__":
    print("Running comprehensive leaderboard fix...")
    success, results = comprehensive_leaderboard_fix()
    
    if success:
        print("\n🎉 LEADERBOARD FIX SUCCESSFUL!")
        print("The leaderboard should now show correct data for all users.")
    else:
        print("\n❌ LEADERBOARD FIX FAILED!")
        print("Check the errors above and resolve them before trying again.")
        
    print(f"\nTotal errors: {len(results['errors'])}")
    if results['errors']:
        print("Errors encountered:")
        for error in results['errors']:
            print(f"  - {error}")
