#!/usr/bin/env python3
"""
Debug why 9/26/2025 data point isn't showing in charts
"""

import os
import sys
import json
from datetime import date, datetime
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from models import db, User, PortfolioSnapshot, UserPortfolioChartCache

def debug_chart_data_gap():
    """Debug why 9/26/2025 isn't showing in charts"""
    print("=== DEBUGGING CHART DATA GAP ===")
    
    # Check what snapshots exist around 9/25 and 9/26
    print("\n📸 Portfolio Snapshots around 9/25-9/26:")
    target_dates = [date(2025, 9, 24), date(2025, 9, 25), date(2025, 9, 26), date(2025, 9, 27)]
    
    for target_date in target_dates:
        snapshots = PortfolioSnapshot.query.filter_by(date=target_date).all()
        print(f"  {target_date}: {len(snapshots)} snapshots")
        
        for snapshot in snapshots:
            user = User.query.get(snapshot.user_id)
            username = user.username if user else f"User {snapshot.user_id}"
            print(f"    - {username}: ${snapshot.total_value:.2f}")
    
    # Check what's in the chart cache
    print(f"\n📊 User Chart Cache Contents:")
    users = User.query.all()
    
    for user in users:
        print(f"\n👤 {user.username} (User {user.id}):")
        
        # Check 1M chart cache (most likely to show recent data)
        chart_cache = UserPortfolioChartCache.query.filter_by(
            user_id=user.id, 
            period='1M'
        ).first()
        
        if chart_cache:
            try:
                chart_data = json.loads(chart_cache.chart_data)
                
                # Look at the data points
                if 'data' in chart_data and chart_data['data']:
                    data_points = chart_data['data']
                    print(f"  📈 1M Chart: {len(data_points)} data points")
                    
                    # Show last few data points
                    last_points = data_points[-5:] if len(data_points) >= 5 else data_points
                    print(f"  📅 Last 5 data points:")
                    for point in last_points:
                        if isinstance(point, dict) and 'x' in point and 'y' in point:
                            # Convert timestamp to readable date
                            if isinstance(point['x'], (int, float)):
                                point_date = datetime.fromtimestamp(point['x'] / 1000).date()
                                print(f"    {point_date}: ${point['y']:.2f}")
                            else:
                                print(f"    {point['x']}: ${point['y']:.2f}")
                else:
                    print(f"  ❌ No data points in 1M chart")
                    
            except Exception as e:
                print(f"  ❌ Error parsing chart data: {e}")
        else:
            print(f"  ❌ No 1M chart cache found")
    
    # Check if chart generation logic is working
    print(f"\n🔧 Testing Chart Generation Logic:")
    
    try:
        from leaderboard_utils import generate_user_portfolio_chart
        
        # Test generating a fresh 1M chart for first user
        first_user = users[0] if users else None
        if first_user:
            print(f"\n🧪 Testing fresh 1M chart generation for {first_user.username}:")
            
            fresh_chart = generate_user_portfolio_chart(first_user.id, '1M')
            
            if fresh_chart and 'data' in fresh_chart:
                data_points = fresh_chart['data']
                print(f"  ✅ Generated {len(data_points)} data points")
                
                # Show last few points
                last_points = data_points[-5:] if len(data_points) >= 5 else data_points
                print(f"  📅 Last 5 data points from fresh generation:")
                for point in last_points:
                    if isinstance(point, dict) and 'x' in point and 'y' in point:
                        if isinstance(point['x'], (int, float)):
                            point_date = datetime.fromtimestamp(point['x'] / 1000).date()
                            print(f"    {point_date}: ${point['y']:.2f}")
                        else:
                            print(f"    {point['x']}: ${point['y']:.2f}")
            else:
                print(f"  ❌ Fresh chart generation failed or returned no data")
                
    except Exception as e:
        print(f"  ❌ Error testing chart generation: {e}")
        import traceback
        traceback.print_exc()
    
    # Summary
    print(f"\n📋 DIAGNOSIS:")
    print(f"1. Check if 9/26/2025 snapshots exist in database")
    print(f"2. Check if chart cache includes 9/26/2025 data points")
    print(f"3. Test if fresh chart generation picks up 9/26/2025")
    print(f"4. Identify where the disconnect is happening")

if __name__ == "__main__":
    debug_chart_data_gap()
