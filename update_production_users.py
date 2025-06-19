import os
import requests
import stripe
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def list_stripe_prices():
    """List available price IDs from Stripe"""
    stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')
    if not stripe.api_key:
        print("STRIPE_SECRET_KEY not found in environment variables")
        return None
        
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

def main():
    """
    This script helps update users in the production environment
    by calling the admin route we'll add to the app.
    """
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
    
    # Get the production URL
    production_url = input("\nEnter the production URL (e.g., https://your-app.vercel.app): ")
    
    # Get admin credentials
    email = input("Enter your admin email: ")
    password = input("Enter your admin password: ")
    
    # Login to get session cookie
    print("\nLogging in...")
    session = requests.Session()
    login_response = session.post(
        f"{production_url}/login",
        data={"email": email, "password": password}
    )
    
    if login_response.status_code != 200:
        print(f"Login failed with status code {login_response.status_code}")
        return
    
    # Update problematic users
    users_to_update = ['wild-bronco', 'wise-buffalo']
    for username in users_to_update:
        print(f"Updating {username}...")
        update_response = session.post(
            f"{production_url}/admin/update-user/{username}",
            json={
                "subscription_price": price_amount,
                "stripe_price_id": price_id
            }
        )
        
        if update_response.status_code == 200:
            print(f"Successfully updated {username} with price ${price_amount} and price ID {price_id}")
        else:
            print(f"Failed to update {username}: {update_response.status_code}")
            print(update_response.text)

if __name__ == "__main__":
    main()
