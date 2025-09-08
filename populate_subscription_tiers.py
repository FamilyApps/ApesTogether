"""
Populate subscription tiers with the 5-tier pricing model
Run this after the database migration to set up the tier data
"""
from app import app, db
from models import SubscriptionTier

def populate_subscription_tiers():
    """Populate the subscription_tier table with the 5-tier pricing model"""
    
    # Define the 5 tiers - you'll need to replace these with actual Stripe price IDs
    tiers = [
        {
            'tier_name': 'Light',
            'price': 8.00,
            'max_trades_per_day': 3,
            'stripe_price_id': 'price_1S4tN2HwKH0J9vzFchmuJXTze'
        },
        {
            'tier_name': 'Standard', 
            'price': 12.00,
            'max_trades_per_day': 6,
            'stripe_price_id': 'price_1S4tNdHwKH0J9vzFdJY3Opim'
        },
        {
            'tier_name': 'Active',
            'price': 20.00,
            'max_trades_per_day': 12,
            'stripe_price_id': 'price_1S4tO8HwKH0J9vzFqZBDgCOK'
        },
        {
            'tier_name': 'Pro',
            'price': 30.00,
            'max_trades_per_day': 25,
            'stripe_price_id': 'price_1S4tOYHwKH0J9vzFckMoFWwG'
        },
        {
            'tier_name': 'Elite',
            'price': 50.00,
            'max_trades_per_day': 50,
            'stripe_price_id': 'price_1S4tOtHwKH0J9vzFuxiERwQv'
        }
    ]
    
    with app.app_context():
        # Clear existing tiers
        SubscriptionTier.query.delete()
        
        # Add new tiers
        for tier_data in tiers:
            tier = SubscriptionTier(**tier_data)
            db.session.add(tier)
        
        db.session.commit()
        print(f"Successfully populated {len(tiers)} subscription tiers")
        
        # Verify the data
        all_tiers = SubscriptionTier.query.all()
        for tier in all_tiers:
            print(f"  {tier.tier_name}: ${tier.price}/month, {tier.max_trades_per_day} trades/day")

if __name__ == '__main__':
    populate_subscription_tiers()
