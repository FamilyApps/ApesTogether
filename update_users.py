import os
from dotenv import load_dotenv
from app import app, db, User
import stripe

# Load environment variables
load_dotenv()

# Set up Stripe API key
stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')

def create_stripe_price(amount, nickname):
    """Create a Stripe price for subscription"""
    try:
        # First create a product
        product = stripe.Product.create(
            name=f"Portfolio Subscription - {nickname}",
            description=f"Monthly subscription to {nickname}'s stock portfolio"
        )
        
        # Then create a price for that product
        price = stripe.Price.create(
            unit_amount=int(amount * 100),  # Convert to cents
            currency="usd",
            recurring={"interval": "month"},
            product=product.id,
            nickname=f"{nickname} Monthly Subscription"
        )
        
        return price.id
    except Exception as e:
        print(f"Error creating Stripe price: {str(e)}")
        return None

def update_user(username, subscription_price):
    """Update a user with subscription data"""
    try:
        user = User.query.filter_by(username=username).first()
        if not user:
            print(f"User {username} not found")
            return False
        
        print(f"Updating user {username}...")
        
        # Create Stripe price
        stripe_price_id = create_stripe_price(subscription_price, username)
        if not stripe_price_id:
            print(f"Failed to create Stripe price for {username}")
            return False
        
        # Update user
        user.subscription_price = subscription_price
        user.stripe_price_id = stripe_price_id
        db.session.commit()
        
        print(f"Successfully updated {username} with price ${subscription_price}/month and Stripe price ID {stripe_price_id}")
        return True
    except Exception as e:
        print(f"Error updating user {username}: {str(e)}")
        db.session.rollback()
        return False

def main():
    """Main function to update problematic users"""
    print("Updating users with subscription data...")
    
    # Update the problematic users with subscription data
    # Using $5.99/month as the subscription price
    update_user('wild-bronco', 5.99)
    update_user('wise-buffalo', 5.99)
    
    print("Done!")

if __name__ == "__main__":
    with app.app_context():
        main()
