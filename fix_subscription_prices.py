#!/usr/bin/env python3
"""
Script to fix missing subscription prices for existing users.
Sets default $4.00 subscription price and Stripe price ID for users who don't have them.
"""

import os
import sys
from datetime import datetime

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from models import db, User
from app import create_app

def fix_subscription_prices():
    """Set default subscription prices for users who don't have them."""
    
    # Create app context
    app = create_app()
    
    with app.app_context():
        # Find users without subscription prices
        users_without_prices = User.query.filter(
            (User.subscription_price == None) | (User.stripe_price_id == None)
        ).all()
        
        print(f"Found {len(users_without_prices)} users without subscription pricing:")
        
        for user in users_without_prices:
            print(f"- {user.username} (ID: {user.id})")
            print(f"  Current subscription_price: {user.subscription_price}")
            print(f"  Current stripe_price_id: {user.stripe_price_id}")
            
            # Set default values
            if user.subscription_price is None:
                user.subscription_price = 4.00
                print(f"  → Set subscription_price to $4.00")
                
            if user.stripe_price_id is None:
                user.stripe_price_id = 'price_1RbX0yQWUhVa3vgDB8vGzoFN'  # Default $4 price
                print(f"  → Set stripe_price_id to default")
            
            print()
        
        # Commit changes
        try:
            db.session.commit()
            print(f"✅ Successfully updated {len(users_without_prices)} users with default subscription pricing.")
        except Exception as e:
            db.session.rollback()
            print(f"❌ Error updating users: {e}")
            return False
    
    return True

if __name__ == '__main__':
    print("🔧 Fixing subscription prices for existing users...")
    success = fix_subscription_prices()
    
    if success:
        print("✅ All users now have subscription pricing configured.")
    else:
        print("❌ Failed to update subscription prices.")
        sys.exit(1)
