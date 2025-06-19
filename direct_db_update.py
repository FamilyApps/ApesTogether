import os
import stripe
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Initialize Stripe
stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')

# Define User model (matching your existing model)
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    subscription_price = db.Column(db.Float, nullable=True)
    stripe_price_id = db.Column(db.String(255), nullable=True)
    # Other fields omitted for brevity

def list_stripe_prices():
    """List available price IDs from Stripe"""
    try:
        prices = stripe.Price.list(active=True, limit=10)
        print("\nAvailable Stripe Prices:")
        print("-" * 50)
        for price in prices.data:
            product = stripe.Product.retrieve(price.product)
            print(f"ID: {price.id}")
            print(f"Product: {product.name}")
            print(f"Amount: ${price.unit_amount/100:.2f} {price.currency}")
            print(f"Recurring: {price.recurring.interval if price.recurring else 'No'}")
            print("-" * 50)
        return prices.data
    except Exception as e:
        print(f"Error listing Stripe prices: {str(e)}")
        return None

def update_user(username, price_id, price_amount):
    """Update a user's subscription price and Stripe price ID"""
    with app.app_context():
        user = User.query.filter_by(username=username).first()
        if not user:
            print(f"User {username} not found")
            return False
        
        print(f"Updating {username}...")
        user.subscription_price = price_amount
        user.stripe_price_id = price_id
        
        try:
            db.session.commit()
            print(f"Successfully updated {username} with price ${price_amount} and price ID {price_id}")
            return True
        except Exception as e:
            db.session.rollback()
            print(f"Error updating {username}: {str(e)}")
            return False

def main():
    """Update problematic users with valid subscription data"""
    # First, list available price IDs
    prices = list_stripe_prices()
    if not prices:
        print("No Stripe prices found or error occurred. Please check your Stripe API key.")
        return
    
    # Ask user to select a price ID
    price_id = input("\nEnter the Stripe price ID to use (copy from above): ")
    price_amount = None
    
    # Find the selected price to get its amount
    for price in prices:
        if price.id == price_id:
            price_amount = price.unit_amount / 100
            break
    
    if not price_amount:
        print(f"Price ID {price_id} not found in the list. Please check and try again.")
        return
    
    # Update problematic users
    users_to_update = ['wild-bronco', 'wise-buffalo']
    for username in users_to_update:
        update_user(username, price_id, price_amount)

if __name__ == "__main__":
    main()
