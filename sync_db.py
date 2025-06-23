import os
import json
import requests
from dotenv import load_dotenv
from app import app, db, User, Stock, Subscription

load_dotenv()

def get_vercel_api_token():
    """Get Vercel API token from environment or prompt user."""
    token = os.environ.get('VERCEL_API_TOKEN')
    if not token:
        print("Please enter your Vercel API token:")
        token = input("> ")
    return token

def export_production_db():
    """
    Export production database to a JSON file.
    This would normally use Vercel's API to access production data,
    but for this example we'll create a placeholder.
    """
    print("Exporting production database...")
    
    # In a real implementation, this would call Vercel's API
    # to get a database dump or use a database export tool
    
    # For now, we'll just create a placeholder function
    print("NOTE: This is a placeholder function.")
    print("To properly sync databases, you would need to:")
    print("1. Set up a database export endpoint in your production app")
    print("2. Call that endpoint to get the current production data")
    print("3. Import that data into your local database")
    
    print("\nAlternatively, you could:")
    print("1. Use a database management tool to export your production database")
    print("2. Import the dump into your local development environment")

def import_to_local_db():
    """Import data from JSON file to local database."""
    print("Importing data to local database...")
    
    # This would normally parse the JSON file and insert data into the local database
    print("This would import the production data into your local database.")
    
    # Example of what this would look like:
    """
    with open('production_data.json', 'r') as f:
        data = json.load(f)
    
    # Clear existing data
    db.session.query(Subscription).delete()
    db.session.query(Stock).delete()
    db.session.query(User).delete()
    db.session.commit()
    
    # Import users
    for user_data in data['users']:
        user = User(
            username=user_data['username'],
            email=user_data['email'],
            password_hash=user_data['password_hash'],
            oauth_provider=user_data.get('oauth_provider'),
            oauth_id=user_data.get('oauth_id'),
            stripe_price_id=user_data.get('stripe_price_id'),
            subscription_price=user_data.get('subscription_price'),
            stripe_customer_id=user_data.get('stripe_customer_id')
        )
        db.session.add(user)
    
    db.session.commit()
    
    # Import stocks and subscriptions
    # ...
    """

def create_db_sync_endpoint():
    """Create a database export endpoint in the Flask app."""
    print("To create a database export endpoint, add this code to your app.py file:")
    
    print("""
@app.route('/api/export-db', methods=['GET'])
@login_required
def export_db():
    # Only allow admin users
    if not current_user.email == 'fordutilityapps@gmail.com':
        abort(403)
        
    try:
        # Export users
        users = User.query.all()
        users_data = []
        for user in users:
            user_data = {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'password_hash': user.password_hash,
                'oauth_provider': user.oauth_provider,
                'oauth_id': user.oauth_id,
                'stripe_price_id': user.stripe_price_id,
                'subscription_price': user.subscription_price,
                'stripe_customer_id': user.stripe_customer_id
            }
            users_data.append(user_data)
            
        # Export stocks
        stocks = Stock.query.all()
        stocks_data = []
        for stock in stocks:
            stock_data = {
                'id': stock.id,
                'ticker': stock.ticker,
                'quantity': stock.quantity,
                'purchase_price': stock.purchase_price,
                'purchase_date': stock.purchase_date.isoformat(),
                'user_id': stock.user_id
            }
            stocks_data.append(stock_data)
            
        # Export subscriptions
        subscriptions = Subscription.query.all()
        subscriptions_data = []
        for sub in subscriptions:
            sub_data = {
                'id': sub.id,
                'subscriber_id': sub.subscriber_id,
                'subscribed_to_id': sub.subscribed_to_id,
                'stripe_subscription_id': sub.stripe_subscription_id,
                'status': sub.status
            }
            subscriptions_data.append(sub_data)
            
        # Combine all data
        export_data = {
            'users': users_data,
            'stocks': stocks_data,
            'subscriptions': subscriptions_data
        }
        
        return jsonify(export_data)
    except Exception as e:
        app.logger.error(f"Database export error: {str(e)}")
        return jsonify({'error': str(e)}), 500
    """)

def main():
    print("Database Sync Utility")
    print("=====================")
    print("This tool helps you sync your local development database with production.")
    print()
    
    print("Options:")
    print("1. Export production database to JSON")
    print("2. Import production data to local database")
    print("3. View instructions for creating a database export endpoint")
    print("4. Exit")
    
    choice = input("Enter your choice (1-4): ")
    
    if choice == '1':
        export_production_db()
    elif choice == '2':
        import_to_local_db()
    elif choice == '3':
        create_db_sync_endpoint()
    elif choice == '4':
        print("Exiting...")
    else:
        print("Invalid choice. Please enter a number between 1 and 4.")

if __name__ == "__main__":
    main()
